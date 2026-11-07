#!/usr/bin/env python3
"""spice_merge_islands.py <in.spice> <out.spice>: MEASUREMENT COPY. Finds power-pin nodes that are not VPWR/VGND (VPB/VNB/VPWR/VGND
pins of instances in the top cell) and renames those nodes to the net they should be on (VPB,VPWR -> VPWR; VNB,VGND -> VGND).
Used only to learn what ELSE differs once the well-tie islands are removed from the comparison. Two passes, streaming."""
import sys, re
inp, outp = sys.argv[1], sys.argv[2]
exp = {"VPWR": "VPWR", "VPB": "VPWR", "VGND": "VGND", "VNB": "VGND"}
ports = {}; ren = {}
def logical(f):
    buf = None
    for line in f:
        if line.startswith("+"):
            if buf is not None: buf[0] += " " + line[1:].strip(); buf[1].append(line)
            continue
        if buf is not None: yield buf
        buf = [line.strip(), [line]] if (line.strip() and not line.startswith("*")) else None
        if buf is None: yield None
    if buf is not None: yield buf
intop = False
with open(inp, errors="replace") as f:
    for b in logical(f):
        if not b: continue
        t = b[0].split()
        if t[0].lower() == ".subckt": ports[t[1]] = t[2:]; intop = t[1] == "rv32i_cpu_top"
        elif intop and t[0].startswith("X") and t[-1] in ports:
            for p, node in zip(ports[t[-1]], t[1:-1]):
                if p in exp and node != exp[p]: ren[node] = exp[p]
print(f"renaming {len(ren)} nodes: {ren}")
pat = re.compile("|".join(re.escape(k) for k in sorted(ren, key=len, reverse=True))) if ren else None
with open(inp, errors="replace") as f, open(outp, "w") as o:
    for line in f:
        if pat and (line.startswith("X") or line.startswith("+")):
            toks = line.split(" ")
            line = " ".join(ren.get(x.rstrip("\n"), x.rstrip("\n")) + ("\n" if x.endswith("\n") else "") for x in toks)
        o.write(line)
