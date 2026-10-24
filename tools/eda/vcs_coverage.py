#!/usr/bin/env python3
"""VCS code coverage for the cocotb regressions: instrumented run + urg merge/report.

  vcs_coverage.py run   --area soc|cpu|all [--root DIR] [--jobs N] [--shard JOBSPEC ...]
  vcs_coverage.py merge --root DIR --out DIR

`run` drives tools/eda/run_cocotb_targets.py (the same driver, job lists and results.xml-only verdicts
as the uninstrumented regression) with COVERAGE=1, so every simulation is compiled with
`-cm line+cond+fsm+tgl+branch+assert` and writes its own uniquely named test into the build's
simv.vdb (see tb/cocotb/common/sim_portability.mk).  Instrumentation must not change pass/fail:
the printed pass totals are meant to be compared against the uninstrumented run (soc 872 / cpu 265).

`merge` collects every `*/simv.vdb` below --root, merges them with one `urg` call
(`-dbname <out>/merged -report <out>/urgReport -format both`) and prints how many tests were merged
next to how many simulations were expected (rule: a merge that silently dropped tests must be visible).

Environment: `source tools/eda/sim_env.sh` first (VCS_HOME, licence, venv).  Bounded by --jobs
(default 3: 15 GB host).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "tools/eda/run_cocotb_targets.py"
SPECS = REPO / "tools/eda/regress_specs.py"


def specs(area: str) -> list[str]:
    out = subprocess.run([sys.executable, str(SPECS), area], capture_output=True, text=True, check=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def run_area(area: str, root: Path, jobs: int, only: list[str]) -> dict:
    aroot = root / area
    aroot.mkdir(parents=True, exist_ok=True)
    jl = only or specs(area)
    # sim/ jobs write ./results.xml in place (sim/Makefile cannot relocate it): strictly serial.
    nj = 1 if area == "cpu" else jobs
    js = aroot / "driver.json"
    cmd = [sys.executable, str(DRIVER), "--sim", "vcs", "--root", str(aroot), "--jobs", str(nj),
           "--json", str(js), "--make-arg", "COVERAGE=1", *jl]
    t0 = time.time()
    print(f"[vcs_coverage] {area}: {len(jl)} job(s), --jobs {nj}, root {aroot}", flush=True)
    rc = subprocess.run(cmd).returncode
    data = json.loads(js.read_text()) if js.is_file() else {"chains": []}
    tot = {k: sum(c["totals"][k] for c in data["chains"]) for k in ("tests", "failures", "errors", "skipped")}
    tot["passed"] = tot["tests"] - tot["failures"] - tot["errors"] - tot["skipped"]
    summ = {"area": area, "rc": rc, "wall_s": round(time.time() - t0, 1),
            "chains": len(data["chains"]), "chains_pass": sum(c["verdict"] == "PASS" for c in data["chains"]), **tot}
    print(f"[vcs_coverage] {area}: rc={rc} chains {summ['chains_pass']}/{summ['chains']} PASS, "
          f"tests={tot['tests']} passed={tot['passed']} failed={tot['failures']} errors={tot['errors']} "
          f"skipped={tot['skipped']} wall={summ['wall_s']}s", flush=True)
    (aroot / "summary.json").write_text(json.dumps(summ, indent=1))
    return summ


def count_vdb_tests(vdb: Path) -> int:
    """Number of simulations recorded in one simv.vdb (one directory per -cm_name under snps/coverage/db/testdata)."""
    td = vdb / "snps/coverage/db/testdata"
    if not td.is_dir():
        return 0
    return sum(1 for p in td.iterdir() if p.is_dir() or p.is_file())


def merge(root: Path, out: Path, dbname: str = "merged") -> int:
    vdbs = sorted({p for p in root.rglob("simv.vdb") if p.is_dir()})
    if not vdbs:
        print(f"[vcs_coverage] no simv.vdb below {root}: nothing was instrumented", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    expected = sum(count_vdb_tests(v) for v in vdbs)
    cmd = ["urg", "-full64", "-lca", "-dir", *[str(v) for v in vdbs], "-flex_merge", "modules", "-dbname", str(out / dbname), "-report", str(out / "urgReport"),
           "-format", "both", "-log", str(out / "urg.log")]
    print(f"[vcs_coverage] merging {len(vdbs)} vdb(s), {expected} recorded test(s) -> {out}", flush=True)
    t0 = time.time()
    rc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).returncode
    dash = out / "urgReport/dashboard.txt"
    n = None
    scored = False
    if dash.is_file():
        txt = dash.read_text(errors="replace")
        m = re.search(r"Number of tests:\s*(\d+)", txt)
        n = int(m.group(1)) if m else None
        k = txt.find("Total Coverage Summary")
        row = txt[k:].splitlines()[2].split() if k >= 0 and len(txt[k:].splitlines()) > 2 else []
        scored = any(re.fullmatch(r"\d+(\.\d+)?", x) for x in row)  # all "--" = nothing instrumented
        print(f"[vcs_coverage] Total Coverage Summary row: {' '.join(row)}", flush=True)
    ok = rc == 0 and dash.is_file() and dash.stat().st_mtime >= t0 - 1 and scored
    if not scored:
        print("[vcs_coverage] ERROR: urg reported no coverage scores (databases not instrumented, or the "
              "-cm_hier scope excluded everything); a '--' dashboard is NOT a result", file=sys.stderr)
    print(f"[vcs_coverage] urg rc={rc} wall={time.time() - t0:.0f}s; urg 'Number of tests' = {n}; "
          f"recorded in vdbs = {expected}", flush=True)
    if n is not None and n != expected:
        print(f"[vcs_coverage] WARNING: urg merged {n} tests but the vdbs hold {expected} "
              f"(duplicate -cm_name or a dropped database?)", file=sys.stderr)
    (out / "merge_summary.json").write_text(json.dumps(
        {"vdbs": len(vdbs), "recorded_tests": expected, "urg_tests": n, "urg_rc": rc}, indent=1))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="instrumented regression (then merge + report unless --no-merge)")
    r.add_argument("--area", choices=["soc", "cpu", "all"], default="all")
    r.add_argument("--root", type=Path, default=REPO / "sim_build_cov")
    r.add_argument("--out", type=Path, default=None,
                   help="urg output base dir (default <root>/report); reports land in <out>/<area> (+ <out>/all)")
    r.add_argument("--jobs", type=int, default=3)
    r.add_argument("--no-merge", action="store_true")
    r.add_argument("--keep", action="store_true", help="do not delete a previous <root>/<area> first")
    r.add_argument("jobs_spec", nargs="*", metavar="JOB", help="restrict to these driver job specs")
    m = sub.add_parser("merge", help="urg-merge every simv.vdb below --root")
    m.add_argument("--root", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "merge":
        return merge(a.root.resolve(), a.out.resolve())
    if a.jobs > 3:
        ap.error("--jobs > 3 would risk the 15 GB host with instrumented tb_soc_top builds")
    root = a.root.resolve()
    rc = 0
    areas = ["soc", "cpu"] if a.area == "all" else [a.area]
    for area in areas:
        if not a.keep and (root / area).exists():
            subprocess.run(["rm", "-rf", str(root / area)], check=True)  # stale vdbs would be merged
        s = run_area(area, root, a.jobs, a.jobs_spec)
        rc |= s["rc"]
    if not a.no_merge:
        out = (a.out or root / "report").resolve()
        for area in areas:
            rc |= merge(root / area, out / area)
        if len(areas) > 1:
            rc |= merge(root, out / "all")
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
