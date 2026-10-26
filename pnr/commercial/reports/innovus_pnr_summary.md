# Cadence Innovus place-and-route, Sky130 `rv32i_cpu_top` (steps B5b, B5c)

**B5c verdict (final Innovus arm result): the flow completes to GDS with timing met at tt but routing DRC is NOT zero: 3 `verify_drc` Metal Short markers remain (B5b: 1,579).**
Routing-DRC verdict: **FAIL (3 markers), not DRC-clean.** Max-tran / max-cap: **FAIL, unrepaired** (115 and 476 nets violating at tt, worst -4.793 ns / -0.649 pF; B5b 122 / 475). All numbers are Innovus-native,
tt, tech-LEF RC (no qrcTechFile; the capTable stop-gap was rejected by Innovus, see B5b notes). Final timing/parasitics are the neutral judge's job. Nothing was LEC'd, LVS'd or opened in KLayout.
The B5b sections further down are kept as the first attempt; the Innovus deliverables are now the **B5c** ones in `pnr/commercial/impl/innovus/runs/b5c_innovus_s2/out/` (`reports/*.txt` were overwritten with the B5c reports;
B5b originals are in git and in `runs/b5b_innovus`).

## B5c: reroute to fix the left-edge DRC hotspot
**Root cause (diagnosis from the B5b DEF vs the OpenROAD and ICC2 DEFs, no tool run needed).** The 16 pins in the hotspot window are `commit_insn_o[8..23]`, met3 on the left edge, 17.68 um apart, all exactly on the
met3 y tracks (offset 0.34, pitch 0.68; integer track index): pin access/off-grid is **not** the cause. The cause is placement. Innovus put **536 logic cells in the 100 um pocket x<100** beside the tag-SRAM column
(OpenROAD 66, ICC2 24) and **370 cells above it** (x<300, y 917-1050; OpenROAD 12, ICC2 7): mostly `FE_OFC*`/`FE_PHC*` port buffers (`apb_pwdata_i`, `commit_insn_o`, `mbist_cfg_i`, `commit_pc_o`...) pulled toward the
left-edge pins. That pocket is the through-route channel for nets whose pins are on the top (`mbist_status_o`, `axi_aw*`, `axi_wdata_o`), right (`apb_pwdata_i`) and bottom (`axi_ar*`, `axi_rdata_i`) edges, so the macro OBS
(met1/met2 full, met3/met4 partial) plus the cells left no tracks: 1,507 shorts, 91 % of the markers in x 0-300 / y 750-1050. Other regions (channel, gaps, right strip) matched the reference arms (2,131 vs 2,720 / 2,533 channel cells).
The global-route overflow map of the window was not obtained (`report_congestion` does not exist in this Innovus; the design-wide overflow after place was 0.48 % H / 1.09 % V). No PDN strap or SRAM halo exists in the window beyond the
PDN already described (no halo in any arm).

**Step 1 (primary fix, from 03_place): a left-edge placement screen** (`B5C_SCREEN=1` in `03_place.tcl`): hard placement blockage `{0 0 100 917.5}` (the dead-end pocket) + partial blockage 15 % `{0 917.5 300 1100}`. Everything else
unchanged (same netlist, SDC, tt MMMC, LEF RC, same scripts); floorplan and PDN re-run from scratch (deterministic). Run `runs/b5c_innovus`.
**Step 2 (separate change, from 02_pdn): keep the met4 straps 25 um away from the D-cache SRAM bottom edge** (`B5C_STRAP=1`, `addStripe -area_blockage {20 495 3580 520}` for the met4 stripes only), chosen because after step 1 the 31
remaining markers were 22 met4 `ParallelRunLength` spacings between signal wires and the VPWR/VGND met4 straps plus 9 shorts, 27 on met4, all at y=519.6 (the D-cache macro pin edge) - i.e. a PDN-vs-macro-pin interaction, the
ICC2 arm's solution family (it cut its met4 straps at the macros). Full flow re-run from 02_pdn, run `runs/b5c_innovus_s2` (placement screen kept).
**Step 3 (tried, discarded):** an extra `ecoRoute -fix_drc` loop after post-route opt (`05d_final_repair.tcl`) went 3 -> 5 markers; reverted by re-running `06_finish` from the step-2 `05_route` label (3 markers, verified).
The in-flow `05b_repair` (ecoRoute, 4 passes) moved: step 1 30 -> 25 (post-route opt re-introduced to 31); step 2 3 -> 2 (post-route opt back to 3).

### B5b -> B5c delta
| Metric | B5b (no fix) | B5c step 1 (placement screen) | **B5c final (screen + strap keep-out)** |
|---|---|---|---|
| Detail-route DRC at the start of NanoRoute | 4,769 | 707 | n/a (3 after route) |
| `verify_drc` after routing | 1,584 | 30 | **3** |
| `verify_drc` final (after post-route opt + fill) | 1,579 (1,507 shorts) | 31 (22 spacing met4 vs PDN, 9 shorts) | **3 Metal Short** (2 met4, 1 met3; 2 within 10 um of an SRAM edge at x~100/y~520 and x~1.2/y~580, 1 at x 96.7/y 685.6) |
| Logic cells in the left pocket x<100 / x<300,y917-1050 | 536 / 370 | 9 / 182 | 7 / 196 |
| Antenna (`verifyProcessAntenna`) | 0 | 3 nets | 1 net / 1 pin |
| Setup WNS tt (I/O group; reg2reg) | +0.173 ns (+2.147) | **-0.574 ns**, TNS -0.860, 2 paths (+2.934) | **+0.008 ns**, TNS 0, 0 paths (+1.408) |
| Hold WNS tt (reg2reg) | -0.0004 ns, 1 path (+2.156) | +0.006 ns (+2.346) | **+0.115 ns**, 0 paths (+2.809) |
| max_tran violating nets (worst) | 122 (-3.639 ns) | 115 (-4.191) | **115 (-4.793)** |
| max_cap violating nets (worst) | 475 (-0.504 pF) | 474 (-0.578) | **476 (-0.649)** |
| Power (default activity, indicative) | 87.82 mW | 90.99 mW | **91.46 mW** (internal 54.78, switching 36.59, leakage 0.095) |
| Signal wirelength | 6,050,812 um | 6,523,112 um | **6,592,299 um** (met1 2,165,312; met2 2,170,403; met3 1,704,234; met4 552,349) |
| Cut vias (report_route) | 305,986 | 306,750 | **307,565** |
| `report_area` (incl. 1,907,125 um2 macros) | 2,229,879 um2 | 2,252,674 um2 | **2,251,218 um2** -> ~344,093 um2 logic+clock+tie+diode |
| diode_2 / conb_1 / taps | 271 / 133 / 63,521 | 265 / 133 / 63,521 | 262 / 133 / 63,521 |
| Wall: place / CTS / route / post-route opt / finish | 9.5 / 9.3 / 63 / 52.5 / 2.3 min | 15.5 / 13.4 / 12.8 / 14.3 / 7.6 min | **9.8 / 8.2 / 5.3 / 7.4 / 3.3 min** (router converges in 5 min instead of 63) |
| Peak RSS (finish) | 7.1 GB | 6.9 GB | 6.9 GB |
Step-1/final timing is the same SDC, tt, LEF RC, `-effortLevel low` post-route extraction; the step-1 setup regression (-0.574 ns on two I/O paths) disappears in the final run, which is a different placement/CTS/route
outcome, not a measured effect of the strap change alone: the two runs differ in PDN and therefore in every downstream stage, so no per-step timing attribution is claimed. Wall times are contended-host figures (Techgen and StarRC were running).

### B5c verdicts
- **Routing DRC: FAIL, 3 markers (was 1,579).** The remaining 3 shorts are single-net-pair shorts near the left-edge pocket / macro column; repair attempts do not converge (ecoRoute 3 -> 2 in the loop, back to 3 after the post-route opt; a post-opt repair made it 5).
- **Antenna: 1 net / 1 pin** (`verifyProcessAntenna`). **Max-tran / max-cap: FAIL, unrepaired** (115 / 476 nets).
- Setup/hold at tt (LEF RC): met (+0.008 / +0.115 ns), with the usual caveat that Innovus optimises setup to ~0; the neutral judge decides.
- PG/well-pin connectivity reports are still saturated by decap/fill well pins and unusable (as in B5b); `verifyPowerVia` clean.

### B5c outputs (replace the B5b ones as the Innovus arm's deliverables)
`pnr/commercial/impl/innovus/runs/b5c_innovus_s2/out/`: `rv32i_cpu_top.nl.v` (logical, no PG/physical cells, not LEC'd), `rv32i_cpu_top.pg.pnl.v` (PG + physical, for LVS), `rv32i_cpu_top.def`, `rv32i_cpu_top.gds`
(hd + SRAM merged, Sky130 layers; not opened in KLayout), `rv32i_cpu_top.sdc`, `rv32i_cpu_top.innovus_native.spef` (tech-LEF RC, NOT signoff). Databases in `runs/b5c_innovus_s2/dbs` (`05_route` and `06_finish` are the final labels;
`05d_final` is the discarded step 3). Step-1 run: `runs/b5c_innovus`. Reproduce: `TAG=b5c_innovus_s2 B5C_STRAP=1 scripts/chain_b5c.sh` (step 1 only: `scripts/chain_b5c.sh`), final fill/outputs via `FROM_LABEL=05_route scripts/run_stage.sh 06_finish b5c_innovus_s2`.
DRC classification files: `reports/drc_classification_b5b_final.txt`, `..._b5c_step1_after_route.txt`, `..._b5c_final.txt`.

## B5b (first attempt, kept for the record)
Run dir (gitignored): `pnr/commercial/impl/innovus/runs/b5b_innovus` (`dbs/`: `01_floorplan 02_pdn 03_place 04a_cts_raw 04_cts 05a_routed 05_route 06_finish`).
Scripts + Makefile: `pnr/commercial/impl/innovus/`. Native reports as `.txt`: `pnr/commercial/impl/innovus/reports/`. Innovus 23.14-s088_1, `setMultiCpuUsage -localCpu 2`,
every run under `safe_run.sh` (SAFE_MEM_MAX 7G). Netlist in: `syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v` (Conformal-proven, B4b). SDC: the ORIGINAL
`sky130_cpu.sdc` (md5 3c69635042a9d65cb87e71a9db713e4e), not Genus's. The Conformal check of the Innovus output netlist is NOT RUN.

## Inputs and setup actually used
| Item | Used |
|---|---|
| Netlist | `syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v` (Conformal-proven, B4b). Hierarchy kept as in the netlist (4 modules); physical design is flat. 131 Genus `assign`s remain in the db (ports tied to constants / aliased outputs). |
| SDC | the ORIGINAL `pnr/sky130/cpu/constraints/sky130_cpu.sdc` (md5 3c69635042a9d65cb87e71a9db713e4e), not Genus's. Innovus skips `set_max_area` (CTE-25). |
| MMMC | tt only (`scripts/mmmc_tt.tcl`): `sky130_fd_sc_hd__tt_025C_1v80` + patched TT SRAM lib, setup and hold both `av_tt`. |
| RC | **no qrcTechFile** (Techgen nom still running). Implementation stages 01-04 use **tech-LEF RC** (preRoute). A stop-gap capTable from the authored ICT (`generateCapTbl`, `runs/captbl/sky130A_nom.captbl`, finished rc=0, ~55 min single thread) is wired in for post-route extraction only (`update_rc_corner` in 05/06). Layer-name mapping of that table to the LEF (li1 is a LEF routing layer, the table has M1..M5) is NOT verified. |
| Die/core | die 0 0 3600 1800; core 20.24 24.48 3579.72 1778.88 (the OpenROAD row lattice, 645 rows, first row MX = DEF "FS"); `floorPlan -noSnapToGrid`. |
| Pins | `pin_template.def` read with `defIn`, 503 pins, all fixed (met2/met3). |
| Macros | 10 SRAMs placed + fixed at the `macro_placement.cfg` coordinates (orientation N = R0); the Genus names `u_core/u_{i,d}cache_gen_data_sram[k].u_data_sram` / `..._u_tag_sram` were mapped 10/10. The 5 I-cache macros sit at y=20 while the core starts at y=24.48 (same as the OpenROAD config; reported by checkPlace as out-of-core fixed). |
| Tracks | LEF pitches restored (`sky130_tracks_innovus.tcl`) **and** the preferred-direction start offsets now match the tech-LEF OFFSETs (met3 y .34, met4 x .46, met5 y 1.7; li1/met1/met2 already matched): `add_tracks -offsets` is accepted but ignored, so all 12 track patterns are re-created from a TRACKS-only DEF read with `defIn` (`01_floorplan.tcl`). Non-preferred-direction offsets stay Innovus-chosen. This is closer to OpenROAD than the part-2a state. |
| Routing layers | met1..met4 (`setDesignMode -bottomRoutingLayer met1 -topRoutingLayer met4`; NanoRoute layers 2..5), li1 not routed. |
| PDN | `globalNetConnect` VPWR/VPB/vccd1 and VGND/VNB/vssd1 (SRAM power tied to VPWR/VGND, single net pair); met1 followpins (`sroute -connect corePin`); met4 vertical + met5 horizontal straps width 3.1, spacing 1.7, set-to-set 100, offset 20; `sroute -connect blockPin` to the SRAM met4 pins. 68+70 met4 and 28+28 met5 stripes, 25k+25k stacked vias. **Not blocked over the SRAM footprints** (ICC2 cut the met4 straps at the macros); whether that is the source of the routing DRCs is untested. |
| Taps / endcaps | `tapvpwrvgnd_1`, `-cellInterval 26 -checkerBoard` (FP_TAPCELL_DIST 13 x 2): **63,521** taps (OpenROAD 59,641); `decap_3` endcaps: 4,210 (also placed at row ends beside the macros). |
| Placement | `place_opt_design` with `place_global_max_density 0.25`, `specifyCellPad -left 4 -right 4` on 415 lib cells (OpenROAD GPL/DPL_CELL_PADDING 4), timing- and routability-driven. |
| CTS | `clock_opt_design -cts` (`ccopt_design` is rejected on a PODv2 db), `buffer_cells` clkbuf_2/4/8/16, no inverters, `max_fanout 25`. **The clkbuf_16 root buffer cannot be forced** (IMPCCOPT-2069: no per-net-type form of `buffer_cells`); recorded limitation. |
| dont_use | PDK-enablement `dont_use.tcl` list + LibreLane `drc_exclude.cells` + probe cells; diode_2 re-enabled for antenna repair. |
| Antenna | 115 input-port protection diodes (`attachDiode`, `diode_2`, all input ports except `clk_i` that have a load; 8 inputs with no load skipped); route-time diode insertion armed (`-routeInsertAntennaDiode true -routeAntennaCellName diode_2`). The OpenROAD arm's `RUN_HEURISTIC_DIODE_INSERTION` put 64,086 diodes in the design; this arm does not do that, so antenna counts are not comparable until the router finishes. |

## Results (Innovus native, tt, tech-LEF RC, `-effortLevel low` post-route extraction, OCV mode without derates)
| Stage | Result | Wall | Peak RSS |
|---|---|---|---|
| 01 floorplan | 645 rows, 503 pins fixed, 10/10 macros placed + fixed, tracks at LEF pitches and LEF offsets | 20 s | 2.5 GB |
| 02 PDN | 68+70 met4, 28+28 met5 stripes, 25k+25k vias | 28 s | 2.7 GB |
| 03 place_opt | pre-CTS setup WNS +1.771 ns (reg2reg +3.457), density 14.1 % | 9 min 30 s | 4.6 GB |
| 04 CTS + post-CTS opt | setup +0.017 ns (I/O group; reg2reg +3.360), hold +0.004 ns (reg2reg +0.152); 249 clock buffers, 0 inverters, 5,228 sinks, clock wire 91,883 um | 9 min 17 s | 4.7 GB |
| 05a NanoRoute (`routeDesign -globalDetail`) | 1,584 DRC at the end (4,769 at iteration 1, 1,711-1,880 from iteration ~19 to 27 and beyond); antenna 16 nets | 63 min | 3.2 GB (router peak) |
| 05 post-route opt (`optDesign -postRoute` setup + hold) | pre-opt setup -0.386 ns, hold -0.602 ns (36 I/O paths); after: **setup WNS +0.173 ns, TNS 0; hold WNS -0.0004 ns (1 path), TNS 0; reg2reg +2.147 / +2.156 ns** | 52 min 31 s | 3.9 GB |
| 06 finish (decap + fill, checks, outputs) | see below | 2 min 16 s | **7.1 GB (6.8 GiB)**, close to the 7G cap |

## Final numbers
| Item | Value | Source |
|---|---|---|
| Routing DRC (`verify_drc`) | **1,579 markers**: 1,507 Metal Short, 69 ParallelRunLength Spacing, 3 Min Area; met2 852, met1 377, met3 269, met4 81 | `reports/final_drc.txt` |
| DRC location | **open core 86.1 %, within 10 um of an SRAM edge 12.5 %, I/D-cache channel 0.8 %, inside an SRAM footprint 0.6 %**; 91 % (1,443) sit in the 300x150 um bins x 0-300 / y 750-1050 (left die edge, left of and above the D-cache tag SRAM corner); the other 12 bins hold <= 88 each | `reports/drc_classification_post_opt.txt`, `scripts/classify_drc.py` |
| Antenna (`verifyProcessAntenna`) | **0 violations** after post-route opt (16 nets right after routing) | `reports/final_antenna.txt` |
| Setup, tt | WNS +0.173 ns (path-group `default` = I/O), reg2reg +2.147 ns, 0 violating | `final_setup.summary.txt` |
| Hold, tt | WNS -0.0004 ns (1 path, rounds to -0.000), reg2reg +2.156 ns | `final_hold.summary.txt`, `final_timing_hold.txt` |
| DRV | max_cap 475 nets (worst -0.504), max_tran 122 nets (worst -3.639 ns), not repaired | `final_setup.summary.txt` |
| Power (vectorless, default activity) | 87.82 mW total (internal 53.74, switching 33.99, leakage 0.095); macro 29.26, comb 31.15, seq 19.55, clock 7.87 | `final_power.txt` |
| Wirelength / vias | 6,050,812 um signal (met1 1,993,520, met2 1,979,171, met3 1,490,657, met4 587,463, li1 and met5 0); cut vias 305,986 (mcon 112,934, via 149,358, via2 32,224, via3 11,470, via4 0) | `final_route_summary.txt` |
| Leaf cells (after fill) | 133 conb_1 ties, 271 diode_2, decap_3/4/6/8/12 = 67,126 / 59,938 / 20,516 / 18,269 / 202,453, fill_1/2 = 318 / 2,581, 63,521 taps | `final_cellcount.txt` |
| `report_area` (no physical cells) | 2,229,879 um2 incl. 1,907,125 um2 macros -> ~322,754 um2 logic + clock + tie + diode | `final_area.txt` |
| `verifyPowerVia` | no problems | `final_powervia.txt` |
| Connectivity / PG connectivity | **NOT EVALUATED**: both reports hit the 100,000-message cap, all "terminal not connected" (decap/fill/tap well pins `VPB`/`VNB` are nwell/pwell layer pins with no metal) plus 130 dangling PG wires in the PG report. Pre-fill check on `02_pdn` showed the same well-pin class only. Real PG/LVS status needs Netgen/Magic. | `final_connectivity.txt`, `final_pg_connectivity.txt` (14 MB each, kept in the gitignored `runs/b5b_innovus/logs/`) |

## What had to be changed vs the first draft, and deviations
1. **capTable stop-gap rejected.** `generateCapTbl -ict sky130A_nom.ict` (55 min, no `-lef`: the LEF crashes it on the `licon` cut layer) produced a table with layers M1..M5; Innovus refused it at post-route
   (IMPEXT-3548 "layer M6 missing", IMPEXT-2715 syntax error line 96: li1 is a LEF routing layer, so the table is off by one layer). **All stages therefore use tech-LEF RC**, including the
   post-route extraction and the native SPEF (labelled below). No qrcTechFile exists (Techgen nom hit its 4 h timeout and was killed; the coordinator's `queue_extraction2.sh` is regenerating).
2. **Post-route needs OCV mode** (IMPOPT-7027): `setAnalysisMode -analysisType onChipVariation -cppr both` (no derates in the SDC, so numerically a single-corner analysis).
3. **`ccopt_design` is rejected on a PODv2 db** (IMPCCOPT-2440): `clock_opt_design -cts` used. The clkbuf_16 root buffer cannot be forced (IMPCCOPT-2069).
4. **DRC repair did not work.** `ecoRoute -fix_drc` from `05a_routed` went 1,584 -> 1,466 over 20 iterations and was stopped (killed) as non-converging; the post-route `optDesign` (which re-runs detail
   routing, ~50 min) ended at 1,579. The final database is the `05_route` label, not a repaired one.
5. **The coordinator's strap-cutting experiment was NOT run**: the evidence does not point at the SRAMs (86 % of markers are in open core; the hotspot is at the left die edge next to a macro corner, not along SRAM
   pins). Untested suspects: congestion in the 100 um strip between the die edge and the macro column (all nets to the 96 left-edge met3 pins, plus the bottom-edge met2 pins, pass there; nets in the markers include
   `mbist_status_o`, `commit_insn_o`, `axi_*`, `apb_pwdata_i`), the PDN stripes in that strip, and `-drouteUseMultiCutViaEffort low`. A rerun costs > 1 h per attempt (place stage 10 min + route 63 min + opt 52 min).
6. `final_violators.txt` was not produced (`report_constraint -drv_violation_type min_pulse_width` is an invalid value in this version); DRV counts come from the timing summaries instead.
7. Taps: 63,521 (`-cellInterval 26 -checkerBoard`) vs OpenROAD 59,641 / ICC2 63,237. Endcaps decap_3: 4,210 (same count as ICC2). Antenna: 115 port diodes + 156 route-inserted diode_2; the OpenROAD arm's
   `RUN_HEURISTIC_DIODE_INSERTION` put 64,086 diodes in; ICC2 used a lenient `diode_mode 1` rule. Antenna counts are not comparable across arms.
8. Decap (12/8/6/4/3) was placed before fill, as in OpenROAD. ICC2 skipped decap because of li1 shorts; here `verify_drc` after fill shows the same 1,579 markers as before fill, i.e. decap adds none.
9. PDN straps were not blocked over the SRAMs (ICC2 cut met4 there). 5 I-cache macros sit at y=20 while the core starts at y=24.48 (as in the OpenROAD config).
10. Track start offsets in the non-preferred direction are Innovus-chosen; the preferred-direction offsets match the LEF OFFSETs (met3/met4/met5 re-created from a TRACKS DEF).

## Comparison (OpenROAD = `b2_openroad`, ICC2 = `b5a_icc2`; each arm used its own netlist)
| Metric | OpenROAD | ICC2 | Innovus |
|---|---|---|---|
| Netlist | Yosys+ABC, 5,299 flops, 339,360 um2 | DC-NXT, 5,284 flops, 259,850 um2 | Genus, 5,208 flops, 251,744 um2 (synth) |
| Setup WNS nom_tt | +3.031 ns (post-route, SPEF) | -0.0046 ns | **+0.173 ns** (I/O group; reg2reg +2.147), LEF RC |
| Hold WNS nom_tt | -0.458 ns (156 I/O paths) | +0.0008 ns | **-0.0004 ns** (1 path) |
| Routing DRC | 0 | 0 | **1,579** (hotspot, unrepaired) |
| Antenna | 116 nets / 119 pins | 0 (lenient rule) | 0 (`verifyProcessAntenna`, LEF rules) |
| Max-tran / max-cap violating nets | 3,437 / 270 | 57 / 164 | 122 / 475 (tt, not repaired) |
| Power (indicative, tool-native) | 103.4 mW | 55.9 mW | 87.8 mW (default activity; not comparable) |
| Std-cell area excl. macros (logic+clock+diodes) | 707,819 um2 incl. decap/tap | 302,778 um2 | ~322,754 um2 |
| Taps / endcaps | 59,641 / n/a | 63,237 / 4,210 | 63,521 / 4,210 |
| Wirelength / vias | 5,586,306 um / 517,723 | 4,464,228 um / 389,127 | 6,050,812 um / 305,986 (cut-layer table, counts differ by tool) |
| Clock cells | 1,015 buf + 628 inv | 1,492 clkbuf_2/4/8/16 + 474 inv | 249 buf, 0 inv |
| Runtime place..route..opt (2 threads) | 4 threads, ~49 min summed stages | place_opt 480 s, clock_opt 732 s, route see ICC2 summary | place_opt 9.5 min, CTS 9.3 min, route 63 min + post-route opt 52 min, finish 2.3 min |
| Peak RSS | not recorded | 3.8 GB | 7.1 GB (finish: fill + SPEF + GDS), 4.7 GB CTS |
Caveats: Innovus used LEF RC with low-effort post-route extraction; ICC2 used nominal TLU+; OpenROAD used OpenRCX. Setup slack of a commercial optimiser stopping at ~0 and OpenROAD
keeping margin is not a quality ordering. Compare only through the judge.

## Outputs (all under `pnr/commercial/impl/innovus/runs/b5b_innovus/out/`, gitignored)
| File | Content |
|---|---|
| `rv32i_cpu_top.nl.v` (6.5 MB) | flat logical netlist: no PG, no taps/endcaps/decap/fill (0 cell instances of those); **not LEC'd** |
| `rv32i_cpu_top.pg.pnl.v` (52.5 MB) | flat PG netlist with physical cells, for LVS (not run) |
| `rv32i_cpu_top.def` (95.6 MB) | routed DEF with routing, vias, physical cells |
| `rv32i_cpu_top.gds` (100 MB) | `streamOut`, hd std-cell GDS + SRAM GDS merged, Sky130 layer numbers from `scripts/gds_layer_map.innovus` (drawing 20, via 44, pin 16, label 5); **not opened in KLayout, no DRC/LVS** |
| `rv32i_cpu_top.sdc` | `write_sdc -view av_tt` (the judge should use the original SDC) |
| `rv32i_cpu_top.innovus_native.spef` (31.9 MB) | **Innovus native SPEF, tech-LEF RC, effort low: NOT signoff-quality**, nominal rc corner |
Reports as `.txt`: `pnr/commercial/impl/innovus/reports/` (final_*, drc_after_route, drc classification files in runs/.../reports).

## Open
1. 1,579 routing DRC in the left-edge hotspot (x 0-300, y 750-1050). Candidates for one controlled experiment: block/shift the PDN stripes or add a routing blockage/halo strategy in the 100 um left strip, give the router
   more layers/tracks there, or lower local congestion in placement; evidence so far says congestion, not SRAM pins.
2. Real parasitics: qrcTechFile (or a layer-correct capTable) -> re-extract the final DB and write a Quantus-quality SPEF; the neutral StarRC -> PrimeTime judge reads the GDS/DEF/netlist independently.
3. LEC (Conformal) of `out/rv32i_cpu_top.nl.v` against RTL / the Genus netlist; LVS (Netgen) and DRC (KLayout/Magic) on the GDS; PG connectivity.
4. max_tran / max_cap violations (122 / 475 nets) are unrepaired.

## Reproduce / resume
```
cd pnr/commercial/impl/innovus
make all            # 01_floorplan 02_pdn 03_place 04_cts 05a_route, then 05_route (FROM_LABEL=05a_routed) and 06_finish (FROM_LABEL=05_route)
scripts/run_stage.sh 05b_repair b5b_innovus           # optional ecoRoute -fix_drc loop (did not converge; not part of the final DB)
python3 -I scripts/classify_drc.py runs/b5b_innovus/reports/final_drc.txt
make reports        # native reports -> reports/*.txt
```
Note: the original `05a_routed` database was produced by the routing half of the first-draft `05_route.tcl`; `scripts/05a_route.tcl` is that half, split out afterwards and not re-executed.
