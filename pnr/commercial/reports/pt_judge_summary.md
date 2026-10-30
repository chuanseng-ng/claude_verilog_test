# Neutral PrimeTime / PrimePower judge, Sky130 `rv32i_cpu_top` (task B6)

**Pass label: UNTUNED ITF.** Every timing and power number below uses the StarRC SPEFs extracted with the authored, uncalibrated ITF
(`starrc_extraction_summary.md`: correlation vs OpenRCX fails the gate at nom and max, both labelled **INDICATIVE**; min passes the median test only by cancellation).
The extraction agent is regenerating the SPEFs with a tuned ITF; this pass reads the frozen copies in
`pnr/commercial/signoff/starrc/runs/_superseded_untuned/`. **Re-run on the tuned SPEFs with one command: `make -C pnr/commercial/signoff/pt rejudge`** (reads the
current `starrc/runs/*` SPEFs fresh, snapshots them with md5, reruns only what changed; output `runs/`, `reports/current/`).

**Comparison run, not a closure run.** No ECO, no netlist or SDC modification. Judge engine: PrimeTime X-2025.06 (`pt_shell`) with PrimePower.
**Innovus is PENDING**: `impl/innovus/runs/b5c_innovus/out/` is empty and no `innovus_<corner>` SPEFs exist. One command adds it once they do:
`make -C pnr/commercial/signoff/pt innovus` (it is part of `judge` and `rejudge` and prints PENDING until then).

Status per the orchestrator contract: stage `multi_corner_analysis` **WARN** (measurement complete for OpenROAD and ICC2, annotation gate PASS on all 27 runs;
the results are a measurement, not a sign-off, and no sign-off criterion is met by either arm); `sta.signoff=false`, `sta.judged_by="signoff"` (PrimeTime on StarRC),
`sta.engine="pt_shell X-2025.06"`, `sta.sdc_md5=3c69635042a9d65cb87e71a9db713e4e`.

## 1. Conditions (what makes the comparison fair, and where it is not)

| Item | Value |
|---|---|
| SDC | `pnr/sky130/cpu/constraints/sky130_cpu.sdc`, md5 `3c69635042a9d65cb87e71a9db713e4e`, asserted inside every `pt_shell` run (abort on mismatch) and recorded in each run's `inputs.txt`. The tools' written SDCs were not used (differences in section 6) |
| PT settings (identical for every arm) | `set_propagated_clock [all_clocks]` after `read_sdc`; no derate/OCV/POCV; `si_enable_analysis false` (OpenSTA has no SI); CRPR on (PT default in X-2025.06, as OpenSTA); `read_parasitics -format spef` with default options (coupling caps lumped to ground at factor 1.0, "Reduced coupling capacitances" in the log); pin caps from the library (the SPEFs are `PIN_CAP NONE`); `set_host_options -max_cores 2` |
| Libraries | `sky130_fd_sc_hd` `.db` tt_025C_1v80 / ss_100C_1v60 / ff_n40C_1v95 (`pdk/sky130/build/db`) + **the SRAM macro `.db` at TT 1.8 V 25 C for every corner (bead `o1i`: TT-only SRAM model; the ss and ff results below therefore time the SRAM at TT)** |
| Corner pairing | 9 = RC {nom,min,max} x lib {tt,ss,ff}; label `<rc>_<lib>` = LibreLane's `nom_tt_025C_1v80 ... max_ff_n40C_1v95`. LibreLane pairs RC and lib independently (e.g. `max_ss` = ss lib + max SPEF), as here. Unlike a conventional setup-slow/hold-fast pairing, all 9 combinations are reported for both setup and hold |
| Parasitics | StarRC X-2025.06-SP1 SPEF per arm and RC corner (md5s in section 2); **authored ITF, single 25 C temperature for all corners, uniform dielectric scaling for min/max** |
| Netlists | OpenROAD `pnr/commercial/runs/openroad/rv32i_cpu_top.nl.v` (md5 `a0f0731993ea3e6a5422e2579810f1e5`; the logical variant, whose net names match the DEF/SPEF; `.pnl.v` only adds `VPWR`/`VGND`); ICC2 `impl/icc2/runs/b5a_icc2/out/rv32i_cpu_top.nl.v` (md5 `e9150655c154779119d823b4222358d5`). The OpenROAD netlist contains tap/fill/decap cells that are not in the `.db` (`sky130_ef_sc_hd__decap_12`, `fill_1/2`, `tapvpwrvgnd_1`): PT black-boxes them (LNK-005/043 warnings, no connections, no timing effect). The 64,096 "no-function" cells in that arm are the 64,086 heuristic diodes + 10 SRAMs |
| Netlists differ by construction | OpenROAD = Yosys/ABC netlist, ICC2 = DC-NXT netlist, different cell counts and placement/CTS. Results compare the *implementations as judged*, not the P&R tools in isolation |
| Host | one `pt_shell` at a time under `safe_run.sh`, 2 threads, 6 GB cap, process-group kill; each run 8-43 s wall, 1.0-1.3 GB RSS. No bare `timeout` |

## 2. Inputs and annotation gate

Gate (skill `multi_corner_analysis` rule 2): **PASS on all 27 runs.** "p2p" = nets with a driver and at least one load; the gate is `> 1 %` p2p unannotated or any clock net unannotated.

| Arm | netlist nets | p2p nets | p2p unannotated | clock nets | clock unannotated | loadless / driverless nets (no timing arc, not counted) | SPEF nets not in netlist |
|---|---:|---:|---:|---:|---:|---|---:|
| OpenROAD (StarRC) | 42,611 | 42,196 | 0 | 913 | 0 | 415 / 0 | 0 |
| ICC2 (StarRC) | 35,637 | 35,141 | 0 | 410 | 0 | 359 / 137 | 8 (`_dummynet0..7`, PARA-124 x16, no pins, harmless) |
| OpenROAD (OpenRCX SPEF) | 42,611 | 42,196 | 0 | 913 | 0 | 415 / 0 | 0 |

SPEF snapshot md5s (each run copies its SPEF into `runs_untuned/<tag>/spef/` and checks the md5 before and after the copy; recorded in `runs_untuned/<tag>/inputs.txt` and in `reports/untuned/judge_results.json`):

| Arm | nom | min | max |
|---|---|---|---|
| OpenROAD StarRC (untuned) | `e4decacbe1ff8ef76bc8882a9c1614c1` | `e9cab9ea3821814f1939cefd3bc8b2c6` | `afd0054fc546717cc2e223cc5750d5db` |
| ICC2 StarRC (untuned) | `bc2b889a3cdb866e91793e2873919063` | `d858f034023cbde6727c0b928c0aa73a` | `3543223c4cfa5eba039b9a94093b431d` |
| OpenROAD OpenRCX (the flow's own SPEFs, unchanged by the tuning) | `3cbabd15466ec03a232846811dac4f89` | `422555b4836b029080afc87823e8a873` | `9bc424693c8a495ad319dc7b0c77e06c` |

(An earlier mixed batch, in which the extraction agent replaced the OpenROAD/ICC2 nom SPEFs mid-run, was discarded; it was deleted and is superseded by this pass.)

## 3. Nine-corner results (PrimeTime on StarRC, untuned ITF)

Setup/hold WNS and TNS in ns; "viol" = unique violating endpoints, in brackets (reg->reg / I/O) from PT's `report_global_timing` categories (I/O = in->reg + reg->out + in->out, so an endpoint
can appear in both an r2r and an I/O count). max_tran / max_cap = violating **pins** (`report_constraint`, library + SDC limits). Full tables with r2r and I/O WNS/TNS split, annotation counts, wall and RSS:
`pnr/commercial/signoff/pt/reports/untuned/{openroad,icc2,openroad_rcx}_9corner.txt`.
**nom and max rows are INDICATIVE (extraction correlation gate failed); SRAM is TT-only at every corner (o1i).**

#### OpenROAD (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +3.0493 | 0.000 | 0 (0 / 0) | -0.3470 | -4.579 | 62 (0 / 62) | 4143 | 271 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| nom_ss_100C_1v60 | -3.6789 | -1466.222 | 1130 (1055 / 75) | -0.8225 | -27.928 | 124 (0 / 124) | 58696 | 295 | `_51961_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.8917 | 0.000 | 0 (0 / 0) | -0.1524 | -0.673 | 9 (0 / 9) | 1584 | 265 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.6856 | 0.000 | 0 (0 / 0) | -0.0347 | -0.035 | 1 (0 / 1) | 1643 | 250 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_ss_100C_1v60 | -2.1167 | -448.660 | 645 (641 / 4) | -0.3414 | -0.663 | 5 (0 / 5) | 22611 | 267 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.1739 | 0.000 | 0 (0 / 0) | +0.0985 | 0.000 | 0 (0 / 0) | 649 | 248 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +2.1797 | 0.000 | 0 (0 / 0) | -0.6981 | -48.499 | 231 (0 / 231) | 10541 | 289 | `_51959_/CLK` -> `axi_araddr_o[2]` |
| max_ss_100C_1v60 | -5.3352 | -3004.335 | 1480 (1376 / 104) | -1.3624 | -95.575 | 199 (0 / 199) | 88325 | 324 | `_51961_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.5418 | 0.000 | 0 (0 / 0) | -0.4315 | -8.831 | 90 (0 / 90) | 3190 | 276 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

#### ICC2 (StarRC)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | -0.0909 | -0.160 | 2 (2 / 0) | -1.1597 | -171.277 | 432 (5 / 427) | 677 | 164 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| nom_ss_100C_1v60 | -14.9330 | -4572.401 | 1504 (1488 / 16) | -2.0797 | -399.996 | 468 (0 / 468) | 40243 | 166 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| nom_ff_n40C_1v95 | +2.6717 | 0.000 | 0 (0 / 0) | -0.7186 | -81.926 | 401 (98 / 303) | 33 | 161 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| min_tt_025C_1v80 | +0.3839 | 0.000 | 0 (0 / 0) | -0.9884 | -131.402 | 370 (1 / 369) | 36 | 154 | `u_core/ex1a_ex1b_reg_q_reg_immediate__0_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ss_100C_1v60 | -14.4809 | -2971.842 | 842 (841 / 1) | -1.8059 | -336.688 | 467 (0 / 467) | 26975 | 156 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| min_ff_n40C_1v95 | +3.1705 | 0.000 | 0 (0 / 0) | -0.5988 | -61.379 | 341 (98 / 243) | 24 | 152 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |
| max_tt_025C_1v80 | -1.4141 | -17.264 | 67 (67 / 0) | -1.3408 | -214.760 | 463 (15 / 448) | 11592 | 176 | `u_core/u_icache_ic_addr_q_reg_7_/CLK` -> `u_core/u_if_pc_q_reg_31_/D` |
| max_ss_100C_1v60 | -15.4061 | -7281.157 | 2293 (2225 / 68) | -2.3746 | -472.103 | 478 (0 / 478) | 49535 | 178 | `u_core/ex1a_ex1b_reg_q_reg_pc__1_/CLK` -> `u_core/ex1c_ex1b_reg_q_reg_dec_redirect_target__31_/D` |
| max_ff_n40C_1v95 | +2.1312 | 0.000 | 0 (0 / 0) | -0.8512 | -107.907 | 436 (102 / 334) | 562 | 176 | `u_core/u_icache_gen_data_sram_2__u_data_sram/clk0` -> `u_core/u_icache_data_dout_r_reg_2__29_/D` |

#### Innovus b5c (StarRC)

PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).

#### OpenROAD (OpenRCX SPEF)

| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| nom_tt_025C_1v80 | +2.9768 | 0.000 | 0 (0 / 0) | -0.5197 | -30.138 | 192 (0 / 192) | 4166 | 270 | `_51959_/CLK` -> `axi_araddr_o[3]` |
| nom_ss_100C_1v60 | -3.5188 | -1156.629 | 1048 (968 / 80) | -1.1609 | -81.751 | 197 (0 / 197) | 49081 | 295 | `_53923_/CLK` -> `_53323_/D` |
| nom_ff_n40C_1v95 | +3.8218 | 0.000 | 0 (0 / 0) | -0.2793 | -4.202 | 50 (0 / 50) | 1953 | 262 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| min_tt_025C_1v80 | +3.4334 | 0.000 | 0 (0 / 0) | -0.3351 | -7.539 | 109 (0 / 109) | 2715 | 262 | `_51959_/CLK` -> `axi_araddr_o[3]` |
| min_ss_100C_1v60 | -2.6617 | -636.431 | 754 (686 / 68) | -0.8912 | -43.648 | 152 (0 / 152) | 30817 | 286 | `_53923_/CLK` -> `_53323_/D` |
| min_ff_n40C_1v95 | +4.0251 | 0.000 | 0 (0 / 0) | -0.1377 | -0.672 | 15 (0 / 15) | 1167 | 254 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |
| max_tt_025C_1v80 | +2.5645 | 0.000 | 0 (0 / 0) | -0.6888 | -59.158 | 272 (0 / 272) | 6326 | 274 | `_51959_/CLK` -> `axi_araddr_o[3]` |
| max_ss_100C_1v60 | -4.2715 | -1757.610 | 1189 (1094 / 95) | -1.3806 | -116.593 | 226 (0 / 226) | 65290 | 304 | `_52681_/CLK` -> `_53323_/D` |
| max_ff_n40C_1v95 | +3.7128 | 0.000 | 0 (0 / 0) | -0.4215 | -11.788 | 113 (0 / 113) | 2615 | 265 | `u_core.u_icache.gen_data_sram[0].u_data_sram/clk0` -> `_52811_/D` |

Reading the tables (measured):
- **OpenROAD (StarRC)**: setup meets at all six tt/ff corners (nom_tt +3.049, max_tt +2.180 ns); **setup fails at the three ss corners** (nom_ss -3.679, min_ss -2.117, max_ss -5.335 ns; 1130 / 645 / 1480 endpoints, almost all reg->reg). Hold: **0 reg->reg violators at any corner**; all hold violators are I/O ports (input min-delay 0.5-1.0 ns against a 2.7 ns propagated clock): 62 (nom_tt) up to 231 (max_tt) endpoints, only min_ff meets.
- **ICC2 (StarRC)**: setup is at about zero slack at the one corner ICC2 optimised (nom_tt -0.091 ns, 2 endpoints), meets at min_tt (+0.384) and the ff corners (+2.1 to +3.2), fails at **max_tt -1.414 ns (67 endpoints)** and **catastrophically at ss (-14.4 to -15.4 ns, 842-2293 endpoints)**: the DC-NXT netlist was optimised for one scenario (tt, nominal TLU+) only. Hold fails at **all nine corners on 243-478 I/O endpoints** (worst -2.375 ns at max_ss) plus 1-102 reg->reg endpoints at tt/ff (worst -0.107 ns): see section 5 for why.
- **Sign-off criteria** (setup/hold WNS >= 0, TNS = 0 at all corners): **not met by either arm** on this measurement. This is a comparison, nothing was repaired.
- Max-fanout violators (OpenROAD 3670, ICC2 173) are in the full tables only: ICC2 ignores the SDC `set_max_fanout` (CSTR-011) and used 16 as an optimiser option, OpenROAD ran 8 against the SDC's 16.

## 4. Power (PrimePower, vectorless, nom_tt = tt lib + nom SPEF)

Activity assumption (identical for every arm, written into `scripts/judge.tcl`): `power_default_toggle_rate 0.1` (reference clock `related`), `power_default_static_probability 0.5`, averaged mode,
no SAIF/VCD, clock activity from the SDC clock (`clk_i`, 13.333 ns), propagated clocks, same SPEF as the timing run. Two variants:
**A = PrimePower defaults** (activity on primary inputs, propagated through registers and logic) and **B = A plus 0.1 / 0.5 asserted on every register output pin (5939 / 5924 pins)**.
B is the headline because it is the closest PT can get to OpenROAD's default: OpenSTA does not derive register-output activity from the D input, and B reproduces OpenSTA's native comb / clock / macro split
(OpenSTA comb 18.33 mW vs B 18.4-18.6; A gives 4.6). That OpenSTA assumption is INFERRED from this match (the OpenSTA source was not read; no OpenROAD binary on the host outside the container). mW:

| Arm | PT variant | Total | Internal | Switching | Leakage | clock_network | register | comb | memory (SRAM) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OpenROAD (StarRC) | **B (headline)** | **93.985** | 65.261 | 28.660 | 0.0954 | 43.3 | 2.985 | 18.6 | 29.1 |
| ICC2 (StarRC) | **B (headline)** | **67.990** | 48.649 | 19.274 | 0.0953 | 23.5 | 3.090 | 12.4 | 29.0 |
| Innovus b5c | B | PENDING | | | | | | | |
| OpenROAD (OpenRCX SPEF) | B | 93.113 | 65.253 | 27.793 | 0.0954 | 42.7 | 2.913 | 18.4 | 29.1 |
| OpenROAD (StarRC) | A | 77.080 | 59.998 | 17.021 | 0.0954 | 43.3 | 0.076 | 4.603 | 29.1 |
| ICC2 (StarRC) | A | 55.724 | 45.479 | 10.208 | 0.0953 | 23.5 | 0.118 | 3.106 | 29.0 |
| OpenROAD (OpenRCX SPEF) | A | 76.499 | 59.998 | 16.445 | 0.0954 | 42.7 | 0.077 | 4.622 | 29.1 |

Native figures (labelled **native**, not ranked against the judge's):

| Arm | native tool and activity | Total | Internal | Switching | Leakage | Judge B | Judge A |
|---|---|---:|---:|---:|---:|---|---|
| OpenROAD | OpenSTA `report_power`, nom_tt corner, OpenRCX nom SPEF, OpenSTA default activity (`57-openroad-stapostpnr/nom_tt_025C_1v80/power.rpt`) | **91.333** | 63.052 | 28.090 | 0.191 | 93.985 (+2.9 %); 93.113 on OpenRCX (+1.9 %) | 77.080 (-15.6 %) |
| ICC2 | ICC2 `report_power` (PrimePower engine), nominal TLU+ SPEF, default propagated activity (`icc2/reports/final_power.txt`) | **55.9** | 45.6 | 10.2 | 0.0953 | 67.990 | 55.724 (-0.3 %) |
| Innovus | b5b run was 87.82 mW but is superseded; b5c pending | n/a | | | | PENDING | PENDING |

(The OpenROAD `metrics.json` headline 103.4 mW is the max_ff corner, not nom_tt; nom_tt is 91.33.) Leakage differs 2x between OpenSTA (0.191 mW) and PT (0.095 mW) on the same SRAM-dominated design: SRAM leakage state-dependence handling, not diagnosed; 0.2 % of total.
Reading: with the PrimePower-default activity, **the judge reproduces ICC2's native number to 0.3 %** (same engine, a good check of the judge plumbing), and with the OpenSTA-style register assumption it reproduces OpenROAD's native number to 2-3 %.
Under the matched assumption B the OpenROAD implementation burns 94.0 mW against ICC2's 68.0 mW; the difference is clock network (43.3 vs 23.5 mW) and combinational (18.6 vs 12.4 mW), the SRAM macros are equal (29 mW). Different netlists and CTS, so this is a measured outcome, not a tool ranking.

## 5. Judge vs native, and what explains the deltas

### 5.1 OpenROAD: native (OpenSTA + OpenRCX) vs PT on the same OpenRCX SPEF vs PT on StarRC

Full 9-corner table: `reports/untuned/openroad_three_way.txt` (setup/hold WNS, violators, hold r2r violators, max_tran, max_cap). Engine effect = PT/OpenRCX minus native; extractor effect = PT/StarRC minus PT/OpenRCX.

| corner | setup WNS native | PT / OpenRCX | PT / StarRC | hold WNS native | PT / OpenRCX | PT / StarRC | hold viol native / PT-RCX / PT-Star |
|---|---:|---:|---:|---:|---:|---:|---|
| nom_tt | +3.031 | +2.977 | +3.049 | -0.458 | -0.520 | -0.347 | 156 / 192 / 62 |
| nom_ss | -3.323 | -3.519 | -3.679 | -1.074 | -1.161 | -0.823 | 176 / 197 / 124 |
| nom_ff | +3.218 | +3.822 | +3.892 | -0.226 | -0.279 | -0.152 | 33 / 50 / 9 |
| min_ss | -2.520 | -2.662 | -2.117 | -0.810 | -0.891 | -0.341 | 132 / 152 / 5 |
| max_tt | +2.741 | +2.565 | +2.180 | -0.603 | -0.689 | -0.698 | 208 / 272 / 231 |
| max_ss | -3.996 | -4.272 | -5.335 | -1.296 | -1.381 | -1.362 | 217 / 226 / 199 |

1. **Engine effect (same SPEF), measured.** Max-capacitance violators are **identical at all 9 corners** (270, 295, 262, ... 304, 265), so the two engines agree on loads. Setup at tt is within 0.2 ns, at ss PT is 0.14-0.28 ns *more* pessimistic (+40 to +109 violators), hold PT is 0.04-0.09 ns more pessimistic with 20-70 % more I/O violators; r2r hold is clean in both (0 violators at 9/9 corners). Hold and ss delta cause: **not diagnosed** (candidates: PT vs OpenSTA slew merging and CRPR, INFERRED, untested).
2. **ff-corner setup: PT is 0.5-0.75 ns less pessimistic than OpenSTA, and this is explained by measurement.** The worst OpenSTA path is the falling-edge-launched SRAM path. I re-timed that exact path (`SRAM[2].dout0[18]` -> `_52883_/D`) in PT on the same OpenRCX SPEF (`scripts/diag_sram_path.tcl`): same net, same 0.3416 pF load, **SRAM clk0->dout0 = 0.4257 ns in PT vs 2.2466 ns in OpenSTA** (path slack +4.97 vs +2.97 ns). The load is far outside the SRAM `.lib` output-load table, so the two engines extrapolate differently (OpenSTA linearly, PT clamps; INFERRED from the numbers). Any SRAM-launched path is therefore engine-dependent by up to ~2 ns until the SRAM is characterised for the real load range (bead `o1i`). ICC2's native power run shows the same table-extrapolation class of warning (POW-046).
3. **Extractor effect (StarRC vs OpenRCX, same engine), measured and consistent with the correlation gate.** StarRC total C is x1.03 / x0.91 / x1.15 of OpenRCX at nom / min / max. Setup follows: max_tt -0.38, max_ss **-1.06 ns**, min_ss +0.55 ns; hold at nom_tt/min_tt is far less pessimistic with StarRC (62 vs 192 and 1 vs 109 violators) because StarRC puts only ~34 % of C into coupling (OpenRCX ~55 %) and coupling is lumped to ground here. **The extractor choice moves ss/max slack by up to 1 ns, larger than the engine effect**; with the authored ITF this is the dominant uncertainty of the whole judge. Do not read any single ss/max figure to better than about 1 ns.
4. **max_transition: PT reports 15-25 % more violating pins than OpenSTA on the same SPEF** at the OpenRCX corners (e.g. nom_tt 4166 vs 3437). Not reconciled (counting and limit semantics differ; not proven).

### 5.2 ICC2: native vs PT, nom_tt

| Metric | ICC2 native | PT + ICC2 native SPEF (diag) | PT + StarRC (judge) |
|---|---:|---:|---:|
| setup WNS / TNS / endpoints | -0.0046 / -0.0046 / 1 | -0.0438 / -0.0864 / 2 | -0.0909 / -0.1597 / 2 |
| hold WNS / endpoints | +0.0008 / 0 | -1.1827 / 442 | -1.1597 / 432 |
| max_cap pins | 164 | 164 | 164 |
| max_tran | 57 nets (244 pins) | 891 pins | 677 pins |
| power (mW) | 55.9 | n/a | 55.72 (A) |

1. **Hold: the large delta is explained and verified.** ICC2's own SDC (`out/rv32i_cpu_top.sdc`) carries `set_clock_latency 1.77814 [get_clocks clk_i]` ("Set latency for io paths", `-origin useful_skew`) and `set_propagated_clock [get_ports clk_i]`; the shared SDC has neither. Without it, input ports launch at 1.0 ns (source latency) + 0.5 ns min input delay against a capture clock arriving at ~2.7 ns, which fails hold by ~1.2 ns on every `axi_rdata_i` path (worst `axi_rdata_i[10] -> u_dcache/uncached_rdata_q_reg_10_/D`). Re-timing the ICC2 arm in PT with that single line added (`scripts/diag_io_latency.tcl`, emulation applied to the whole clock) gives **"No hold violations found"** at nom_tt (setup r2r -0.136 ns, 4 endpoints, so the emulation shifts r2r setup by ~0.05 ns and is not an exact replica). So ICC2 closed I/O hold against an I/O budget that is 1.78 ns easier than the shared SDC. The judge numbers are right for the shared SDC; the ICC2 arm was not implemented against it. The OpenROAD arm was (it ran the original SDC), and Innovus (SDC "the ORIGINAL sky130_cpu.sdc") should have the same property as OpenROAD. **Whether the shared SDC should carry an I/O clock latency is the SDC owner's decision; nothing was changed here.**
2. **Setup:** ICC2 -0.0046 vs PT -0.044 (its native SPEF) vs -0.091 (StarRC): the native SPEF -> StarRC step costs 0.047 ns (extractor), the ICC2 -> PT step 0.039 ns (engine/SDC: latency line, ICC2 effort), all at the one corner where ICC2 left a single endpoint at zero slack. Same order, consistent.
3. **max_cap 164 = 164 = 164**: engines and extractors agree. **max_tran 57 nets / 244 pins vs 677 (StarRC) or 891 (ICC2-native SPEF) pins is NOT reconciled.** The worst offender is the same (`axi_rdata_i[14]` port net), the unit differs (ICC2 counts nets, PT pins; PT has ~275 driver pins among its 677), and a x2.8 gap remains after pin-counting. It is not an extractor effect (the native SPEF gives more, not fewer). Flagged as the one open judge-vs-native delta; it does not change any conclusion above (all max_tran counts are far from zero for both arms).
4. **Power:** 55.72 (A) vs 55.9 native, -0.3 %; same engine, parasitics differ by 0.4 % in total C.

## 6. SDC: tool-written files vs the shared SDC (diffed, not used)

Both written SDCs are per-port expansions of the same constraints (379 `set_load` + 379 `set_max_capacitance 0.1` on outputs, 178 `set_input_delay`, 332 `set_output_delay`, 124 `set_driving_cell buf_4/X`, same `create_clock 13.333`, uncertainty 0.5/0.2, `set_clock_latency -source 1.0`, `set_max_transition 0.5`, 4 multicycle paths, 2 false-path groups). Differences:
- OpenROAD-written (`runs/openroad/rv32i_cpu_top.sdc`): adds `set_propagated_clock [get_clocks clk_i]` (the judge does the same); `set_driving_cell ... -input_transition_rise/fall 0.0`; no other change.
- ICC2-written (`impl/icc2/runs/b5a_icc2/out/rv32i_cpu_top.sdc`): adds **`set_clock_latency 1.77814 clk_i`** and `set_propagated_clock` on the port; **drops `set_max_fanout 16`** (ICC2 ignores it, CSTR-011; fanout 16 was an optimiser option); `set_max_area 0` not carried. The first is the cause of 5.2(1).

## 7. Caveats and what is open

Caveats that apply to every number:
1. **Untuned, authored ITF** (INDICATIVE at nom and max, min passes only by cancellation): ss/max slack uncertainty is about 1 ns (5.1(3)). All three corners use one 25 C temperature, so ss/ff resistance is not temperature-scaled.
2. **TT-only SRAM model at every corner (o1i)**; SRAM-launched paths are engine-dependent by up to ~2 ns (5.1(2)); ss and ff results are therefore not true ss/ff timing for the 10 SRAM macros.
3. **Coupling is lumped to ground (SI off).** StarRC carries ~34 % of its C as coupling vs OpenRCX ~55 %, so a PT-SI run on these SPEFs would be the weakest part (not run; the PT-SI licence is available).
4. Different netlists per arm (Yosys/ABC vs DC-NXT): the judge removes the STA/extraction differences, not the synthesis differences. ICC2 was optimised at one scenario (tt/nominal TLU+); OpenROAD's flow ran 9 corners.
5. No derate/OCV/POCV anywhere (Sky130 has no foundry OCV table here).

Open items:
1. **Innovus b5c: PENDING.** One command once `impl/innovus/runs/b5c_innovus/out/rv32i_cpu_top.nl.v` and `starrc/runs/innovus_{nom,min,max}/` exist (`make -C pnr/commercial/signoff/starrc innovus` then `make -C pnr/commercial/signoff/pt innovus`). It will be extracted with whatever ITF is then current, so a tuned Innovus next to an untuned OpenROAD/ICC2 would not be like for like: rerun all arms with `make rejudge`.
2. **Rerun on the tuned-ITF SPEFs:** `make -C pnr/commercial/signoff/pt rejudge` (about 12-15 min of pt_shell wall for 27 runs when the host load gate is open; the OpenRCX arm is `make rcx`).
3. ICC2 max_transition count delta (5.2(3)) and the OpenSTA-vs-PT hold/ss pessimism (5.1(1)) are unreconciled.
4. Shared-SDC I/O latency decision (5.2(1)), for the SDC owner.
5. PT-SI run, and a per-corner SRAM characterisation (o1i), would remove caveats 2 and 3.

## 8. Files

| Item | Path |
|---|---|
| Scripts, Makefile, .gitignore (`runs*/`, `!reports/`) | `pnr/commercial/signoff/pt/{Makefile,.gitignore,scripts/}`: `judge.tcl` (one pt_shell: link, shared SDC with md5 assert, SPEF, annotation gate, 9-corner metrics, PrimePower A/B), `run_one.sh` (SPEF snapshot + md5 stamp + safe_run), `arms.sh` (netlist/SPEF per arm), `collect.py` (tables), diagnostics `diag_io_latency.tcl`, `diag_sram_path.tcl`, `diag_native_spef.tcl`, `power_diag.tcl` via `run_diag.sh` |
| Targets | `make untuned` (this pass, frozen untuned SPEFs); `make rejudge` / `judge` (current SPEFs); `openroad`, `icc2`, `innovus`, `rcx`; `tables`; `force-<arm>` |
| This pass, compact reports | `pnr/commercial/signoff/pt/reports/untuned/`: `{openroad,icc2,openroad_rcx}_9corner.txt`, `openroad_three_way.txt`, `power_nom_tt.txt`, `*_nom_tt_worst_{setup,hold}.txt`, `*_nom_tt_power_full.txt`, `compact_tables.md`, `judge_tables.md`, `judge_results.json` (all metrics, every md5) |
| I/O-latency variant (B6b) | section 10; `make untuned-iolat`, `reports/untuned_iolat/`, `runs_untuned_iolat/` |
| Raw runs (gitignored) | `pnr/commercial/signoff/pt/runs_untuned/<arm>_<rc>_<lib>/` (`pt.log`, `metrics.tsv`, `inputs.txt`, `spef/` snapshot, reports) |

## 9. Tool gotchas (for back-porting into the agent suite)

| Symptom | Cause / fix |
|---|---|
| `Error: Cannot specify '-from' with '-clock_tree'` | `all_fanout -flat -clock_tree` takes no start point; it returns the clock-network pins of all clocks. `get_nets -of_objects` on them gives the clock nets for an annotation check |
| Annotation counts not on stdout | `read_parasitics` runs in the background and writes its summary to `parasitics_command.log` in the cwd; `report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets` (redirected) gives the table. PT splits nets into pin-to-pin / driverless / loadless, which makes the "unannotated driver nets" gate unambiguous: gate on the pin-to-pin row only |
| `report_global_timing` has no table when clean | prints `No setup violations found.` instead of WNS/TNS/NUM rows; a parser must handle both. Digits come from `set_app_var report_default_significant_digits 4` (default 2 hides a -0.0046 ns slack) |
| PrimePower vectorless power differs 15 % from OpenSTA | PT propagates register activity from D; OpenSTA effectively gives register outputs the default activity. `set_switching_activity -toggle_rate 0.1 -static_probability 0.5 -base_clock clk_i [all_registers -output_pins]` matched OpenSTA within 2-3 %. Always state which one a power number uses |
| `Unable to resolve reference to sky130_ef_sc_hd__decap_12 / fill_1 / tapvpwrvgnd_1` (LNK-005) | physical-only cells are not in the `.db`; PT black-boxes them (no connections, no effect). `is_black_box` also matches diodes and SRAM macros (no-function cells) |
| SPEF net not in design (PARA-124) | ICC2's StarRC DEF has 8 `_dummynet*` nets; harmless, count them in the gate report |
| SRAM clk->dout delay differs 0.43 vs 2.25 ns between PT and OpenSTA | load outside the SRAM `.lib` table; engines extrapolate differently (o1i) |
| Native vs judge hold delta of ~1.2 ns on I/O | a tool-written SDC may add `set_clock_latency <n>` ("io paths", ICC2 `-origin useful_skew`) that the shared SDC lacks; diff the written SDC before comparing |
| SPEF replaced during a run | copy the SPEF into the run dir and take the md5 before and after the copy (`run_one.sh`); stamp = md5 of SPEF + netlist + SDC + scripts + power flag, so `make rejudge` reruns only what changed |
| Host load gate | `safe_run.sh` waits for load < 6 in 30 s steps (up to 2 h); with an Innovus job and a DRC/LVS job running, the first PT start waited about 10 minutes. Shell `sleep N` chains are blocked in this harness: use background `until` loops |
| `rm -rf runs reports/*` | blocked by the harness's safety check; the stale directories were `mv`-ed aside and deleted later by explicit path on the coordinator's say-so |

## 10. I/O-latency SDC variant (task B6b, comparison only)

**What and why.** Section 5.2 found that ICC2 closed I/O hold against an SDC with `set_clock_latency 1.77814 [get_clocks clk_i]` that the shared SDC lacks. Per the user's decision the shared SDC
`pnr/sky130/cpu/constraints/sky130_cpu.sdc` is **not edited** (the production LibreLane CPU-macro flow uses it). Instead a generated, comparison-only copy models the I/O latency as a **virtual I/O clock**:

- Generator `pnr/commercial/constraints/gen_iolat_sdc.py` -> `pnr/commercial/constraints/sky130_cpu_iolat.sdc` (+ `.md5` sidecar). It asserts the source md5 `3c69635042a9d65cb87e71a9db713e4e` and fails otherwise, is deterministic (no timestamps), and asserts that all 66 I/O delays were rewritten (28 `set_input_delay` + 38 `set_output_delay`, `-clock clk_i` -> `-clock clk_io`).
- **Generated SDC md5: `e90bdba8b93f8f4e985c5fbaa6d4ab90`** (whole file; the header states the md5 of the file with its own md5 line removed, `8941f999c9530089b2c1c42197e0109a`, because a file cannot contain its own md5).
- Added after the clk_i block: `create_clock -name clk_io -period 13.333` (virtual, no source), `set_clock_latency -source 1.0` and `set_clock_latency 1.778` on clk_io, uncertainty 0.5 / 0.2 as clk_i; and `group_path -name IO -from` / `-to [get_clocks clk_io]`. Everything else (false paths, multicycles, drive/load, DRC limits, clk_i itself) is unchanged.
- Assumption (stated in the file header): the SoC-side flops have about the same insertion delay as the macro's internal flops. 1.778 is ICC2's derived 1.77814, rounded. **clk_io is ideal: the judge now propagates only clk_i (`set_propagated_clock [get_clocks clk_i]`; in the base SDC this is identical to `all_clocks`); a propagated virtual clock would ignore its network latency.**
- Parameterised judge: `PT_SDC=base|iolat` (md5 asserted in `run_one.sh` and again in `judge.tcl`); `make untuned-iolat` (frozen untuned SPEFs -> `runs_untuned_iolat/`, `reports/untuned_iolat/`), `make judge-iolat` (current SPEFs -> `runs_iolat/`, `reports/iolat/`), `make compare-untuned` / `compare-current`; **`make rejudge` runs both variants** on the current SPEFs. The base set was rerun with the final scripts (numbers unchanged from sections 3-5). Same frozen untuned SPEFs, same netlists, all 9 corners, OpenROAD and ICC2 only (the OpenRCX sanity arm is not part of this variant). Innovus stays PENDING (its b5c_innovus_s2 netlist exists but no StarRC SPEFs yet).

**Validation at nom_tt, both arms** (`reports/untuned_iolat/validation_nom_tt.txt`):
1. `check_timing -verbose`: **no new unconstrained endpoints or ports**. Unconstrained endpoints 34 and ports without input delay 26 in both variants and both arms; set comparison of the full warning lists: 0 added, 0 removed (the 34 are the `mbist_status_o` outputs, the 26 are inputs already unconstrained in the base).
2. `report_clocks` (iolat): `clk_i 13.3330 {0 6.6665} p {clk_i}` and `clk_io 13.3330 {0 6.6665} (ideal, sources {})`; PT warns UITE-121 "Creating virtual clock clk_io with no sources", expected.
3. Spot path `axi_rdata_i[10] -> _52592_/D` (OpenROAD, min): base `clock network delay (propagated) 1.0000`, input delay 0.5, launch 1.5000 ns, slack +0.1023. iolat `clock clk_io (rise)`, `clock network delay (ideal) 2.7780` (= 1.0 source + 1.778 network), input delay 0.5, launch 3.2780 ns, slack +1.8803. Same effect on the setup spot path (launch 3.0 -> 4.778, slack 8.602 -> 6.824). Capture side (clk_i, propagated, source latency 1.0 + CTS tree) is unchanged.
4. **Propagated-clock reg->reg results are unchanged**: identical in 36/36 (arm, setup/hold, corner) cells (WNS, TNS, violators and endpoint count to 1e-9; `reports/untuned_iolat/base_vs_iolat.txt`). Where reg->reg meets, `judge.tcl` records no value (`get_timing_paths` returned only violating paths), so the worst reg->reg slack was also checked directly at nom_tt (`scripts/diag_r2r_wns.tcl`, 6 digits): OpenROAD setup +3.374176 / hold +0.532610 and ICC2 setup -0.090911 / hold -0.014733, **all identical in both variants**. (PT's `report_global_timing` reg->reg / in->reg split is *not* invariant: it re-assigns an endpoint between categories when an I/O constraint changes; the explicit `-from` register clock pins `-to` register data pins query is.)
5. **Power is unchanged by the I/O constraint, confirmed at nom_tt, one run per arm** (`reports/untuned_iolat/power_nom_tt.txt`): variant B OpenROAD 93.985 mW, ICC2 67.990 mW; variant A 77.080 / 55.724 mW; identical to section 4 to the printed digits.

**Base vs iolat, nine corners** (nom and max rows INDICATIVE; SRAM TT-only; untuned ITF). Full tables with reg->reg / I/O WNS and TNS: `reports/untuned_iolat/base_vs_iolat.txt`.

#### OpenROAD (StarRC, untuned): base SDC -> iolat SDC

Each cell: WNS / TNS / violating endpoints (reg->reg / I/O). ns.

| corner | setup base | setup iolat | hold base | hold iolat |
|---|---|---|---|---|
| nom_tt_025C_1v80 | +3.0493 / 0.000 / 0 (0/0) | +3.0953 / 0.000 / 0 (0/0) | -0.3470 / -4.579 / 62 (0/62) | +0.5326 / 0.000 / 0 (0/0) |
| nom_ss_100C_1v60 | -3.6789 / -1466.222 / 1130 (1055/75) | -3.6789 / -1426.074 / 1084 (1054/30) | -0.8225 / -27.928 / 124 (0/124) | +0.9555 / 0.000 / 0 (0/0) |
| nom_ff_n40C_1v95 | +3.8917 / 0.000 / 0 (0/0) | +3.8917 / 0.000 / 0 (0/0) | -0.1524 / -0.673 / 9 (0/9) | +0.2473 / 0.000 / 0 (0/0) |
| min_tt_025C_1v80 | +3.6856 / 0.000 / 0 (0/0) | +3.2300 / 0.000 / 0 (0/0) | -0.0347 / -0.035 / 1 (0/1) | +0.5600 / 0.000 / 0 (0/0) |
| min_ss_100C_1v60 | -2.1167 / -448.660 / 645 (641/4) | -2.1167 / -453.796 / 666 (641/25) | -0.3414 / -0.663 / 5 (0/5) | +1.3152 / 0.000 / 0 (0/0) |
| min_ff_n40C_1v95 | +4.1739 / 0.000 / 0 (0/0) | +4.1739 / 0.000 / 0 (0/0) | +0.0985 / 0.000 / 0 (0/0) | +0.2614 / 0.000 / 0 (0/0) |
| max_tt_025C_1v80 | +2.1797 / 0.000 / 0 (0/0) | +2.6595 / 0.000 / 0 (0/0) | -0.6981 / -48.499 / 231 (0/231) | +0.4962 / 0.000 / 0 (0/0) |
| max_ss_100C_1v60 | -5.3352 / -3004.335 / 1480 (1376/104) | -5.3352 / -2883.810 / 1447 (1376/71) | -1.3624 / -95.575 / 199 (0/199) | +0.4156 / 0.000 / 0 (0/0) |
| max_ff_n40C_1v95 | +3.5418 / 0.000 / 0 (0/0) | +3.5418 / 0.000 / 0 (0/0) | -0.4315 / -8.831 / 90 (0/90) | +0.2070 / 0.000 / 0 (0/0) |

#### ICC2 (StarRC, untuned): base SDC -> iolat SDC

Each cell: WNS / TNS / violating endpoints (reg->reg / I/O). ns.

| corner | setup base | setup iolat | hold base | hold iolat |
|---|---|---|---|---|
| nom_tt_025C_1v80 | -0.0909 / -0.160 / 2 (2/0) | -0.0909 / -0.160 / 2 (2/0) | -1.1597 / -171.277 / 432 (5/427) | -0.0147 / -0.028 / 5 (5/0) |
| nom_ss_100C_1v60 | -14.9330 / -4572.401 / 1504 (1488/16) | -14.9330 / -4615.273 / 1519 (1464/55) | -2.0797 / -399.996 / 468 (0/468) | -0.3017 / -3.386 / 22 (0/22) |
| nom_ff_n40C_1v95 | +2.6717 / 0.000 / 0 (0/0) | +2.6717 / 0.000 / 0 (0/0) | -0.7186 / -81.926 / 401 (98/303) | -0.0908 / -4.068 / 99 (99/0) |
| min_tt_025C_1v80 | +0.3839 / 0.000 / 0 (0/0) | +0.3839 / 0.000 / 0 (0/0) | -0.9884 / -131.402 / 370 (1/369) | -0.0027 / -0.003 / 1 (1/0) |
| min_ss_100C_1v60 | -14.4809 / -2971.842 / 842 (841/1) | -14.4809 / -2992.382 / 870 (841/29) | -1.8059 / -336.688 / 467 (0/467) | -0.0279 / -0.036 / 2 (0/2) |
| min_ff_n40C_1v95 | +3.1705 / 0.000 / 0 (0/0) | +3.1705 / 0.000 / 0 (0/0) | -0.5988 / -61.379 / 341 (98/243) | -0.0887 / -3.692 / 101 (99/2) |
| max_tt_025C_1v80 | -1.4141 / -17.264 / 67 (67/0) | -1.4141 / -17.264 / 67 (67/0) | -1.3408 / -214.760 / 463 (15/448) | -0.0191 / -0.107 / 15 (15/0) |
| max_ss_100C_1v60 | -15.4061 / -7281.157 / 2293 (2225/68) | -15.4061 / -7306.531 / 2258 (2225/33) | -2.3746 / -472.103 / 478 (0/478) | -0.5966 / -12.385 / 40 (0/40) |
| max_ff_n40C_1v95 | +2.1312 / 0.000 / 0 (0/0) | +2.1312 / 0.000 / 0 (0/0) | -0.8512 / -107.907 / 436 (102/334) | -0.1066 / -4.755 / 103 (103/0) |

Counts of corners with zero violating endpoints (of 9): OpenROAD setup 6 -> 6, **hold 1 -> 9**; ICC2 setup 4 -> 4, **hold 0 -> 0 (I/O-clean 0 -> 5)**.

**Reading (measured).**
- **ICC2 I/O hold now closes at five corners** (nom_tt, nom_ff, min_tt, max_tt, max_ff have 0 I/O hold violators; the ~1.2 ns tt violation is gone, so section 5.2's explanation is confirmed on all 9 corners). It does **not** fully close hold anywhere: reg->reg hold violators remain at every tt/ff corner, unchanged by the variant (-0.0027 to -0.1066 ns, 1 to 103 endpoints; nom_tt -0.0147 ns, 5 endpoints, i.e. the same -0.015 ns the shared SDC shows, against ICC2's native +0.0008), and I/O hold residuals remain at min_ff (-0.044 ns, 2 endpoints) and at the ss corners (nom_ss -0.302 ns / 22, min_ss -0.028 / 2, max_ss -0.597 / 40). The ss residuals are a corner ICC2 never optimised.
- **OpenROAD I/O hold closes everywhere with iolat** (hold violators 1-231 at 8 of 9 base corners -> 0 at all 9 corners; hold WNS +0.207 (max_ff) to +1.315 ns (min_ss)): its input hold paths were short because it was built against an SDC whose I/O clock arrives with no network latency; with the later I/O launch they have margin. The hold WNS that remains is reg->reg (e.g. nom_tt +0.5326 ns). So the OpenROAD hold failures of section 3 are entirely an artefact of the I/O launch time, not of the implementation's reg->reg hold.
- **I/O setup moves in opposite directions for inputs and outputs**: the input launch is 1.778 ns later (less setup margin) and the output capture is 1.778 ns later (more margin). Where setup was met it stays met in both arms at all tt/ff corners (OpenROAD I/O setup violators 0 -> 0, ICC2 0 -> 0). At the ss corners, where setup already fails, OpenROAD's I/O setup WNS **improves** (nom_ss -3.076 -> -1.335 ns, 75 -> 30 endpoints; max_ss -4.565 -> -2.787, 104 -> 71) because its violations were on outputs, while ICC2's I/O setup WNS **worsens** (nom_ss -3.094 -> -4.872 ns, 16 -> 55 endpoints; max_ss -3.949 -> -5.727, 68 -> 33 endpoints but deeper). Total-design setup WNS does not move at the ss corners (reg->reg dominates: OpenROAD -3.679 / -2.117 / -5.335, ICC2 -14.9 / -14.5 / -15.4); at OpenROAD min_tt the total setup WNS drops 3.686 -> 3.230 and at max_tt rises 2.180 -> 2.660 (the worst path there is an I/O path), still met.
- **Sign-off view**: neither variant makes either arm sign-off clean (ss setup fails by -2 to -15 ns reg->reg in both). The iolat variant removes OpenROAD's hold failures and turns ICC2's I/O hold from 243-478 violating endpoints per corner to 0-40 (0 at five corners), leaving its small reg->reg residue.

**Caveat on fairness (report both variants).** OpenROAD (and Innovus, b5c) were implemented and repaired against the **base** SDC; ICC2 was effectively implemented against the **iolat** form. Neither variant is perfectly fair to every arm: base penalises ICC2's I/O hold (an artefact of the SDC it was not given) and iolat flatters OpenROAD's I/O hold (hold it never had to repair) and penalises ICC2's input setup at ss. The 1.778 ns is ICC2's own derived value, not a measured latency of a real SoC clock tree; the SoC-side insertion delay assumption is unverified. Use base for "does this meet the production macro SDC" and iolat only to separate SDC-modelling effects from implementation quality. The decision whether the production SDC should carry an I/O latency remains with the SDC owner (open item 4 in section 7).

Files (B6b): `pnr/commercial/constraints/{gen_iolat_sdc.py,sky130_cpu_iolat.sdc,sky130_cpu_iolat.sdc.md5}`; `pnr/commercial/signoff/pt/reports/untuned_iolat/{openroad,icc2}_9corner.txt, base_vs_iolat.txt, validation_nom_tt.txt, power_nom_tt.txt, judge_results.json}`; raw runs `pnr/commercial/signoff/pt/runs_untuned_iolat/`; scripts `compare_variants.py`, `diag_r2r_wns.tcl`.

**Additional gotchas (B6b).** A propagated virtual clock ignores `set_clock_latency` network latency: propagate only the real clock. `create_clock` with no source gives UITE-121 (expected). `get_timing_paths -from regs -to regs -max_paths N` returned only violating paths in this setup, so a "worst slack including positive" query needs `-max_paths 1`. Header md5 of a generated file cannot cover itself: state the md5 of the file minus that line and keep the full-file md5 in a sidecar the consumer asserts.

---

# 11. Tuned-ITF baseline: OpenROAD / ICC2 b5a / Innovus b5d (task B7 step 1, 2026-10-31)

**Pass label: TUNED ITF, "calibrated to OpenRCX", not to silicon.** First PrimeTime/PrimePower judge on the tuned StarRC SPEFs (sections 1 to 10 above are the UNTUNED pass and stay as history). This is the baseline that the
b5e (ICC2) and b5g (Innovus) re-judges in section 12 are compared against. **Judge, not native**: PrimeTime X-2025.06 on StarRC SPEFs; the tools' own numbers are labelled native wherever they appear.
All 54 runs (3 arms x 9 corners x 2 SDC variants) were run with `FORCE=1` after a host power-off killed the first attempt; every run has its `.done` stamp, annotation gate PASS 9/9 per arm.
Netlists: OpenROAD `runs/openroad/rv32i_cpu_top.nl.v`, ICC2 `b5a_icc2/out/rv32i_cpu_top.nl.v` (md5 `e9150655c154779119d823b4222358d5`), Innovus `b5d_innovus/out/rv32i_cpu_top.nl.v`. SDC md5s asserted inside every run:
base `3c69635042a9d65cb87e71a9db713e4e`, iolat (comparison-only, virtual I/O clock latency 1.778 ns) `e90bdba8b93f8f4e985c5fbaa6d4ab90`. SPEF md5 per run in `pt/runs*/<tag>/inputs.txt`; frozen per-corner tables in
`pt/reports/{current,iolat}_b5a_b5d/` (run dirs in `pt/runs{,_iolat}_baseline_b5a_b5d/`, gitignored). Generated by `pt/scripts/summ_compare.py`. Cells are WNS / TNS / violating endpoints (ns).

#### SETUP WNS / TNS / violators (ns), base SDC (sky130_cpu.sdc, md5 3c69635042a9d65cb87e71a9db713e4e)

| corner | OpenROAD | ICC2 b5a | Innovus b5d |
|---|---:|---:|---:|
| nom_tt | +3.172 / 0.0 / 0 | +0.040 / 0.0 / 0 | -0.617 / -1.7 / 5 |
| nom_ss | -3.426 / -1221.5 / 1062 | -14.883 / -4393.6 / 1444 | -7.868 / -2937.5 / 1440 |
| nom_ff | +3.928 / 0.0 / 0 | +2.692 / 0.0 / 0 | +2.035 / 0.0 / 0 |
| min_tt | +3.548 / 0.0 / 0 | +0.263 / 0.0 / 0 | +0.149 / 0.0 / 0 |
| min_ss | -2.777 / -776.6 / 800 | -14.698 / -3654.0 / 1139 | -7.119 / -2157.2 / 1211 |
| min_ff | +4.066 / 0.0 / 0 | +2.910 / 0.0 / 0 | +2.742 / 0.0 / 0 |
| max_tt | +2.679 / 0.0 / 0 | -0.525 / -1.7 / 7 | -1.813 / -7.7 / 6 |
| max_ss | -4.326 / -1948.5 / 1207 | -15.118 / -5670.4 / 1914 | -8.859 / -4084.5 / 1672 |
| max_ff | +3.713 / 0.0 / 0 | +2.393 / 0.0 / 0 | +0.992 / 0.0 / 0 |

#### HOLD WNS / TNS / violators (ns), base SDC (sky130_cpu.sdc, md5 3c69635042a9d65cb87e71a9db713e4e)

| corner | OpenROAD | ICC2 b5a | Innovus b5d |
|---|---:|---:|---:|
| nom_tt | -0.319 / -3.5 / 51 | -1.162 / -170.5 / 430 | -1.796 / -92.0 / 209 |
| nom_ss | -0.800 / -25.6 / 121 | -2.084 / -399.4 / 469 | -3.010 / -267.0 / 383 |
| nom_ff | -0.136 / -0.5 / 8 | -0.720 / -81.4 / 401 | -1.164 / -45.3 / 89 |
| min_tt | -0.174 / -0.5 / 5 | -1.084 / -151.8 / 408 | -1.653 / -94.7 / 259 |
| min_ss | -0.588 / -7.4 / 78 | -1.960 / -370.1 / 467 | -2.801 / -278.7 / 413 |
| min_ff | -0.015 / -0.0 / 3 | -0.661 / -70.8 / 371 | -1.062 / -44.2 / 123 |
| max_tt | -0.522 / -21.8 / 169 | -1.270 / -196.4 / 454 | -1.984 / -91.0 / 167 |
| max_ss | -1.071 / -55.3 / 155 | -2.250 / -440.3 / 476 | -3.309 / -261.2 / 367 |
| max_ff | -0.307 / -3.3 / 43 | -0.801 / -97.1 / 421 | -1.303 / -49.1 / 82 |

#### SETUP WNS / TNS / violators (ns), iolat SDC (comparison-only, md5 e90bdba8b93f8f4e985c5fbaa6d4ab90)

| corner | OpenROAD | ICC2 b5a | Innovus b5d |
|---|---:|---:|---:|
| nom_tt | +3.123 / 0.0 / 0 | +0.040 / 0.0 / 0 | +1.161 / 0.0 / 0 |
| nom_ss | -3.426 / -1193.0 / 1014 | -14.883 / -4434.2 / 1462 | -7.868 / -2897.3 / 1421 |
| nom_ff | +3.928 / 0.0 / 0 | +2.692 / 0.0 / 0 | +3.642 / 0.0 / 0 |
| min_tt | +3.186 / 0.0 / 0 | +0.263 / 0.0 / 0 | +1.712 / 0.0 / 0 |
| min_ss | -2.777 / -774.8 / 788 | -14.698 / -3686.4 / 1169 | -7.119 / -2128.1 / 1189 |
| min_ff | +4.066 / 0.0 / 0 | +2.910 / 0.0 / 0 | +3.946 / 0.0 / 0 |
| max_tt | +3.019 / 0.0 / 0 | -0.525 / -1.7 / 7 | -0.035 / -0.0 / 1 |
| max_ss | -4.326 / -1880.3 / 1155 | -15.118 / -5710.3 / 1901 | -8.859 / -4027.2 / 1653 |
| max_ff | +3.713 / 0.0 / 0 | +2.393 / 0.0 / 0 | +2.770 / 0.0 / 0 |

#### HOLD WNS / TNS / violators (ns), iolat SDC (comparison-only, md5 e90bdba8b93f8f4e985c5fbaa6d4ab90)

| corner | OpenROAD | ICC2 b5a | Innovus b5d |
|---|---:|---:|---:|
| nom_tt | +0.526 / 0.0 / 0 | -0.016 / -0.0 / 5 | -0.018 / -0.0 / 1 |
| nom_ss | +0.978 / 0.0 / 0 | -0.306 / -3.3 / 22 | -1.232 / -19.4 / 37 |
| nom_ff | +0.243 / 0.0 / 0 | -0.098 / -4.0 / 99 | +0.027 / 0.0 / 0 |
| min_tt | +0.542 / 0.0 / 0 | -0.011 / -0.0 / 2 | +0.125 / 0.0 / 0 |
| min_ss | +1.190 / 0.0 / 0 | -0.182 / -1.0 / 11 | -1.023 / -14.6 / 29 |
| min_ff | +0.250 / 0.0 / 0 | -0.097 / -3.9 / 100 | +0.024 / 0.0 / 0 |
| max_tt | +0.495 / 0.0 / 0 | -0.021 / -0.0 / 8 | -0.206 / -0.2 / 1 |
| max_ss | +0.707 / 0.0 / 0 | -0.472 / -7.9 / 31 | -1.531 / -27.3 / 39 |
| max_ff | +0.212 / 0.0 / 0 | -0.106 / -4.4 / 101 | +0.030 / 0.0 / 0 |

#### Power, PrimePower nom_tt (mW), variant B (headline) / variant A, base SDC

| set | B total | B internal | B switching | B clock_nw | B comb | B memory | A total |
|---|---:|---:|---:|---:|---:|---:|---:|
| OpenROAD | 93.13 | 65.26 | 27.90 | 42.8 | 18.3 | 29.1 | 76.49 |
| ICC2 b5a | 67.77 | 48.65 | 19.14 | 23.4 | 12.3 | 29.0 | 55.60 |
| Innovus b5d | 70.09 | 50.66 | 19.34 | 23.8 | 15.3 | 29.0 | 56.75 |

#### Annotation gate and DRV (violating pins), base SDC

| set | gate PASS corners | max_tran nom_tt / max_ss | max_cap nom_tt / max_ss |
|---|---:|---|---|
| OpenROAD | 9/9 | 3613 / 71277 | 268 / 302 |
| ICC2 b5a | 9/9 | 550 / 45120 | 163 / 168 |
| Innovus b5d | 9/9 | 351 / 28217 | 227 / 267 |

Reading (measured, from the tables above):
- Tuned vs untuned moves the numbers by 0.1 to 1.6 ns at most; e.g. ICC2 b5a nom_tt setup -0.091 (untuned) -> +0.040 (tuned), OpenROAD nom_tt +3.049 -> +3.172, OpenROAD max_ss -5.335 -> -4.326, ICC2 max_ss -15.406 -> -15.118. No arm changes sign at tt/ff except ICC2 min_tt (+0.384 -> +0.263, still met).
- Base SDC: all three arms fail setup at every ss corner (SRAM timed at TT, bead `o1i`) and fail hold at all 9 corners (I/O hold from the missing io-latency line, section 5.2); r2r-only hold is clean for OpenROAD and ICC2 at tt (see `reports/current_b5a_b5d/compact_tables.md`).
- iolat SDC (comparison-only): OpenROAD hold is met at 9/9 corners; ICC2 b5a leaves 2 to 101 hold endpoints per corner (worst -0.472 ns at max_ss); Innovus b5d meets hold at ff/tt min and fails at ss (worst -1.531 ns).
- Setup at nom_tt on the base SDC: OpenROAD +3.172, ICC2 b5a +0.040, Innovus b5d -0.617 (5 I/O endpoints, `apb_prdata_o` outputs). Different netlists and CTS; this compares the implementations as judged.
- Power (PrimePower, nom_tt, headline variant B): OpenROAD 93.13, ICC2 b5a 67.77, Innovus b5d 70.09 mW. SRAM macros equal at 29 mW; the difference is clock network and combinational power.
