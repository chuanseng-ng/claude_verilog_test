# Canonical source: pnr/constraints/phase5_soc_multiclock.sdc
# This copy exists only so PNR_SDC_FILE/SIGNOFF_SDC_FILE/FALLBACK_SDC_FILE's
# "dir::constraints/..." resolution (relative to pnr/asap7/soc/) finds it,
# matching how phase5_soc.sdc is consumed by the single-clock run-14 config.
# Edit the canonical file above and re-copy; do not hand-edit this copy.
###############################################################################

# phase5_soc_multiclock.sdc — 2-domain IMPLEMENTATION constraints for soc_top
# (synthesis / P&R). Post-route CDC budget verification lives in the
# COMPANION file phase5_soc_multiclock_check.sdc — see the section 11-13
# note below for why the split exists (bead claude_verilog_test-k07).
# IMPORTANT: all time values are in PICOSECONDS (ASAP7 stdcell Liberty
# declares time_unit: "1ps" — see pnr/asap7/soc/constraints/phase5_soc.sdc
# and pnr/asap7/cpu/constraints/asap7.sdc headers for the historical Run
# 7-32 units bug this project already paid for once; do not repeat it here).
# Clock topology (2-domain SoC, sv2v synthesis, GH #92/#93):
#   clk_i      = fabric-domain top-level reference input. CTS root for sys_clk.
#   core_clk   = PLL stub output net (BUFx2 passthrough, divide-1) — feeds
#                GPU, crossbar, DMA, SRAM, all peripherals, and the PMU.
#   cpu_clk_i  = SECOND, INDEPENDENT top-level reference input (GH #92) — its
#                own PLL stub (u_cpu_pll_sub) is NOT derived from clk_i.
#   cpu_core_clk = u_cpu_pll_sub's PLL-stub output net (BUFx2 passthrough,
#                divide-1) — feeds u_cpu_cg (rv32i_clock_gate), whose output
#                cpu_gated_clk feeds u_cpu (the CPU hard macro) and
#                u_cpu_axi_cdc's s_* (CPU-domain) face.
# Doc: tm:pd:asap7-soc-phase5-multiclock-sdc, cr:pd:asap7-soc-phase5-multiclock-sdc

create_clock -name sys_clk -period 1750 -waveform {0 875} [get_ports clk_i]

set_clock_uncertainty -setup 15 [get_clocks sys_clk]
set_clock_uncertainty -hold  10 [get_clocks sys_clk]
set_clock_transition   10       [get_clocks sys_clk]
set_clock_latency -source 50    [get_clocks sys_clk]

create_clock -name cpu_clk -period 780 -waveform {0 390} [get_ports cpu_clk_i]

set_clock_uncertainty -setup 15 [get_clocks cpu_clk]
set_clock_uncertainty -hold  10 [get_clocks cpu_clk]
set_clock_transition   10       [get_clocks cpu_clk]
set_clock_latency -source 50    [get_clocks cpu_clk]

###############################################################################
# 2. core_clk / cpu_core_clk — generated from clk_i / cpu_clk_i through their
#    respective PLL-stub BUFx2 cells. Run-13 lesson (see header): do NOT
#    create_generated_clock for either. CTS traces through both BUFx2 cells
#    automatically (CLOCK_NET config per domain) so macro and std-cell sinks
#    on each side land on one balanced tree.
###############################################################################
# (no create_generated_clock for core_clk)
# (no create_generated_clock for cpu_core_clk)
puts "INFO: No generated clock for core_clk — CTS traces through the fabric PLL BUFx2 as part of sys_clk's tree."
puts "INFO: No generated clock for cpu_core_clk — CTS traces through the CPU-domain PLL BUFx2 as part of cpu_clk's tree."

set_clock_groups -name cdc_boundary -asynchronous \
    -group [get_clocks sys_clk] \
    -group [get_clocks cpu_clk]

###############################################################################
# 4. Asynchronous resets — not timed
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
set_false_path -from [get_ports cpu_rst_n_i]

###############################################################################
# 5. SoC I/O delays — timed ports only, per domain.
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "rst_n_i" && $_n ne "cpu_clk_i" && $_n ne "cpu_rst_n_i"} {
        lappend _in_timed $_p
    }
}

if {[llength $_in_timed] > 0} {
    set_input_delay  -max 175 -clock sys_clk $_in_timed
    set_input_delay  -min  10 -clock sys_clk $_in_timed
}

set_output_delay -max 175 -clock sys_clk [all_outputs]
set_output_delay -min  10 -clock sys_clk [all_outputs]

###############################################################################
# 6. Debug/APB interface — infrequent config path; false-path for timing.
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
# 7. Observability outputs — registered; relax output delay.
foreach _sig {commit_valid_o commit_pc_o commit_insn_o pll_locked_o cpu_pll_locked_o gpu_irq_o} {
    set _port [get_ports -quiet $_sig]
    if {[llength $_port] > 0} {
        set_false_path -to $_port
    }
}

###############################################################################
# 8. UART/SPI asynchronous board-level pins — unaffected (peripherals stay in
#    the fabric domain).
###############################################################################
foreach _sig {uart_rx_i spi_miso_i} {
    set _p [get_ports -quiet $_sig]
    if {[llength $_p] > 0} { set_false_path -from $_p }
}

###############################################################################
# 9. SRAM input hold false-paths (Liberty artifact: no hold arc on SRAM
#    inputs) — unaffected (sram_controller stays in the fabric domain).
###############################################################################
set _sram_din  [get_pins -hierarchical -filter "name =~ *din0*"  -quiet]
set _sram_addr [get_pins -hierarchical -filter "name =~ *addr0*" -quiet]
set _sram_csb  [get_pins -hierarchical -filter "name =~ *csb0*"  -quiet]
if {[llength $_sram_din]  > 0} { set_false_path -hold -to $_sram_din  }
if {[llength $_sram_addr] > 0} { set_false_path -hold -to $_sram_addr }
if {[llength $_sram_csb]  > 0} { set_false_path -hold -to $_sram_csb  }

###############################################################################
# 10. Hard-macro timing budgets — CPU and GPU are black-box macros.
set _gpu_in  [get_pins -hierarchical -filter "full_name =~ *u_gpu/*" -quiet]

if {[llength $_gpu_in] > 0} {
    set_multicycle_path -setup 2 -to $_gpu_in
    set_multicycle_path -hold  1 -to $_gpu_in
}


set _cpu_apb_in [get_pins -quiet {u_cpu/apb_paddr_i[*] u_cpu/apb_psel_i u_cpu/apb_penable_i u_cpu/apb_pwrite_i u_cpu/apb_pwdata_i[*]}]

if {[llength $_cpu_apb_in] == 0} {
    puts "ERROR: SDC-EXCEPTION-MISS: section 10b matched no u_cpu APB input pins."
    error "phase5_soc_multiclock.sdc section 10b bound to nothing — refusing to run with the CPU macro APB inputs unconstrained."
}
puts "INFO: section 10b: APB input multicycle applied to [llength $_cpu_apb_in] macro pin(s)."
set_multicycle_path -setup 3 -to $_cpu_apb_in
set_multicycle_path -hold  2 -to $_cpu_apb_in


###############################################################################
# 14. I/O hold false-paths — suppress spurious port hold violations.
###############################################################################
set_false_path -hold -from [all_inputs]
set_false_path -hold -to [all_outputs]

# (Former section 15, the CDC exception coverage hard-fail gate, moved to
# phase5_soc_multiclock_check.sdc along with the cdc_require_match proc and
# the sections 11-13 exceptions it guards — this file no longer defines any
# CDC exceptions for it to guard.)
