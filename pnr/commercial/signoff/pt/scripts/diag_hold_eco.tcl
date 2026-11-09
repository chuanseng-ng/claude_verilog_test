# diag_hold_eco.tcl -- DIAGNOSTIC: virtual hold ECO in PrimeTime.  Reads env HOLD_EP (file of capture D pins), HOLD_CELL (lib cell, default buf_1).
# Reports reg->reg hold and setup slack of those endpoints before and after inserting one buffer in front of each D pin (new nets unannotated = zero wire load; an upper bound on the gain).
set ROOT $::env(J_ROOT)
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set CELLN sky130_fd_sc_hd__buf_1; if {[info exists ::env(HOLD_CELL)]} { set CELLN $::env(HOLD_CELL) }
set_host_options -max_cores 2
set_app_var report_default_significant_digits 5
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * $LIBN($::env(J_LIB)).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
set fh [open $::env(HOLD_EP) r]; set eps {}; while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne ""} { lappend eps $l } }; close $fh
proc rep {tag} {
  global eps
  foreach e $eps {
    set p [get_pins $e]
    set h [get_timing_paths -delay_type min -to $p -max_paths 1]; set s [get_timing_paths -delay_type max -to $p -max_paths 1]
    puts "EP $tag $e hold=[get_attribute $h slack] setup=[get_attribute $s slack]"
  }
  set h [get_timing_paths -delay_type min -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1]
  set s [get_timing_paths -delay_type max -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1]
  puts "R2R $tag hold_wns=[get_attribute $h slack] setup_wns=[get_attribute $s slack]"
}
rep before
set i 0
foreach e $eps { insert_buffer [get_pins $e] $CELLN -new_cell_names hb7_$i -new_net_names hb7n_$i; incr i }
update_timing
rep after
exit
