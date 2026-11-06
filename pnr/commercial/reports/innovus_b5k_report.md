# Innovus b5k: round-2 in-place ECOs on b5j (no re-place, no re-CTS)

Tag `runs/b5k_innovus` (gitignored). Start = b5j's `05j_taps` db; b5h/b5j/b5g untouched. capTable rc_nom, `update_io_latency false`, clk_io 3.295 ns kept (the b5k SDC carries the same statements). Run 1 of the finish/verification (antenna diodes left overlapping cells) is superseded and not used anywhere below.

## 1. What was done (in order, each measured before the next)
| # | Step | Result |
|---|---|---|
| 8 | min/max capTables (`mk_ict_li1m1.py` ICT trick, no Techgen/Quantus), `rc_min`/`rc_max`, delay corners dc_tt_max/dc_ff_{nom,min,max}, views av_tt, av_tt_max (setup) + av_tt, av_ff_nom/min/max (hold) | works post-restore. **Trap:** Innovus keeps clock latencies in each view's `latency.sdc`, not in the mode SDC; a new view starts EMPTY, so clk_io latency was 0 and hold read -1.8 ns / setup -2.4 ns (first attempt, wrong). Fix: `create_analysis_view -latency_file constraints/sky130_cpu_innovus_b5k_latency.sdc` (= av_tt's file). Baseline then: hold nom_ff -0.124, min_ff -0.283, max_ff +0.024; setup tt +0.215, tt_max -0.437 (9 violators; StarRC/PT says max_tt +0.214, so Innovus' new max capTable is ~0.65 ns more pessimistic) |
| 6 | 26 mbist inputs (`mbist_run_i`, `mbist_cfg_i[25:0]`) | `set_input_delay -clock clk_io -max 2.0 / -min 0.5`, the synchronous class (RTL `rv32i_cpu_top.sv:113-120`: CPU-domain holding register, same clock source, "ordinary sync-to-clk_i"), so timed, not false-pathed. `gen_b5k_sdc.py` appends them to the post-CTS SDC; exported SDC has 54 mbist lines. Spot path mbist_cfg_i[5] setup +3.23 |
| 7 | multi-corner hold ECO (`optDesign -postRoute -hold`, 4 hold views) | ff hold min_ff -0.283 -> -0.001, nom_ff -0.124 -> +0.022; tt setup 0.215 -> 0.213; DRC 0 (no loop needed) |
| 5 | max_cap / max_tran | `optDesign -postRoute -drv`: max_tran pins 845 -> 396. Remaining max_cap was 102 input-PORT nets (limit 0.561 pF = the set_driving_cell buf_4), 160 SRAM dout0 pins (macro Liberty limit, bead o1i, NOT fixable here) and 1 other; max_fanout 205 = CTS clock-tree buffers (exempt by design). One `buf_8` repeater on each violating input-port net (13 + 95 = 108, `ecoAddRepeater`, ecoRoute): max_cap nets 493 -> 378 (terms 496 -> 381), max_tran nets 431 -> 122 (terms 845 -> 411); **side effect: tt setup +0.213 -> +0.464 and tt_max -0.440 -> +0.065, 0 violators**; DRC 0. Left: SRAM output pins, repeater/diode input slews on port nets |
| 2 | KLayout m3.6 (54) | each is a lone 0.33x0.33 um met3 via pad at a die-edge pin (the pin rectangle is pin-purpose in the GDS; Innovus counts the pin shape so verify_drc is blind to it). `add_shape -layer met3 -net N -rect {...}` adds a met3 special wire from the pad to the die edge (`create_shape` does not exist, `editAddRoute` silently does nothing in 23.14). 54/54 added, DRC 0. KLayout m3.6: 54 -> 0 |
| 3 | KLayout npc.2 (6) | root cause measured: **every `and2_0` placed S/FN (x-mirrored) with a decap cell on its right violates (6 of 6); the 18 N/FS ones are clean.** Fix in `06k_finish.tcl` (`NPC2FIX=1`): replace that one decap by device-free fill (decap_8->fill_8, decap_4->fill_4, decap_12->fill_8+fill_4). 6 cells replaced; KLayout npc.2: 6 -> 0 |
| 4 | antenna | `verifyProcessAntenna` has no side-area switch (help: `-detailed -error -reportfile`; `setAntennaMode` does not exist), so its count (1) cannot be reconciled with the deck-style check (OpenROAD `check_antennas`, ANTENNASIDEAREARATIO): all 8 violators on the b5k pre-fill DEF are SIDE-AREA ones (met2/met3/met4). `attachDiode` (diode_2) on those 8 gate pins + **`refinePlace` before ecoRoute** (without it the diodes overlapped neighbours: 45 KLayout licon/li hits, 19 checkPlace violations, LVS nets 35,684 vs 35,688 - run 1, superseded) -> deck violators 8 -> 3; a second diode on the 3 remaining pins changed nothing (not used). Final deck count 2 |
| 9 | Magic nwell.4 reclassification | NOT RUN (user decision: Magic DRC only on b6) |

## 2. Table b5h -> b5j -> b5k
| Metric | b5h | b5j | **b5k** |
|---|---|---|---|
| untied n-well islands | 146 | 0 | 0 |
| Instances (incl. physical) | 462,049 | 462,195 | 462,702 (+108 buf_8 repeaters, +110 diode_2, +1 dlygate/hold changes, 6 decap->fill) |
| Native verify_drc | 0 | 0 | 0 |
| Native antenna (verifyProcessAntenna) | 1 | 1 | 1 |
| Signoff-deck antenna (OpenROAD) | n/a | 10 nets | **2 nets** (FE_PDN241_mbist_status_o_51 met4 side; CTS_152 CLK met2 side) |
| Native setup WNS, SI on (all active views) | +0.215 | +0.215 | **+0.065** (tt nom +0.464, tt max +0.065; SI off +0.223) |
| Native hold WNS | +0.139 | +0.139 | **+0.011** (tt +0.139, ff_nom +0.022, ff_min +0.011, ff_max +0.024) |
| Power @ activity 0.1 | 70.62 mW | 70.62 mW | **71.73 mW** (50.81 + 20.83 + 0.095; more buffers/diodes) |
| Native max_cap nets (max view) | 480 (tt) | n/a | 493 -> **378** (160 of the pins are SRAM outputs) |
| Native max_tran nets | 110 (tt) | n/a | 431 -> **122** |
| Netgen LVS, GDS-mode | not run | devices 34,255 = 34,255; nets 35,214 = 35,214 | **devices 34,800 = 34,800; nets 35,688 = 35,688**; top-level pin matching fails only on 3 netlist `assign` pairs (axi_awlen_o[1], axi_arlen_o[1], axi_arburst_o[0]) + layout-only VPWR/VGND |
| KLayout DRC | b5g 482 | 60 (m3.6 54, npc.2 6) | **0** |
| Magic DRC | b5g 28,320,643 | not run | not run (user decision: b6 only) |
| Conformal LEC | never | EQUIVALENT 4/4 negctl | **EQUIVALENT 4/4 negctl** (5,597 points) |
| PT judge, own SDC nom_tt setup / hold (power) | +0.706 / +0.140 (69.5 mW) | identical | **+1.006 / +0.140 (70.5 mW)** |
| own, min_tt / max_tt setup | +1.066 / +0.214 | identical | **+1.315 / +0.456** |
| own, nom_ff hold (viol) | -0.310 (11) | identical | **-0.013 (3)** |
| own, min_ff hold (viol) | -0.446 (29) | identical | **-0.159 (27)** |
| own, max_ff hold (viol) | -0.129 (2) | identical | **+0.023 (0)** |
| own, ss corners (SRAM tt-only) | nom_ss -7.77/-0.46, min_ss -7.03/-0.24, max_ss -8.76/-0.74 | identical | -7.83/-0.50, -7.10/-0.28, -8.83/-0.79 (setup worse by 0.07: more buffers on the ss path; ss out of scope, bead o1i) |
| shared SDC nom_tt setup / hold (viol) | -0.456 / -2.200 (474) | identical | -0.594 / -2.224 (510) |
| iolat SDC nom_tt setup / hold (viol) | +1.322 / -0.422 | identical | +1.184 / -0.446 (5) |

All 27 judge runs completed (own 9, shared 9, iolat 9); b5j == b5h in all 27.

## 3. Limits and follow-ups
- **Hold at ff in the judge is not closed** (own SDC: nom_ff -0.013 / 3 violators, min_ff -0.159 / 27 violators, all output-port hold paths such as `u_dcache_wb_tag_q_reg[15] -> axi_awaddr_o[27]`), although Innovus' own views read +0.011..+0.024. Innovus and PT disagree by ~0.17 ns at ff (b5h/b5j tt hold agreed to 0.001). Next step: repeat the hold ECO with `setOptMode -holdTargetSlack 0.2`, then re-finish and re-verify.
- Innovus' new max capTable is pessimistic vs StarRC (tt_max setup -0.437 before the repeaters vs judge +0.214); the repeater fix cleared it in both.
- Deck antenna 2 nets remain (side-area on long met4/met2 wires): need a reroute / layer hop, diodes do not help.
- max_cap on the 160 SRAM dout0 pins and slew on port-net repeater/diode pins stay (macro Liberty limits, bead o1i); max_fanout 205 are CTS buffers.
- Magic DRC / nwell.4 reclass: b6 only.
