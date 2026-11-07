#!/usr/bin/env python3
"""pg_labels.py <def> <out.tcl>: pick one met5 horizontal (else met4 vertical) stripe midpoint per PG net from the DEF SPECIALNETS (streamed) so the GDS-based
extraction can label the power nets (an ICC2 GDS carries no VPWR/VGND text; its DEF PG pins have no geometry)."""
import re, sys
want = {"VPWR": None, "VGND": None}   # net -> (x_um, y_um, layer)
cur = None; units = 1000
pat = re.compile(r"(met4|met5)\s+\d+\s+(?:\+\s+SHAPE\s+STRIPE\s+)?\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(\*|-?\d+)\s+(\*|-?\d+)\s*\)")
insp = False
with open(sys.argv[1]) as f:
    for line in f:
        m = re.match(r"^UNITS DISTANCE MICRONS (\d+)", line)
        if m: units = int(m.group(1))
        if line.startswith("SPECIALNETS"): insp = True; continue
        if line.startswith("END SPECIALNETS"): break
        if not insp: continue
        m = re.match(r"^\s*-\s+(\S+)(?:\s|$)", line)
        if m: cur = m.group(1) if m.group(1) in want else None; continue
        if cur:
            m = pat.search(line)
            if not m: continue
            if m.group(1) == "met5" and m.group(5) == "*" and m.group(4) != "*" and (want[cur] is None or want[cur][2] == "m4"):
                # horizontal met5 stripe ( x1 y ) ( x2 * ): longest-reaching top-level strap, preferred (spans the die)
                x1, y, x2 = int(m.group(2)), int(m.group(3)), int(m.group(4))
                want[cur] = ((x1 + x2) / 2 / units, y / units, "m5")
            elif m.group(1) == "met4" and m.group(4) == "*" and want[cur] is None:   # fallback: vertical met4 stripe ( x y ) ( * y2 )
                x, y, y2 = int(m.group(2)), int(m.group(3)), int(m.group(5))
                want[cur] = (x / units, (y + y2) / 2 / units, "m4")
with open(sys.argv[2], "w") as o:
    o.write("# pg labels (um): net x y on met4\nset ::pg_labels {}\n")
    for n, p in want.items():
        if p: o.write(f"lappend ::pg_labels {n} {p[0]:.3f} {p[1]:.3f} {p[2]}\n")
print(want)
