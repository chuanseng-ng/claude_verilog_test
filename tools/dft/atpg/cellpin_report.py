#!/usr/bin/env python3
"""Coverage on the Sky130 cell-pin fault universe from a Quaigh per-fault report (bead j41m.20).

usage: cellpin_report.py CUT_DIR FAULT_REPORT --label NAME --out report.json [--whole-cut DIR] [--md]

CUT_DIR is the output of `mk_cut.py --cellpin` (cut_sites.txt); FAULT_REPORT is `quaigh atpg|atpg-report --fault-sites
CUT_DIR/cut_sites.txt --fault-report FILE` (patch 0002): line `k S`, fault k = site k // 2 stuck-at (k % 2), S one of
D (detected), U (SAT-proven untestable), R (unresolved), N (not detected, report mode: no SAT ran).

Reported:
  raw          fault coverage D / total, test coverage D / (total - U)   (U only exists for an `atpg` run)
  credited     the scan-path pins SCD and SCE of the scan flops (the only Sky130 pins named so) counted as detected by
               implication: they are exercised by the chain shift/flush test, not by a capture pattern (Tessent's DI class).
               This is a claim on the chain test (bead j41m.19, not yet run), so it is labelled and never the only number.
  by_pin       detected / not detected per pin name, the largest undetected classes first.
  whole        --whole-cut DIR: the same detected count against the pin-fault total of the keep-unscanned cut (the excluded
               cones counted as undetected; the two cuts are not a subset pair, so this is an estimate, as in 18.7).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

SCAN_PATH_PINS = ("SCD", "SCE")


def pin_of(site: str) -> str:
    """Pin name of a site net: an input pin keeps `<inst>.cvtpin_<PIN>`; an output-pin buffer drives the outer net."""
    return site.rsplit(".cvtpin_", 1)[1] if ".cvtpin_" in site else "<output>"


def load_report(path: Path, n_faults: int) -> List[str]:
    st = [""] * n_faults
    for ln in Path(path).read_text().split("\n"):
        if ln.strip():
            k, s = ln.split()
            st[int(k)] = s
    if any(s == "" for s in st):
        raise SystemExit(f"fault report has {sum(s == '' for s in st)} missing faults of {n_faults}")
    return st


def summarise(sites: List[str], st: List[str], whole_faults: Optional[int] = None) -> Dict:
    n = len(st)
    if n != 2 * len(sites):
        raise SystemExit(f"{n} faults in the report vs {len(sites)} sites")
    cnt = {s: st.count(s) for s in "DURN"}
    scan = [k for k in range(n) if pin_of(sites[k // 2]) in SCAN_PATH_PINS]
    scan_set = set(scan)
    d_non = sum(1 for k in range(n) if st[k] == "D" and k not in scan_set)
    u_non = sum(1 for k in range(n) if st[k] == "U" and k not in scan_set)
    sat_ran = bool(cnt["U"] or cnt["R"]) or not cnt["N"]
    rep = {
        "faults": n, "detected": cnt["D"], "untestable_proven": cnt["U"], "unresolved": cnt["R"], "not_detected": cnt["N"],
        "fault_coverage_pct": 100.0 * cnt["D"] / n,
        "test_coverage_pct": 100.0 * cnt["D"] / (n - cnt["U"]) if sat_ran else None,
        "scan_path_pin_faults": len(scan),
        "scan_path_detected_in_capture": sum(st[k] == "D" for k in scan),
        "credited_fault_coverage_pct": 100.0 * (d_non + len(scan)) / n,
        "credited_test_coverage_pct": (100.0 * (d_non + len(scan)) / (n - u_non)) if sat_ran else None,
    }
    by: Dict[str, Dict[str, int]] = {}
    for k in range(n):
        p = pin_of(sites[k // 2])
        by.setdefault(p, {"faults": 0, "detected": 0, "untestable": 0})
        by[p]["faults"] += 1
        by[p]["detected"] += st[k] == "D"
        by[p]["untestable"] += st[k] == "U"
    rep["by_pin"] = dict(sorted(by.items(), key=lambda kv: kv[1]["detected"] - kv[1]["faults"]))
    if whole_faults:
        rep["whole_pin_faults"] = whole_faults
        rep["whole_fault_coverage_pct"] = 100.0 * cnt["D"] / whole_faults
        rep["whole_credited_fault_coverage_pct"] = 100.0 * (d_non + len(scan)) / whole_faults
    return rep


def md(label: str, r: Dict) -> str:
    tc = f"{r['test_coverage_pct']:.2f} %" if r["test_coverage_pct"] is not None else "n/a (report mode)"
    ctc = f"{r['credited_test_coverage_pct']:.2f} %" if r["credited_test_coverage_pct"] is not None else "n/a"
    s = (f"**{label}** (cell pins): faults {r['faults']}, detected {r['detected']}, proven untestable {r['untestable_proven']}, "
         f"unresolved {r['unresolved']}; fault coverage {r['fault_coverage_pct']:.2f} %, test coverage {tc}. "
         f"Scan-path pins SCD/SCE credited (chain test, j41m.19): fault coverage {r['credited_fault_coverage_pct']:.2f} %, "
         f"test coverage {ctc} ({r['scan_path_pin_faults']} faults, {r['scan_path_detected_in_capture']} detected in capture).")
    if "whole_fault_coverage_pct" in r:
        s += (f" Whole-cut estimate: {r['whole_fault_coverage_pct']:.2f} % raw, {r['whole_credited_fault_coverage_pct']:.2f} % "
              f"credited, of {r['whole_pin_faults']} pin faults.")
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cut_dir")
    ap.add_argument("fault_report")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--whole-cut", help="mk_cut.py --cellpin --keep-unscanned output DIR (its cut_info.json pin_faults)")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args(argv)
    sites = (Path(a.cut_dir) / "cut_sites.txt").read_text().split()
    st = load_report(Path(a.fault_report), 2 * len(sites))
    whole = json.loads((Path(a.whole_cut) / "cut_info.json").read_text())["pin_faults"] if a.whole_cut else None
    rep = summarise(sites, st, whole)
    rep["label"] = a.label
    Path(a.out).write_text(json.dumps(rep, indent=1))
    print(md(a.label, rep) if a.md else json.dumps({k: v for k, v in rep.items() if k != "by_pin"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
