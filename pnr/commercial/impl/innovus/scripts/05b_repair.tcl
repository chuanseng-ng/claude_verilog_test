# 05b_repair.tcl -- Step B5b stage 5b: incremental detail-route DRC repair (ecoRoute -fix_drc) until verify_drc reports 0 (max 4 passes), then re-time.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 05a_routed
common_settings
setNanoRouteMode -drouteEndIteration 30
proc count_drc {f} {
  set n -1; set fh [open $f r]
  while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }
  close $fh; return $n
}
for {set i 1} {$i <= 4} {incr i} {
  verify_drc -limit 100000 -report $RUN/reports/repair_drc_$i.txt
  set d [count_drc $RUN/reports/repair_drc_$i.txt]
  puts "REPAIR_PASS $i: DRC=$d"
  if {$d == 0} break
  ecoRoute -fix_drc
}
verify_drc -limit 100000 -report $RUN/reports/repair_drc_final.txt
verifyProcessAntenna -reportfile $RUN/reports/antenna_after_repair.txt -error 100000
save_stage 05b_repair
stage_time repair $t0
exit
