# b9_06g_eco.tcl -- ICC2 b9 round 3e: hold repair after the 06f fanout moves.  06f (24 excess clock sinks moved to sibling leaf buffers, 25 max-fanout violators -> 1) left native ff hold at -0.009 ns (b9 06e: +0.011):
#   three reg-to-reg endpoints (none of them a moved sink: the leaf buffers they hang on changed load / clock route).  Same repair as b7 (hold buffers, one buf_1 in front of each violating D pin, native
#   func_ff hold < B9G_TARGET (default +0.008 ns)), up to 3 passes.  Input 06f_eco, output 06g_eco (06f_eco, 06e_eco kept).
source [file join [file dirname [info script]] b8_common.tcl]
set t0 [clock seconds]
open_stage 06f_eco 06g_eco
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
chkq 0
foreach s [get_object_name [all_scenarios]] { foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "D9_TIMING_PRE $s $nm worst_slack=[get_attribute $p slack]" } } }
proc near_pin {nm pin dx dy} {
  set pb [get_attribute $pin bbox]
  set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0 + $dx}]; set cy [expr {([lindex $pb 0 1] + [lindex $pb 1 1]) / 2.0 + $dy}]
  set_cell_location [get_cells $nm] -coordinates [list $cx $cy]
}
set TARGET [expr {[info exists ::env(B9G_TARGET)] ? $::env(B9G_TARGET) : 0.008}]
set nb 0
for {set pass 1} {$pass <= 3} {incr pass} {
  set eps {}
  foreach sc {func_ff func_tt} {
    set lim [expr {$sc eq "func_ff" ? $TARGET : 0.03}]
    set ps [get_timing_paths -scenarios $sc -delay_type min -max_paths 60 -nworst 1 -slack_lesser_than $lim]
    foreach_in_collection p $ps { set e [get_object_name [get_attribute $p endpoint]]; if {[string match */D $e] && [lsearch $eps $e] < 0} { lappend eps $e } }
  }
  puts "G6_PASS $pass: [llength $eps] hold endpoints below target: $eps"
  if {[llength $eps] == 0} break
  set newc {}
  foreach e $eps {
    set pin [get_pins $e]
    set rc [catch { insert_buffer -new_cell_names HB9G_$nb -new_net_names HB9GN_$nb $pin sky130_hd_mcmm/sky130_fd_sc_hd__buf_1 } msg]
    if {$rc} { puts "G6_FAIL $e: $msg"; continue }
    set c [get_cells -quiet *HB9G_$nb]; near_pin [get_object_name $c] $pin -1.0 0; lappend newc [get_object_name $c]; incr nb
  }
  if {[llength $newc] > 0} {
    legalize_placement -cells [get_cells $newc]
    connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
    connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
    connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
    connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
  }
  set rc [catch { route_eco -max_detail_route_iterations 60 } m]; puts "G6_ROUTE_ECO pass $pass rc=$rc $m"
  chkq p$pass
  foreach s [get_object_name [all_scenarios]] { foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "G6_TIMING pass$pass $s $nm worst_slack=[get_attribute $p slack]" } } }
}
puts "G6_HOLD_BUFFERS: $nb"
set r [chkq 1]
for {set i 2} {$i <= 4} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 2] == 0 && [lindex $r 3] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chkq $i]
}
catch { open_drc_error_data -name zroute.err } m
catch { foreach_in_collection e [get_drc_errors -error_data zroute.err] { puts "D9_DRC [get_attribute $e type_name] [get_attribute $e bbox]" } } m
redirect -file $R/d9_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/d9_pg_drc.txt { check_pg_drc }
catch { write_def $RUN/out/pre_ant_06g.def }
foreach s [get_object_name [all_scenarios]] { foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "D9_TIMING $s $nm worst_slack=[get_attribute $p slack]" } } }
save_stage 06g_eco
stage_time eco9g $t0
exit
