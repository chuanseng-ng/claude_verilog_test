#!/usr/bin/env python3
"""Seeded fault sample for the scan replay (bead j41m.19).

usage: fault_sample.py --cut-dir CUT5 --status B3/status.txt --status-sub status_first_N.txt --out faults.json
                       [--seed 244] [--n-detected 50] [--n-untestable 20] [--n-scd 24] [--n-sce 16]

Groups (fault index k of a Quaigh --fault-report = site k//2, stuck-at k%2, as in cellpin_report.py):
  detected     status D in the report for the replayed pattern subset (--status-sub), pin not SCD/SCE: Quaigh claims the subset
               detects them; the replay must too.
  untestable   status U in the full report (SAT-proven untestable in the cut), pin not SCD/SCE: negative control, must NOT be seen.
  scd, sce     SCD / SCE pin faults: the chain-integrity (flush) test is what has to detect them.
Output: JSON list of {net, value, k, group, pin}, `net` being the site net that pin_inject.site_pins maps to an instance pin.
"""
import argparse
import json
import random
from pathlib import Path


def codes(path, n):
    st = [""] * n
    for ln in Path(path).read_text().split("\n"):
        if ln.strip():
            k, s = ln.split()
            st[int(k)] = s
    return st


def pin_of(site):
    return site.rsplit(".cvtpin_", 1)[1] if ".cvtpin_" in site else "<output>"


def draw(ids, n, rng):
    ids = sorted(ids)
    return sorted(rng.sample(ids, min(n, len(ids))))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut-dir", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--status-sub", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=244)
    ap.add_argument("--n-detected", type=int, default=50)
    ap.add_argument("--n-untestable", type=int, default=20)
    ap.add_argument("--n-scd", type=int, default=24)
    ap.add_argument("--n-sce", type=int, default=16)
    a = ap.parse_args(argv)
    sites = (Path(a.cut_dir) / "cut_sites.txt").read_text().split()
    n = 2 * len(sites)
    full, sub = codes(a.status, n), codes(a.status_sub, n)
    rng = random.Random(a.seed)
    pin = [pin_of(s) for s in sites]
    inpin = lambda k: pin[k // 2] not in ("SCD", "SCE", "<output>")  # noqa: E731  input pins: injectable as a branch fault
    det = [k for k in range(n) if sub[k] == "D" and full[k] == "D" and inpin(k)]
    unt = [k for k in range(n) if full[k] == "U" and inpin(k)]
    scd = [k for k in range(n) if pin[k // 2] == "SCD"]
    sce = [k for k in range(n) if pin[k // 2] == "SCE"]
    groups = [("detected", draw(det, a.n_detected, rng)), ("untestable", draw(unt, a.n_untestable, rng)),
              ("scd", draw(scd, a.n_scd, rng)), ("sce", draw(sce, a.n_sce, rng))]
    out = []
    for g, ks in groups:
        for k in ks:
            out.append({"net": sites[k // 2], "value": k % 2, "k": k, "group": g, "pin": pin[k // 2], "full_status": full[k],
                        "sub_status": sub[k]})
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({g: len(ks) for g, ks in groups}), "pool sizes", {"detected": len(det), "untestable": len(unt),
                                                                       "scd": len(scd), "sce": len(sce)})


if __name__ == "__main__":
    main()
