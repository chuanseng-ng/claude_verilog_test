# diag_r2r_wns.tcl -- DIAGNOSTIC ONLY.  Worst pure reg->reg slack (setup and hold) irrespective of sign, so the base-vs-iolat r2r
# identity can be checked on corners where reg->reg meets (get_timing_paths in judge.tcl only returned violating paths there).
set ROOT $::env(J_ROOT)
set_host_options -max_cores 2
set_app_var report_default_significant_digits 6
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * sky130_fd_sc_hd__tt_025C_1v80.db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
foreach dt {max min} {
  set p [get_timing_paths -delay_type $dt -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1]
  puts "R2RWNS $dt [get_attribute $p slack] [get_object_name [get_attribute $p startpoint]] -> [get_object_name [get_attribute $p endpoint]]"
}
exit
