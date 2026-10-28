#!/usr/bin/env python3
"""def_pg_summary.py <def>: summarise PG stripes (met4/met5, 3.1 um) per special net from the DEF (streamed): count, distinct x/y, extents."""
import sys, re, collections
net = None; st = collections.defaultdict(list); insp = False
for l in open(sys.argv[1], errors="replace"):
    if l.startswith("SPECIALNETS"): insp = True; continue
    if l.startswith("END SPECIALNETS"): break
    if not insp: continue
    m = re.match(r"^\s*-\s+(\S+)", l)
    if m: net = m.group(1); continue
    m = re.search(r"(met[45])\s+3100\s+(?:\+\s+SHAPE\s+STRIPE\s+)?\(\s*(\d+)\s+(\d+)\s*\)\s+\(\s*(\*|\d+)\s+(\*|\d+)", l)
    if m and net: st[(net, m.group(1))].append((int(m.group(2)) / 1000, int(m.group(3)) / 1000, m.group(4), m.group(5)))
for k, v in sorted(st.items()):
    if k[1] == "met4":
        xs = sorted(set(round(a[0]) for a in v)); ys = [a[1] for a in v]; y2 = [int(a[3]) / 1000 for a in v if a[3] != "*"]
        print(k, len(v), "vertical segments; x", xs[0], "..", xs[-1], "distinct x", len(xs), "y-start min/max", min(ys), max(ys), "y-end min/max", min(y2), max(y2))
    else:
        ys = sorted(set(round(a[1]) for a in v)); print(k, len(v), "horizontal straps; distinct y", len(ys), "y", ys[0], "..", ys[-1])
