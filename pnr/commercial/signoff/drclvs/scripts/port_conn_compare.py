#!/usr/bin/env python3
"""port_conn_compare.py <extracted.spice> <netlist.v> [top]: per top-level port, compare the multiset of (cell type, pin) attached to the
port net in the extracted layout vs the Verilog netlist. Direct localisation of opens/shorts at the 503 signal ports, independent of
Netgen's partition cascade. Streams the SPICE; parses the (8 MB) logical Verilog with a regex."""
import sys, re, collections
sp, vf = sys.argv[1], sys.argv[2]; top = sys.argv[3] if len(sys.argv) > 3 else "rv32i_cpu_top"
txt = open(vf, errors="replace").read()
ports = set()
for d, hi, lo, n in re.findall(r"^\s*(input|output|inout)\s+(?:\[(\d+):(\d+)\]\s+)?(\S+)\s*;", txt, re.M):
    if hi: ports.update(f"{n}[{i}]" for i in range(int(lo), int(hi) + 1))
    else: ports.add(n)
ports -= {"VPWR", "VGND"}
vmap = collections.defaultdict(collections.Counter)
for m in re.finditer(r"^(sky130_\w+)\s+(?:\\\S+|\S+)\s*\((.*?)\)\s*;", txt, re.M | re.S):
    cell, body = m.group(1), m.group(2)
    for pin, net in re.findall(r"\.(\w+)\s*\(\s*([^)]*?)\s*\)", body):
        net = net.strip()
        if net in ports: vmap[net][(cell, pin)] += 1
lmap = collections.defaultdict(collections.Counter); sub = {}; buf = None; intop = False
def handle(t):
    if not t[0].startswith("X") or t[-1] not in sub: return
    for p, n in zip(sub[t[-1]], t[1:-1]):
        n2 = n.replace("\\", "")
        if n2 in ports: lmap[n2][(t[-1], p)] += 1
with open(sp, errors="replace") as f:
    for line in f:
        if line.startswith("+"):
            if buf is not None: buf += " " + line[1:].strip()
            continue
        if buf is not None:
            t = buf.split()
            if t and t[0].lower() == ".subckt": sub[t[1]] = t[2:]; intop = t[1] == top
            elif intop: handle(t)
            buf = None
        if line.strip() and not line.startswith("*"): buf = line.strip()
bad = []
for p in sorted(ports):
    if lmap[p] != vmap[p]: bad.append(p)
print(f"signal ports {len(ports)}; ports whose attached (cell,pin) set differs layout vs netlist: {len(bad)}")
for p in bad[:40]:
    print(f"  {p}: layout={dict(lmap[p])} netlist={dict(vmap[p])}")
