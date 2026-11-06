# ICC2 arm, B5e corrective rerun (complete; 1 DRC / 1 short left)

Run `b5e_icc2` (`pnr/commercial/impl/icc2/runs/b5e_icc2/`, gitignored). `b5a_icc2` is untouched. Same netlist (DC-NXT `b3a_dc_tt`), SDC (md5 `3c696350...`), floorplan,
macro placement, pins, PDN, scenario and tool settings as B5a. Three fixes:

1. **Router never on li1** (fixed at the generator): `gen_techfile.py` now emits into `sky130_tech_setup.tcl`
   `set_ignored_layers -min_routing_layer met1 -max_routing_layer met4` and `set_app_options -name route.common.global_min_layer_mode -value hard`
   (new args `--route-min-layer/--route-max-layer`). Root cause confirmed from the man pages: `set_ignored_layers -min_routing_layer` IS the router's global minimum,
   but `route.common.global_min_layer_mode` defaults to `soft` ("discouraged, not forbidden"), so B5a's setting was never enforced. `.tf` is byte-identical (md5 `c845f6d1...`),
   so no NDM rebuild. Vias down to li1 cell pins stay allowed (`number_of_vias_under_global_min_layer` = 1). `reload.tcl` now aborts a stage if the mode is not `hard`.
2. **Tap/endcap**: see "Findings" below (the premise did not hold; the tap stage is unchanged and audited).
3. **GDS**: `write_gds ... -long_names -output_pin all -merge_gds_top_cell rv32i_cpu_top` (06_finish.tcl:67).

## Result (final, 2026-10-29): outputs complete in `runs/b5e_icc2/out/`
Final block: `06_finish` from `05y_repair` (`05z_fix`, a targeted rip-up of the last short, left it at 1 DRC / 1 short after 3 passes and was not saved/used). Lineage: 01 floorplan -> 02 pdn -> 03 place -> 04 cts -> `05x_route` -> `05y_repair` -> 06 finish -> 07 write_verilog.
The host was powered off 10-28 21:50 to 10-29 18:54 mid-run; the design library survived and the run resumed from the saved labels. **ICC2-native numbers, tt/1.80 V/25 C, nominal TLU+, one scenario; not the neutral StarRC->PrimeTime judge.**

| Metric (ICC2 native) | B5a (`b5a_icc2`) | B5e (`b5e_icc2`) | Note |
|---|---|---|---|
| Setup WNS / TNS | -0.0046 / -0.0046 ns (1 path) | **+0.0725 / 0** (0 violating paths) | not a quality claim: ICC2 optimises to ~0 and stops, one run per arm |
| Hold WNS / TNS | +0.0008 / 0 | **+0.0037 / 0** | |
| Routing DRC (`check_routes`) | 0 | **1** (a 0.14 x 0.14 um met1 short, nets `u_core/ex1c_comb[158]` / `u_core/ex1c_ex1b_reg_q[124]`, at (1918.1, 882.9)) | **not clean**: the 8-pass `05y` loop sat at 1 for 4 passes and a targeted rip-up (`05z`) did not move it |
| Shorts (`check_lvs`) / opens | 0 / 0 | **1 / 0** | the same single short |
| Antenna (`check_routes -antenna`) | 0 | 0 | same lenient rule set as B5a (diode_mode 1); the OpenROAD-checker figure on the B5a DEF was 532 nets, not re-measured on B5e |
| li1 routed wire (ICC2 `check_routes`) | 2,587 um (14 signal wires up to 400 um through SRAMs) | **0 um** | |
| li1 audit of the written DEF (`li1_audit.py`) | 2,944 segments / 2,670 um on 2,271 nets, longest 400.5 um | **32 segments / 4.6 um total, longest 0.7 um** (32 nets) | the 32 are sub-micron li1 landing patches at mcon vias (min-area/enclosure), no signal routing; 121,342 mcon vias land on li1 cell pins (B5a 122,122) |
| Routed wirelength | 4,464,228 um | 4,499,456 um (met1 1,098,495; met2 1,473,650; met3 1,284,802; met4 641,933; met5 576) | +0.8 % |
| Vias / contacts | 389,127 | 390,255 | |
| Utilisation | site-row 7.23 %, 37.0 % cells+macros (pre-fill) | site-row 7.22 % (cell area 313,097 um2 + 1,917,876 um2 macros) | |
| Power (tool-native, vectorless) | 55.9 mW (clock network 23.7) | 55.8 mW (dyn 55.7 + leak 0.095; clock network 23.5) | indicative only |
| Max-transition / max-cap violations (`report_constraints`) | 57 / 164 | 121 / 170 | worse on transition; not tuned (comparison run) |
| `check_pg_drc` | the file `final_pg_drc.txt` of B5a lists 189 "shorts on pwell" (the B5a text above says "no errors" for the stage-2 check) | 181 "shorts on pwell"; `check_pg_connectivity`: 0 floating macros/pads/terminals/blocks | the pwell reports are in both runs; not investigated |
| Leaf cells before fill | 34,782 non-physical | 34,731 | |
| Fillers removed for overlapping routed shapes | 428 | **0** (`FILLER_FIX pass 1: 0`) | consequence of no li1 stubs |
| Floating n-well islands (`nwell_islands.py` on the DEF) | 7 (13 cells), confirmed by the Netgen LVS | **0** | 1,053 well regions, every one has a tap; max tap-free stretch 12.88 um |
| Row segments without a tap (02_pdn audit) | 0 of 2,105 | 0 of 2,105 | tap insertion unchanged |
| ICC2 wall (sum of sessions, final lineage) | ~1,780 s (b5a: place 480, cts 732) | 3,660 s (place 818, cts 757, route 271, repair 1,339, finish 426) | B5e ran with the host at load 10-14; not a tool-speed comparison |
| Peak RSS | 3.8 GB (CTS) | 3.9 GB (CTS), 3.5 GB finish | |

Outputs (`runs/b5e_icc2/out/`, gitignored): `rv32i_cpu_top.nl.v` (5.9 MB), `.pg.nl.v` (8.3 MB), `.full.pnl.v` (98.8 MB), `.def` (110.9 MB), `.gds` (79.9 MB), `.sdc`, `.icc2native.spef.tlu_nom_25.spef` (127.9 MB); `fp.def` is the floorplan input.
The netlists are not LEC'd and the GDS is not DRC/LVS'd (downstream steps not run here).
**Not equivalent to a clean route: 1 DRC / 1 short remains** (see above). Whether it matters for the physical check is the DRC/LVS step's call; it is in a congested SRAM-gap column.

### GDS integrity of the real B5e GDS (`scripts/gds_check.py`)
368 structures, **1 top cell** (`rv32i_cpu_top`); 0 undefined and 0 empty referenced structures; 10 SRAM instances reference `sky130_sram_1kbyte_1rw1r_32x256_8` (33 chars, not truncated; 20,516 own shapes);
503 pin-size rectangles (294 met2 0.28 x 4.0 um, 209 met3 4.0 x 0.6 um) and 503 labels (69:5 / 70:5), **all 503 labels inside a pin rectangle**; top-level li1 boundaries 32 (the landing patches).
Layer data type: pin geometry is written on the drawing datatype (69:20 / 70:20), text on 69:5 / 70:5. Only the stream was parsed; it was not opened in KLayout.

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
`05y` final (ICC2 `check_routes`): li1 wire length **0 um**, met5 576 um (the soft max-layer setting, as in B5a: 468 um), 4,500,627 um total, 390,255 contacts. DEF-level li1 audit of the final DEF: see Result.

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
  where they overlapped router li1 pin-access stubs (428 removed in B5a), which breaks n-well abutment. So the island is a consequence of li1 routing, not of tap placement; with no li1 wires the removals vanish (B5e: 0 removed).
  This is verified on the B5e final DEF (result: 0 islands, see Result). No change was made to tap insertion; it is audited in `02_pdn.tcl` (error if any segment has no tap) and the well-island check runs on the final DEF.
- Both floorplans have the die area offset by 3.36 um in y (`DIEAREA ( 0 3360 ) ( 3600000 1803360 )`); the bottom-edge ports at y = 0..4 um are partly outside it (router warnings ZRT-720). Unchanged from B5a (identical floorplan was requested); worth a look in the next floorplan revision.

## GDS write (tested on the B5a block copy, before the rerun)
`write_gds -layer_map ... -merge_files ... -long_names -output_pin all -merge_gds_top_cell rv32i_cpu_top -units 1000` (18 s). `scripts/gds_check.py` (own stream reader): 368 structures, **1 top cell**,
0 undefined and 0 empty referenced structures, 10 SRAM instances reference the full-length `sky130_sram_1kbyte_1rw1r_32x256_8` (20,516 own shapes, no rename), **503 pin rectangles (294 met2 0.28x4.0, 209 met3 4.0x0.6) and 503 labels, every label inside a pin rectangle**.
The real B5e GDS gives the same result (see Result).

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

## B5i: in-place routing ECO on b5e (met1 short + met4 m4.5ab) -- 2026-11-01

Run `pnr/commercial/impl/icc2/runs/b5i_icc2/` (copy of the b5e library; b5e untouched). Base = b5e `05y_repair`, no re-place, no opt. Script `scripts/05i_eco.tcl`:
72 temporary 0.1 um met4 halo blockages on the >3 um PG straps + rip-up/reroute (route_eco, then route_detail incremental) of 61 nets (the 2 shorted nets + 59 nets within 0.4 um of a strap, from `scripts/met4_near_strap.py` and the KLayout marker positions); blockages removed before save.

| | b5e | b5i |
|---|---|---|
| check_routes DRCs / check_lvs shorts / opens / antenna (native) | 1 / 1 / 0 / 0 | **0 / 0 / 0 / 0** (cleared at pass A1; nets rerouted: 61) |
| native setup / hold WNS (tt, own RC) | +0.0725 / +0.0037 | +0.0746 / **-0.0016** (1 path) |
| native power | 55.8 mW | 55.8 mW |
| li1 stubs / n-well islands / GDS pins | 32 / 0 / 503 | 31 / 0 / 503 |
| KLayout DRC | 132 (`m4.5ab`) | **1** (`m4.5ab`) |
| nl.v md5 | 1ee342ed... | 5b3934b4... (differs only in the `Generated on` and `Write Command` header comments; md5 of the rest 69919654... for both; pg.nl.v and full.pnl.v likewise identical) |
| StarRC | `SX-0955` shorted nets warning | no short warning (nom/min/max) |
| judge (shared SDC) nom_tt setup / hold | +0.0855 / -1.2264 | +0.0851 / -1.2282 |

Root cause of m4.5ab: the offending shapes are 0.3 um signal met4 wires and 0.33 um via3 pads 0.365-0.38 um from the 3.1 um PG straps. The ICC2 tech does contain the wide-metal table (`fat_table_threshold 0 3`, `fat_table_parallel_length 0 0.001`, `fat_table_spacing 0.3 0.3 0.3 0.4`, equal to the tech LEF), so the rule is not missing; ICC2 detail route and `check_routes` do not apply it between a signal wire and a PG stripe. The residual KLayout item is at the VGND strap start (1738.69-1741.79, y 942.93, bottom of the lowest met5 stripe) against a via-stack pad edge at y 942.63: a PDN geometry item, not routable.
Met1 short: the net124 jog crossed the comb[158] wire on met1; it did not clear in b5e 05z (3 plain re-routes) but cleared once the 59 neighbouring nets were ripped up together with halo blockages (the router re-solved the region).

### B5i Netgen LVS verdict (GDS-mode Magic extraction vs full.pnl.v, PIN_MODE=none) -- 2026-11-01
| variant | b5e | b5i |
|---|---|---|
| as delivered (`supply1/0` declarations + case-colliding names untouched) | not equal (35,440 vs 35,441 nets; pin matching failed) | not equal (35,441 vs 35,440; pin matching failed) - the known artifacts, same class as b5e |
| `_clean` (supply1/0 removed, case-colliding names made unique) | **not equal** (35,440 vs 35,441: the met1 short merged two nets) | **Circuits match uniquely** (35,441 vs 35,441 nets) |
| `_merged` (clean + isolated well-tie islands renamed VPWR) | not equal (35,440 vs 35,441) | **Circuits match uniquely** (35,441 vs 35,441) |
The b5e net-count difference of one was the met1 short (ex1c_comb[158] x ex1c_ex1b_reg_q[124]); with it gone the layout and netlist agree. Reports: `signoff/drclvs/reports/icc2_b5i_lvsgds{,_clean,_merged}_netgen.rpt.full`.

## B5m: round-2 in-place ECO on b5i (PDN strap trim + antenna diodes + name hygiene) -- 2026-11-02

Run `runs/b5m_icc2/` (copy of the b5i library; b5e, b5i untouched), base label `05i_eco`, script `scripts/05m_eco.tcl`, finish `finish_chain_b5m.sh` (06_finish + `07_write_verilog_m.tcl`).
| step | result |
|---|---|
| P: PDN strap-end trim (user-approved) | the stripe at x 1738.69-1741.79, y 942.93 is the **VPWR** met4 strap (not VGND); its bottom edge raised to y 943.03 (0.1 um, gap to the via-stack pad edge at 942.63 becomes 0.40); check_routes/check_lvs 0/0/0 afterwards; `check_pg_connectivity`: 0 floating wires/vias/cells; `check_pg_drc`: 181 "shorts on pwell", identical to b5i (pre-existing, unchanged). KLayout confirmation: see the b5m KLayout line below |
| A: antenna | OpenROAD `check_antennas` on the b5i DEF: **492 nets / 556 pins** (b5e 488/549). 556 `sky130_fd_sc_hd__diode_2` (one per violating sink pin) placed at the pin's cell row, legalised (0 failures), route_eco + 1 incremental pass: **DRCs 0, shorts 0, opens 0**; setup +0.0746 ns unchanged, hold -1.6 ps -> -3.2 ps (diode load) |
| B: max-transition 135 / max-cap 169 (native tt) | **rejected, not in b5m**: upsizing the 126 violating nets' drivers cut max_transition to 54 and max_cap to 162 but collapsed tt hold from -0.0016 to **-0.205 ns** and left 2 shorts. The violators are the weak ZBUF/ZINV chains the optimiser inserted as hold delay (2.8 ns transitions), so DRV repair and hold are in direct conflict; label `05m_drv` kept for evidence only |
| C: hold fix | **abandoned**: one buffer on the single hold endpoint (`u_ex2_ex_mem_reg_o_reg_mem_wdata_aligned__16_/D`; fixes hold to +2.3 ps in the model) could not be placed legally in that dense site: dlygate4sd1_1 and buf_1 both left cell/rail overlaps (3-4 check_lvs shorts) after `legalize_placement`, and `remove_buffers` of the reverted cell left 1 open + 2 min-area DRCs. b5m therefore keeps tt hold at -3.2 ps (1 path). Multi-corner (ff/ss) hold ECO not attempted: only the tt NDM is linked in this flow (ff/ss NDMs share cell names), no min/max TLU+; the b5e iolat judge shows ff 112-121 and ss 20-44 reg-to-reg hold violators (-0.09 / -0.45..-0.63 ns), far beyond the +0.075 ns tt setup margin without a PrimeTime-ECO flow |
| E: export hygiene | `change_names -rules (net, -case_insensitive)` renamed exactly the 3 case-colliding nets (`u_core/n1435`, `n1438`, `n1439` -> `_0`); `write_verilog -exclude supply_statements`: 0 `supply1/supply0` lines in nl.v / pg.nl.v / full.pnl.v |
Native b5m (label `05m_exp` -> 06_finish): check_routes DRC 0, antenna 0, check_lvs shorts 0 opens 0; setup +0.0746 ns; hold -0.0032 ns (1 path); power 55.8 mW; nl.v md5 86af59b6... (556 ANTDIO diodes added, 3 nets renamed, supply lines removed).
Verification results: see "B5m verification" below.

### B5m verification (all measured 2026-11-02; b5e -> b5i -> b5m)
| check | b5e | b5i | b5m |
|---|---|---|---|
| native check_routes DRC / check_lvs shorts / opens | 1 / 1 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| native setup / hold WNS (tt, ICC2 RC) | +0.0725 / +0.0037 | +0.0746 / -0.0016 | +0.0746 / -0.0032 |
| KLayout DRC (sky130A_mr, same options as LibreLane) | 132 (`m4.5ab`) | 1 (`m4.5ab`, VPWR strap start) | **0** (0 rules violated) |
| signoff antenna (OpenROAD `check_antennas`) | 488 nets / 549 pins | 492 nets / 556 pins | **3 nets / 3 pins** (556 diode_2 added) |
| Netgen LVS, GDS-mode, `_clean` / `_merged` | no match (35,440 vs 35,441) | match uniquely (35,441) | match uniquely (35,441); as delivered also **matches** (no supply1/0, no case collisions) |
| Formality RTL vs ICC2 netlist (with SVF) | EQUIVALENT (97a1307) | cited from b5e (netlist content identical) | **SUCCEEDED**, 6,233 passing, 0 failing; 671 unmatched impl points = the 115 port + 556 antenna diodes; the diode-stripped variant has 0 unmatched and also SUCCEEDED (vs RTL+SVF and vs DC) |
| Formality negative controls | 4/4 | n/a | **4/4 detected** (fwdb_inv, swap x vs DC and vs RTL) |
| StarRC nom / min / max | `SX-0955` shorted-nets warning | no short warning, 3/3 rc=0 | 3/3 complete, rc=0, SPEF `*END` present |
| PrimePower nom_tt (vectorless) | 67.8 mW | 67.8 mW | 67.8 mW (4-digit resolution; diode leakage not visible) |
| nl.v md5 (as written) | 1ee342ed... | 5b3934b4... | 86af59b6... |

Judge (PrimeTime, StarRC SPEFs, setup WNS / hold WNS in ns, (hold violators)). The shared SDC has its known I/O hold artefact (-1.2 ns at nom_tt for all three); the iolat SDC (ICC2's symmetric latency) is the meaningful hold view:

**shared SDC: setup WNS / hold WNS (ns) per corner; hold violators**

| corner | b5e | b5i | b5m |
|---|---|---|---|
| nom_tt | +0.0855 / -1.2264 (521) | +0.0851 / -1.2282 (523) | +0.0853 / -1.2315 (523) |
| nom_ss | -14.3315 / -2.2231 (550) | -14.3333 / -2.2258 (549) | -14.3330 / -2.2319 (549) |
| nom_ff | +3.3352 / -0.7755 (534) | +3.3447 / -0.7768 (533) | +3.3448 / -0.7787 (534) |
| min_tt | +0.2274 / -1.1363 (512) | +0.2272 / -1.1378 (512) | +0.2274 / -1.1411 (512) |
| min_ss | -14.0743 / -2.0721 (547) | -14.0747 / -2.0749 (546) | -14.0745 / -2.0808 (547) |
| min_ff | +3.5241 / -0.7074 (505) | +3.5337 / -0.7085 (505) | +3.5334 / -0.7104 (505) |
| max_tt | -0.3612 / -1.3561 (538) | -0.3625 / -1.3582 (544) | -0.3653 / -1.3612 (545) |
| max_ss | -14.6682 / -2.4058 (555) | -14.6705 / -2.4095 (554) | -14.6702 / -2.4157 (553) |
| max_ff | +3.0773 / -0.8779 (583) | +3.0875 / -0.8793 (586) | +3.0874 / -0.8812 (585) |

**iolat SDC: setup WNS / hold WNS (ns) per corner; hold violators**

| corner | b5e | b5i | b5m |
|---|---|---|---|
| nom_tt | +0.0855 / +0.0013 (0) | +0.0851 / -0.0051 (2) | +0.0853 / -0.0070 (2) |
| nom_ss | -14.3315 / -0.4451 (28) | -14.3333 / -0.4478 (28) | -14.3330 / -0.4539 (29) |
| nom_ff | +3.3352 / -0.0949 (117) | +3.3447 / -0.0999 (115) | +3.3448 / -0.1011 (115) |
| min_tt | +0.2274 / +0.0075 (0) | +0.2272 / +0.0036 (0) | +0.2274 / +0.0019 (0) |
| min_ss | -14.0743 / -0.2941 (20) | -14.0747 / -0.2969 (19) | -14.0745 / -0.3028 (20) |
| min_ff | +3.5241 / -0.0886 (112) | +3.5337 / -0.0926 (112) | +3.5334 / -0.0936 (112) |
| max_tt | -0.3612 / -0.0104 (3) | -0.3625 / -0.0175 (6) | -0.3653 / -0.0196 (6) |
| max_ss | -14.6682 / -0.6278 (44) | -14.6705 / -0.6315 (44) | -14.6702 / -0.6377 (46) |
| max_ff | +3.0773 / -0.1023 (121) | +3.0875 / -0.1102 (121) | +3.0874 / -0.1115 (121) |

**PrimePower nom_tt (vectorless, mW)**: b5e 67.80, b5i 67.80, b5m 67.80

Reading of the table: the like-for-like layout fixes (b5i: met1 short + 131 of 132 `m4.5ab`; b5m: last `m4.5ab`, antenna 556->3, supply/case export hygiene) leave setup within 3 ps of b5e at every corner but **cost hold**: nom_tt iolat hold +1.3 ps (0 violators) -> -5.1 ps (b5i, 2) -> -7.0 ps (b5m, 2), max_tt iolat -10.4 -> -17.5 -> -19.6 ps. The ss/ff hold violators (28-46 ss, 112-121 ff) and the 135/169 max-transition/max-cap violators are unchanged and are left to b6 (user decision); the tt hold regression is the part of those a b6 hold ECO has to absorb.

Magic DRC on b5m: **not run (user decision: b6 only)**. A first attempt was killed by the guard at 9.2 GiB container RSS (cap 9) and a second (cap 11) was stopped on request; no Magic DRC result exists for b5i or b5m. The b5e Magic result (27,738,097 total, `met4.5a/b` 984 outside the SRAM footprints) is the last measured; the `met4.5a/b` items correspond to the KLayout `m4.5ab` that is now 0 on b5m.


---

## B6: ICC2 MCMM arm from the DC v2 (MCMM) netlist -- 2026-11-07

**Comparison run, no target.** Run `runs/b6_icc2/` (gitignored; scripts `scripts/b6_*.tcl`, driver `scripts/b6_chain.sh`, verification driver `signoff/chain_b6_all.sh`, both resumable with done markers). Netlist = DC v2 `syn/dc/runs/b3c_dc_mcmm` (md5 `ffe468f2...`, Formality 6,233/0 with 4/4 negative controls), SDC = shared `sky130_cpu.sdc` (md5 `3c696350...`, asserted in the log), floorplan / 10 SRAM placements / 503 pins / PDN / max layer met4 / CTS cells clkbuf_2/4/8/16 / taps+endcaps identical to b5. **The 10 SRAM `.db` is TT 1.8 V 25 C only in every scenario (bead `o1i`)**: the ss and ff scenarios time the SRAM-limited paths (cache `*_dout_r`, tag) with a TT macro, so ss is not pessimistic on them, in ICC2 and in the PrimeTime judge alike.

### What changed vs b5m
1. **MCMM, with the ss/ff/tt cell-name clash solved at the library level.** Linking `sky130_hd_{tt,ss,ff}.ndm` together binds every instance to the first library (`Library has 1 pane`, `PVT-030` voltage/temperature mismatches at ss and ff, measured in `b6_03a_mcmmtest`): ICC2 has no per-scenario link library. The mechanism that works is **one reference NDM with three PVT panes**: `pdk/sky130/scripts/build_ndm_mcmm.tcl` reads LEF once and `read_db` of the tt, ss and ff `.db` into one `icc2_lm_shell` workspace (`check_workspace -allow_missing`; without it the check fails on 316 missing arcs, all of them `clock_pulse_width_*` / `clock_gating_pulse_width_low` checks that exist in only some corners, 0 delay/setup/hold arcs). Each corner then selects its pane with `set_process_number 1 / set_voltage {1.6|1.8|1.95} / set_temperature {100|25|-40}`; the SRAM cells are pinned to 1.8 V / 25 C / process 1. Result: `PVT-032 no PVT mismatches` in all three corners, and per-scenario `report_timing -scenarios` differs (floorplan probe: hold ff -0.013 ns, tt +0.110 ns).
2. **Scenarios**: `func_ss` (setup, max TLU+ 100 C), `func_tt` (setup + hold, nom TLU+ 25 C), `func_ff` (hold, min TLU+ -40 C); max-transition / max-capacitance enforced at ss and tt; power at tt; the same SDC read unchanged into each. Mapping equals `pdk/sky130/scripts/mmmc.tcl` and DC v2.
3. **b5 fixes applied up front, not as ECOs**: `route.common.global_min_layer_mode hard`; strap-end trim (b5m section P) and 72 met4 halo routing blockages (0.1 um, all PG straps wider than 3 um) created in the PDN stage and kept through CTS and routing (they are removed in the ECO stage); `change_names -case_insensitive` + `write_verilog -exclude supply_statements` in the export (0 `supply1/supply0` lines in nl.v / pg.nl.v / full.pnl.v); route.global.effort high + macro-boundary track utilisation 60 + DRC-aware partitioning from b5x from the first route; antenna diodes taken from OpenROAD `check_antennas` (not the lenient ICC2 rule).
4. **Hold by the optimiser with all views active, no tt-only hold ECO**: `place_opt`, `clock_opt` and `route_opt` ran with ff+tt hold and ss+tt setup+DRV together; the hold cell set is restricted by `set_lib_cell_purpose` to real delay cells (`dlygate*`, `dlymetal*`, `clkdlybuf*`; 106 inserted: clkdlybuf4s25_1 61, clkdlybuf4s50_1 16, dlygate4sd1_1 15, dlymetal6s2s_1 14). Post-CTS and post-route ff hold was 0.00 with 0 violators; the b5m failure mode (upsizing the weak buffer chains lost hold) did not arise. No DRV upsizing ECO was run.

### Route convergence (check_routes DRC / shorts / opens; shorts exclude the artefact between a halo blockage and the strap it covers)
| step | b5e | b6 |
|---|---|---|
| after `route_auto` | 266 DRC (05x) | 3 / 570 / 114 opens |
| after `route_opt` | 231 / 347 | **2 / 4 / 0** |
| after the repair loop (10 passes) | 1 / 1 (8 passes) | 1 / 2 / 0 (stuck from pass 1) |
| residual | met1 short at (1918, 883), x 1900-1960 d-cache macro gap | met2 short `HFSNET_4041` x `HFSNET_6006` at (1916.3, 879.2): a 620 um repeater net runs on met2 across the access point of `u_core_u_dcache/U895/B1` (same macro-gap column) |
| fix | b5i: rip-up of 61 nets with halos | **ECO section S4**: `set_routing_rule -min_routing_layer met3 -min_layer_mode allow_pin_connection` on the long net + rip-up/reroute of 37 neighbours -> 0 / 0 / 0 (plain rip-up of the two nets, then of the nets within 4 um, did not move it) |
The up-front halos + global-route settings took the first-route count from 291 DRC / 439 shorts (b5e, li1 ban only) to 2 / 4 after `route_opt`.

### b5m -> b6 table
ICC2-native numbers are tool-native (own RC); the judge rows are PrimeTime on StarRC SPEFs (not native). b5m: single tt scenario; b6: three scenarios.
| Metric | b5m | b6 |
|---|---|---|
| Synthesis netlist | DC v1 (tt only, ss -10.46 ns zero-wire) | DC v2 MCMM (ss +1.16 ns zero-wire); 35,644 cells |
| Scenarios / TLU+ | 1 (tt) / nom | 3 (ss tt ff) / max nom min, 3-pane NDM |
| Native setup WNS (ns) | +0.0746 (tt) | ss **-0.0225** (3 paths, TNS -0.040); tt +3.344 |
| Native hold WNS (ns) | -0.0032 (tt, 1 path) | ff **+0.0029**; tt +0.111 |
| Native route DRC / shorts / opens / antenna | 0 / 0 / 0 / 0 | **0 / 0 / 0 / 0** (630 + 11 + 4 antenna diodes, 115 port diodes) |
| Native max-transition / max-cap violators | 135 / 169 (tt) | tt 2 / 159; ss 113 / 160 (about 155 are the 10 SRAM macro `dout0` nets against the 0.03 pF pin limit, not tuned) |
| Native power (vectorless, tt) | 55.8 mW | 57.9 mW dynamic + 0.095 leakage |
| Clock (post-CTS) | global skew 1.08 ns tt | 5,304 sinks, 8 levels, 408 repeaters; global skew ff 0.49 / tt 0.74 / ss 1.37 ns; max latency 1.37 / 2.09 / 3.80 ns |
| Wall (tool, host idle) | ~3,660 s total at load 10-14 | place 1,515 s, CTS 1,412 s, route 512 s, ECO 4 + 2 + 1.5 min, finish 146 s; peak RSS 4.1 GB (CTS) |
| KLayout DRC (sky130A_mr.drc) | 0 | **0** (2 `m1.7` after ECO round 1 were re-routed away) |
| Deck antenna (OpenROAD `check_antennas`) | 3 nets / 3 pins | **1 net / 1 pin** (`u_core_u_dcache/n3594` -> `data_dout_r_reg_2__26_/D`, survives 3 extra diodes; **not closed**) |
| Netgen LVS, GDS-mode (as delivered / clean / merged) | match uniquely x3 | match uniquely x3 (41,741 nets each side) |
| Formality RTL+SVF v2 vs netlist; vs DC v2 netlist | 6,233 pass / 0 fail | 6,233 pass / 0 fail, 0 unmatched with diodes stripped (760 unmatched = port/antenna diodes in the as-delivered variant) |
| Negative controls | 4/4 | **4/4** detected: `fwdb_inv` 1 failing point (vs DC and vs RTL), `swap` 43 failing points (vs DC and vs RTL) |
| StarRC | nom/min/max | nom/min/max, annotation gate: 0 unannotated pin-to-pin nets |
| Magic DRC | not run | see "Magic DRC" below |

### Neutral judge (PrimeTime + StarRC), ICC2 b6 next to b5m, Innovus b5k and OpenROAD
Cells are `setup WNS ns (violators) / hold WNS ns (violators)`; judge SDC variants: `base` = shared SDC (md5 `3c696350...`), `iolat` = comparison-only `sky130_cpu_iolat.sdc` (virtual I/O clock; removes the I/O-port hold artefact), `own` = the arm's own exported SDC (ICC2 b6: `func_tt` written SDC, md5 `44ce62ce...`; no own file for b5m / OpenROAD). 27 runs per arm and variant set: 9 corners x 3 variants for b6, all `rc=0`. Generated by `signoff/pt/scripts/table_b6.py`.

### SDC variant `base`: setup WNS ns (violators) / hold WNS ns (violators)

| corner | ICC2 b6 | ICC2 b5m | Innovus b5k | OpenROAD |
|---|---|---|---|---|
| nom_tt | +3.314 (0) / -1.230 (556) | +0.085 (0) / -1.232 (523) | -0.594 (3) / -2.224 (510) | +3.172 (0) / -0.319 (51) |
| nom_ss | -1.594 (12) / -2.234 (577) | -14.333 (1356) / -2.232 (549) | -8.484 (948) / -3.792 (548) | -3.426 (1062) / -0.800 (121) |
| nom_ff | +4.015 (0) / -0.780 (374) | +3.345 (0) / -0.779 (534) | +2.242 (0) / -1.477 (241) | +3.928 (0) / -0.136 (8) |
| min_tt | +3.505 (0) / -1.145 (544) | +0.227 (0) / -1.141 (512) | +0.120 (0) / -2.068 (526) | +3.548 (0) / -0.174 (5) |
| min_ss | -1.079 (7) / -2.107 (571) | -14.074 (1201) / -2.081 (547) | -7.513 (723) / -3.571 (574) | -2.777 (800) / -0.588 (78) |
| min_ff | +4.165 (0) / -0.722 (325) | +3.533 (0) / -0.710 (505) | +2.814 (0) / -1.367 (336) | +4.066 (0) / -0.015 (3) |
| max_tt | +3.028 (0) / -1.345 (570) | -0.365 (26) / -1.361 (545) | -1.640 (4) / -2.424 (457) | +2.679 (0) / -0.522 (169) |
| max_ss | -2.268 (26) / -2.412 (586) | -14.670 (1619) / -2.416 (553) | -9.759 (1189) / -4.085 (545) | -4.326 (1207) / -1.071 (155) |
| max_ff | +3.774 (0) / -0.865 (441) | +3.087 (0) / -0.881 (585) | +1.396 (0) / -1.627 (163) | +3.713 (0) / -0.307 (43) |

reg-to-reg (r2rx) worst setup / hold, ns (violators):

| corner | ICC2 b6 | ICC2 b5m | Innovus b5k | OpenROAD |
|---|---|---|---|---|
| nom_tt | none (0) / none (0) | none (0) / -0.007 (2) | none (0) / none (0) | none (0) / none (0) |
| nom_ss | none (0) / none (0) | -14.333 (1320) / none (0) | -7.833 (848) / none (0) | -3.426 (987) / none (0) |
| nom_ff | none (0) / -0.004 (2) | none (0) / -0.101 (115) | none (0) / none (0) | none (0) / none (0) |
| min_tt | none (0) / none (0) | none (0) / none (0) | none (0) / none (0) | none (0) / none (0) |
| min_ss | none (0) / none (0) | -14.074 (1173) / none (0) | -7.099 (641) / none (0) | -2.777 (761) / none (0) |
| min_ff | none (0) / none (0) | none (0) / -0.094 (112) | none (0) / none (0) | none (0) / none (0) |
| max_tt | none (0) / none (0) | -0.365 (26) / -0.020 (6) | none (0) / none (0) | none (0) / none (0) |
| max_ss | -0.059 (3) / none (0) | -14.670 (1563) / none (0) | -8.829 (1064) / none (0) | -4.326 (1122) / none (0) |
| max_ff | none (0) / -0.027 (8) | none (0) / -0.112 (121) | none (0) / none (0) | none (0) / none (0) |

nom_tt PrimePower total (raw `Total` row tail, W): ICC2 b6 70.8 mW; ICC2 b5m 67.8 mW; Innovus b5k 70.5 mW; OpenROAD 93.1 mW

### SDC variant `iolat`: setup WNS ns (violators) / hold WNS ns (violators)

| corner | ICC2 b6 | ICC2 b5m | Innovus b5k | OpenROAD |
|---|---|---|---|---|
| nom_tt | +3.314 (0) / +0.114 (0) | +0.085 (0) / -0.007 (2) | +1.184 (0) / -0.446 (5) | +3.123 (0) / +0.526 (0) |
| nom_ss | +0.184 (0) / -0.456 (42) | -14.333 (1378) / -0.454 (29) | -7.833 (940) / -2.014 (81) | -3.426 (1014) / +0.978 (0) |
| nom_ff | +4.015 (0) / -0.004 (2) | +3.345 (0) / -0.101 (115) | +4.020 (0) / +0.022 (0) | +3.928 (0) / +0.243 (0) |
| min_tt | +3.505 (0) / +0.115 (0) | +0.227 (0) / +0.002 (0) | +1.898 (0) / -0.290 (1) | +3.186 (0) / +0.542 (0) |
| min_ss | +0.699 (0) / -0.329 (31) | -14.074 (1199) / -0.303 (20) | -7.099 (727) / -1.793 (71) | -2.777 (788) / +1.190 (0) |
| min_ff | +4.165 (0) / +0.003 (0) | +3.533 (0) / -0.094 (112) | +4.420 (0) / +0.020 (0) | +4.066 (0) / +0.250 (0) |
| max_tt | +3.028 (0) / +0.112 (0) | -0.365 (26) / -0.020 (6) | +0.138 (0) / -0.646 (15) | +3.019 (0) / +0.495 (0) |
| max_ss | -0.490 (5) / -0.634 (66) | -14.670 (1707) / -0.638 (46) | -8.829 (1166) / -2.307 (96) | -4.326 (1155) / +0.707 (0) |
| max_ff | +3.774 (0) / -0.027 (8) | +3.087 (0) / -0.112 (121) | +3.174 (0) / +0.023 (0) | +3.713 (0) / +0.212 (0) |

reg-to-reg (r2rx) worst setup / hold, ns (violators):

| corner | ICC2 b6 | ICC2 b5m | Innovus b5k | OpenROAD |
|---|---|---|---|---|
| nom_tt | none (0) / none (0) | none (0) / -0.007 (2) | none (0) / none (0) | none (0) / none (0) |
| nom_ss | none (0) / none (0) | -14.333 (1320) / none (0) | -7.833 (848) / none (0) | -3.426 (987) / none (0) |
| nom_ff | none (0) / -0.004 (2) | none (0) / -0.101 (115) | none (0) / none (0) | none (0) / none (0) |
| min_tt | none (0) / none (0) | none (0) / none (0) | none (0) / none (0) | none (0) / none (0) |
| min_ss | none (0) / none (0) | -14.074 (1173) / none (0) | -7.099 (641) / none (0) | -2.777 (761) / none (0) |
| min_ff | none (0) / none (0) | none (0) / -0.094 (112) | none (0) / none (0) | none (0) / none (0) |
| max_tt | none (0) / none (0) | -0.365 (26) / -0.020 (6) | none (0) / none (0) | none (0) / none (0) |
| max_ss | -0.059 (3) / none (0) | -14.670 (1563) / none (0) | -8.829 (1064) / none (0) | -4.326 (1122) / none (0) |
| max_ff | none (0) / -0.027 (8) | none (0) / -0.112 (121) | none (0) / none (0) | none (0) / none (0) |

nom_tt PrimePower total (raw `Total` row tail, W): ICC2 b6 70.8 mW; ICC2 b5m 67.8 mW; Innovus b5k 70.5 mW; OpenROAD 93.1 mW

### SDC variant `own`: setup WNS ns (violators) / hold WNS ns (violators)

| corner | ICC2 b6 | ICC2 b5m | Innovus b5k | OpenROAD |
|---|---|---|---|---|
| nom_tt | +3.314 (0) / -1.230 (556) | n/a | +1.006 (0) / +0.140 (0) | n/a |
| nom_ss | -1.594 (12) / -2.234 (577) | n/a | -7.833 (962) / -0.497 (1) | n/a |
| nom_ff | +4.015 (0) / -0.780 (374) | n/a | +2.673 (0) / -0.013 (3) | n/a |
| min_tt | +3.505 (0) / -1.145 (544) | n/a | +1.315 (0) / +0.139 (0) | n/a |
| min_ss | -1.079 (7) / -2.107 (571) | n/a | -7.099 (734) / -0.276 (1) | n/a |
| min_ff | +4.165 (0) / -0.722 (325) | n/a | +3.020 (0) / -0.159 (27) | n/a |
| max_tt | +3.028 (0) / -1.345 (570) | n/a | +0.456 (0) / +0.140 (0) | n/a |
| max_ss | -2.268 (26) / -2.412 (586) | n/a | -8.829 (1193) / -0.790 (5) | n/a |
| max_ff | +3.774 (0) / -0.865 (441) | n/a | +2.154 (0) / +0.023 (0) | n/a |

reg-to-reg (r2rx) worst setup / hold, ns (violators):

| corner | ICC2 b6 | ICC2 b5m | Innovus b5k | OpenROAD |
|---|---|---|---|---|
| nom_tt | none (0) / none (0) | n/a | none (0) / none (0) | n/a |
| nom_ss | none (0) / none (0) | n/a | -7.833 (848) / none (0) | n/a |
| nom_ff | none (0) / -0.004 (2) | n/a | none (0) / none (0) | n/a |
| min_tt | none (0) / none (0) | n/a | none (0) / none (0) | n/a |
| min_ss | none (0) / none (0) | n/a | -7.099 (641) / none (0) | n/a |
| min_ff | none (0) / none (0) | n/a | none (0) / none (0) | n/a |
| max_tt | none (0) / none (0) | n/a | none (0) / none (0) | n/a |
| max_ss | -0.059 (3) / none (0) | n/a | -8.829 (1064) / none (0) | n/a |
| max_ff | none (0) / -0.027 (8) | n/a | none (0) / none (0) | n/a |

nom_tt PrimePower total (raw `Total` row tail, W): ICC2 b6 70.8 mW; ICC2 b5m -; Innovus b5k 70.5 mW; OpenROAD -


Reading the judge:
- **ss is where MCMM pays.** With the iolat SDC b6 closes `nom_ss` at +0.184 ns (0 violators) against -14.33 ns for b5m (1,378 violators), -7.83 Innovus b5k and -3.43 OpenROAD; `min_ss` +0.699; `max_ss` -0.490 (5 violators) against -14.67 / -8.83 / -4.33. b6 is the best of the four at every ss corner. The base-SDC ss figures (-1.59 nom, -2.27 max) are I/O-port paths with the 0-latency I/O artefact; reg-to-reg ss is clean at nom and min and -0.059 ns (3 endpoints) at `max_ss`.
- tt / ff setup is large positive (tt +3.0 to +3.5 ns): the netlist is ss-sized, so tt carries unused slack (not a quality claim; b5m optimised to ~0 at tt).
- **Hold**: tt hold is clean with iolat (+0.114 / +0.115 / +0.112); ff hold is -0.004 (2 endpoints, nom) and -0.027 (8, max), min_ff +0.003. **ss hold fails** (nom -0.456, 42 endpoints; max -0.634, 66): ss was a setup-only scenario, as in the mmmc definition (hold on ff and tt only), and the judge checks ss hold; all ss hold violators are I/O-port paths (reg-to-reg ss hold: none). Not repaired.
- **Power (PrimePower, nom_tt, vectorless)**: b6 70.8 mW, b5m 67.8, Innovus b5k 70.5, OpenROAD 93.1 mW (comparison run, no budget). b6 is +3 mW over b5m (+10 % std-cell area from DC v2 and 4,364 vs 1,230 optimiser buffers, mostly the ss-driven `ZBUF_`/`ZINV_` buffering).

### Not closed / caveats
- Deck antenna 1 net / 1 pin (OpenROAD checker); ICC2's own antenna check is 0 (lenient rule). Innovus b5k is at 2.
- Native ss setup -0.0225 ns (3 paths) was left; the judge's ss result differs (StarRC max RC + the TT SRAM model).
- Max-cap (about 155 SRAM-output nets) and ss max-transition (113) were not tuned (comparison run).
- ss hold fails on I/O ports in the judge (above); ss is not a hold scenario.
- Wire-load: none; native numbers use the tool's own RC (TLU+ from the tuned-ITF generation, not correlated with StarRC for sign-off purposes: `starrc_extraction_summary.md` WARN applies, all numbers are **indicative**).
- ECO history of this run: first pass `06_eco` (0/0/0), deck found 2 KLayout `m1.7` + 11 antenna pins -> `06b_eco2` (5 nets re-routed, 11 diodes) -> deck 2 antenna pins -> `06c_eco3` (2 more diodes on each) -> deck 1 antenna pin. Verification of the passes superseded earlier ones is in `signoff/chain_b6_pass1`, `chain_b6_pass2`; the reported numbers are all from the final pass (`06c_eco3` -> `07_finish`).
