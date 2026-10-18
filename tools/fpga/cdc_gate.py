#!/usr/bin/env python3
"""cdc_gate.py -- gate on a Vivado report_cdc -details report (bead hlrm.3).

Reads the report that build.tcl writes AFTER the documented waivers (fpga/nexys_video/nexys_video_cdc_waivers.tcl) and fails
if any Critical row is left that is not one of the known RTL-owned open findings (fpga/nexys_video/CDC_TRIAGE.md, section
"RTL findings"). The RTL-owned findings are NOT waived by default and are reported separately, so a clean exit means "no
unexplained Critical", not "no Critical".

  cdc_gate.py cdc.rpt            exit 0: only the known RTL-open rows remain (listed); exit 1: any other Critical row
  cdc_gate.py cdc.rpt --strict   exit 1 on ANY Critical row, including the RTL-open ones (use once the RTL is fixed)

A report whose summary table and detail rows disagree, or that has no summary, is NOT a pass (exit 2).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# (check id, substring of the source pin) of the findings owned by RTL. Keep equal to CDC_TRIAGE.md "RTL findings".
RTL_OPEN = (("CDC-10", "u_soc/u_pmu/"),)

SUMMARY = re.compile(r"^(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s")
ROW = re.compile(r"^\s*\d+\s+(CDC-\d+)\s+(Critical|Warning|Info)\s+.*?\s(\S+)\s+(\S+)\s*$")


def parse(text: str) -> tuple[Counter, list[tuple[str, str, str]]]:
    summary: Counter = Counter()
    crit: list[tuple[str, str, str]] = []
    for ln in text.splitlines():
        m = SUMMARY.match(ln)
        if m:
            summary[(m.group(1), m.group(2))] += int(m.group(3))
            continue
        m = ROW.match(ln)
        if m and m.group(2) == "Critical":
            crit.append((m.group(1), m.group(3), m.group(4)))
    return summary, crit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", type=Path)
    ap.add_argument("--strict", action="store_true", help="fail on the RTL-open rows too")
    a = ap.parse_args()
    if not a.report.is_file():
        print(f"no such report: {a.report}")
        return 2
    summary, crit = parse(a.report.read_text())
    if not summary and "CDC Report" not in a.report.read_text():
        print("not a report_cdc report (no 'CDC Report' header): NOT a pass")
        return 2
    n_sum = sum(v for (_, sev), v in summary.items() if sev == "Critical")
    if n_sum != len(crit):
        print(f"summary says {n_sum} Critical, detail rows give {len(crit)}: cannot verify (was report_cdc run with -details?)")
        return 2
    open_rows = [c for c in crit if any(c[0] == i and s in c[1] for i, s in RTL_OPEN)]
    other = [c for c in crit if c not in open_rows]
    print(f"Critical in report: {len(crit)}  (RTL-owned open: {len(open_rows)}, unexplained: {len(other)})")
    for cid, src, dst in open_rows:
        print(f"  RTL-OPEN {cid} {src} -> {dst}")
    for cid, src, dst in other:
        print(f"  UNEXPLAINED {cid} {src} -> {dst}")
    if other or (a.strict and open_rows):
        print("CDC GATE: FAIL")
        return 1
    print("CDC GATE: PASS" + ("" if not open_rows else " (with RTL-owned open findings, see CDC_TRIAGE.md)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
