# dc_drivers.tcl -- step 4b: map the SoC-side drivers of the CPU-macro input pins (u_cpu_axi_cdc = async_axi_fifo, u_apb_dbg_cdc = apb_cdc_bridge)
#   to sky130_fd_sc_hd (tt db) so PrimeTime can time launch-edge -> macro-pin arrival per corner (scripts/pt_arrival.tcl).
#   Source RTL = the SoC's own sv2v netlist pnr/sky130/soc/soc_top_sv2v.v (what the SoC synthesis reads), default parameters as instantiated in soc_top.
#   dc_shell -f dc_drivers.tcl   env: REPO RUN
set REPO $::env(REPO); set RUN $::env(RUN)
set B $REPO/pnr/commercial/pdk/sky130/build
set_host_options -max_cores 2
suppress_message {LBDB-272 LBDB-1054 LBDB-607 LBDB-396 LBDB-301 LBDB-172}
set_app_var search_path   [list $B/db]
set_app_var target_library [list sky130_fd_sc_hd__tt_025C_1v80.db]
set_app_var link_library   [list * sky130_fd_sc_hd__tt_025C_1v80.db]
file mkdir $RUN/out $RUN/reports
define_design_lib WORK -path $RUN/WORK
set rc [analyze -format verilog $REPO/pnr/sky130/soc/soc_top_sv2v.v]
puts "ANALYZE_RESULT: $rc"
foreach {m params} {async_axi_fifo {} apb_cdc_bridge {}} {
  remove_design -all
  set rc [elaborate $m]
  puts "ELABORATE_RESULT $m: $rc"
  current_design $m
  link
  source $REPO/pnr/commercial/pdk/sky130/scripts/dont_use.tcl
  foreach c $_pdk_dont_use { set_dont_use [get_lib_cells */[string map {sky130_fd_sc_hd__ sky130_fd_sc_hd__} $c]] }
  create_clock -name s_clk -period 25 [get_ports s_clk_i]
  create_clock -name m_clk -period 25 [get_ports m_clk_i]
  set_clock_groups -asynchronous -group s_clk -group m_clk
  set_input_delay 0 -clock s_clk [remove_from_collection [all_inputs] [get_ports {s_clk_i m_clk_i}]]
  set_output_delay 0 -clock s_clk [all_outputs]
  set_load 0.01 [all_outputs]
  set_driving_cell -lib_cell sky130_fd_sc_hd__buf_2 [remove_from_collection [all_inputs] [get_ports {s_clk_i m_clk_i}]]
  compile_ultra -no_autoungroup
  ungroup -all -flatten
  change_names -rules verilog -hierarchy
  write -format verilog -hierarchy -output $RUN/out/${m}.mapped.v
  report_area > $RUN/reports/${m}.area.rpt
  report_cell > $RUN/reports/${m}.cell.rpt
  check_design > $RUN/reports/${m}.check.rpt
}
puts "DC_DONE"
exit
