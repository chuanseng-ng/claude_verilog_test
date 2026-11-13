# asap7_gpu.sdc - Timing constraints for gpu_top on ASAP7 (clock clk)
#
# Scope: pnr/asap7/gpu/config.json and config_3014.json set PNR_SDC_FILE, SIGNOFF_SDC_FILE and FALLBACK_SDC_FILE to this file.
# Contents: clock clk with uncertainty, transition and source latency; false paths on the AXI-Lite slave ports (s_axil_*);
#   I/O delays on the timed ports; false path from rst_n; SRAM input hold false paths (Liberty artifact: no hold arc on din0, addr0, csb0);
#   hold false path from the m_axi inputs.
# Inputs: none. The period and delays are literal values in this file.
# User rules:
#   All time values are picoseconds. The ASAP7 Liberty time unit is one picosecond. OpenROAD reads create_clock -period raw against it.
#   Do not write ns values here. The file mirrors pnr/asap7/cpu/constraints/asap7.sdc.
#   Do not copy the m_axi input hold false paths into a SoC SDC without checking the real fabric timing.
#   The GPU shared-memory banks are SRAM macros (sram_1rw_128x32_asap7) clocked directly by clk. There is no ICG, so no generated clock is needed.
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
# 3. I/O delays on timed ports.
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
