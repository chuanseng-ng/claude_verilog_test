#!/usr/bin/env python3
"""Per-module line + toggle coverage report from a merged Verilator ``coverage.dat``.

Why this exists (GH #216, bead nkj7)
------------------------------------
``VERIFICATION_PLAN.md`` sets a >95 % line-coverage exit criterion but, until the
``soc_coverage`` Makefile target, nothing measured it for the SoC regression
(``tb/cocotb/soc`` ``soc_all_ci``).  That target runs the regression instrumented, merges
every per-simulation ``.dat`` with ``verilator_coverage --write`` and calls this script.

What it reads
-------------
Verilator's ``.dat`` (``# SystemC::Coverage-3``), one record per coverage point::

    C '<\\x01key\\x02value ...>' <count>

keys: ``f`` file, ``l`` line, ``n`` column, ``t`` type, ``page`` (``v_line``, ``v_branch`` or
``v_toggle`` followed by ``/<module>``), ``o`` object (signal and direction for toggles, the
branch arm for branches), ``S`` source-line set, ``h`` instance hierarchy.  Other pages (user
coverage and so on) are ignored.

How it counts
-------------
* Parameter specialisations (Verilator's ``<module>__<params>`` page names) fold into the base
  module.
* The hierarchy is dropped: a point is identified by (module, file, kind, line, column, object,
  source lines), so the same point in two instances -- or in two testbenches -- is ONE point,
  and it is hit when ANY instance hit it.
* Line % is ``v_line`` + ``v_branch`` points; toggle % is ``v_toggle`` points (one point per
  bit per direction, exactly as Verilator counts them).  They are never mixed.
* Only RTL under the repo root is reported.  Triaged trees: ``rtl/soc``, ``rtl/periph``,
  ``rtl/npu``.  Informational trees: ``rtl/cpu``, ``rtl/mem``, ``rtl/gpu``.  Testbenches
  (``tb/``), ``sim/`` and the behavioural SRAM models are excluded.

Waivers
-------
``tools/verif/coverage_waivers.txt`` (``--waivers``) lists points that are unreachable BY
DESIGN (a tie-off, an ``EN_*=0`` generate arm, an elaboration guard).  One per line::

    module | kind | regex | category | justification

``kind`` is ``line`` (line and branch points, matched as ``L<line>`` or ``L<line> <arm>``),
``toggle`` (matched as ``<signal>[<bit>]:<from>-><to>``) or ``any``.  ``category`` is ``b``
(the only waivable class: test gaps and bugs are beads, never waivers).  A justification is
mandatory.  A waiver can only remove an UNCOVERED point from the denominator; the raw
percentage stays in the report beside the adjusted one, and a waiver that matches nothing is
reported as stale.  The list is external on purpose: grandfathered RTL gets no pragma edits.

Exit status
-----------
Without ``--gate``: 0 for any coverage level (informational; see
``docs/verification/SOC_COVERAGE_REPORT.md``).  Nonzero (2) on a missing, malformed or empty
``.dat``, on a bad waiver or ratchet file, or when no triaged RTL was measured at all: a clean
exit over no data is never a pass (cf. bead dwp).  With ``--gate``: additionally 1 when any
triaged module fails the gate (see below).  Exit 2 always means "could not evaluate", never
"evaluated and failed".

Gate (bead s1cg)
----------------
``--gate`` enforces, on the TRIAGED trees only (``rtl/soc``, ``rtl/periph``, ``rtl/npu``; the
informational trees never fail it):

* **line floor** (``--line-floor``, default 95): every module's adjusted line % (line + branch
  points, waived points removed) is at least the floor;
* **control-signal toggle floor** (``--toggle-floor``, default 100): every module's toggle % over
  its CONTROL signals is at least the floor.  A control signal is a 1-bit scalar: its Verilator
  toggle object has no ``[bit]`` index (valid/ready/enable/irq/start/done/busy/FSM-strobe nets).
  Buses, per-bit address/data lanes, FSM state vectors and arrays are datapath and are never
  gated.  The rule is mechanical -- no hand-kept signal list to rot;
* **ratchet** (``--toggle-ratchet FILE``, ``module | floor | bead | justification``): overrides
  the toggle floor for a named module whose control-toggle gap is a KNOWN test gap tracked by a
  bead.  It can only be edited upward without an explicit, reviewable lowering; a module sitting
  well above its entry is reported so the entry can be raised or removed.  It never relaxes the
  line floor.

* **line-only trees** (``--line-gate-trees``, default ``rtl/cpu,rtl/mem,rtl/gpu``, bead a5ze):
  the line floor above applies to every module of these trees too, evaluated on the same
  (combined) data.  The control-toggle floor does NOT: their wide CSR / address / data buses
  dominate toggle exactly as in the triaged trees and no ratchet was calibrated for them.  A
  line-only tree with no measured module is an ERROR (exit 2), never a pass -- a gate run fed
  only the SoC ``.dat`` must not look green -- and a gated module whose inputs disagree on its
  point set is a failure (the union would inflate its denominator).  ``--line-gate-trees ""``
  turns the extension off for a SoC-only local run.

A module with nothing to gate does not pass vacuously: no line points and no control signals
(and nothing waived) is a failure, "unmeasured".  A module with no line points but control
signals is gated on those alone and the report says so; one whose line points are all waived
passes with a note.

Combined report (bead 1eyv)
---------------------------
``--dat`` may be repeated.  The inputs are concatenated and aggregated exactly like instances of
one run -- the point identity already drops the hierarchy, so a point of ``rtl/cpu/...`` measured
by the SoC regression AND by the CPU/cache/GPU suites is one point, hit if either hit it.  Because
the inputs come from different checkouts, file paths are normalised to repo-relative (anchored on
the ``rtl/<tree>/`` component when the path is not under ``--root``).  Two inputs that measured
the same module are compared: if their point sets disagree (a different Verilator version or
source revision) the module is listed under "Cross-input point-set consistency" and flagged
SUSPECT below 80 % overlap; an input that contributes no reportable RTL at all is an error.

Usage::

    coverage_report.py --dat merged.dat [--dat more.dat ...] [--root <repo>] [--waivers <file>]
                       [--out-md report.md] [--out-json report.json]
                       [--gate [--line-floor 95] [--toggle-floor 95] [--toggle-ratchet <file>]
                        [--line-gate-trees rtl/cpu,rtl/mem,rtl/gpu]]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK, EXIT_GATE_FAIL, EXIT_ERROR = 0, 1, 2

SOH, STX = "\x01", "\x02"
HEADER_PREFIX = "# SystemC::Coverage-"

TRIAGED_TREES = ("rtl/soc", "rtl/periph", "rtl/npu")
INFORMATIONAL_TREES = ("rtl/cpu", "rtl/mem", "rtl/gpu")
# Trees that join the gate for LINE coverage only (bead a5ze); the CLI default.  The library
# default (GateConfig.line_trees) is empty so a caller opts in explicitly.
LINE_GATED_TREES = INFORMATIONAL_TREES
# Behavioural SRAM models are simulation stand-ins for hard macros, not design logic.
EXCLUDED_BASENAME = re.compile(r"^(sram_1rw_|sky130_sram_)")
EXCLUDED_PREFIXES = ("tb/", "sim/")

KINDS = ("line", "toggle", "any")
WAIVABLE_CATEGORIES = ("b",)
LINE_FLOOR_PCT = 95.0
# Chosen from measurement (bead s1cg): after the structural waivers 40 of 42 triaged modules sit at
# exactly 100.0 % control-signal toggle, bit-identical across a local and an independent CI run.
TOGGLE_FLOOR_PCT = 100.0
# A ratchet entry this many points below the module's measured control-toggle % is reported as
# raisable: the ratchet exists to stop regressions, so slack above it is a missed tightening.
RATCHET_HEADROOM_PCT = 2.0
# Two inputs that measured the same module/file should have (nearly) the same point set: the
# instrumentation depends on the source and the Verilator version, not on the test.  Below this
# overlap the inputs almost certainly disagree on point identity (different Verilator, different
# source revision), and the union then double-counts the denominator.
CONSISTENCY_SUSPECT_PCT = 80.0
# Anchor for paths recorded under a different checkout (CI runner, developer worktree).
_RTL_ANCHOR = re.compile(r"(?:^|/)(rtl/(?:soc|periph|npu|cpu|mem|gpu)/.+)$")

_RECORD = re.compile(r"^C '(.*)' (\d+)\s*$", re.DOTALL)
_PAGE_KIND = {"v_line": "line", "v_branch": "branch", "v_toggle": "toggle"}


class CoverageError(Exception):
    """Unusable input (bad .dat, bad waiver file, nothing measured); maps to exit status 2."""


# --------------------------------------------------------------------------- data model


@dataclass(frozen=True)
class Point:
    """One coverage point exactly as recorded in one instance."""

    module: str
    kind: str  # "line" | "branch" | "toggle"
    file: str
    line: int
    col: int
    name: str  # ``o`` key
    src: str  # ``S`` key (source-line set), may be empty
    hier: str
    count: int
    source: str = ""  # label of the .dat this point came from (bead 1eyv multi-input merge)


@dataclass(frozen=True)
class Waiver:
    """One waiver-file entry; ``lineno`` is its line in the waiver file."""

    module: str
    kind: str
    pattern: str
    category: str
    justification: str
    lineno: int

    def matches(self, module: str, kind: str, text: str) -> bool:
        if module != self.module:
            return False
        if self.kind != "any" and self.kind != ("line" if kind in ("line", "branch") else kind):
            return False
        return re.search(self.pattern, text) is not None


@dataclass
class LineGap:
    label: str  # "L20" or "L31 else"
    kind: str  # "line" | "branch"
    line: int
    span: str


@dataclass
class ToggleGap:
    signal: str
    hit: int
    total: int

    @property
    def never_toggles(self) -> bool:
        return self.hit == 0


@dataclass
class ModuleRow:
    module: str
    file: str  # repo-relative
    tree: str
    triaged: bool
    line_hit: int = 0
    line_total: int = 0  # adjusted (waived points removed)
    line_waived: int = 0
    toggle_hit: int = 0
    toggle_total: int = 0
    toggle_waived: int = 0
    uncovered_lines: list[LineGap] = field(default_factory=list)
    uncovered_toggles: list[ToggleGap] = field(default_factory=list)
    # Control signals = 1-bit scalar toggle objects (a subset of the toggle_* counts above).
    ctl_hit: int = 0
    ctl_total: int = 0  # adjusted (waived points removed)
    ctl_waived: int = 0
    uncovered_ctl: list[str] = field(default_factory=list)

    @staticmethod
    def _pct(hit: int, total: int) -> float | None:
        return None if total == 0 else 100.0 * hit / total

    @property
    def line_pct(self) -> float | None:
        return self._pct(self.line_hit, self.line_total)

    @property
    def line_raw_pct(self) -> float | None:
        return self._pct(self.line_hit, self.line_total + self.line_waived)

    @property
    def toggle_pct(self) -> float | None:
        return self._pct(self.toggle_hit, self.toggle_total)

    @property
    def toggle_raw_pct(self) -> float | None:
        return self._pct(self.toggle_hit, self.toggle_total + self.toggle_waived)

    @property
    def ctl_pct(self) -> float | None:
        return self._pct(self.ctl_hit, self.ctl_total)


@dataclass
class InputStat:
    """What one ``--dat`` input contributed after path normalisation and tree filtering."""

    name: str
    reportable: int  # points under rtl/{soc,periph,npu,cpu,mem,gpu}
    hit: int


@dataclass
class Consistency:
    """A module/file measured by >= 2 inputs whose point sets are not identical."""

    module: str
    file: str
    shared: int  # points present in every input that measured this module/file
    total: int  # points in the union
    only_in: dict[str, int]  # input -> points only that input has
    suspect: bool  # overlap below CONSISTENCY_SUSPECT_PCT


@dataclass
class Report:
    modules: list[ModuleRow]
    waivers: list[Waiver]
    waiver_hits: dict[int, int]  # waiver lineno -> matched uncovered points
    inputs: list[InputStat] = field(default_factory=list)
    consistency: list[Consistency] = field(default_factory=list)

    @property
    def unused_waivers(self) -> list[Waiver]:
        return [w for w in self.waivers if self.waiver_hits.get(w.lineno, 0) == 0]


# ------------------------------------------------------------------------------ parsing


def _parse_fields(body: str, where: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for chunk in body.split(SOH):
        if not chunk:
            continue
        key, sep, value = chunk.partition(STX)
        if not sep:
            raise CoverageError(f"{where}: malformed record (field without value separator)")
        fields[key] = value
    return fields


def parse_dat(path: Path, label: str | None = None) -> list[Point]:
    """Parse a Verilator coverage ``.dat`` into line / branch / toggle points.

    ``label`` names the input in multi-input reports (default: the file name).
    """
    if not path.is_file():
        raise CoverageError(f"{path}: coverage file is missing")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].startswith(HEADER_PREFIX):
        raise CoverageError(
            f"{path}: not a Verilator coverage file (header '{HEADER_PREFIX}*' missing)"
        )

    source = label if label is not None else path.name
    points: list[Point] = []
    for lineno, raw in enumerate(lines[1:], start=2):
        if not raw.strip() or raw.startswith("#"):
            continue
        where = f"{path}:{lineno}"
        m = _RECORD.match(raw)
        if not m:
            raise CoverageError(f"{where}: malformed record")
        fields = _parse_fields(m.group(1), where)
        if "f" not in fields or "page" not in fields:
            raise CoverageError(f"{where}: malformed record (no file / page key)")
        page_kind, _, module = fields["page"].partition("/")
        # Verilator names a parameter specialisation "<module>__<params>"; no RTL module in this
        # repo has "__" in its own name, so the base name identifies the RTL module.
        module = module.split("__", 1)[0]
        kind = _PAGE_KIND.get(page_kind)
        if kind is None:
            continue  # user / functional pages are out of scope
        points.append(
            Point(
                module=module,
                kind=kind,
                file=fields["f"],
                line=int(fields.get("l", "0") or 0),
                col=int(fields.get("n", "0") or 0),
                name=fields.get("o", ""),
                src=fields.get("S", ""),
                hier=fields.get("h", ""),
                count=int(m.group(2)),
                source=source,
            )
        )
    if not points:
        raise CoverageError(f"{path}: no coverage points (empty or only non-line/toggle pages)")
    return points


# ------------------------------------------------------------------------------- waivers


def load_waivers(path: Path) -> list[Waiver]:
    """Parse the waiver file; every structural defect is an error, never a silent skip."""
    if not path.is_file():
        raise CoverageError(f"{path}: waiver file is missing")
    waivers: list[Waiver] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        where = f"{path}:{lineno}"
        # ' | ' (whitespace-delimited) so a regex may itself contain an alternation bar.
        parts = [p.strip() for p in re.split(r"\s+\|\s+", stripped + " ", maxsplit=4)]
        if len(parts) != 5:
            raise CoverageError(
                f"{where}: expected 'module | kind | regex | category | justification' "
                f"(5 fields; a justification is mandatory)"
            )
        module, kind, pattern, category, justification = parts
        if kind not in KINDS:
            raise CoverageError(f"{where}: kind '{kind}' must be one of {', '.join(KINDS)}")
        if category not in WAIVABLE_CATEGORIES:
            raise CoverageError(
                f"{where}: category '{category}' must be 'b' (unreachable by design); "
                f"test gaps and bugs are beads, not waivers"
            )
        if not justification:
            raise CoverageError(f"{where}: justification is empty")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise CoverageError(f"{where}: bad regex {pattern!r}: {exc}") from exc
        waivers.append(Waiver(module, kind, pattern, category, justification, lineno))
    return waivers


# ---------------------------------------------------------------------------- aggregation


def _relpath(file: str, root: Path) -> str | None:
    """Repo-relative POSIX path, or None when the file is not reportable RTL.

    A path under ``root`` is made relative to it.  Any other path -- recorded by a run in a
    different checkout (CI runner, developer worktree) or relative to another directory
    (``../rtl/...``) -- is anchored on its ``rtl/<tree>/`` component, so the same source file
    gets the same identity in every input.
    """
    norm = os.path.normpath(file.replace("\\", "/"))
    if os.path.isabs(norm):
        try:
            return Path(norm).relative_to(root).as_posix()
        except ValueError:
            pass
    posix = Path(norm).as_posix()
    anchored = _RTL_ANCHOR.search(posix)
    if anchored:
        return anchored.group(1)
    return None if os.path.isabs(norm) else posix


def _classify(rel: str) -> tuple[str, bool] | None:
    """Return (tree, triaged) for a reportable repo-relative path, else None."""
    if rel.startswith(EXCLUDED_PREFIXES) or EXCLUDED_BASENAME.match(Path(rel).name):
        return None
    for tree in TRIAGED_TREES:
        if rel.startswith(tree + "/"):
            return tree, True
    for tree in INFORMATIONAL_TREES:
        if rel.startswith(tree + "/"):
            return tree, False
    return None


def _first_src_line(src: str, fallback: int) -> int:
    m = re.match(r"\s*(\d+)", src)
    return int(m.group(1)) if m else fallback


def is_control_toggle(obj: str) -> bool:
    """True for the toggle object of a 1-bit scalar signal (no ``[bit]`` index).

    Verilator names a vector bit ``sig[3]:0->1`` and a scalar ``sig:0->1``.  Only scalars are
    control signals; indexed objects (bus bits, array elements, ``logic [0:0]`` nets) are
    datapath and conservatively stay outside the control gate.
    """
    return "[" not in obj.split(":", 1)[0]


def _signal_of(obj: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", obj.split(":", 1)[0])


def build_report(points: list[Point], root: Path, waivers: list[Waiver]) -> Report:
    """Aggregate points per module (across instances) and apply the waivers."""
    # Pass 1: union over instances and inputs.  Identity drops the hierarchy and the input; hit =
    # any instance in any input hit.  Per-input key sets feed the consistency check.
    union: dict[tuple[str, str, str, int, int, str, str], bool] = {}
    per_input: dict[tuple[str, str], dict[str, set[tuple[str, str, str, int, int, str, str]]]] = (
        defaultdict(lambda: defaultdict(set))
    )
    input_stats: dict[str, list[int]] = {}
    for p in points:
        stat = input_stats.setdefault(p.source, [0, 0])
        rel = _relpath(p.file, root)
        if rel is None or _classify(rel) is None:
            continue
        key = (p.module, rel, p.kind, p.line, p.col, p.name, p.src)
        union[key] = union.get(key, False) or p.count > 0
        per_input[(p.module, rel)][p.source].add(key)
        stat[0] += 1
        stat[1] += int(p.count > 0)
    if not union:
        raise CoverageError(
            "no reportable RTL points (nothing under rtl/{soc,periph,npu,cpu,mem,gpu})"
        )
    for name, (reportable, _hit) in input_stats.items():
        if reportable == 0:
            raise CoverageError(
                f"input '{name}' contributed no reportable RTL points -- wrong checkout, wrong "
                f"tree, or an empty run; refusing to merge it silently"
            )

    rows: dict[tuple[str, str], ModuleRow] = {}
    waiver_hits: dict[int, int] = defaultdict(int)
    toggles: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )

    for (module, rel, kind, line, _col, name, src), hit in sorted(union.items()):
        classified = _classify(rel)
        assert classified is not None  # filtered in pass 1
        tree, triaged = classified
        row = rows.setdefault((module, rel), ModuleRow(module, rel, tree, triaged))
        is_line = kind in ("line", "branch")
        if is_line:
            # Label with the point's OWN line (``l``), never the start of its ``S`` span: inside a
            # generate loop Verilator writes ``l=294`` with ``S=277,294``, and the first number of
            # ``S`` is the ``for`` header, not the point (GH #222 T1).
            label = f"L{line}" if kind == "line" else f"L{line} {name}"
        else:
            label = name

        waived_by = None
        if not hit:
            waived_by = next((w for w in waivers if w.matches(module, kind, label)), None)
        if waived_by is not None:
            waiver_hits[waived_by.lineno] += 1
            if is_line:
                row.line_waived += 1
            else:
                row.toggle_waived += 1
                row.ctl_waived += int(is_control_toggle(name))
            continue

        if is_line:
            row.line_total += 1
            row.line_hit += int(hit)
            if not hit:
                row.uncovered_lines.append(LineGap(label, kind, line, src))
        else:
            row.toggle_total += 1
            row.toggle_hit += int(hit)
            if is_control_toggle(name):
                row.ctl_total += 1
                row.ctl_hit += int(hit)
                if not hit:
                    row.uncovered_ctl.append(name)
            bucket = toggles[(module, rel)][_signal_of(name)]
            bucket[1] += 1
            bucket[0] += int(hit)

    for key, per_signal in toggles.items():
        rows[key].uncovered_toggles = [
            ToggleGap(sig, hit, total)
            for sig, (hit, total) in sorted(per_signal.items())
            if hit < total
        ]

    modules = sorted(rows.values(), key=lambda r: (not r.triaged, r.tree, r.module))
    if not any(r.triaged for r in modules):
        raise CoverageError(
            "no triaged RTL was measured (rtl/soc, rtl/periph, rtl/npu) -- "
            "the regression ran but nothing in the triaged trees was instrumented"
        )
    return Report(
        modules,
        waivers,
        dict(waiver_hits),
        inputs=[InputStat(n, r, h) for n, (r, h) in input_stats.items()],
        consistency=_consistency(per_input),
    )


def _consistency(
    per_input: dict[tuple[str, str], dict[str, set[tuple[str, str, str, int, int, str, str]]]],
) -> list[Consistency]:
    """Modules measured by >= 2 inputs whose point sets differ, worst overlap first."""
    out: list[Consistency] = []
    for (module, rel), by_source in sorted(per_input.items()):
        if len(by_source) < 2:
            continue
        sets = list(by_source.values())
        everything = set().union(*sets)
        shared = set.intersection(*sets)
        if len(shared) == len(everything):
            continue
        only = {
            src: len(keys - set().union(*(o for s2, o in by_source.items() if s2 != src)))
            for src, keys in by_source.items()
        }
        pct = 100.0 * len(shared) / len(everything)
        out.append(
            Consistency(
                module, rel, len(shared), len(everything), only, pct < CONSISTENCY_SUSPECT_PCT
            )
        )
    return sorted(out, key=lambda c: (c.shared / c.total, c.module))


# ------------------------------------------------------------------------------------ gate


@dataclass(frozen=True)
class Ratchet:
    """One ratchet entry: a per-module control-toggle floor for a known, bead-tracked gap."""

    module: str
    floor: float
    bead: str
    justification: str
    lineno: int


@dataclass(frozen=True)
class GateConfig:
    line_floor: float = LINE_FLOOR_PCT
    toggle_floor: float = TOGGLE_FLOOR_PCT
    ratchet: dict[str, Ratchet] = field(default_factory=dict)
    line_trees: tuple[str, ...] = ()  # line-only gated trees (bead a5ze)


@dataclass(frozen=True)
class GateFailure:
    module: str
    check: str  # "line" | "toggle" | "unmeasured" | "inconsistent"
    detail: str


@dataclass
class GateResult:
    config: GateConfig
    failures: list[GateFailure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    modules_gated: int = 0

    @property
    def passed(self) -> bool:
        return not self.failures


def load_ratchet(path: Path) -> dict[str, Ratchet]:
    """Parse the ratchet file (``module | floor | bead | justification``); defects are errors."""
    if not path.is_file():
        raise CoverageError(f"{path}: ratchet file is missing")
    entries: dict[str, Ratchet] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        where = f"{path}:{lineno}"
        parts = [p.strip() for p in re.split(r"\s+\|\s+", stripped + " ", maxsplit=3)]
        if len(parts) != 4 or not parts[3]:
            raise CoverageError(
                f"{where}: expected 'module | floor | bead | justification' "
                f"(4 fields; a justification is mandatory)"
            )
        module, floor_text, bead, justification = parts
        try:
            floor = float(floor_text)
        except ValueError as exc:
            raise CoverageError(f"{where}: floor {floor_text!r} is not a number") from exc
        if not 0.0 <= floor <= 100.0:
            raise CoverageError(f"{where}: floor {floor} must be within 0..100")
        if not bead:
            raise CoverageError(f"{where}: bead is empty -- every ratchet entry tracks a gap")
        if module in entries:
            raise CoverageError(
                f"{where}: duplicate entry for {module} (first at line {entries[module].lineno})"
            )
        entries[module] = Ratchet(module, floor, bead, justification, lineno)
    return entries


def _below(hit: int, total: int, floor: float) -> bool:
    """True when ``hit/total`` is under ``floor`` %; exact at the boundary (95/100 meets 95)."""
    return hit * 100 < floor * total


def evaluate_gate(report: Report, cfg: GateConfig) -> GateResult:
    """Apply the line and control-toggle floors to the triaged modules, plus the line floor to
    the modules of ``cfg.line_trees``.  Raises CoverageError if a line-gated tree is absent."""
    res = GateResult(cfg)
    triaged = [r for r in report.modules if r.triaged]
    line_only = [r for r in report.modules if not r.triaged and r.tree in cfg.line_trees]
    missing = [t for t in cfg.line_trees if not any(r.tree == t for r in line_only)]
    if missing:
        raise CoverageError(
            f"line-gated tree(s) {', '.join(missing)} not measured -- the gate needs the "
            "CPU/cache/GPU input (pass its .dat with --dat, or --line-gate-trees '' for a "
            "SoC-only run); a gate over data that lacks them is not a pass"
        )
    res.modules_gated = len(triaged) + len(line_only)
    for r in triaged:
        _gate_line(r, cfg, res)
        _gate_toggle(r, cfg, res)
        if not (r.line_total or r.line_waived or r.ctl_total or r.ctl_waived):
            res.failures.append(
                GateFailure(
                    r.module,
                    "unmeasured",
                    "no line points and no control signals were measured -- nothing to gate "
                    f"on ({r.file}); a module with nothing measured is not a pass",
                )
            )
    suspect = {(c.module, c.file): c for c in report.consistency if c.suspect}
    for r in line_only:
        _gate_line(r, cfg, res)
        bad = suspect.get((r.module, r.file))
        if bad is not None:
            res.failures.append(
                GateFailure(
                    r.module,
                    "inconsistent",
                    f"the inputs disagree on this module's point set ({bad.shared}/{bad.total} "
                    "points shared), so its line % is not trustworthy; regenerate every input "
                    "from the same commit with the same Verilator",
                )
            )
    known = {r.module for r in triaged}
    for name, entry in sorted(cfg.ratchet.items()):
        if name not in known:
            res.warnings.append(
                f"ratchet entry at line {entry.lineno} ({name}, {entry.bead}) is stale: no such "
                f"triaged module in this report -- remove or fix it"
            )
    return res


def _gate_line(r: ModuleRow, cfg: GateConfig, res: GateResult) -> None:
    if r.line_total == 0:
        if r.line_waived:
            res.notes.append(
                f"{r.module}: line gate n/a, all {r.line_waived} line points are waived"
            )
        else:
            res.notes.append(f"{r.module}: line gate n/a, no line points (pure wiring)")
        return
    if _below(r.line_hit, r.line_total, cfg.line_floor):
        res.failures.append(
            GateFailure(
                r.module,
                "line",
                f"line {r.line_hit}/{r.line_total} = {_fmt_pct(r.line_pct)} % "
                f"< floor {cfg.line_floor:g} %; uncovered: "
                + ", ".join(_gap_text(g) for g in sorted(r.uncovered_lines, key=lambda g: g.line)),
            )
        )


def _gate_toggle(r: ModuleRow, cfg: GateConfig, res: GateResult) -> None:
    entry = cfg.ratchet.get(r.module)
    if r.ctl_total == 0:
        why = (
            f"all {r.ctl_waived} control points are waived"
            if r.ctl_waived
            else "no control signals"
        )
        res.notes.append(f"{r.module}: control-toggle gate n/a, {why}")
        return
    if entry is not None:
        floor, label = entry.floor, f"ratchet floor {entry.floor:g} % ({entry.bead})"
    else:
        floor, label = cfg.toggle_floor, f"floor {cfg.toggle_floor:g} %"
    pct = r.ctl_pct
    assert pct is not None
    if _below(r.ctl_hit, r.ctl_total, floor):
        shown = ", ".join(r.uncovered_ctl[:12]) + (" ..." if len(r.uncovered_ctl) > 12 else "")
        res.failures.append(
            GateFailure(
                r.module,
                "toggle",
                f"control toggle {r.ctl_hit}/{r.ctl_total} = {pct:.1f} % < {label}; "
                f"not toggled: {shown}",
            )
        )
    elif entry is not None and pct - entry.floor > RATCHET_HEADROOM_PCT:
        res.warnings.append(
            f"{r.module}: control toggle {pct:.1f} % is {pct - entry.floor:.1f} points above its "
            f"ratchet floor {entry.floor:g} % ({entry.bead}) -- raise the floor"
            + (" or remove the entry" if pct >= cfg.toggle_floor else "")
        )


# --------------------------------------------------------------------------- rendering


def _fmt_pct(pct: float | None) -> str:
    return "-" if pct is None else f"{pct:.1f}"


def _totals(rows: list[ModuleRow]) -> dict[str, float | int | None]:
    lh = sum(r.line_hit for r in rows)
    lt = sum(r.line_total for r in rows)
    th = sum(r.toggle_hit for r in rows)
    tt = sum(r.toggle_total for r in rows)
    return {
        "modules": len(rows),
        "line_hit": lh,
        "line_total": lt,
        "line_pct": None if lt == 0 else round(100.0 * lh / lt, 2),
        "toggle_hit": th,
        "toggle_total": tt,
        "toggle_pct": None if tt == 0 else round(100.0 * th / tt, 2),
        "modules_below_line_floor": sum(
            1 for r in rows if r.line_pct is not None and r.line_pct < LINE_FLOOR_PCT
        ),
    }


def _table(rows: list[ModuleRow]) -> list[str]:
    out = [
        "| Module | Tree | Line % | Line hit/total | Toggle % | Toggle hit/total "
        "| Waived (line/toggle) |",
        "| :----- | :--- | -----: | -------------: | -------: | ---------------: "
        "| -------------------: |",
    ]
    for r in rows:
        out.append(
            f"| {r.module} | {r.tree} | {_fmt_pct(r.line_pct)} | {r.line_hit}/{r.line_total} "
            f"| {_fmt_pct(r.toggle_pct)} | {r.toggle_hit}/{r.toggle_total} "
            f"| {r.line_waived}/{r.toggle_waived} |"
        )
    t = _totals(rows)
    out.append(
        f"| **Total ({t['modules']} modules)** | | **{_fmt_pct(t['line_pct'])}** "  # type: ignore[arg-type]
        f"| {t['line_hit']}/{t['line_total']} | **{_fmt_pct(t['toggle_pct'])}** "  # type: ignore[arg-type]
        f"| {t['toggle_hit']}/{t['toggle_total']} | |"
    )
    return out


def _gap_text(gap: LineGap) -> str:
    """Label, plus the ``S`` span when it starts on another line (a generate-loop body)."""
    start = _first_src_line(gap.span, gap.line)
    return gap.label if start == gap.line else f"{gap.label} (span {gap.span})"


def _gaps(rows: list[ModuleRow]) -> list[str]:
    out: list[str] = []
    for r in rows:
        if not r.uncovered_lines and not r.uncovered_toggles:
            continue
        out.append(f"### {r.module} (`{r.file}`)")
        out.append("")
        if r.uncovered_lines:
            labels = ", ".join(
                _gap_text(g) for g in sorted(r.uncovered_lines, key=lambda g: g.line)
            )
            out.append(f"- Uncovered line/branch points ({len(r.uncovered_lines)}): {labels}")
        never = [g for g in r.uncovered_toggles if g.never_toggles]
        partial = [g for g in r.uncovered_toggles if not g.never_toggles]
        if never:
            names = ", ".join(f"{g.signal} ({g.total} pts)" for g in never)
            out.append(f"- Signals that never toggle ({len(never)}): {names}")
        if partial:
            names = ", ".join(f"{g.signal} ({g.hit}/{g.total})" for g in partial)
            out.append(f"- Signals toggling in one direction/bit only ({len(partial)}): {names}")
        out.append("")
    return out


def _inputs_section(report: Report) -> list[str]:
    """Per-input contribution and the cross-input consistency table (multi-input runs only)."""
    if len(report.inputs) < 2:
        return []
    out = [
        "## Inputs",
        "",
        "| Input | Reportable points | Hit |",
        "| :---- | ----------------: | --: |",
        *(f"| {i.name} | {i.reportable} | {i.hit} |" for i in report.inputs),
        "",
    ]
    if report.consistency:
        out += [
            "## Cross-input point-set consistency",
            "",
            "Modules measured by more than one input whose point sets differ.  The union is "
            "reported; an overlap",
            f"below {CONSISTENCY_SUSPECT_PCT:.0f} % means the inputs disagree on point identity "
            "(different Verilator version or",
            "source revision) and the module's denominator is inflated -- re-run both inputs "
            "on one toolchain.",
            "",
            "| Module | File | Shared/total | Only in | Status |",
            "| :----- | :--- | -----------: | :------ | :----- |",
        ]
        for c in report.consistency:
            only = ", ".join(f"{k}: {v}" for k, v in c.only_in.items())
            status = "SUSPECT" if c.suspect else "minor (parameter variants)"
            out.append(f"| {c.module} | `{c.file}` | {c.shared}/{c.total} | {only} | {status} |")
        out.append("")
    else:
        out += [
            "Cross-input point-set consistency: all shared modules have identical point sets.",
            "",
        ]
    return out


def _gate_section(report: Report, gate: GateResult) -> list[str]:
    """Per-module gate table, verdict, failures, notes and warnings (``--gate`` runs only)."""
    cfg = gate.config
    out = [
        "## Gate",
        "",
        f"Line floor {cfg.line_floor:g} % per module; control-signal toggle floor "
        f"{cfg.toggle_floor:g} % (1-bit scalar signals only), with {len(cfg.ratchet)} ratchet "
        f"override(s).  Triaged trees"
        + (
            f"; {', '.join(cfg.line_trees)} are line-only (no toggle gate)."
            if cfg.line_trees
            else " only."
        ),
        "",
        "| Module | Line % | Line hit/total | Control toggle % | Control hit/total "
        "| Control floor | Status |",
        "| :----- | -----: | -------------: | ---------------: | ----------------: "
        "| ------------: | :----- |",
    ]
    bad = {f.module for f in gate.failures}
    for r in (r for r in report.modules if r.triaged or r.tree in cfg.line_trees):
        entry = cfg.ratchet.get(r.module)
        floor = f"{entry.floor:g} (ratchet)" if entry else f"{cfg.toggle_floor:g}"
        if not r.triaged:
            floor = "line-only"
        out.append(
            f"| {r.module} | {_fmt_pct(r.line_pct)} | {r.line_hit}/{r.line_total} "
            f"| {_fmt_pct(r.ctl_pct)} | {r.ctl_hit}/{r.ctl_total} | {floor} "
            f"| {'FAIL' if r.module in bad else 'pass'} |"
        )
    out += [
        "",
        f"**Gate {'PASS' if gate.passed else 'FAIL'}**: {gate.modules_gated} gated modules, "
        f"{len(gate.failures)} failure(s).",
        "",
    ]
    for f in gate.failures:
        out.append(f"- FAIL `{f.module}` [{f.check}]: {f.detail}")
    out += [f"- note: {n}" for n in gate.notes]
    out += [f"- WARNING: {w}" for w in gate.warnings]
    out.append("")
    return out


def render_markdown(report: Report, gate: GateResult | None = None) -> str:
    triaged = [r for r in report.modules if r.triaged]
    info = [r for r in report.modules if not r.triaged]
    verdict = (
        "Gate enforced on the triaged trees (and the line floor on the line-only trees "
        "when enabled): see the Gate section below "
        "(`docs/verification/SOC_COVERAGE_REPORT.md`)."
        if gate is not None
        else "Informational: no coverage percentage gates "
        "(see `docs/verification/SOC_COVERAGE_REPORT.md`)."
    )
    lines = [
        "# SoC line + toggle coverage",
        "",
        verdict,
        "Line % = `v_line` + `v_branch` points, toggle % = `v_toggle` points "
        "(per bit, per direction);",
        "a point is hit if any instance in any testbench hit it. "
        "Waived points are removed from the",
        "denominator; `Waived` shows how many.",
        "",
        "## Triaged trees (rtl/soc, rtl/periph, rtl/npu)",
        "",
        *_table(triaged),
        "",
    ]
    if info:
        lines += [
            "## Informational trees (rtl/cpu, rtl/mem, rtl/gpu)",
            "",
            *_table(info),
            "",
        ]
    lines += _inputs_section(report)
    if gate is not None:
        lines += _gate_section(report, gate)
    lines += ["## Uncovered items, triaged trees", "", *(_gaps(triaged) or ["None.", ""])]
    lines += ["## Waivers", ""]
    if report.waivers:
        lines += [
            "| Module | Kind | Pattern | Cat | Points waived | Justification |",
            "| :----- | :--- | :------ | :-- | ------------: | :------------ |",
        ]
        for w in report.waivers:
            n = report.waiver_hits.get(w.lineno, 0)
            lines.append(
                f"| {w.module} | {w.kind} | `{w.pattern}` | {w.category} | {n} "
                f"| {w.justification} |"
            )
        lines.append("")
        for w in report.unused_waivers:
            lines.append(
                f"WARNING: waiver on line {w.lineno} ({w.module} / `{w.pattern}`) matched no "
                f"uncovered point -- stale, remove it."
            )
        lines.append("")
    else:
        lines += ["None.", ""]
    return "\n".join(lines)


def _count_dict(hit: int, total: int, waived: int, pct: float | None, raw: float | None) -> dict:
    return {
        "hit": hit,
        "total": total,
        "waived": waived,
        "pct": None if pct is None else round(pct, 2),
        "raw_pct": None if raw is None else round(raw, 2),
    }


def gate_to_dict(gate: GateResult) -> dict:
    cfg = gate.config
    return {
        "passed": gate.passed,
        "line_floor": cfg.line_floor,
        "toggle_floor": cfg.toggle_floor,
        "line_trees": list(cfg.line_trees),
        "ratchet": {
            m: {"floor": e.floor, "bead": e.bead, "justification": e.justification}
            for m, e in sorted(cfg.ratchet.items())
        },
        "modules_gated": gate.modules_gated,
        "failures": [
            {"module": f.module, "check": f.check, "detail": f.detail} for f in gate.failures
        ],
        "notes": gate.notes,
        "warnings": gate.warnings,
    }


def report_to_dict(report: Report, gate: GateResult | None = None) -> dict:
    """JSON-serialisable form of the report; ``gate`` adds control-toggle numbers + verdict."""
    modules = []
    for r in report.modules:
        modules.append(
            {
                "module": r.module,
                "file": r.file,
                "tree": r.tree,
                "triaged": r.triaged,
                "line": _count_dict(
                    r.line_hit, r.line_total, r.line_waived, r.line_pct, r.line_raw_pct
                ),
                "toggle": _count_dict(
                    r.toggle_hit, r.toggle_total, r.toggle_waived, r.toggle_pct, r.toggle_raw_pct
                ),
                "uncovered_lines": [
                    g.label for g in sorted(r.uncovered_lines, key=lambda g: g.line)
                ],
                "uncovered_toggles": [
                    {
                        "signal": g.signal,
                        "hit": g.hit,
                        "total": g.total,
                        "never_toggles": g.never_toggles,
                    }
                    for g in r.uncovered_toggles
                ],
            }
        )
    if gate is not None:
        for entry, r in zip(modules, report.modules, strict=True):
            entry["control_toggle"] = _count_dict(
                r.ctl_hit, r.ctl_total, r.ctl_waived, r.ctl_pct, None
            )
            entry["uncovered_control"] = list(r.uncovered_ctl)
    return {
        **({"gate": gate_to_dict(gate)} if gate is not None else {}),
        "summary": {
            "triaged": _totals([r for r in report.modules if r.triaged]),
            "informational": _totals([r for r in report.modules if not r.triaged]),
        },
        "modules": modules,
        "waivers": [
            {
                "module": w.module,
                "kind": w.kind,
                "pattern": w.pattern,
                "category": w.category,
                "justification": w.justification,
                "points_waived": report.waiver_hits.get(w.lineno, 0),
            }
            for w in report.waivers
        ],
        "unused_waivers": [w.lineno for w in report.unused_waivers],
        "inputs": [
            {"name": i.name, "reportable": i.reportable, "hit": i.hit} for i in report.inputs
        ],
        "consistency": [
            {
                "module": c.module,
                "file": c.file,
                "shared": c.shared,
                "total": c.total,
                "only_in": c.only_in,
                "suspect": c.suspect,
            }
            for c in report.consistency
        ],
    }


# ------------------------------------------------------------------------------------ CLI


def _parse_inputs(paths: list[Path]) -> list[Point]:
    """Parse every input; label by file name, or by full path when two names collide."""
    names = [p.name for p in paths]
    points: list[Point] = []
    for path in paths:
        label = str(path) if names.count(path.name) > 1 else path.name
        points += parse_dat(path, label)
    return points


def main(argv: list[str]) -> int:
    """CLI entry point; see the module docstring for the contract."""
    default_root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--dat",
        required=True,
        action="append",
        type=Path,
        help="merged Verilator coverage .dat; repeat to merge several (bead 1eyv)",
    )
    ap.add_argument(
        "--root", type=Path, default=default_root, help="repo root (default: this repo)"
    )
    ap.add_argument("--waivers", type=Path, help="waiver file (module | kind | regex | b | why)")
    ap.add_argument("--out-md", type=Path, help="write the markdown report here")
    ap.add_argument("--out-json", type=Path, help="write the JSON report here")
    ap.add_argument(
        "--gate",
        action="store_true",
        help="enforce the line + control-toggle floors on the triaged trees (exit 1 on failure)",
    )
    ap.add_argument(
        "--line-floor", type=float, help=f"gate: line floor %% (default {LINE_FLOOR_PCT:g})"
    )
    ap.add_argument(
        "--toggle-floor",
        type=float,
        help=f"gate: control-signal toggle floor %% (default {TOGGLE_FLOOR_PCT:g})",
    )
    ap.add_argument(
        "--line-gate-trees",
        default=None,
        metavar="TREES",
        help="gate: comma-separated rtl/cpu|mem|gpu trees that also get the LINE floor "
        f"(default {','.join(LINE_GATED_TREES)}; empty string = triaged trees only). "
        "A tree with no measured module is an error",
    )
    ap.add_argument(
        "--toggle-ratchet",
        type=Path,
        help="gate: per-module control-toggle floors for known gaps (module | floor | bead | why)",
    )
    args = ap.parse_args(argv[1:])
    if not args.gate and (
        args.line_floor is not None
        or args.toggle_floor is not None
        or args.toggle_ratchet is not None
        or args.line_gate_trees is not None
    ):
        ap.error(
            "--line-floor, --toggle-floor, --toggle-ratchet and --line-gate-trees require --gate"
        )
    if args.line_gate_trees is None:
        line_trees = LINE_GATED_TREES
    else:
        line_trees = tuple(t.strip() for t in args.line_gate_trees.split(",") if t.strip())
        unknown = [t for t in line_trees if t not in LINE_GATED_TREES]
        if unknown:
            ap.error(
                f"--line-gate-trees: {', '.join(unknown)} is not one of "
                f"{', '.join(LINE_GATED_TREES)} (the triaged trees are always gated)"
            )

    try:
        waivers = load_waivers(args.waivers) if args.waivers else []
        report = build_report(_parse_inputs(args.dat), args.root.resolve(), waivers)
        gate: GateResult | None = None
        if args.gate:
            cfg = GateConfig(
                line_floor=LINE_FLOOR_PCT if args.line_floor is None else args.line_floor,
                toggle_floor=TOGGLE_FLOOR_PCT if args.toggle_floor is None else args.toggle_floor,
                ratchet=load_ratchet(args.toggle_ratchet) if args.toggle_ratchet else {},
                line_trees=line_trees,
            )
            gate = evaluate_gate(report, cfg)
    except CoverageError as exc:
        print(f"coverage_report: ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    markdown = render_markdown(report, gate)
    if args.out_md:
        args.out_md.write_text(markdown + "\n", encoding="utf-8")
    if args.out_json:
        args.out_json.write_text(
            json.dumps(report_to_dict(report, gate), indent=2) + "\n", encoding="utf-8"
        )
    if not args.out_md:
        print(markdown)

    t = report_to_dict(report)["summary"]["triaged"]
    tail = "" if gate is not None else " (informational)"
    print(
        f"coverage_report: triaged {t['modules']} modules, line {t['line_hit']}/{t['line_total']} "
        f"({_fmt_pct(t['line_pct'])} %), toggle {t['toggle_hit']}/{t['toggle_total']} "
        f"({_fmt_pct(t['toggle_pct'])} %), {t['modules_below_line_floor']} below the "
        f"{LINE_FLOOR_PCT:.0f} % line floor{tail}"
    )
    for w in report.unused_waivers:
        print(f"coverage_report: WARNING: stale waiver at line {w.lineno}", file=sys.stderr)
    for c in report.consistency:
        if c.suspect:
            print(
                f"coverage_report: WARNING: {c.module}: inputs disagree on its point set "
                f"({c.shared}/{c.total} shared) -- denominator inflated, see the report",
                file=sys.stderr,
            )
    if gate is None:
        return EXIT_OK
    for w in gate.warnings:
        print(f"coverage_report: GATE WARNING: {w}", file=sys.stderr)
    if gate.passed:
        print(
            f"coverage_report: GATE PASS: {gate.modules_gated} gated modules meet the "
            f"{gate.config.line_floor:g} % line floor and the control-toggle floors",
        )
        return EXIT_OK
    print(
        f"coverage_report: GATE FAIL: {len({f.module for f in gate.failures})} module(s), "
        f"{len(gate.failures)} failure(s):",
        file=sys.stderr,
    )
    for f in gate.failures:
        print(f"coverage_report:   {f.module} [{f.check}] {f.detail}", file=sys.stderr)
    return EXIT_GATE_FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv))
