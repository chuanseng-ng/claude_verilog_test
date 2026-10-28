#!/usr/bin/env python3
"""spice_pg_nets.py <extracted.spice>: stream the Magic-extracted SPICE; for every instance of a filler/tap/decap/diode cell,
count the node names seen on its power pins (VPWR/VGND/VPB/VNB). Exposes PG net fragmentation / mis-tie. Streams; low memory."""
import sys, re, collections
ports = {}; cnt = collections.defaultdict(collections.Counter)
cur = None; top = None
def handle(tokens):
    name = tokens[0]
    if not name.startswith("X"): return
    cell = tokens[-1]
    if cell not in ports: return
    nodes = tokens[1:-1]
    for p, n in zip(ports[cell], nodes):
        if p in ("VPWR", "VGND", "VPB", "VNB", "DIODE") and ("fill" in cell or "tap" in cell or "decap" in cell or "diode" in cell or p in ("VPWR","VGND")):
            cnt[(cell, p)][n] += 1
buf = None
with open(sys.argv[1], errors="replace") as f:
    inside_top = False
    for line in f:
        if line.startswith("+"):
            if buf is not None: buf += " " + line[1:].strip()
            continue
        if buf is not None:
            t = buf.split()
            if t and t[0].lower() == ".subckt":
                ports[t[1]] = t[2:]; inside_top = (t[1] == "rv32i_cpu_top")
            elif inside_top: handle(t)
            buf = None
        if line.strip() and not line.startswith("*"): buf = line.strip()
for (cell, p), c in sorted(cnt.items()):
    if "fill" in cell or "tap" in cell or "diode" in cell:
        top = c.most_common(6)
        print(f"{cell:36s} {p:5s} distinct_nodes={len(c):6d} total={sum(c.values()):7d} top={top}")
