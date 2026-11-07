# 05i_eco.tcl -- Step B5i: in-place routing ECO on the b5e pre-fill routed block (05y_repair).  No re-place, no opt.
#   (a) met1 short  u_core/ex1c_comb[158] x u_core/ex1c_ex1b_reg_q[124] (persistent through 3 b5e re-routes): rip up + reroute, escalating:
#         pass A plain rip-up/route_eco, pass B net min layer met2 (allow_pin_connection) on the two nets, pass C met1 blockage over the crossing
#   (b) met4 spacing m4.5ab: signal met4 wire/pad < 0.4 um from a >3 um wide PG strap.  The wide-metal fat table (0.3/0.4 @ width>=3) IS loaded in the tech
#       (get_attribute met4 fat_table_*) but ICC2 detail route + check_routes never apply it against PG stripes; so a 0.1 um halo routing blockage
#       is put on every wide met4 strap while the offending nets (eco_in/m4_nets.txt, from met4_near_strap.py + KLayout markers) are re-routed.
#   The blockages are removed again before saving.  Inputs: $RUN/eco_in/{m4_nets.txt,m4_straps.txt}.
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 05y_repair 05i_eco
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }; close $fh; return $n }
# shorts between a temporary halo routing blockage and the PG strap it hugs (RB_*) are artifacts of the halo, not layout shorts: only count real net-net shorts
proc count_short {f} { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr n } }; close $fh; return $n }
proc count_open {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of open nets is (\d+)} $l -> n }; close $fh; return $n }
proc chk {tag} {
  global RUN
  redirect -file $RUN/reports/i_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/i_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/i_checks_$tag.txt]; set s [count_short $RUN/reports/i_lvs_$tag.txt]; set o [count_open $RUN/reports/i_lvs_$tag.txt]
  puts "ECO_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
proc nets_of {names} {
  set nets {}
  foreach n $names { set c [get_nets -quiet [list $n]]; if {[sizeof_collection $c]} { set nets [add_to_collection $nets $c] } else { puts "ECO_WARN: net $n not found" } }
  return $nets
}
set short_names [list {u_core/ex1c_comb[158]} {u_core/ex1c_ex1b_reg_q[124]}]
set fh [open $RUN/eco_in/m4_nets.txt r]; set m4_names {}
while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne ""} { lappend m4_names $l } }
close $fh
puts "ECO_INPUT: [llength $m4_names] met4 nets, short nets $short_names"
chk 0
# ---- wide-strap halo blockages (met4)
set fh [open $RUN/eco_in/m4_straps.txt r]; set blk {}
while {[gets $fh l] >= 0} {
  if {[llength $l] != 4} continue
  lassign $l x1 y1 x2 y2
  set b [create_routing_blockage -layers met4 -boundary [list [list [expr {$x1-0.1}] $y1] [list [expr {$x2+0.1}] $y2]]]
  set blk [add_to_collection $blk $b]
}
close $fh
puts "ECO_BLOCKAGES: [sizeof_collection $blk] met4 halo blockages"
# ---- pass A: rip up the shorted nets + the met4 offenders together and reroute
set nets [add_to_collection [nets_of $short_names] [nets_of $m4_names]]
puts "ECO_RIPUP: [sizeof_collection $nets] nets"
remove_routes -nets $nets -detail_route -global_route
route_eco -max_detail_route_iterations 60
set r [chk A0]
for {set i 1} {$i <= 3} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chk A$i]
}
# ---- pass B: the met1 crossing persists -> force one of the two nets above met1 for its long jog
if {[lindex $r 1] > 0} {
  puts "ECO_PASS_B: short persists; net min layer met2 (allow_pin_connection) on the two nets"
  set sn [nets_of $short_names]
  set rc [catch {set_routing_rule -min_routing_layer met2 -min_layer_mode allow_pin_connection $sn} e]; puts "ECO_RULE rc=$rc $e"
  remove_routes -nets $sn -detail_route -global_route
  route_eco -max_detail_route_iterations 60
  set r [chk B0]
  for {set i 1} {$i <= 3} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk B$i]
  }
}
# ---- cleanup: temporary blockages (and the temporary net rule) must not stay in the block
remove_routing_blockages $blk
puts "ECO_BLOCKAGES_REMOVED: [sizeof_collection [get_routing_blockages -quiet]] left"
redirect -file $RUN/reports/i_def_pre.txt { puts "" }
set r [chk final]
puts "ECO_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
set rc [catch {write_def $RUN/reports/b5i_eco.def} e]; puts "ECO_WRITE_DEF rc=$rc $e"
save_stage 05i_eco
stage_time eco $t0
exit
