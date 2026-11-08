# Innovus b6: full MMMC (ss + tt + ff) place, CTS, route and post-route optimisation from the Genus v1 netlist

Tag `impl/innovus/runs/b6_innovus` (gitignored; tracked copies of the key native reports in `impl/innovus/reports/b6/`). Question: is Innovus's reg-to-reg ss setup loss in the judge (b5k: -7.8 / -7.1 / -8.8 ns at nom/min/max_ss, 848 / 641 / 1064 reg-to-reg violators) caused by P&R being scoped to tt only? The Genus v1 netlist is already +0.61 ns at ss with zero wire load (`synth_ss_probe_step1.md`), so synthesis is not the cause.
Status: measurement, comparison run, no targets; `pd.signoff=false`; every figure indicative (the SRAM Liberty is TT 1.8 V 25 C only in every view, bead `o1i`, so ss and ff time the SRAM-limited cache paths with a TT macro).

## 1. Verdict
**Yes for the reg-to-reg ss loss: with ss and ff views active during place_opt, CCOpt and post-route optimisation, the judge sees ZERO reg-to-reg violations at all 9 corners under all three SDC variants (own, shared, iolat), against -7.1..-8.8 ns and 641..1064 violators on b5k.** Same netlist, same floorplan, same pins, same PDN, same max layer. What remains at ss is I/O: not reg-to-reg, and mostly an artefact of modelling (section 5).
Cost: standard-cell buffers 7,730 -> 15,858 (+105 %), logical cells 34,844 -> 46,187 (+33 %, the ss/hold fixing), instances 462,702 -> 471,051 (+1.8 %, physical cells dominate), PrimePower nom_tt 70.5 -> 76.2 mW (+8 %, combinational +5.6 mW).

## 2. What b6 does (and what it carries over)
| Item | b6 |
|---|---|
| Views | `av_ss` (ss_100C_1v60 + rc_max), `av_tt` (tt_025C_1v80 + rc_nom), `av_ff` (ff_n40C_1v95 + rc_min); setup {ss tt}, hold {ff tt}. RC = `captbl6` nom/min/max (li1->met0 ICT trick, no TC coefficients, temperature 25 for all three as in b5k). `scripts/mmmc_b6.tcl` |
| SRAM lib | `sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib` in all three library sets (bead `o1i`) |
| I/O latency | `set_ccopt_property update_io_latency false` in every stage; virtual `clk_io`, source 1.0, network 3.295 ns (fixed, as b5h..b5k), applied post-CTS by `update_constraint_mode` with the b5k post SDC plus an explicit `-latency_file` on every view (`update_analysis_view`) plus the interactive `set_clock_latency`; probe on the PDN db showed 3.295 in all three views (`scripts/b6_probe.tcl`). SDC family = shared SDC (md5 `3c69635042a9d65cb87e71a9db713e4e`) + clk_io + the 26 mbist input delays (`sky130_cpu_innovus_b6_pre.sdc`, `..._b5k_post.sdc`) |
| Physical setup | die/core, 10 SRAM placements, 503 pins, PDN (B5F keep-outs), max met4, CTS cells clkbuf_2/4/8/16, B5C/B5D placement screens: identical to b5 |
| Taps at source | `02_pdn.tcl` (env `B6=1`): after `addWellTap`, a tap abutting every endcap whose nearest left tap is 0.3..1.0 um away (the nwell.2a slit signature). 293 taps added (b5j ECO: 146 at x=98.44 only; the rule also covers the other macro-edge columns, all one-site gaps). Result on the final DEF: **n-well islands without a tap 0** (`nwell_islands_innovus.py`), no IMPVFC-92 opens, KLayout nwell.2a 0, with no tap ECO |
| Hold | `setOptMode -holdTargetSlack 0.2`, ff view active, post-CTS and post-route; `-fixHoldAllowSetupTnsDegrade false` |
| DRV with hold | one `buf_8` on each of the 111 violating input-port nets before the first post-route pass, then `optDesign -postRoute`, `-hold`, `-drv`; DRC loop after each |
| Round-2 ECOs | KLayout m3.6: 37 pin stubs by `add_shape` (list from the DRAFT finish, `mk_pinstub_list.py`); antenna: 13 `diode_2` by `attachDiode` driven by the OpenROAD `check_antennas` list (`ant_to_pins.py`) + `refinePlace` before `ecoRoute`; npc.2: decap -> fill swap, 21 cells (rule extended, section 6) |
| Primitives | `addInst -physical` (never `create_inst`); one licensed tool at a time under `licensed_lock.sh` + `safe_run.sh`, <= 2 threads |
Flow: `01_floorplan`, `02_pdn`, `03_place` (place_opt, 11 min), `04_cts` (10 min), `05a_route` (3.4 min, **DRC 0 straight out of NanoRoute**), `05m_post` (21 min), DRAFT `06m_finish` -> open decks -> `05m_eco` -> `06m_finish` + `07_restream`. Scripts: `scripts/chain_inn_b6_{a,b,c,d}.sh`, verification `signoff/chain_innb6_all.sh` (resumable, done markers).

## 3. Native trajectory (Innovus, SI on unless noted; "all" = all active views; r2r = reg2reg)
| Point | setup WNS all / r2r | setup viol | hold WNS | note |
|---|---|---|---|---|
| pre-CTS (ideal clocks, ss+tt) | -0.065 / +0.011 | 17 | n/a | place_opt closed ss reg-to-reg |
| post-CTS opt | -2.041 / +0.010 | 8 | +0.199 | the 8 are ss output ports |
| post-route baseline (m0) | -3.506 / -0.389 | 177 | +0.142 | |
| + 111 port repeaters (m1) | -3.171 / -0.260 | | -0.024 | |
| + `optDesign -postRoute` (m2) | -0.147 / -0.016 | | -0.169 | |
| + hold, target 0.2 (m3) | -0.146 / -0.024 | 19 | +0.134 | |
| + `-drv` (m4 = final) | **-0.683 / -0.089** | 30 (r2r 3) | **+0.145** | max_tran nets 63 -> 41 |
| final, SI off | -0.514 / +0.102 | 5 (r2r 0) | +0.197 | |
Final per view (SI off): av_tt setup +2.880 / hold +0.415, av_ss setup -0.514 (`apb_prdata_o_reg[15] -> apb_prdata_o[15]`, ss tree 5.7..6.7 ns against the fixed 3.295 clk_io), av_ff hold +0.197. The `-drv` pass bought max_tran (63 -> 41 nets) but moved the ss output-port setup from -0.146 to -0.683; it was kept (the judge reg-to-reg is clean) rather than restored: a recorded regression on the native ss I/O number, not on the judge. Native DRV left: max_cap 369 nets (160 are SRAM `dout0` pins, bead `o1i`), max_tran 41, max_fanout 209 (CTS buffers).
CTS insertion delay (Avg ID): ss 5.66 early / 6.66 late, tt 3.05, ff 1.95 ns. The imposed clk_io 3.295 is the b5h..b5k value, not this tree's tt mean (3.05), and it is correct for no ss or ff view; every ss/ff I/O figure below carries that model error.
Native power: the Innovus power view is `av_ss` (leakage 0.43 mW against 0.095 at tt), so the native 69.1 mW at activity 0.1 is not comparable with b5k's tt figure; use PrimePower.

## 4. Table b5j / b5k -> b6
| Metric | b5j | b5k | **b6** |
|---|---|---|---|
| Views in P&R | tt | tt (+ ECO-only tt_max, ff) | **ss, tt, ff** |
| untied n-well islands | 0 (ECO, 146 taps) | 0 | **0 (source, 293 taps)** |
| Instances (incl. physical) / buffers | 462,195 / n/a | 462,702 / 7,730 | **471,051 / 15,858** |
| Native verify_drc | 0 | 0 | **0** (0 right after NanoRoute) |
| Native antenna (verifyProcessAntenna) | 1 | 1 | **0** ("No Violations Found") |
| Signoff-deck antenna (OpenROAD, nets) | 10 | 2 | **2** (`u_core/FE_OFN20491_n`, `FE_OFN21807_n`, side area) |
| Native hold WNS | +0.139 | +0.011 | **+0.145** (SI off +0.197) |
| KLayout DRC | 60 | 0 | **0** (draft 38: m3.6 37, npc.2 1) |
| Netgen LVS (GDS) | devices 34,255 = 34,255; nets 35,214 = 35,214 | 34,800 = 34,800; 35,688 = 35,688 | **46,175 = 46,175; 47,113 = 47,113** |
| Magic DRC | not run | not run | **28,320,055 total (ICC2 b6 28,2xx,xxx class): 28,315,092 inside SRAM footprints, 737 straddling, 4,226 outside** (see section 8) |
| Conformal LEC | EQ 4/4 negctl | EQ 4/4 negctl | **EQ 5,597 points (RTL and Genus goldens, +/- 282 diodes), 4/4 negative controls caught** |
| Judge own SDC nom_tt setup / hold | +0.706 / +0.140 | +1.006 / +0.140 | **+2.830 / +0.411** |
| Judge own, nom/min/max_ss setup (viol) | -7.77 / -7.03 / -8.76 | -7.83 (962) / -7.10 (734) / -8.83 (1193) | **+0.177 (0) / +0.260 (0) / -0.050 (4)** |
| Judge own, ss reg-to-reg viol | many | 848 / 641 / 1064 | **0 / 0 / 0** |
| Judge own, nom/min/max_ff hold (viol) | -0.310 (11) / -0.446 (29) / -0.129 (2) | -0.013 (3) / -0.159 (27) / +0.023 (0) | **+0.197 (0) / -0.007 (1) / +0.202 (0)** |
| PrimePower nom_tt (own SDC, 0.1) | 69.5 mW | 70.5 mW | **76.2 mW** |

## 5. Judge (StarRC nom/min/max on the final b6 DEF, PrimeTime X-2025.06, SI off): the 27 runs
Full tables and the Innovus b6 column next to ICC2 b6, ICC2 b5m, Innovus b5k and OpenROAD: `pt_judge_summary.md` section 14.
- **Reg-to-reg: 0 violators in all 27 runs** (setup and hold, 9 corners x own / shared / iolat). b5k had 641..1064 at ss. ICC2 b6 has 3 setup at max_ss and 2..8 hold at nom/max_ff.
- **Own SDC (what Innovus closed against):** nom_tt +2.830 / +0.411; nom_ss +0.177 / +0.113 (0); min_ss +0.260 / +0.396; max_ss -0.050 (4) / -0.254 (3); ff setup +3.6..+3.9; ff hold +0.197 / **-0.007 (1)** / +0.202. The max_ss items are in2reg/in2out paths against the fixed clk_io (`apb_paddr_i[5] -> apb_prdata_o_reg[19]/D`; hold `axi_rdata_i[2] -> u_icache_data_din_q_reg[2]/D`), i.e. the 3.295 vs 6.66 ns tree mismatch, not reg-to-reg. The single min_ff hold item is `u_dcache_wb_tag_q_reg[10] -> axi_awaddr_o[22]` (-0.007): with `holdTargetSlack 0.2` the b5k ff gap (-0.159, 27 violators) is nearly closed; the native-to-PT ff offset (~0.15..0.2 ns) is still there.
- **Shared SDC:** nom_tt +2.455 / -1.929 (455 hold, the unmodelled-I/O-latency effect every Innovus/ICC2 arm shows); ss setup -1.99 (71) / -1.25 (49) / -3.03 (107) are all I/O (`apb_prdata_o[15]`, `axi_wdata_o[8]`), r2r none.
- **Iolat SDC:** nom_tt +3.628 / -0.151 (3); ss hold -1.40 (39) / -1.12 (29) / -1.77 (78) are input holds against a 1.778 ns I/O latency on a 6.66 ns ss tree.
- **Verified inputs, all 27 runs:** SPEF md5 equals the StarRC output of the final DEF (`out/rv32i_cpu_top.def`, 05:52:57; SPEFs 06:23..06:31), netlist md5 `48d9c7657ab7...`, SDC md5 as asserted (own `99df2bf2...`, shared `3c696350...`, iolat `e90bdba8...`), 0 unannotated pin-to-pin nets, clock nets fully annotated, `rc=0`, setup and hold metrics non-empty. Wall 11..12 s per run (47 s with PrimePower at nom_tt), the same as b5k (11 s).
- **Power (PrimePower B, nom_tt):** 76.2 mW (clock network 24.1, combinational 21.3, register 1.8; b5k 70.5 with combinational 15.7).

## 6. Process notes and defects found
- Probe first: `update_constraint_mode` alone already carried clk_io 3.295 into all three views, `update_analysis_view -latency_file` also works; a view created without `-latency_file` is the b5k trap.
- Tap rule over-generalised on purpose: the floorplan-stage island checker cannot prove it (without std cells 474 artefact islands remain), the final DEF can (0).
- npc.2: the b5k rule (mirrored `and2_0` with a decap on its right) left 1 hit on b6 (`and2_0` N with a `decap_12` on its LEFT at (1595.74, 1060.8)). Extended in `06m_finish.tcl` (non-mirrored `and2_0` with a left decap, 11 more cells, 21 in total) and the finish + open decks were re-run; KLayout 38 -> 1 -> **0**. The chain was stopped by me and restarted for this; the first final layout (`out_final_v1`) is superseded and used nowhere.
- Conformal negative control `swap`: the anchor `a211o_1 \u_core/g419910` had been resized to `a211o_2` by the b6 optimisation; `mk_mutant_innovus.py` now accepts `a211o_[12]`. The chain's LEC step first returned rc=2 (all four compares EQUIVALENT, controls aborted on the anchor), the controls were re-run alone (4/4 NOT_EQUIVALENT) and the done marker written by hand.
- Antenna: the 13-diode ECO took the deck count 13 -> 2 nets; the remaining two are side-area violations on long wires (no diode helps), as in b5k.
- Netgen LVS fails top-level pin matching only on the 3 netlist `assign` pairs (`axi_awlen_o[1]`, `axi_arlen_o[1]`, `axi_arburst_o[0]`) and the layout-only VPWR/VGND labels, identical to b5j/b5k.

## 8. Magic DRC (run alone, last, `GUARD_RSS_GB=11`, 24 min, `make ARM=innovus_b6 SRAM_MODE=real mdrc mdrc-class`)
Classified as the ICC2 b6 run was (rule x inside / straddle / outside the SRAM footprints; `drclvs/reports/innovus_b6_magic_drc_real_by_rule.tsv`):
- **Inside the SRAM footprints: 28,315,092**, every rule except nwell.4 is 100 % inside (li.c2, licon.11, diff/tap.1, ... the known PDK SRAM-abstract artifact, bead `45a`); same rule set and the same order of magnitude as ICC2 b6.
- **nwell.4 (the known abstract artifact class): 4,963 = 737 straddling + 4,226 outside.** Of the 4,226 outside: **3,035 are identical to ICC2 b6's 3,035** (long well strips along the SRAM edges, 314.56 x 2.83 um x 1,740, 119.75 x 2.83 um x 319, ...: same geometry, same count), and **1,191 are Innovus-specific and NOT in that class**: tap-sized wells (0.84 x 1.61 um x 855, 2.22 x 1.61, 1.76 x 1.23, ...) at x = 20, 33, 46, 59, 72, 84, 97, 110 um on the 12.9 um tap lattice inside the left pocket (x < 125, y < 920 um, hard placement blockage: only taps and endcaps are there). The straddle count is 737 against ICC2's 592 (+145, unclassified). **ROOT-CAUSED 2026-11-08 (`reports/magic_nwell4_rootcause.md`; supersedes the INFERRED reading that follows):** Magic's LEF std-cell abstracts carry the n-well but no tap contact, so every well is reported; Innovus' pocket is unfilled (1,302 taps + 624 decap_3, no fill), so each tap well is its own island, whereas ICC2 fills it and gets 148 merged strips. With the std cells from the GDS Magic reports 0 `nwell.4` in the pocket; KLayout finds 0 of 3,435 n-well regions without contact. Waiver PROPOSED, not waived. Earlier text: Magic says those pocket tap wells have no metal-connected N+ tap although the island checker (0 untied), KLayout (nwell.2a 0, no tap rule hit) and Netgen (no isolated VPB nets) are clean; INFERRED, not isolated: a Magic reading of the tap-only rows in the blocked pocket (the ICC2 arm has logic cells there and shows none). Not reclassified as waived.
Total outside-SRAM items: 4,963 against ICC2 b6's 3,627.

## 7. Not closed
- ss and ff are timed with a TT SRAM model (bead `o1i`); the cache SRAM paths are therefore not pessimistic at ss.
- clk_io is a single fixed 3.295 ns in all views (mandated). A per-view clk_io (6.66 / 3.05 / 1.95) would remove the ss/ff I/O artefacts in P&R and in the judge; not done.
- Deck antenna 2 nets; max_cap 369 nets (160 SRAM pins); max_fanout 209 (CTS buffers).
- Magic nwell.4: 1,191 pocket tap wells (+145 straddle) root-caused to the LEF-abstract artefact (unfilled pocket; `reports/magic_nwell4_rootcause.md`); waiver PROPOSED, not waived.
- Native-to-judge ff hold offset ~0.15..0.2 ns remains (Innovus max/min capTable vs StarRC).
