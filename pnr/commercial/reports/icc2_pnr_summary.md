# ICC2 arm, B5e corrective rerun (IN PROGRESS: routing done, finish/outputs queued behind the load gate)

Run `b5e_icc2` (`pnr/commercial/impl/icc2/runs/b5e_icc2/`, gitignored). `b5a_icc2` is untouched. Same netlist (DC-NXT `b3a_dc_tt`), SDC (md5 `3c696350...`), floorplan,
macro placement, pins, PDN, scenario and tool settings as B5a. Three fixes:

1. **Router never on li1** (fixed at the generator): `gen_techfile.py` now emits into `sky130_tech_setup.tcl`
   `set_ignored_layers -min_routing_layer met1 -max_routing_layer met4` and `set_app_options -name route.common.global_min_layer_mode -value hard`
   (new args `--route-min-layer/--route-max-layer`). Root cause confirmed from the man pages: `set_ignored_layers -min_routing_layer` IS the router's global minimum,
   but `route.common.global_min_layer_mode` defaults to `soft` ("discouraged, not forbidden"), so B5a's setting was never enforced. `.tf` is byte-identical (md5 `c845f6d1...`),
   so no NDM rebuild. Vias down to li1 cell pins stay allowed (`number_of_vias_under_global_min_layer` = 1). `reload.tcl` now aborts a stage if the mode is not `hard`.
2. **Tap/endcap**: see "Findings" below (the premise did not hold; the tap stage is unchanged and audited).
3. **GDS**: `write_gds ... -long_names -output_pin all -merge_gds_top_cell rv32i_cpu_top` (06_finish.tcl:67).

## Status at hand-back (2026-10-29): routing done, finish/outputs NOT yet produced
The host was powered off 10-28 21:50 to 10-29 18:54; the design library survived (labels through `05x_route` intact, `rv32i.dlib.bak` kept per stage). Routing is finished
(`05y_repair`, 1 DRC / 1 short left); `05z_fix` (targeted rip-up of the last short) and `06_finish` + `07_write_verilog` are **queued behind the `safe_run.sh` load gate**
(host load 10.5-12.3 for the last hour, set by a Techgen job running at about 490 % CPU; the gate needs load < 6 and gives up after 2 h per stage).
`runs/b5e_icc2/out/` therefore holds only `fp.def` so far. Resume/inspect: `scripts/finish_chain.sh` is already running in the background
(`runs/b5e_icc2/chain_fin.log`, markers in `reports/stage_markers.txt`); if the process is gone: `scripts/run_stage.sh 05z_fix b5e_icc2` (optional) then
`B5E_FINISH_BASE=05y_repair scripts/run_stage.sh 06_finish b5e_icc2 && scripts/run_stage.sh 07_write_verilog b5e_icc2`.

## Routing: DRC / short trend (check_routes DRCs / check_lvs shorts, before each incremental `route_detail` pass)
| Stage (base) | Change vs the previous line | Counts |
|---|---|---|
| B5a `route_auto`+`route_opt`, then repair | li1 routable (soft min layer) | 81 / 100 -> 35 -> 9 -> 4 -> 0 |
| B5e `05_route` (hard li1 ban) | only the li1 fix | **291 / 439** (0 opens) |
| `05b_repair` passes 1-4 | route_detail, `drc_convergence_effort_level high` | 291/439, 1714/3793, 779/1633, 605/1208 |
| `05c_repair` passes 1-8 + final | same | 508/963, 425/840, 394/761, 345/739, 309/608, 287/612, 266/480, 236/453, final **222 / 423** |
| `05d` (from 05c, `allow_pin_connection`) | li1 pin stubs allowed again | 218/423, 172/332, 158/315, final 167/335. **Discarded**: only ~25 % better and it reopens li1 |
| `05e` (from 05c, rip-up of the 248 nets in shorts + `route_eco`) | | 222/423 -> 1073/2360 -> 594/1164 -> 433/833 -> 378/676 -> final 322/585. **Regression, discarded** (05c kept) |
| `05x_route` (from 04_cts, hard li1 ban) | `route.global.effort_level high`, `route.global.macro_boundary_track_utilization 60`, `route.detail.optimize_partition_size_for_drc true` | route_auto 266 DRC; after `route_opt` **231 / 347** (0 opens) |
| `05y_repair` (from 05x, 8 passes) | same repair loop | 231/347, 90/183, 47/94, 25/44, **1/1**, 1/1, 1/1, 1/1 -> final **1 DRC (1 short, met1, nets `u_core/ex1c_comb[158]` / `u_core/ex1c_ex1b_reg_q[124]`, bbox 0.14 x 0.14 um at (1918.1, 882.9))**, 0 opens |
`05y` final (ICC2 `check_routes`): li1 wire length **0 um**, met5 576 um (the soft max-layer setting, as in B5a: 468 um), 4,500,627 um total, 390,255 contacts. Wire/via counts of the DEF-level li1 audit follow with the final DEF.

**What caused the extra passes: the li1 ban, not the tap handling.** (1) The tap stage was not changed and its output is bit-identical to B5a's (`scripts/tap_segments.py`: 645 rows, 2,105 row segments, 0 without a tap, longest tap-free stretch 25.76 um <= 26 um).
Placement/CTS moved only marginally (place setup -0.03 vs 0.00 ns, CTS identical 0.02 ns, leaf cells -0.2 %/-0.2 %). (2) With li1 banned, the first route has 3.6x the DRCs of B5a (291 vs 81) and the shorts sit in one column,
x 1900-1960 um, y 300-1000 um, i.e. the 200 um gap between the D-cache (and I-cache) data SRAMs and its junction with the 102.5 um cache channel, where the ~370 SRAM pins facing the bottom/channel escape.
B5a had solved exactly this spot by sending 14 long vertical li1 wires (up to 400 um) through the SRAM interiors, which the SRAM LEF does not obstruct on li1 (those were the KLayout li.1/li.3 hits).
(3) Plain detail-route iteration converges only at about -8 %/pass in that spot (222 after 12 passes, with the router oscillating at 450-520 violations inside each pass); rip-up (`05e`) made it worse.
What helped was a routing-only combination (`05x`): global-route effort high + lower macro-boundary track utilisation + DRC-aware partition sizing. **The three options were applied together in one run, so their individual contributions are not separated** (and `05x` vs `05b/c` is also a different global route, so the comparison is one run per arm).
Not isolated either: the li1 effect vs the two small placement differences; but B5a (same everything except the soft li1 setting) had no such hot spot, which is the only controlled comparison available.

## Findings that differ from the task description
- **Tap/endcap insertion does not miss row segments** (B5a DEF audited with `scripts/tap_segments.py`: 2,105 segments, 0 without a tap). The 7 floating-well islands (13 cells) are reproduced exactly by
  `scripts/nwell_islands.py` on the B5a DEF (well bands merged across abutting cells and row pairs): each is a chain of 1-4 cells whose neighbours are missing. The gaps are the fillers `06_finish` removes
  where they overlapped router li1 pin-access stubs (428 removed in B5a), which breaks n-well abutment. So the island is a consequence of li1 routing, not of tap placement; with no li1 wires the removals should vanish.
  This is verified on the B5e final DEF (see below, pending). No change was made to tap insertion; it is audited in `02_pdn.tcl` (error if any segment has no tap) and the well-island check runs on the final DEF.
- Both floorplans have the die area offset by 3.36 um in y (`DIEAREA ( 0 3360 ) ( 3600000 1803360 )`); the bottom-edge ports at y = 0..4 um are partly outside it (router warnings ZRT-720). Unchanged from B5a (identical floorplan was requested); worth a look in the next floorplan revision.

## GDS write (tested on the B5a block copy, before the rerun)
`write_gds -layer_map ... -merge_files ... -long_names -output_pin all -merge_gds_top_cell rv32i_cpu_top -units 1000` (18 s). `scripts/gds_check.py` (own stream reader): 368 structures, **1 top cell**,
0 undefined and 0 empty referenced structures, 10 SRAM instances reference the full-length `sky130_sram_1kbyte_1rw1r_32x256_8` (20,516 own shapes, no rename), **503 pin rectangles (294 met2 0.28x4.0, 209 met3 4.0x0.6) and 503 labels, every label inside a pin rectangle**.
The same checks on the real B5e GDS are listed with the final results.

## Tool gotchas found in this step (for the agent suite)
- `route.common.global_min_layer_mode` / `global_max_layer_mode` default to **soft**: `set_ignored_layers -min_routing_layer` alone does not stop the router (the man page says "the router respects this setting", the default mode makes that "discouraged"). Use `hard`; `allow_pin_connection` lets <= ~5.75 um li1 stubs through.
- Layer attributes set with `set_attribute [get_layers ..] routing_direction` need an open block (ATTR-15), they live in the block, not the .tf: the setup script must be re-sourced after every `open_block`.
- Hard li1 ban makes the first route much worse in macro-gap hot spots; the DRC-aware partition option + global-route effort/macro-boundary utilisation fixed it where 12 plain passes and a rip-up did not.
- `route_eco` after `remove_routes` of 248 violating nets is a regression (1073 DRCs). Rip-up helps only for a handful of nets.
- `write_gds`: `-merge_gds_top_cell <top>` gives one top cell and keeps the SRAM name; `-output_pin all` is the default but the old script overrode it with `text`.
- A stage script that ends with `exit` returns 0 even when its loop did not converge: a chain driver must read the result lines (`REPAIR_FINAL`), not the exit code. `run_chain.sh` ran `06_finish` on an unconverged route for that reason (killed, discarded).
- `safe_run.sh` load gate: with another job using ~5 cores the gate (load < 6, 240 x 30 s) can block a stage for hours; stage timing in `.time` files includes the wait.
- zsh: `[ $(grep -c ... missing_file) -ge 5 ]` -> "unknown condition" when the file does not exist yet; use `"$(...)"` with a default.
- Scripts here: `li1_audit.py` (DEF layer-tracking through via chains; a per-segment layer without following the via chain over-counts), `nwell_islands.py`, `tap_segments.py`, `gds_check.py`, `run_chain.sh`, `finish_chain.sh`.


---

# (B5a text below, unchanged)

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
