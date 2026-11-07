# 05m_post.tcl -- b6 post-route optimisation, FULL MMMC (setup views av_ss av_tt, hold views av_ff av_tt).  Restores 05a_routed (NanoRoute result), then:
#   1 baseline timeDesign, all views
#   2 DRV together with the first timing pass: one buf_8 repeater on every violating INPUT-PORT net (b5k lesson: limit 0.561 pF = set_driving_cell buf_4), ecoRoute, DRC loop
#   3 optDesign -postRoute (setup, DRV)            4 optDesign -postRoute -hold with holdTargetSlack 0.2 and the ff view active (b5k: PT ff hold read ~0.17 ns worse than Innovus)
#   5 optDesign -postRoute -drv                    6 a second hold pass if any hold view still violates, DRC loop, final timing, antenna, PDN connectivity
#   Saves 05_route (the label 06m_finish restores).  env FROM_LABEL (05a_routed)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05a_routed"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
proc drc_loop {tag} {
  global R
  verify_drc -limit 100000 -report $R/${tag}_drc_1.txt
  set d [count_drc $R/${tag}_drc_1.txt]; puts "${tag}_DRC_1: $d"
  set k 1
  while {$d > 0 && $k < 5} { ecoRoute -fix_drc; incr k; verify_drc -limit 100000 -report $R/${tag}_drc_$k.txt; set d [count_drc $R/${tag}_drc_$k.txt]; puts "${tag}_DRC_$k: $d" }
  return $d
}
proc view_slacks {tag} {
  global R
  foreach v [all_analysis_views] {
    catch { report_timing -view $v -max_paths 1 -path_type summary > $R/${tag}_view_${v}_setup.txt }
    catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/${tag}_view_${v}_hold.txt }
  }
  catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout} > $R/${tag}_drv_violators.txt }
}
proc tdall {tag} {
  global R
  timeDesign -postRoute -outDir $R/${tag}_setup
  timeDesign -postRoute -hold -outDir $R/${tag}_hold
  view_slacks $tag
}
puts "M_VIEWS: [all_analysis_views]  setup=[all_setup_analysis_views] hold=[all_hold_analysis_views]"
setOptMode -fixFanoutLoad true -fixDrc true -holdTargetSlack 0.2
tdall m0
save_stage 05m_base
# ---- 2: repeaters on violating input-port nets
set ports {}
foreach t [dbGet top.terms] { if {[dbGet $t.isInput] == 1} { lappend ports [dbGet $t.name] } }
report_constraint -all_violators -drv_violation_type {max_capacitance max_transition} > $R/m_before_rep.txt
set viol {}; set fh [open $R/m_before_rep.txt r]
while {[gets $fh l] >= 0} {
  if {[regexp {^\s*\| (\S+)\s+\| ([\d.]+)\s+\| ([\d.-]+)\s+\| (-[\d.]+) \|} $l -> n]} { if {[regexp {^[A-Za-z0-9_]+_i(\[[0-9]+\])?$} $n]} { lappend viol $n } }
}
close $fh
set viol [lsort -unique $viol]
puts "M_REP: [llength $viol] violating input-port nets"
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
set ok 0; set bad 0; set k 0
foreach n $viol {
  incr k
  if {[catch { ecoAddRepeater -net $n -cell sky130_fd_sc_hd__buf_8 -name B6REP_$k } e] && [catch { ecoAddRepeater -net [string map {[ {\[} ] {\]}} $n] -cell sky130_fd_sc_hd__buf_8 -name B6REP_$k } e]} { incr bad; if {$bad < 4} { puts "M_REP_FAIL $n: $e" } } else { incr ok }
}
puts "M_REP: repeaters ok=$ok bad=$bad"
if {$ok > 0} { catch { ecoRoute } e; puts "ecoRoute: $e" }
setEcoMode -reset
drc_loop mrep
tdall m1
save_stage 05m_rep
# ---- 3: setup + DRV pass
optDesign -postRoute -outDir $R/m_opt_setup
drc_loop mopt
tdall m2
save_stage 05m_setup
# ---- 4: hold pass (ff + tt hold views, target slack 0.2)
setEcoMode -reset
setOptMode -fixHoldAllowSetupTnsDegrade false -holdTargetSlack 0.2
optDesign -postRoute -hold -outDir $R/m_opt_hold
drc_loop mhold
tdall m3
save_stage 05m_hold
# ---- 5: DRV
optDesign -postRoute -drv -outDir $R/m_opt_drv
drc_loop mdrv
tdall m4
save_stage 05m_drv
# ---- 6: second hold pass only if a hold view is still negative
set neg 0
foreach v [all_hold_analysis_views] { catch { set fh [open $R/m4_view_${v}_hold.txt r]; set s [read $fh]; close $fh; if {[regexp {slack[^\n]*-[0-9]} $s] || [regexp {\s-[0-9.]+\s*\n} $s]} { incr neg } } }
puts "M_HOLD2: views with a negative hold slack (rough parse): $neg"
if {$neg > 0} {
  optDesign -postRoute -hold -outDir $R/m_opt_hold2
  drc_loop mhold2
  tdall m5
}
verifyProcessAntenna -reportfile $R/m_antenna.txt -error 100000
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/m_pdn_special_$n.txt }
save_stage 05_route
stage_time m_post $t0
exit
