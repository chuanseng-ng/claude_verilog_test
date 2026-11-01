#!/usr/bin/env python3
"""nwell_islands_innovus.py <def> [lef ...] [--cells-out FILE] -- find n-well islands (connected components of std-cell n-wells) that contain no tapvpwrvgnd_1.
Model (from the sky130_fd_sc_hd .mag views, 1 mag unit = 0.005 um): a std cell's n-well spans x -0.19 .. W+0.19 and, for N/FN rows, y +1.305 .. +2.91 above the row
origin (S/FS rows: -0.19 .. +1.415 from the row origin y, i.e. the well grows down from the shared VPWR rail).  Two wells are one island when the rectangles overlap
(touching or abutting cells: they overlap by 0.38 um; a one-site (0.46 um) gap leaves a 0.08 um slit = nwell.2a).  tap_* cells are the only N+ ties.
A hard-macro (SRAM) is NOT part of any std-cell island.  Output: summary + list of untied islands (bbox, cell kinds, number of cells); with --cells-out the instance names."""
import re, sys, collections
args = sys.argv[1:]; cells_out = None
if '--cells-out' in args:
    i = args.index('--cells-out'); cells_out = args[i + 1]; del args[i:i + 2]
d = args[0]
lefs = args[1:] or ['/home/RD/ryan/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef']
W = {}; H = {}
for lf in lefs:
    cur = None
    for l in open(lf):
        m = re.match(r'\s*MACRO (\S+)', l)
        if m: cur = m.group(1)
        m = re.match(r'\s*SIZE ([\d.]+) BY ([\d.]+)', l)
        if m and cur: W[cur] = float(m.group(1)); H[cur] = float(m.group(2))
units = 1000; insts = []; sec = 0
for l in open(d):
    if l.startswith('UNITS'): units = int(l.split()[3])
    if l.startswith('COMPONENTS'): sec = 1; continue
    if l.startswith('END COMPONENTS'): break
    if not sec: continue
    m = re.match(r'\s*- (\S+) (\S+) .*?\( (-?\d+) (-?\d+) \) (\S+)', l)
    if not m: continue
    n, c, x, y, o = m.groups()
    if not c.startswith('sky130_fd_sc_hd__') or c not in W: continue
    insts.append((n, c, int(x), int(y), o))
# nwell rect per instance (dbu): x0 -190.. x1 +190 ; y: top for N/FN, bottom for S/FS
rects = []
for n, c, x, y, o in insts:
    w = int(round(W[c] * units))
    if o in ('N', 'FN'): ya, yb = y + 1305, y + 2910
    else: ya, yb = y - 190, y + 1415
    rects.append((x - 190, ya, x + w + 190, yb))
N = len(insts); par = list(range(N))
def f(a):
    while par[a] != a: par[a] = par[par[a]]; a = par[a]
    return a
# union overlapping rects: bucket by row-strip (ya), then sweep in x; then link strips that overlap in y between adjacent rows
by_strip = collections.defaultdict(list)
for i, r in enumerate(rects): by_strip[r[1]].append(i)
for ya, ids in by_strip.items():
    ids.sort(key=lambda i: rects[i][0]); cur = ids[0]; cx1 = rects[cur][2]
    for i in ids[1:]:
        if rects[i][0] < cx1:   # strictly overlapping (touching edge-to-edge is no merge)
            par[f(i)] = f(cur); cx1 = max(cx1, rects[i][2])
        else: cur = i; cx1 = rects[i][2]
# link strips: a bottom-strip (S rows) with the top-strip of the row below (N rows) -- they overlap in y when ya_bottom < yb_top
tops = {ya: ids for ya, ids in by_strip.items() if rects[ids[0]][3] - ya == 1605 and insts[ids[0]][4] in ('N', 'FN')}
bots = {ya: ids for ya, ids in by_strip.items() if insts[ids[0]][4] in ('S', 'FS')}
topy = sorted(tops)
import bisect
for ya, ids in bots.items():
    # top strip of the N row just below: its yb overlaps [ya, ya+1605]
    cand = [t for t in topy if t < ya and t + 1605 > ya]
    for t in cand:
        A = sorted(tops[t], key=lambda i: rects[i][0]); B = sorted(ids, key=lambda i: rects[i][0])
        j = 0
        for a in A:
            ra = rects[a]
            while j < len(B) and rects[B[j]][2] <= ra[0]: j += 1
            k = j
            while k < len(B) and rects[B[k]][0] < ra[2]:
                par[f(a)] = f(B[k]); k += 1
comp = collections.defaultdict(list)
for i in range(N): comp[f(i)].append(i)
untied = []
for r, ids in comp.items():
    if not any(insts[i][1].endswith('tapvpwrvgnd_1') for i in ids): untied.append(ids)
print(f"std cells {N}; n-well islands {len(comp)}; islands with NO tap: {len(untied)}")
kinds = collections.Counter()
for ids in untied:
    k = tuple(sorted(set(insts[i][1].replace('sky130_fd_sc_hd__', '') for i in ids))); kinds[k] += 1
for k, v in kinds.most_common(): print(f"  {v:5d} islands of cells {k}")
untied.sort(key=lambda ids: (min(insts[i][3] for i in ids), min(insts[i][2] for i in ids)))
for ids in untied[:12] + (['...'] if len(untied) > 12 else []):
    if ids == '...': print('  ...'); continue
    xs = [insts[i][2] for i in ids]; ys = [insts[i][3] for i in ids]
    print("  island: %d cells x %.2f..%.2f y %.2f..%.2f  %s" % (len(ids), min(xs) / units, max(xs) / units, min(ys) / units, max(ys) / units, ' '.join(sorted(insts[i][0] for i in ids))[:90]))
if cells_out:
    with open(cells_out, 'w') as fh:
        for ids in untied:
            fh.write(' '.join('%s,%s,%d,%d,%s' % insts[i] for i in ids) + '\n')
# tap distance: for every island, largest distance from a non-physical std cell to the nearest tap in the island (information)
