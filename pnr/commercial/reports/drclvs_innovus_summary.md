# Physical verification (DRC + LVS) of the Innovus arm GDS, Sky130 `rv32i_cpu_top` (step B7b), with the 3-arm table

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
