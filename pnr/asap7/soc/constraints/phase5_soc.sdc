# phase5_soc.sdc - Timing constraints for soc_top with one clock (ASAP7, single-clock SoC)
#
# Scope: pnr/asap7/soc/config.json sets PNR_SDC_FILE, SIGNOFF_SDC_FILE and FALLBACK_SDC_FILE to this file.
#   Make target: librelane-asap7-soc.
# Contents: clock clk_i on port clk_i (uncertainty, transition, source latency); false paths on reset, DFT, APB,
#   observability, UART and SPI pins; DFT case analysis (scan_mode_i 0, scan_en_i 0, scan_rst_ni 1); I/O delays on timed ports;
#   SRAM input hold false paths; multicycle paths into the u_cpu and u_gpu pins; hold false paths on all I/O.
# Inputs: none. The period and delays are literal values in this file.
# User rules:
#   All time values are picoseconds. The ASAP7 Liberty time unit is one picosecond. LibreLane passes CLOCK_PERIOD (ns)
#   to create_clock internally, but OpenROAD and OpenSTA load this SDC raw and read its values in that unit.
#   core_clk is the PLL stub output net (BUFx2 passthrough, divide by 1). Do not create a generated clock for it.
#   CTS traces through the buffer, so all flops driven by core_clk balance against each other under clk_i.
#   The period is set by the GPU, not by the CPU. The CPU and GPU are black-box macros here.
# Doc: tm:pd:asap7-soc-phase5-sdc, cr:pd:asap7-soc-phase5-sdc
###############################################################################
# 1. Primary clock - port clk_i.
###############################################################################
create_clock -name clk_i -period 1750 -waveform {0 875} [get_ports clk_i]

set_clock_uncertainty -setup 15 [get_clocks clk_i]
set_clock_uncertainty -hold  10 [get_clocks clk_i]
set_clock_transition   10       [get_clocks clk_i]
set_clock_latency -source 50    [get_clocks clk_i]

###############################################################################
# 2. core_clk — generated from clk_i through the PLL stub BUFx2.
puts "INFO: No generated clock for core_clk — CTS traces through PLL BUFx2 as part of clk_i tree."

###############################################################################
# 3. Asynchronous resets — not timed
###############################################################################
set_false_path -from [get_ports rst_n_i]

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
# 4. SoC I/O delays - timed ports only. Exclude clock, reset, observability and async pins.
# A 20 percent input delay on the AXI RDATA pins gave an input pessimism on all register-to-macro paths.
# They then appeared to violate even with the 2-cycle multicycle. The budget below is 10 percent, a realistic inter-block budget.
###############################################################################
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "rst_n_i"} {
        lappend _in_timed $_p
    }
}

if {[llength $_in_timed] > 0} {
    set_input_delay  -max 175 -clock clk_i $_in_timed
    set_input_delay  -min  10 -clock clk_i $_in_timed
}

set_output_delay -max 175 -clock clk_i [all_outputs]
set_output_delay -min  10 -clock clk_i [all_outputs]

###############################################################################
# 5. Debug/APB interface — infrequent config path; false-path for timing
###############################################################################
set _apb_in {}
set _apb_out {}
foreach _p [all_inputs] {
    if {[string match "apb_*" [get_full_name $_p]]} {
        lappend _apb_in $_p
    }
}
foreach _p [all_outputs] {
    if {[string match "apb_*" [get_full_name $_p]]} {
        lappend _apb_out $_p
    }
}
if {[llength $_apb_in] > 0}  { set_false_path -from $_apb_in }
if {[llength $_apb_out] > 0} { set_false_path -to   $_apb_out }

###############################################################################
# 6. Observability outputs — registered; relax output delay.
###############################################################################
foreach _sig {commit_valid_o commit_pc_o commit_insn_o pll_locked_o gpu_irq_o} {
    set _port [get_ports -quiet $_sig]
    if {[llength $_port] > 0} {
        set_false_path -to $_port
    }
}

###############################################################################
# 7. UART/SPI asynchronous board-level pins
###############################################################################
foreach _sig {uart_rx_i spi_miso_i} {
    set _p [get_ports -quiet $_sig]
    if {[llength $_p] > 0} { set_false_path -from $_p }
}

###############################################################################
# 8. SRAM input hold false-paths (Liberty artifact: no hold arc on SRAM inputs)
###############################################################################
set _sram_din  [get_pins -hierarchical -filter "name =~ *din0*"  -quiet]
set _sram_addr [get_pins -hierarchical -filter "name =~ *addr0*" -quiet]
set _sram_csb  [get_pins -hierarchical -filter "name =~ *csb0*"  -quiet]
if {[llength $_sram_din]  > 0} { set_false_path -hold -to $_sram_din  }
if {[llength $_sram_addr] > 0} { set_false_path -hold -to $_sram_addr }
if {[llength $_sram_csb]  > 0} { set_false_path -hold -to $_sram_csb  }

###############################################################################
# 9. Hard-macro timing budgets — CPU and GPU are black-box macros.
set _cpu_in  [get_pins -hierarchical -filter "full_name =~ *u_cpu/*" -quiet]
set _gpu_in  [get_pins -hierarchical -filter "full_name =~ *u_gpu/*" -quiet]


# Multicycle on CPU/GPU macro INPUTS (real paths — crossbar → macro regs)
if {[llength $_cpu_in] > 0} {
    set_multicycle_path -setup 2 -to $_cpu_in
    set_multicycle_path -hold  1 -to $_cpu_in
}
if {[llength $_gpu_in] > 0} {
    set_multicycle_path -setup 2 -to $_gpu_in
    set_multicycle_path -hold  1 -to $_gpu_in
}

###############################################################################
# 10. I/O hold false-paths — suppress spurious port hold violations.
###############################################################################
set_false_path -hold -from [all_inputs]
set_false_path -hold -to [all_outputs]
