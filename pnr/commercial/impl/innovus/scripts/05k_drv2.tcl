# 05k_drv2.tcl -- b5k step (5), part 2.  optDesign -postRoute -drv (05k_hold -> 05k_drv) cut max_tran 845 -> 396 pins but left max_cap at 263 pins / 477 nets.  Evidence (k_drv_drv_violators.txt classification):
#   max_cap 263 = 102 INPUT/OUTPUT PORT nets (limit 0.561 pF = the set_driving_cell buf_4) + 160 SRAM dout0 pins (macro Liberty limit, bead o1i, not fixable here) + 1;
#   max_tran 396 = pins of the diodes/buffers hung on those same port nets + ports; max_fanout 205 = CTS clock-tree buffers (exempt by design).
#   Fix for the port nets: one sky130 buf_8 repeater at the port (ecoAddRepeater on the whole net, the b5g B5G-repeater method), ecoRoute, DRC loop, re-time ALL views.
#   Accept rule (checked by the caller from the reports): tt nominal setup >= 0, no new hold violation in av_tt/av_ff_*, DRC 0; otherwise keep 05k_drv.   env: FROM_LABEL (05k_drv), OUT_LABEL (05k_drv2)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05k_drv"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "05k_drv2"}]
restore_stage $FL
common_settings
set R $RUN/reports
set PFX [expr {[info exists ::env(PFX)] ? $::env(PFX) : ""}]
set KT [expr {[info exists ::env(KTAG)] ? $::env(KTAG) : "kd2"}]
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
# violating port nets from the cap/tran report of the source db
report_constraint -all_violators -drv_violation_type {max_capacitance max_transition} > $R/${KT}_before.txt
set ports {}
foreach t [dbGet top.terms] { if {[dbGet $t.isInput] == 1} { lappend ports [dbGet $t.name] } }
array set isin {}; foreach p $ports { set isin([string map {\\ {}} $p]) $p }
set viol {}; set fh [open $R/${KT}_before.txt r]; set sec ""
while {[gets $fh l] >= 0} {
  if {[regexp {Check type : (\S+)} $l -> s]} { set sec $s }
  if {[regexp {^\s*\| (\S+)\s+\| ([\d.]+)\s+\| ([\d.-]+)\s+\| (-[\d.]+) \|} $l -> n]} {
    if {[regexp {^[A-Za-z0-9_]+_i(\[[0-9]+\])?$} $n]} { lappend viol $n }
  }
}
close $fh
set viol [lsort -unique $viol]
puts "K_DRV2: [llength $viol] violating input-port nets: [lrange $viol 0 8] ..."
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
set ok 0; set bad 0; set k 0
foreach n $viol {
  incr k
  if {[catch { ecoAddRepeater -net $n -cell sky130_fd_sc_hd__buf_8 -name B5KDRV${PFX}_$k } e] && [catch { ecoAddRepeater -net [string map {[ {\[} ] {\]}} $n] -cell sky130_fd_sc_hd__buf_8 -name B5KDRV${PFX}_$k } e]} { incr bad; if {$bad < 4} { puts "K_DRV2_FAIL $n: $e" } } else { incr ok }
}
puts "K_DRV2: repeaters added ok=$ok bad=$bad"
save_stage 05k_drv2_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
verify_drc -limit 100000 -report $R/${KT}_drc_1.txt
set d [count_drc $R/${KT}_drc_1.txt]; puts "${KT}_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 5} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/${KT}_drc_$kk.txt; set d [count_drc $R/${KT}_drc_$kk.txt]; puts "${KT}_DRC_$kk: $d" }
timeDesign -postRoute -outDir $R/${KT}_setup
timeDesign -postRoute -hold -outDir $R/${KT}_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/${KT}_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/${KT}_view_${v}_hold.txt }
}
catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout} > $R/${KT}_drv_violators.txt }
verifyProcessAntenna -reportfile $R/${KT}_antenna.txt -error 100000
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/${KT}_pdn_special_$n.txt }
save_stage $OL
stage_time drv2 $t0
exit
