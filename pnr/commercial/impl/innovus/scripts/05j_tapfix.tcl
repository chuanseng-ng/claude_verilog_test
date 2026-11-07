# 05j_tapfix.tcl -- b5j: in-place ECO on b5h's final pre-fill routed db (05_route): tie the 146 untied endcap n-well islands (x = 98.44 um, the right edge of the left pocket) with one
#   tapvpwrvgnd_1 each, abutting the S-oriented endcap (list: b5j_tap_list.tcl, from nwell_islands_innovus.py).  Physical-only cells: no logic change, no timing change; the routed signal nets are untouched.
#   Root cause (addWellTap lattice, see report): taps are laid every 25.76 um from the row start; the last lattice tap of the 77 um pocket row segment ends 0.46 um (one site) before the endcap,
#   the 0.08 um n-well slit between tap well and endcap well is an nwell.2a violation and the endcap well is not tied to anything.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 05_route
common_settings
set R $RUN/reports
source [file join $SCRIPTDIR b5j_tap_list.tcl]
proc count_drc {f} {
  set n -1; set fh [open $f r]
  while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }
  close $fh; return $n
}
puts "B5J: [llength $B5J_TAPS] taps to add; insts before: [llength [dbGet top.insts]]"
set cell sky130_fd_sc_hd__tapvpwrvgnd_1
set ninst0 [llength [dbGet top.insts]]
set ntap0 [llength [dbGet -p2 top.insts.cell.name $cell]]
verifyConnectivity -type all -noAntenna -report $R/j_connectivity_before.txt -error 100000
puts "B5J_BEFORE connectivity report written"
set added 0; set k 0
foreach t $B5J_TAPS {
  lassign $t x y o
  incr k
  set name B5J_TAP_$k
  set ok 0
  foreach {orient} {MX FS} {
    foreach variant {1 2 3} {
      switch $variant {
        1 { set cmd [list create_inst -cell $cell -inst $name -location [list $x $y] -orient $orient -physical] }
        2 { set cmd [list create_inst -cell $cell -inst $name -location [list $x $y] -orient $orient] }
        3 { set cmd [list addInst -cell $cell -inst $name -loc [list $x $y] -ori $orient -physical] }
      }
      if {![catch $cmd e]} { set ok 1; break } else { if {$k == 1} { puts "B5J_CMD_FAIL: $cmd -> $e" } }
    }
    if {$ok} break
  }
  if {!$ok} { puts "B5J_FATAL: cannot create $name"; catch {help create_inst}; exit 3 }
  if {$k == 1} { puts "B5J_CMD_OK: $cmd" }
  catch { set_db inst:$name .place_status fixed }
  incr added
}
puts "B5J: added $added taps; insts now [llength [dbGet top.insts]]"
globalNetConnect VPWR -type pgpin -pin VPWR -all -override
globalNetConnect VGND -type pgpin -pin VGND -all -override
globalNetConnect VPWR -type pgpin -pin VPB  -all -override
globalNetConnect VGND -type pgpin -pin VNB  -all -override
puts "B5J_CHECK: first tap [dbGet [dbGet -p top.insts.name B5J_TAP_1].box] orient [dbGet [dbGet -p top.insts.name B5J_TAP_1].orient] status [dbGet [dbGet -p top.insts.name B5J_TAP_1].pStatus]"
save_stage 05j_pre
checkPlace $R/j_checkPlace.txt
verify_drc -limit 100000 -report $R/j_drc_1.txt
set d [count_drc $R/j_drc_1.txt]
puts "J_DRC_1: $d"
set k2 1
while {$d > 0 && $k2 <= 4} {
  setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
  ecoRoute -fix_drc
  incr k2
  verify_drc -limit 100000 -report $R/j_drc_$k2.txt
  set d [count_drc $R/j_drc_$k2.txt]
  puts "J_DRC_$k2: $d"
}
verifyConnectivity -type all -noAntenna -report $R/j_connectivity_after.txt -error 100000
verify_connectivity -type special -report $R/j_pg_connectivity_after.txt -error 100000
puts "B5J: taps now [llength [dbGet -p2 top.insts.cell.name $cell]] (was $ntap0); insts [llength [dbGet top.insts]] (was $ninst0)"
save_stage 05j_taps
stage_time tapfix $t0
exit
