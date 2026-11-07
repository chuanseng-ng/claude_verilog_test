#!/usr/bin/env python3
"""nwell_islands.py <def> [lef]  -- tool-neutral n-well connectivity check on a placed DEF (Step B5e).
A std cell's n-well fills the top (orientation N) or bottom (FS/S) half of its row, full cell width, so two rows that share a
cell-boundary line (N row below an FS row) share one well band.  Cells whose well rectangles touch within a band form one well
region; a region without a tapvpwrvgnd cell is a floating n-well island (VPB not tied to VPWR).  Also reports, per region,
the largest x-distance from any cell edge to the nearest tap in the same band (latch-up tap distance)."""
import re, sys, collections, os
d = sys.argv[1]
lef = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef')
w = {}
cur = None
for l in open(lef):
    m = re.match(r'MACRO (\S+)', l)
    if m: cur = m.group(1)
    m = re.match(r'\s*SIZE ([\d.]+) BY ([\d.]+)', l)
    if m and cur: w[cur] = float(m.group(1)); cur = None
units = 1000; y0 = None; ROWH = 2.72
bands = collections.defaultdict(list)   # band -> [(x0, x1, istap, name)]
nstd = 0
sec = None
rows = []
for l in open(d):
    if l.startswith('UNITS'): units = int(l.split()[3])
    if l.startswith('ROW ') and y0 is None: y0 = int(l.split()[4]) / units
    if l.startswith('COMPONENTS'): sec = 'C'; continue
    if l.startswith('END COMPONENTS'): break
    if sec != 'C' or not l.lstrip().startswith('- '): continue
    m = re.match(r'\s*- (\S+) (\S+) .*?\( (-?\d+) (-?\d+) \) (\S+)', l)
    if not m: continue
    nm, cell, x, y, o = m.group(1), m.group(2), int(m.group(3)) / units, int(m.group(4)) / units, m.group(5)
    if cell not in w: continue
    nstd += 1
    r = round((y - y0) / ROWH)
    band = r + 1 if o in ('N', 'FN') else r      # N: well on top, FS/S/FN: see below
    if o in ('FS', 'S'): band = r
    bands[band].append((x, x + w[cell], 'tapvpwrvgnd' in cell, nm, cell))
islands = []; tapgaps = []; nreg = 0
for b, lst in bands.items():
    lst.sort()
    reg = []
    for c in lst:
        if reg and c[0] <= reg[-1][1] + 0.005:
            reg[-1][1] = max(reg[-1][1], c[1]); reg[-1][2].append(c)
        else:
            reg.append([c[0], c[1], [c]])
    for x0, x1, cs in reg:
        nreg += 1
        taps = sorted(c[0] for c in cs if c[2])
        if not taps:
            islands.append((b, x0, x1, len(cs), [c[4].replace('sky130_fd_sc_hd__', '') for c in cs][:6]))
        else:
            gaps = [taps[0] - x0] + [taps[i + 1] - taps[i] for i in range(len(taps) - 1)] + [x1 - taps[-1]]
            tapgaps.append((max(gaps), b, x0, x1))
print(f"std cells {nstd}; well bands {len(bands)}; well regions {nreg}; floating islands (no tap) {len(islands)}")
for b, x0, x1, n, cs in sorted(islands, key=lambda t: (t[0], t[1])):
    print(f"  ISLAND band {b} y~{y0 + b * ROWH:.2f} x {x0:.2f}..{x1:.2f} ({x1 - x0:.2f} um) cells {n}: {' '.join(cs)}")
tapgaps.sort(reverse=True)
print("largest tap-to-tap/edge distance within a region (um), top 8:")
for g in tapgaps[:8]:
    print(f"  {g[0]:.2f} band {g[1]} x {g[2]:.2f}..{g[3]:.2f}")
