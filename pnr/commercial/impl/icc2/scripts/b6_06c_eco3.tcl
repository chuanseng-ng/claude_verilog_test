# b6_06c_eco3.tcl -- ECO round 3 (copy of b6_06b_eco2.tcl): two more diode_2 on each of the 2 sink pins that the OpenROAD deck still flags after round 2.
#   M  KLayout m1.7 (2 items): nets whose routing touches the marker positions (eco_in/m17_none.txt) are ripped up and re-routed (halo blockages on the PG straps active again)
#   A  antenna: eco_in/ant_pins3d.txt = violators of the OpenROAD check_antennas run on the b6 GDS-side DEF after round 1 (one diode_2 per violating sink pin)
# then halos off, checks, save as 06b_eco2 (the finish stage runs on it: B5E_FINISH_BASE=06b_eco2).
source [file join [file dirname [info script]] b6_common.tcl]
set t0 [clock seconds]
open_stage 06b_eco2 06c_eco3
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
set R $RUN/reports
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }; close $fh; return $n }
proc count_short {f} { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr n } }; close $fh; return $n }
proc count_open {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of open nets is (\d+)} $l -> n }; close $fh; return $n }
proc chk {tag} {
  global RUN
  redirect -file $RUN/reports/e3_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/e3_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/e3_checks_$tag.txt]; set s [count_short $RUN/reports/e3_lvs_$tag.txt]; set o [count_open $RUN/reports/e3_lvs_$tag.txt]
  puts "E3_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
proc tim {tag} {
  foreach s [get_object_name [all_scenarios]] {
    foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "E3_TIMING $tag $s $nm worst_slack=[get_attribute $p slack]" } }
  }
  current_scenario func_tt
}
# ---- halos back on (all met4 PG straps wider than 3 um)
set blk {}
foreach_in_collection s [get_shapes -quiet -filter "layer_name==met4 && shape_use==stripe"] {
  set bb [get_attribute $s bbox]
  set x1 [lindex $bb 0 0]; set y1 [lindex $bb 0 1]; set x2 [lindex $bb 1 0]; set y2 [lindex $bb 1 1]
  if {($x2 - $x1) < 3.0} continue
  set blk [add_to_collection $blk [create_routing_blockage -layers met4 -boundary [list [list [expr {$x1-0.1}] [expr {$y1-0.1}]] [list [expr {$x2+0.1}] [expr {$y2+0.1}]]]]]
}
puts "E3_HALO: [sizeof_collection $blk] halos"
chk 0
tim 0
# ---- M: m1.7 locations
set fh [open $RUN/eco_in/m17_none.txt r]; set names {}
while {[gets $fh l] >= 0} {
  if {[llength $l] != 2} continue
  lassign $l x y
  foreach_in_collection sh [get_shapes -quiet -intersect [list [list [expr {$x-1.0}] [expr {$y-1.0}]] [list [expr {$x+1.0}] [expr {$y+1.0}]]]] {
    set o [get_attribute $sh owner]
    if {$o ne "" && [get_attribute $sh layer_name] in {met1 met2 li1 via mcon}} { lappend names [get_attribute $o full_name] }
  }
}
close $fh
set names [lsort -unique $names]
set names [lsearch -all -inline -not -glob $names VPWR]; set names [lsearch -all -inline -not -glob $names VGND]
puts "M_NETS: $names"
set nn {}
foreach n $names { set x [get_nets -quiet [list $n]]; if {[sizeof_collection $x]} { set nn [add_to_collection $nn $x] } }
if {[sizeof_collection $nn] > 0} {
  remove_routes -nets $nn -detail_route -global_route
  route_eco -max_detail_route_iterations 60
  set r [chk M0]
  for {set i 1} {$i <= 3} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk M$i]
  }
}
# ---- A: antenna diodes (round 2)
set fh [open $RUN/eco_in/ant_pins3d.txt r]; set pairs {}
while {[gets $fh l] >= 0} { if {[llength $l] == 2} { lappend pairs [lindex $l 0] [lindex $l 1] } }
close $fh
set diode [get_lib_cells sky130_hd_mcmm/sky130_fd_sc_hd__diode_2]
set k 0; set made {}
foreach {net pn} $pairs {
  set p [get_pins -quiet [list $pn]]
  if {[sizeof_collection $p] == 0} { puts "A_WARN: no pin $pn"; continue }
  set cell [get_cells -of_objects $p]
  set cb [get_attribute $cell bbox]; set pb [get_attribute $p bbox]
  set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0}]
  set oy [lindex $cb 0 1]; set orient [get_attribute $cell orientation]
  set nm ANTDIO3_$k
  create_cell $nm $diode
  connect_net [get_nets -of_objects $p] [get_pins $nm/DIODE]
  set_cell_location $nm -coordinates [list [expr {$cx - 0.23}] $oy] -orientation $orient
  lappend made $nm; incr k
}
puts "A_DIODES3: $k created"
if {$k > 0} {
  legalize_placement -cells [get_cells $made]
  foreach t {VPWR VGND} { }
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO3_*/VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO3_*/VPB]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO3_*/VGND]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO3_*/VNB]
  route_eco -max_detail_route_iterations 60
  set r [chk A0]
  for {set i 1} {$i <= 4} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk A$i]
  }
}
remove_routing_blockages [get_routing_blockages -quiet]
puts "E3_HALO_REMOVED: [sizeof_collection [get_routing_blockages -quiet]] left"
set r [chk final]
puts "E3_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
tim final
redirect -file $R/e3_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/e3_pg_drc.txt { check_pg_drc }
save_stage 06c_eco3
stage_time eco2 $t0
exit
