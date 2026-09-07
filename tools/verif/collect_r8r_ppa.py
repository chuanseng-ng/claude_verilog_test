#!/usr/bin/env python3
"""Collect the GH #119 Stage 2 (bead r8r) leaf-block PPA numbers into one table.

Reads the latest run of each of the four ASAP7 arms and prints area, cell count,
setup slack, fmax and power. Refuses to report a number it did not actually find
(bead dwp): a missing metric prints as "n/a" and sets a non-zero exit, so an
incomplete sweep can never be mistaken for a complete one.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ARMS = [
    ("coalescer_rtl", "memory_coalescer", "hand-RTL"),
    ("coalescer_hls", "memory_coalescer", "HLS"),
    ("hazard_rtl", "rv32i_hazard_unit", "hand-RTL"),
    ("hazard_hls", "rv32i_hazard_unit", "HLS"),
]
_FMAX = re.compile(r"^\s*(\S+)\s+period_min\s*=\s*([\d.]+)\s+fmax\s*=\s*(\S+)", re.M)


def latest(arm: str) -> Path | None:
    """Newest RUN_* directory for one arm, or None."""
    runs = sorted(Path(f"/nobackup/asap7_{arm}_runs").glob("RUN_*"))
    return runs[-1] if runs else None


def fmax_of(run: Path) -> tuple[str, str]:
    """(period_min ps, fmax MHz) for the first real clock in the STA log."""
    logs = list(run.glob("*staprepnr*/nom_tt_025C_0p7V/sta.log"))
    if not logs:
        return "n/a", "n/a"
    for clk, per, f in _FMAX.findall(logs[0].read_text(errors="replace")):
        if f not in ("inf", "0.00"):  # skip degenerate/unconstrained clocks
            return per, f
    return "n/a", "n/a"


def undriven(run: Path) -> str:
    """Count of 'used but has no driver' wires Yosys reported, or n/a."""
    rpt = run / "05-yosys-synthesis/reports/pre_synth_chk.rpt"
    if not rpt.is_file():
        return "n/a"
    m = re.search(r"Found and reported (\d+) problems", rpt.read_text(errors="replace"))
    return m.group(1) if m else "n/a"


def main() -> int:
    """Print the PPA table; non-zero if any arm or metric is missing."""
    rows, ok = [], True
    for arm, block, flow in ARMS:
        run = latest(arm)
        if run is None or not (run / "final/metrics.json").is_file():
            rows.append((block, flow, *["n/a"] * 7, "MISSING RUN"))
            ok = False
            continue
        m = json.loads((run / "final/metrics.json").read_text())
        per, f = fmax_of(run)
        area = m.get("design__instance__area")
        cells = m.get("design__instance__count")
        # timing__setup__wns is worst NEGATIVE slack: it reads 0.0 on a clean
        # design, so it is deliberately NOT used here: it is not the margin.
        # timing__setup__ws is the worst slack and is what carries the number.
        ws = m.get("timing__setup__ws")
        pwr = m.get("power__total")
        # hazard_rtl is purely combinational and timed against a VIRTUAL clock,
        # so report_clock_min_period yields nothing; its delay is period - slack.
        comb = f"{705.0 - ws:.1f}" if (f == "n/a" and ws is not None) else "-"
        if None in (area, cells, ws, pwr):
            ok = False
        rows.append(
            (
                block,
                flow,
                f"{area:.2f}" if area is not None else "n/a",
                str(cells if cells is not None else "n/a"),
                f"{ws:.1f}" if ws is not None else "n/a",
                comb,
                per,
                f,
                f"{pwr * 1000:.3f}" if pwr is not None else "n/a",
                undriven(run),
            )
        )

    hdr = (
        "block",
        "flow",
        "area um2",
        "cells",
        "setup ws ps",
        "comb ps",
        "Tmin ps",
        "fmax MHz",
        "power mW",
        "undriven",
    )
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]
    line = "  ".join(h.ljust(w[i]) for i, h in enumerate(hdr))
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))
    if not ok:
        print(
            "\nERROR: at least one arm or metric is missing - table is incomplete.", file=sys.stderr
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
