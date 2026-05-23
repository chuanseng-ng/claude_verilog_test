###############################################################################
# asap7_gpu.sdc — Timing constraints for gpu_top on ASAP7 7nm predictive
#
# IMPORTANT: All time values are in PICOSECONDS (ASAP7 stdcell Liberty declares
# time_unit : "1ps"; OpenROAD reads create_clock -period raw against that unit).
# This mirrors pnr/asap7/constraints/asap7.sdc — do NOT write ns values here.
#
# Target: 1000 MHz (1000 ps period). The GPU shared-memory banks are SRAM macros
# (sram_1rw_128x32_asap7) clocked directly by clk — no ICG, so no generated
# clock is needed (unlike the CPU's gclk_sram).
###############################################################################

###############################################################################
# 1. Clock
###############################################################################
create_clock -name clk -period 1000 [get_ports clk]

set_clock_uncertainty -setup 15 [get_clocks clk]
set_clock_uncertainty -hold  10 [get_clocks clk]
set_clock_transition   10       [get_clocks clk]
set_clock_latency -source 50    [get_clocks clk]

###############################################################################
# 2. IO delays (≈20% of 1000 ps period budget on the AXI4-Lite / AXI4 ports)
###############################################################################
# OpenSTA does not implement remove_from_collection; use Tcl filter instead.
set _in_no_clk {}
foreach _p [all_inputs] {
    if {[get_full_name $_p] ne "clk"} { lappend _in_no_clk $_p }
}

set_input_delay  -max 200 -clock clk $_in_no_clk
set_input_delay  -min  10 -clock clk $_in_no_clk

set_output_delay -max 200 -clock clk [all_outputs]
set_output_delay -min  10 -clock clk [all_outputs]

###############################################################################
# 3. Asynchronous active-low reset — not timed
###############################################################################
set_false_path -from [get_ports rst_n]
