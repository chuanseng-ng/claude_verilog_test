#!/usr/bin/env python3
"""Run cocotb make targets under SIM=vcs / SIM=xcelium with bounded parallelism and judge them
ONLY from the results.xml files (cocotb 1.x `make` exits 0 even when tests fail).

Why a driver at all: every target of tb/cocotb/{soc,cpu} and sim/ shares a working directory, and
several soc targets run two build points back to back, so the stock ./results.xml keeps only the
last verdict.  With SIM_RESULTS_IN_BUILD=1 (tb/cocotb/common/sim_portability.mk) each build point
writes $(SIM_BUILD)/results__<MODULE>.xml; this script gives every job its own SIM_BUILD_ROOT, runs
it, then reads back every results__*.xml that job produced.

Job spec (positional, repeatable):   AREA:TARGET[:VAR=VAL[,VAR=VAL...]][+AREA:TARGET...]
  AREA   soc | cpu | sim            (tb/cocotb/soc, tb/cocotb/cpu, sim/)
  '+'    chains specs that run SEQUENTIALLY inside one SIM_BUILD_ROOT so they share a compiled model
         (e.g. soc:soc_boot+soc:soc_gpio -- both elaborate tb_soc_top once).

Verdict per job = PASS only if make exited 0 AND at least one results__*.xml exists AND every xml has
>= 1 testcase, 0 <failure>, 0 <error>.  A job whose make exits non-zero or writes no results.xml is
FAIL (missing results.xml == FAIL, by policy).  Skipped testcases are counted and reported; whether
the count is intended is a human judgement, so they never turn a job FAIL by themselves.

Exit status: 0 iff every job PASS.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# cocotb logs non-ASCII (em dashes in test docstrings); under an ASCII locale the logging module raises
# UnicodeEncodeError on every such message.
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "LC_ALL": os.environ.get("LC_ALL") or "C.UTF-8"}
REPO = Path(__file__).resolve().parents[2]
AREA_DIR = {"soc": REPO / "tb/cocotb/soc", "cpu": REPO / "tb/cocotb/cpu", "sim": REPO / "sim"}

# Compile/elab diagnostics, per simulator.  Harmless cocotb/VPI registration noise is counted
# separately so it cannot hide a real error.
DIAG = {
    "vcs": {
        "error": re.compile(r"^Error-\[([^\]]+)\]"),
        "warning": re.compile(r"^Warning-\[([^\]]+)\]"),
    },
    "xcelium": {
        "error": re.compile(r"^(?:xmvlog|xmelab|xmsim|xrun|ncvlog|ncelab)[^\n]*\*E,(\w+)"),
        "warning": re.compile(r"^(?:xmvlog|xmelab|xmsim|xrun|ncvlog|ncelab)[^\n]*\*W,(\w+)"),
    },
}


def parse_results(xml: Path) -> dict:
    try:
        root = ET.parse(xml).getroot()
    except ET.ParseError as e:
        return {"xml": str(xml), "tests": 0, "failures": 0, "errors": 1, "skipped": 0, "parse_error": str(e)}
    cases = list(root.iter("testcase"))
    return {
        "xml": str(xml),
        "tests": len(cases),
        "failures": sum(1 for c in cases if c.find("failure") is not None),
        "errors": sum(1 for c in cases if c.find("error") is not None),
        "skipped": sum(1 for c in cases if c.find("skipped") is not None),
    }


def diag_counts(log: Path, sim: str) -> dict:
    out = {"errors": {}, "warnings": {}}
    pats = DIAG[sim]
    try:
        text = log.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for line in text:
        for kind, key in (("error", "errors"), ("warning", "warnings")):
            m = pats[kind].match(line)
            if m:
                out[key][m.group(1)] = out[key].get(m.group(1), 0) + 1
    return out


def run_spec(sim: str, root: Path, logdir: Path, spec: str, extra_make: list[str]) -> dict:
    area, target, *rest = spec.split(":", 2)
    mvars = [v for v in (rest[0].split(",") if rest and rest[0] else []) if v]
    jroot = root  # per-chain SIM_BUILD_ROOT is created by the caller
    log = logdir / f"{sim}__{area}__{target}{'__' + '_'.join(v.replace('=', '-') for v in mvars) if mvars else ''}.log"
    # sim/Makefile only includes cocotb's makefile when a goal is literally `results.xml`, so its results
    # file cannot be relocated: run it in place (jobs touching sim/ must therefore be serial) and copy it.
    in_build = [] if area == "sim" else ["SIM_RESULTS_IN_BUILD=1"]
    cmd = ["make", "-C", str(AREA_DIR[area]), f"SIM={sim}", f"SIM_BUILD_ROOT={jroot}",
           *in_build, target, *mvars, *extra_make]
    if area == "sim":
        (AREA_DIR[area] / "results.xml").unlink(missing_ok=True)
    t0 = time.time()
    with log.open("w") as fh:
        fh.write("$ " + " ".join(cmd) + "\n")
        fh.flush()
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=ENV).returncode
    wall = time.time() - t0
    if area == "sim" and (AREA_DIR[area] / "results.xml").is_file():
        import shutil
        shutil.copy(AREA_DIR[area] / "results.xml", jroot / f"results__{target}.xml")
    return {"spec": spec, "cmd": cmd, "rc": rc, "wall_s": round(wall, 1), "log": str(log), "t0": t0}


def run_chain(sim: str, base: Path, logdir: Path, chain: str, extra_make: list[str]) -> dict:
    specs = chain.split("+")
    name = re.sub(r"[^A-Za-z0-9_.=-]+", "_", chain)
    jroot = base / name
    jroot.mkdir(parents=True, exist_ok=True)
    (jroot / "suites_ran.txt").touch()
    start = time.time()
    steps = [run_spec(sim, jroot, logdir, s, extra_make) for s in specs]
    results = []
    for xml in sorted(jroot.rglob("results__*.xml")):
        if xml.stat().st_mtime >= start - 1:
            results.append(parse_results(xml))
    tot = {k: sum(r[k] for r in results) for k in ("tests", "failures", "errors", "skipped")}
    ok = (all(s["rc"] == 0 for s in steps) and results
          and all(r["tests"] >= 1 and r["failures"] == 0 and r["errors"] == 0 for r in results))
    diag = {"errors": {}, "warnings": {}}
    for s in steps:
        d = diag_counts(Path(s["log"]), sim)
        for k in ("errors", "warnings"):
            for tag, n in d[k].items():
                diag[k][tag] = diag[k].get(tag, 0) + n
    return {"chain": chain, "sim": sim, "verdict": "PASS" if ok else "FAIL", "totals": tot,
            "results": results, "steps": [{k: v for k, v in s.items() if k != "cmd"} for s in steps],
            "wall_s": round(sum(s["wall_s"] for s in steps), 1), "diag": diag}


def checkpoint(path: Path | None, sim: str, res: dict) -> None:
    if path is None:
        return
    t = res["totals"]
    line = (f"- {dt.datetime.now().isoformat(timespec='seconds')} [{sim}] {res['chain']}: {res['verdict']} "
            f"tests={t['tests']} fail={t['failures']} err={t['errors']} skip={t['skipped']} "
            f"wall={res['wall_s']}s compile_diag_err={sum(res['diag']['errors'].values())} "
            f"warn_kinds={len(res['diag']['warnings'])}\n")
    with path.open("a") as fh:
        fh.write(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", required=True, choices=["vcs", "xcelium"])
    ap.add_argument("--root", type=Path, default=REPO / "sim_build_eda", help="build root (gitignored)")
    ap.add_argument("--logdir", type=Path, default=None)
    ap.add_argument("--jobs", type=int, default=2, help="concurrent chains (max 4: 15 GB host)")
    ap.add_argument("--state", type=Path, default=None, help="append one checkpoint line per finished chain")
    ap.add_argument("--json", type=Path, default=None, help="write the full per-chain results here")
    ap.add_argument("--make-arg", action="append", default=[], help="extra make argument for every job")
    ap.add_argument("jobs_spec", nargs="+", metavar="JOB")
    a = ap.parse_args()
    if a.jobs > 4:
        ap.error("--jobs > 4 would risk the 15 GB host")
    base = (a.root / a.sim).resolve()
    logdir = (a.logdir or (a.root / "logs" / a.sim)).resolve()
    base.mkdir(parents=True, exist_ok=True)
    logdir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    out = []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(run_chain, a.sim, base, logdir, j, a.make_arg): j for j in a.jobs_spec}
        for f in cf.as_completed(futs):
            r = f.result()
            out.append(r)
            checkpoint(a.state, a.sim, r)
            t = r["totals"]
            print(f"[{a.sim}] {r['verdict']:4} {r['chain']:55} tests={t['tests']} fail={t['failures']} "
                  f"err={t['errors']} skip={t['skipped']} wall={r['wall_s']}s", flush=True)
    wall = time.time() - t0
    out.sort(key=lambda r: a.jobs_spec.index(r["chain"]))
    if a.json:
        a.json.write_text(json.dumps({"sim": a.sim, "wall_s": round(wall, 1), "chains": out}, indent=1))
    bad = [r["chain"] for r in out if r["verdict"] != "PASS"]
    print(f"[{a.sim}] {len(out) - len(bad)}/{len(out)} chains PASS, total wall {wall:.0f}s"
          + (f"; FAIL: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
