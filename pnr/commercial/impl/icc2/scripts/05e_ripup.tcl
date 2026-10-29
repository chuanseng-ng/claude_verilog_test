# 05e_ripup.tcl -- Step B5e stage 5e: rip up and re-route the nets that still carry shorts/DRCs/opens after 05c (hard li1 ban stays in force), then incremental repair.
#   Base = 05c_repair (hard mode, 0 li1).  Nets = both ends of every short + every open net (check_lvs), + nets named by check_routes DRCs where listed.
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 05c_repair 05e_ripup
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }; close $fh; return $n }
proc count_short {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of short violations is (\d+)} $l -> n }; close $fh; return $n }
proc bad_nets {lvsf chkf} {
  set names {}
  set fh [open $lvsf r]
  while {[gets $fh l] >= 0} {
    if {[regexp {Net1: (\S+)\. Net2: (\S+)\. BBox} $l -> a b]} { lappend names $a $b }
    if {[regexp {^Open nets are (.*)$} $l -> o]} { foreach x $o { lappend names $x } }
  }
  close $fh
  return [lsort -unique $names]
}
redirect -file $RUN/reports/e_checks_0.txt { check_routes -drc true -antenna true -open_net true }
redirect -file $RUN/reports/e_lvs_0.txt { check_lvs -checks all -max_errors 0 }
puts "RIPUP_START: DRCs=[count_drc $RUN/reports/e_checks_0.txt] shorts=[count_short $RUN/reports/e_lvs_0.txt]"
set names [bad_nets $RUN/reports/e_lvs_0.txt $RUN/reports/e_checks_0.txt]
set nets {}
foreach n $names { set c [get_nets -quiet [list $n]]; if {[sizeof_collection $c]} { set nets [add_to_collection $nets $c] } }
puts "RIPUP_NETS: [llength $names] names, [sizeof_collection $nets] nets resolved"
remove_routes -nets $nets -detail_route -global_route
route_eco -max_detail_route_iterations 60
set _np 4
if {[info exists ::env(B5E_PASSES)]} { set _np $::env(B5E_PASSES) }
for {set i 1} {$i <= $_np} {incr i} {
  redirect -file $RUN/reports/e_checks_$i.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/e_lvs_$i.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/e_checks_$i.txt]; set s [count_short $RUN/reports/e_lvs_$i.txt]
  puts "REPAIR_PASS $i: DRCs=$d shorts=$s"
  if {$d == 0 && $s == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
}
redirect -file $RUN/reports/e_checks_final.txt { check_routes -drc true -antenna true -open_net true }
redirect -file $RUN/reports/e_lvs_final.txt { check_lvs -checks all -max_errors 0 }
puts "REPAIR_FINAL: DRCs=[count_drc $RUN/reports/e_checks_final.txt] shorts=[count_short $RUN/reports/e_lvs_final.txt]"
save_stage 05e_ripup
stage_time ripup $t0
exit
