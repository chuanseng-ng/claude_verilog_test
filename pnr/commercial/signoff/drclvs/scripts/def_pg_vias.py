#!/usr/bin/env python3
"""def_pg_vias.py <def>: via usage per special net (VPWR/VGND) from the SPECIALNETS section (streamed)."""
import sys, re, collections
c = collections.Counter(); net = None; insp = False
for l in open(sys.argv[1], errors="replace"):
    if l.startswith("SPECIALNETS"): insp = True; continue
    if l.startswith("END SPECIALNETS"): break
    if not insp: continue
    m = re.match(r"^\s*-\s+(\S+)", l)
    if m: net = m.group(1)
    for v in re.findall(r"\)\s+([A-Za-z0-9_]+PR[A-Za-z0-9_]*|[A-Za-z0-9_]*via[0-9]*_cc[A-Za-z0-9_]*)", l): c[(net, v)] += 1
for k, v in sorted(c.items()): print(k, v)
