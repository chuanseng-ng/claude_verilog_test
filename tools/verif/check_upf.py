#!/usr/bin/env python3
# ruff: noqa: E501  (diagnostic messages are kept on one line so they can be grepped from CI logs)
"""Structural checker for ``pnr/constraints/phase5_soc.upf`` against the elaborated ``soc_top`` (bead h3lm).

Why this exists
---------------
``phase5_soc.upf`` was written once (Phase 5 M11) and never read by any tool, so it drifted from
``soc_top`` unnoticed: it named isolation nets and power-switch control ports that do not exist,
clamped every output while the RTL clamps a handful of handshakes, and used option syntax no UPF
parser accepts (audit: bead h3lm).  This checker makes the *structural* faithfulness of the UPF to
the RTL a CI gate.  It does NOT interpret UPF semantics the way a power-aware simulator would
(there is no UPF-aware tool in this repo's open flow); it proves the *references* are real.

What it checks (finding ids are stable; ``-v`` lists them)
-----------------------------------------------------------
  U01  every UPF command and option is one this checker knows (a typo or a non-standard option such
       as ``create_power_switch -on_value`` is an error, not silently ignored)
  U02  every ``-elements`` / ``-exclude_elements`` path exists in the elaborated hierarchy (both arms)
  U03  domain membership: the gated domains name real top-level instances, no instance is in two
       domains, and the ``# upf-check aon <inst>`` roster equals the remaining top-level instances
       (so a new always-on instance, e.g. a new synchroniser, forces a UPF review)
  U04  supply network: every supply net has a source (supply port or switch output), every supply
       set / domain supply handle resolves, every switched rail has an OFF port state
  U05  isolation: control net resolves in RTL, clamp value and sense equal the RTL clamp, every
       element is an OUTPUT port of the domain, and the UPF clamped-signal set EQUALS the RTL
       clamp set (both directions).  Every other output of a gated domain must be classified by a
       ``# upf-check unclamped <class>`` line, so a new output cannot silently escape review
  U06  power switches / retention: a switch's control and acknowledge nets must resolve; retention
       commands are refused (no retention state exists in the RTL)
  U07  power-state group: state names and ``pmu_mode_req`` encodings equal ``rtl/soc/pmu.sv``, each
       state's CPU/GPU rail state equals the PMU's ``dom_target_on`` for that mode, and the scan
       state's claim (clock gates forced open) is true of the RTL
  U08  facts file is complete for the references the UPF makes

Inputs
------
  UPF      pnr/constraints/phase5_soc.upf
  FACTS    pnr/constraints/phase5_soc_rtl_facts.json   GENERATED from the RTL by ``gen-facts``
           (pyslang elaboration of rtl/filelist/soc_top.f, once per arm: asap7, sky130).  The checker
           itself reads only this JSON, so ``check`` needs the standard library alone.
  PMU      rtl/soc/pmu.sv   (mode encodings and per-mode domain targets, parsed as text)

Usage
-----
    python3 tools/verif/check_upf.py                     # check (stdlib only)        exit 0 / 1
    python3 tools/verif/check_upf.py -v                  # also list what was verified
    python3 tools/verif/check_upf.py gen-facts           # (re)write the facts file    needs pyslang
    python3 tools/verif/check_upf.py gen-facts --check   # CI drift gate: facts == fresh elaboration

Exit codes: 0 ok, 1 findings / drift, 2 an input could not be read, 3 pyslang unavailable (gen only).

Scope limits (do not over-read a PASS): this proves references and set equalities.  It does not prove
the UPF is accepted by any particular tool (see docs/design/UPF_POWER_SPEC.md "Tool compatibility"),
nor that a clamp is electrically sufficient.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPF = REPO_ROOT / "pnr/constraints/phase5_soc.upf"
DEFAULT_FACTS = REPO_ROOT / "pnr/constraints/phase5_soc_rtl_facts.json"
DEFAULT_PMU = REPO_ROOT / "rtl/soc/pmu.sv"
DEFAULT_DFT = REPO_ROOT / "rtl/soc/dft/dft_ctrl_ports.sv"
FILELIST = "rtl/filelist/soc_top.f"
TOP = "soc_top"

# Arm selectors: the same defines the sv2v/Yosys flows pass (pnr/Makefile SOC_SV2V_DEFINES,
# SKY130_SOC_SV2V_DEFINES).  The UPF must hold for both: hierarchy at the levels it names is arm-invariant.
ARMS: dict[str, list[str]] = {
    "asap7": ["SRAM_ASAP7", "USE_ICG_CELL", "__pnr__"],
    "sky130": ["SRAM_SKY130", "__pnr__"],
}

UPF_VERSION = "3.0"
CLASSES = ("payload", "slave_response", "observability")
# States the UPF may define beyond the PMU's modes.  SCAN is not a PMU mode: it is the test-mode
# override (soc_top scan_mode_i).  Anything else must come from pmu.sv.
EXTRA_STATES = ("SCAN",)

# --------------------------------------------------------------------------------------------------
# Tcl-ish UPF reader
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Word:
    text: str
    braced: bool = False


@dataclass
class Cmd:
    name: str
    line: int
    words: list[Word] = field(default_factory=list)


def tokenize(text: str) -> list[Cmd]:
    """Split UPF/Tcl text into commands. Handles ``#`` comments, ``\\`` continuations, ``{}`` and ``""``."""
    cmds: list[Cmd] = []
    cur: list[Word] = []
    cur_line = 1
    line = 1
    i, n = 0, len(text)

    def flush() -> None:
        nonlocal cur
        if cur:
            cmds.append(Cmd(cur[0].text, cur_line, cur[1:]))
            cur = []

    while i < n:
        c = text[i]
        if c == "\n":
            flush()
            line += 1
            i += 1
        elif c == ";":
            flush()
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "\\" and text[i + 1 : i + 2] == "\n":
            line += 1
            i += 2
        elif c == "#" and not cur:
            while i < n and text[i] != "\n":
                i += 1
        else:
            if not cur:
                cur_line = line
            if c == "{":
                depth, j = 1, i + 1
                while j < n and depth:
                    if text[j] == "\\":
                        j += 2
                        continue
                    depth += (text[j] == "{") - (text[j] == "}")
                    j += 1
                if depth:
                    raise ValueError(f"line {line}: unbalanced '{{'")
                inner = text[i + 1 : j - 1]
                line += inner.count("\n")
                cur.append(Word(inner.replace("\\\n", " "), True))
                i = j
            elif c == '"':
                j = text.index('"', i + 1)
                cur.append(Word(text[i + 1 : j], False))
                line += text[i:j].count("\n")
                i = j + 1
            else:
                j = i
                while j < n and text[j] not in " \t\r\n;":
                    if text[j] == "\\" and text[j + 1 : j + 2] == "\n":
                        break
                    j += 1
                cur.append(Word(text[i:j], False))
                i = j
    flush()
    return cmds


def split_list(s: str) -> list[str]:
    """Tcl list split: whitespace-separated, ``{...}`` groups kept as one element (braces stripped)."""
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i].isspace():
            i += 1
        elif s[i] == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                depth += (s[j] == "{") - (s[j] == "}")
                j += 1
            out.append(s[i + 1 : j - 1].strip())
            i = j
        else:
            j = i
            while j < n and not s[j].isspace():
                j += 1
            out.append(s[i:j])
            i = j
    return out


# option name -> number of values (0 flag, 1 value).  Repeatable options are simply allowed to repeat.
_SWITCH_OPTS = {
    "-domain": 1, "-input_supply_port": 1, "-output_supply_port": 1, "-control_port": 1,
    "-ack_port": 1, "-on_state": 1, "-off_state": 1, "-on_partial_state": 1, "-error_state": 1,
    "-supply_set": 1, "-ack_delay": 1, "-lib_cells": 1, "-update": 0,
}  # fmt: skip
SPECS: dict[str, tuple[int, dict[str, int]]] = {
    # command: (max positional args, options)
    "upf_version": (1, {}),
    "set_design_top": (1, {}),
    "create_supply_port": (1, {"-direction": 1, "-domain": 1}),
    "create_supply_net": (1, {"-domain": 1, "-reuse": 0}),
    "connect_supply_net": (1, {"-ports": 1}),
    "add_port_state": (1, {"-state": 1}),
    "create_supply_set": (1, {"-function": 1, "-update": 0}),
    "create_power_domain": (1, {
        "-elements": 1, "-exclude_elements": 1, "-supply": 1, "-available_supplies": 1, "-update": 0,
    }),
    "create_power_switch": (1, _SWITCH_OPTS),
    "set_isolation": (1, {
        "-domain": 1, "-isolation_supply_set": 1, "-clamp_value": 1, "-isolation_signal": 1,
        "-isolation_sense": 1, "-elements": 1, "-applies_to": 1, "-location": 1, "-update": 0,
    }),
    "create_power_state_group": (1, {}),
    "add_power_state": (1, {"-supply": 1, "-domain": 1, "-group": 1, "-state": 1, "-update": 0}),
}  # fmt: skip
REFUSED: dict[str, str] = {
    "set_retention": "no retention state exists in the RTL (pmu.sv ret_save/ret_restore drive nothing)",
    "set_retention_control": "no retention state exists in the RTL",
    "map_retention_cell": "no retention state exists in the RTL",
    "map_isolation_cell": "ASAP7/Sky130 libraries carry no isolation cell; the RTL clamp is plain logic",
    "set_level_shifter": "single-voltage design",
    "create_pst": "legacy PST form; use create_power_state_group + add_power_state -group",
    "add_pst_state": "legacy PST form; use create_power_state_group + add_power_state -group",
}


@dataclass
class Parsed:
    cmd: Cmd
    pos: list[str]
    opts: list[tuple[str, Word]]

    def get(self, name: str) -> list[Word]:
        return [w for o, w in self.opts if o == name]

    def one(self, name: str) -> str | None:
        v = self.get(name)
        return v[0].text if v else None

    def lst(self, name: str) -> list[str]:
        out: list[str] = []
        for w in self.get(name):
            out.extend(split_list(w.text))
        return out


@dataclass(frozen=True)
class Finding:
    fid: str
    line: int
    msg: str

    def __str__(self) -> str:
        loc = f"line {self.line}" if self.line else "-"
        return f"  {self.fid} [{loc}] {self.msg}"


# --------------------------------------------------------------------------------------------------
# UPF model
# --------------------------------------------------------------------------------------------------


@dataclass
class Isolation:
    name: str
    line: int
    domain: str
    supply_set: str | None
    clamp: str | None
    signal: str | None
    sense: str | None
    elements: list[str] | None
    location: str | None


@dataclass
class Upf:
    findings: list[Finding] = field(default_factory=list)
    version: str | None = None
    design_top: str | None = None
    ports: dict[str, int] = field(default_factory=dict)  # supply port -> line
    nets: dict[str, int] = field(default_factory=dict)
    connected: dict[str, list[str]] = field(default_factory=dict)  # net -> supply ports
    port_states: dict[str, dict[str, str]] = field(default_factory=dict)
    sets: dict[str, dict[str, str]] = field(default_factory=dict)  # set -> function -> net
    set_line: dict[str, int] = field(default_factory=dict)
    domains: dict[str, dict[str, Any]] = field(default_factory=dict)
    isolations: list[Isolation] = field(default_factory=list)
    switches: list[dict[str, Any]] = field(default_factory=list)
    set_states: dict[str, dict[str, str]] = field(default_factory=dict)  # set -> state -> expr
    group_states: dict[str, dict[str, tuple[str, int]]] = field(default_factory=dict)
    aon_roster: dict[str, int] = field(default_factory=dict)
    unclamped: dict[str, tuple[str, int]] = field(default_factory=dict)  # path -> (class, line)
    aon_domain: str | None = None  # the domain with -elements {.}
    aon_power: str | None = None  # its primary power net

    def err(self, fid: str, line: int, msg: str) -> None:
        self.findings.append(Finding(fid, line, msg))


_DIRECTIVE = re.compile(r"^\s*#\s*upf-check\s+(aon|unclamped)\b(.*)$")


def parse_directives(text: str, up: Upf) -> None:
    for ln, raw in enumerate(text.splitlines(), 1):
        m = _DIRECTIVE.match(raw)
        if not m:
            continue
        kind, rest = m.group(1), m.group(2)
        rest = rest.split("--", 1)[0].strip()
        if kind == "aon":
            toks = rest.split()
            if len(toks) != 1:
                up.err("U03", ln, f"malformed '# upf-check aon' line: {raw.strip()!r}")
            else:
                up.aon_roster[toks[0]] = ln
        else:
            head, _, tail = rest.partition(":")
            cls = head.strip()
            if cls not in CLASSES:
                up.err("U05", ln, f"unclamped class {cls!r} not in {CLASSES}")
                continue
            for p in tail.split():
                up.unclamped[p] = (cls, ln)


def parse_upf(text: str) -> Upf:
    up = Upf()
    parse_directives(text, up)
    try:
        cmds = tokenize(text)
    except ValueError as exc:
        up.err("U01", 0, f"cannot tokenize: {exc}")
        return up
    for cmd in cmds:
        if cmd.name in REFUSED:
            up.err("U01", cmd.line, f"{cmd.name} refused: {REFUSED[cmd.name]}")
            continue
        if cmd.name not in SPECS:
            up.err("U01", cmd.line, f"unknown or unsupported UPF command {cmd.name!r}")
            continue
        npos, ospec = SPECS[cmd.name]
        pos: list[str] = []
        opts: list[tuple[str, Word]] = []
        ws = cmd.words
        k = 0
        bad = False
        while k < len(ws):
            w = ws[k]
            if (
                not w.braced
                and w.text.startswith("-")
                and len(w.text) > 1
                and not w.text[1].isdigit()
            ):
                if w.text not in ospec:
                    up.err("U01", cmd.line, f"{cmd.name}: unknown option {w.text}")
                    bad = True
                    k += 1
                    continue
                if ospec[w.text]:
                    if k + 1 >= len(ws):
                        up.err("U01", cmd.line, f"{cmd.name}: option {w.text} has no value")
                        bad = True
                        k += 1
                        continue
                    opts.append((w.text, ws[k + 1]))
                    k += 2
                else:
                    opts.append((w.text, Word("", False)))
                    k += 1
            else:
                pos.append(w.text)
                k += 1
        if len(pos) > npos:
            up.err("U01", cmd.line, f"{cmd.name}: unexpected extra arguments {pos[npos:]}")
            bad = True
        if not bad:
            _apply(up, Parsed(cmd, pos, opts))
    return up


def _apply(up: Upf, p: Parsed) -> None:
    c, ln = p.cmd.name, p.cmd.line
    a0 = p.pos[0] if p.pos else None
    if c == "upf_version":
        up.version = a0
    elif c == "set_design_top":
        up.design_top = a0
    elif c == "create_supply_port":
        if a0 is None or p.one("-direction") not in ("in", "out", "inout"):
            up.err("U04", ln, "create_supply_port needs a name and -direction in|out|inout")
        elif a0 in up.ports:
            up.err("U04", ln, f"supply port {a0} created twice")
        else:
            up.ports[a0] = ln
    elif c == "create_supply_net":
        if a0 is None:
            up.err("U04", ln, "create_supply_net needs a name")
        elif a0 in up.nets and not p.get("-reuse"):
            up.err("U04", ln, f"supply net {a0} created twice")
        elif a0 not in up.nets and p.get("-reuse"):
            up.err("U04", ln, f"supply net {a0}: -reuse but the net does not exist")
        else:
            up.nets[a0] = ln
    elif c == "connect_supply_net":
        ports = p.lst("-ports")
        if a0 not in up.nets:
            up.err("U04", ln, f"connect_supply_net: net {a0} not created")
        for port in ports:
            if port not in up.ports:
                up.err("U04", ln, f"connect_supply_net {a0}: {port} is not a supply port")
        up.connected.setdefault(a0 or "?", []).extend(ports)
    elif c == "add_port_state":
        if a0 not in up.ports:
            up.err("U04", ln, f"add_port_state: {a0} is not a supply port")
        for w in p.get("-state"):
            parts = split_list(w.text)
            if len(parts) != 2 or not (parts[1] == "off" or re.fullmatch(r"[0-9.]+", parts[1])):
                up.err(
                    "U04",
                    ln,
                    f"add_port_state {a0}: -state must be {{NAME voltage|off}}, got {w.text!r}",
                )
            else:
                up.port_states.setdefault(a0 or "?", {})[parts[0]] = parts[1]
    elif c == "create_supply_set":
        fns: dict[str, str] = {}
        for w in p.get("-function"):
            parts = split_list(w.text)
            if len(parts) != 2 or parts[0] not in ("power", "ground", "nwell", "pwell"):
                up.err("U04", ln, f"create_supply_set {a0}: bad -function {w.text!r}")
            else:
                fns[parts[0]] = parts[1]
        if a0 is None or "power" not in fns or "ground" not in fns:
            up.err("U04", ln, f"create_supply_set {a0}: needs power and ground functions")
        else:
            up.sets[a0] = fns
            up.set_line[a0] = ln
    elif c == "create_power_domain":
        sup: dict[str, str] = {}
        for w in p.get("-supply"):
            parts = split_list(w.text)
            if len(parts) != 2:
                up.err("U04", ln, f"create_power_domain {a0}: bad -supply {w.text!r}")
            else:
                sup[parts[0]] = parts[1]
        if a0 is None or a0 in up.domains:
            up.err("U03", ln, f"create_power_domain: missing or duplicate name {a0}")
        else:
            up.domains[a0] = {
                "line": ln, "elements": p.lst("-elements"), "exclude": p.lst("-exclude_elements"),
                "supply": sup, "available": p.lst("-available_supplies"),
            }  # fmt: skip
    elif c == "create_power_switch":
        sw: dict[str, Any] = {"name": a0, "line": ln, "domain": p.one("-domain")}
        for key in ("-input_supply_port", "-output_supply_port", "-control_port", "-ack_port"):
            sw[key] = [tuple(split_list(w.text)) for w in p.get(key)]
        up.switches.append(sw)
    elif c == "set_isolation":
        els = p.lst("-elements") if p.get("-elements") else None
        up.isolations.append(Isolation(
            a0 or "?", ln, p.one("-domain") or "", p.one("-isolation_supply_set"), p.one("-clamp_value"),
            p.one("-isolation_signal"), p.one("-isolation_sense"), els, p.one("-location"),
        ))  # fmt: skip
    elif c == "create_power_state_group":
        up.group_states.setdefault(a0 or "?", {})
    elif c == "add_power_state":
        _apply_power_state(up, p)


def _apply_power_state(up: Upf, p: Parsed) -> None:
    ln = p.cmd.line
    target_supply = p.one("-supply") or (
        p.pos[0] if p.pos and not p.get("-group") and not p.get("-domain") else None
    )
    group = p.one("-group")
    for w in p.get("-state"):
        parts = split_list(w.text)
        if not parts:
            up.err("U07", ln, "add_power_state: empty -state")
            continue
        name = parts[0]
        body = " ".join(parts[1:])
        m = re.search(r"-(supply_expr|logic_expr)\s*\{(.*)\}\s*$", w.text, re.S) or re.search(
            r"-(supply_expr|logic_expr)\s*\{(.*?)\}\s*(?:-\w+.*)?$", w.text, re.S
        )
        if not m:
            up.err(
                "U07",
                ln,
                f"add_power_state state {name}: needs -supply_expr or -logic_expr ({body!r})",
            )
            continue
        expr = " ".join(_brace_arg(w.text, m.group(1)).split())
        if group:
            if group not in up.group_states:
                up.err("U07", ln, f"add_power_state -group {group}: group not created")
            else:
                up.group_states[group][name] = (expr, ln)
        elif target_supply:
            if target_supply not in up.sets:
                up.err(
                    "U07", ln, f"add_power_state -supply {target_supply}: supply set not created"
                )
            up.set_states.setdefault(target_supply, {})[name] = expr
        else:
            up.err("U07", ln, "add_power_state: need -supply <set> or -group <group>")


def _brace_arg(s: str, opt: str) -> str:
    """Return the balanced ``{...}`` that follows ``-opt`` inside a state body."""
    k = s.index("-" + opt) + len(opt) + 1
    while s[k].isspace():
        k += 1
    if s[k] != "{":
        return s[k:].split()[0]
    depth, j = 1, k + 1
    while depth:
        depth += (s[j] == "{") - (s[j] == "}")
        j += 1
    return s[k + 1 : j - 1]


# --------------------------------------------------------------------------------------------------
# References the UPF makes into the RTL (also drives gen-facts)
# --------------------------------------------------------------------------------------------------

_LITERAL = re.compile(r"^\d+'[bBhHdD][0-9a-fA-F_]+$")


def logic_terms(expr: str) -> list[tuple[str, str]]:
    """Split a ``a == b && c == d`` expression into (lhs, rhs) pairs; a bare term has rhs ''."""
    out: list[tuple[str, str]] = []
    for term in expr.split("&&"):
        term = term.strip()
        m = re.fullmatch(r"(\S+)\s*==\s*(\S+)", term)
        out.append((m.group(1), m.group(2)) if m else (term, ""))
    return out


def rtl_net_refs(up: Upf) -> set[str]:
    """Every design-net name the UPF refers to (isolation signals, switch nets, logic_expr nets)."""
    refs: set[str] = set()
    for iso in up.isolations:
        if iso.signal:
            refs.add(iso.signal)
    for sw in up.switches:
        for key in ("-control_port", "-ack_port"):
            for tup in sw[key]:
                if len(tup) == 2:
                    refs.add(tup[1])
    for states in up.group_states.values():
        for expr, _ln in states.values():
            for lhs, _rhs in logic_terms(expr):
                if lhs not in up.sets:
                    refs.add(lhs)
    return refs


def rtl_path_refs(up: Upf) -> set[str]:
    """Every hierarchical instance path the UPF names (domain elements / excludes, isolation elements)."""
    refs: set[str] = set()
    for d in up.domains.values():
        for e in d["elements"] + d["exclude"]:
            if e != ".":
                refs.add(e)
    for iso in up.isolations:
        for e in iso.elements or []:
            refs.add(e.rsplit("/", 1)[0] if "/" in e else e)
    return refs


# --------------------------------------------------------------------------------------------------
# pmu.sv facts (text parse; the checker stays stdlib-only)
# --------------------------------------------------------------------------------------------------


def parse_pmu(text: str) -> dict[str, Any]:
    modes = {
        m.group(1): int(m.group(2), 2) for m in re.finditer(r"MODE_(\w+)\s*=\s*2'b([01]{2})", text)
    }
    targets: dict[str, dict[str, int]] = {}
    for m in re.finditer(r"MODE_(\w+):\s*begin(.*?)\bend\b", text, re.S):
        body = m.group(2)
        cpu = re.search(r"dom_target_on\[DOM_CPU\]\s*=\s*1'b([01])", body)
        gpu = re.search(r"dom_target_on\[DOM_GPU\]\s*=\s*1'b([01])", body)
        if cpu and gpu:
            targets[m.group(1)] = {"cpu": int(cpu.group(1)), "gpu": int(gpu.group(1))}
    return {"modes": modes, "targets": targets}


# --------------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------------


def _domain_elems(up: Upf, dom: str) -> list[str]:
    return [e for e in up.domains[dom]["elements"] if e != "."]


def check(
    up: Upf, facts: dict[str, Any], pmu: dict[str, Any], dft_text: str, log: list[str]
) -> list[Finding]:
    f = up.findings
    arms: dict[str, Any] = facts.get("arms", {})
    if not arms:
        up.err("U08", 0, "facts file has no arms; run gen-facts")
        return f
    if up.version != UPF_VERSION:
        up.err("U01", 0, f"upf_version must be {UPF_VERSION} (IEEE 1801-2015), got {up.version!r}")
    if up.design_top != facts.get("top", TOP):
        up.err("U01", 0, f"set_design_top must name {facts.get('top', TOP)}, got {up.design_top!r}")

    _check_supply(up, log)
    gated = _check_domains(up, arms, log)
    _check_isolation(up, arms, gated, log)
    _check_switch_and_net_refs(up, arms, log)
    _check_pst(up, arms, pmu, dft_text, log)
    return f


def _check_supply(up: Upf, log: list[str]) -> None:
    sourced: set[str] = set()
    for net, ports in up.connected.items():
        if ports:
            sourced.add(net)
    for sw in up.switches:
        for tup in sw["-output_supply_port"]:
            if len(tup) == 2:
                sourced.add(tup[1])
    for net, ln in up.nets.items():
        if net not in sourced:
            up.err(
                "U04",
                ln,
                f"supply net {net} has no source (no connect_supply_net to a port, no switch output)",
            )
    for port, ln in up.ports.items():
        if not any(port in ports for ports in up.connected.values()):
            up.err("U04", ln, f"supply port {port} is not connected to any supply net")
    for name, fns in up.sets.items():
        for fn, net in fns.items():
            if net not in up.nets:
                up.err(
                    "U04", up.set_line[name], f"supply set {name}: {fn} net {net} does not exist"
                )
    for dname, d in up.domains.items():
        prim = d["supply"].get("primary")
        if prim not in up.sets:
            up.err("U04", d["line"], f"domain {dname}: primary supply set {prim!r} does not exist")
        for s in d["available"]:
            if s not in up.sets:
                up.err(
                    "U04", d["line"], f"domain {dname}: available supply set {s!r} does not exist"
                )
    # A rail that can be OFF (its port has an off state) must say so in its supply set's states.
    for sname, fns in up.sets.items():
        net = fns.get("power", "")
        ports = up.connected.get(net, [])
        can_off = any("off" in up.port_states.get(pt, {}).values() for pt in ports)
        states = up.set_states.get(sname, {})
        has_off = any("OFF" in e for e in states.values())
        if can_off and not has_off:
            up.err(
                "U04",
                up.set_line[sname],
                f"supply set {sname}: rail {net} can be off but no OFF power state is defined",
            )
        if not can_off and has_off:
            up.err(
                "U04",
                up.set_line[sname],
                f"supply set {sname}: OFF state defined but rail {net} has no off port state",
            )
        if sname not in up.set_states:
            up.err("U04", up.set_line[sname], f"supply set {sname}: no add_power_state")
    log.append(f"supply: {len(up.ports)} ports, {len(up.nets)} nets, {len(up.sets)} sets")


def _check_domains(up: Upf, arms: dict[str, Any], log: list[str]) -> dict[str, list[str]]:
    """Returns {gated domain: [instance]} (domains whose primary rail differs from the always-on rail)."""
    gated: dict[str, list[str]] = {}
    aon_dom = None
    for dname, d in up.domains.items():
        if "." in d["elements"]:
            aon_dom = dname
    if aon_dom is None:
        up.err(
            "U03",
            0,
            "no domain has -elements {.}; top-level glue logic (the clamps) would be in no domain",
        )
        return gated
    aon_power = up.sets.get(up.domains[aon_dom]["supply"].get("primary", ""), {}).get("power")
    up.aon_domain = aon_dom
    up.aon_power = aon_power
    seen: dict[str, str] = {}
    for dname, d in up.domains.items():
        if dname == aon_dom:
            continue
        for e in d["elements"]:
            if e in seen:
                up.err("U03", d["line"], f"{e} is an element of both {seen[e]} and {dname}")
            seen[e] = dname
        prim = up.sets.get(d["supply"].get("primary", ""), {}).get("power")
        if prim != aon_power:
            gated[dname] = d["elements"]
    excluded = set(up.domains[aon_dom]["exclude"])
    if excluded != set(seen):
        up.err(
            "U03",
            up.domains[aon_dom]["line"],
            f"{aon_dom} -exclude_elements {sorted(excluded)} != other domains' elements {sorted(seen)}",
        )
    for arm, af in arms.items():
        insts: dict[str, str] = af["instances"]
        for dname, d in up.domains.items():
            for e in d["elements"] + d["exclude"]:
                if e == ".":
                    continue
                if e not in af["paths"] or af["paths"][e] is None:
                    up.err(
                        "U02",
                        d["line"],
                        f"[{arm}] {dname}: element {e!r} does not exist in elaborated {TOP}",
                    )
        expected_aon = set(insts) - set(seen)
        roster = set(up.aon_roster)
        for miss in sorted(expected_aon - roster):
            up.err(
                "U03",
                0,
                f"[{arm}] top-level instance {miss} ({insts[miss]}) is in {aon_dom} but not in the '# upf-check aon' roster",
            )
        for extra in sorted(roster - expected_aon):
            up.err(
                "U03",
                up.aon_roster[extra],
                f"[{arm}] roster names {extra} which is not an always-on top-level instance",
            )
    log.append(
        f"domains: {len(up.domains)} ({', '.join(up.domains)}); gated: {', '.join(gated) or 'none'}; aon roster: {len(up.aon_roster)} instances"
    )
    return gated


def _check_isolation(
    up: Upf, arms: dict[str, Any], gated: dict[str, list[str]], log: list[str]
) -> None:
    covered_domains: set[str] = set()
    aon_power = up.aon_power
    for iso in up.isolations:
        ln = iso.line
        if iso.domain not in up.domains:
            up.err("U05", ln, f"{iso.name}: domain {iso.domain!r} does not exist")
            continue
        covered_domains.add(iso.domain)
        if iso.domain not in gated:
            up.err("U05", ln, f"{iso.name}: domain {iso.domain} is always-on; nothing to isolate")
        if iso.supply_set not in up.sets:
            up.err(
                "U05",
                ln,
                f"{iso.name}: -isolation_supply_set {iso.supply_set!r} is not a supply set",
            )
        elif up.sets[iso.supply_set].get("power") != aon_power:
            up.err(
                "U05",
                ln,
                f"{iso.name}: isolation supply {iso.supply_set} is not the always-on rail; the clamp would die with the domain",
            )
        if iso.location != "parent":
            up.err(
                "U05",
                ln,
                f"{iso.name}: -location must be 'parent' (soc_top clamps sit outside u_cpu/u_gpu), got {iso.location!r}",
            )
        if iso.clamp not in ("0", "1"):
            up.err("U05", ln, f"{iso.name}: -clamp_value must be 0 or 1, got {iso.clamp!r}")
        if iso.sense not in ("high", "low"):
            up.err("U05", ln, f"{iso.name}: -isolation_sense must be high|low, got {iso.sense!r}")
        if iso.elements is None:
            up.err(
                "U05",
                ln,
                f"{iso.name}: -elements is required (the clamp set is exactly the RTL's, not 'all outputs')",
            )
    for dom in gated:
        if dom not in covered_domains:
            up.err("U05", up.domains[dom]["line"], f"gated domain {dom} has no set_isolation")

    for arm, af in arms.items():
        rtl = {c["element"]: c for c in af["clamps"]}
        ports = af["ports"]
        upf_elems: dict[str, Isolation] = {}
        for iso in up.isolations:
            for e in iso.elements or []:
                inst, _, port = e.rpartition("/")
                if inst not in ports or port not in ports[inst]:
                    up.err(
                        "U05",
                        iso.line,
                        f"[{arm}] {iso.name}: element {e} is not a port of {inst or '?'}",
                    )
                    continue
                if ports[inst][port][0] != "out":
                    up.err(
                        "U05",
                        iso.line,
                        f"[{arm}] {iso.name}: element {e} is an {ports[inst][port][0]}put; applies_to outputs only",
                    )
                if inst not in up.domains.get(iso.domain, {}).get("elements", []):
                    up.err(
                        "U05",
                        iso.line,
                        f"[{arm}] {iso.name}: {e} is not inside domain {iso.domain}",
                    )
                if e in upf_elems:
                    up.err(
                        "U05",
                        iso.line,
                        f"[{arm}] {e} isolated twice ({upf_elems[e].name}, {iso.name})",
                    )
                upf_elems[e] = iso
        for e, iso in upf_elems.items():
            c = rtl.get(e)
            if c is None:
                up.err("U05", iso.line, f"[{arm}] UPF isolates {e} but soc_top does not clamp it")
                continue
            if iso.signal != c["iso"]:
                up.err(
                    "U05",
                    iso.line,
                    f"[{arm}] {e}: UPF isolation_signal {iso.signal!r} != RTL clamp net {c['iso']!r}",
                )
            if iso.clamp != str(c["clamp"]):
                up.err(
                    "U05",
                    iso.line,
                    f"[{arm}] {e}: UPF clamp_value {iso.clamp} != RTL clamp {c['clamp']}",
                )
            if iso.sense != c["sense"]:
                up.err(
                    "U05",
                    iso.line,
                    f"[{arm}] {e}: UPF isolation_sense {iso.sense} != RTL sense {c['sense']}",
                )
        for e in sorted(set(rtl) - set(upf_elems)):
            up.err(
                "U05",
                0,
                f"[{arm}] soc_top clamps {e} (net {rtl[e]['iso']}) but the UPF does not isolate it",
            )
        # Everything else that leaves a gated domain must be classified.
        gated_insts = {i for els in gated.values() for i in els}
        outs = {
            f"{i}/{p}"
            for i in gated_insts
            if i in ports
            for p, (d, _w) in ports[i].items()
            if d == "out"
        }
        for e in sorted(outs - set(upf_elems) - set(up.unclamped)):
            up.err(
                "U05",
                0,
                f"[{arm}] output {e} of a gated domain is neither isolated nor classified by '# upf-check unclamped'",
            )
        for e in sorted(set(up.unclamped) - outs):
            up.err(
                "U05",
                up.unclamped[e][1],
                f"[{arm}] unclamped list names {e}, which is not an output of a gated domain",
            )
        for e in sorted(set(up.unclamped) & set(upf_elems)):
            up.err("U05", up.unclamped[e][1], f"[{arm}] {e} is both isolated and listed unclamped")
        log.append(
            f"isolation[{arm}]: {len(upf_elems)} UPF-isolated == {len(rtl)} RTL-clamped; {len(set(up.unclamped) & outs)} outputs classified unclamped"
        )


def _check_switch_and_net_refs(up: Upf, arms: dict[str, Any], log: list[str]) -> None:
    for sw in up.switches:
        if sw["domain"] not in up.domains:
            up.err(
                "U06", sw["line"], f"switch {sw['name']}: domain {sw['domain']!r} does not exist"
            )
        for key in ("-input_supply_port", "-output_supply_port"):
            for tup in sw[key]:
                if len(tup) != 2 or tup[1] not in up.nets:
                    up.err(
                        "U06",
                        sw["line"],
                        f"switch {sw['name']}: {key} {tup} does not name a supply net",
                    )
        if not sw["-control_port"]:
            up.err("U06", sw["line"], f"switch {sw['name']}: no -control_port")
    for arm, af in arms.items():
        nets = af["nets"]
        for ref in sorted(rtl_net_refs(up)):
            if ref not in nets:
                up.err(
                    "U08",
                    0,
                    f"[{arm}] net {ref!r} is referenced by the UPF but absent from the facts file; run gen-facts",
                )
            elif nets[ref] is None:
                up.err("U06" if any(ref == t[1] for sw in up.switches for k in ("-control_port", "-ack_port") for t in sw[k] if len(t) == 2) else "U05",
                       0, f"[{arm}] net {ref!r} referenced by the UPF does not resolve in elaborated {TOP}")  # fmt: skip
        for ref in sorted(rtl_path_refs(up)):
            if ref not in af["paths"]:
                up.err(
                    "U08",
                    0,
                    f"[{arm}] path {ref!r} is referenced by the UPF but absent from the facts file; run gen-facts",
                )


def _check_pst(
    up: Upf, arms: dict[str, Any], pmu: dict[str, Any], dft_text: str, log: list[str]
) -> None:
    if not up.group_states:
        up.err("U07", 0, "no power-state group (create_power_state_group)")
        return
    modes: dict[str, int] = pmu["modes"]
    targets: dict[str, dict[str, int]] = pmu["targets"]
    if not modes:
        up.err("U07", 0, "could not parse MODE_* encodings from pmu.sv")
        return
    for gname, states in up.group_states.items():
        names = set(states)
        want = set(modes)
        for miss in sorted(want - names):
            up.err("U07", 0, f"group {gname}: PMU mode {miss} (pmu.sv) has no power state")
        for extra in sorted(names - want - set(EXTRA_STATES)):
            up.err(
                "U07",
                states[extra][1],
                f"group {gname}: state {extra} is not a pmu.sv mode and not in {EXTRA_STATES}",
            )
        cpu_set, gpu_set = _domain_set(up, "PD_CPU"), _domain_set(up, "PD_GPU")
        aon_set = up.domains.get(up.aon_domain or "", {}).get("supply", {}).get("primary")
        for name, (expr, ln) in states.items():
            terms = dict(logic_terms(expr))
            supply = {k: v for k, v in terms.items() if k in up.sets}
            nets = {k: v for k, v in terms.items() if k not in up.sets}
            for k, v in supply.items():
                if v not in up.set_states.get(k, {}):
                    up.err("U07", ln, f"state {name}: {k} == {v} but {k} has no state {v}")
            scan = nets.get("scan_mode_i")
            if name == "SCAN":
                if scan != "1'b1":
                    up.err("U07", ln, f"state SCAN must require scan_mode_i == 1'b1, got {scan!r}")
                if "u_pmu/pmu_mode_req" in nets:
                    up.err(
                        "U07",
                        ln,
                        "state SCAN must not depend on pmu_mode_req (the scan override is independent of the PMU)",
                    )
                for s in (aon_set, cpu_set, gpu_set):
                    if s and supply.get(s) != "ON":
                        up.err(
                            "U07",
                            ln,
                            f"state SCAN must have every rail ON; {s} == {supply.get(s)!r}",
                        )
                _check_scan_claim(up, arms, dft_text, ln)
                continue
            if name not in modes:
                continue
            if scan != "1'b0":
                up.err(
                    "U07",
                    ln,
                    f"state {name} must require scan_mode_i == 1'b0 so it is exclusive with SCAN, got {scan!r}",
                )
            enc = nets.get("u_pmu/pmu_mode_req")
            if (
                enc is None
                or not re.fullmatch(r"2'b[01]{2}", enc)
                or int(enc[3:], 2) != modes[name]
            ):
                up.err(
                    "U07",
                    ln,
                    f"state {name}: pmu_mode_req encoding {enc!r} != pmu.sv MODE_{name} = 2'b{modes[name]:02b}",
                )
            tgt = targets.get(name)
            if tgt is None:
                up.err("U07", ln, f"state {name}: pmu.sv has no dom_target_on row for MODE_{name}")
                continue
            for label, sset, on in (("CPU", cpu_set, tgt["cpu"]), ("GPU", gpu_set, tgt["gpu"])):
                got = supply.get(sset or "")
                if got != ("ON" if on else "OFF"):
                    up.err(
                        "U07",
                        ln,
                        f"state {name}: {label} rail {sset} == {got!r} but pmu.sv dom_target_on says {'ON' if on else 'OFF'}",
                    )
            if aon_set and supply.get(aon_set) != "ON":
                up.err("U07", ln, f"state {name}: always-on rail {aon_set} must be ON")
    log.append(
        f"power states: {', '.join(next(iter(up.group_states.values())))} (names/encodings/targets match pmu.sv)"
    )


def _domain_set(up: Upf, dom: str) -> str | None:
    d = up.domains.get(dom)
    return d["supply"].get("primary") if d else None


def _check_scan_claim(up: Upf, arms: dict[str, Any], dft_text: str, ln: int) -> None:
    """SCAN says 'all domains ON, clock gates forced open'. True iff each gate's test_en is dft_test_en and
    dft_ctrl_ports drives test_en_o from scan_mode_i."""
    if not re.search(r"assign\s+test_en_o\s*=\s*scan_mode_i\b", dft_text):
        up.err("U07", ln, "SCAN: dft_ctrl_ports.sv no longer drives test_en_o from scan_mode_i")
    for arm, af in arms.items():
        gates = af.get("clock_gates", {})
        if not gates:
            up.err("U07", ln, f"[{arm}] SCAN: no rv32i_clock_gate at top level in the facts")
        for g, info in gates.items():
            if info.get("test_en") != af.get("test_en_net"):
                up.err(
                    "U07",
                    ln,
                    f"[{arm}] SCAN: clock gate {g} test_en is {info.get('test_en')!r}, not the dft test-enable net {af.get('test_en_net')!r}",
                )


# --------------------------------------------------------------------------------------------------
# Facts generation (pyslang)
# --------------------------------------------------------------------------------------------------


def _elaborate(arm: str) -> Any:
    from pyslang.driver import CommandLineOptions, Driver  # noqa: PLC0415 - optional dependency

    d = Driver()
    d.addStandardArgs()
    args = f"slang --ignore-unknown-modules --top {TOP} -f {FILELIST} " + " ".join(
        f"-D{x}" for x in ARMS[arm]
    )
    if not (
        d.parseCommandLine(args, CommandLineOptions())
        and d.processOptions()
        and d.parseAllSources()
    ):
        raise RuntimeError(f"slang could not load {FILELIST} for arm {arm}")
    comp = d.createCompilation()
    tops = [i for i in comp.getRoot().topInstances if i.name == TOP]
    if not tops:
        raise RuntimeError(f"{TOP} not found for arm {arm}")
    return tops[0]


def _find_member(body: Any, name: str, kinds: tuple[str, ...]) -> Any:
    for m in body:
        if m.name == name and str(m.kind).split(".")[-1] in kinds:
            return m
    return None


def _walk_instance(top: Any, path: str) -> Any:
    cur = top
    for seg in path.split("/"):
        cur = _find_member(cur.body, seg, ("Instance",))
        if cur is None:
            return None
    return cur


def _unwrap(e: Any) -> Any:
    while str(e.kind).endswith("Conversion"):
        e = e.operand
    return e


def _sym_name(e: Any) -> str | None:
    e = _unwrap(e)
    sym = getattr(e, "symbol", None)
    return sym.name if sym is not None and str(e.kind).endswith("NamedValue") else None


def _const_int(e: Any) -> int | None:
    e = _unwrap(e)
    v = getattr(e, "constant", None)
    if v is None:
        return None
    try:
        return (
            int(str(v).split("'")[-1].lstrip("bdhBDH"), 2 if "'b" in str(v).lower() else 10)
            if "'" in str(v)
            else int(str(v))
        )
    except ValueError:
        return None


def build_facts_arm(arm: str, up: Upf) -> dict[str, Any]:
    top = _elaborate(arm)
    body = top.body
    insts = {m.name: m.body.definition.name for m in body if str(m.kind).endswith("Instance")}
    gated_insts = sorted(
        {e for d in up.domains.values() if "." not in d["elements"] for e in d["elements"]}
    )
    iso_insts = sorted(
        {e.rsplit("/", 1)[0] for iso in up.isolations for e in iso.elements or []}
        | set(gated_insts)
    )

    ports: dict[str, dict[str, list[Any]]] = {}
    driver_of: dict[
        str, tuple[str, str]
    ] = {}  # net -> (instance, port) for top-level instance outputs
    for m in body:
        if not str(m.kind).endswith("Instance"):
            continue
        for pc in m.portConnections:
            if str(pc.port.direction).endswith("Out") and pc.expression is not None:
                lhs = getattr(pc.expression, "left", None)
                nm = _sym_name(lhs) if lhs is not None else None
                if nm:
                    driver_of[nm] = (m.name, pc.port.name)
        if m.name in iso_insts:
            ports[m.name] = {
                p.name: ["out" if str(p.direction).endswith("Out") else "in", int(p.type.bitWidth)]
                for p in m.body.portList
            }

    clamps: list[dict[str, Any]] = []
    for m in body:
        if not str(m.kind).endswith("ContinuousAssign"):
            continue
        r = _unwrap(m.assignment.right)
        if not str(r.kind).endswith("ConditionalOp"):
            continue
        cond = r.conditions[0].expr
        sense = "high"
        if str(cond.kind).endswith("UnaryOp"):
            cond, sense = cond.operand, "low"
        iso = _sym_name(cond)
        val = _const_int(r.left) if sense == "high" else _const_int(r.right)
        src = _sym_name(r.right) if sense == "high" else _sym_name(r.left)
        if not iso or "iso" not in iso or val is None or not src:
            continue
        drv = driver_of.get(src)
        clamps.append({
            "element": f"{drv[0]}/{drv[1]}" if drv else f"?/{src}",
            "iso": iso, "clamp": val, "sense": sense,
        })  # fmt: skip
    clamps.sort(key=lambda c: c["element"])

    def resolve_net(path: str) -> dict[str, Any] | None:
        parts = path.split("/")
        cur = top
        for seg in parts[:-1]:
            cur = _find_member(cur.body, seg, ("Instance",))
            if cur is None:
                return None
        m = _find_member(cur.body, parts[-1], ("Variable", "Net", "Port"))
        if m is None:
            return None
        return {
            "kind": "port" if str(m.kind).endswith("Port") else "net",
            "width": int(m.type.bitWidth),
        }

    paths = {}
    for pth in sorted(rtl_path_refs(up)):
        inst = _walk_instance(top, pth)
        paths[pth] = inst.body.definition.name if inst is not None else None

    clock_gates: dict[str, dict[str, Any]] = {}
    test_en_net = None
    for m in body:
        if str(m.kind).endswith("Instance") and m.body.definition.name == "rv32i_clock_gate":
            te = None
            for pc in m.portConnections:
                if pc.port.name == "test_en":
                    te = _sym_name(pc.expression) or str(pc.expression)
            clock_gates[m.name] = {"test_en": te}
        if str(m.kind).endswith("Instance") and m.body.definition.name == "dft_ctrl":
            for pc in m.portConnections:
                if pc.port.name == "test_en_o":
                    lhs = getattr(pc.expression, "left", None)
                    test_en_net = _sym_name(lhs) if lhs is not None else None

    return {
        "defines": ARMS[arm],
        "instances": dict(sorted(insts.items())),
        "ports": ports,
        "clamps": clamps,
        "paths": paths,
        "nets": {n: resolve_net(n) for n in sorted(rtl_net_refs(up))},
        "clock_gates": dict(sorted(clock_gates.items())),
        "test_en_net": test_en_net,
    }


def build_facts(up: Upf) -> dict[str, Any]:
    return {
        "_comment": "GENERATED by tools/verif/check_upf.py gen-facts from rtl/filelist/soc_top.f - DO NOT EDIT. "
        "CI runs 'gen-facts --check' and fails on any difference.",
        "schema": 1,
        "top": TOP,
        "filelist": FILELIST,
        "arms": {arm: build_facts_arm(arm, up) for arm in ARMS},
    }


def dump_facts(facts: dict[str, Any]) -> str:
    return json.dumps(facts, indent=1, sort_keys=True) + "\n"


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------


def run_check(upf: Path, facts_path: Path, pmu_path: Path, dft_path: Path, verbose: bool) -> int:
    try:
        text = upf.read_text()
        facts = json.loads(facts_path.read_text())
        pmu = parse_pmu(pmu_path.read_text())
        dft_text = dft_path.read_text()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"check_upf: cannot read an input: {exc}", file=sys.stderr)
        return 2
    up = parse_upf(text)
    log: list[str] = []
    findings = check(up, facts, pmu, dft_text, log)
    if verbose or not findings:
        for ln in log:
            print(f"  ok  {ln}")
    if findings:
        print(
            f"check_upf: FAIL - {len(findings)} finding(s) in {upf.relative_to(REPO_ROOT) if upf.is_relative_to(REPO_ROOT) else upf}"
        )
        for fd in sorted(set(findings), key=lambda x: (x.fid, x.line, x.msg)):
            print(fd)
        return 1
    print(
        "check_upf: PASS - UPF references and clamp/state sets match soc_top (both arms) and pmu.sv"
    )
    return 0


def run_gen(upf: Path, out: Path, check_only: bool) -> int:
    try:
        up = parse_upf(upf.read_text())
    except OSError as exc:
        print(f"check_upf: cannot read {upf}: {exc}", file=sys.stderr)
        return 2
    if up.findings:
        print("check_upf gen-facts: the UPF has syntax findings; fix those first:", file=sys.stderr)
        for fd in up.findings:
            print(fd, file=sys.stderr)
        return 1
    try:
        fresh = dump_facts(build_facts(up))
    except ImportError as exc:
        print(
            f"check_upf gen-facts: pyslang is required ({exc}); pip install pyslang==11.0.0",
            file=sys.stderr,
        )
        return 3
    if not check_only:
        out.write_text(fresh)
        print(f"check_upf: wrote {out}")
        return 0
    old = out.read_text() if out.exists() else ""
    if old == fresh:
        print("check_upf gen-facts --check: facts file is up to date")
        return 0
    print(
        "check_upf gen-facts --check: DRIFT - the committed facts differ from a fresh elaboration of the RTL.",
        file=sys.stderr,
    )
    print(
        "  Re-run `python3 tools/verif/check_upf.py gen-facts`, review the diff, and commit it.",
        file=sys.stderr,
    )
    for ln in list(
        difflib.unified_diff(
            old.splitlines(), fresh.splitlines(), "committed", "fresh", lineterm=""
        )
    )[:60]:
        print(ln, file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--upf", type=Path, default=DEFAULT_UPF)
    ap.add_argument("--facts", type=Path, default=DEFAULT_FACTS)
    ap.add_argument("--pmu", type=Path, default=DEFAULT_PMU)
    ap.add_argument("--dft", type=Path, default=DEFAULT_DFT)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser(
        "gen-facts", help="regenerate (or --check) the RTL facts file; needs pyslang"
    )
    g.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "gen-facts":
        return run_gen(args.upf, args.facts, args.check)
    return run_check(args.upf, args.facts, args.pmu, args.dft, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
