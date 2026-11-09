# b9_06e_eco.tcl -- ICC2 b9 round 3b: try to clear the one soft "Min-max layer" violation (li1 shape {343.075 433.89}-{343.245 434.06} on net u_core_u_icache_tag_dout0[4]) by ripping up the detail route of that net and re-routing it.
#   Input label 06c_eco (diode move), output 06e_eco.  Never overwrites 06c_eco.  If the violation does not disappear or a hard DRC/short/open appears, the chain keeps 06c_eco (B5E_FINISH_BASE).
source [file join [file dirname [info script]] b8_common.tcl]
set t0 [clock seconds]
open_stage 06c_eco 06e_eco
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
set_app_options -name route.detail.report_soft_drc_separately -value true
set R $RUN/reports
proc chkq {tag} {
  global RUN
  redirect -file $RUN/reports/d9_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/d9_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set hard -1; set soft -1; set o -1; set s 0
  set fh [open $RUN/reports/d9_checks_$tag.txt r]; while {[gets $fh l] >= 0} { regexp {TOTAL VIOLATIONS =\s*(\d+)} $l -> hard; regexp {TOTAL SOFT VIOLATIONS =\s*(\d+)} $l -> soft } ; close $fh
  set fh [open $RUN/reports/d9_lvs_$tag.txt r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr s }; regexp {Total number of open nets is (\d+)} $l -> o } ; close $fh
  puts "D9_CHECK $tag: hard=$hard soft=$soft shorts=$s opens=$o"
  return [list $hard $soft $s $o]
}
set net [get_nets {u_core_u_icache_tag_dout0[4]}]
chkq 0
puts "D9_NET pins: [get_object_name [get_pins -of_objects $net]]"
set dc [get_cells ANTDIO_292]; set bb [get_attribute $dc bbox]
set nx [expr {[lindex $bb 0 0] - 3.45}]; set ny [lindex $bb 0 1]
puts "D9_MOVE ANTDIO_292 from $bb to ($nx,$ny)"
catch { set_placement_status placed $dc }
set_cell_location $dc -coordinates [list $nx $ny]
legalize_placement -cells $dc
puts "D9_AFTER ANTDIO_292 [get_attribute $dc bbox]"
connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
set rc [catch { route_eco -max_detail_route_iterations 60 } m]; puts "D9_ROUTE_ECO rc=$rc $m"
set r [chkq 1]
for {set i 2} {$i <= 4} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 2] == 0 && [lindex $r 3] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chkq $i]
}
catch { foreach_in_collection s [get_shapes -quiet -of_objects $net -filter "layer_name==li1"] { puts "D9_LI1 [get_attribute $s bbox]" } } m
catch { open_drc_error_data -name zroute.err } m
catch { foreach_in_collection e [get_drc_errors -error_data zroute.err] { puts "D9_DRC [get_attribute $e type_name] [get_attribute $e bbox]" } } m
redirect -file $R/d9_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/d9_pg_drc.txt { check_pg_drc }
catch { write_def $RUN/out/pre_ant_06e.def }
foreach s [get_object_name [all_scenarios]] { foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "D9_TIMING $s $nm worst_slack=[get_attribute $p slack]" } } }
save_stage 06e_eco
stage_time eco9e $t0
exit
