# diag_hold_r2r.tcl -- DIAGNOSTIC: every reg->reg endpoint with hold slack < H (default 0.05 ns) and its setup slack, base SDC, one corner.
set ROOT $::env(J_ROOT)
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set H 0.05; if {[info exists ::env(HOLD_BELOW)]} { set H $::env(HOLD_BELOW) }
set_host_options -max_cores 2
set_app_var report_default_significant_digits 5
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * $LIBN($::env(J_LIB)).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
set vp [get_timing_paths -delay_type min -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 100000 -nworst 1 -slack_lesser_than $H]
foreach_in_collection p $vp {
  set e [get_object_name [get_attribute $p endpoint]]; set s [get_object_name [get_attribute $p startpoint]]
  set sl [get_attribute $p slack]
  puts "HOLDR2R $sl $s -> $e"
}
exit
