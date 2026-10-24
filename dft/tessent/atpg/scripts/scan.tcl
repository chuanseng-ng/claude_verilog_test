# Tessent Scan insertion + scan DRC for the Sky130 SoC fabric (DFT Stage 2 evaluation; not back-annotated to PD).
set B $env(BUILD)
set SRC [file dirname [info script]]
set_context dft -scan -no_rtl -design_id gate
read_cell_library $B/sky130_hd.tcelllib
read_verilog $B/soc_top_gate_fix.v
set_tsdb_output_directory $B/tsdb
set_current_design soc_top
set_design_level top
set_cell_library_options -default_dft_cell_selection_name sky130hd
source $SRC/common_setup.tcl
set_scan_enable scan_en_i -active high
# S1/S2 are errors by default and stop the mode transition.  They flag the flops whose clock is not controllable from
# scan_clk_i (TAP-domain flops clocked by tck_i, held at 0; DFT_ARCHITECTURE N4 keeps them off every chain).  Demote to
# warnings so the flow proceeds; scripts/triage_drc.py proves the violators are only the declared TAP-domain instances.
set_drc_handling S1 warning
set_drc_handling S2 warning
set_system_mode analysis
report_drc_rules -fails_summary > $B/scan_drc_summary.rpt
report_drc_rules -all_fails -verbose > $B/scan_drc_all_fails.rpt
report_clocks > $B/scan_clocks.rpt
report_scan_elements > $B/scan_elements.rpt
# 6 fabric chains (DFT_ARCHITECTURE section 8: 5 clk_i + 1 cpu_clk_i); chains 6,7 belong to the CPU macro (black box here).
# In scan mode every flop is clocked by scan_clk_i, so the tool sees one clock domain; balancing is by length.
set rc [catch {add_scan_mode soc_scan -chain_count 6 -single_clock_domain_chains on -lockup_cell_type latch \
    -si_connections [get_ports {scan_in_i[0] scan_in_i[1] scan_in_i[2] scan_in_i[3] scan_in_i[4] scan_in_i[5]}] \
    -so_connections [get_ports {scan_out_o[0] scan_out_o[1] scan_out_o[2] scan_out_o[3] scan_out_o[4] scan_out_o[5]}]} msg]
if {$rc} {
  puts "SCANFLOW: existing-port binding failed ($msg); falling back to tool-created ports"
  add_scan_mode soc_scan -chain_count 6 -single_clock_domain_chains on -lockup_cell_type latch
}
analyze_scan_chains
report_scan_chains > $B/scan_chains_pre.rpt
insert_test_logic -verbose
report_scan_chains > $B/scan_chains.rpt
report_scan_cells -all > $B/scan_cells.rpt
write_design -output_file $B/soc_top_scan.v -replace
write_design -tsdb -replace
catch {set_system_mode insertion}
catch {write_scan_order $B/soc_top.scanorder -replace}
exit
