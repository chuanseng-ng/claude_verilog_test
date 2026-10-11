#!/usr/bin/env python3
"""Fail a synthesis run that let the frontend silently replace logic with undef (bead gc0y).

Why this exists
---------------
Synlig/UHDM elaborated two hazard-unit port connections (a part-select of a packed-struct member
in a port connection) as ``5'x`` and logged only ``Warning: Range select [639:608] out of bounds
on signal ... Setting all 32 result bits to undef``.  Synthesis then deleted the forwarding-select
flops; lint, ``Checker.YosysSynthChecks``, LVS and P&R all passed on the smaller, wrong design
(beads dud4 / ma7; docs/SKY130_CPU_SYNLIG_DUD4.md).

Two independent detectors, so a wording change in one tool release cannot blind the gate:

* **Log scanner** (``scan_log``) - message patterns from the yosys 0.46/0.62 and Synlig plugin
  binaries and from probe designs run through both frontends (tools/verif/synth_gate/probes).
* **Structural check** (``scan_header_json``) - reads the pre-synthesis ``<design>.h.json`` that the
  flow already writes (``Yosys.JsonHeader``: elaborated, hierarchical, before optimisation) and
  fails on any module-instance input port, or any named net, connected to constant ``x``.  It does
  not depend on any message text.

One narrow exemption (bead j1b7): yosys inlines every function call and gives the function's own
argument/local/result wires (``<func>$func$<file>:<line>$<n>.<name>``) a constant-x ``update``
that nothing reads - the real value flows through proc temporaries.  Those nets used to be
``x-driven-net`` hits (509 on the Sky130 SoC).  A net is exempt (rule ``func-temp-dead-init``)
only if the PRE-``proc`` RTLIL of the same elaboration (``--pre-rtlil``) shows NO reader of the
wire, no other driver and a full-width x update; a name match alone never exempts, and a function
that leaves its result unassigned on a path (a read of the x wire) stays a FAIL.  Every exempted
net is counted per function in the report.  See docs/SYNTH_UNDEF_GATE.md.

Exit codes: 0 pass, 1 an un-allowlisted FAIL finding, 2 the input could not be judged (no log,
empty log, no recognisable synthesis banner).  Never a vacuous pass.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ALLOWLIST = Path(__file__).with_name("synth_undef_allowlist.txt")

# rule id -> (severity, regex, one-line reason).  Order matters: first match wins per line.
RULES: dict[str, tuple[str, str, str]] = {
    "undef-range-select": (
        "FAIL",
        r"out of bounds on signal .*Setting .*to undef",
        "constant bit/part-select outside the signal; the frontend substituted x (the dud4 defect)",
    ),
    "undef-substitution": (
        "FAIL",
        r"Warning:.*\b(?:[Ss]etting|[Rr]eplacing|[Ss]ubstituting)\b.*\bundef\b",
        "the tool states it replaced an expression with undef",
    ),
    "no-driver": (
        "FAIL",
        r"Wire .* is used but has no driver",
        "a used net has no driver; yosys later ties it to an arbitrary constant",
    ),
    "multi-driver": (
        "FAIL",
        r"multiple conflicting drivers for",
        "two drivers on one net; one is silently dropped or the result is x",
    ),
    "port-resize": (
        "FAIL",
        r"Resizing cell port .* from \d+ bits to \d+ bits",
        "instance port connected with a different width; bits silently dropped or zero-extended",
    ),
    "implicit-decl": (
        "FAIL",
        r"Identifier .* is implicitly declared",
        "an identifier was not declared; a typo becomes a new undriven 1-bit net",
    ),
    "tool-error": (
        "FAIL",
        r"(?:^|[\s:])ERROR:",
        "the tool reported an error (a flow that continued past it must not pass)",
    ),
    "post-increment": (
        "WARN",
        r"Post-incrementation operations are handled as pre-incrementation",
        "Synlig treats x++ as ++x; harmless for a for-loop step, a hard error when the value is "
        "used (probes p13/p19, docs/SYNTH_UNDEF_GATE.md)",
    ),
    "removed-module": (
        "WARN",
        r"Removing unelaborated module: (\S+)",
        "Synlig drops the un-parameterised copy once a $paramod copy exists (cross-checked)",
    ),
    "mem2reg": (
        "INFO",
        r"Replacing memory .* with list of registers",
        "array turned into registers; an out-of-range constant index shows up as x-driven-net",
    ),
    "assigned-in-block": (
        "INFO",
        r"wire '.*' is assigned in a block",
        "a wire-typed object assigned procedurally; yosys treats it as a reg",
    ),
    "setundef-count": (
        "INFO",
        r"Replacing (\d+) occurrences of constant undef bits with constant zero bits",
        "SYNTH_TIE_UNDEFINED: total x bits tied low after optimisation (informational count)",
    ),
}
# Rules that only exist for the structural detectors / cross-checks.
STRUCTURAL_RULES = {
    "x-driven-instance-input": "an instance input port is wired to constant x",
    "x-driven-net": "a named net is (partly) driven by constant x",
    "removed-module-missing": "module removed as unelaborated but no $paramod copy exists",
    "header-flattened": "header JSON is flattened; the structural check had nothing to inspect",
    "func-temp-dead-init": "sv2v/yosys function temporary whose x driver is provably never read",
}
ALL_RULES = set(RULES) | set(STRUCTURAL_RULES)
_COMPILED = {k: (sev, re.compile(rx), why) for k, (sev, rx, why) in RULES.items()}
_BANNER = re.compile(r"Yosys \d+\.\d+|^\d+\. Executing |Executing \w+ pass|Executing .* frontend")


class InputError(Exception):  # noqa: D101
    """The input could not be judged (maps to exit code 2)."""


class AllowlistError(Exception):
    """Malformed allowlist (maps to exit code 2)."""


@dataclass(frozen=True)
class Finding:
    """One scanner hit."""

    rule: str
    severity: str
    path: Path
    line: int
    text: str
    extra: str = ""
    allowed: bool = False
    note: str = ""


@dataclass
class AllowEntry:
    """One justified allowlist line."""

    rule: str
    pattern: str
    justification: str
    used: int = field(default=0)

    def matches(self, f: Finding) -> bool:
        if f.rule != self.rule:
            return False
        try:
            return re.search(self.pattern, f.text) is not None
        except re.error:
            return self.pattern in f.text


def scan_log(path: Path | str) -> list[Finding]:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"log not found: {p}")
    raw = p.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        raise InputError(f"log is empty: {p}")
    if not any(_BANNER.search(ln) for ln in raw.splitlines()):
        raise InputError(f"no recognisable yosys synthesis banner in {p}; cannot certify it")
    out: list[Finding] = []
    for n, line in enumerate(raw.splitlines(), 1):
        for rule, (sev, rx, _why) in _COMPILED.items():
            m = rx.search(line)
            if m:
                extra = m.group(1).lstrip("\\") if rule == "removed-module" else ""
                out.append(Finding(rule, sev, p, n, line.strip(), extra))
                break
    return out


# ----------------------------------------------------- function temporaries (bead j1b7)

# yosys names a function call's own wires  <func>$func$<file>:<line>$<autoidx>.<variable>
FUNC_TEMP_RE = re.compile(r"^\\?(?P<func>[A-Za-z_]\w*)\$func\$(?P<loc>.+?)\$\d+\.(?P<var>.+)$")
_ALL_X = re.compile(r"^\d+'x+$")
_BLOCK_OPENERS = {"module", "cell", "process", "switch"}

FuncKey = tuple[str, str, str, str]  # (module base name, function, "file:line", variable)


@dataclass
class FuncTempGroup:
    """The x-initialised wires of one function-temporary group in the pre-proc RTLIL."""

    wires: int = 0  # wires that carry a constant-x update (the candidates)
    reads: list[str] = field(default_factory=list)  # observable reads (evidence lines)
    benign_reads: int = 0  # reads whose value provably never reaches anything observable
    other_driver: bool = False
    partial: bool = False

    @property
    def dead_init(self) -> bool:
        """Every candidate is only ever x-updated at full width, and no read of it is observable."""
        return self.wires > 0 and not self.reads and not self.other_driver and not self.partial


@dataclass
class _Wire:
    """Per-wire drive evidence while parsing one module."""

    key: FuncKey
    x_full: bool = False
    x_partial: bool = False
    other_driver: bool = False


@dataclass
class _Stmt:
    """One RTLIL statement that moves or observes values (``kind`` = assign/update/connect/read)."""

    kind: str
    lhs: list[str]
    rhs: list[str]
    line: str


def _module_base(name: str) -> str:
    return name.rsplit("\\", 1)[-1]


def _func_key(module: str, name: str) -> FuncKey | None:
    m = FUNC_TEMP_RE.match(name)
    if not m:
        return None
    loc_file, _, loc_line = m.group("loc").rpartition(":")
    base = loc_file.rsplit("/", 1)[-1]
    return (_module_base(module), m.group("func"), f"{base}:{loc_line}", m.group("var"))


def _split_sigspec(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split ``<sigspec> <sigspec>`` into two token lists (``{..}``/name/const plus ``[..]``)."""
    i = 0
    if tokens and tokens[0] == "{":
        depth = 0
        while i < len(tokens):
            depth += tokens[i] == "{"
            depth -= tokens[i] == "}"
            i += 1
            if depth == 0:
                break
    elif tokens:
        i = 1
    while i < len(tokens) and tokens[i].startswith("["):
        i += 1
    return tokens[:i], tokens[i:]


def _classify_drive(wires: dict[str, _Wire], stmt: _Stmt) -> None:
    is_x = len(stmt.rhs) == 1 and _ALL_X.match(stmt.rhs[0]) is not None
    partial = any(t.startswith("[") for t in stmt.lhs)
    for t in stmt.lhs:
        w = wires.get(t)
        if w is None:
            continue
        if stmt.kind == "connect" or not is_x:
            w.other_driver = True
        elif partial:
            w.x_partial = True
        else:
            w.x_full = True


def _propagate_taint(cands: dict[str, _Wire], stmts: list[_Stmt]) -> dict[str, set[str]]:
    """Which candidate x-wires can flow into each signal name (flow-insensitive, so conservative)."""
    taint: dict[str, set[str]] = {}
    changed = True
    while changed:
        changed = False
        for st in stmts:
            if st.kind == "read":
                continue
            srcs: set[str] = set()
            for t in st.rhs:
                if t in cands:
                    srcs.add(t)
                srcs |= taint.get(t, set())
            if not srcs:
                continue
            for lhs in st.lhs:
                if lhs.startswith("[") or lhs in cands:
                    continue
                cur = taint.setdefault(lhs, set())
                if not srcs <= cur:
                    cur |= srcs
                    changed = True
    return taint


def _flush_module(
    groups: dict[FuncKey, FuncTempGroup],
    module: str,
    wires: dict[str, _Wire],
    stmts: list[_Stmt],
    outputs: set[str],
) -> None:
    """Fold one module's evidence into groups.

    Candidates are the wires with a constant-x update.  A read of a candidate is *observable* only
    if the value it produces can reach a cell input, a ``switch``/``sync`` expression, a real
    (non-candidate) signal updated by a process, or an output port; a read whose value only ever
    flows into the dead ``$0`` temporaries of x-initialised wires - the "keep my old value" branch
    of a call made inside an ``if`` - is counted as benign.
    """
    cands = {n: w for n, w in wires.items() if w.x_full or w.x_partial}
    if not cands:
        return
    taint = _propagate_taint(cands, stmts)
    evidence: dict[str, list[str]] = {n: [] for n in cands}
    benign: dict[str, int] = {n: 0 for n in cands}

    def observe(names: Iterable[str], line: str) -> None:
        srcs: set[str] = set()
        for t in names:
            if t in cands:
                srcs.add(t)
            srcs |= taint.get(t, set())
        for s in srcs:
            evidence[s].append(f"{_module_base(module)}: {line}")

    for st in stmts:
        if st.kind == "read":
            observe(st.rhs, st.line)
        elif st.kind == "update":
            if any(t in cands or t in taint for t in st.rhs) and not any(
                t in cands for t in st.lhs
            ):
                observe(st.rhs, st.line)
        elif any(t in cands for t in st.rhs):
            for t in st.rhs:
                if t in cands:
                    benign[t] += 1
    for n, srcs in taint.items():
        if n in outputs:
            for s in srcs:
                evidence[s].append(f"{_module_base(module)}: value reaches output port {n}")
    for n, w in cands.items():
        g = groups.setdefault(w.key, FuncTempGroup())
        g.wires += 1
        g.reads += evidence[n]
        g.benign_reads += 0 if evidence[n] else benign[n]
        g.other_driver |= w.other_driver
        g.partial |= w.x_partial


def parse_func_temps(text: str) -> dict[FuncKey, FuncTempGroup]:
    """Classify every function-temporary wire of a pre-``proc`` RTLIL dump (``write_rtlil``).

    A wire is *dead-init* only if every appearance outside its declaration is a full-width
    ``update``/``assign`` of constant x, or a read whose value cannot reach anything observable.
    A read that can (cell connection, ``switch``/``sync``, a process update of a real signal, an
    output port) or a second driver is recorded and defeats the exemption (fail closed).
    """
    groups: dict[FuncKey, FuncTempGroup] = {}
    module = ""
    wires: dict[str, _Wire] = {}
    stmts: list[_Stmt] = []
    outputs: set[str] = set()
    stack: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        toks = line.split()
        if not toks or toks[0] in ("attribute", "autoidx", "parameter"):
            continue
        kw = toks[0]
        if kw == "module":
            _flush_module(groups, module, wires, stmts, outputs)
            module, wires, stmts, outputs, stack = toks[1], {}, [], set(), ["module"]
        elif kw == "wire":
            if "output" in toks[:-1]:
                outputs.add(toks[-1])
            key = _func_key(module, toks[-1])
            if key is not None:
                wires[toks[-1]] = _Wire(key)
        elif kw == "end":
            if stack:
                stack.pop()
        elif kw in _BLOCK_OPENERS:
            stack.append(kw)
            if kw == "switch":  # the selector is read
                stmts.append(_Stmt("read", [], toks[1:], line))
        elif kw in ("assign", "update") or (kw == "connect" and stack[-1:] != ["cell"]):
            lhs, rhs = _split_sigspec(toks[1:])
            st = _Stmt(kw, lhs, rhs, line)
            stmts.append(st)
            _classify_drive(wires, st)
        elif kw in ("connect", "sync"):  # cell port connection / sync condition: a read
            stmts.append(_Stmt("read", [], toks[2:], line))
        else:  # case, memory, ...: every mention is a read
            stmts.append(_Stmt("read", [], toks[1:], line))
    _flush_module(groups, module, wires, stmts, outputs)
    return groups


def load_func_temp_proof(paths: Iterable[Path | str]) -> dict[FuncKey, FuncTempGroup]:
    """Parse and merge the pre-proc RTLIL dumps that serve as the proof for the exemption."""
    merged: dict[FuncKey, FuncTempGroup] = {}
    for path in paths:
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise InputError(f"pre-proc RTLIL unreadable: {p}: {exc}") from exc
        if not re.search(r"^module ", text, re.MULTILINE):
            raise InputError(f"no RTLIL module in {p}; not a write_rtlil dump")
        for key, g in parse_func_temps(text).items():
            m = merged.setdefault(key, FuncTempGroup())
            m.wires += g.wires
            m.reads += g.reads
            m.benign_reads += g.benign_reads
            m.other_driver |= g.other_driver
            m.partial |= g.partial
    return merged


def summarise_exemptions(findings: Iterable[Finding]) -> dict[str, int]:
    """Exempted nets per function name (the report line that makes a new function visible)."""
    out: dict[str, int] = {}
    for f in findings:
        if f.rule == "func-temp-dead-init":
            out[f.extra] = out.get(f.extra, 0) + 1
    return dict(sorted(out.items()))


def format_exemptions(findings: Iterable[Finding]) -> list[str]:
    """Human-readable exemption summary: rule, total, per-function counts."""
    by_func = summarise_exemptions(findings)
    if not by_func:
        return []
    return [
        f"EXEMPT  [func-temp-dead-init] {sum(by_func.values())} net(s) in {len(by_func)} "
        "function(s) (constant-x update proven unread in the pre-proc RTLIL): "
        + " ".join(f"{fn}={n}" for fn, n in by_func.items())
    ]


def _is_user_cell(ctype: str) -> bool:
    return not ctype.startswith("$") or ctype.startswith("$paramod")


def _resolve_func_temps(
    path: Path,
    cands: dict[FuncKey, list[tuple[str, str, int]]],
    proof: dict[FuncKey, FuncTempGroup] | None,
) -> list[Finding]:
    """Exempt a candidate group only if the pre-proc RTLIL proves every wire of it dead-init."""
    out: list[Finding] = []
    for key, nets in cands.items():
        g = proof.get(key) if proof else None
        if g is None:
            why = (
                "no pre-proc RTLIL proof supplied (--pre-rtlil)"
                if proof is None
                else "group not found in the pre-proc RTLIL proof"
            )
        elif g.reads:
            why = f"function temporary is READ before it is assigned: {g.reads[0]}"
        elif g.other_driver or g.partial:
            why = "function temporary has another driver or a partial x update"
        elif g.wires != len(nets):
            why = f"proof has {g.wires} wire(s) for this group but the netlist has {len(nets)}"
        else:
            why = ""
        for short, nname, width in nets:
            if why:
                out.append(
                    Finding(
                        "x-driven-net",
                        "FAIL",
                        path,
                        0,
                        f"net {nname} (in {short}): {width}/{width} bits constant x; {why}",
                    )
                )
            else:
                out.append(
                    Finding(
                        "func-temp-dead-init",
                        "EXEMPT",
                        path,
                        0,
                        f"net {nname} (in {short}): {width} bits x, function '{key[1]}' temporary "
                        "never read",
                        extra=key[1],
                    )
                )
    return out


def scan_header_json(
    path: Path | str, proof: dict[FuncKey, FuncTempGroup] | None = None
) -> list[Finding]:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        mods = data["modules"]
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(f"header JSON unreadable: {p}: {exc}") from exc
    out: list[Finding] = []
    func_cands: dict[FuncKey, list[tuple[str, str, int]]] = {}
    for mname, mod in mods.items():
        short = mname.rsplit("\\", 1)[-1]
        for cname, cell in mod.get("cells", {}).items():
            if not _is_user_cell(cell.get("type", "$")):
                continue
            tgt_ports = mods.get(cell["type"], {}).get("ports", {})
            dirs = cell.get("port_directions", {})
            for pname, bits in cell.get("connections", {}).items():
                if not any(b == "x" for b in bits if isinstance(b, str)):
                    continue
                direction = dirs.get(pname) or tgt_ports.get(pname, {}).get("direction", "?")
                if direction == "output":
                    continue
                pat = "".join(b if isinstance(b, str) else "." for b in bits)
                out.append(
                    Finding(
                        "x-driven-instance-input",
                        "FAIL",
                        p,
                        0,
                        f"{cname} (in {short}, type {cell['type'].rsplit(chr(92), 1)[-1]}) "
                        f"port {pname} [{direction}] <- {pat}",
                    )
                )
        for nname, net in mod.get("netnames", {}).items():
            if nname.startswith("$"):
                continue
            bits = net.get("bits", [])
            nx = sum(1 for b in bits if b == "x")
            key = _func_key(mname, nname) if nx and nx == len(bits) else None
            if key is not None:
                func_cands.setdefault(key, []).append((short, nname, nx))
            elif nx:
                out.append(
                    Finding(
                        "x-driven-net",
                        "FAIL",
                        p,
                        0,
                        f"net {nname} (in {short}): {nx}/{len(bits)} bits constant x",
                    )
                )
    out += _resolve_func_temps(p, func_cands, proof)
    if len(mods) == 1 and any(
        c.get("type", "").startswith("$")
        for m in mods.values()
        for c in m.get("cells", {}).values()
    ):
        out.append(
            Finding(
                "header-flattened",
                "INFO",
                p,
                0,
                "header JSON holds a single flattened module; structural check not informative",
            )
        )
    return out


def cross_check_removed_modules(findings: Iterable[Finding], header: Path | str) -> list[Finding]:
    try:
        mods = json.loads(Path(header).read_text(encoding="utf-8"))["modules"]
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(f"header JSON unreadable: {header}: {exc}") from exc
    names = list(mods)
    out: list[Finding] = []
    for f in findings:
        if f.rule != "removed-module" or not f.extra:
            continue
        if any(
            n == f.extra
            or n.endswith("\\" + f.extra)
            or n.startswith("$paramod\\" + f.extra + "\\")
            for n in names
        ):
            continue
        out.append(
            Finding(
                "removed-module-missing",
                "FAIL",
                f.path,
                f.line,
                f"module {f.extra} removed as unelaborated and no copy of it is in {header}",
            )
        )
    return out


def load_allowlist(path: Path | str) -> list[AllowEntry]:
    p = Path(path)
    entries: list[AllowEntry] = []
    for n, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [s.strip() for s in line.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            raise AllowlistError(f"{p}:{n}: need 'rule | pattern | justification' (all non-empty)")
        if parts[0] not in ALL_RULES:
            raise AllowlistError(f"{p}:{n}: unknown rule '{parts[0]}'")
        entries.append(AllowEntry(*parts))
    return entries


def apply_allowlist(findings: Iterable[Finding], entries: Sequence[AllowEntry]) -> list[Finding]:
    out: list[Finding] = []
    for f in findings:
        hit = next((e for e in entries if e.matches(f)), None)
        if hit is None:
            out.append(f)
            continue
        hit.used += 1
        out.append(dataclasses.replace(f, allowed=True, note=hit.justification))
    return out


def stale_entries(entries: Sequence[AllowEntry]) -> list[AllowEntry]:
    return [e for e in entries if e.used == 0]


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    seen: dict[tuple[str, str], int] = {}
    out: list[Finding] = []
    for f in findings:
        key = (f.rule, re.sub(r"^\S*/", "", f.text))
        if key in seen:
            seen[key] += 1
            continue
        seen[key] = 1
        out.append(f)
    return out


def find_run_inputs(run_dir: Path) -> tuple[list[Path], list[Path]]:
    logs = sorted(run_dir.glob("*yosys*/yosys-*.log"))
    headers = sorted(run_dir.glob("*yosys*/*.h.json"))
    return logs, headers


def evaluate(
    logs: Sequence[Path],
    headers: Sequence[Path],
    entries: Sequence[AllowEntry],
    proof: dict[FuncKey, FuncTempGroup] | None = None,
) -> dict:
    findings: list[Finding] = []
    for lg in logs:
        findings += scan_log(lg)
    for h in headers:
        findings += scan_header_json(h, proof)
        findings += cross_check_removed_modules(findings, h)
    findings = apply_allowlist(dedupe(findings), entries)
    bad = [f for f in findings if f.severity == "FAIL" and not f.allowed]
    exempt = summarise_exemptions(findings)
    return {
        "verdict": "FAIL" if bad else "PASS",
        "fail_count": len(bad),
        "findings": findings,
        "logs": [str(x) for x in logs],
        "headers": [str(x) for x in headers],
        "structural_check": "RAN" if headers else "NOT RUN (no *.h.json found)",
        "stale_allowlist": list(stale_entries(entries)),
        "exempt_by_function": exempt,
        "exempt_total": sum(exempt.values()),
        "exemption_proof": "pre-proc RTLIL" if proof is not None else "none supplied",
    }


def _fmt(f: Finding) -> str:
    loc = f"{f.path}:{f.line}" if f.line else str(f.path)
    tag = "ALLOWED" if f.allowed else f.severity
    s = f"{tag:7s} [{f.rule}] {loc}: {f.text}"
    if f.allowed:
        s += f"\n          allowlisted: {f.note}"
    return s


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    ap.add_argument("logs", nargs="*", type=Path, help="yosys/Synlig synthesis logs")
    ap.add_argument(
        "--run-dir", type=Path, help="LibreLane run dir (finds *yosys*/ logs + *.h.json)"
    )
    ap.add_argument("--header-json", type=Path, action="append", default=[])
    ap.add_argument(
        "--allowlist",
        type=Path,
        action="append",
        default=[],
        help="extra allowlist file(s), added to the repo default",
    )
    ap.add_argument(
        "--no-allowlist", action="store_true", help="ignore ALL allowlists (audit mode)"
    )
    ap.add_argument(
        "--pre-rtlil",
        type=Path,
        action="append",
        default=[],
        help="pre-proc RTLIL (write_rtlil before proc) of the SAME elaboration as --header-json; "
        "the proof that lets dead sv2v function temporaries through (rule func-temp-dead-init)",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="also print WARN/INFO findings")
    args = ap.parse_args(argv)

    logs = list(args.logs)
    headers = list(args.header_json)
    pre_rtlil = list(args.pre_rtlil)
    try:
        if args.run_dir:
            if not args.run_dir.is_dir():
                raise InputError(f"run dir not found: {args.run_dir}")
            rl, rh = find_run_inputs(args.run_dir)
            logs += rl
            headers += rh
            pre_rtlil += sorted(args.run_dir.glob("*yosys*/*.pre.il"))
        if not logs:
            raise InputError("no synthesis logs given or found")
        al_paths = ([DEFAULT_ALLOWLIST] if DEFAULT_ALLOWLIST.is_file() else []) + args.allowlist
        entries = [] if args.no_allowlist else [e for ap_ in al_paths for e in load_allowlist(ap_)]
        proof = load_func_temp_proof(pre_rtlil) if pre_rtlil else None
        res = evaluate(logs, headers, entries, proof)
    except (InputError, AllowlistError) as exc:
        print(f"check_synth_undef: INPUT ERROR (exit 2): {exc}", file=sys.stderr)
        return 2

    if args.json:
        out = dict(res)
        out["findings"] = [dataclasses.asdict(f) | {"path": str(f.path)} for f in res["findings"]]
        out["stale_allowlist"] = [dataclasses.asdict(e) for e in res["stale_allowlist"]]
        print(json.dumps(out, indent=1))
    else:
        for f in res["findings"]:
            if f.severity == "FAIL" or f.allowed or args.verbose:
                print(_fmt(f))
        for line in format_exemptions(res["findings"]):
            print(line)
        for e in res["stale_allowlist"] if args.verbose else []:
            print(f"WARN    [stale-allowlist] '{e.rule} | {e.pattern}' matched nothing")
        print(
            f"check_synth_undef: {res['verdict']} ({res['fail_count']} un-allowlisted FAIL; "
            f"logs={len(logs)}; structural check {res['structural_check']})"
        )
    return 1 if res["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
