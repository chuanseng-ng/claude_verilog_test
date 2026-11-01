# 05k_pin.tcl -- b5k step (2): KLayout m3.6 (met3 min area) at 54 die-edge I/O pins.  Each hit is the lone 0.33 x 0.33 um met3 via pad where a met2 stub meets a met3 pin (the pin rectangle is pin-purpose in the GDS).
#   Fix: add a met3 wire rectangle on the pin's own net from the pad to the die edge (list: b5k_pinstub_list.tcl from mk_pinstub_list.py).  env: FROM_LABEL (default 05k_drv), OUT_LABEL (default 05k_pin).
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05k_drv"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "05k_pin"}]
restore_stage $FL
common_settings
set R $RUN/reports
source [file join $SCRIPTDIR b5k_pinstub_list.tcl]
proc nwires {n} { return [llength [dbGet [dbGet -p top.nets.name $n].wires]] }
set ok 0; set bad 0; set k 0
foreach s $B5K_STUBS {
  lassign $s net x0 y0 x1 y1 side
  incr k
  set n0 [nwires $net]
  set done 0
  foreach cmd [list \
     [list create_shape -layer met3 -net $net -rect [list $x0 $y0 $x1 $y1] -shape none] \
     [list create_shape -layer met3 -net $net -rect [list $x0 $y0 $x1 $y1]] \
     [list editAddRoute -net $net -layer met3 -width 0.33 -pts [list [list [expr {$side eq "E" ? $x0 + 0.165 : $x1 - 0.165}] [expr {($y0+$y1)/2}]] [list [expr {$side eq "E" ? $x1 : $x0}] [expr {($y0+$y1)/2}]]]]] {
    if {[catch $cmd e]} { if {$k == 1} { puts "K_PIN_CMD_FAIL: $cmd -> $e" }; continue }
    if {[nwires $net] != $n0 || [llength [dbGet [dbGet -p top.nets.name $net].sWires]] > 0} { set done 1; if {$k == 1} { puts "K_PIN_CMD_OK: $cmd" }; break }
    if {$k == 1} { puts "K_PIN_CMD_NOEFFECT: $cmd" }
  }
  if {$done} { incr ok } else { incr bad; puts "K_PIN_FAIL $net" }
}
puts "K_PIN: stubs ok=$ok bad=$bad of [llength $B5K_STUBS]"
verify_drc -limit 100000 -report $R/kp_drc.txt
set d -1; set fh [open $R/kp_drc.txt r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set d $v } }; close $fh
puts "KP_DRC: $d"
verifyProcessAntenna -reportfile $R/kp_antenna.txt -error 100000
verifyConnectivity -type regular -noAntenna -net debug_rs1_data_o\[30\] -report $R/kp_conn_sample.txt -error 1000
save_stage $OL
stage_time pin $t0
exit
