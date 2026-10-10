#!/usr/bin/env python3
"""First cycle at which two per-cycle boundary traces (tb +trace=) differ, and the differing
fields at that cycle and the next few, using decode_trace.py's field layout.

  first_divergence.py <ref.trc> <dut.trc> [n_lines=4]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sky130"))
from decode_trace import dec  # noqa: E402

ref, dut = sys.argv[1], sys.argv[2]
nshow = int(sys.argv[3]) if len(sys.argv) > 3 else 4
shown = 0
with open(ref) as fa, open(dut) as fb:
    for la, lb in zip(fa, fb):
        if la == lb and shown == 0:
            continue
        c, x = dec(la)
        _, y = dec(lb)
        diff = {k: (hex(x[k]), hex(y[k])) for k in x if x[k] != y[k]}
        print(f"cyc {c}: ref cpc={x['cpc']:08x} cinsn={x['cinsn']:08x} cvalid={x['cvalid']}  DIFF(ref,dut)={diff}")
        shown += 1
        if shown >= nshow:
            break
    else:
        if shown == 0:
            print("traces identical")
