# Cadence Innovus place-and-route, Sky130 `rv32i_cpu_top` (steps B5b, B5c)

## B5g: in-place repair of b5f - DRC 0, setup +0.394 ns, PG still one piece per net (antenna 4, not 0)
**Result (Innovus-native, tt, tech-LEF RC; not signoff):** `verify_drc` = 0, setup WNS **+0.394 ns** / TNS 0 / 0 violators (b5f -2.702 / -31.576 / 21), hold WNS **+0.252 ns** / 0 violators (b5f +0.264),
PDN self-check **VPWR 1 piece / VGND 1 piece** (before and after fill), connectivity unchanged vs b5f (144 endcap-VPB "regular opens" + 1 IMPVFC-200, baseline class), antenna **4 violations on 3 clock-tree nets (b5f 5, b5d 1) - NOT zero**.
No re-placement and no CTS: restored the pre-fill post-route database `runs/b5f_innovus/dbs/05_route` into `runs/b5g_innovus` (b5f unchanged); fill/decap re-added by `06_finish`.

**Cause and fix.** The 21 setup violators were all `axi_rdata_i[*]` input ports on the bottom die edge (x up to 2867 um) whose first buffer sits near x~600 um: the port nets were 2-6 mm routed and unbuffered (port slew 3.3 ns,
first `buf_12` stage 13.45 ns, max_cap -0.593 pF); post-route `optDesign` had left them. Fix: `ecoAddRepeater -net <net> -cell sky130_fd_sc_hd__buf_8 -firstSpreadDist 40 -spreadDist 600` on the 28 AXI input nets longer than 2 mm
(`reports/b5g/g_nets.txt`), 232 repeaters kept, then `ecoRoute` and `ecoRoute -fix_drc`. That also rerouted away the b5f met1 short at (8.9, 923). One repeater (`B5G16__inst_131`) could not be legalised and created two new met1 shorts with VPWR/VGND;
`ecoDeleteRepeater` removed it (the wire merges, no timing loss) and a final `ecoRoute` gave DRC 0. An `attachDiode` attempt on the 4 antenna-violating clock-tree pins had no effect (no such instances in the final DEF).
Scripts: `scripts/05g_repair.tcl`, `scripts/05h_fix.tcl`, `scripts/b5g_nets.py`; then `06_finish` (FROM_LABEL=05h_final) and `07_restream` with the fixed map `gds_layer_map.innovus`.

| Metric | b5d | b5f | **b5g** |
|---|---|---|---|
| `verify_drc` | 0 | 1 | **0** |
| VPWR / VGND special pieces | 7 / 6 | 1 / 1 | **1 / 1** |
| Setup WNS (I/O group; reg2reg) | +0.047 | -2.702 (+1.899) | **+0.394 (+1.854)** |
| Setup TNS / violators | 0 / 0 | -31.576 / 21 | **0 / 0** |
| Hold WNS | +0.102 | +0.264 | **+0.252** |
| Antenna | 1 | 5 | **4** (3 clock nets) |
| max_tran / max_cap nets | 122 / 484 | 111 / 457 | 100 / 433 (unrepaired) |
| Power (default activity) | 91.39 mW | 91.65 mW | 92.65 mW |
| Signal wirelength | 6,440,254 um | 6,524,044 um | 6,557,473 um |
| Area incl. macros | 2,254,240 um2 | 2,261,987 um2 | 2,265,508 um2 |

**Not done / caveats.** Antenna is not 0. Conformal LEC (the netlist now has 232 extra buffers vs the Genus netlist), LVS, KLayout/Magic DRC, Quantus/StarRC and the signoff STA were NOT re-run on b5g; all numbers above are Innovus-native.
Outputs: `pnr/commercial/impl/innovus/runs/b5g_innovus/out/` (DEF, logical + PG netlists, SDC, native SPEF, GDS; md5 in `runs/b5g_innovus/SUMMARY.md`). Tracked reports: `pnr/commercial/impl/innovus/reports/b5g/`.

**UPDATE B5d: `verify_drc` = 0 on `runs/b5d_innovus` - see the B5d section; it replaces s2.**

**B5c verdict (superseded by B5d): the flow completes to GDS with timing met at tt but routing DRC is NOT zero: 3 `verify_drc` Metal Short markers remain (B5b: 1,579).**
Routing-DRC verdict: **FAIL (3 markers), not DRC-clean.** Max-tran / max-cap: **FAIL, unrepaired** (115 and 476 nets violating at tt, worst -4.793 ns / -0.649 pF; B5b 122 / 475). All numbers are Innovus-native,
tt, tech-LEF RC (no qrcTechFile; the capTable stop-gap was rejected by Innovus, see B5b notes). Final timing/parasitics are the neutral judge's job. Nothing was LEC'd, LVS'd or opened in KLayout.
The B5b sections further down are kept as the first attempt; the Innovus deliverables are now the **B5c** ones in `pnr/commercial/impl/innovus/runs/b5c_innovus_s2/out/` (`reports/*.txt` were overwritten with the B5c reports;
B5b originals are in git and in `runs/b5b_innovus`).

## B5d: wider keep-out to clear the 3 residual shorts of b5c_innovus_s2 (one run)
**Result: `verify_drc` = 0 ("No DRC violations were found" after route-repair, after post-route opt and on the final database with fill). b5d replaces s2** as the Innovus arm's deliverable, with no material
timing regression; the downstream jobs have to be repointed from `runs/b5c_innovus_s2/` to `runs/b5d_innovus/` (not done here). `b5c_innovus_s2` is untouched.

**Classification of the 3 s2 shorts (from `final_drc.txt`).** All three are Regular-wire vs Regular-wire (signal vs signal): no PG strap and no pin-access short.
(1) met4 at (99.67-99.97, 519.71-520.71): `FE_OFN19220_debug_rs1_data_o_7` vs `FE_OFN20926_axi_wlast_o`, hugging the SW corner of the D-cache tag SRAM (macro edge x=100, y=520; the macro OBS on met3/met4 starts 0.6 um inside its edge);
(2) met3 at (96.7, 685.6): `u_core/FE_OFN22404_n` vs `u_core/FE_OFN18569_n`, 3 um left of the macro edge in the pocket; (3) met4 at (1.23, 580.4): `FE_PDN633_axi_wdata_o_14` vs `FE_OFN19398_n`, the outermost met4 track at the die edge.
Common cause: through-routes squeezed through the 100 um left pocket and its mouth next to the macro edge (the residual of the B5b root cause), not PDN or pins.

**Changes (all in one run, placement/route set-up only; SDC, tt MMMC, tech-LEF RC, PDN and every other script unchanged; `B5D=1` in `03_place.tcl`, rerun from 03_place, floorplan/PDN re-run deterministically):**
1. hard placement blockage widened from x<100 to x<120 (`{100 0 120 917.5}` added): keeps cells off the 100-120 band along the macro edges (shorts 1, 2);
2. 15 % partial placement blockage over the pocket mouth `{0 417.5 300 520}`: thins cells at the junction where short 1 sat;
3. met4 routing blockage `{0 520 3 700}` at the left die edge beside the pocket: keeps the router off the outermost met4 tracks (short 3).
The individual contribution of each change is NOT separated (one run only) and the result is a different placement/route outcome, so no per-change attribution is claimed.

### s2 -> b5d delta
| Metric | b5c_innovus_s2 | **b5d_innovus** | Change |
|---|---|---|---|
| `verify_drc` final | 3 (Metal Short) | **0** | -3 |
| In-flow route repair | NanoRoute 3 -> `ecoRoute` 2 -> opt re-introduced 3 | NanoRoute 2 -> `ecoRoute` 0 -> post-route opt kept 0 | |
| Antenna (`verifyProcessAntenna`) | 1 net / 1 pin | 1 net / 1 pin | same |
| Setup WNS tt (I/O group; reg2reg) | +0.008 ns (+1.408) | **+0.047 ns (+2.022)** | better |
| Hold WNS tt (reg2reg) | +0.115 ns (+2.809) | **+0.102 ns (+2.671)** | -0.013 ns, no violations |
| Setup / hold violating paths, TNS | 0 / 0, 0 | 0 / 0, 0 | same |
| max_tran violating nets (worst) | 115 (-4.793 ns) | **122 (-4.408 ns)** | +7 nets (unrepaired in both) |
| max_cap violating nets (worst) | 476 (-0.649 pF) | **484 (-0.856 pF)** | +8 nets (unrepaired in both) |
| Power (default activity, indicative) | 91.46 mW | 91.39 mW (internal 54.90, switching 36.40, leakage 0.095) | -0.1 % |
| Signal wirelength | 6,592,299 um | **6,440,254 um** (met1 2,129,856; met2 2,102,623; met3 1,672,517; met4 535,258) | -2.3 % |
| Cut vias (report_route) | 307,565 | 301,229 | -2.1 % |
| `report_area` (incl. 1,907,125 um2 macros) | 2,251,218 um2 (~344,093 um2 logic) | 2,254,240 um2 (~347,115 um2 logic) | +0.13 % total, +0.9 % logic |
| diode_2 / conb_1 / taps | 262 / 133 / 63,521 | 252 / 133 / 63,521 | |
| Wall (contended host): place / CTS / route / finish | 9.8 / 8.2 / 5.3 / 3.3 min | 10.9 / 10.1 / 6.3 / 49.0 min (finish ran at host load 13-26) | host contention only |
| Peak RSS (finish) | 6.9 GB | 6.8 GB | |
Routing-DRC verdict: **PASS (0 markers, Innovus `verify_drc`)**. Max-tran / max-cap: **still FAIL, unrepaired** (122 / 484 nets). Caveats unchanged: tech-LEF RC at low-effort extraction (no qrcTechFile), native SPEF not signoff quality, PG/well-pin
connectivity reports saturated by decap/fill well pins (unusable), LEC / Netgen LVS / Magic-KLayout DRC of the b5d outputs NOT RUN by this arm (the downstream jobs own them). Two host power-offs interrupted the run (05_route and 06_finish were resumed from the
saved `05b_repair` / `05_route` databases without re-routing; `05_route` has no `.time` file because its process was killed after the database was saved).

Outputs (`pnr/commercial/impl/innovus/runs/b5d_innovus/out/`): `rv32i_cpu_top.nl.v` (logical), `rv32i_cpu_top.pg.pnl.v` (PG + physical, for LVS), `rv32i_cpu_top.def`, `rv32i_cpu_top.gds`, `rv32i_cpu_top.sdc`,
`rv32i_cpu_top.innovus_native.spef` (tech-LEF RC, NOT signoff). Reports: `reports/b5d/*.txt` (the top-level `reports/*.txt` still hold the s2 copies). Databases: `runs/b5d_innovus/dbs` (final labels `05_route`, `06_finish`).
Reproduce: `TAG=b5d_innovus B5C_STRAP=1 B5D=1 scripts/chain_b5c.sh` (resume after interruption: `scripts/chain_b5d_resume.sh`, then `FROM_LABEL=05_route scripts/run_stage.sh 06_finish b5d_innovus`).

## B5f: PG split fixed at its root (narrow D-cache-column strap keep-out), one run - acceptance NOT met, b5f does NOT replace b5d
**Change (from 02_pdn, run `runs/b5f_innovus`; b5d untouched):** the full-width met4 strap keep-out `{20 495 3580 520}` is replaced (`B5F=1` in `02_pdn.tcl`) by five keep-outs on the D-cache SRAM pin columns only: macro x-extent +-5 um,
y 495-520 (`{95 495 584.78 520} {674.78 495 1164.56 520} {1354.56 495 1844.34 520} {2034.34 495 2524.12 520} {2714.12 495 3203.9 520}`); straps stay continuous through the gaps beside and between the macros (ICC2 also cut only at macros).
All b5d placement screens and the met4 left-edge routing blockage are unchanged; SDC, tt MMMC, tech-LEF RC unchanged. New in 02_pdn: a **PDN self-check** (`verify_connectivity -type special -net` per PG net, counts the "special routes with opens" pieces, prints
`PDN_SELFCHECK ... PASS/FAIL`; the chain stops on FAIL; endcap-VPB/VNB well-pin messages are a different class and ignored). It passed at 02_pdn (VPWR 1 piece, VGND 1 piece). The b5d database measured with the same command gives 7 and 6 pieces, so the check discriminates; I did not re-run a negative control stage.

**Acceptance vs result**
| Criterion | Result |
|---|---|
| `verify_drc` = 0 | **FAIL, 1 marker**: a Metal Short on met1 at (8.9, 923.0), open core at the left die edge at the top of the pocket (`FE_OFN19511_debug_rs1_data_o_4` vs `FE_PDN506_axi_awaddr_o_22`). It is NOT at the D-cache pin edge, so the narrowed keep-out was not too narrow. NanoRoute 2 -> `ecoRoute` 2 -> post-route opt 1... final 1 |
| VPWR / VGND special wiring each ONE piece | **PASS**: 1 piece each (`IMPVFC-200` = 1; was 7 / 6 in b5d) |
| No floating followpin rails | **PASS**: 0 isolated rails (was 5 VPWR + 4 VGND) |
| No material timing/DRV regression vs b5d | **FAIL, setup**: WNS **-2.702 ns**, 21 violating paths, TNS -31.6 (b5d +0.047 ns, 0 paths). Hold fine (+0.264). DRV slightly better |
Per the instructions I stopped here (one run, no iteration).

**Setup failure, cause as far as seen.** All 21 violators are I/O-to-macro/flop paths from `axi_rdata_i[*]` (bottom-edge input pins) to the D-cache SRAM `din0` and the `uncached_rdata` / refill-buffer flops (reg2reg stays +1.899 ns). Path 1 (`axi_rdata_i[30]`): one `FE_OFC7835_axi_rdata_i_30`
`buf_12` has a **13.45 ns stage delay** (a very long or heavily loaded net, i.e. the same unrepaired max-tran/max-cap class that exists in every Innovus run), followed by an inverter-pair chain; pre-opt WNS was -6.405 ns and post-route opt recovered it only to -2.702 ns. This is a
different placement/route/opt outcome from b5d (the PDN change alters every downstream stage), not an effect I can attribute to the PG change itself; the same endpoints met timing in b5b/c/d. The fix would be a DRV/timing repair of that net class (e.g. a max-tran-driven `optDesign -postRoute -drv`), which I did not try.

### b5d -> b5f
| Metric | b5d | **b5f** |
|---|---|---|
| `verify_drc` final | 0 | **1** (met1 short, open core, (8.9, 923.0)) |
| VPWR / VGND special-wire pieces | 7 / 6 | **1 / 1** |
| Isolated followpin rails | 5 VPWR + 4 VGND | **0** |
| VPWR dangling wires / VGND dangling | 168 / 78 | 146 / 66 |
| Endcap VPB patches (VPWR "regular opens", well-pin class) | 144 | 144 (unchanged, harmless) |
| met4 / met5 stripes | 68+70 / 28+28 | 69+70 / 28+28 |
| Setup WNS tt (I/O group; reg2reg) | +0.047 ns (+2.022) | **-2.702 ns**, TNS -31.6, 21 paths (+1.899) |
| Hold WNS tt (reg2reg) | +0.102 ns (+2.671) | +0.264 ns (+2.834) |
| Antenna (`verifyProcessAntenna`) | 1 net / 1 pin | 5 violations / 4 nets |
| max_tran / max_cap violating nets (worst) | 122 (-4.408 ns) / 484 (-0.856 pF) | 111 (-4.416 ns) / 457 (-0.593 pF) |
| Power (default activity) | 91.39 mW | 91.65 mW |
| Signal wirelength | 6,440,254 um | 6,524,044 um (+1.3 %) |
| Cut vias | 301,229 | 304,270 |
| `report_area` incl. macros | 2,254,240 um2 | 2,261,987 um2 (+0.34 %) |
| diode_2 / conb_1 | 252 / 133 | 274 / 133 |
| Wall: place / CTS / route / finish | 10.9 / 10.1 / 6.3 / 49.0 min | 7.7 / 8.3 / 4.6 / 4.3 min (idle host) |
| GDS | fixed map | fixed map: one top cell, 441 structures, 0 unresolved SREFs, 503 pin labels |
**Verdict: b5f fixes the PG topology (the stated root cause) but fails `verify_drc` (1) and setup timing (-2.702 ns), so it does not replace b5d.** b5d keeps DRC 0 and timing met but has the PG split (PG status FAIL); b5f has a connected grid but is not DRC/timing clean.
Candidate next step (needs approval): keep the b5f PDN and repair the two residuals in place on `runs/b5f_innovus/dbs/05_route` - `optDesign -postRoute -drv` (or a targeted resize/buffer of `axi_rdata_i[*]` nets) for the setup paths, then a local `ecoRoute -fix_drc` for the single met1 short.
Outputs: `runs/b5f_innovus/out/` (nl.v, pg.pnl.v, def, gds with the fixed map, sdc, native SPEF), reports `reports/b5f/*.txt`, full PG reports in `runs/b5f_innovus/reports/gdsfix/`. Reproduce: `scripts/chain_b5f.sh`.

## B5d GDS re-stream (no re-route) and PG connectivity check
**GDS map fix (`scripts/gds_layer_map.innovus`; old map kept as `.badmap`, old GDS as `out/rv32i_cpu_top.gds.badmap`).** Diff: (1) removed the six per-layer `LABEL` lines (accepted, wrote no text);
(2) added `VIA` entries on every metal: `li1 VIA 67 20`, `met1 VIA 68 20`, `met2 VIA 69 20`, `met3 VIA 70 20`, `met4 VIA 71 20`, `met5 VIA 72 20` (the via metal enclosure pads); (3) added pin-text lines
`NAME li1/PIN 67 5`, `NAME met1/PIN 68 5`, ... `NAME met5/PIN 72 5`. The PDK `sky130A.map` form `NAME <layer>/LABEL,<layer>/LEFPIN` was tried first and writes NO text for design pins; per the Innovus `streamOut` man
page `NAME <layer>/PIN` labels the top-level IO pins (label datatype 5 = Sky130 convention). `scripts/07_restream.tcl` restores `06_finish` and re-runs only `streamOut` with the same merge settings (hd + SRAM GDS); no routing.
**Verification (own GDSII record reader, no KLayout on this host; old vs new):** one top cell `rv32i_cpu_top`, 437 structures, 0 unresolved SREFs, SRAM master present (unchanged). All 26 generated via cells
(`M1M2_PR`, `M1M2_PR_M/_R/_MR`, `M2M3_PR`, `M3M4_PR`, `M3M4_PR_R`, `rv32i_cpu_top_VIA*` PG stacks) went from cut-only (0 with metal) to cut + metal pads on both adjacent metals (e.g. `M1M2_PR` {68/20, 69/20, 68/44},
`rv32i_cpu_top_VIA8` {71/20, 72/20, 71/44 x2}). Top cell: 503 pin shapes (294 on 69/16, 209 on 70/16) and now 503 pin labels (294 on 69/5, 209 on 70/5), 503 unique names. Routing geometry counts are unchanged.
Not done: KLayout DRC / Netgen LVS of the new GDS (the DRC/LVS agent owns it).

**PG connectivity (Innovus `verify_connectivity`, per net, error cap 1,000,000; `reports/b5d/pg_connectivity_findings.txt`).** Signal-side/regular check of VPWR and VGND: clean. Special (PG) check, noise separated by class:
- Well-pin noise (not a defect): VGND 295,876 "terminal not connected" = `VNB` pwell pins of DECAP/FILL/standard cells (pin has no metal) and 50,912 matching "regular routing opens"; VPWR shows the equivalent only as 144 patches below.
- **Real opens, and Innovus does see them.** VPWR special wires = 7 pieces, VGND = 6: the power grid is split into a lower piece (y 21-496: icache row, pocket) and an upper piece (y 520-1779: logic + dcache), plus **5 isolated VPWR and 4 isolated VGND met1 followpin rails at y 496-521** (no strap, no via) feeding rows that hold 915 logic cells (+8,623 tap/endcap/decap/fill cells).
  Cause: the step-2 PDN change `B5C_STRAP` (met4 strap keep-out `{20 495 3580 520}` across the FULL die width, introduced in b5c_innovus_s2 and inherited by b5d) deletes every met4 strap through that band; ICC2 only cut its straps over the macro footprints. This is a flaw I introduced
  with that change (I assumed the rails would still tie to the straps); it also explains Magic's 153 VPWR components (1 big + 1 other strap piece + 150 small = 144 below + 5 floating rails + 1).
- 144 VPWR "regular opens": 1.76 x 2.83 um patches at x 98.25-100.01, one per VPWR row of the two pockets (y 28-913): the VPB (nwell) pin of the endcap at the right end of the pocket rows, next to the macro edge; well-pin class, no signal impact. 168 dangling VPWR wires (132 met4, 36 met5) and 78 VGND: strap stubs ending at macro/band edges and the ends of the met5 straps at x=20/3580; harmless stubs.
- **Consequence for the verdicts above:** `verify_drc` = 0 stands, but "b5d replaces s2" is NOT a clean PG result: the PG network of s2 and b5d is not connected as designed (two pieces + nine floating rails), so IR/EM, power-aware LVS and any PG-connectivity sign-off on these databases will flag it. Treat the PG status as FAIL.
- **Proposed fix, not applied:** an sroute/addStripe-only change on the 05_route/06_finish database: add a small number of met4 stub straps through the band only where no macro pin or signal wire is nearby (e.g. one VPWR/VGND pair per 100 um at the existing strap x, y 495-523), then `ecoRoute -fix_drc` for local signal repair - no re-placement. A safer alternative is to shrink the keep-out from the full-width band to the dcache pin columns only (x ranges of the five D-cache macros, y 495-520), which needs a rerun from 02_pdn (about 40-60 min on an idle host). Needs your decision; either may disturb the 0-DRC result and must be re-checked with `verify_drc`, `verify_connectivity -type special` and timing.

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

## B5h (2026-10-31): capTable RC + symmetric SDC-visible I/O latency
See `reports/innovus_b5h_report.md`. Native nom_tt: DRC 0, antenna 1, PG 1/1, setup +0.215, hold +0.139, 87.5 mW @0.2 / 70.6 mW @0.1; judge with its own exported SDC: +0.706 / +0.140, PrimePower 69.5 mW. Same 144+1 well-tap opens as b5g.
