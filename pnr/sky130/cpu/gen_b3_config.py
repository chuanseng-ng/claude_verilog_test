#!/usr/bin/env python3
"""Generate config_b3.json (OpenROAD generation B3) from config.json.

B3 = the B2 flow (Classic, no scan, config.json of 915cc013) with ONE bundle of changes (user task 2026-11-15, step 9):
  1. flipped I-cache floorplan (macro_placement_flipic.cfg)                              [section 7 item 6]
  2. SRAM dout0 max-cap buffers: one buf_2/buf_4 on the driver of every dout0 pin that violated max-cap in the B2 judge
     at any of the 9 corners (266 pins; buf_4 when the B2 nom_tt load was >= 0.05 pF, as in ICC2 b7), placed next to the pin
  3. antenna: GRT_ANTENNA_ITERS 5 -> 20, GRT_ANTENNA_MARGIN 20 -> 50 (the knobs that cut the SoC deck-antenna count, bead 58q)
  4. RUN_MAGIC_DRC false: no full-layout Magic DRC in the flow (host hangs); Magic DRC is the window method, step C.
  DRT_THREADS 8 -> 2 (host rule: <= 2 threads).  Scan insertion keys removed (B2 predates them).
Usage: gen_b3_config.py <dout0_union.txt> <nom_tt_loads.tsv>   (see the step-9 run_state for how they were made)
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEF = Path.home() / "pdk/sky130A/libs.ref/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef"
cfg = json.load(open(HERE / "config.json"))
for k in ("// SCAN_NOTE", "CVT_SCAN_CLOCKS", "CVT_SCAN_MAX_LENGTH", "CVT_SCAN_EN_NET"):
    cfg.pop(k, None)
cfg["meta"] = {"version": 2, "flow": "CVTClassicB3"}
cfg["MACRO_PLACEMENT_CFG"] = "dir::macro_placement_flipic.cfg"
cfg["GRT_ANTENNA_ITERS"] = 20
cfg["GRT_ANTENNA_MARGIN"] = 50
cfg["DRT_THREADS"] = 2
cfg["RUN_MAGIC_DRC"] = False

lef = LEF.read_text()
size = re.search(r"SIZE ([\d.]+) BY ([\d.]+) ;", lef)
W, H = float(size.group(1)), float(size.group(2))
pins = {}
for m in re.finditer(r"PIN (dout0\[(\d+)\]).*?END \1", lef, re.S):
    r = re.search(r"RECT\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", m.group(0))
    x0, y0, x1, y1 = map(float, r.groups())
    pins[int(m.group(2))] = ((x0 + x1) / 2, (y0 + y1) / 2)
place = {}
for l in open(HERE / "macro_placement_flipic.cfg"):
    if l.startswith("#") or not l.strip():
        continue
    n, x, y, o = l.split()
    place[n] = (float(x), float(y), o)

loads = {}
for l in open(sys.argv[2]):
    p, c = l.split()
    loads[p] = float(c)
bufs = []
for l in open(sys.argv[1]):
    p = l.strip()
    if not p:
        continue
    inst, pin = p.split("/")
    idx = int(re.search(r"\[(\d+)\]$", pin).group(1))
    x0, y0, o = place[inst]
    px, py = pins[idx]
    ax = x0 + px
    if o == "N":
        ay = y0 + py
        by = ay - 8.0            # D-cache: pins on the bottom edge (y=520) facing the channel above; buffer just inside it
    else:  # FS, mirrored about X
        ay = y0 + (H - py)
        by = ay + 2.0            # I-cache: pins on the top edge (y=417.5); first channel row starts at y=418.88
    buf = "sky130_fd_sc_hd__buf_4" if loads.get(p, 0.0) >= 0.05 else "sky130_fd_sc_hd__buf_2"
    bufs.append({"target": f"{inst}/{pin}", "buffer": buf, "placement": [round(ax - 0.5, 3), round(by, 3)]})
cfg["INSERT_ECO_BUFFERS"] = bufs
cfg["// B3_NOTE"] = ("OpenROAD generation B3 (step 9, 2026-11-15): flip + dout0 driver buffers + antenna knobs; see gen_b3_config.py. "
                    "Generated file: regenerate with that script.")
json.dump(cfg, open(HERE / "config_b3.json", "w"), indent=4)
print(len(bufs), "buffers;", sum(b["buffer"].endswith("buf_4") for b in bufs), "buf_4")
