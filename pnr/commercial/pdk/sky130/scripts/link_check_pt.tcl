# link_check_pt.tcl -- PrimeTime link + library summary for the Sky130 .db corners (tt/ss/ff hd + TT SRAM).
#   pt_shell -f link_check_pt.tcl     (env HERE = pdk/sky130 dir)
set HERE $::env(HERE)
set B $HERE/build
set sram sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
foreach c {tt_025C_1v80 ss_100C_1v60 ff_n40C_1v95} {
  puts "######## corner $c"
  catch {remove_design -all}
  set_app_var search_path [list $B/db]
  set_app_var link_path [list * sky130_fd_sc_hd__$c.db $sram]
  read_verilog $HERE/tests/link_trivial.v
  current_design link_trivial
  link_design link_trivial
  puts "LINK_OK corner=$c cells=[sizeof_collection [get_cells -hier *]]"
  report_lib sky130_fd_sc_hd__$c -nosplit
  check_timing -verbose
  report_design
}
puts "######## sram lib"
report_lib sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C_lib -nosplit
exit
