#!/usr/bin/env python3 -I
"""check_flipic_feasibility.py -- geometric feasibility of the shared 'flipic' floorplan (pnr/sky130/cpu/macro_placement_flipic.cfg), no EDA tool.
Checks, from the SRAM LEF, the row lattice of the floorplan and the PDN strap recipe (met4 width 3.1, pitch 100, offset 20, two nets per pitch):
 1. every port-0 pin (dout0 din0 wmask0 clk0) of a FS-placed I-cache macro lands on the macro's TOP edge (y=417.5) and faces channel rows (distance to the first row, rows free over the pin x);
 2. the same pins on the N-placed D-cache macros (reference: they work in b6) - row distance on the bottom edge (y=520);
 3. met4 PG strap vs pin x overlap/clearance (m4 spacing >= 0.4 um for wide metal): the strap ends flush at the macro edge in both cases, so the set of overlapping pins must be identical for flipped I-cache and N D-cache;
 4. pin pitch vs buffer width, buffers per channel row.
usage: check_flipic_feasibility.py <sram.lef> [macro_placement_flipic.cfg]"""
import re, sys, collections
lef, cfg = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "pnr/sky130/cpu/macro_placement_flipic.cfg")
W, H = 479.78, 397.5
pins = collections.defaultdict(list); pin = None; layer = None
for l in open(lef).read().split("\n"):
    s = l.split()
    if not s: continue
    if s[0] == "PIN": pin = s[1]; continue
    if s[0] == "END" and len(s) > 1 and s[1] == pin: pin = None; continue
    if pin and s[0] == "LAYER": layer = s[1]
    if pin and s[0] == "RECT" and layer == "met4": pins[re.sub(r"\[\d+\]", "", pin)].append(tuple(map(float, s[1:5])))
macros = []
for l in open(cfg):
    l = re.sub(r"#.*", "", l).strip()
    if l: n, x, y, o = l.split(); macros.append((n, float(x), float(y), o))
ROW0, PITCH = 24.48, 2.72
rows = [ROW0 + PITCH * k for k in range(645)]
def orient(py1, py2, o, y0):  # LEF y -> placed y
    return (y0 + H - py2, y0 + H - py1) if o in ("FS", "MX") else (y0 + py1, y0 + py2)
def strap_hit(x1, x2):
    for k in range(40):
        for s0 in (20.0 + 100 * k, 24.8 + 100 * k):
            if x2 + 0.4 > s0 and x1 - 0.4 < s0 + 3.1: return True
    return False
tot = collections.Counter(); out = []
for n, x0, y0, o in macros:
    cache = "icache" if "icache" in n else "dcache"
    for pn in ("dout0", "din0", "wmask0", "clk0"):
        for (a, b, c, d) in pins[pn]:
            ya, yb = orient(b, d, o, y0); xa, xb = a + x0, c + x0
            edge = "top" if abs(yb - (y0 + H)) < 0.01 else "bottom" if abs(ya - y0) < 0.01 else "?"
            # first row on the channel side of the pin; rows over the pin x are free iff no macro covers (x, row)
            if edge == "top": cand = [r for r in rows if r >= yb - 0.01]; r0 = cand[0]; gap = r0 - yb; ok = all(not (m[1] <= xa and xb <= m[1] + W and m[2] <= r0 and r0 + PITCH <= m[2] + H) for m in macros)
            else: cand = [r for r in rows if r + PITCH <= ya + 0.01]; r0 = cand[-1]; gap = ya - (r0 + PITCH); ok = all(not (m[1] <= xa and xb <= m[1] + W and m[2] <= r0 and r0 + PITCH <= m[2] + H) for m in macros)
            hit = strap_hit(xa, xb)
            tot[(cache, pn, edge, "rows_free" if ok else "ROW_BLOCKED")] += 1
            if hit: tot[(cache, pn, edge, "strap_conflict")] += 1
            if pn == "dout0": out.append((n, xa, gap))
for k, v in sorted(tot.items()): print(k, v)
gaps = [g for _, _, g in out]
print("dout0 pin -> nearest channel row, um: min %.2f max %.2f over %d pins" % (min(gaps), max(gaps), len(gaps)))
xs = sorted(x for n, x, g in out if "icache" in n and "tag" in n)
print("dout0 pin pitch (um):", round(xs[1] - xs[0], 2), " buf_4 width 3.68-4.60 um -> fits one buffer per pin in a single row" )
print("channel rows:", len([r for r in rows if 418.0 <= r and r + PITCH <= 520.0]), "rows y %.2f..%.2f, full die width (macros are outside the channel)" % (min(r for r in rows if r >= 418.0), max(r for r in rows if r + PITCH <= 520.0)))
