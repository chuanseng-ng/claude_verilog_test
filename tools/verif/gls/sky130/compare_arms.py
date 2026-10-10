#!/usr/bin/env python3
"""Compare the runs of two arms of the dud4 differential, and (optionally) a run
against the generator's by-construction expectation.

  compare_arms.py diff   <ref_run_dir> <dut_run_dir>      -> exit 1 on any divergence
  compare_arms.py expect <run_dir> <progdir>              -> exit 1 on any mismatch

`diff` compares, per program:
  * COMMIT stream functionally (pc, insn) and cycle-exactly (cyc, pc, insn)
  * AXI write stream (addr, data, strb, len) functionally and cycle-exactly
  * the 32 debug-port GPR reads (APBR x0..x31)
  * the per-cycle boundary trace (every macro output port, every cycle): the
    first differing cycle is reported
"""
import json
import os
import re
import sys


def parse_log(path):
    commits, writes, apbr = [], [], {}
    done = None
    with open(path) as f:
        for ln in f:
            m = re.match(r"COMMIT cyc=(\d+) pc=(\w+) insn=(\w+) trap=(\d)", ln)
            if m:
                commits.append((int(m[1]), m[2], m[3], m[4]))
                continue
            m = re.match(r"AXIW cyc=(\d+) addr=(\w+) data=(\w+) strb=(\w) len=(\d+)", ln)
            if m:
                writes.append((int(m[1]), m[2], m[3], m[4], m[5]))
                continue
            m = re.match(r"APBR x(\d+)=(\w+)", ln)
            if m:
                apbr[int(m[1])] = m[2]
                continue
            if ln.startswith(("DONE", "TIMEOUT")):
                done = ln.strip()
    return commits, writes, apbr, done


def first_trace_diff(a, b):
    with open(a) as fa, open(b) as fb:
        n = 0
        for la, lb in zip(fa, fb):
            n += 1
            if la != lb:
                return n, la.split()[0], la.strip(), lb.strip()
        ra, rb = fa.readline(), fb.readline()
        if ra or rb:
            return n + 1, "len", ra.strip(), rb.strip()
    return None


def cmd_diff(ref, dut):
    bad = 0
    for fn in sorted(os.listdir(ref)):
        if not fn.endswith(".log"):
            continue
        name = fn[:-4]
        if not os.path.exists(os.path.join(dut, fn)):
            print(f"{name}: MISSING in dut run")
            bad += 1
            continue
        rc, rw, rp, rd = parse_log(os.path.join(ref, fn))
        dc, dw, dp, dd = parse_log(os.path.join(dut, fn))
        res = []
        res.append(("commit(pc,insn)", [c[1:3] for c in rc] == [c[1:3] for c in dc]))
        res.append(("commit(cycle-exact)", rc == dc))
        res.append(("axi-write(addr,data,strb,len)", [w[1:] for w in rw] == [w[1:] for w in dw]))
        res.append(("axi-write(cycle-exact)", rw == dw))
        res.append(("debug-GPR x0..x31", rp == dp and len(rp) == 32))
        t = first_trace_diff(os.path.join(ref, name + ".trc"), os.path.join(dut, name + ".trc"))
        res.append(("per-cycle boundary trace", t is None))
        ok = all(r for _, r in res) and rd == dd and rd is not None and rd.startswith("DONE")
        bad += 0 if ok else 1
        print(f"{name}: {'IDENTICAL' if ok else 'DIVERGES'}  "
              f"({len(rc)} commits, {len(rw)} axi writes, {len(rp)} gpr reads; ref={rd} dut={dd})")
        for k, r in res:
            if not r:
                print(f"    FAIL {k}")
        if t is not None:
            print(f"    first trace divergence: line {t[0]} cyc {t[1]}")
        if rp != dp:
            for r in range(32):
                if rp.get(r) != dp.get(r):
                    print(f"    GPR x{r}: ref={rp.get(r)} dut={dp.get(r)}")
        if [c[1:3] for c in rc] != [c[1:3] for c in dc]:
            for i, (a, b) in enumerate(zip(rc, dc)):
                if a[1:3] != b[1:3]:
                    print(f"    first commit divergence #{i}: ref pc={a[1]} insn={a[2]} | dut pc={b[1]} insn={b[2]}")
                    break
        if [w[1:] for w in rw] != [w[1:] for w in dw]:
            for i, (a, b) in enumerate(zip(rw, dw)):
                if a[1:] != b[1:]:
                    print(f"    first AXI write divergence #{i}: ref addr={a[1]} data={a[2]} | dut addr={b[1]} data={b[2]}")
                    break
    return 1 if bad else 0


def cmd_expect(run, progs):
    bad = 0
    for fn in sorted(os.listdir(run)):
        if not fn.endswith(".log"):
            continue
        name = fn[:-4]
        ex = os.path.join(progs, name + ".expect.json")
        if not os.path.exists(ex):
            continue
        e = json.load(open(ex))
        _, w, p, _ = parse_log(os.path.join(run, fn))
        ew = [(a, d) for a, d in e["writes"]]
        gw = [(x[1], x[2]) for x in w]
        wok = ew == gw
        pok = all(p.get(int(r)) == v for r, v in e["final_gpr"].items())
        bad += 0 if (wok and pok) else 1
        print(f"{name}: stores {'OK' if wok else 'MISMATCH'} ({len(gw)}/{len(ew)}), "
              f"final GPRs {'OK' if pok else 'MISMATCH'}")
        if not wok:
            for i, (a, b) in enumerate(zip(ew, gw)):
                if a != b:
                    print(f"    first store mismatch #{i}: expect {a} got {b}")
                    break
        if not pok:
            for r, v in e["final_gpr"].items():
                if p.get(int(r)) != v:
                    print(f"    x{r}: expect {v} got {p.get(int(r))}")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "diff":
        sys.exit(cmd_diff(sys.argv[2], sys.argv[3]))
    if len(sys.argv) == 4 and sys.argv[1] == "expect":
        sys.exit(cmd_expect(sys.argv[2], sys.argv[3]))
    print(__doc__)
    sys.exit(2)
