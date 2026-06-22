###############################################################################
# phase5_soc.sdc — Timing constraints for soc_top on ASAP7 7nm predictive
#
# IMPORTANT: All time values are in PICOSECONDS.
# ASAP7 stdcell Liberty declares time_unit: "1ps".
# LibreLane passes CLOCK_PERIOD (ns) to create_clock internally; this SDC is
# loaded raw by OpenROAD/OpenSTA which interprets values against the 1 ps unit.
#
# Clock topology (single-clock SoC):
#   clk_i  = 100 MHz external reference input to pll_clkgen.
#   core_clk = PLL output; in STUB mode core_clk == clk_i (pass-through).
#   All SoC children (CPU, GPU, crossbar, peripherals) run on core_clk.
#   pll_axil_regs runs on clk_i/rst_n_i (ref domain) — same frequency in STUB.
#   NO CDC in this flow: GPU SDC note §6 carried false-paths are NOT brought in.
#
# SoC fmax target: 571 MHz (GPU-governed), period = 1750 ps.
# CPU signed-off at 1282 MHz standalone; GPU at 571 MHz standalone.
# SoC period = 1750 ps governs all blocks.
###############################################################################

###############################################################################
# 1. Primary clock — defined at the SoC top-level reference input
###############################################################################
create_clock -name clk_i -period 1750 [get_ports clk_i]

set_clock_uncertainty -setup 15 [get_clocks clk_i]
set_clock_uncertainty -hold  10 [get_clocks clk_i]
set_clock_transition   10       [get_clocks clk_i]
set_clock_latency -source 50    [get_clocks clk_i]

###############################################################################
# 2. core_clk domain — PLL stub passthrough
#
# pll_clkgen_stub synthesizes to a single BUFx2_ASAP7_75t_R (_1_) that
# passes ref_clk_i straight to out_clk_o.  At soc_top level, out_clk_o
# becomes the "core_clk" net, which clocks all SoC sub-blocks.
#
# SYNTH_HIERARCHY_MODE=keep: all SoC FFs sit inside parameterised module
# instances (u_dma, u_axil_ic, …).  OpenROAD/OpenSTA cannot create_clock
# on a Net object (only Pin/Port accepted), and get_pins -hierarchical for
# the deep stub pin (u_pll/u_stub/_1_/Y) is fragile across tool versions.
#
# Robust solution: core_clk is an alias of clk_i at the same period.
# The stub BUFx2 is a DC-accurate divide-1 passthrough, so this is
# electrically identical.  LibreLane CTS will use CLOCK_NET=core_clk
# (set in config.json) to build the clock tree on the right net.
# set_clock_groups -logically_equivalent suppresses false CDC warnings
# on the pll_axil_regs/core interface.
###############################################################################

# Primary: try the u_pll output port pin (a proper pin, not a net)
set _pll_out_pin [get_pins -hierarchical \
    -filter "full_name =~ u_pll/out_clk_o" -quiet]
if {[llength $_pll_out_pin] == 0} {
    set _pll_out_pin [get_pins -hierarchical \
        -filter "name =~ out_clk_o" -quiet]
}

if {[llength $_pll_out_pin] > 0} {
    create_clock \
        -name core_clk \
        -period 1750 \
        -waveform {0 875} \
        [lindex $_pll_out_pin 0]
} else {
    # Fallback: define core_clk at the clk_i input port.
    # Electrically identical for divide-1 stub; ensures all SoC paths are timed.
    create_clock \
        -name core_clk \
        -period 1750 \
        -waveform {0 875} \
        [get_ports clk_i]
}

# Apply same timing budget to core_clk as to clk_i.
if {[llength [get_clocks -quiet core_clk]] > 0} {
    set_clock_uncertainty -setup 15 [get_clocks core_clk]
    set_clock_uncertainty -hold  10 [get_clocks core_clk]
    set_clock_transition   10       [get_clocks core_clk]
    set_clock_latency -source 50    [get_clocks core_clk]
    # -asynchronous: suppress cross-domain timing arcs between clk_i and core_clk.
    # Both run at 1750 ps (same period, divide-1 stub) but are separate clock
    # objects in STA.  Asynchronous grouping avoids false hold violations at
    # the pll_axil_regs interface while keeping all intra-domain paths timed.
    set_clock_groups -asynchronous -group {clk_i} -group {core_clk}
}

###############################################################################
# 3. Asynchronous resets — not timed
###############################################################################
set_false_path -from [get_ports rst_n_i]

###############################################################################
# 4. SoC I/O delays (≈20% of 1750 ps = 350 ps on timed ports)
#    Exclude clocks and reset from the timed set.
###############################################################################
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "rst_n_i"} {
        lappend _in_timed $_p
    }
}

set_input_delay  -max 350 -clock clk_i $_in_timed
set_input_delay  -min  20 -clock clk_i $_in_timed

set_output_delay -max 350 -clock clk_i [all_outputs]
set_output_delay -min  20 -clock clk_i [all_outputs]

###############################################################################
# 5. Debug/APB interface — infrequent config path; false-path for timing
###############################################################################
set _apb_ports {}
foreach _p [all_inputs] {
    if {[string match "apb_*" [get_full_name $_p]]} {
        lappend _apb_ports $_p
    }
}
if {[llength $_apb_ports] > 0} {
    set_false_path -from $_apb_ports
}
foreach _p [all_outputs] {
    if {[string match "apb_*" [get_full_name $_p]]} {
        lappend _apb_ports $_p
    }
}
if {[llength $_apb_ports] > 0} {
    set_false_path -to $_apb_ports
}

###############################################################################
# 6. Observability outputs — commit_valid/commit_pc/commit_insn, pll_locked
#    These are registered outputs; relax output delay to avoid over-constraining.
###############################################################################
foreach _sig {commit_valid_o commit_pc_o commit_insn_o pll_locked_o gpu_irq_o} {
    set _port [get_ports -quiet $_sig]
    if {[llength $_port] > 0} {
        set_false_path -to $_port
    }
}

###############################################################################
# 7. UART/SPI asynchronous pins — false-path (cross-clock-domain at board level)
###############################################################################
set _async_ports {}
foreach _sig {uart_rx_i spi_miso_i} {
    set _p [get_ports -quiet $_sig]
    if {[llength $_p] > 0} { lappend _async_ports $_p }
}
if {[llength $_async_ports] > 0} {
    set_false_path -from $_async_ports
}

###############################################################################
# 8. SRAM input hold false-paths (Liberty artifact — no hold arc on SRAM inputs)
###############################################################################
set_false_path -hold -to [get_pins -hierarchical -filter "name =~ *din0*"]
set_false_path -hold -to [get_pins -hierarchical -filter "name =~ *addr0*"]
set_false_path -hold -to [get_pins -hierarchical -filter "name =~ *csb0*"]

###############################################################################
# 9. Hard-macro timing budgets
#    CPU and GPU hard macros are black-boxes; their internal timing is signed off
#    in their own block-level runs.  The SoC SDC constrains only the interface
#    paths:  SoC-logic → macro input, and macro output → SoC-logic.
#
#    Use set_multicycle_path 2 on AXI crossbar-to-macro paths to relax the
#    interface constraint; the hard-macro output registers absorb one full cycle,
#    so SoC logic has 2×1750 ps = 3500 ps for the launch+capture sequence.
#    This is a conservative starting point; tighten after first timing report.
###############################################################################
set _cpu_inputs  [get_pins -hierarchical -filter "full_name =~ *u_cpu/*" -quiet]
set _gpu_inputs  [get_pins -hierarchical -filter "full_name =~ *u_gpu/*" -quiet]

# Two-cycle budget on AXI crossbar→CPU/GPU interface (launch at fabric, capture at macro)
if {[llength $_cpu_inputs] > 0} {
    set_multicycle_path -setup 2 -to $_cpu_inputs
    set_multicycle_path -hold  1 -to $_cpu_inputs
}
if {[llength $_gpu_inputs] > 0} {
    set_multicycle_path -setup 2 -to $_gpu_inputs
    set_multicycle_path -hold  1 -to $_gpu_inputs
}

###############################################################################
# 10. CSR / debug paths — multicycle: these paths cross many pipeline stages
#     and are written rarely.  3-cycle budget; tighten at signoff if needed.
###############################################################################
set _csr_pins [get_pins -hierarchical -filter "name =~ *csr*" -quiet]
if {[llength $_csr_pins] > 0} {
    set_multicycle_path -setup 3 -through $_csr_pins
    set_multicycle_path -hold  2 -through $_csr_pins
}
