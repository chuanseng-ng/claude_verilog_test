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
# Two clock domains since bead j41m.5 (2026-10-16): core_clk (clk_i) and cpu_clk (cpu_clk_i),
# both 25.0 ns (40 MHz), declared asynchronous (see "Second clock root" and "Clock groups"
# below). Before that change this was a single-clock file and the whole CPU domain was
# unclocked, so every sign-off number recorded before RUN_2026-10-16 EXCLUDES the CPU-domain
# fabric flops and the CPU-macro boundary arcs.
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
# Second clock root: cpu_clk_i (bead claude_verilog_test-j41m.5, DFT_ARCHITECTURE.md
# section 4 item 20 / 14.5; GH #92-#96 multi-clock epic).
#
# cpu_clk_i is a SECOND, independent top-level reference (u_cpu_pll_sub's reference; the
# CPU clock gate u_cpu_cg is sourced from cpu_core_clk). Until now it had NO create_clock,
# so every flop behind it -- the CPU macro's clk_i pin (cpu_gated_clk), u_cpu_axi_cdc's
# CPU-side face, the APB/PLL2 bridge's CPU side, the CPU-domain synchronisers -- was
# UNCLOCKED: not timed, not balanced by CTS, and every CPU-macro boundary arc was checked
# against an undefined clock. Defining it newly constrains those flops and gives CTS a second
# tree to build; that is the point of this change, and it moves sign-off timing.
#
# Period: 25.0 ns, the same as core_clk (40 MHz). The Sky130 SoC runs both domains at the
# one frequency the fabric closes at; the CPU macro itself was hardened at 13.333 ns
# standalone, so the macro boundary has more headroom here than in its own sign-off. The two
# clocks are declared asynchronous (section "Clock groups" below), so the equal period does
# NOT make CDC paths timed as synchronous.
#
# Like core_clk, NO create_generated_clock: the PLL stub is a passthrough and the
# dft_clk_mux / u_cpu_cg are combinational (mux, latch+AND) on the clock path, which STA
# propagates through. Run-13 lesson (phase5_soc_multiclock.sdc): a generated clock on a
# passthrough makes CTS build split, unbalanced trees.
###############################################################################
create_clock \
    -name cpu_clk \
    -period $clock_period \
    [get_ports cpu_clk_i]

set_clock_uncertainty -setup 0.300 [get_clocks cpu_clk]
set_clock_uncertainty -hold  0.150 [get_clocks cpu_clk]

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
# DFT Stage 1b (j41m.3): the JTAG inputs are timed against tck (section "JTAG TAP" below),
# not core_clk, and tck_i is a clock port (STA-0441), so they are not in this list.
set _jtag_in_names {tck_i tms_i tdi_i trst_ni}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "cpu_clk_i" && [lsearch -exact $_jtag_in_names $_n] < 0} {
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
    [get_ports {clk_i cpu_clk_i}]

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
set _out_timed {}
foreach _p [all_outputs] {
    if {[lsearch -exact {tdo_o tdo_oe_o} [get_full_name $_p]] < 0} {
        lappend _out_timed $_p
    }
}
set_output_delay [expr $clock_period * 0.20] -clock core_clk -max $_out_timed
set_output_delay [expr $clock_period * 0.05] -clock core_clk -min $_out_timed

###############################################################################
# Asynchronous / quasi-static ports — false path
###############################################################################
set_false_path -from [get_ports rst_n_i]

# DFT test access (bead claude_verilog_test-j41m.2, GH #244) -- FUNCTIONAL-MODE constraints.
# soc_top gained scan_mode_i / scan_en_i / scan_rst_ni / scan_clk_i / scan_in_i / scan_out_o.
# In functional mode scan_mode_i = 0, scan_en_i = 0 and scan_rst_ni = 1, so every scan mux is
# transparent: pin them with case analysis (this also blocks scan_clk_i out of the clock
# network, since the dft_clk_mux select is constant 0), and take the test ports out of timing.
# A separate SCAN-MODE SDC (scan_clk_i as the shift clock, scan_en timing, scan_mode = 1,
# scan_in / scan_out delays) is a Stage 2 deliverable and does not exist yet. Guarded with
# -quiet so a netlist from before this change still sources.
foreach {_dft_p _dft_v} {scan_mode_i 0 scan_en_i 0 scan_rst_ni 1} {
    if {[llength [get_ports -quiet $_dft_p]] > 0} {
        set_case_analysis $_dft_v [get_ports $_dft_p]
    }
}
set _dft_in {}
foreach _dft_p {scan_mode_i scan_en_i scan_rst_ni scan_clk_i scan_in_i} {
    foreach _dft_x [get_ports -quiet $_dft_p] { lappend _dft_in $_dft_x }
}
if {[llength $_dft_in] > 0} { set_false_path -from $_dft_in }
if {[llength [get_ports -quiet scan_out_o]] > 0} { set_false_path -to [get_ports scan_out_o] }

###############################################################################
# JTAG TAP (bead claude_verilog_test-j41m.3, DFT Stage 1b) -- FUNCTIONAL-MODE constraints.
# CONSTRAINTS TEXT ONLY: Tcl-syntax / port-resolution checked, NO P&R or STA sign-off run.
#
# tck_i is a third, asynchronous clock root that clocks ONLY the TAP (jtag_tap.sv: FSM, IR,
# TDRs, TDO). 100 ns (10 MHz) is a conservative placeholder until a pad ring and an ATE
# exist (DFT_ARCHITECTURE.md 9.5, 9.6). The TAP's outputs scan_mode / test_en / scan_rst /
# scan_en are static controls (DFT_ARCHITECTURE.md 15.5, crossing 2), so the tck <-> core_clk
# relation is declared asynchronous rather than timed.
#
# KNOWN GAP (Stage 2): scan_mode is now also driven by a TAP flop, so the dft_clk_mux selects
# are no longer constant under set_case_analysis on scan_mode_i alone, and STA will propagate
# tck / scan_clk_i through the muxes into the core clock network. That flop has no name that
# survives hierarchy flattening, so it cannot be case-analysed from this file; the scan-mode
# SDC (a Stage 2 deliverable) must pin it (or set_clock_sense -stop_propagation on the mux
# outputs once their pin names are known after synthesis).
#
# The glitch-free test-clock switch (dft_clk_switch.sv, DFT_ARCHITECTURE.md 15.5) adds two latch-based
# enables and two 2-FF handshake synchronisers between tck_i and scan_clk_i. scan_clk_i has no clock in
# this functional-mode SDC (it is a false-path port), so their handshake paths and the clock-gating
# checks on the enable latches are timed only by the Stage 2 scan-mode SDC. Not run here.
###############################################################################
if {[llength [get_ports -quiet tck_i]] > 0} {
    set _jtag_period 100.0
    create_clock -name tck -period $_jtag_period [get_ports tck_i]
    set_clock_uncertainty -setup 0.300 [get_clocks tck]
    set_clock_uncertainty -hold  0.150 [get_clocks tck]

    set _jtag_data_in {}
    foreach _jtag_p {tms_i tdi_i} {
        foreach _jtag_x [get_ports -quiet $_jtag_p] { lappend _jtag_data_in $_jtag_x }
    }
    if {[llength $_jtag_data_in] > 0} {
        set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X $_jtag_data_in
        set_input_delay [expr $_jtag_period * 0.20] -clock tck -max $_jtag_data_in
        set_input_delay [expr $_jtag_period * 0.05] -clock tck -min $_jtag_data_in
    }
    # TDO / TDO_OE are launched on the falling edge of tck inside the TAP; the external
    # capture is the next rising edge, so half a period minus the board allowance remains.
    set _jtag_out {}
    foreach _jtag_p {tdo_o tdo_oe_o} {
        foreach _jtag_x [get_ports -quiet $_jtag_p] { lappend _jtag_out $_jtag_x }
    }
    if {[llength $_jtag_out] > 0} {
        set_output_delay [expr $_jtag_period * 0.20] -clock tck -max $_jtag_out
        set_output_delay [expr $_jtag_period * 0.05] -clock tck -min $_jtag_out
    }
    # trst_ni: asynchronous assert into a cdc_reset_sync, same class as rst_n_i.
    foreach _jtag_x [get_ports -quiet trst_ni] { set_false_path -from $_jtag_x }
}

###############################################################################
# Clock groups (bead claude_verilog_test-j41m.5): core_clk, cpu_clk and tck are three
# mutually asynchronous roots. core_clk and cpu_clk are two independent top-level
# references (GH #92) bridged ONLY by the declared CDC modules (async_axi_fifo
# u_cpu_axi_cdc, apb_cdc_bridge u_apb_dbg_cdc / u_apb_pll2_cdc, and the cdc_sync /
# cdc_reset_sync instances on the PMU/IRQ signals, including the iso-ack return
# u_cpu_iso_ack_sync, bead 3ogd), so ordinary setup/hold between them would
# only report fabricated violations on those synchroniser paths; tck is declared against both
# (the TAP's outputs are static controls, DFT_ARCHITECTURE.md 15.5 crossing 2).
#
# THE CDC BUDGETS (max-delay on the crossings) ARE NOT IN THIS FILE, ON PURPOSE. The
# request that opened this bead asked for `set_max_delay -datapath_only` modelled on
# phase5_soc_multiclock.sdc, but that file's own header records two tool-verified facts
# (bead k07, OpenSTA 2.6.0 and the OpenROAD-embedded engine, STA-0563): (1) -datapath_only
# is not an implemented flag of set_max_delay and aborts read_sdc outright; (2) even without
# it, a set_max_delay across clocks declared set_clock_groups -asynchronous is DROPPED
# (set_false_path > set_max_delay, regardless of -through/-from/-to specificity). So the
# budgets live in the separate post-route check SDC, sky130_soc_cdc_check.sdc, which declares
# both clocks WITHOUT any group/false-path relation and is read only by
# pnr/scripts/check_cdc_timing_sky130.tcl (`make -C pnr check-cdc-timing-sky130-soc`), the
# same split phase5_soc_multiclock.sdc / phase5_soc_multiclock_check.sdc use.
#
# Guarded per clock so an older netlist/port set still sources.
###############################################################################
set _async_groups {}
foreach _c {core_clk cpu_clk tck} {
    if {[llength [get_clocks -quiet $_c]] > 0} {
        lappend _async_groups -group [get_clocks $_c]
    }
}
if {[llength $_async_groups] > 2} {
    set_clock_groups -name async_domains -asynchronous {*}$_async_groups
}

###############################################################################
# CDC gray-pointer capture pins: NO HOLD CHECK in the functional implementation
# (bead claude_verilog_test-j41m.5 / j41m.4; docs/SKY130_CDC_MAXSS_ANALYSIS.md, decision B).
#
# WHY. The DFT test clock enters BOTH domain roots (dft_clk_mux A1 -> core tree and cpu tree),
# and the group above only separates tck from core_clk/cpu_clk, not tck from itself. So the
# flow STA times every flop pair that straddles the two trees as tck -> tck, a SAME-clock hold
# race with the full inter-tree skew (2.45 ns measured at nom_tt on RUN_2026-10-17_14-07-01:
# the capture flop sits behind u_cpu_cg and its clock arrives 2.45 ns after the launch flop's;
# hold slack -2.16 ns). The resizer paid for that fictitious race with 10 dlygate4sd3_1 cells
# (11.8 ns at ss) in front of each async_axi_fifo gray-pointer synchroniser, which broke the
# 0.5x destination-period CDC budget at all three ss corners (fifo_rd2wr -0.715 ns, fifo_wr2rd
# -0.516 ns at max_ss). In FUNCTIONAL mode the two domains are asynchronous and the
# synchroniser's stage-0 flop is allowed to sample the old or the new gray value, so there is
# no hold requirement to pad for.
#
# WHAT. set_false_path -hold -from <opposite-domain launch flops> -to <stage-0 D pins>, for the
# gray-pointer synchronisers of the five async_axi_fifo FIFOs of u_cpu_axi_cdc ONLY. Setup is
# untouched. The other CDC groups (apb_cdc_bridge req/ack, the PMU/IRQ cdc_sync cells) have
# >= 12 ns of budget slack at every corner and are deliberately NOT exempted here; adding one
# is one more row in the table below.
#
# HOW IT BINDS (structural, robust to the flattened netlist; same resolver as the check SDC,
# pnr/sky130/soc/constraints/sky130_soc_cdc_check.sdc): hierarchy survives only as dot-joined
# escaped NET names and cells are anonymous, so the stage-0 Q net `<inst>.sync_q[0]...` is
# found by name token, its driver is the capture flop, and the launch flops are the
# from-domain startpoints in the fan-in of that flop's D pin. A miss is a hard error, not a
# silent skip: an exception that matched nothing would put the 11.8 ns of padding back.
#
# SCAN MODE (the reason this is not free). In scan capture the same test clock reaches both
# trees, so this IS a real same-clock path and the exemption means the flow no longer repairs
# its hold. What keeps that safe, and what is still UNVERIFIED, is recorded in
# docs/SKY130_CDC_MAXSS_ANALYSIS.md section 6. Short form: a hold failure here can only corrupt
# the captured value of the stage-0 flops (a test-response mismatch, never a functional
# failure), those flops must be masked in the capture response, and the real scan-mode hold
# slack is measured by re-sourcing this file with CVT_SDC_SCAN_VIEW=1 (below) after Stage 2
# (bead j41m.8) has inserted chains. Until then it is NOT verified.
#
# CVT_SDC_SCAN_VIEW=1 in the environment skips the exemption, i.e. gives the scan-mode timing
# view of the same crossings (hold kept on tck -> tck). The flow never sets it; it exists so a
# standalone STA of a finished run can measure the scan-mode exposure from this one file.
###############################################################################
set ::cvt_cdc_hold_exempt_pins {}
set ::cvt_cdc_hold_exempt_misses {}
set ::cvt_cdc_regs_cache [dict create]

proc cvt_cdc_plain_name {obj} {
    return [string map {"\\" ""} [get_full_name $obj]]
}

proc cvt_cdc_regs_on_clock {clk_name} {
    if {![dict exists $::cvt_cdc_regs_cache $clk_name]} {
        set _ns [dict create]
        foreach c [all_registers -clock [get_clocks $clk_name]] { dict set _ns [get_full_name $c] 1 }
        dict set ::cvt_cdc_regs_cache $clk_name $_ns
    }
    return [dict get $::cvt_cdc_regs_cache $clk_name]
}

proc cvt_cdc_filter_by_clock {cells clk_name} {
    set _ns [cvt_cdc_regs_on_clock $clk_name]
    set _r {}
    foreach c $cells { if {[dict exists $_ns [get_full_name $c]]} { lappend _r $c } }
    return $_r
}

# Returns the number of bits exempted; every unresolved bit is recorded as a miss.
proc cvt_cdc_hold_exempt {inst_token from_clk to_clk description} {
    set _nets {}
    foreach _n [get_nets -hierarchical -filter "name =~ *${inst_token}*sync_q*" -quiet] {
        set _nm [cvt_cdc_plain_name $_n]
        if {[string first "sync_q\[0\]" $_nm] >= 0} { lappend _nets $_n }
    }
    if {[llength $_nets] == 0} {
        lappend ::cvt_cdc_hold_exempt_misses "${description}: no stage-0 net matched"
        return 0
    }
    set _done 0
    foreach _n $_nets {
        set _drv [get_pins -of_objects $_n -filter {direction == output} -quiet]
        set _caps [cvt_cdc_filter_by_clock [get_cells -of_objects $_drv -quiet] $to_clk]
        set _dpins {}
        if {[llength $_caps] > 0} {
            set _dpins [get_pins -of_objects $_caps -filter {direction == input && name == D} -quiet]
        }
        if {[llength $_dpins] == 0} {
            lappend ::cvt_cdc_hold_exempt_misses "${description}: [get_full_name $_n] no ${to_clk} capture flop D pin"
            continue
        }
        set _launch [cvt_cdc_filter_by_clock [get_fanin -to $_dpins -startpoints_only -flat -only_cells] $from_clk]
        if {[llength $_launch] == 0} {
            lappend ::cvt_cdc_hold_exempt_misses "${description}: [get_full_name $_n] no ${from_clk} launch flop"
            continue
        }
        set_false_path -hold -from $_launch -to $_dpins
        foreach _p $_dpins { lappend ::cvt_cdc_hold_exempt_pins [get_full_name $_p] }
        incr _done
    }
    return $_done
}

if {[info exists ::env(CVT_SDC_SCAN_VIEW)] && $::env(CVT_SDC_SCAN_VIEW) eq "1"} {
    puts "INFO: CDC-HOLD-EXEMPT: CVT_SDC_SCAN_VIEW=1 -- gray-pointer hold exemption NOT applied (scan-mode view)."
} elseif {[llength [get_clocks -quiet cpu_clk]] > 0 && [llength [get_clocks -quiet core_clk]] > 0} {
    # fifo  write-domain clock  read-domain clock   (AW/W/AR: CPU writes; B/R: fabric writes)
    foreach {_fifo _wr_clk _rd_clk} {
        u_aw_fifo cpu_clk  core_clk
        u_w_fifo  cpu_clk  core_clk
        u_ar_fifo cpu_clk  core_clk
        u_b_fifo  core_clk cpu_clk
        u_r_fifo  core_clk cpu_clk
    } {
        cvt_cdc_hold_exempt "u_cpu_axi_cdc*${_fifo}*u_wr_ptr_to_rd" $_wr_clk $_rd_clk \
            "u_cpu_axi_cdc.${_fifo}.u_wr_ptr_to_rd (${_wr_clk} -> ${_rd_clk})"
        cvt_cdc_hold_exempt "u_cpu_axi_cdc*${_fifo}*u_rd_ptr_to_wr" $_rd_clk $_wr_clk \
            "u_cpu_axi_cdc.${_fifo}.u_rd_ptr_to_wr (${_rd_clk} -> ${_wr_clk})"
    }
    if {[llength $::cvt_cdc_hold_exempt_misses] > 0} {
        foreach _m $::cvt_cdc_hold_exempt_misses { puts "ERROR: CDC-HOLD-EXEMPT-MISS: $_m" }
        error "sky130_soc.sdc: [llength $::cvt_cdc_hold_exempt_misses] CDC gray-pointer hold exemption(s) failed to bind (see CDC-HOLD-EXEMPT-MISS lines); the hold padding they exist to stop would return."
    }
    puts "INFO: CDC-HOLD-EXEMPT: [llength $::cvt_cdc_hold_exempt_pins] gray-pointer capture D pins exempt from hold (10 synchronisers)."
}

# Second-domain reference reset (GH #92/#93). Same class as rst_n_i above: an
# asynchronous reset feeding a cdc_reset_sync, so timing it against core_clk is
# meaningless. This line was MISSING from 2026-08-02 (when cpu_rst_n_i became a
# real top-level port) until 2026-09-26, and the gap was visible: two
# cpu_rst_n_i recovery/removal hold violations appeared at the ss corners in
# RUN_2026-09-20_19-46-05. They no longer appear once the resizer hold margins
# were raised, but the constraint gap was real and is closed here so it cannot
# resurface.
set_false_path -from [get_ports cpu_rst_n_i]

# GPIO inputs (Phase 6a, bead claude_verilog_test-ckc) — asynchronous external
# pins. Same class as uart_rx_i / spi_miso_i below: gpio_controller.sv
# synchronises EVERY pin through its own per-pin cdc_sync before anything
# in core_clk uses it, so a setup/hold check from the pad against core_clk has
# no physical meaning.
#
# Measured, not assumed: this was the LAST remaining hold violation in the
# design. RUN_2026-09-25_22-02-12 closed 68 of 71 hold violations via the
# resizer hold-margin raise, and the 3 survivors were all the same path --
# gpio_in_i[31] -> _60250_ (a cdc_sync stage-1 flop) at max_ss/nom_ss/
# min_ss, worst -0.2456 ns. Every tt and ff corner was already clean.
set_false_path -from [get_ports gpio_in_i]

# ---------------------------------------------------------------------------
# Phase 6 pre-allocated peripheral pins (bead claude_verilog_test-f7vs.3).
#
# These ports exist on soc_top NOW, tied off, so that the Verilator cache-stale
# hazard from growing tb_soc_top.sv's port list fires exactly once instead of
# three times. Their SDC exceptions are added at the same time, for the same
# reason: a constraint naming a port that is currently tied off is inert,
# whereas discovering a missing exception during a 4-10 h Sky130 harden is not.
#
# Same class as gpio_in_i above (async external pin -> cdc_sync) for the
# inputs, and as uart_tx_o below (async sink, nothing timed against core_clk)
# for the outputs.
#
# i2c_*_i  : asynchronous open-drain bus lines, each synchronised by its own
#            single-bit cdc_sync inside i2c_controller.sv (6a-5).
# pwm_o    : push-pull outputs, no receiver in this timing scope (6a-2).
# wdt_rst_req_o : level-held reset request consumed off-chip / by the pad ring;
#            the CPU-domain reset path it also feeds is a cdc_reset_sync, i.e.
#            an async-clear path rather than a setup-checked datapath (6a-3).
#
# TRNG, CRYPTO and NPU add no top-level pins at all, so they need nothing here.
set_false_path -from [get_ports i2c_scl_i]
set_false_path -from [get_ports i2c_sda_i]
set_false_path -to   [get_ports pwm_o]
set_false_path -to   [get_ports i2c_scl_o]
set_false_path -to   [get_ports i2c_scl_oe_o]
set_false_path -to   [get_ports i2c_sda_o]
set_false_path -to   [get_ports i2c_sda_oe_o]
set_false_path -to   [get_ports wdt_rst_req_o]

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
# cpu_pll_locked_o is launched by a cpu_clk-domain flop (u_cpu_pll_sub). Once cpu_clk exists
# it would otherwise be a cpu_clk -> core_clk-referenced output path; same class as
# pll_locked_o (a level status flag, no timed receiver). Guarded: older port sets lack it.
foreach _p [get_ports -quiet cpu_pll_locked_o] { set_false_path -to $_p }

###############################################################################
# CPU macro hold false-path on I/O boundary
# The CPU macro timing model covers setup; hold on I/O ports is an external
# board-level concern and is excluded to avoid false hold violations on the
# macro's output boundary in this flat SoC flow.
###############################################################################
set_false_path -hold -from [get_ports clk_i] -to [all_outputs]
