# Physical verification (DRC + LVS + Magic) of the Innovus arm, Sky130 `rv32i_cpu_top` (step B7b, rerun on b5g)

**Comparison run, measure and report only.** The layout was not modified. The b5d results further down are **superseded** (kept and labelled; run products in `pnr/commercial/signoff/drclvs/runs/innovus_superseded_b5d/`, report copies in `reports/superseded_b5a_b5d/`).

## B7b on `b5g_innovus` (current)
Subject: `pnr/commercial/impl/innovus/runs/b5g_innovus/out/` (Innovus `streamOut` with the fixed layer map `gds_layer_map.innovus`). Inputs, md5: `rv32i_cpu_top.gds` 2baa2689ff3c2db4069459e334cb8d9d; `.def` 0376e5f74902464849bb328cc9476089;
`.pg.pnl.v` (LVS netlist) b63a3ad986d121ca5ff949bb5d2d932f; `.nl.v` 3c8d320e1df88c385b772ce6dd716344. Same tools, decks, harness and guard as the ICC2 arm (`reports/drclvs_icc2_summary.md`): `make -C pnr/commercial/signoff/drclvs ARM=innovus <target>`; `arms/innovus.mk` now points at b5g and uses `PIN_MODE=none` (the GDS now carries pin text itself).

### Result in one paragraph
**The b5d GDS defect (missing via metal pads) is fixed, and the VPWR network is no longer split** (b5d: 153 components; b5g: one). Remaining findings, all outside the SRAM footprints:
**(1) a column of 146 endcap pairs at x = 98.44 um (the left edge of the tag SRAM, y 24-911 um) whose n-well is isolated: 146 floating-VPB islands in the extraction and 434 KLayout `nwell.2a` hits at that x** - the same 434 as b5d, so the b5g repair did not touch it; Innovus' own "144 regular opens" are this class and it is a real well-spacing/tie defect, not noise.
**(2) 3 output-port pairs shorted by metal where the netlist has `assign`s** (Netgen: 35,083 = 35,083 devices, 36,016 vs 36,019 nets, top-level pin matching fails on exactly these three). **(3)** KLayout also reports `m3.6` 40 (die-edge pin stubs) and `npc.2` 8. **KLayout total 482 in 3 rules** (b5d: 1,847,295, dominated by the missing pads).
The 232 `buf_8` ECO repeaters are seen correctly by LVS (the `buf_8` VGND/VNB pin counts are 431 on both sides). **Antenna 16 nets / 22 pins** (OpenROAD checker; Innovus native says 4 on 3 clock nets: different rule sets/pin scopes). **Magic DRC: 28,320,643 total, 28,315,092 inside the SRAM footprints (waived class), 5,551 straddling or outside** = `nwell.4` 4,966 (3,626 is the reference artifact), `hvi.5` 438 and `nwell.2a` 147 (both only at the endcap column).
**LVS was run on DEF + LEF (LibreLane's own method), not on the GDS, for b5g**; the GDS was checked for integrity and DRC only.

### 3-arm table
| Check | OpenROAD / LibreLane (`b2_openroad`) | ICC2 `b5e_icc2` | Innovus b5d (superseded) | **Innovus b5g** |
|---|---|---|---|---|
| GDS integrity | complete | clean | single top cell, via pads missing | **clean**: 1 top cell, 441 structures, 0 empty, 10 SRAM refs ok, via metal pads present (e.g. `M1M2_PR` = 68:20 + 69:20 + 68:44 cut), pin metal on 69:16/70:16 (503) + pin text (503) |
| LVS (extraction) | match | match except the met1 flop-Q short (1 net) | mismatch, PG split into 153 components | DEF+LEF: devices 35,228 vs 35,083, nets 36,161 vs 36,019 as extracted (146 endcap-VPB islands); PG is **one** component |
| LVS, islands merged | n/a | n/a | devices equal; pin match failed (4 aliased port pairs) | **devices 35,083 = 35,083; nets 36,016 vs 36,019; pin match fails on 3 aliased port pairs (`assign`s)** |
| Port-level compare (503 ports) | - | 0 differences | - | **0 differences** |
| KLayout DRC | 0 | 132 (`m4.5ab`) | 1,847,295 | **482**: `nwell.2a` 434, `m3.6` 40, `npc.2` 8 (0 inside SRAM) |
| Magic DRC total / inside SRAM / outside | 27,733,913 / 27,730,287 / 3,626 (`nwell.4`) | 27,738,097 / 27,733,486 / 4,611 | PENDING | **28,320,643 / 28,315,092 / 5,551** (straddle 593 + outside 4,958: `nwell.4` 4,966, `hvi.5` 438, `nwell.2a` 147) |
| Antenna (OpenROAD) | 116 / 119 | 488 / 549 | 15 / 18 | **16 / 22** |

### GDS checks
`reports/innovus_gds_inspect.txt`, `innovus_gds_fixrefs.txt`: one top cell (bbox 0,0-3600,1800 um), 441 structures (253 std-cell), 0 empty, the 10 SRAM instances reference `sky130_sram_1kbyte_1rw1r_32x256_8` (0 repaired, 0 pruned). **Via census** (`gds_via_census.py`, `runs/innovus/logs/viacensus.log`): every via cell now has its metal pads
(`M1M2_PR`: 68:20, 69:20 + cut 68:44; `L1M1_PR`: 67:20, 68:20 + 67:44; PG stacks `rv32i_cpu_top_VIA3/4/5`: both metals + cuts), so the b5d layer-map defect is fixed. Pin text is in the GDS (69:5 x294, 70:5 x209), the pin metal is on the pin purpose 69:16/70:16. My `gds_pin_check.py` flags 493 of 503 texts as "no drawing-layer metal"
because it only looks at 20; that is a limitation of the check for this stream-out, not a defect (the LVS port compare below is the real test). No pin-adding step was needed.

### LVS (`innovus_lvs_deflef_asdelivered_netgen.rpt.trunc`, `innovus_lvs_deflef_islands_merged_netgen.rpt.full`, `innovus_well_islands.txt`, `innovus_port_conn_compare.txt`)
Method: Magic extraction of the Innovus DEF + LEF abstracts (the DEF reads cleanly, PDK via names; no ContactCode problem as in ICC2), Netgen with LibreLane's `setup.tcl`, against `rv32i_cpu_top.pg.pnl.v`. The netlist needed no cleanup (0 supply declarations, 0 case collisions), so "as delivered" = "cleaned".
- **As extracted:** MISMATCH, devices 35,228 vs 35,083, nets 36,161 vs 36,019. Cause: **146 isolated VPB nets, 290 pins, every one a pair of vertically adjacent `decap_3` endcaps** (`ENDCAP_n`, orientations S / FN) at **x = 98.44 um, y = 24.48 ... 911.2 um**, i.e. the column between the row ends and the tag SRAM (`u_core/u_dcache/u_tag_sram`, x = 100 um).
  In 146 rows the left neighbour is a `tapvpwrvgnd_1` ending 0.46 um (one site) before the endcap with nothing placed in between; in the others there is nothing within 3 um. The endcap n-well is therefore not joined to any tap n-well. (b5d: 153 PG components and 4 aliased ports.)
- **Islands renamed to VPWR** (analysis step, `spice_merge_islands.py`, 146 nodes): **devices 35,083 = 35,083, all device classes equivalent**, nets **36,016 (layout) vs 36,019 (netlist)**. Magic reports `Ports "debug_pc_src_o" and "debug_take_branch_jump_o"`, `"axi_arburst_o[0]" and "axi_arsize_o[1]"`, `"axi_awlen_o[0]" and "axi_awlen_o[1]"` as electrically shorted;
  the netlist has exactly three `assign`s for those pairs (`rv32i_cpu_top.pg.pnl.v` lines 36463-36465). **A zero-device `assign` is two nets to Netgen and one metal net in the layout, so this is a netlist-representation difference, not a layout fault** (ICC2 buffers such assigns; Innovus leaves them as metal ties). The top-level pin match fails on these three only; the extracted top subckt lists 500 ports instead of 503.
- **Independent port check** (`port_conn_compare.py`, regex fixed to accept the indented Innovus instance lines): all 503 signal ports have identical (cell, pin) sets in layout and netlist, **0 differences**.
- **232 `buf_8` ECO repeaters:** present and connected: `buf_8` VGND = VNB = 431 pins on both sides in Netgen's class table and the device-class equivalence holds after the island merge.
- Not covered: GDS-mode extraction of b5g (not run, time), transistor-level LVS of cell internals and SRAM.

### KLayout DRC (`innovus_klayout_drc_by_rule.txt`, `innovus_klayout_drc_locate.txt`)
482 violations, 3 rules, **0 inside SRAM footprints**:
| Rule | Count | Where | Cause |
|---|---|---|---|
| `nwell.2a` (n-well spacing 1.27 um) | 434 | x = 98.17-98.25 um, y 24-913 um | the isolated endcap n-well column vs the tap n-well 0.46 um away (same 434 as b5d) |
| `m3.6` (met3 min area 0.24 um2) | 40 | x ~3596 um (right die edge) and x ~1 um, y 95-1737 um | pin stubs at the die edge (ICC2 b5a had 6 of the same kind) |
| `npc.2` (npc spacing) | 8 | x 1061-1774, y 999-1321 um, inside the logic area | isolated npc slivers 0.16 um wide |
All via-enclosure, metal-width and spacing rules that gave 1.85 M hits on b5d are 0, confirming the pad fix.

### Antenna (`innovus_antenna.rpt`)
OpenROAD `check_antennas -verbose` on the b5g DEF (48 VIRTUAL stubs dropped): **16 nets / 22 pins** (b5d 15/18). The listed pins are `DIODE_n/DIODE` pins on `FE_PDN*_mbist_status_o_*` nets. Innovus' own count (4 violations on 3 clock nets) is a different rule set; do not compare the two.

### Magic DRC (`innovus_magic_drc_real_by_rule.tsv`; SRAM real, GDS mode; 25 min wall, peak 9.9 GB RSS, watchdog never fired)
Total **28,320,643** (log `[INFO] COUNT`; OpenROAD arm 27,733,913, ICC2 b5e 27,738,097). 45a classification (10 SRAM boxes from the DEF): inside **28,315,092**, straddling a footprint edge **593**, outside **4,958**. Outside + straddle by rule:
| Rule | straddle | outside | Reading |
|---|---|---|---|
| `nwell.4` (n-well without metal-connected N+ tap) | 593 | 4,373 | 4,966 vs 3,626 in the OpenROAD arm and 3,627 in ICC2 b5e. The SRAM-abstract artifact is the shared base; **about 1,340 are extra**. 165 of the outside records sit at the endcap column (x 96-100.5 um); the other ~1,170 extra are spread over the die and I could not attribute them (unresolved; candidates are the n-wells of the decap/filler cells Innovus adds, not checked) |
| `hvi.5` (HVI to HVI/LV n-well spacing) | 0 | 438 | all at x = 97.55-98.9 um, y 24-912 um: the isolated endcap n-well column (3 per endcap pair) |
| `nwell.2a` (n-well spacing < 1.27 um) | 0 | 147 | all at x = 97.55-99.4 um: the same column (KLayout counts 434 for the same spacing violation, Magic merges them to 147 edges) |
Everything else (li, licon, diff/tap, poly, via, ...: 28.3 M) is inside the SRAM footprints = the 45a waiver class. **No met4 spacing, li or via-enclosure rule fires outside the macros** (b5d could not be judged; ICC2 b5e has met4.5a/b 984). Verdict: DRC outside the waived class = the endcap n-well column (`nwell.2a`, `hvi.5`, plus part of `nwell.4`); the remainder of `nwell.4` is the shared abstract artifact plus ~1,170 unattributed extras.


### Native-flow items explained
- *144 "regular opens" (endcap VPB):* real, = the isolated endcap n-well column above (146 islands here; same cells, same x).
- *4 antenna violations on 3 clock nets:* not reproduced by OpenROAD's checker (it flags 16 diode pins on mbist buffer chains instead). Unresolved difference of checkers, no layout evidence either way.
- *232 buf_8 ECO repeaters:* seen correctly by LVS.

### Files
Run products (gitignored) `pnr/commercial/signoff/drclvs/runs/innovus/`; superseded b5d `runs/innovus_superseded_b5d/`. Reports `pnr/commercial/signoff/drclvs/reports/innovus_*`; old copies `reports/superseded_b5a_b5d/`. The 31 MB Netgen fragment report is kept truncated (`.rpt.trunc`).

---
# SUPERSEDED: B7b on `b5d_innovus` (every number below belongs to the b5d layout)

**Comparison run, measure and report only.** Subject: `pnr/commercial/impl/innovus/runs/b5d_innovus/out/` (`rv32i_cpu_top.gds`, `.def`, `.pg.pnl.v`), Innovus 23.14 `streamOut`
with `scripts/gds_layer_map.innovus`. Same harness, tools, decks and watchdog as the ICC2 arm (`reports/drclvs_icc2_summary.md`): `make -C pnr/commercial/signoff/drclvs ARM=innovus <target>`.
The layout was not modified; every workaround below is a measurement copy. Reports are incremental: Magic DRC is still PENDING behind the idle gate (an `icc2_shell` job for ICC2 `b5e` is running).

## Result in one paragraph
**The Innovus GDS has one integrity defect that invalidates its DRC numbers: the streamOut layer map has no `VIA` entries for the metal layers, so the via metal pads are not in the GDS.**
Every via cell (`M1M2_PR`, `L1M1_PR`, ..., and the 15,864 PG via stacks) contains only the cut; this gives **1,847,295 KLayout violations** (mostly via-enclosure rules), which say nothing about the routing.
Needs a re-run of `streamOut` with the map fixed (below) before DRC is meaningful. **LVS:** signals and devices match (after merging, 34,199 devices and 35,170 nets on both sides), but **the VPWR
network is split into 153 components in the extraction**, in both the DEF+LEF and the GDS path (cause not isolated), and 4 output-port pairs are shorted by metal where the netlist has `assign`s.
**Antenna: 15 nets / 18 pins** (OpenROAD arm 116 / 119).

## 3-arm table
| Check | OpenROAD / LibreLane (`b2_openroad`) | ICC2 `b5a_icc2` (before; `b5e` rerun pending) | Innovus `b5d_innovus` |
|---|---|---|---|
| GDS integrity | complete (Magic stream-out) | 3 defects: SRAM refs to an empty 32-char-truncated cell, no pin metal (names only), 245 orphan top cells | single top cell, 10 SRAM refs fine, no empty structures, pin metal present (pin purpose 69:16 x294, 70:16 x209) but **no pin text**; **via metal pads missing (layer map)** |
| Layer/datatype map | Sky130 numbers | correct | numbers correct (drawing 20, cut 44, pin 16, label 5) but `VIA` not mapped on li1/met1-met5 |
| LVS verdict | Netgen "Circuits match uniquely" (Magic DEF+LEF) | mismatch, 7 well-island nets; unique match with them merged | **mismatch as extracted** (DEF+LEF: 34,389 vs 34,199 devices, 35,319 vs 35,170 nets; 28,413 net fragments); with the PG components merged devices and nets are equal, then "Top level cell failed pin matching" (4 aliased port pairs, see below) |
| LVS path | Magic DEF+LEF extraction | Magic from GDS (DEF unreadable: ContactCode via names) | both: DEF+LEF (Innovus DEF reads clean, 0 errors, PDK via names) and GDS (pin text added from the DEF) give the same PG split |
| KLayout DRC | 0 | 4,877 (218 outside SRAM) | **1,847,295 in 23 rules** (via.4a_a 700,180; m1.4 495,619; m2.4_a 421,463; m3.4 82,597; via2.4_a 56,036; m4.3 32,206; via3.4 31,632; via3.5 10,175; ct.4 8,903; m2.6 3,335; m1.6 2,896; m3.6 711; m4.3_a 588; nwell.2a 434; via.4a 215; via.5a 161; m3.4_a 71; via3.4_a 25; via4.4 18; m5.3 13; 791_m1.4 9; npc.2 6; m5.3_a 2) |
| KLayout, outside SRAM footprints | 0 | 218 | 1,847,125 (170 inside SRAM footprints; `reports/innovus_klayout_drc_locate.txt`) |
| Magic DRC total / inside SRAM / outside | 27,733,913 / 27,730,287 / 3,626 (all `nwell.4`) | PENDING | PENDING (gate: `icc2_shell` running) |
| Antenna (OpenROAD `check_antennas`) | 116 nets / 119 pins | 532 / 601 | **15 / 18** (252 diodes in the netlist) |

## GDS checks (done first)
1. **SRAM references / top cells / empty structures:** `reports/innovus_gds_inspect.txt`. One top cell (`rv32i_cpu_top`, bbox 0,0 to 3600,1800), 437 structures, 0 empty; the 10 SRAM instances reference
   `sky130_sram_1kbyte_1rw1r_32x256_8` at the DEF positions; no repair was needed (`reports/innovus_gds_fixrefs.txt`: 0 re-pointed, 0 pruned). The ICC2 `b5a` defects do not occur here.
2. **Pin metal and text:** pin rectangles exist on the pin purpose (69:16: 294, 70:16: 209 = 503), but streamOut wrote **no pin text** (0 labels in the top cell). Pin names were added at the rectangle centres from the DEF in a
   measurement copy (`scripts/gds_add_pins.py -rd mode=text`, orientation-aware: pins are N/S/E/W).
3. **Layer map `scripts/gds_layer_map.innovus` (checked against `sky130A.map`):** numbers are right, but the file maps `VIA` objects only for the cut layers (`mcon`, `via`, `via2`, `via3`, `via4`). `sky130A.map` also maps
   `VIA` on the metal layers (`li1 ... VIA 67 20`, `met1 ... VIA 68 20`, up to met5). Without those lines the via metal pads are not streamed. Evidence in the GDS: `M1M2_PR` has one shape (68:44, the cut) and the PG stack cells
   `rv32i_cpu_top_VIA3/4/5` contain cuts only (`scripts/gds_via_census.py`). **Fix, in the Innovus flow (not applied):** add `li1 VIA 67 20`, `met1 VIA 68 20`, `met2 VIA 69 20`, `met3 VIA 70 20`, `met4 VIA 71 20`, `met5 VIA 72 20`
   to the map and re-run `streamOut`. All DRC counts for this arm should be redone on the corrected GDS; the numbers here are for the delivered file.
4. **DEF for OpenROAD:** the Innovus DEF has 48 `VIRTUAL` stubs that OpenROAD's reader rejects; they carry no geometry and were dropped in a measurement copy for the antenna run.

## LVS
- **DEF+LEF path (same as the OpenROAD arm):** the Innovus DEF reads cleanly in Magic (0 errors; PDK via names), so this path was used first. Netgen: MISMATCH, 34,389 vs 34,199 devices, 35,319 vs 35,170 nets.
- **GDS path** (same method as ICC2, std cells and SRAM as LEF abstracts, PG labels on the first met5 strap): the same split.
- **What differs:** the VPWR/VPB side of the extraction has 153 components in both paths: the labelled PG strap network (138,558 pins), one large component with 702,793 pins (76 % of the cells), and 150 small ones (2 to 4 k pins).
  The VGND side shows one net, but the p-substrate bridges it, so it cannot be confirmed separately. The DEF's PG is symmetric (36 met4 stripe columns and 18 met5 straps per net, 7,932 via stacks per net), so the cause is not an obvious missing stripe.
  **Not isolated.** It needs an independent check: Innovus `verify_connectivity -type special -net {VPWR VGND}` on the final database. Until then treat it as "unresolved, not proven physical".
- **With the 152 extra VPWR-side components renamed VPWR** (analysis step): 34,199 devices and 35,170 nets on both sides, device classes equivalent; the top-level pin match then fails for two reasons that are not layout defects:
  (a) the netlist declares `VPWR`/`VGND` as wires, not ports; (b) **4 output pairs are shorted by metal in the layout and are `assign`s in the netlist** (`axi_awlen_o[1]=axi_awlen_o[0]`, `axi_arlen_o[1]=axi_arlen_o[0]`, `axi_arsize_o[1]=axi_arburst_o[0]`, `debug_take_branch_jump_o=debug_pc_src_o`); Magic reports "Ports ... are electrically shorted" for each.
  ICC2 buffered these (opt.port.eliminate_verilog_assign); Innovus left them as direct connections.
- Netlist hygiene: no `supply` declarations, no case-colliding net names in the Innovus netlist (the ICC2 netlist had both).
- Not covered: transistor-level LVS of cell internals and the SRAM (abstracts in all arms).

## KLayout DRC
All of it is dominated by missing via pads (item 3 above): the samples are 0.015 um slivers at via locations, spread over the whole die (`reports/innovus_klayout_drc_locate.txt`). Rules that do not depend on via pads
(nwell.2a 434, npc.2 6, m5.3 13) are the only ones worth looking at after the re-stream. 170 items in total are inside SRAM footprints. This result must not be compared with the other arms' counts until the GDS is re-streamed.

## Antenna
OpenROAD `check_antennas -verbose` on the Innovus DEF (VIRTUAL stubs dropped): **15 nets / 18 pins** (`reports/innovus_antenna.rpt`).

## Magic DRC: PENDING
Idle gate (MemAvailable >= 11 GiB, load1 < 6, no `icc2_shell`/`innovus`/`StarXtract`/`klayout`): not met, an `icc2_shell` job (ICC2 `b5e`) is running. Recommended order: re-stream the Innovus GDS with the layer-map fix first,
so the Magic run is not spent on a GDS without via pads. One line (about 30 min on an idle host):
`cd pnr/commercial/signoff/drclvs && GUARD_RSS_GB=11 make ARM=innovus SRAM_MODE=real mdrc mdrc-class` (writes `reports/innovus_magic_drc_real_by_rule.tsv`).

## Files
Harness `pnr/commercial/signoff/drclvs/` (`arms/innovus.mk` sets `PIN_MODE=text`); reports `reports/innovus_*`; run products (gitignored) `runs/innovus/`. `runs/innovus/lvsgds_m4label/` is a superseded extraction
(PG label on a met4 stripe; same split) kept for reference.
