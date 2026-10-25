# 05c_repair.tcl -- Step B5a stage 5b: incremental detail-route repair until check_routes DRCs and check_lvs shorts reach 0 (max 6 passes).
#   First route_auto + route_opt left 81 DRCs and 100 shorts, mostly at SRAM pin edges (see reports/route_checks.txt).
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 05b_repair 05c_repair
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
proc count_drc {f} {
  set n -1; set fh [open $f r]
  while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }
  close $fh; return $n
}
proc count_short {f} {
  set n -1; set fh [open $f r]
  while {[gets $fh l] >= 0} { regexp {Total number of short violations is (\d+)} $l -> n }
  close $fh; return $n
}
for {set i 1} {$i <= 8} {incr i} {
  redirect -file $RUN/reports/repair_checks_$i.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/repair_lvs_$i.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/repair_checks_$i.txt]; set s [count_short $RUN/reports/repair_lvs_$i.txt]
  puts "REPAIR_PASS $i: DRCs=$d shorts=$s"
  if {$d == 0 && $s == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
}
save_stage 05c_repair
stage_time repair $t0
exit
