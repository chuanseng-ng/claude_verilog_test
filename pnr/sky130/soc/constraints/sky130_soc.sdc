# sky130_soc.sdc — Timing constraints for SoC Stage 2 (Sky130A, 65 MHz)
#
# GH #104 (2026-07-24): clock target relaxed from 75 MHz (13.333 ns) to
# 65 MHz (15.385 ns) per user decision, after the sign-off run
# (RUN_2026-07-24_09-58-19) showed nom_tt setup WNS -1.069 ns at 75 MHz
# (single CPU-macro-internal-boundary violator). The added +2.051 ns of
# slack is expected to close nom_tt/max_tt setup but NOT the slow
# (ss) corners -- see memory/pd/run_state.md for the full analysis.
#
# *** FIRST-CLASS KNOWN LIMITATION (GH #104, 2026-07-24): MACRO TIMING
# IS NOT CHARACTERIZED PER-CORNER -- THIS BOUNDS THE VALIDITY OF EVERY
# MULTI-CORNER RESULT IN THIS FLOW. ***
# Both hard macros used in this SoC -- rv32i_cpu_top and
# sky130_sram_4kbyte_1rw1r_32x1024_8 -- provide only ONE characterized
# Liberty view each (nom_tt_025C_1v80 / TT_1p8V_25C respectively).
# pnr/sky130/soc/config.json's MACROS entries map that single .lib to
# EVERY PVT corner via a wildcard: "lib": {"*": [<the one nom_tt file>]}.
# CONFIRMED from the run's own log (not inferred): analyzing the
# "nom_ss_100C_1v60" corner literally reads
# ".../rv32i_cpu_top__nom_tt_025C_1v80.lib" for the CPU macro's internal
# timing arcs (and the equivalent TT_1p8V_25C.lib for the SRAM macro).
# Only the sky130_fd_sc_hd standard-cell library genuinely varies by
# corner in this flow; both macros' internal delays are corner-invariant,
# always, for every reported corner.
#
# CONSEQUENCE, STATED IN BOTH DIRECTIONS:
#   - nom_tt results ARE VALID -- this is the one corner where the
#     macros' characterization actually matches the analysis label.
#   - ss/ff-corner results that touch either macro's internal timing
#     ARE NOT RELIABLE, in OPPOSITE directions depending on check type:
#       * SETUP at slow (ss) corners is likely OPTIMISTIC/understated --
#         real slow-corner silicon would have slower macro-internal
#         delay than the nom_tt value used here, so a genuinely-
#         characterized ss corner could show WORSE setup violations than
#         reported (e.g. the -5.32 ns max_ss WNS on the fully-CPU-internal
#         path u_cpu/axi_araddr_o[15]->u_cpu/axi_arready_i may understate
#         the true slow-corner violation).
#       * HOLD at slow (ss) corners is likely PESSIMISTIC/overstated --
#         real slow-corner silicon would have MORE launch-side delay out
#         of the macro than modeled, giving more hold margin than
#         reported (e.g. the max_ss -0.0708 ns residual on
#         u_cpu/axi_bready_o -> {_45649_/D, _43792_/D} is plausibly
#         better in real silicon than this report shows).
#   Paths entirely within flat standard-cell logic (the bulk of the
#   TNS improvement from the 65 MHz relaxation) ARE corner-accurate,
#   since sky130_fd_sc_hd genuinely varies per corner.
#
# SCOPE OF THIS SIGN-OFF: given the above, GH #104 Stage-2 is a
# TYPICAL-CORNER (nom_tt) TIMING SIGN-OFF. It is NOT a validated
# multi-corner timing sign-off and MUST NOT be recorded as one anywhere
# downstream. The reported ss/ff numbers are directionally informative
# but not to be treated as closed/validated results.
#
# REAL FIX (not a resizer/margin knob): characterize both macros at
# ss/ff corners -- i.e. re-run their Liberty (.lib) generation per
# corner (OpenRAM's own multi-corner characterization for the SRAM
# macro; the Stage-1 CPU flow's equivalent for rv32i_cpu_top) -- so
# slow/fast-corner analysis actually reflects each macro's own
# corner-dependent delay instead of a constant nom_tt stand-in. Tracked
# as a follow-up alongside the DRC-violation bead
# (claude_verilog_test-0jp) -- see memory/pd/run_state.md.
#
# Single clock domain: core_clk = 15.385 ns (65 MHz).
# CPU is a hard macro with its own characterised timing arcs in the .lib;
# path analysis through the CPU macro boundary uses those timing arcs.
#
# set_driving_cell matches Stage-1 CPU SDC (buf_4 at all inputs) so that
# input-slew assumptions are consistent with the CPU macro timing model.

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
###############################################################################
set_driving_cell \
    -lib_cell sky130_fd_sc_hd__buf_4 \
    -pin X \
    [all_inputs]

set_load 0.1 [all_outputs]

###############################################################################
# Input / output delays (20% of period for setup, 5% for hold)
# Exclude clk_i from set_input_delay — STA-0441: input delay on clock port
# not allowed.  Use the same OpenSTA-compatible foreach idiom as ASAP7 SoC SDC.
###############################################################################
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i"} {
        lappend _in_timed $_p
    }
}
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
