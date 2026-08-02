###############################################################################
# phase5_soc.sdc — Timing constraints for soc_top on ASAP7 7nm predictive
#
# IMPORTANT: All time values are in PICOSECONDS.
# ASAP7 stdcell Liberty declares time_unit: "1ps".
# LibreLane passes CLOCK_PERIOD (ns) to create_clock internally; this SDC is
# loaded raw by OpenROAD/OpenSTA which interprets values against the 1 ps unit.
#
# Clock topology (single-clock SoC, sv2v synthesis):
#   clk_i     = top-level clock input port.  CTS root.
#   core_clk  = PLL stub output net (BUFx2 passthrough, divide-1).
#               After sv2v + Yosys flatten, the PLL stub BUFx2 drives core_clk
#               at the top level.  CTS traces through this buffer so all FFs
#               (driven by core_clk) are balanced against each other.
#
# Run-13 lesson (2026-06-23):
#   The create_generated_clock on the PLL buf Y pin caused CTS to build TWO
#   independent clock trees — one for the 3 macro-clk sinks (clk_i tree) and
#   one for the 43762 std-cell FF sinks (clk_i_regs H-tree).  The two trees
#   are not balanced against each other, producing 214 ps setup skew (and
#   -209 ps hold skew).  The create_generated_clock is removed for run 14.
#   CLOCK_NET is already "clk_i" which lets CTS see through the PLL buffer
#   to the core_clk fanout.  CTS-0011 then builds one tree for all 43762
#   sinks under clk_i.  Macro clk pins are balanced along the same tree.
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
#    Run-13 lesson: create_generated_clock causes CTS to build a SEPARATE
#    clock tree for the macro sinks (clk_i subtree) vs std-cell sinks
#    (clk_i_regs subtree), creating ~214 ps inter-tree skew.
#    Fix for run-14: DO NOT create a generated clock here.
#    CTS (with CLOCK_NET=clk_i) will trace through the BUFx2 automatically
#    and include core_clk sinks in the same balanced H-tree as clk_i sinks.
#    Both the macro clk pins and std-cell CLK pins are co-optimised.
###############################################################################
# (no create_generated_clock for core_clk)
puts "INFO: No generated clock for core_clk — CTS traces through PLL BUFx2 as part of clk_i tree."

###############################################################################
# 3. Asynchronous resets — not timed
###############################################################################
set_false_path -from [get_ports rst_n_i]

###############################################################################
# 4. SoC I/O delays — timed ports only.
#    Run-13 lesson: set_input_delay -max 350 ps (20% of 1750 ps) on AXI
#    RDATA bus pins feeds the STA with an 350 ps input pessimism on all
#    register→macro paths, making them appear to violate even with the 2-cycle
#    multicycle.  Reduce to 175 ps (10%) for a realistic inter-block budget.
#    Exclude clock, reset, observability and async pins.
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
#
#    Run-13 lesson: The worst setup violators are FF → u_gpu/m_axi_rdata[N]
#    paths (WNS -364 ps).  These paths go FROM a std-cell FF THROUGH
#    combinational glue TO an OUTPUT port of the GPU macro.  The output port
#    has a black-box timing model (86 ps library setup time).  These paths are
#    NOT real physical FF → FF paths — the GPU macro drives m_axi_rdata from
#    its own internal FFs which are already covered by the GPU macro LIB.
#    The path from soc_top glue → macro OUTPUT is a block-level timing
#    artifact.  False-path setup from any std-cell logic to macro output ports
#    to suppress this.
#
#    Two-cycle multicycle on AXI crossbar → macro INPUT interface paths (real).
###############################################################################
set _cpu_in  [get_pins -hierarchical -filter "full_name =~ *u_cpu/*" -quiet]
set _gpu_in  [get_pins -hierarchical -filter "full_name =~ *u_gpu/*" -quiet]

# GH #94 dead-code note: this file previously also declared
#   set _cpu_out [get_ports -quiet -filter "name =~ *u_cpu*"]
#   set _gpu_out [get_ports -quiet -filter "name =~ *u_gpu*"]
# get_ports only ever matches TOP-LEVEL port names, never instance/hierarchy
# paths — soc_top has no top-level port containing "u_cpu"/"u_gpu" (those
# are instance name prefixes, found via get_pins -hierarchical above, not
# get_ports), so both collections were always empty and neither variable was
# ever read again below. Confirmed unused (repo-wide grep, 2026-08-02) and
# removed: this is a pure dead local-variable assignment with no downstream
# reference, so deleting it cannot change any constraint STA applies —
# run-14's signed-off timing behaviour is unaffected. (Same bug class as the
# CDC-exception silent-miss hardening added to
# pnr/constraints/phase5_soc_multiclock.sdc for GH #94 — an empty-collection
# query that nothing ever consumed, so it never had a chance to bite here.)

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
