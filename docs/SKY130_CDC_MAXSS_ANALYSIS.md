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

## 5. Decision (user, 2026-10-17): B + C. Implemented, flow NOT re-run

B. `pnr/sky130/soc/constraints/sky130_soc.sdc`, new block after "Clock groups": for the ten gray-pointer
synchronisers of the five `async_axi_fifo` FIFOs (`u_cpu_axi_cdc`), per bit:
`set_false_path -hold -from <opposite-domain launch flops> -to <stage-0 capture D pin>`. Setup is untouched.
It is structural (stage-0 `sync_q[0]` net -> driver = capture flop -> `get_fanin -startpoints_only` filtered by
`all_registers -clock`), the same resolver as the check SDC, so it does not depend on anonymous cell names or
on a `.` in an OpenSTA `-filter`. A miss is a hard `error` (CDC-HOLD-EXEMPT-MISS), because a silently unbound
exception would put the 11.8 ns of padding back. All three SoC configs (`config.json`, `config_rccal.json`,
`config_rccal_wl1500.json`) point `PNR_SDC_FILE`/`SIGNOFF_SDC_FILE`/`FALLBACK_SDC_FILE` at this one file, so no
config edit is needed. Deliberately NOT exempted: the apb_cdc_bridge req/ack and PMU/IRQ `cdc_sync` captures
(>= 12 ns slack at every corner, one extra table row each if ever needed) and the payload registers covered by the
section-10 fallback (the fallback `core2cpu` finding at max_ss is the same worst path and should clear with the
rest; if a payload register turns out to be padded after the re-run, extend then, with a measurement).

C. `check-cdc-timing-sky130-soc` now loops `CDC_CORNERS` (default `nom_tt_025C_1v80 max_ss_100C_1v60`,
`all` = nine, `CDC_CORNER=<one>` still wins), one `sta` at a time, FAIL on any corner, with a summary.
`check_cdc_timing_sky130.tcl` adds a per-pointer bit-skew report (section "Per-pointer bit-skew"): max minus min
data arrival at the stage-0 D pins of a pointer, clocks propagated, limit `CDC_CHECK_SKEW_FRAC` (default 0.25) x
min(source, destination period) = 6.25 ns, or absolute `CDC_CHECK_SKEW_LIMIT`. The Gray criterion's hard limit is
one source period (the pointer moves at most once per source cycle, so more spread than that can mix bits of two
updates); 0.25 is a 4x derate for OCV, jitter and the corner spread a single SPEF measurement cannot see.

## 6. Scan-mode hold: the approach chosen, and what is NOT verified

The tck -> tck race is fictitious in functional mode and real in scan capture, where one test clock reaches both
trees (DFT_ARCHITECTURE.md 9.3). Options considered:

| Option | Fixes functional padding | Keeps scan hold safe | Cost / verdict |
|---|---|---|---|
| `set_false_path -hold` limited to functional clocks | no change: core->cpu is already in the async group; the padded path IS tck->tck | n/a | meaningless here |
| Scan-mode-only SDC/corner in LibreLane | needs a second constraint set | yes | LibreLane Classic has one SDC per corner, no MMMC; a second set is a post-route standalone STA, not a repair |
| Lock-up latch | no | no | fixes the Q->SI chain hop between domains, not the functional D path of a crossing; still needed at chain joins (Stage 2) |
| Exclude stage-0 flops from scan | yes | no | they still sample a live pointer during shift, so they are X and X-propagate into FIFO flags; costs coverage on 34 flops |
| Balance the ICG/trees in CTS | partly | partly | two independent roots; skew is inherent, balancing async trees is a CTS research item |
| Exemption + masked capture + scan-view measurement (CHOSEN) | yes | residual, see below | no area, no RTL change, deterministic |

Chosen: exempt in the functional implementation (above), and keep scan hold on a separate, explicit footing:
1. The same file re-sourced with `CVT_SDC_SCAN_VIEW=1` skips the exemption, i.e. the scan-mode view of the same
   crossings (hold kept on tck -> tck). It is the single source for the scan-mode measurement, so it cannot drift
   from the functional list. The flow never sets it.
2. A hold failure on these 34 pins in scan capture can only corrupt the captured value of the stage-0 flops (a
   test-response mismatch). It cannot corrupt the FIFO state functionally and cannot occur in functional mode.
   The test protocol therefore has to treat the 34 stage-0 capture flops as masked in the expected response (or
   hold the pointer registers across the capture cycle). Cost: 34 flops lose capture observability for faults on
   their own D path.
3. UNVERIFIED until Stage 2 (j41m.8) inserts chains and a real scan-mode SDC exists: (a) the scan-capture hold
   slack of these pins on a post-fix netlist (measurable with the scan view; before the fix it was -1.369 ns
   post-CTS without parasitics, -2.16 ns with, and +2.12 to +3.66 ns after the resizer padded it); (b) that
   the stage-0 flops are actually masked in the pattern set (there is no X-masking engine in the open ATPG tools,
   DFT_ARCHITECTURE.md section 2.4); (c) the capture sequencing per domain, which is hand-written. Bead j41m.8
   owns this; do not read "scan hold safe" from this change.

## 7. Evidence (RUN_2026-10-17_14-07-01, read-only; one STA at a time)

Binding of the exemption (OpenSTA `sta` and the flow's own `openroad`, nom_tt, clocks propagated; endpoints =
distinct hold-checked endpoints from `report_checks -path_delay min -format end`):
- Synthesis netlist, post-CTS netlist/ODB, and post-repair fill netlist + nom SPEF: the SDC exempts **34 pins**
  (10 synchronisers: bits 3,3,3,3,3,3,4,4,4,4), identical to the 34 capture D pins the check SDC budgets
  (`fifo_rd2wr` 17 + `fifo_wr2rd` 17).
- Hold endpoints, exemption off (scan view) vs on: 19341 -> 19307 (CTS netlist) and 19341 -> 19307 (final).
  The 34 removed endpoints are exactly the exempt list (set equality), none added, 0 changed slack on the rest,
  and a repeat is bit-identical.
- Before the fix the removed endpoints had hold slack -1.369 .. +1.848 ns at post-CTS (17 of 34 negative) and
  +2.123 .. +3.663 ns on the padded final netlist (the buffers the exemption stops).
- Negative control: bogus instance token -> "no stage-0 net matched"; launch clock wrong -> "no core_clk launch
  flop" (3 bits); both clocks swapped -> "no cpu_clk capture flop D pin" (3 bits): 7 misses, 0 pins bound. In the
  SDC any miss is a hard error.

New check on the existing run, `make -C pnr check-cdc-timing-sky130-soc` (default corners):
- nom_tt: PASS (fifo_rd2wr +5.994, fifo_wr2rd +6.089 ns).
- max_ss: FAIL, as expected for a run that predates the fix (fifo_rd2wr -0.715, fifo_wr2rd -0.516 ns,
  `core2cpu` fallback is the same path). The default now catches what the nom_tt default hid.
- Bit skew, all 10 pointers, both corners: 0.014 to 0.512 ns (max `u_aw_fifo.rd2wr` 0.512 ns at max_ss) against a
  6.25 ns limit. A limit of 0.1 ns flags 3 of 10 pointers at nom_tt (the check can fail). The padding chains
  inflate arrival, not spread, so skew is not the failure mode here.

Open (at the time of section 7): the re-harden that proves the fix had not been run. Section 8 is that run.

## 8. Re-harden #5 with the hold exemption: RUN_2026-10-17_23-06-56 (measured, 2026-10-18)

`make -C pnr librelane-sky130-soc-noklayout` (rccal default, KLayout DRC skipped), origin tip `e47709e`, 12 GB cgroup cap,
about 4 h 26 min wall. Not a single-variable comparison with 14-07-01 (hold repair differs wherever the 34 pins fed), but the
only intended input change is the `set_false_path -hold` on the 34 stage-0 capture D pins.

Binding (early check): `INFO: CDC-HOLD-EXEMPT: 34 gray-pointer capture D pins exempt from hold (10 synchronisers)` in every
SDC load (9 prepnr corners, floorplan, global/detailed placement, CTS); no `CDC-HOLD-EXEMPT-MISS` anywhere in the run dir.

| Gate | 14-07-01 (before) | 23-06-56 (this run) |
|---|---|---|
| LVS | PASS | PASS (0 errors) |
| Routing DRC | 0 | 0 (iterations 61879, 23674, 20711, 1491, 30, 1, 0) |
| Magic DRC | 8984 (deferred, waived `45a`) | 8984 (same) |
| Antenna nets / pins | 225 / 312 | 198 / 257 |
| Setup violators, 9 corners | 0 | 0 |
| Hold violators, 9 corners | 0 | 0 (worst +0.2704 max_ff, +0.4742 nom_tt, +0.5013 max_ss; before +0.2731 worst) |
| `CVT.MaxCapViolations` (empty waiver list) | PASS | PASS, 0 waived / 0 unwaived, 9 corners |
| Hold buffers (`design__instance__count__hold_buffer`) | 543 | 488 |
| `dlygate4sd3_1` in the fanin cone of the 34 pins | 170 | 0 |
| `dlygate4sd3_1` whole design | 19246 | 19094 |
| CDC check nom_tt + max_ss (default) | max_ss FAIL (-0.715 / -0.516 ns) | PASS both |
| CDC check, all 9 corners (`CDC_CORNERS=all`) | not run | PASS all 9 |
| `make -C pnr dft-scan-check` | 0 | 0 violations |

Notes on the table. "Setup worst slack" prints 0.0 in LibreLane's summary for both runs: that is the latch time-borrow paths
(4 inferred latches), not a margin. The smallest non-zero setup slack in `max.rpt` is +3.136 ns at max_ss (+3.060 before).
Setup/hold violator counts are what gate.

CDC budget groups after the fix: `fifo_rd2wr` and `fifo_wr2rd` worst slack +11.69 / +11.71 ns at nom_tt and +11.09 / +11.14 ns at
max_ss, on a 12.5 ns budget, so the crossing datapath is about 1.4 ns at max_ss (was -0.715 slack). Worst over all nine corners
+11.094 ns. All other groups MET at both default corners.

Bit skew, all 10 pointers: nom_tt 0.014 to 0.103 ns, max_ss 0.028 to 0.196 ns (limit 6.25 ns); over all nine corners the
maximum is 0.196 ns.

Clock root cells survive CTS (no CTS-0105 in this run, 0 in 14-07-01 too): `buf_16` x3 (`u_cpu_cg.g_cell.u_root_buf`,
`u_cpu_pll_sub.u_ref_cm.u_root_buf`, `u_pll_sub.u_ref_cm.u_root_buf`), `sdlclkp_4` x1 (`u_cpu_cg.g_cell.u_icg`), `mux2_4` x2
(`u_ref_cm.u_mux`, cpu and fabric). CTS built trees on core_clk (17784 sinks), cpu_core_clk, tck_i and dft_test_clk.

### Scan-view hold on the 34 pins (information for Stage 2, NOT a pass/fail)

Standalone OpenSTA on the final fill netlist and nom SPEF, the flow's own `sky130_soc.sdc` with `CVT_SDC_SCAN_VIEW=1` (no
exemption), all clocks propagated, nom_tt Liberty. Script: the same endpoint list the SDC builds (stage-0 `sync_q[0]` D pins).
- 17 of 34 pins VIOLATE hold on tck -> tck: slack -3.086 to -3.240 ns (worst `_150140_/D`: launch clock latency 3.308 ns,
  capture 6.748 ns, data 0.319 ns clk->Q, no logic in between). The other 17 are MET at +3.523 to +3.634 ns (opposite domain
  direction, capture tree earlier than launch). Setup in the same view: +95.8 ns or better (tck period).
- Before the fix the resizer had padded these with 170 `dlygate4sd3_1`; with the same standalone STA on 14-07-01 the same pins
  show +2.123 ns hold. So the exemption trades a hidden scan-mode hold failure for a functional-mode non-padding. The 17 failing
  pins are the whole tck-skew exposure of section 6 (core vs cpu tree insertion delay differs by about 3.4 ns), now measured at
  -3.24 ns worst on a post-route netlist, i.e. worse than the -2.16 ns (with parasitics, pre-padding) quoted in section 6.
- Nothing here changes the section 6 conclusion: masking the 34 stage-0 flops in the capture response (or holding the pointers
  across capture) remains the Stage 2 (bead j41m.8) obligation, and "scan hold safe" is still NOT claimed.
