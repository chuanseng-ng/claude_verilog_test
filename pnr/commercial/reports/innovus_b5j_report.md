# Innovus b5j: in-place fix of the untied endcap n-well column (b5h + 146 `tapvpwrvgnd_1`)

Tag `runs/b5j_innovus` (gitignored). Started from a verified byte-identical copy (`diff -rq`) of b5h's final pre-fill routed db `05_route`; b5h and b5g untouched. capTable rc_nom, `update_io_latency false` and clk_io 3.295 ns are unchanged (the exported SDC differs from b5h's only in comment headers).

## 1. Root cause (measured on b5h's `out/rv32i_cpu_top.def`)
`scripts/nwell_islands_innovus.py` models every std cell's n-well from the sky130_fd_sc_hd `.mag` views (nwell x -0.19..W+0.19; y +1.305..+2.91 over the row origin for N/FN rows, -0.19..+1.415 for S/FS rows; two wells are one island when they overlap; `tapvpwrvgnd_1` is the only N+ tie) and unions them. On b5h: 462,039 std cells, 2,221 islands, **146 without a tap, every one made of `decap_3` endcaps at x = 98.44 um, y 24.48..911.2** (144 N+FS pairs and 2 singles). Nothing else on the die is untied (left die edge x=20.24, the other 7 macro-edge columns and the right die edge are all tied).
- `02_pdn.tcl`: `addEndCap` then `addWellTap -cellInterval 26 -checkerBoard`. The tap lattice is 25.76 um (56 sites) from the row start with no rule that a tap abuts a row-segment end. The row segment between the die edge and the tag SRAM is ~77 um (21.62..98.44); FS rows carry their last tap at 97.52..97.98, i.e. **one site (0.46 um) short of the endcap at 98.44**; N rows' last tap is at 84.64.
- Well geometry: tap n-well ends at 98.17, endcap n-well starts at 98.25: a 0.08 um slit = KLayout `nwell.2a` (x 98.17-98.25) and a floating endcap well (VPB open).
- Nothing fills the slit: `03_place.tcl` adds a hard placement blockage over x<120, y<917.5 (B5C/B5D screens), after the taps were placed, so neither logic nor decap/fill can land there.

## 2. Fix
`scripts/05j_tapfix.tcl` (+ generated `b5j_tap_list.tcl`): 146 x `tapvpwrvgnd_1`, orientation FS, at x = 97.98 in the FS row of each island (abutting the existing tap at 97.52 and overlapping the endcap well). Innovus `create_inst` failed silently (with and without `-physical`); legacy `addInst ... -physical` worked, `place_status fixed`. No re-place/re-route/`ecoRoute` was needed: `verify_drc` after the ECO = 0 (the logged `J_DRC_1: -1` is my parser missing the "No DRC violations were found" wording). Then `06_finish` (decap/fill, reports, outputs) and `07_restream` (GDS).
Physical-only cell count: `tapvpwrvgnd_1` 63,521 -> **63,667 (+146)**; every other master identical; instances 101,991 -> 102,137. The logical netlist (non-comment text md5 `6f3a123afa3c95f111d47cb192666e7a`) and the exported SDC are identical to b5h's.
Checker after the fix: **untied n-well islands 146 -> 0.**

## 3. Results, b5h -> b5j
| Check | b5h | **b5j** |
|---|---|---|
| nwell islands without tap (`nwell_islands_innovus.py`) | 146 | **0** |
| Innovus special-wire check VPWR (IMPVFC-92 / -200 / -96) | 144 / 1 / 2 | **0 / 0 / 0** (146 IMPVFC-94 dangling-wire notes unchanged) |
| `special_VGND` | 51,270 IMPVFC-92 (fill/decap VNB terminals) | not completed (the job was left to run for hours on a thrashing host; not on the signoff path) |
| `verify_drc` / antenna (native) / PG pieces | 0 / 1 / 1+1 | **0 / 1 / 1+1** |
| Native setup WNS / hold WNS (SI on; SI off) | +0.215 / +0.139 (+0.323 / +0.139) | **identical** (+0.215 / +0.139; +0.323 / +0.139) |
| Native power @ activity 0.1 | 70.62 mW | **70.62 mW** (50.674 + 19.854 + 0.095) |
| Netgen LVS, GDS-mode | not run | **devices 34,255 = 34,255; nets 35,214 = 35,214; fails top-level pin matching only on 3 netlist `assign` pairs (`axi_awlen_o[1]`, `axi_arlen_o[1]`, `axi_arburst_o[0]`) + layout-only VPWR/VGND labels; no isolated VPB nets** |
| Netgen LVS, DEF+LEF | (b5g: 146 VPB islands) | devices 34,255 = 34,255, nets 35,214 = 35,214, same 3-pair pin mismatch |
| KLayout DRC | (b5g 482: nwell.2a 434, m3.6 40, npc.2 8) | **60: m3.6 54, npc.2 6, nwell.2a 0** |
| Signoff antenna (OpenROAD) | (b5g 16 nets / 22 pins) | **10 nets / 10 pins** |
| Magic DRC | (b5g 28,320,643) | NOT RUN (host never idle) |
| Conformal LEC (RTL and Genus goldens, +/- diodes) | never run | **EQUIVALENT, 5,597 compare points, 0 non-eq / 0 abort / 0 unknown; 4/4 negative controls caught** (`lec_innovus_conformal.md` B4j) |
| StarRC (tuned ITF) nets | 35,088 | 35,088 (SPEF md5 differs by the 146 taps' parasitics) |
| PT judge, own SDC, nom_tt setup / hold | +0.706 / +0.140 | **+0.706 / +0.140 (identical to 6 digits)**; power (PrimePower B) 69.5 mW both |
| PT judge, all 27 runs (own / shared / iolat SDC x 9 corners), setup WNS and hold WNS (+ hold-violator count) | b5h recorded | **identical in all 27 runs** (compared metrics.tsv setup_wns, setup_tns, hold_wns, hold_viol of every b5h/b5j pair: 0 differ) |
|  own SDC | nom_tt +0.706/+0.140; ss/ff corners fail (SRAM tt-only model) | nom_tt +0.706/+0.140, min_tt +1.066/+0.139, max_tt +0.214/+0.140; nom_ss -7.766/-0.456, min_ss -7.032/-0.239, max_ss -8.759/-0.744; nom_ff +2.651/-0.310 (11 viol), min_ff +2.945/-0.446 (29), max_ff +2.143/-0.129 (2) |
|  shared SDC | nom_tt -0.456/-2.200 | nom_tt -0.456/-2.200, min_tt +0.316/-2.046, max_tt -1.609/-2.396, nom_ss -8.455/-3.751, min_ss -7.470/-3.534, max_ss -9.761/-4.039, nom_ff +2.185/-1.459, min_ff +2.833/-1.351, max_ff +1.212/-1.608 |
|  iolat SDC | nom_tt +1.322/-0.422 | nom_tt +1.322/-0.422, min_tt +2.094/-0.268, max_tt +0.169/-0.618, nom_ss -7.766/-1.973, min_ss -7.032/-1.756, max_ss -8.759/-2.261, nom_ff +3.963/+0.022, min_ff +4.462/+0.020, max_ff +2.990/+0.023 |

Attribution: b5h is a re-route from the start of P&R, not an ECO of b5g, so KLayout `m3.6`/`npc.2` and antenna differ from b5g's by lineage; they could not be split from the tap ECO without a b5h DRC run. What the ECO changed is measured exactly (nwell.2a 434 -> 0, islands 146 -> 0, connectivity opens 144 -> 0) and timing, power, netlist and SDC did not move.
Remaining KLayout items: `m3.6` = 0.33 x 0.33 um met3 squares (0.109 um2 < 0.24) at the die edges (x 0.5-3.6 and 3595.9-3599.4, y 130-1722), `npc.2` = six 0.13 um npc spacing pairs at (1454.4,1127.4), (1524.3,1396.7), (1197.8,1195.3), (1781.5,1094.8), (1203.3,1189.9), (1499.1,1287.8).

## 4. Host and process notes
A host power loss (2026-10-31 night) lost the first tap-fix attempt; restarted from the verified copy. Innovus start-up/exit took 10-25 min under host memory thrash (kswapd / 100 % system time, load 40-97). Two licensed tools once started together (pgrep race) before the flock lock was introduced. All 27 judge runs completed (2026-11-02 02:10).

Out of scope, unchanged: max_cap/max_tran nets (480/110), 26 unconstrained mbist inputs, min/max capTables (round 2 / b5k).
