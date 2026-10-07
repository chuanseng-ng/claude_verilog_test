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
0 for any coverage level -- the gate is informational (see
``docs/verification/SOC_COVERAGE_REPORT.md``).  Nonzero (2) on a missing, malformed or empty
``.dat``, on a bad waiver file, or when no triaged RTL was measured at all: a clean exit over
no data is never a pass (cf. bead dwp).

Usage::

    coverage_report.py --dat merged.dat [--root <repo>] [--waivers <file>]
                       [--out-md report.md] [--out-json report.json]
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

EXIT_OK, EXIT_ERROR = 0, 2

SOH, STX = "\x01", "\x02"
HEADER_PREFIX = "# SystemC::Coverage-"

TRIAGED_TREES = ("rtl/soc", "rtl/periph", "rtl/npu")
INFORMATIONAL_TREES = ("rtl/cpu", "rtl/mem", "rtl/gpu")
# Behavioural SRAM models are simulation stand-ins for hard macros, not design logic.
EXCLUDED_BASENAME = re.compile(r"^(sram_1rw_|sky130_sram_)")
EXCLUDED_PREFIXES = ("tb/", "sim/")

KINDS = ("line", "toggle", "any")
WAIVABLE_CATEGORIES = ("b",)
LINE_FLOOR_PCT = 95.0

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


@dataclass
class Report:
    modules: list[ModuleRow]
    waivers: list[Waiver]
    waiver_hits: dict[int, int]  # waiver lineno -> matched uncovered points

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


def parse_dat(path: Path) -> list[Point]:
    """Parse a Verilator coverage ``.dat`` into line / branch / toggle points."""
    if not path.is_file():
        raise CoverageError(f"{path}: coverage file is missing")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].startswith(HEADER_PREFIX):
        raise CoverageError(
            f"{path}: not a Verilator coverage file (header '{HEADER_PREFIX}*' missing)"
        )

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
    """Repo-relative POSIX path, or None when the file is outside ``root``."""
    norm = os.path.normpath(file)
    if os.path.isabs(norm):
        try:
            return Path(norm).relative_to(root).as_posix()
        except ValueError:
            return None
    return Path(norm).as_posix()


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


def _signal_of(obj: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", obj.split(":", 1)[0])


def build_report(points: list[Point], root: Path, waivers: list[Waiver]) -> Report:
    """Aggregate points per module (across instances) and apply the waivers."""
    # Pass 1: union over instances.  Identity drops the hierarchy; hit = any instance hit.
    union: dict[tuple[str, str, str, int, int, str, str], bool] = {}
    for p in points:
        rel = _relpath(p.file, root)
        if rel is None or _classify(rel) is None:
            continue
        key = (p.module, rel, p.kind, p.line, p.col, p.name, p.src)
        union[key] = union.get(key, False) or p.count > 0
    if not union:
        raise CoverageError(
            "no reportable RTL points (nothing under rtl/{soc,periph,npu,cpu,mem,gpu})"
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
            continue

        if is_line:
            row.line_total += 1
            row.line_hit += int(hit)
            if not hit:
                row.uncovered_lines.append(LineGap(label, kind, line, src))
        else:
            row.toggle_total += 1
            row.toggle_hit += int(hit)
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
    return Report(modules, waivers, dict(waiver_hits))


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


def render_markdown(report: Report) -> str:
    triaged = [r for r in report.modules if r.triaged]
    info = [r for r in report.modules if not r.triaged]
    lines = [
        "# SoC line + toggle coverage",
        "",
        "Informational: no coverage percentage gates "
        "(see `docs/verification/SOC_COVERAGE_REPORT.md`).",
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


def report_to_dict(report: Report) -> dict:
    """JSON-serialisable form of the report."""
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
    return {
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
    }


# ------------------------------------------------------------------------------------ CLI


def main(argv: list[str]) -> int:
    """CLI entry point; see the module docstring for the contract."""
    default_root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dat", required=True, type=Path, help="merged Verilator coverage .dat")
    ap.add_argument(
        "--root", type=Path, default=default_root, help="repo root (default: this repo)"
    )
    ap.add_argument("--waivers", type=Path, help="waiver file (module | kind | regex | b | why)")
    ap.add_argument("--out-md", type=Path, help="write the markdown report here")
    ap.add_argument("--out-json", type=Path, help="write the JSON report here")
    args = ap.parse_args(argv[1:])

    try:
        waivers = load_waivers(args.waivers) if args.waivers else []
        report = build_report(parse_dat(args.dat), args.root.resolve(), waivers)
    except CoverageError as exc:
        print(f"coverage_report: ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    markdown = render_markdown(report)
    if args.out_md:
        args.out_md.write_text(markdown + "\n", encoding="utf-8")
    if args.out_json:
        args.out_json.write_text(
            json.dumps(report_to_dict(report), indent=2) + "\n", encoding="utf-8"
        )
    if not args.out_md:
        print(markdown)

    t = report_to_dict(report)["summary"]["triaged"]
    print(
        f"coverage_report: triaged {t['modules']} modules, line {t['line_hit']}/{t['line_total']} "
        f"({_fmt_pct(t['line_pct'])} %), toggle {t['toggle_hit']}/{t['toggle_total']} "
        f"({_fmt_pct(t['toggle_pct'])} %), {t['modules_below_line_floor']} below the "
        f"{LINE_FLOOR_PCT:.0f} % line floor (informational)"
    )
    for w in report.unused_waivers:
        print(f"coverage_report: WARNING: stale waiver at line {w.lineno}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
