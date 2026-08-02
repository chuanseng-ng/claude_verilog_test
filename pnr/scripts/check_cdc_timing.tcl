#================================================================
# Post-route CDC budget verification for the 2-domain ASAP7 SoC
# Tool: OpenSTA (invoked as 'sta' standalone binary)
# bead claude_verilog_test-k07 / GH #96
#
# Companion to pnr/constraints/phase5_soc_multiclock_check.sdc — see that
# file's header (and phase5_soc_multiclock.sdc section 3) for WHY this is a
# separate SDC/script from the normal 07_sta.tcl signoff flow: OpenSTA does
# not honour set_max_delay exceptions on paths between clocks declared
# set_clock_groups -asynchronous (tool-verified, bead k07), so the CDC
# budgets can only be timed by a file that never makes that declaration —
# which means it cannot be used for a full-chip report_wns/report_tns
# sweep (every unrelated cross-domain FF pair would show as a fabricated
# violation). This script therefore only runs TARGETED report_checks
# queries against the specific CDC endpoints phase5_soc_multiclock_check.sdc
# excepts, not a general signoff sweep.
#
# Invoked via: sta pnr/scripts/check_cdc_timing.tcl
# (Makefile target: make check-cdc-timing-asap7-soc, see pnr/Makefile)
#
# Requires a routed netlist that actually contains the CDC modules
# (async_axi_fifo / apb_cdc_bridge / second PLL stub) — i.e. a P&R run of
# pnr/asap7/soc/config.json with PNR_SDC_FILE pointed at
# phase5_soc_multiclock.sdc instead of the single-clock phase5_soc.sdc.
# That re-closure run is GH #96's scope, not this bead's — as of
# 2026-08-02 no such run exists yet (the signed-off run 14 predates GH
# #91-95's CDC RTL entirely). Until then this script will correctly report
# "Netlist not found" rather than silently doing nothing.
#================================================================

set RUN_DIR    $::env(CDC_CHECK_RUN_DIR)
set TOP_MODULE "soc_top"

# phase5_soc_multiclock_check.sdc lives under pnr/constraints/ (shared
# staging location, alongside phase5_soc_multiclock.sdc — see that file's
# STATUS header), NOT under pnr/asap7/soc/constraints/ where the per-node
# signed-off SDCs live. Pass an absolute path via CDC_CHECK_SDC (the
# Makefile target does); fall back to a path relative to this script's own
# location so the script also works if invoked directly from pnr/.
if {[info exists ::env(CDC_CHECK_SDC)]} {
    set CHECK_SDC $::env(CDC_CHECK_SDC)
} else {
    set CHECK_SDC [file join [file dirname [info script]] .. constraints phase5_soc_multiclock_check.sdc]
}

set NETLIST "$RUN_DIR/final/nl/${TOP_MODULE}.nl.v"
set REPORTS_DIR "reports"
file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# ASAP7 stdcell + macro liberty (paths match pnr/asap7/soc/config.json's
# LIB/EXTRA_LIBS; override via env if the PDK is installed elsewhere).
#----------------------------------------------------------------
set ASAP7_LIB_DIR [expr {[info exists ::env(ASAP7_LIB_DIR)] \
    ? $::env(ASAP7_LIB_DIR) \
    : "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib"}]

set _stdcell_libs {
    asap7sc7p5t_AO_RVT_TT_nldm_211120.lib
    asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib
    asap7sc7p5t_OA_RVT_TT_nldm_211120.lib
    asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib
    asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib
}

puts "================================================================"
puts "Reading ASAP7 stdcell liberty ($ASAP7_LIB_DIR)"
puts "================================================================"
foreach _lib $_stdcell_libs {
    set _path "$ASAP7_LIB_DIR/$_lib"
    if {![file exists $_path]} {
        error "Liberty file not found: $_path (set ASAP7_LIB_DIR if the PDK lives elsewhere)"
    }
    read_liberty $_path
}

# Macro libs (CPU/GPU hard macros, SRAM) — same set as EXTRA_LIBS in
# pnr/asap7/soc/config.json.
foreach _macro_lib {
    macro/rv32i_cpu_top__nom_tt_025C_0p7V.lib
    macro/gpu_top__nom_tt_025C_0p7V.lib
} {
    set _path "$_macro_lib"
    if {[file exists $_path]} {
        read_liberty $_path
    } else {
        puts "  (skip, not found: $_path)"
    }
}
if {[file exists "../sram_1rw_256x32_asap7_TT_0p7V_25C.lib"]} {
    read_liberty "../sram_1rw_256x32_asap7_TT_0p7V_25C.lib"
}

#----------------------------------------------------------------
# Gate-level netlist
#----------------------------------------------------------------
puts "================================================================"
puts "Reading gate-level netlist: $NETLIST"
puts "================================================================"
if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST -- no CDC re-closure P&R run exists yet (GH #96 scope). Run pnr/asap7/soc/config.json with PNR_SDC_FILE=phase5_soc_multiclock.sdc first, then set CDC_CHECK_RUN_DIR to that run's directory."
}
read_verilog $NETLIST
link_design $TOP_MODULE

#----------------------------------------------------------------
# CDC check-only SDC (NOT the implementation SDC -- see file header)
#----------------------------------------------------------------
puts "================================================================"
puts "Reading CDC check-only SDC: $CHECK_SDC"
puts "================================================================"
read_sdc $CHECK_SDC

#----------------------------------------------------------------
# Targeted CDC path reports. -unconstrained is NOT used here: the whole
# point is to prove these specific paths ARE constrained (report_checks
# succeeding with a real slack number is the pass signal; "No paths found"
# or "(Path is unconstrained)" is the bead-k07 failure mode this file
# exists to prevent from recurring silently).
#----------------------------------------------------------------
puts "================================================================"
puts "CDC boundary timing -- async_axi_fifo (u_cpu_axi_cdc), all 5 channels"
puts "================================================================"
report_checks -through [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/*/mem_q*" -quiet] \
    -path_delay max -format full_clock_expanded -digits 3 \
    > $REPORTS_DIR/cdc_fifo_memq.rpt
report_checks -through [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/*/u_wr_ptr_to_rd/q_o*" -quiet] \
    -path_delay max -format full_clock_expanded -digits 3 \
    > $REPORTS_DIR/cdc_fifo_wr2rd.rpt
report_checks -through [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/*/u_rd_ptr_to_wr/q_o*" -quiet] \
    -path_delay max -format full_clock_expanded -digits 3 \
    > $REPORTS_DIR/cdc_fifo_rd2wr.rpt

puts "================================================================"
puts "CDC boundary timing -- apb_cdc_bridge (u_apb_pll2_cdc, u_apb_dbg_cdc)"
puts "================================================================"
report_checks -through [get_pins -hierarchical -filter "full_name =~ *u_apb_pll2_cdc/u_req_sync/q_o* || full_name =~ *u_apb_pll2_cdc/u_ack_sync/q_o*" -quiet] \
    -path_delay max -format full_clock_expanded -digits 3 \
    > $REPORTS_DIR/cdc_apb_pll2_toggle.rpt
report_checks -through [get_pins -hierarchical -filter "full_name =~ *u_apb_dbg_cdc/u_req_sync/q_o* || full_name =~ *u_apb_dbg_cdc/u_ack_sync/q_o*" -quiet] \
    -path_delay max -format full_clock_expanded -digits 3 \
    > $REPORTS_DIR/cdc_apb_dbg_toggle.rpt

puts "================================================================"
puts "CDC boundary timing -- PMU/IRQ single-bit crossings"
puts "================================================================"
report_checks -through [get_pins -hierarchical -filter "full_name =~ *u_cpu_clk_dis_sync/q_o* || full_name =~ *u_cpu_iso_en_sync/q_o* || full_name =~ *u_ext_irq_sync/q_o* || full_name =~ *u_timer_irq_sync/q_o*" -quiet] \
    -path_delay max -format full_clock_expanded -digits 3 \
    > $REPORTS_DIR/cdc_pmu_irq.rpt

puts ""
puts "================================================================"
puts "CDC timing reports written to $REPORTS_DIR/cdc_*.rpt"
puts "PASS SIGNAL: each report shows real timed paths with computed slack"
puts "  (not 'No paths found' / 'Path Group: unconstrained' -- see bead"
puts "  k07 / phase5_soc_multiclock.sdc section 3 for why that distinction"
puts "  matters here)."
puts "================================================================"
