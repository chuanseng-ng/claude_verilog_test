###############################################################################
# asap7_gpu.sdc — Timing constraints for gpu_top on ASAP7 7nm predictive
#
# IMPORTANT: All time values are in PICOSECONDS (ASAP7 stdcell Liberty declares
# time_unit : "1ps"; OpenROAD reads create_clock -period raw against that unit).
# This mirrors pnr/asap7/constraints/asap7.sdc — do NOT write ns values here.
#
# The GPU shared-memory banks are SRAM macros (sram_1rw_128x32_asap7) clocked
# directly by clk — no ICG, so no generated clock is needed.
###############################################################################

# Doc: tm:pd:asap7-gpu-sdc, cr:pd:asap7-gpu-sdc
###############################################################################
# 1. Clock
###############################################################################
create_clock -name clk -period 1750 [get_ports clk]

set_clock_uncertainty -setup 15 [get_clocks clk]
set_clock_uncertainty -hold  10 [get_clocks clk]
set_clock_transition   10       [get_clocks clk]
set_clock_latency -source 50    [get_clocks clk]

###############################################################################
# 2. AXI-Lite slave (s_axil_*) — kernel config/launch, not timing-critical
#    These ports are written infrequently by the CPU between kernel launches.
###############################################################################
set _s_axil_ports {}
foreach _p [all_inputs] {
    if {[string match "s_axil_*" [get_full_name $_p]]} {
        lappend _s_axil_ports $_p
    }
}
if {[llength $_s_axil_ports] > 0} {
    set_false_path -from $_s_axil_ports
}

###############################################################################
# 3. IO delays (≈20% of 2000 ps period on timed ports)
###############################################################################
# OpenSTA does not implement remove_from_collection; use Tcl filter instead.
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk" && $_n ne "rst_n" && ![string match "s_axil_*" $_n]} {
        lappend _in_timed $_p
    }
}

set_input_delay  -max 400 -clock clk $_in_timed
set_input_delay  -min  20 -clock clk $_in_timed

set_output_delay -max 400 -clock clk [all_outputs]
set_output_delay -min  20 -clock clk [all_outputs]

###############################################################################
# 4. Asynchronous active-low reset — not timed
###############################################################################
set_false_path -from [get_ports rst_n]

###############################################################################
# 5. SRAM input hold false-paths (Liberty artifact — no hold arc on din0/addr0/csb0)
###############################################################################
set_false_path -hold -to [get_pins -hierarchical -filter "name =~ *din0*"]
set_false_path -hold -to [get_pins -hierarchical -filter "name =~ *addr0*"]
set_false_path -hold -to [get_pins -hierarchical -filter "name =~ *csb0*"]

set _m_axi_inputs {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {[string match "m_axil_if_*" $_n] || [string match "m_axi_*" $_n]} {
        lappend _m_axi_inputs $_p
    }
}
if {[llength $_m_axi_inputs] > 0} {
    set_false_path -hold -from $_m_axi_inputs
}
