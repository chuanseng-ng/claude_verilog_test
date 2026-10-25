# Tessent ATPG on the scan-inserted Sky130 SoC fabric: stuck-at, then transition (launch-on-capture).
set B $env(BUILD)
set SRC [file dirname [info script]]
set_context patterns -scan
read_cell_library $B/sky130_hd.tcelllib
set_tsdb_output_directory $B/tsdb
read_design soc_top -design_id gate -verbose
set_current_design soc_top
set_current_mode stuck
import_scan_mode soc_scan
source $SRC/common_setup.tcl
set_multiprocessing_options -multithreading on
catch {add_processors localhost -number $env(THREADS)}
catch {report_processors}
set_system_mode analysis
report_drc_rules -fails_summary > $B/atpg_drc_summary.rpt
report_drc_rules -all_fails -verbose > $B/atpg_drc_all_fails.rpt
report_clocks > $B/atpg_clocks.rpt
report_scan_chains > $B/atpg_scan_chains.rpt

# ---- stuck-at ----
set_fault_type stuck
create_patterns
report_statistics > $B/stuck_statistics.rpt
report_statistics -hierarchy -level 2 > $B/stuck_statistics_hier.rpt
report_faults -class AU > $B/stuck_faults_AU.rpt
report_faults -class UC > $B/stuck_faults_UC.rpt
report_faults -class UO > $B/stuck_faults_UO.rpt
report_faults -class DI > $B/stuck_faults_DI.rpt
write_patterns $B/patterns/soc_stuck.stil -stil2005 -replace
write_patterns $B/patterns/soc_stuck_serial.v -verilog -serial -sample 20 -replace
write_patterns $B/patterns/soc_stuck.wgl -wgl -replace
exit
