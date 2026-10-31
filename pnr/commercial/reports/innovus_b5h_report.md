# Innovus b5h: capTable RC + symmetric, SDC-visible I/O latency, re-closed from the start of P&R

Tag `runs/b5h_innovus` (gitignored; tracked copies in `impl/innovus/reports/b5h/`). b5g is untouched. Same synthesized netlist and physical setup as b5f/b5g (die/core, 10 SRAM placement, 503 pins, PDN with B5F keep-outs, max met4, CTS cells, taps/endcaps, fill/decap, placement screens B5C/B5D). Only two things change: the RC corner and the I/O latency model.
Native = Innovus 23.14, tt, OCV+CPPR, SI-aware unless stated. Judge = StarRC (tuned ITF) + PrimeTime X-2025.06, SI off.

## 1. What was changed
**Fix 1, I/O latency.** `set_ccopt_property update_io_latency false` (verified: "Determine whether to update IO latencies within ccopt_design", default `true`, set in `common_settings` for every stage). Replaced by a virtual ideal clock `clk_io` (same construction as `sky130_cpu_iolat.sdc`): source latency 1.0, network latency **3.295 ns**, every `set_input_delay`/`set_output_delay` re-referenced to it. 3.295 = measured mean clock insertion delay of clk_i after CTS (Avg ID of `report_ccopt_skew_groups`, `reports/cts_skew_groups.txt`; the b5g update had used 2.909 rise / 2.652 fall = same mean 2.78 at its own tree). Pre-CTS file `constraints/sky130_cpu_innovus_pre.sdc` (clocks ideal); post-CTS file written by `04_cts.tcl` through `constraints/gen_innovus_io_sdc.py` (shared SDC md5 3c69635042a9d65cb87e71a9db713e4e asserted, never modified).
Lesson found on the way: Innovus keeps SDC clock latencies in the view's `latency.sdc` and re-applies that file AFTER the SDC on restore/`update_constraint_mode`. `update_constraint_mode` alone therefore left clk_io at the stale network latency 0 (first attempt: input hold -3.7 ns, 1176 violators, hold buffers inserted for nothing, superseded in `runs/b5h_innovus/superseded_*`). The explicit `set_clock_latency $LIO [get_clocks clk_io]` in the interactive constraint mode after the update fixes it; `reports/b5h_spot_input_hold_postcts.txt` shows `Network Insertion Delay 3.295`.
**SDC visibility check (passes).** Exported `out/rv32i_cpu_top.sdc` (md5 `42a1cffc82a8c891439a4316e9fc3113`) latency statements: `set_clock_latency -source -early/-late -min/-max 1` for clk_i and clk_io, and `set_clock_latency 3.295 [get_clocks clk_io]`. The final view `dbs/06_finish.enc.dat/mmmc/views/av_tt/latency.sdc` contains exactly the same set (sorted diff identical), nothing else, and no `-1.9` style entry. Only clk_i is propagated (`set_propagated_clock [get_clocks clk_i]`), clk_io is ideal (`report_clocks`: Propagated n).
**Fix 2, cap table.** `impl/innovus/captbl6/sky130A_nom_li1m1.captbl` (+ `.ict`) from the tuned ICT `build/tech/ict/sky130A_nom.ict` ("calibrated to OpenRCX, not silicon"). Root cause of the old rejection: `generateCapTbl` classifies the conductor named `li1` as the POLY-class layer (IMPEXT-6091) and writes M1..M5 = met1..met5, while the tech LEF has six routing layers (IMPEXT-3548 "layer M6 missing"). `scripts/mk_ict_li1m1.py` renames li1 -> met0 in a derived ICT, giving M1=li1 .. M6=met5 (+ VIA licon/mcon/via1..4); Innovus loads it in every stage via `create_rc_corner -cap_table` (`mmmc_tt.tcl`, env `CAPTBL`). Generation 56 min wall (2 workers). nom only: the Innovus flow is tt-only and the judge uses StarRC for min/max, so min/max tables were not built (script takes the corner as argument).

## 2. Native results (Innovus, nom_tt)
| Metric | b5g | **b5h** |
|---|---|---|
| verify_drc | 0 | **0** (after route 0, after post-route opt 0; no repair step needed) |
| Antenna (verifyProcessAntenna) | 4 viol / 3 nets | **1 violation** |
| PG pieces VPWR / VGND | 1 / 1 | **1 / 1** |
| verifyConnectivity regular opens / special | 144 + 1 | **144 + 1 (identical)** |
| Setup WNS / TNS (all paths) | +0.394 / 0 | **+0.215 / 0**, 0 violators (SI off: +0.323) |
| Setup reg2reg | +1.854 | +1.214 |
| Hold WNS / TNS | +0.252 / 0 | **+0.139 / 0**, 0 violators (SI off +0.139), reg2reg +0.139, default group +0.412 |
| max_cap / max_tran nets | 433 / 100 | 480 / 110 (still unrepaired: SRAM-pin / output nets) |
| Power @ default activity 0.2 | 92.65 mW | **87.52 mW** (internal 54.81 + switching 32.62 + leakage 0.095) |
| Power @ activity 0.1 (seq+PI, = PrimePower toggle) | n/a (73.2 on native RC) | **70.62 mW** (50.67 + 19.85 + 0.095) |
Worst native setup path: `apb_paddr_i[4] -> apb_prdata_o_reg[0]/D` (constrained I/O); worst hold `u_mbist_ctrl_tg_addr_q_reg[2][6] -> [3][6]` (reg2reg). The b5g repair (05g repeaters on 28 long AXI port nets, 05h) was NOT needed: with the capTable RC the AXI input paths are positive post-route (pre-opt +0.201), the b5f failure did not reproduce. Runtime: 03_place 9.4 min, 04_cts 9.5 min, 05a_route 24.6 min (host contention), 05_route 4.6 min, 06_finish 6.6 min (peak 7.0 GB).
Caveat unchanged: the 26 mbist_cfg_i/mbist_run_i inputs have no input delay in the shared SDC; Innovus times them against an undefined clock and spends hold buffers on them (post-CTS hold before opt -3.67 on them). PT does not time them. Not changed (shared SDC rule).
Not run: Conformal LEC (netlist has post-CTS/hold buffers vs Genus), DRC/LVS of b5h (follow-ups).

## 3. RC correlation, Innovus native SPEF vs StarRC tuned nom (`signoff/starrc/reports/correlation_innovus_b5h_vs_b5g_nom.md`)
| | b5g (tech-LEF RC) | **b5h (capTable)** |
|---|---|---|
| total C per net, median ratio (p5/p95) | 1.132 (0.889/1.410) | **1.056 (0.898/1.181)** |
| nets outside +-10 % | 64.9 % | 31.8 % |
| total design C (Innovus/StarRC) | 1.250 | **1.104** |
| total R per net, median | 0.797 | **1.014** (sum R 0.982) |
| r (lin) of total C | 0.9963 | 0.9985 |
Nets (StarRC fF / Innovus fF): axi_rdata_i[11] 842.9 / 974.1 (1.156), axi_rdata_i[21] 794.6 / 895.6 (1.127), axi_rdata_i[18] 770.8 / 894.5 (1.161); R within 0.4-0.7 % on all of them (b5g C ratios 1.36 / 1.18 / 1.45). Remaining +10 % in C: Innovus' rcOut writes all coupling lumped into ground (coupling 0 pF in the SPEF vs StarRC's 261 pF = 28 % of total), so the ground-C ratio 2.5 is a bookkeeping difference; total C is what PT sees (coupling to ground, factor 1.0) and Innovus' 2.5D low-effort capTable extraction is ~5-16 % high per net. R is now right.

## 4. Judge (StarRC nom/min/max on b5h DEF, PT, SI off, 9 corners, PrimePower at nom_tt)
SDC variants: shared (3c69635042a9d65cb87e71a9db713e4e), iolat (e90bdba8b93f8f4e985c5fbaa6d4ab90, clk_io 1.778), own (= Innovus b5h exported SDC, only syntax edits for PT: `current_design` line removed, `get_designs` -> `current_design`; `constraints/sky130_cpu_innovus_b5h_own_pt.sdc`). Full 27-row table `impl/innovus/reports/b5h/pt_judge_b5h_all.tsv`.
| nom_tt | shared | iolat | **own SDC** | native (SI on / off) |
|---|---|---|---|---|
| b5h setup / hold WNS | -0.456 (3v) / -2.200 (474v) | +1.322 / -0.422 (5v) | **+0.706 / +0.140, 0 violators** | +0.215 / +0.139 ; +0.323 / +0.139 |
| b5g (for reference) | -0.320 / -2.044 | +1.458 / -0.266 | (natlat SDC +1.040 / +0.120) | +0.394 / +0.252 |
Worst corner ss (max_ss): own setup -8.759 (1142v) hold -0.744; iolat -8.759 / -2.261; shared -9.761 / -4.039 (b5g shared -8.879 / -3.800, iolat -8.823 / -2.022). Closure is tt only, as for every arm (SRAM model is TT at all corners; reg2reg setup -7.77 at nom_ss is the cache path, identical between SDC variants). ff hold with own SDC: nom_ff -0.310 (11v), min_ff -0.446 (29v), on output-port hold (axi_awaddr_o[13]); tt hold is clean at nom/min/max (+0.139..+0.140).
Power (PrimePower, nom_tt, 0.1): variant B **69.5 mW**, variant A 56.7 mW (b5g 70.6 / 57.3). Native at the same activity 70.62 mW: **-1.6 %**, engines agree (b5g gap was 22 mW at default activity, 3.5 % after matching).
**Residual native-vs-judge gap with its own SDC**: hold 0.001 ns (same endpoint). Setup +0.706 vs +0.215 (SI on) / +0.323 (SI off): same endpoint (`apb_prdata_o_reg[0]/D`), 0.11 ns is SI (native SI-aware), the other 0.38 ns is extraction (Innovus native +10 % C on long nets, section 3) plus engine residual (b5g measured 0.07). INFERRED, not isolated by a swap experiment this time. Compared with b5g the gap fell from -2.9 ns (hidden latency) to 0 on hold and 0.5 ns on setup; shared-SDC and iolat judge numbers are not comparable because b5h was closed against clk_io 3.295.

## 5. Follow-ups
- b5h inherits the b5g physical issue reported by the DRC/LVS run: 144 `IMPVFC-92` regular opens + 1 special (identical to b5g): the decap_3 endcap column at x~98.4 um (y 24-911, left edge of the tag SRAM) has untied n-well/VPB. Fix = tap/endcap placement next to that SRAM edge; not done here.
- Conformal LEC and DRC/LVS of b5h not run. Antenna 1, max_cap 480 / max_tran 110 nets unrepaired.
- PT judge defects found: `run_one.sh` accepted a run whose `read_sdc` aborted (DONE with empty metrics); fixed to require non-empty setup/hold WNS. Innovus-exported SDC needs two syntax edits for PT; `read_sdc` stops at the first error and silently drops the rest.
- Host: concurrent KLayout/Magic (up to 10 GB) caused ~2 h of memory-pressure stalls (stages 5-10x slower, one Innovus update hung 38 min); StarRC and PT (0.4 / 1.2 GB) were run with a relaxed memory gate (`GATE_LIGHT=1`, MemAvailable >= 2 GB, no Magic wait), one tool at a time, <= 2 threads.
- min/max capTables not built.
