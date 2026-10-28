#!/usr/bin/env python3
"""sram_boxes.py <def> [--lef-w 479.78 --lef-h 397.5]  -> prints "name x0 y0 x1 y1" (um) for each sky130_sram_* component.
Streams the DEF (110 MB) line by line. Orientation N/S/FN/FS keep the footprint; E/W/FE/FW swap w/h."""
import re, sys
w, h = 479.78, 397.5
args = sys.argv[1:]
path = args[0]
for i, a in enumerate(args):
    if a == "--lef-w": w = float(args[i + 1])
    if a == "--lef-h": h = float(args[i + 1])
units = 1000
comp = re.compile(r"^\s*-\s+(\S+)\s+(sky130_sram_\S+)\s+.*?\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\w+)")
n = 0
with open(path) as f:
    for line in f:
        m = re.match(r"^UNITS DISTANCE MICRONS (\d+)", line)
        if m: units = int(m.group(1))
        m = comp.match(line)
        if m:
            x, y, o = int(m.group(3)) / units, int(m.group(4)) / units, m.group(5)
            ww, hh = (h, w) if o in ("E", "W", "FE", "FW") else (w, h)
            print(f"{m.group(1)} {x:.3f} {y:.3f} {x+ww:.3f} {y+hh:.3f}"); n += 1
        if line.startswith("END COMPONENTS"): break
sys.stderr.write(f"{n} sram components\n")
