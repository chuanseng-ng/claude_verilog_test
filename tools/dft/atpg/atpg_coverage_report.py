#!/usr/bin/env python3
"""Turn a Quaigh `atpg` log into a coverage record with its exclusion statement (bead j41m.15).

usage: atpg_coverage_report.py QUAIGH_LOG [--metrics metrics.json] [--exclusions exclusions.json] [--label NAME] [--out report.json] [--md]

Definitions (DFT_ARCHITECTURE 2.1):
    fault coverage = detected / total
    test coverage  = detected / (total - proven untestable)
`total` is the universe Quaigh used (collapsed faults, `Fault::all_unique`, unless --with-redundant-faults).
`proven untestable` is Quaigh's `unobservable=N`: in quaigh 0.0.6 atpg.rs a fault is counted there only when
`find_pattern_detecting_fault` returns None, i.e. the Kissat miter good-vs-faulty is UNSAT (a complete proof in the
cut as given).  Faults that are neither detected nor proven are `unresolved` and stay undetected in both numbers.

Quaigh prints the final counts through tqdm (carriage returns) and only `Generated ... total` / `Kept ...` as normal
lines, so a log is a result only when the `Kept` line is present; a log from a run killed by the cap or the wall limit is
reported INCOMPLETE and carries no coverage number.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

ANALYZING = re.compile(
    r"Analyzing network with (\d+) inputs, (\d+) outputs, (\d+) gates, (\d+) possible faults, (\d+) unique faults")
GENERATED = re.compile(r"Generated (\d+) patterns total, detecting (\d+)/(\d+) faults")
KEPT = re.compile(r"Kept (\d+) patterns, detecting (\d+)/(\d+) faults")
UNOBS = re.compile(r"unobservable=(\d+)")


def parse_log(text: str) -> dict:
    text = text.replace("\r", "\n")
    out = {"complete": False, "inconsistent": False, "untestable_proven": 0}
    m = ANALYZING.search(text)
    if m:
        out.update(inputs=int(m[1]), outputs=int(m[2]), gates=int(m[3]), faults_all=int(m[4]), faults_universe=int(m[5]))
    g = GENERATED.findall(text)
    k = KEPT.findall(text)
    u = UNOBS.findall(text)
    if u:
        out["untestable_proven"] = int(u[-1])
    if g:
        out["patterns_generated"] = int(g[-1][0])
    if k:
        out["patterns_kept"] = int(k[-1][0])
        out["detected"] = int(k[-1][1])
        out["total"] = int(k[-1][2])
        out["complete"] = True
        if g and (int(g[-1][1]), int(g[-1][2])) != (out["detected"], out["total"]):
            out["inconsistent"] = True
    return out


def coverage(detected: int, total: int, untestable: int) -> dict:
    testable = total - untestable
    return {
        "unresolved": total - detected - untestable,
        "fault_coverage_pct": 100.0 * detected / total if total else None,
        "test_coverage_pct": 100.0 * detected / testable if testable else None,
    }


STATEMENT = (
    "Fault universe excludes: {tck} tck_i-clocked and {sck} scan_clk_i-clocked flops (TAP and MBIST TDRs, unscanned, "
    "tested through JTAG: user decision 2026-10-26), {key} crypto key flops (decision 3, masked in scan mode); "
    "{hold} scan-view hold-masked capture flops have their D pin unobserved (Q still shift-controllable)."
)


def exclusion_statement(excl: Optional[dict]) -> str:
    if not excl:
        return "No exclusions declared for this run."
    return STATEMENT.format(
        tck=excl.get("tck_flops", 0), sck=excl.get("scan_clk_flops", 0),
        key=excl.get("crypto_key_flops", 0), hold=excl.get("hold_masked_flops", 0))


def build_report(log_text: str, metrics: Optional[dict], exclusions: Optional[dict], label: str) -> dict:
    p = parse_log(log_text)
    rep = {"label": label, "metrics": metrics, "exclusions": exclusions,
           "exclusion_statement": exclusion_statement(exclusions), "log": p}
    run_ok = metrics is None or bool(metrics.get("completed"))
    if not p["complete"] or not run_ok:
        rep.update(status="INCOMPLETE", detected=p.get("detected"), total=p.get("total"),
                   fault_coverage_pct=None, test_coverage_pct=None)
        return rep
    if p["inconsistent"]:
        rep.update(status="INCONSISTENT", detected=p["detected"], total=p["total"],
                   fault_coverage_pct=None, test_coverage_pct=None)
        return rep
    cov = coverage(p["detected"], p["total"], p["untestable_proven"])
    rep.update(status="OK", detected=p["detected"], total=p["total"],
               untestable_proven=p["untestable_proven"], patterns_kept=p["patterns_kept"], **cov)
    return rep


def render_markdown(rep: dict) -> str:
    if rep["status"] != "OK":
        return f"**{rep['label']}**: {rep['status']} (no coverage number)\n\n{rep['exclusion_statement']}\n"
    return (
        f"**{rep['label']}**: faults {rep['total']}, detected {rep['detected']}, proven untestable {rep['untestable_proven']}, "
        f"unresolved {rep['unresolved']}; fault coverage {rep['fault_coverage_pct']:.2f} %, "
        f"test coverage {rep['test_coverage_pct']:.2f} %, patterns {rep['patterns_kept']}.\n\n{rep['exclusion_statement']}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--metrics")
    ap.add_argument("--exclusions")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args(argv)
    metrics = json.loads(Path(a.metrics).read_text()) if a.metrics else None
    excl = json.loads(Path(a.exclusions).read_text()) if a.exclusions else None
    rep = build_report(Path(a.log).read_text(errors="replace"), metrics, excl, a.label)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1))
    print(render_markdown(rep) if a.md else json.dumps({k: rep.get(k) for k in (
        "label", "status", "total", "detected", "untestable_proven", "unresolved", "fault_coverage_pct", "test_coverage_pct")}))
    return 0 if rep["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
