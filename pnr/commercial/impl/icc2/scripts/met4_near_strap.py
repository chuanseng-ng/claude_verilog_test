#!/usr/bin/env python3
"""met4_near_strap.py DEF [margin_um=0.4] -- nets whose met4 signal wire / via3-via4 pad is closer than <margin> to a wide (>3 um) met4 PG stripe.
Sky130 m4.5ab (KLayout/Magic met4.5a/b): spacing 0.4 um between a >=3 um wide met4 and any other met4 (parallel run > 0).
Prints one net per line plus 'x y' of the offending segment on stderr summary.  Used by B5i 05i_met4_eco.tcl (net list) and to cross-check KLayout."""
import re, sys
defn = sys.argv[1]; margin = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
U = 1000.0
straps = []   # (x1,y1,x2,y2) in um
sig = []      # (net, x1,y1,x2,y2)
mode = None; net = None
pt = re.compile(r'\(\s*(\*|-?\d+)\s+(\*|-?\d+)(?:\s+\d+)?\s*\)')
PAD = 0.165  # half of the 0.33 um met4 via pad (via3_cc/via4_cc as measured in the GDS)
with open(defn) as f:
    for line in f:
        if line.startswith('SPECIALNETS'): mode = 'S'; continue
        if line.startswith('END SPECIALNETS'): mode = None; continue
        if line.startswith('NETS'): mode = 'N'; continue
        if line.startswith('END NETS'): mode = None; continue
        if mode is None: continue
        if mode == 'N' and re.match(r'^\s*-\s+\S', line):
            net = line.split()[1]
        if 'met4' not in line and 'via3' not in line and 'via4' not in line and not (mode == 'N' and line.lstrip().startswith('NEW')): 
            continue
        m = re.search(r'(?:ROUTED|NEW)\s+(\S+)(?:\s+(\d+))?\s+(?:\+ SHAPE \w+\s+)?(\(.*)', line)
        if not m: continue
        layer, w, rest = m.group(1), m.group(2), m.group(3)
        pts = pt.findall(rest)
        if not pts: continue
        if mode == 'S':
            if layer == 'met4' and w and int(w) >= 3000:
                (x1, y1), (x2, y2) = pts[0], pts[1]
                x1 = int(x1); y1 = int(y1); x2 = x1 if x2 == '*' else int(x2); y2 = y1 if y2 == '*' else int(y2)
                hw = int(w) / 2.0
                straps.append(((x1 - hw) / U, min(y1, y2) / U, (x2 + hw) / U, max(y1, y2) / U))
            continue
        if layer == 'met4':
            hw = (int(w) if w else 300) / 2000.0
            # a NEW segment: first point absolute, second may have *
            xs = []
            cur = None
            for a, b in pts:
                pass
            (x1, y1) = pts[0]
            if len(pts) > 1:
                x2, y2 = pts[1]
            else:
                x2, y2 = '*', '*'
            x1 = int(x1) / U; y1 = int(y1) / U
            x2 = x1 if x2 == '*' else int(x2) / U; y2 = y1 if y2 == '*' else int(y2) / U
            sig.append((net, min(x1, x2) - hw, min(y1, y2) - hw, max(x1, x2) + hw, max(y1, y2) + hw))
        # via pads: "NEW met3 ( x y ) via3_cc"  (via3 joins met3/met4) ; "NEW met4 ( x y ) via4_cc" (pad on met4)
        if re.search(r'\bvia[34]_\w+', rest) or re.search(r'\bvia[34]\b', rest):
            x, y = pts[0]; x = int(x) / U; y = int(y) / U
            sig.append((net, x - PAD, y - PAD, x + PAD, y + PAD))
bad = {}
for (n, a, b, c, d) in sig:
    for (sx1, sy1, sx2, sy2) in straps:
        if d < sy1 or b > sy2: continue
        gap = max(sx1 - c, a - sx2)       # horizontal gap between boxes (>0 : separated)
        if gap <= 0: continue
        if gap < margin - 1e-6 and min(d, sy2) - max(b, sy1) > 0:
            bad.setdefault(n, []).append((round(gap, 3), round(a, 2), round(b, 2)))
for n in sorted(bad): print(n)
print("# straps=%d sig_met4_items=%d offending_nets=%d offending_items=%d" % (len(straps), len(sig), len(bad), sum(len(v) for v in bad.values())), file=sys.stderr)
for n in sorted(bad)[:8]: print("#", n, bad[n][:3], file=sys.stderr)
