# 05z_fix.tcl -- Step B5e stage 5z: targeted rip-up/re-route of the last remaining short (nets read from the 05y final check_lvs report), then re-check.
#   Base = 05y_repair (hard li1 ban).  Same options as the repair loops.
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 05y_repair 05z_fix
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
proc count_short {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of short violations is (\d+)} $l -> n }; close $fh; return $n }
redirect -file $RUN/reports/z_checks_0.txt { check_routes -drc true -antenna true -open_net true }
redirect -file $RUN/reports/z_lvs_0.txt { check_lvs -checks all -max_errors 0 }
puts "FIX_START: DRCs=[count_drc $RUN/reports/z_checks_0.txt] shorts=[count_short $RUN/reports/z_lvs_0.txt]"
set names {}
set fh [open $RUN/reports/z_lvs_0.txt r]
while {[gets $fh l] >= 0} { if {[regexp {Net1: (\S+)\. Net2: (\S+)\. BBox} $l -> a b]} { lappend names $a $b } }
close $fh
set names [lsort -unique $names]
set nets {}
foreach n $names { set c [get_nets -quiet [list $n]]; if {[sizeof_collection $c]} { set nets [add_to_collection $nets $c] } }
puts "FIX_NETS: $names ([sizeof_collection $nets] resolved)"
if {[sizeof_collection $nets] > 0} {
  remove_routes -nets $nets -detail_route -global_route
  route_eco -max_detail_route_iterations 60
}
for {set i 1} {$i <= 3} {incr i} {
  redirect -file $RUN/reports/z_checks_$i.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/z_lvs_$i.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/z_checks_$i.txt]; set s [count_short $RUN/reports/z_lvs_$i.txt]
  puts "FIX_PASS $i: DRCs=$d shorts=$s"
  if {$d == 0 && $s == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
}
puts "FIX_FINAL: DRCs=[count_drc $RUN/reports/z_checks_$i.txt] shorts=[count_short $RUN/reports/z_lvs_$i.txt]"
save_stage 05z_fix
stage_time fix $t0
exit
