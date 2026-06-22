###############################################################################
# phase5_soc.sdc — Timing constraints for soc_top on ASAP7 7nm predictive
#
# IMPORTANT: All time values are in PICOSECONDS.
# ASAP7 stdcell Liberty declares time_unit: "1ps".
# LibreLane passes CLOCK_PERIOD (ns) to create_clock internally; this SDC is
# loaded raw by OpenROAD/OpenSTA which interprets values against the 1 ps unit.
#
# Clock topology (single-clock SoC, deferred_flatten synthesis):
#   clk_i    = top-level clock input port.
#   core_clk = PLL stub output net (BUFx2 passthrough, divide-1).
#   After deferred_flatten synthesis, the PLL stub is flattened and the
#   BUFx2 (_1_) drives core_clk directly at the top level.
#   CTS (CLOCK_NET=clk_i) builds the clock tree from the clk_i port, tracing
#   through the BUFx2 to the core_clk fanout reaching all SoC FFs.
#   pll_axil_regs.clk_i is also driven directly from clk_i (same period).
#
# SoC fmax target: 571 MHz (GPU-governed), period = 1750 ps.
# CPU signed-off at 1282 MHz standalone; GPU at 571 MHz standalone.
###############################################################################

###############################################################################
# 1. Primary clock — clk_i port, 1750 ps (571 MHz)
###############################################################################
create_clock -name clk_i -period 1750 -waveform {0 875} [get_ports clk_i]

set_clock_uncertainty -setup 15 [get_clocks clk_i]
set_clock_uncertainty -hold  10 [get_clocks clk_i]
set_clock_transition   10       [get_clocks clk_i]
set_clock_latency -source 50    [get_clocks clk_i]

###############################################################################
# 2. core_clk — generated from clk_i through the PLL stub BUFx2.
#    After deferred_flatten, the flat netlist has a BUFx2 cell (named _1_
#    by Yosys) driving the core_clk net at the top level.
#    OpenSTA propagates clk_i through this buffer automatically.
#    We add create_generated_clock for clean report labelling.
#    In flat mode, get_pins -hierarchical finds the Y pin of the flattened
#    BUFx2 directly (no module boundary to cross).
###############################################################################
set _pll_buf_out [get_pins -hierarchical \
    -filter "full_name =~ *_1_/Y" -quiet]

if {[llength $_pll_buf_out] > 0} {
    create_generated_clock \
        -name core_clk \
        -source [get_ports clk_i] \
        -divide_by 1 \
        [lindex $_pll_buf_out 0]
    set_clock_uncertainty -setup 15 [get_clocks core_clk]
    set_clock_uncertainty -hold  10 [get_clocks core_clk]
    set_clock_transition   10       [get_clocks core_clk]
    set_clock_latency -source 50    [get_clocks core_clk]
} else {
    puts "INFO: PLL stub BUFx2 _1_/Y not found in flat netlist; clk_i propagates automatically."
}

###############################################################################
# 3. Asynchronous resets — not timed
###############################################################################
set_false_path -from [get_ports rst_n_i]

###############################################################################
# 4. SoC I/O delays (20% of 1750 ps = 350 ps on timed ports)
#    Exclude clock and reset.
###############################################################################
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "rst_n_i"} {
        lappend _in_timed $_p
    }
}

if {[llength $_in_timed] > 0} {
    set_input_delay  -max 350 -clock clk_i $_in_timed
    set_input_delay  -min  20 -clock clk_i $_in_timed
}

set_output_delay -max 350 -clock clk_i [all_outputs]
set_output_delay -min  20 -clock clk_i [all_outputs]

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
#    Two-cycle multicycle on AXI crossbar->macro interface paths.
###############################################################################
set _cpu_inputs [get_pins -hierarchical -filter "full_name =~ *u_cpu/*" -quiet]
set _gpu_inputs [get_pins -hierarchical -filter "full_name =~ *u_gpu/*" -quiet]

if {[llength $_cpu_inputs] > 0} {
    set_multicycle_path -setup 2 -to $_cpu_inputs
    set_multicycle_path -hold  1 -to $_cpu_inputs
}
if {[llength $_gpu_inputs] > 0} {
    set_multicycle_path -setup 2 -to $_gpu_inputs
    set_multicycle_path -hold  1 -to $_gpu_inputs
}

###############################################################################
# 10. I/O hold false-paths — suppress spurious port hold violations.
###############################################################################
set_false_path -hold -from [all_inputs]
set_false_path -hold -to [all_outputs]
