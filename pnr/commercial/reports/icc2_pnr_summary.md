# Synopsys ICC2 arm, Sky130 `rv32i_cpu_top` place and route (step B5a)

**Comparison run, no tuning target.** One flow pass from the Formality-proven DC-NXT netlist (`syn/dc/runs/b3a_dc_tt/out/rv32i_cpu_top.nl.v`,
RTL == netlist, 6,233/0 compare points) to routed, filled, GDS-written layout, with the same physical setup as the OpenROAD arm
(`openroad_summary.md`, run `b2_openroad`). SDC is the original `pnr/sky130/cpu/constraints/sky130_cpu.sdc` (md5 `3c69635042a9d65cb87e71a9db713e4e`,
verified in the log), **not** DC's written SDC. Git base `934c83e`, branch `feat/commercial-pd-sky130`.

Tool: `icc2_shell` X-2025.06-SP1, `set_host_options -max_cores 2`, every stage under `safe_run.sh` (6 GB cap). Scripts, Makefile:
`pnr/commercial/impl/icc2/` (`make -C pnr/commercial/impl/icc2 all`). Run dir (gitignored): `pnr/commercial/impl/icc2/runs/b5a_icc2/`
(`rv32i.dlib` with one block label per stage, `logs/`, `out/`). Committed report copies: `pnr/commercial/impl/icc2/reports/*.txt`.

## Result in one paragraph
Routed with **0 DRC, 0 shorts, 0 opens, 0 antenna (ICC2 `check_routes` / `check_lvs`, see the antenna caveat), PG DRC clean, no floating PG**, setup **-0.0046 ns**
(one path, TNS -0.0046) and hold **+0.0008 ns** at tt with nominal TLU+, 4.46 Mum of wire, 389 k contacts, 30 min wall total, 3.8 GB peak.
It did **not** converge on the first pass: `route_auto` + `route_opt` left 81 DRC and 100 shorts, almost all in the 20 um strip below the I-cache
SRAMs (their pins face the die edge). Two more incremental detail-route loops with `drc_convergence_effort_level high` brought it to 0.
All numbers below are tool-native ICC2 readings; the neutral StarRC->PrimeTime judge has not run.

## Table vs the OpenROAD arm (tt, `nom` parasitics)
| Metric | OpenROAD / LibreLane (`b2_openroad`) | ICC2 (`b5a_icc2`) | Read with |
|---|---|---|---|
| Netlist in | Yosys+ABC, 5,299 flops, 339,360 um2 synth std area | DC-NXT, 5,284 flops, 259,850 um2 | different netlists (cell choices, -23 % area) |
| Setup WNS / TNS (nom_tt) | **+3.031 ns** / 0 (ss reg-to-reg fails, -3.996 ns, 1149 viol.) | **-0.0046 ns** / -0.0046 ns, 1 violating path | ICC2 optimises to slack 0 and stops; OR keeps margin. Not a quality ordering. ICC2 had one scenario (tt) only |
| Hold WNS / TNS (nom_tt) | -0.458 ns / -18.0 ns (156 viol., all I/O ports; 0 reg-to-reg) | +0.0008 ns / 0 (0 viol.) | ICC2 repaired port hold paths too |
| Clock skew, tt | worst setup skew 1.02 ns, hold -1.09 ns (STA) | global skew 1.08 ns, latency 1.06-2.14 ns, 5,304 sinks | |
| Power (tool-native, indicative) | 103.4 mW (OpenSTA, post-route) | 55.9 mW total (dyn 55.8, leak 0.095), clock network 23.7 mW | **not comparable**: different default activity (75 % of nets zero toggle in ICC2), no activity file in either |
| Std-cell area (excl. macros) | 707,819 um2 (includes 160,369 um2 decap-class cells, 74,623 tap, 1,015 clk bufs, 10,603 timing-repair bufs) | 302,778 um2 logic+clock+diodes (netlist area 2,220,654 - macros 1,917,876); +94,924 um2 taps/endcaps (pre-fill) | OR figure includes decaps ICC2 did not place |
| Core utilisation (cells+macros / 6,254,430 um2) | 41.81 % (with decaps) | 37.0 % pre-fill (taps/endcaps in, no decap); site-row util 7.23 % | |
| Leaf cells | 166,315 instances: 5,299 flops, 59,641 tap, 64,086 decap, 390,647 fill, 10,603 repair bufs, 1,015 clk bufs + 628 clk invs, 10 macros | 628,289: 5,284 flops, 63,237 tap, 4,210 endcap, 526,060 fill, 115 port diodes, 10 macros; 34,782 non-physical leaf cells (pre-fill) | fill/decap mixes differ (below) |
| Clock cells | clkbuf_2/4/8/16 + inverters, 1,015 + 628 | clkbuf_2 317, _4 837, _8 283, _16 55, clkinv_* 474, plus 1,043 clkbuf_1 (optimisation buffers, not CTS) | |
| Routed wirelength | 5,586,306 um | 4,464,228 um (li1 2,587, met1 1,092,672, met2 1,466,901, met3 1,268,870, met4 631,466, met5 468) | |
| Vias | 517,723 (all single cut) | 389,127 contacts (mcon 122,122; via 185,126; via2 63,129; via3 18,744; via4 6) | |
| Routing DRC | 0 (iteration 21; 53,401 at iteration 1) | 0 (81 after first route_auto+route_opt, 35 -> 9 -> 4 -> 0 over the repair loops) | |
| Shorts / opens | LVS 0 errors (Netgen) | 0 / 0 (ICC2 `check_lvs`) | tools differ; no Netgen run on the ICC2 GDS yet |
| Antenna | 116 nets / 119 pins (OpenROAD checker) | **0** (ICC2 `check_routes -antenna`) | **rule differs**, see caveats; do not read as better |
| Max-transition / max-cap violations | 3,437 / 270 (nom_tt) | 57 / 164 (`report_constraints`, tt) | OR limits 0.5 ns, fanout 8; ICC2 SDC values |
| PG | PSM: all shapes connected | `check_pg_drc` no errors, `check_pg_connectivity` 0 floating wires/vias/macros | |
| Runtime, equivalent stages | floorplan+tap+PDN 33 s; place+repair+DPL 268 s; CTS 306 s; GRT+antenna+resizer 1,034 s; DRT 1,165 s; fill 19 s; RCX+STA 88 s (4 threads) | floorplan 14 s; PDN 14 s; place_opt 480 s; clock_opt 732 s; route_auto+route_opt 220 s (+ repair 152+144 s); finish 132 s (2 cores) | wall clock incl. tool start; ICC2 total 1,780 s |
| Peak RSS | not recorded per step | 1.9 GB floorplan, 2.0 PDN, 3.1 place, **3.8 CTS**, 3.3 route, 3.0/2.6 repair, 3.6 finish | |

Per-stage wall/RSS: `reports/stage_markers.txt`. Cell-type histogram: `reports/final_cellcount.txt`.

## Physical setup actually used (what matches OpenROAD, what does not)
Matches: die 0 0 3600 1800 and core on the OpenROAD row lattice (x 20.24..3579.72, y 24.48..1778.88, 645 rows, first row flipped) via
`initialize_floorplan` + core offsets; 503 pins fixed from `pin_template.def` (`read_def -include ports`, 503/503 fixed); 10 SRAMs at the
`macro_placement.cfg` coordinates, orientation N, fixed (instance names are DC's: `u_core/u_icache_gen_data_sram_N__u_data_sram`,
`u_core/u_dcache/gen_data_sram_N__u_data_sram`); netlist flattened with `ungroup_cells -all -flatten`; routing layers met1-met4 (`set_ignored_layers`);
tracks at the tech-LEF pitches/offsets; PDN met1 followpin rails 0.48, met4 vertical + met5 horizontal straps width 3.1 / spacing 1.7 / pitch 100 /
offset 20, SRAM vccd1/vssd1 on VPWR/VGND, met4 straps cut at the SRAMs and met5 straps over them dropping vias onto the SRAM met4 ring pins;
taps `tapvpwrvgnd_1` at 26 um per row staggered (OpenROAD `-distance 13` checkerboard) and `decap_3` endcaps; `dont_use` = the 21-cell
`dont_use.tcl` list plus LibreLane's `drc_exclude.cells` and the two probe cells (diode_2 re-enabled for antenna fixing); CTS cells clkbuf_2/4/8/16.

Differences that change the numbers (set approximately or not replicable):
1. **Placement density and padding.** OpenROAD `PL_TARGET_DENSITY_PCT 25` is a target; ICC2 got `place.coarse.max_density 0.25` (a cap). Cell padding 4 sites per side
   is modelled as a placement spacing rule (illegal gap 0..7 sites between any two logic cells). Timing- and congestion-driven placement are ICC2 defaults.
2. **Max fanout.** ICC2 ignores the SDC `set_max_fanout` (CSTR-011); `opt.common.max_fanout 16` carries the SDC value. OpenROAD ran `MAX_FANOUT_CONSTRAINT 8`.
3. **CTS.** ICC2 has no root-buffer option, so `CTS_ROOT_BUFFER clkbuf_16` is not enforced; sink clustering size 25 is `cts.common.max_fanout`; no NDR.
4. **Antenna.** The generated `sky130_antenna_rules` proc passes the LEF PWL tables as `-diode_ratio` pairs, which ICC2 rejects (on the first route attempt
   the rules were silently not defined). `scripts/antenna_rules.tcl` defines the unprotected ratios from the tech LEF (li1 75, mcon 3, met1-4 400, vias 6) with
   **diode_mode 1 (a diode makes a net safe)**, so the LEF diode-area relaxation is not modelled. 115 input-port diodes (`diode_2`, every input but `clk_i`) and
   router-inserted diodes; no heuristic pre-insertion like OpenROAD's. The 0 is therefore lenient for diode-protected nets and not comparable to OpenROAD's 116.
5. **Fill.** OpenROAD inserted `decap_12/8/6/4/3` then `fill_*` (64,086 + 390,647). ICC2 inserted **fill_* only** (526,060 after removing 428 that overlapped router
   pin-access stubs on li1). Decaps were tried first and gave 13,065 shorts: the decap/fill frames carry a li1 blockage over the whole cell, and ICC2 routes li1 pin-access stubs.
   `sky130_ef_sc_hd__decap_12` is not in the NDM in any case.
6. **li1 use.** The router used li1 for 2,587 um of pin-access stubs (122 k mcon vias). `set_ignored_layers -min_routing_layer met1` does not forbid this; OpenROAD's detailed
   router does not use li1. Signal routing proper is met1-met4 in both.
7. **Taps/endcaps.** 63,237 taps and 4,210 endcaps vs 59,641 and 2,792: the OpenROAD macro halo (10 um for taps) and its row cutting at macros are not replicated.
8. **Parasitics and corners.** One scenario at tt/1.80 V/25 C, `read_parasitic_tech` with the nominal TLU+ for both early and late (no min/max TLU+ exist), authored-ITF TLU+ not yet
   correlated with OpenRCX (part 2b). OpenROAD's flow reported 9 corners. The ICC2 SPEF is **tool-native** (`out/rv32i_cpu_top.icc2native.spef.tlu_nom_25.spef`).
9. **Netlist front end.** DC-NXT vs Yosys netlist differ in flop count (5,284 vs 5,299), cell mix and area (see the table), so P&R results mix synthesis and P&R effects.
10. **PDN via arrays.** The generated `.tf` ContactCodes carry no cut spacing, so the default PG via arrays overlapped their own cuts (1.73 M `check_pg_drc` "overlap of via cuts").
    `set_pg_via_master_rule` with the tech-LEF cut spacings (via 0.17, via2/via3 0.2, via4 0.8) fixes it (`scripts/02_pdn.tcl`). Worth folding into the `.tf` generator.
11. **Power.** `set_voltage` on the PG nets did not take (no supply-net objects without UPF; tool warns POW-080 and uses library nominal), so the power figure is a vectorless estimate.
    No IR drop or EM analysis was run (RedHawk later).

## Outputs (`pnr/commercial/impl/icc2/runs/b5a_icc2/out/`, gitignored)
| File | Content |
|---|---|
| `rv32i_cpu_top.nl.v` (5.9 MB, md5 `e9150655...`) | logical netlist: no PG ports/connections, no taps/endcaps/fillers, 115 port diodes kept, 0 `assign`; contains one `supply1 VPWR;` declaration; **not LEC'd** |
| `rv32i_cpu_top.pg.nl.v` (8.4 MB, md5 `2ee758bc...`) | PG netlist (VPWR/VGND, SRAM vccd1/vssd1), no physical-only cells |
| `rv32i_cpu_top.full.pnl.v` (99 MB) | PG netlist with taps (63,237), endcaps (4,210), fillers (526,060): for LVS |
| `rv32i_cpu_top.def` (105 MB) | routed DEF with all physical cells, PG special nets |
| `rv32i_cpu_top.gds` (80 MB) | `write_gds`, std-cell GDS (`sky130_fd_sc_hd.gds`) and SRAM GDS merged, layer map `scripts/gds_layer_map.txt` (tool layer -> `sky130A.map` numbers, labels as text on x:5). **Not opened in KLayout, not DRC/LVS'd** |
| `rv32i_cpu_top.sdc` | `write_sdc` of the final block (the judge should use the original SDC) |
| `rv32i_cpu_top.icc2native.spef.tlu_nom_25.spef` (125 MB) | tool-native SPEF, nominal TLU+, scenario `default` |

Netlist changes relative to DC (function unchanged by construction, **not formally re-verified**): `assign` elimination buffers, optimisation and CTS buffers/resizing, 115 port diodes.

## Stage notes (what was found, in order)
- Floorplan: `remove_site_rows -all` leaves the rows `initialize_floorplan` created, and `-boundary` is the core (not the die), so the core boundary was given as the OpenROAD row lattice with core offsets reaching 0 0 3600 1800.
- ICC2 stage chaining: `save_lib` writes edits made to an opened block back into that label; each stage therefore copies the previous label first (`open_stage`).
- Placement (`place_opt`, 8 min): legal, setup 0.00 / hold +0.12, site-row util 6.6 %.
- CTS (`clock_opt`, 12 min): setup +0.02, hold 0.00.
- Routing: the shorts sat in the strip below the I-cache SRAMs (84 of 100 at y < 25 um) where ~370 SRAM pins must escape sideways to the 200 um gaps. Default effort oscillated
  (81 -> 107 -> 71 -> 91 ...); `route.detail.drc_convergence_effort_level high` with `route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60` converged (35, 9, 4, then 3, 2, 7, 1, 1, 1, 0).
- Final setup -0.0046 ns appeared after those repair passes (route_opt had ended at 0.00); no further `route_opt` was run.

## Not done / open
- Neutral StarRC->PrimeTime judging, ss/ff corners, Magic/KLayout DRC and Netgen LVS on the ICC2 GDS, Formality of the ICC2 netlist against RTL, IR drop (RedHawk), a second timing-repair pass to clear the -0.0046 ns path.
- Reproduce: `make -C pnr/commercial/impl/icc2 all` (needs `pnr/commercial/pdk/sky130/build/{ndm,nxtgrd,tech}` from `make part2a`/the TLU+ queue and the DC netlist); one stage: `scripts/run_stage.sh 06_finish b5a_icc2`.
