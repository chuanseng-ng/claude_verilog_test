#!/usr/bin/env python3
"""List the instance names of every sky130_fd_sc_hd__mux4 cell whose A0..A3 inputs are
regfile storage words regs[0..3][b] (the first-level read-mux cells that select x1 among
x0..x3 for bit b, in every read tree). Used to build a broad negative-control fault
(inject_fault.py tie1 on all of them forces x1 reads to 0 in every read tree).

  find_x1_read_cells.py <netlist.nl.v>   -> space-separated cell names
"""
import re
import sys

t = open(sys.argv[1]).read()
names = []
for m in re.finditer(r"sky130_fd_sc_hd__mux4_\d+ (\S+)\s+\((.*?)\);", t, flags=re.S):
    body = m.group(2)
    a0 = re.search(r"\.A0\(\\u_core\.u_regfile\.regs\[0\]\[(\d+)\]\s*\)", body)
    a1 = re.search(r"\.A1\(\\u_core\.u_regfile\.regs\[1\]\[(\d+)\]\s*\)", body)
    if a0 and a1:
        names.append(m.group(1))
print(" ".join(names))
