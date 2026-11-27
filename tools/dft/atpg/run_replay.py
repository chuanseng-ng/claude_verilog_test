#!/usr/bin/env python3
"""Run the replay binary for the good machine and for each injected fault, and tabulate verdicts (bead j41m.19).

usage: run_replay.py --vtb BUILD/obj/Vtb --vec VECDIR --faults faults.json --mode pat|flush --out result.json
                     [--tap 0|1] [--npat N] [--jobs 2] [--only-group g,...]

The tb prints one `RESULT mode=.. fault=.. so_mismatch=N po_mismatch=M ...` line (replay_tb.sv); a fault is DETECTED when the
number of scan-out mismatches plus primary-output mismatches is positive.  The good machine (fault=-1) must show 0.
faults.json is the list written by fault_sample.py (same order as the fsel inputs of the build).
"""
import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RES = re.compile(r"RESULT mode=(\S+) tap=(\d+) fault=(-?\d+) npat=(\d+) so_mismatch=(\d+) first_so_pat=(-?\d+) first_so_chains=0x([0-9a-f]+) "
                 r"po_mismatch=(\d+) first_po_pat=(-?\d+)")


def run_one(vtb, vec, mode, tap, fault, npat):
    cmd = [vtb, f"+dir={vec}", f"+mode={mode}", f"+tap={tap}", f"+fault={fault}"] + ([f"+npat={npat}"] if npat else [])
    p = subprocess.run(cmd, capture_output=True, text=True)
    m = RES.search(p.stdout)
    if not m:
        return {"fault": fault, "error": (p.stdout + p.stderr)[-400:], "rc": p.returncode}
    so, fs, ch, po, fp = int(m.group(5)), int(m.group(6)), int(m.group(7), 16), int(m.group(8)), int(m.group(9))
    return {"fault": fault, "so_mismatch": so, "first_so_pat": fs, "so_chain_mask": ch, "po_mismatch": po, "first_po_pat": fp,
            "detected": so + po > 0, "rc": p.returncode}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtb", required=True)
    ap.add_argument("--vec", required=True)
    ap.add_argument("--faults", required=True)
    ap.add_argument("--mode", default="pat")
    ap.add_argument("--tap", type=int, default=0)
    ap.add_argument("--npat", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--only-group")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    faults = json.loads(Path(a.faults).read_text())
    want = set(a.only_group.split(",")) if a.only_group else None
    ids = [-1] + [k for k, f in enumerate(faults) if want is None or f["group"] in want]
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(lambda k: run_one(a.vtb, a.vec, a.mode, a.tap, k, a.npat), ids))
    for r in res:
        if r["fault"] >= 0:
            r.update({x: faults[r["fault"]][x] for x in ("group", "pin", "value", "net")})
    by = {}
    for r in res:
        if r["fault"] >= 0 and "detected" in r:
            g = by.setdefault(r["group"], {"n": 0, "detected": 0})
            g["n"] += 1
            g["detected"] += int(r["detected"])
    summary = {"mode": a.mode, "tap": a.tap, "good": res[0], "groups": by, "errors": [r for r in res if "error" in r]}
    Path(a.out).write_text(json.dumps({"summary": summary, "runs": res}, indent=1))
    print(json.dumps(summary))
    return 0 if "error" not in res[0] and res[0].get("so_mismatch") == 0 and res[0].get("po_mismatch") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
