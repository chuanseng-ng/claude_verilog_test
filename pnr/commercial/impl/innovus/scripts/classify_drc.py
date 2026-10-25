#!/usr/bin/env python3
"""classify_drc.py <verify_drc report> -- break Innovus verify_drc markers down by type, layer and location relative to the 10 SRAM footprints."""
import re, sys, collections
xs = [100.0, 679.78, 1359.56, 2039.34, 2719.12]; W, H = 479.78, 397.5
macros = [(x, y, x + W, y + H) for y in (20.0, 520.0) for x in xs]
def where(cx, cy):
    for i, (a, b, c, d) in enumerate(macros):
        if a <= cx <= c and b <= cy <= d:
            return "inside SRAM footprint"
    for (a, b, c, d) in macros:
        if a - 10 <= cx <= c + 10 and b - 10 <= cy <= d + 10:
            return "within 10um of SRAM edge"
    if 417.5 <= cy <= 520: return "I/D-cache channel (y 417.5-520)"
    return "open core"
cnt = collections.Counter(); bytype = collections.Counter(); bylayer = collections.Counter(); loc_by_type = collections.Counter()
txt = open(sys.argv[1]).read()
for m in re.finditer(r"^(\w+): \( ([^)]*) \)(.*?)\(\s*(\w+)\s*\)\s*\nBounds : \( ([\d.]+), ([\d.]+) \) \( ([\d.]+), ([\d.]+) \)", txt, re.M):
    typ, sub, _, lay, x1, y1, x2, y2 = m.groups()
    cx, cy = (float(x1) + float(x2)) / 2, (float(y1) + float(y2)) / 2
    k = f"{typ} {sub.strip()}"
    w = where(cx, cy)
    bytype[k] += 1; bylayer[lay] += 1; loc_by_type[(k, w)] += 1; cnt[w] += 1
tot = sum(bytype.values())
print("total markers parsed:", tot)
print("\nby type:");  [print(f"  {v:6d}  {k}") for k, v in bytype.most_common()]
print("\nby layer:"); [print(f"  {v:6d}  {k}") for k, v in bylayer.most_common()]
print("\nby location:"); [print(f"  {v:6d}  {k}  ({100*v/tot:.1f} %)") for k, v in cnt.most_common()]
print("\ntype x location:"); [print(f"  {v:6d}  {k[0]} @ {k[1]}") for k, v in loc_by_type.most_common(14)]
