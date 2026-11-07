#!/usr/bin/env python3
"""gen_ploc.py <def> <out.ploc> [inset_um]  -- RedHawk pad (ideal voltage source) list for a macro that has no pad ring.

Assumption (identical for every arm): the macro is fed from its edges.  One ideal source on each end of every top-layer
(met5) horizontal PG stripe of VPWR and VGND, `inset` um inside the stripe end.  No package/bondwire R-L.
Reads the PG SPECIALNETS of a DEF (VPWR/VGND only; the SRAM vccd1/vssd1 pins are on the same nets in all three DEFs)."""
import re, sys
defp, outp = sys.argv[1], sys.argv[2]
inset = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
unit = 1000.0
cur = None; insn = False; segs = {}
pt = re.compile(r"\(\s*(\*|-?\d+)\s+(\*|-?\d+)\s*(?:\d+\s*)?\)")
with open(defp) as f:
    for line in f:
        if line.startswith("SPECIALNETS"): insn = True; continue
        if line.startswith("END SPECIALNETS"): break
        if not insn: continue
        m = re.match(r"^\s*-\s+(\S+)", line)
        if m: cur = m.group(1); continue
        if cur not in ("VPWR", "VGND"): continue
        m = re.search(r"(?:ROUTED|NEW)\s+met5\s+(\d+)\b(.*)", line)
        if not m: continue
        w = int(m.group(1)); pts = pt.findall(m.group(2))
        if len(pts) < 2 or "STRIPE" not in line: continue
        (x1, y1), (x2, y2) = pts[0], pts[1]
        x1 = int(x1); y1 = int(y1)
        x2 = x1 if x2 == "*" else int(x2); y2 = y1 if y2 == "*" else int(y2)
        segs.setdefault(cur, []).append((x1, y1, x2, y2, w))
out = []
for net, tag in (("VPWR", "vdd"), ("VGND", "vss")):
    for i, (x1, y1, x2, y2, w) in enumerate(sorted(segs.get(net, []), key=lambda s: (s[1], s[0]))):
        if y1 != y2: raise SystemExit("non-horizontal met5 stripe %s" % ((x1, y1, x2, y2),))
        xa, xb = min(x1, x2) / unit + inset, max(x1, x2) / unit - inset
        out.append("pad_%s_%d_L %.3f %.3f met5 %s" % (tag, i, xa, y1 / unit, net))
        out.append("pad_%s_%d_R %.3f %.3f met5 %s" % (tag, i, xb, y1 / unit, net))
open(outp, "w").write("\n".join(out) + "\n")
print("%s: VPWR stripes %d, VGND stripes %d, pads %d" % (defp.split('/')[-4], len(segs.get("VPWR", [])), len(segs.get("VGND", [])), len(out)))
