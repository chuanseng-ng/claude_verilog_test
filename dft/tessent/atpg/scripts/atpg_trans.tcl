# Tessent transition-delay ATPG (launch-on-capture, 2 capture pulses of scan_clk_i, scan_en static low across them).
# Evaluation only: no timing data and no clock controller; the only functional clock is the ATE-supplied scan_clk_i
# (DFT_ARCHITECTURE section 9.6 says a two-pulse LOC burst from the ATE is physically possible, LOS is not).
set B $env(BUILD)
set SRC [file dirname [info script]]
set_context patterns -scan
read_cell_library $B/sky130_hd.tcelllib
set_tsdb_output_directory $B/tsdb
read_design soc_top -design_id gate -verbose
set_current_design soc_top
set_current_mode transition
import_scan_mode soc_scan
source $SRC/common_setup.tcl
set_multiprocessing_options -multithreading on
set_fault_type transition
foreach c {{set_pattern_type -sequential 2} {set_clock_sequential_depth 2}} { if {[catch {eval $c} m]} { puts "TRANS-NOTE: '$c' -> $m" } }
set_system_mode analysis
report_drc_rules -fails_summary > $B/trans_drc_summary.rpt
create_patterns
report_statistics > $B/trans_statistics.rpt
write_patterns $B/patterns/soc_trans.stil -stil2005 -replace
exit
