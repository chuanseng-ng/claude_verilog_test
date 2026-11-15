#!/usr/bin/env python3 -I
"""mk_windows.py -- window plan for the OpenROAD std-cell-GDS Magic run by the WINDOW method (step 9 C).  Writes windows.tsv: name x0 y0 x1 y1 (core box, um).
Coverage = every part of the die that is NOT SRAM interior: left/right pockets, the I$/D$ channel, the gaps between the SRAMs, the standard-cell logic zone.
Each core box is clipped with an 8 um margin (items touching the clip boundary are excluded from the count, so the margin keeps the core measured).
Die 3600 x 1800; I$ row y 20..417.5, D$ row y 520..917.5, SRAM x 100/679.78/1359.56/2039.34/2719.12 + 479.78 wide (macro_placement_flipic.cfg)."""
import sys
sx = [100.0, 679.78, 1359.56, 2039.34, 2719.12]; W = 479.78
rows = [("I", 20.0, 417.5), ("D", 520.0, 917.5)]
w = []
w.append(("TINY", 1250, 1100, 1350, 1200))                    # first run: 100 x 100 um of logic, to prove container start + Magic stable
w.append(("PL", 0, 0, 100, 920)); w.append(("PR", sx[4] + W, 0, 3600, 920))
for r, y0, y1 in rows:
    for i in range(4):
        w.append((f"G{r}{i}", sx[i] + W, y0, sx[i + 1], y1))
for i in range(5):
    w.append((f"CH{i}", 720 * i, 417.5, 720 * (i + 1), 520))
nx, ny = 8, 3
for j in range(ny):
    for i in range(nx):
        w.append((f"L{j}{i}", 3600 / nx * i, 917.5 + (1800 - 917.5) / ny * j, 3600 / nx * (i + 1), 917.5 + (1800 - 917.5) / ny * (j + 1)))
w.append(("BOT", 0, 0, 3600, 20)); w.append(("MID", 0, 917.5, 3600, 920))  # thin strips (bottom row below the SRAM, SRAM-row seam)
with open(sys.argv[1], "w") as f:
    for n, a, b, c, d in w:
        f.write(f"{n}\t{a:.3f}\t{b:.3f}\t{c:.3f}\t{d:.3f}\n")
print(len(w), "windows")
