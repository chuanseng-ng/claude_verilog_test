# vivado_fmax_constraints.tcl -- Vivado timing constraints for the soc_top timing harness (bead hlrm).
#
# Translates the INTENT of pnr/constraints/phase5_soc_multiclock.sdc (+ the CDC budgets of phase5_soc_multiclock_check.sdc)
# to Vivado. It is a translation, not a copy: every ASIC statement is either translated here, or listed under NOT TRANSLATED
# below, and the run prints a CDC-TRANSLATED / CDC-MISS line for every exception it tried to bind. Nothing is cut silently:
# `report_exceptions` is written next to the timing reports.
#
# TRANSLATED
#   * create_clock on the four real harness pins (clk_i = sys_clk, cpu_clk_i = cpu_clk, scan_clk_i, tck_i). The core_clk,
#     cpu_core_clk and cpu_gated_clk nets are NOT given generated clocks: Vivado propagates the port clock through the
#     combinational dft_clk_mux LUT and the latch+AND clock gate, exactly as the SDC's "no create_generated_clock" decision.
#   * clk_i <-> cpu_clk_i: the committed SDC has `set_clock_groups -asynchronous`; the check SDC then bounds every crossing with
#     `set_max_delay 0.9 x destination period`. Vivado's own CDC guidance does the same without a clock group (a clock group
#     would override the budgets and cut the paths), so: set_max_delay -datapath_only 0.9 x destination period, both directions.
#   * the tighter per-crossing budgets (0.5 x destination period on the gray-pointer crossings of the five async_axi_fifo
#     channels) -> set_max_delay -datapath_only on the first synchroniser stage D pins, where the cells can be found.
#   * cdc_reset_sync async set/clear pins -> set_false_path (the SDC does the same: async-clear reset path, not a datapath).
#   * scan_clk_i vs the functional clocks: they meet only at dft_clk_mux, so -physically_exclusive.
# NOT TRANSLATED (and why)
#   * Port constraints (set_input_delay / set_output_delay, the apb_* / commit_* / gpio false paths, the SRAM -hold false paths):
#     the harness has six pins; the 99 inputs / 189 outputs are registered shells, so no pad path exists to constrain.
#   * set_case_analysis scan_mode_i/scan_en_i/scan_rst_ni: in the harness they are flops of the input shift register, not ports,
#     and the DFT clock switch is built from latches that case analysis would not cross. The scan mux is therefore left real
#     (conservative: more logic in the netlist than the functional mode uses).
#   * set_multicycle_path -to u_gpu pins / -to u_cpu APB pins: they exist for the ASIC hard-macro boundaries; here CPU and GPU are
#     plain RTL, so there is no macro boundary to relax.
#   * clock uncertainty / transition / source latency (ASIC clock-tree model): Vivado derives its own from the routed clock nets.
#   * tck_i has no clock in the SoC SDC (all DFT ports are false-pathed there). Here it IS created so its logic is timed, and it
#     is declared asynchronous to the other clocks, so TCK <-> functional crossings are CUT (reported by report_exceptions).
#   * The remaining single-bit PMU/IRQ synchroniser budgets and the apb_cdc_bridge req/ack budgets are only attempted when the
#     cell pattern matches (see CDC-TRANSLATED / CDC-MISS lines); otherwise they fall under the domain-wide 0.9 x period bound.

proc cdc_log {kind msg} { puts "VFMAX-CDC $kind: $msg" }

# Bound every path ending on the D pin of a cell whose full name matches `pattern` (budget in ns, datapath only).
proc bound_capture_d {pattern budget what} {
    set cells [get_cells -hierarchical -quiet -filter "NAME =~ $pattern && IS_SEQUENTIAL"]
    if {[llength $cells] == 0} { cdc_log MISS "$what: no cell matches $pattern"; return 0 }
    set pins [get_pins -quiet -of_objects $cells -filter {REF_PIN_NAME == D}]
    if {[llength $pins] == 0} { cdc_log MISS "$what: [llength $cells] cells, no D pins"; return 0 }
    set_max_delay -datapath_only $budget -to $pins
    cdc_log TRANSLATED "$what: set_max_delay -datapath_only $budget to [llength $pins] D pins ([llength $cells] cells)"
    return [llength $pins]
}

proc apply_constraints {period period_cpu rdir} {
    set ::vf_period $period
    create_clock -name clk_i     -period $period     [get_ports clk_i]
    create_clock -name cpu_clk_i -period $period_cpu [get_ports cpu_clk_i]
    create_clock -name scan_clk_i -period $period    [get_ports scan_clk_i]
    create_clock -name tck_i      -period $period    [get_ports tck_i]

    set_clock_groups -physically_exclusive -group [get_clocks clk_i] -group [get_clocks scan_clk_i]
    set_clock_groups -physically_exclusive -group [get_clocks cpu_clk_i] -group [get_clocks scan_clk_i]
    set_clock_groups -asynchronous -group [get_clocks tck_i] -group [get_clocks {clk_i cpu_clk_i scan_clk_i}]
    cdc_log CUT "tck_i asynchronous to clk_i / cpu_clk_i / scan_clk_i (clock group); scan_clk_i physically exclusive with clk_i, cpu_clk_i"

    # domain-wide crossing bounds, 0.9 x destination period (check-SDC rule), datapath only
    set b_to_sys [expr {0.9 * $period}]
    set b_to_cpu [expr {0.9 * $period_cpu}]
    set_max_delay -datapath_only $b_to_sys -from [get_clocks cpu_clk_i] -to [get_clocks clk_i]
    set_max_delay -datapath_only $b_to_cpu -from [get_clocks clk_i] -to [get_clocks cpu_clk_i]
    cdc_log TRANSLATED "domain-wide: cpu_clk_i->clk_i ${b_to_sys} ns, clk_i->cpu_clk_i ${b_to_cpu} ns (set_max_delay -datapath_only)"

    # reset synchronisers: async set/clear pins are a reset path, not a setup-checked datapath
    set rs [get_cells -hierarchical -quiet -filter {NAME =~ *rst_sync* && IS_SEQUENTIAL}]
    set rpins {}
    foreach p {CLR PRE} {
        foreach x [get_pins -quiet -of_objects $rs -filter "REF_PIN_NAME == $p"] { lappend rpins $x }
    }
    if {[llength $rpins] > 0} {
        set_false_path -to $rpins
        cdc_log TRANSLATED "cdc_reset_sync async pins: set_false_path to [llength $rpins] CLR/PRE pins"
    } else {
        cdc_log MISS "cdc_reset_sync async pins: none found"
    }

    # tighter gray-pointer budgets (0.5 x destination period) on the five channel FIFOs of u_cpu_axi_cdc
    foreach {fifo dest} {u_aw_fifo cpu u_w_fifo cpu u_ar_fifo cpu u_b_fifo sys u_r_fifo sys} {
        # write-pointer crossing lands in the READ domain, read-pointer crossing in the WRITE domain
        set rd [expr {$dest eq "cpu" ? $period_cpu : $period}]
        set wr [expr {$dest eq "cpu" ? $period : $period_cpu}]
        bound_capture_d "*u_cpu_axi_cdc*$fifo*u_wr_ptr_to_rd*" [expr {0.5 * $rd}] "$fifo wr-ptr -> rd domain"
        bound_capture_d "*u_cpu_axi_cdc*$fifo*u_rd_ptr_to_wr*" [expr {0.5 * $wr}] "$fifo rd-ptr -> wr domain"
    }
    bound_capture_d "*u_apb_pll2_cdc*req_q*"  $period_cpu "u_apb_pll2_cdc req_q (s->m)"
    bound_capture_d "*u_apb_pll2_cdc*ack_q*"  $period     "u_apb_pll2_cdc ack_q (m->s)"
    bound_capture_d "*u_apb_dbg_cdc*req_q*"   $period_cpu "u_apb_dbg_cdc req_q (s->m)"
    bound_capture_d "*u_apb_dbg_cdc*ack_q*"   $period     "u_apb_dbg_cdc ack_q (m->s)"
    bound_capture_d "*u_cpu_clk_dis_sync*"    $period_cpu "u_cpu_clk_dis_sync single-bit CDC"
}
