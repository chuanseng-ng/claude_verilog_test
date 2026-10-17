# Sky130 SoC CDC budget failure at the ss corners (bead j41m.5 / j41m.4)

Read-only analysis of `RUN_2026-10-17_14-07-01` (re-harden #4, buf_16 clock roots), 2026-10-17.
No flow was re-run. Source of every number: `make -C pnr check-cdc-timing-sky130-soc` reports under
`/nobackup/sky130_soc_runs/cdc_check_reports/<run>_<corner>/`, the run's step-32 `min.rpt`, and the
step-49 DEF.

## 1. What fails

`sky130_soc_cdc_check.sdc` sec. 11 budgets every `async_axi_fifo` gray-pointer crossing at 0.5x the
destination period. Both clocks are 25.0 ns (`set clock_period 25.0`, one value, correct for both
directions), so the budget is 12.5 ns each way. The SDC has no period or corner bug.

| Corner (run 14-07-01) | fifo_rd2wr | fifo_wr2rd | all other groups |
|---|---|---|---|
| nom_tt / min_tt / max_tt | +6.0 / +6.0 / +6.0 | +6.1 / +6.1 / +6.1 | MET |
| nom_ff / min_ff / max_ff | +8.1 / +8.1 / +8.0 | +8.1 / +8.1 / +8.1 | MET |
| min_ss | -0.625 | -0.431 | MET |
| nom_ss | -0.672 | -0.477 | MET |
| max_ss | -0.715 | -0.516 | MET |

Only the three ss corners fail. The `domain_wide_core2cpu` finding is not a second problem: it
reports the same worst path (the 12.5 ns per-crossing budget wins over the 22.5 ns fallback).
The 3 findings at each ss corner are one root cause. The apb_cdc_bridge and PMU/IRQ sync groups
have 12 ns or more of slack at every corner.

Failing endpoints are the core_clk-launched, cpu_clk-captured crossings only (10 of 17 per group
listed, all violated, worst -0.715 ns on `_150222_/D`). The cpu_clk-launched direction arrives in
0.7 ns and passes by 11 ns.

## 2. Why: hold padding on the crossing, not wire or placement

Worst path (max_ss): launch `_150213_` (`u_cpu_axi_cdc.u_aw_fifo.rd_bin_q[2]`, dfrtp_2) ->
10 x `dlygate4sd3_1` (1.14 to 1.35 ns each, 11.8 ns) -> capture `_150222_/D`; arrival 12.594 ns.
Clk-to-Q is 0.78 ns. Wire delay is negligible. Placement is not the cause: launch and capture
flops are 17.4 um apart, and the whole 12-cell chain is 168 um Manhattan.

The 10 cells are hold buffers (`hold*`, RSZ-0032: 18,756 inserted in step 33, 543 in step 40).
The flow STA times this path as `tck` -> `tck`: the DFT test clock enters both domain roots
through the two `dft_clk_mux` A1 inputs, so a flop in the core_clk tree and a flop in the
cpu_core_clk tree are both "clocked by tck" and the async clock group does not cover tck-to-tck.
Step-32 `min.rpt` (nom_tt): launch clock arrives at 2.93 ns, capture clock at 5.38 ns because the
capture flop sits behind `u_cpu_cg` (sdlclkp_4 + buf_16) in the cpu_gated_clk tree, so hold slack
is -2.16 ns and the resizer pads ~2.2 ns (tt). Delay cells are about 2x slower at ss, so the
same chain costs 11.8 ns there and breaks the 12.5 ns budget.

Measured: the path, the cells, the positions, the tck clocking and the -2.16 ns hold slack.
Inferred (not isolated by an experiment): that this skew is the only reason the resizer padded
this path.

## 3. Regression or pre-existing?

Both. `RUN_2026-10-16_04-53-49` (same check, same SDC) PASSES but with a thin margin and a
nine-cell chain on its worst path:

| Corner | 04-53-49 rd2wr / wr2rd | 14-07-01 rd2wr / wr2rd |
|---|---|---|
| nom_tt | +6.79 / +7.14 | +6.0 / +6.1 |
| max_ss | +0.951 / +1.677 | -0.715 / -0.516 |
| min_ss | +0.996 / +1.697 | -0.625 / -0.431 |
| max_ff | +8.6 / +8.9 | +8.0 / +8.1 |

So the gap is latent (hold padding on the crossing is not new, nom_tt hides it and the default
`CDC_CORNER` is nom_tt) and this run lost about 1.7 ns at ss. The 2026-10-09/10-11 runs predate
the CPU clock domain, so they carry no CDC budget to compare.

## 4. Options

A. Relax the check budget. Evidence: needed arrival is 12.594 + 0.3 + 0.321 = 13.2 ns, so 0.53x
passes; 0.6x (15.0 ns) gives +1.8 ns at max_ss, 1.0x (25 ns, the Cummings one-period limit) gives
+11.8 ns. Gray-code safety depends on bit-to-bit skew across a pointer (here at most ~0.55 ns
among the listed endpoints), not on absolute delay, so the functional risk is low. Cost: no
re-run, one-line SDC change; but it weakens a target the user set (0.5x OpenTitan GRAY_MAX_DELAY)
and keeps 12 ns of padding. Needs a user decision (Stage Gating item 7).

B. Stop padding the crossing (root cause, needs a re-run, about 4.4 h). In the implementation
SDC, hold-exempt the CDC capture D pins (`set_false_path -hold -to <stage-0 D pins>` for the 19
structurally found crossings, reusing the check script's net-name matching), so the resizer stops
inserting delay for an async crossing. Cost: a full flow run, an SDC edit that must be justified
for scan mode (tck shift/capture across domains) with the DFT owner (beads j41m.5/j41m.8), and a
new baseline (not single-variable).

C. Change the check, not the budget: make the default check run max_ss as well as nom_tt (the
nom_tt default hid a 0.95 ns margin), and add a per-pointer bit-skew measurement as the
Cummings criterion. Cost: small script/Makefile change, no re-run; it does not by itself clear
the failing budget, so combine with A or B.

Recommendation (analysis only, not a decision): B for tape-out quality, A as the interim record
if the schedule needs a green check, C in either case.
