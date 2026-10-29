# 05d_repair.tcl -- Step B5e stage 5d (continuation of 05c with an experiment knob via env B5E_MIN_MODE): incremental detail-route repair until check_routes DRCs and check_lvs shorts reach 0 (max 6 passes).
#   First route_auto + route_opt left 81 DRCs and 100 shorts, mostly at SRAM pin edges (see reports/route_checks.txt).
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
set _base 05c_repair; set _out 05d_repair
if {[info exists ::env(B5E_BASE)]} { set _base $::env(B5E_BASE) }
if {[info exists ::env(B5E_OUT)]} { set _out $::env(B5E_OUT) }
open_stage $_base $_out
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
source [file join $SCRIPTDIR reload.tcl]
if {[info exists ::env(B5E_MIN_MODE)] && $::env(B5E_MIN_MODE) ne ""} { set_app_options -name route.common.global_min_layer_mode -value $::env(B5E_MIN_MODE); puts "B5E_MIN_MODE override: [get_app_option_value -name route.common.global_min_layer_mode]" }
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
set _np 4
if {[info exists ::env(B5E_PASSES)]} { set _np $::env(B5E_PASSES) }
for {set i 1} {$i <= $_np} {incr i} {
  redirect -file $RUN/reports/repair_checks_$i.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/repair_lvs_$i.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/repair_checks_$i.txt]; set s [count_short $RUN/reports/repair_lvs_$i.txt]
  puts "REPAIR_PASS $i: DRCs=$d shorts=$s"
  if {$d == 0 && $s == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
}
# final state after the last route_detail (the loop above checks BEFORE each route_detail)
redirect -file $RUN/reports/repair_checks_final_05d.txt { check_routes -drc true -antenna true -open_net true }
redirect -file $RUN/reports/repair_lvs_final_05d.txt { check_lvs -checks all -max_errors 0 }
puts "REPAIR_FINAL: DRCs=[count_drc $RUN/reports/repair_checks_final_05d.txt] shorts=[count_short $RUN/reports/repair_lvs_final_05d.txt]"
save_stage $_out
stage_time repair $t0
exit
