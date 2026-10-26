# 05d_final_repair.tcl (B5c step 3: ecoRoute -fix_drc AFTER post-route opt, which re-introduced a DRC)  [derived from 05b_repair.tcl]
# 05b_repair.tcl -- Step B5b stage 5b: incremental detail-route DRC repair (ecoRoute -fix_drc) until verify_drc reports 0 (max 4 passes), then re-time.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 05_route
common_settings
setNanoRouteMode -drouteEndIteration 30
proc count_drc {f} {
  set n -1; set fh [open $f r]
  while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }
  close $fh; return $n
}
for {set i 1} {$i <= 4} {incr i} {
  verify_drc -limit 100000 -report $RUN/reports/finalrepair_drc_$i.txt
  set d [count_drc $RUN/reports/finalrepair_drc_$i.txt]
  puts "REPAIR_PASS $i: DRC=$d"
  if {$d == 0} break
  ecoRoute -fix_drc
}
verify_drc -limit 100000 -report $RUN/reports/finalrepair_drc_final.txt
verifyProcessAntenna -reportfile $RUN/reports/antenna_after_finalrepair.txt -error 100000
timeDesign -postRoute -outDir $RUN/reports/timing_postFinalRepair
timeDesign -postRoute -hold -outDir $RUN/reports/timing_postFinalRepair_hold
save_stage 05d_final
stage_time repair $t0
exit
