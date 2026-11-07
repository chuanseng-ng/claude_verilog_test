# diag_io_latency.tcl -- DIAGNOSTIC ONLY (not in the judge tables).  ICC2's own SDC carries `set_clock_latency 1.77814 clk_i`
# ("Set latency for io paths", -origin useful_skew) that the shared SDC does not.  Re-time the ICC2 arm at nom_tt with that one extra
# line to test whether it explains the native-vs-judge I/O hold/setup delta.  Latency value read from the arm's written SDC.
set ROOT $::env(J_ROOT)
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * sky130_fd_sc_hd__tt_025C_1v80.db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [all_clocks]
if {[info exists ::env(J_EXTRA_LATENCY)]} { set_clock_latency $::env(J_EXTRA_LATENCY) [get_clocks clk_i]; puts "EXTRA network latency $::env(J_EXTRA_LATENCY)" }
read_parasitics -format spef $::env(J_SPEF)
update_timing
report_global_timing
exit
