#!/usr/bin/env python3
"""Gate: fail the build when detailed routing committed zero wires.

Motivation (bead claude_verilog_test-xy6): `pnr/scripts/openroad/drt.tcl` (a
local patch to LibreLane, not upstream) wraps the entire `detailed_route` Tcl
call in a `catch {}` so that a single unresolved pin-access point
(`[ERROR DRT-0073]` on a macro pin, `[ERROR DRT-0074]` on a top-level I/O pin)
does not abort the flow. That is reasonable *if* routing otherwise completed
and the error is a handful of stragglers. In practice, on every ASAP7 run
inspected in this repo's history to date -- run 14 (the accepted M11 SoC
sign-off), both GPU 571 MHz sign-off runs, and every CPU tuning run in the
#96 pin_order.cfg campaign -- the pin-access error fires *before* track
assignment ever starts, so `detailed_route` throws immediately, the catch
swallows it, and `write_views` commits a DEF with **zero `ROUTED` nets**.
Every downstream checker (`design__violations`, antenna, DRC) then reports 0
because there is nothing routed to violate -- not because routing is clean.

This is exactly the class of bug bead `dwp` named: a tool that exits 0 with
an empty or absent report must never be read as PASS. This script re-derives
the verdict from the artifacts a completed LibreLane run actually produced,
independent of the flow's own exit code:

  1. `final/def/*.def` must contain at least one `ROUTED ` net record.
  2. `final/metrics.json`'s `route__wirelength__max`, if present, must be > 0.
  3. The `OpenROAD.DetailedRouting` step log must contain zero `[ERROR DRT-*]`
     lines. (A run that routed cleanly but left informational DRT-0xxx *INFO*
     lines is unaffected -- only `[ERROR DRT-` is counted.)

All three must hold for PASS. Any violated check is FAIL, not a warning.

Usage:
    check_asap7_routing.py <run_dir> [--json out.json]

Exit codes:
    0  PASS   detailed routing actually committed wires, no DRT errors
    1  FAIL   zero committed wires and/or unresolved DRT errors -- real signal
    2  ERROR  the run's artifacts could not be found/parsed -- distinct from
              FAIL so an incomplete or missing run can never masquerade as PASS
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

PASS, FAIL, ERROR = 0, 1, 2

MAX_SAMPLE = 20


def _cap(items: list) -> list:
    if len(items) <= MAX_SAMPLE:
        return items
    return items[:MAX_SAMPLE] + [f"... {len(items) - MAX_SAMPLE} more (see raw log)"]


def find_detailedrouting_log(run_dir: str) -> str | None:
    candidates = sorted(
        glob.glob(os.path.join(run_dir, "*-*detailedrouting*", "*.log"))
        + glob.glob(os.path.join(run_dir, "*-*DetailedRouting*", "*.log"))
    )
    # Prefer the log that actually mentions detailed routing, not an
    # unrelated step whose directory name happens to substring-match.
    for c in candidates:
        if "detailedrouting" in os.path.basename(c).lower():
            return c
    return candidates[0] if candidates else None


def count_drt_errors(log_path: str) -> tuple[int, list[str]]:
    text = open(log_path, errors="replace").read()
    lines = re.findall(r"^\[ERROR DRT-\d+\].*$", text, re.M)
    return len(lines), lines


def count_routed_nets(run_dir: str) -> tuple[int, list[str]]:
    def_files = sorted(glob.glob(os.path.join(run_dir, "final", "def", "*.def")))
    total = 0
    for f in def_files:
        with open(f, "rb") as fh:
            total += fh.read().count(b"ROUTED ")
    return total, def_files


def read_wirelength_max(run_dir: str) -> int | None | str:
    metrics_path = os.path.join(run_dir, "final", "metrics.json")
    if not os.path.isfile(metrics_path):
        return "NO_METRICS_JSON"
    try:
        d = json.load(open(metrics_path))
    except Exception as e:  # noqa: BLE001 - surfaced in the verdict, not swallowed
        return f"UNPARSABLE:{e}"
    if "route__wirelength__max" not in d:
        return "MISSING_KEY"
    return d["route__wirelength__max"]


def check(run_dir: str) -> tuple[int, dict]:
    if not os.path.isdir(run_dir):
        return ERROR, {"error": f"run directory not found: {run_dir}"}

    drt_log = find_detailedrouting_log(run_dir)
    if drt_log is None:
        return ERROR, {
            "error": "no OpenROAD.DetailedRouting log found under run_dir",
            "run_dir": run_dir,
        }

    drt_error_count, drt_error_lines = count_drt_errors(drt_log)
    routed_count, def_files = count_routed_nets(run_dir)
    wl_max = read_wirelength_max(run_dir)

    if not def_files:
        return ERROR, {
            "error": "no final/def/*.def found -- run did not reach write_views",
            "run_dir": run_dir,
            "drt_log": drt_log,
            "drt_error_count": drt_error_count,
        }

    reasons = []
    if routed_count == 0:
        reasons.append("final DEF contains zero 'ROUTED ' net records")
    if isinstance(wl_max, int) and wl_max == 0:
        reasons.append("route__wirelength__max == 0 in final/metrics.json")
    if drt_error_count > 0:
        reasons.append(
            f"{drt_error_count} unresolved [ERROR DRT-*] line(s) in "
            "OpenROAD.DetailedRouting log (swallowed by drt.tcl's catch)"
        )

    summary = {
        "run_dir": run_dir,
        "drt_log": drt_log,
        "drt_error_count": drt_error_count,
        "drt_error_sample": _cap(drt_error_lines),
        "routed_net_record_count": routed_count,
        "def_files_checked": def_files,
        "route_wirelength_max": wl_max,
    }

    if reasons:
        summary["fail_reasons"] = reasons
        return FAIL, summary

    return PASS, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", help="LibreLane run directory, e.g. pnr/asap7/soc/runs/RUN_...")
    ap.add_argument("--json", metavar="PATH", help="also write the verdict JSON to this path")
    args = ap.parse_args()

    status, summary = check(args.run_dir)
    verdict = {"status": {PASS: "PASS", FAIL: "FAIL", ERROR: "ERROR"}[status], **summary}
    text = json.dumps(verdict, indent=2, default=str)
    print(text)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(text + "\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
