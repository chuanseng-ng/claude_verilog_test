# sky130_soc.sdc — Timing constraints for SoC Stage 2 (Sky130A, 40 MHz)
#
# ############################################################################
# CURRENT CONTRACT (2026-07-31, adopted run RUN_2026-07-30_06-42-17):
#   clock_period          = 25.0 ns (40 MHz)   <- set below, line ~205
#   TIMING_VIOLATION_CORNERS = ["*"]           <- all 9 corners gated
#   Result: hold clean at all 9 corners; setup clean at tt/ff; setup STILL
#   FAILS at ss (max_ss -4.643 ns) -- tracked as bead ujv, DEFERRED
#   host-blocked 2026-07-31 (honest ss closure needs per-corner SRAM
#   characterization; bead o1i measured that as infeasible on this host).
#   Stage 2 closed on that basis as a typical-corner (nom_tt) sign-off.
# Everything below this block describing 75 MHz / 65 MHz / nom_tt-only
# gating is HISTORICAL CONTEXT ONLY. Do not read it as the current target.
# ############################################################################
#
# --- HISTORICAL (2026-07-24, superseded) ---
# GH #104 (2026-07-24): clock target relaxed from 75 MHz (13.333 ns) to
# 65 MHz (15.385 ns) per user decision, after the sign-off run
# (RUN_2026-07-24_09-58-19) showed nom_tt setup WNS -1.069 ns at 75 MHz
# (single CPU-macro-internal-boundary violator). The added +2.051 ns of
# slack is expected to close nom_tt/max_tt setup but NOT the slow
# (ss) corners -- see memory/pd/run_state.md for the full analysis.
# That 65 MHz value was itself superseded on 2026-07-31: it did NOT close
# ss (WNS -8.902 ns), and relaxing to 25.0 ns only improved ss to
# -4.643 ns because path delay scales with period at ~0.52 ns/ns.
# Extrapolated closure is ~29 MHz -- a two-point lower bound, not a
# validated target. See bead ujv.
#
# *** KNOWN LIMITATION (GH #104): THE SRAM MACRO IS STILL NOT
# CHARACTERIZED PER-CORNER. The CPU macro NOW IS (fixed 2026-07-25). ***
#
# STATUS AS OF 2026-07-25 (RUN_2026-07-25_13-29-40):
#   - rv32i_cpu_top: FIXED. config.json now maps 9 EXACT corner keys to 9
#     genuinely distinct per-corner Liberty views in pnr/sky130/cpu/macro/.
#     Those views already existed -- the Stage-1 run's OpenROAD.STAPostPNR
#     step wrote all nine; only nom_tt had ever been staged, and the config
#     wildcarded it to every corner. VERIFIED from each corner's own
#     sta.log: nom_ss_100C_1v60 now reads rv32i_cpu_top__nom_ss_100C_1v60.lib,
#     and all 9 corners load their own matching file.
#   - sky130_sram_4kbyte_1rw1r_32x1024_8: STILL nom_tt-only. Its lib entry
#     is deliberately still {"*": [<the one TT_1p8V_25C file>]}, so its
#     internal timing arcs remain corner-invariant for every reported
#     corner. This macro is now the SOLE source of this limitation.
#     Tracked as GH #120 / bead claude_verilog_test-o1i (P3).
#
# WHAT THE FIX ACTUALLY REVEALED -- the prior speculation was WRONG on
# the hold direction, and this matters:
#   The earlier version of this header reasoned that ss SETUP was
#   optimistic (correct) but ss HOLD was PESSIMISTIC, i.e. that the
#   max_ss -0.0708 ns residual on u_cpu/axi_bready_o was "plausibly
#   better in real silicon". With genuine per-corner CPU libs, hold got
#   WORSE, not better:
#       max_ss  hold WS: -0.0708 ns -> -0.3997 ns (2 paths -> 3)
#       nom_tt  hold WS: +0.1807 ns MET -> -0.0923 ns VIOLATING
#       max_ss setup WS: -5.3197 ns -> -10.4730 ns (TNS -98.5 -> -252.6)
#   So the wildcard was optimistic in BOTH directions, not offsetting.
#   nom_tt SETUP still passes (+0.2413 ns), but nom_tt HOLD no longer does.
#
#   ATTRIBUTION CAVEAT: that comparison run changed TWO things at once --
#   per-corner CPU libs AND the newly-enabled antenna repair, which
#   inserted 2018 diodes and thereby perturbed routing and timing. The
#   deltas above CANNOT be cleanly attributed to the corner libs alone.
#   Isolating them would need a third run with libs-only.
#
#   Paths entirely within flat standard-cell logic ARE corner-accurate,
#   since sky130_fd_sc_hd genuinely varies per corner.
#
# SCOPE OF THIS SIGN-OFF: still a TYPICAL-CORNER (nom_tt) TIMING SIGN-OFF,
# because one macro remains single-corner. It is NOT a validated
# multi-corner timing sign-off and MUST NOT be recorded as one anywhere
# downstream.
#   UPDATE 2026-07-31 (adopted run RUN_2026-07-30_06-42-17): the "even
#   nom_tt now carries a hold violation" clause that used to appear here
#   is SUPERSEDED. That violation was root-caused to the clk_i
#   set_driving_cell issue (bead y7v, see FIX 2026-07-26 below) and the
#   adopted run reports hold clean at all 9 corners. The scope statement
#   itself still stands: "hold clean at all 9 corners" is a statement
#   about 9 corner LABELS, not 9 independently characterized macro
#   models. The SRAM macro's timing arcs are identical in all nine.
#
# REMAINING REAL FIX: SPICE-characterize the SRAM macro per corner
# (analytical_delay=False, nominal_corner_only=False). This would also fix
# the macro's internal_power tables, which OpenRAM's analytical model
# emitted as ~1.99e11 and which are currently ZEROED in the staged .lib --
# see that file's header. GH #120 / bead claude_verilog_test-o1i.
#
# FIX 2026-07-26 (bead claude_verilog_test-y7v): the nom_tt hold violation
# reported just above (-0.0923 ns, apb_paddr_i[4] -> u_cpu) was root-caused
# to set_driving_cell [all_inputs] also covering clk_i with the same weak
# buf_4 used for data inputs -- min.rpt showed this cost the clock port
# 886 ps of delay / 1.218 ns slew before CTS's clkbuf_16 root buffer even
# entered the picture, inflating capture-clock latency and, 1:1, every
# downstream hold requirement. clk_i is now excluded from the buf_4
# set_driving_cell line and given its own -lib_cell clkbuf_16 (matches
# CTS_ROOT_BUFFER in config.json) so the clock source model is neither an
# ideal zero-slew source (optimistic) nor buf_4 (spuriously weak for a
# clock pin). See RUN_2026-07-25_13-29-40 min.rpt for the violator detail.
#
# VERIFIED (RUN_2026-07-26_09-36-48): the clk_i change alone is worth
# +0.362 ns of hold slack at the worst endpoint, measured at post-CTS STA
# (step 32) before any hold repair runs: -1.3339 -> -0.9723 ns WS,
# TNS -51.02 -> -34.38. Final nom_tt hold closed at +0.1354 ns (was
# -0.0923). It is SETUP-NEUTRAL: steps 32 and 34 setup WS match the
# baseline to 6 decimal places (4.190165/4.190166, 4.933771/4.933770),
# as expected -- common clock latency cancels on reg-to-reg paths, so
# reducing it moves hold only.
#
# RESOLVED 2026-07-26 by RUN_2026-07-26_16-05-43. nom_tt_025C_1v80 now closes
# BOTH: setup +1.38729 ns (TNS 0.0), hold +0.14439 ns, violator list EMPTY.
# LVS "Circuits match uniquely". Full series:
#     RUN_2026-07-25_13-29-40 baseline:             hold -0.0923 FAIL | setup +0.2413 MET
#     RUN_2026-07-26_09-36-48 clk fix, margin 0.15: hold +0.1354 MET  | setup -1.6877 FAIL
#     RUN_2026-07-26_12-43-06 clk fix, margin 0.05: hold +0.1453 MET  | setup -1.4304 FAIL
#     RUN_2026-07-26_15-38-37 + postGRT repair:     DIED step 37, RSZ-0090
#     RUN_2026-07-26_16-05-43 + SRAM max_trans fix: hold +0.1444 MET  | setup +1.3873 MET
#
# TWO fixes were needed, not one:
#   (1) the clk_i driving-cell change described below -- closes hold;
#   (2) RUN_POST_GRT_DESIGN_REPAIR true in config.json, which required
#       raising the SRAM macro .lib max_transition 0.04 -> 0.5 because 40 ps
#       is unachievable in sky130_fd_sc_hd and OpenROAD hard-aborts with
#       RSZ-0090 -- closes setup. See that .lib's header for the tradeoff.
#
# PROOF the setup fix hit the real defect rather than a lucky placement
# reshuffle: the offending net returned to baseline values.
#     u_cpu/axi_araddr_o[18]  broken:   fanout 2, cap 0.625885, clk->Q 5.572786
#                             fixed:    fanout 1, cap 0.019504, clk->Q 4.544736
#                             baseline: fanout 1, cap 0.019349, clk->Q 4.544564
# Setup also finished +1.15 ns BETTER than baseline, because post-GRT design
# repair fixed other over-cap/over-slew nets that had gone unrepaired for the
# whole Stage-2 history while that step was disabled.
#
# COST: antenna regressed. Pin violations across the series ran
# 154 -> 152 -> 144 -> 164; the repair buffers added ~20 over the best run and
# 10 over baseline. Antenna was already FAILED in every run; tracked on bead
# claude_verilog_test-58q. DRC unchanged: KLayout 4 (known macro-internal),
# Magic 9081 (known artifact class).
#
# The historical analysis below is retained because it documents two wrong
# diagnoses that cost runs -- do not repeat them.
#
# The setup violator throughout was u_cpu/axi_araddr_o[18] -> u_cpu/axi_arready_i.
#
# GRT_RESIZER_HOLD_SLACK_MARGIN WAS NOT THE CAUSE. An earlier revision of
# this header blamed the 0.05 -> 0.15 margin raise; RUN_2026-07-26_12-43-06
# put it back to 0.05 and DISPROVED that:
#     step-40 setup: 4.0600 baseline | 3.2044 at margin 0.15 | 3.0776 at 0.05
#     step-40 hold : 0.2620799207389556 at BOTH 0.15 and 0.05 -- bit-identical
# The knob moved neither hold nor setup in the direction claimed; setup at
# step 40 is if anything worse at 0.05. Margin is left at 0.05 (the default)
# because nothing justifies deviating, NOT because it fixes anything.
#
# ACTUAL MECHANISM (RUN_2026-07-26_12-43-06 max.rpt, same path both runs):
# the clock half behaves correctly -- launch and capture clock both drop
# 0.588 ns and cancel exactly, as reg-to-reg through one macro clock pin
# must. The loss is 1.672 ns of DATA path, and 1.028 ns of that is the CPU
# macro's own clk->Q arc inflating because its output net exploded:
#     u_cpu/axi_araddr_o[18]  fanout 1 -> 2, cap 0.019349 -> 0.625885 pF
#                             slew 0.0425 -> 1.6868 ns
#                             clk->Q 4.5446 -> 5.5728 ns
# The CPU is a hard macro with fixed output drive, so that load lands
# directly on its delay arc with no resizing possible.
#
# WHY THE NET CHANGED: cascade, not a direct effect of the clock model.
# Better hold slack -> post-CTS hold repair inserts different buffers ->
# different placement -> different GRT -> antenna violations 556 -> 558 and
# diodes 2018 -> 2039 -> this net picked up a second, distant sink and a
# long route. A diode's own load is ~0.005 pF and cannot explain 0.36 pF;
# the wire length does.
#
# CONTEXT: this is the SAME path that forced 75 -> 65 MHz (GH #104) and that
# GH #123 measured at 8.83 ns of crossbar fabric across 20 driver stages.
# Baseline's +0.2413 ns is 1.6% of the 15.385 ns period -- the path has
# always been critically marginal and routing-sensitive, so a placement
# reshuffle flips it. RUN_POST_GRT_DESIGN_REPAIR was false and
# Checker.MaxSlewViolations / MaxCapViolations are skipped, so nothing in the
# flow was repairing that 1.687 ns slew / 0.626 pF cap. Enabling that step is
# what fixed it -- see the RESOLVED block at the top of this section.
#
# DO NOT record either configuration as a sign-off: one fails hold, the
# other fails setup, both at nom_tt. Tracked on bead claude_verilog_test-y7v.
#
###############################################################################
# 2026-07-29 (bead claude_verilog_test-58q, coordinator-directed scope change):
# CLOCK RELAXED 65 MHz (15.385 ns) -> 40 MHz (25.0 ns), AND
# TIMING_VIOLATION_CORNERS WIDENED FROM ['*tt*'] TO ['*] (all 9 corners
# gated: nom/min/max x tt/ss/ff).
#
# Manufacturability.rpt for RUN_2026-07-27_17-15-57 (65 MHz, tt-only gate)
# showed the ss corner genuinely fails setup by WNS -8.902 ns -- the *tt*-only
# gate in prior runs hid this from the Checker.SetupViolations/HoldViolations
# gates, reporting only a tt-clean, non-multi-corner sign-off. Root cause is
# NOT this SDC or the SoC fabric: it is the CPU macro's own clk->Q arc, which
# per bead 1ls / GH #123 is 8.16 ns at ss vs 4.55 ns at tt (9-corner CPU libs,
# commit 86e89c1) -- a macro-internal characteristic, out of scope for an SoC
# ECO to fix (no RTL, no macro re-timing here).
#
# PERIOD CHOICE: arithmetic minimum to close ss with the OLD 15.385 ns
# critical-path delay would be 15.385 + 8.902 = 24.287 ns (41.17 MHz). That
# assumes the ss critical-path delay is invariant under period relaxation,
# which it is not -- loosening the period lets the resizer legally downsize
# drive strength on non-critical cells it previously had to oversize, and
# delays on marginal paths typically grow back somewhat when that happens
# (observed directly in this project's own history: the 65->75 MHz tightening
# in bead 1ls moved delays on the SAME araddr[18]/awlen critical path by
# hundreds of ps purely from resizer/placement response to the new budget).
# 25.0 ns (40 MHz) was chosen to give ~0.7 ns of headroom over the naive
# arithmetic minimum for that effect, without over-relaxing and losing
# frequency for no reason.
#
# CAVEAT ON SS-CORNER CONFIDENCE: the CPU macro now has real 9-corner
# characterisation (commit 86e89c1), but the SRAM macro
# (sky130_sram_4kbyte_1rw1r_32x1024_8) remains single-corner analytical
# (TT_1p8V_25C only, wildcarded to all 9 corner keys -- GH #120 / bead
# claude_verilog_test-o1i, SPICE per-corner characterisation measured NOT
# feasible on this host, ~80-95 h for 3 corners). Every ss/ff number that
# touches SRAM read/write timing through this run therefore carries
# unquantified model error in the SRAM's contribution specifically; only the
# CPU macro and the flat sky130_fd_sc_hd fabric are corner-accurate. This
# sign-off is "all 9 corners gated" but NOT "all 9 corners independently
# verified at the macro level" -- report both facts, do not conflate them.
###############################################################################
#
# Single clock domain: core_clk = 25.0 ns (40 MHz).
# CPU is a hard macro with its own characterised timing arcs in the .lib;
# path analysis through the CPU macro boundary uses those timing arcs.
#
# set_driving_cell matches Stage-1 CPU SDC (buf_4) for all DATA inputs so
# that input-slew assumptions are consistent with the CPU macro timing
# model. clk_i is excluded and driven by clkbuf_16 instead (see FIX above).

set clock_period 25.0

###############################################################################
# Primary clock
###############################################################################
create_clock \
    -name core_clk \
    -period $clock_period \
    [get_ports clk_i]

set_clock_uncertainty -setup 0.300 [get_clocks core_clk]
set_clock_uncertainty -hold  0.150 [get_clocks core_clk]

###############################################################################
# Load and drive modelling
#
# Bead claude_verilog_test-y7v (2026-07-26): clk_i was previously swept into
# set_driving_cell [all_inputs] along with buf_4, the same weak driver used
# for real data inputs. min.rpt (RUN_2026-07-25_13-29-40) showed this cost
# the clock port 886 ps of delay with a 1.218 ns slew (fanout 5, cap 0.4516
# pF) before CTS's own clkbuf_16 root buffer ever got involved — a pure
# weak-driver modelling artifact that inflates capture-clock latency and,
# 1:1, the hold requirement at every downstream endpoint. Excluded clk_i
# here using the same "_in_timed = all_inputs minus clk_i" idiom already
# used below for set_input_delay (STA-0441), computed once and reused by
# both. clk_i now gets its own driving cell: sky130_fd_sc_hd__clkbuf_16,
# matching CTS_ROOT_BUFFER in config.json — modelling the clock source as
# "driven by the same strength buffer CTS will use as its root", not a
# zero-slew ideal source (optimistic) and not buf_4 (spuriously weak for a
# clock pin). Data inputs keep buf_4 — Stage-1 CPU SDC uses buf_4 and this
# file matches it deliberately (see header).
###############################################################################
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i"} {
        lappend _in_timed $_p
    }
}

set_driving_cell \
    -lib_cell sky130_fd_sc_hd__buf_4 \
    -pin X \
    $_in_timed

set_driving_cell \
    -lib_cell sky130_fd_sc_hd__clkbuf_16 \
    -pin X \
    [get_ports clk_i]

set_load 0.1 [all_outputs]

###############################################################################
# Input / output delays (20% of period for setup, 5% for hold)
# Exclude clk_i from set_input_delay — STA-0441: input delay on clock port
# not allowed. Reuses $_in_timed computed above.
###############################################################################
if {[llength $_in_timed] > 0} {
    set_input_delay  [expr $clock_period * 0.20] -clock core_clk -max $_in_timed
    set_input_delay  [expr $clock_period * 0.05] -clock core_clk -min $_in_timed
}
set_output_delay [expr $clock_period * 0.20] -clock core_clk -max [all_outputs]
set_output_delay [expr $clock_period * 0.05] -clock core_clk -min [all_outputs]

###############################################################################
# Asynchronous / quasi-static ports — false path
###############################################################################
set_false_path -from [get_ports rst_n_i]

# UART I/O (asynchronous serial)
set_false_path -from [get_ports uart_rx_i]
set_false_path -to   [get_ports uart_tx_o]

# SPI I/O (asynchronous from SoC timing perspective at this abstraction)
set_false_path -from [get_ports spi_miso_i]
set_false_path -to   [get_ports spi_sclk_o]
set_false_path -to   [get_ports spi_mosi_o]
set_false_path -to   [get_ports spi_cs_n_o]

###############################################################################
# APB debug interface — 2-cycle multicycle (low-speed debug bus)
###############################################################################
set_multicycle_path 2 -setup -from [get_ports {apb_paddr_i apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i}]
set_multicycle_path 1 -hold  -from [get_ports {apb_paddr_i apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i}]
set_multicycle_path 2 -setup -to   [get_ports {apb_prdata_o apb_pready_o apb_pslverr_o}]
set_multicycle_path 1 -hold  -to   [get_ports {apb_prdata_o apb_pready_o apb_pslverr_o}]

###############################################################################
# Observability outputs — relaxed (sampled externally, not on-chip timing)
###############################################################################
set_false_path -to [get_ports {commit_valid_o commit_pc_o commit_insn_o gpu_irq_o pll_locked_o}]

###############################################################################
# CPU macro hold false-path on I/O boundary
# The CPU macro timing model covers setup; hold on I/O ports is an external
# board-level concern and is excluded to avoid false hold violations on the
# macro's output boundary in this flat SoC flow.
###############################################################################
set_false_path -hold -from [get_ports clk_i] -to [all_outputs]
