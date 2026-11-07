#!/usr/bin/env python3
"""mk_fp_def.py -- write a small floorplan DEF for DC-topo: die, rows, 503 pins (FIXED).
Sources (all committed):  pnr/sky130/cpu/config.json geometry (die 3600x1800, core 20..3580 x 20..1780),
pnr/sky130/cpu/macro_placement.cfg (macro xy/orientation), pnr/sky130/cpu/pin_template.def (pin rectangles).
usage: mk_fp_def.py <repo> <out.def>
"""
import re, sys
repo, out = sys.argv[1], sys.argv[2]
DBU = 1000
die = (0, 0, 3600 * DBU, 1800 * DBU)
core = (20 * DBU, 20 * DBU, 3580 * DBU, 1780 * DBU)
SITE_W, SITE_H = 460, 2720            # unithd, DBU
L = ["VERSION 5.8 ;", 'DIVIDERCHAR "/" ;', 'BUSBITCHARS "[]" ;', "DESIGN rv32i_cpu_top ;",
     f"UNITS DISTANCE MICRONS {DBU} ;", f"DIEAREA ( {die[0]} {die[1]} ) ( {die[2]} {die[3]} ) ;"]
# rows: same lattice the OpenROAD arm used (x0 = 20.24 = core x + half-site snap, y0 = 24.48)
x0, y0 = 20240, 24480
nsite = (core[2] - x0) // SITE_W
y, k = y0, 0
while y + SITE_H <= core[3]:
    L.append(f"ROW ROW_{k} unithd {x0} {y} {'FS' if k % 2 == 0 else 'N'} DO {nsite} BY 1 STEP {SITE_W} 0 ;")
    y += SITE_H; k += 1
# SRAM macros are NOT written here: DC names generate-block cells "gen_data_sram[i].u_data_sram", which a DEF cannot
# express reliably; dc_synth.tcl places them with set_cell_location straight from macro_placement.cfg.
pins = []
for ln in open(f"{repo}/pnr/sky130/cpu/pin_template.def"):
    m = re.match(r"- (\S+) \+ NET (\S+) \+ DIRECTION (\w+) \+ USE (\w+) \+ LAYER (\w+) \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", ln)
    if m: pins.append(m.groups())
L.append(f"PINS {len(pins)} ;")
for nm, net, d, use, lay, x1, y1, x2, y2 in pins:
    x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    L.append(f"- {nm} + NET {net} + DIRECTION {d} + USE {use} + LAYER {lay} ( {x1-cx} {y1-cy} ) ( {x2-cx} {y2-cy} ) + FIXED ( {cx} {cy} ) N ;")
L += ["END PINS", "END DESIGN"]
open(out, "w").write("\n".join(L) + "\n")
print(f"fp.def: {len(pins)} pins, {k} rows")
