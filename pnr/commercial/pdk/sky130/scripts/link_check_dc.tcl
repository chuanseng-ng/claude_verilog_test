# link_check_dc.tcl -- DC NXT (NDM) topographical link check of the trivial netlist against the Sky130 .db + NDM views.
#   dcnxt_shell -topographical_mode -f link_check_dc.tcl   (env HERE = pdk/sky130 dir)
#   NOTE: plain dc_shell -topographical_mode is the Milkyway flow and has no create_lib/NDM support (CMD-005);
#   the NDM reference libraries built by build_ndm.tcl are consumed by dcnxt_shell.
set HERE $::env(HERE)
set B $HERE/build
set_app_var search_path [list $B/db $B/ndm]
set_app_var target_library [list sky130_fd_sc_hd__tt_025C_1v80.db]
set_app_var link_library   [list * sky130_fd_sc_hd__tt_025C_1v80.db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
if {[file exists $B/work/dc/WORK.dlib]} { file delete -force $B/work/dc/WORK.dlib }
create_lib -technology $B/ndm/sky130_hd.tf \
  -ref_libs [list $B/ndm/sky130_hd_tt.ndm $B/ndm/sky130_hd_phys.ndm $B/ndm/sky130_sram_1kbyte_1rw1r_32x256_8.ndm] \
  $B/work/dc/WORK.dlib
open_lib $B/work/dc/WORK.dlib
read_verilog $HERE/tests/link_trivial.v
current_design link_trivial
puts "=== link"
set lr [link]
puts "LINK_RESULT: $lr"
puts "=== routing directions + dont_use"
foreach l [get_layers {li1 met1 met2 met3 met4 met5}] { puts "dir [get_object_name $l] = [get_attribute $l routing_direction]" }
source $HERE/scripts/dont_use.tcl
puts "dont_use hd cells: [sizeof_collection [get_lib_cells -quiet -filter dont_use==true sky130_fd_sc_hd__tt_025C_1v80/*]]"
puts "=== check_design"
check_design
puts "=== check_library"
check_library
puts "=== report_lib (summary)"
catch {report_lib sky130_fd_sc_hd__tt_025C_1v80}
puts "=== cells"
report_cell
puts "=== tech / layers"
puts "layers: [get_object_name [get_layers]]"
catch {report_design -physical}
exit
