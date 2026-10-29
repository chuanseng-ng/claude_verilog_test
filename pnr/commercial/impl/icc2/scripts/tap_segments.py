#!/usr/bin/env python3
"""tap_segments.py <def> [max_gap_um=26] -- row-segment tap coverage check on a DEF that has endcaps + taps (Step B5e, run right after tap insertion).
A row segment is the stretch between two consecutive boundary cells (endcaps, which ICC2 puts at both row ends and next to every macro cut) of one row.
Reports segments with NO tap and the largest tap-free stretch (segment edge to tap, tap to tap) per segment; flags > max_gap.  Exit 0 always (report)."""
import re, sys, collections
d = sys.argv[1]; maxgap = float(sys.argv[2]) if len(sys.argv) > 2 else 26.0
W = {'decap_3': 1.38, 'tapvpwrvgnd_1': 0.46}
units = 1000; y0 = None
ends = collections.defaultdict(list); taps = collections.defaultdict(list)
sec = None
for l in open(d):
    if l.startswith('UNITS'): units = int(l.split()[3])
    if l.startswith('ROW ') and y0 is None: y0 = int(l.split()[4]) / units
    if l.startswith('COMPONENTS'): sec = 1; continue
    if l.startswith('END COMPONENTS'): break
    if not sec or not l.lstrip().startswith('- '): continue
    m = re.match(r'\s*- (\S+) (\S+) .*?\( (-?\d+) (-?\d+) \) (\S+)', l)
    if not m: continue
    nm, cell, x, y = m.group(1), m.group(2), int(m.group(3)) / units, int(m.group(4)) / units
    r = round((y - y0) / 2.72)
    if cell.endswith('decap_3') and nm.startswith('boundarycell'): ends[r].append(x)
    elif cell.endswith('tapvpwrvgnd_1'): taps[r].append(x)
nseg = 0; notap = []; worst = []
for r in sorted(ends):
    e = sorted(ends[r]); t = sorted(taps[r])
    # endcaps come in (right-end of segment k, left-end of segment k+1) pairs: first is a left endcap, then alternate right/left
    # robust form: segment = [e[i].x1 .. e[i+1].x0] for i = 0,2,4,... when endcaps come paired left/right
    segs = [(e[i] + W['decap_3'], e[i + 1]) for i in range(0, len(e) - 1, 2)]
    for a, b in segs:
        nseg += 1
        ts = [x for x in t if a <= x <= b]
        pts = [a] + ts + [b]
        g = max(pts[i + 1] - pts[i] for i in range(len(pts) - 1))
        if not ts: notap.append((r, a, b))
        worst.append((g, r, a, b, len(ts)))
worst.sort(reverse=True)
print(f"rows {len(ends)}; row segments {nseg}; segments with NO tap: {len(notap)}; segments with a tap-free stretch > {maxgap} um: {sum(1 for w in worst if w[0] > maxgap)}")
for r, a, b in notap[:20]: print(f"  NO TAP row {r} x {a:.2f}..{b:.2f} ({b - a:.2f} um)")
print("worst tap-free stretches:")
for g, r, a, b, n in worst[:8]: print(f"  {g:.2f} um row {r} segment {a:.2f}..{b:.2f} taps {n}")
