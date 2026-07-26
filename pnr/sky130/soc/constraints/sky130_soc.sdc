# sky130_soc.sdc — Timing constraints for SoC Stage 2 (Sky130A, 65 MHz)
#
# GH #104 (2026-07-24): clock target relaxed from 75 MHz (13.333 ns) to
# 65 MHz (15.385 ns) per user decision, after the sign-off run
# (RUN_2026-07-24_09-58-19) showed nom_tt setup WNS -1.069 ns at 75 MHz
# (single CPU-macro-internal-boundary violator). The added +2.051 ns of
# slack is expected to close nom_tt/max_tt setup but NOT the slow
# (ss) corners -- see memory/pd/run_state.md for the full analysis.
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
# because one macro remains single-corner -- and note that even nom_tt now
# carries a hold violation. It is NOT a validated multi-corner timing
# sign-off and MUST NOT be recorded as one anywhere downstream.
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
# clock pin). Paired with GRT_RESIZER_HOLD_SLACK_MARGIN raised 0.05 -> 0.15
# ns in config.json to cover GRT-estimate-to-RCX-extracted drift during
# hold repair. See RUN_2026-07-25_13-29-40 min.rpt for the violator detail
# and the re-run launched after this fix for the outcome.
#
# Single clock domain: core_clk = 15.385 ns (65 MHz).
# CPU is a hard macro with its own characterised timing arcs in the .lib;
# path analysis through the CPU macro boundary uses those timing arcs.
#
# set_driving_cell matches Stage-1 CPU SDC (buf_4) for all DATA inputs so
# that input-slew assumptions are consistent with the CPU macro timing
# model. clk_i is excluded and driven by clkbuf_16 instead (see FIX above).

set clock_period 15.385

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
