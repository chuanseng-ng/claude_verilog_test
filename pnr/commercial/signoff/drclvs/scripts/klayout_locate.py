#!/usr/bin/env python3
"""klayout_locate.py <report.xml> <sram_boxes.txt> [grid_um]: per rule, how many KLayout DRC items lie inside an SRAM footprint, and for the
rest a coarse spatial histogram (streamed with iterparse; one item in memory at a time)."""
import sys, re, collections
import xml.etree.ElementTree as ET
boxes = [tuple(map(float, l.split()[1:5])) for l in open(sys.argv[2]) if l.strip()]
grid = float(sys.argv[3]) if len(sys.argv) > 3 else 100.0
num = re.compile(r"-?\d+\.?\d*(?:e-?\d+)?")
res = collections.defaultdict(lambda: [0, 0, collections.Counter(), [1e9, 1e9, -1e9, -1e9]])
samples = collections.defaultdict(list)
for ev, el in ET.iterparse(sys.argv[1], events=("end",)):
    if el.tag != "item": continue
    cat = (el.findtext("category") or "?").strip("'\"")
    vals = [v.text or "" for v in el.iter("value")]
    xs, ys = [], []
    for v in vals:
        n = [float(x) for x in num.findall(v)]
        xs += n[0::2]; ys += n[1::2]
    if xs:
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        inside = any(x0 >= b[0]-0.01 and y0 >= b[1]-0.01 and x1 <= b[2]+0.01 and y1 <= b[3]+0.01 for b in boxes)
        r = res[cat]
        if inside: r[0] += 1
        else:
            r[1] += 1; r[2][(int(x0 // grid) * int(grid), int(y0 // grid) * int(grid))] += 1
            r[3] = [min(r[3][0], x0), min(r[3][1], y0), max(r[3][2], x1), max(r[3][3], y1)]
            if len(samples[cat]) < 3: samples[cat].append((round(x0,3), round(y0,3), round(x1,3), round(y1,3)))
    el.clear()
print(f"{'rule':10s} {'in_sram':>8s} {'outside':>8s}  outside-extent(um)  top grid cells (x,y of {grid:.0f}um bin: n)")
for cat, (i, o, h, ext) in sorted(res.items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
    print(f"{cat:10s} {i:8d} {o:8d}  {[round(e) for e in ext] if o else '-'}  {h.most_common(5)}")
    for s in samples[cat]: print(f"             sample {s}")
