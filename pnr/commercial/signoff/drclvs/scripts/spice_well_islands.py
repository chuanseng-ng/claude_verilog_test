#!/usr/bin/env python3
"""spice_well_islands.py <extracted.spice> [def]: list every instance whose VPB/VNB/VPWR/VGND pin sits on a net other than VPWR (VPB,VPWR)
or VGND (VNB,VGND): well-tie / power islands in the extracted layout. Streams the SPICE."""
import sys, collections
ports = {}; bad = collections.defaultdict(list); n = 0
exp = {"VPWR": "VPWR", "VPB": "VPWR", "VGND": "VGND", "VNB": "VGND"}
buf = None; intop = False
def handle(t):
    global n
    if not t[0].startswith("X") or t[-1] not in ports: return
    n += 1
    for p, node in zip(ports[t[-1]], t[1:-1]):
        if p in exp and node != exp[p]: bad[node].append((t[0], t[-1], p))
with open(sys.argv[1], errors="replace") as f:
    for line in f:
        if line.startswith("+"):
            if buf is not None: buf += " " + line[1:].strip()
            continue
        if buf is not None:
            t = buf.split()
            if t and t[0].lower() == ".subckt": ports[t[1]] = t[2:]; intop = t[1] == "rv32i_cpu_top"
            elif intop: handle(t)
            buf = None
        if line.strip() and not line.startswith("*"): buf = line.strip()
print(f"instances checked: {n}; power-pin nodes not on VPWR/VGND: {len(bad)} nets, {sum(len(v) for v in bad.values())} pins")
for node, v in sorted(bad.items(), key=lambda kv: -len(kv[1]))[:40]:
    print(f"  net {node}: " + ", ".join(f"{a}({b.split('__')[-1]}).{c}" for a, b, c in v[:8]))
