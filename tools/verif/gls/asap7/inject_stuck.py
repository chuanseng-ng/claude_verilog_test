#!/usr/bin/env python3
"""Negative-control fault injection for the ASAP7 ma7 differential.

Writes a COPY of a flat ASAP7 netlist in which the named net is stuck at a constant on every
sink pin (its driver is left alone). Only nets that survive synthesis with a name can be targeted
(in the synthesis netlists that is e.g. `\\u_core.mem_wb_reg[N]`; regfile storage is anonymous).

  inject_stuck.py <in.v> <out.v> <net> <0|1> [<net> <0|1> ...]
  net is the escaped name without the leading backslash, e.g.  u_core.mem_wb_reg[150]
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
pairs = list(zip(sys.argv[3::2], sys.argv[4::2]))
text = open(src).read()
for net, val in pairs:
    # sink pins are any pin that is not an output pin of the cell library (Y, QN, GCLK, H, L, CON, SN)
    pat = re.compile(r"\.(?!(?:Y|QN|GCLK|H|L|CON|SN|dout0)\()([A-Za-z0-9_]+)\(\\" + re.escape(net) + r" ?\)")
    text, n = pat.subn(lambda m: f".{m.group(1)}(1'b{val})", text)
    if n == 0:
        raise SystemExit(f"net not found as a sink: {net}")
    print(f"stuck-at-{val} on {net}: {n} sink pin(s)")
open(dst, "w").write(text)
