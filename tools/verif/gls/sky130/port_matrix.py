#!/usr/bin/env python3
"""31-register x 3-read-port matrix from the sweep runs (sweepA/B/C) of one arm.

Ports:  rs1  = ID read port 1 (ADDI D,xN,0 -> SW)         expected store at base+16N+0
        rs2  = ID read port 2 (ADD D,x0,xN -> SW, and SW xN direct)  stores at +4 and +8
        both = ADD D,xN,xN (both ports at once)           store at +12
        dbg  = APB debug read port, final register file vs by-construction expectation
A cell is PASS when every contributing run produced the expected (addr,data) store /
GPR value; MISSING when no run exercised it (a register is B or D in a run); FAIL otherwise.

  port_matrix.py <run_dir> <progdir>
"""
import json
import os
import re
import sys

run, progs = sys.argv[1], sys.argv[2]
MMIO = 0x20000100
res = {}  # (reg, port) -> list of bool
for name in ("sweepA", "sweepB", "sweepC"):
    ex = json.load(open(os.path.join(progs, name + ".expect.json")))
    got = {}
    apbr = {}
    for ln in open(os.path.join(run, name + ".log")):
        m = re.match(r"AXIW cyc=\d+ addr=(\w+) data=(\w+)", ln)
        if m:
            got.setdefault(m[1], m[2])
        m = re.match(r"APBR x(\d+)=(\w+)", ln)
        if m:
            apbr[int(m[1])] = m[2]
    expw = {a: d for a, d in ex["writes"]}
    for n in ex["tested"]:
        for off, port in ((0, "rs1"), (4, "rs2"), (8, "rs2"), (12, "both")):
            a = f"{MMIO + 16 * n + off:08x}"
            res.setdefault((n, port), []).append(got.get(a) == expw[a])
    for r in range(1, 32):
        res.setdefault((r, "dbg"), []).append(apbr.get(r) == ex["final_gpr"][str(r)])

def cell(r, p):
    v = res.get((r, p))
    return "MISSING" if not v else ("PASS" if all(v) else "FAIL")

print("reg  rs1      rs2      both     dbg")
bad = 0
tot = 0
for r in range(1, 32):
    row = [cell(r, p) for p in ("rs1", "rs2", "both", "dbg")]
    bad += row.count("FAIL")
    tot += sum(1 for c in row if c != "MISSING")
    print(f"x{r:<3d} " + " ".join(f"{c:8s}" for c in row))
print(f"cells exercised {tot}, FAIL {bad}")
