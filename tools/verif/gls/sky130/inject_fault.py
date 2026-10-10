#!/usr/bin/env python3
"""Negative-control fault injection for the dud4 differential.

Writes a COPY of the netlist with a deliberate fault in the named
sky130_fd_sc_hd__mux4 cells (the original is never modified):

  swap : exchange the S0/S1 select pins (index 1 <-> 2)
  tie1 : tie data input A1 to 1'b0   (index-1 data forced to 0 in that cell)

NOTE: 'swap' on a bit where registers 1 and 2 hold equal bit values is
invisible (x1=5, x2=7 share bit 0) -- an early attempt at a negative control
was therefore uninformative; use 'tie1' with programs whose x1 has a 1 there.

  inject_fault.py swap|tie1 <in.nl.v> <out.nl.v> <cell> [<cell> ...]
"""
import re
import sys

mode, src, dst, cells = sys.argv[1], sys.argv[2], sys.argv[3], set(sys.argv[4:])
text = open(src).read()
done = set()


def fault(m):
    name = m.group(2)
    if name not in cells:
        return m.group(0)
    body = m.group(3)
    if mode == "swap":
        s0 = re.search(r"\.S0\(([^)]*)\)", body)
        s1 = re.search(r"\.S1\(([^)]*)\)", body)
        assert s0 and s1, name
        body = body.replace(s0.group(0), "@@S0@@").replace(s1.group(0), "@@S1@@")
        body = body.replace("@@S0@@", f".S0({s1.group(1)})").replace("@@S1@@", f".S1({s0.group(1)})")
    elif mode == "tie1":
        a1 = re.search(r"\.A1\(([^)]*)\)", body)
        assert a1, name
        body = body.replace(a1.group(0), ".A1(1'b0)")
    else:
        raise SystemExit("mode must be swap|tie1")
    done.add(name)
    return f"{m.group(1)}{name} ({body});"


out = re.sub(r"(sky130_fd_sc_hd__mux4_\d+ )(\S+)\s+\((.*?)\);", fault, text, flags=re.S)
assert done == cells, f"cells not found: {cells - done}"
open(dst, "w").write(out)
print(f"{mode} fault on {sorted(done)} -> {dst}")
