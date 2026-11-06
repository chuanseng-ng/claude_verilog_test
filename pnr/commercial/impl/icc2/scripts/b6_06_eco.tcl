# b6_06_eco.tcl -- b6 stage 6: antenna diode ECO (violators taken from OpenROAD check_antennas on the b6_05 DEF: eco_in/ant_pins.txt, one sky130_fd_sc_hd__diode_2 per violating sink pin),
#   re-route with the met4 halos still active, then remove the halos, final checks, net-name hygiene (change_names -case_insensitive).  No tt-only hold/DRV ECO (b5m lesson): hold + DRV were fixed
#   by place_opt/clock_opt/route_opt over the ff/ss/tt scenarios.  Env: B6_BASE (default 05_route).
source [file join [file dirname [info script]] b6_common.tcl]
set t0 [clock seconds]
set BASE 05_route
if {[info exists ::env(B6_BASE)]} { set BASE $::env(B6_BASE) }
open_stage $BASE 06_eco
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
  redirect -file $RUN/reports/e_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/e_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/e_checks_$tag.txt]; set s [count_short $RUN/reports/e_lvs_$tag.txt]; set o [count_open $RUN/reports/e_lvs_$tag.txt]
  puts "E_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
proc tim {tag} {
  global RUN
  foreach s [get_object_name [all_scenarios]] {
    current_scenario $s
    foreach {dt nm} {max SETUP min HOLD} {
      catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "E_TIMING $tag $s $nm worst_slack=[get_attribute $p slack]" }
    }
  }
  current_scenario func_tt
  redirect -file $RUN/reports/e_constraints_$tag.txt { report_constraints -all_violators -max_transition -max_capacitance }
}
puts "B6_HALO_PRESENT: [sizeof_collection [get_routing_blockages -quiet]] routing blockages"
chk 0
tim 0
# ============================================================ A: antenna diodes
if {[file exists $RUN/eco_in/ant_pins.txt]} {
  set fh [open $RUN/eco_in/ant_pins.txt r]; set pairs {}
  while {[gets $fh l] >= 0} { if {[llength $l] == 2} { lappend pairs [lindex $l 0] [lindex $l 1] } }
  close $fh
  set diode [get_lib_cells sky130_hd_mcmm/sky130_fd_sc_hd__diode_2]
  set k 0; set nf 0; set made {}
  foreach {net pn} $pairs {
    set p [get_pins -quiet [list $pn]]
    if {[sizeof_collection $p] == 0} { incr nf; puts "A_WARN: no pin $pn"; continue }
    set cell [get_cells -of_objects $p]
    set cb [get_attribute $cell bbox]; set pb [get_attribute $p bbox]
    set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0}]
    set oy [lindex $cb 0 1]
    set orient [get_attribute $cell orientation]
    set nn [get_nets -of_objects $p]
    set name ANTDIO_$k
    create_cell $name $diode
    connect_net $nn [get_pins $name/DIODE]
    set_cell_location $name -coordinates [list [expr {$cx - 0.23}] $oy] -orientation $orient
    lappend made $name
    incr k
  }
  puts "A_DIODES: $k created, $nf pins not found"
  legalize_placement -cells [get_cells $made]
  redirect -file $R/e_legality_A.txt { check_legality -verbose }
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO_*/VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO_*/VPB]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO_*/VGND]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO_*/VNB]
  route_eco -max_detail_route_iterations 60
  set r [chk A0]
  for {set i 1} {$i <= 6} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk A$i]
  }
  puts "A_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
  tim A
} else { puts "A_SKIP: no eco_in/ant_pins.txt" }
# ============================================================ halos off, final checks
remove_routing_blockages [get_routing_blockages -quiet]
puts "B6_HALO_REMOVED: [sizeof_collection [get_routing_blockages -quiet]] routing blockages left"
# ============================================================ E: net-name hygiene (case-insensitive collisions)
define_name_rules b6_net -type net -case_insensitive
redirect -file $R/e_change_names.txt { change_names -rules b6_net -verbose }
puts "E_NAMES: change_names done (reports/e_change_names.txt)"
set r [chk final]
puts "E_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
tim final
redirect -file $R/e_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/e_pg_drc.txt { check_pg_drc }
save_stage 06_eco
stage_time eco $t0
exit
