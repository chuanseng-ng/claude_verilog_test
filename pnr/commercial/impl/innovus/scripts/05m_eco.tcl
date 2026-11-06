# 05m_eco.tcl -- b6 round-2 ECO set on the post-route db (05_route), in the b5k order, lists derived from the b6 DRAFT finish:
#   (1) KLayout m3.6: a met3 special-wire rectangle from each lone 0.33 x 0.33 um via pad to the die edge (add_shape; list STUBLIST from mk_pinstub_list.py)
#   (2) antenna: attachDiode (diode_2) on every gate pin that OpenROAD check_antennas marks VIOLATED (list ANTLIST from ant_to_pins.py), refinePlace BEFORE ecoRoute (b5k run-1 lesson), ecoRoute, DRC loop
#   then re-time all views, antenna, PDN connectivity, save 05m_eco and dump the pre-fill DEF to out_pre/ (input of the pre-fill signoff antenna check).
#   env: STUBLIST, ANTLIST (tcl files; either may be absent), FROM_LABEL (05_route), OUT_LABEL (05m_eco)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05_route"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "05m_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
# ---- (1) pin stubs
if {[info exists ::env(STUBLIST)] && [file exists $::env(STUBLIST)]} {
  source $::env(STUBLIST)
  set ok 0; set bad 0
  foreach s $B5K_STUBS {
    lassign $s net x0 y0 x1 y1 side
    if {[catch { add_shape -layer met3 -net $net -rect [list $x0 $y0 $x1 $y1] } obj] || $obj eq "0x0" || $obj eq ""} { incr bad; puts "M_PIN_FAIL $net: $obj" } else { incr ok }
  }
  puts "M_PIN: stubs ok=$ok bad=$bad of [llength $B5K_STUBS]"
  verify_drc -limit 100000 -report $R/mp_drc.txt; puts "MP_DRC: [count_drc $R/mp_drc.txt]"
}
# ---- (2) antenna diodes
if {[info exists ::env(ANTLIST)] && [file exists $::env(ANTLIST)]} {
  source $::env(ANTLIST)
  setEcoMode -reset
  catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
  set k 0; set ok 0
  foreach p $PINS {
    lassign $p i pin
    incr k
    set rc [catch { attachDiode -diodeCell sky130_fd_sc_hd__diode_2 -pin $i $pin -prefix B6ANT } e]; puts "M_ANT_ATTACH $i/$pin rc=$rc $e"
    if {!$rc} { incr ok }
  }
  puts "M_ANT: diodes attached ok=$ok of [llength $PINS]"
  set rc [catch { refinePlace } e]; puts "M_ANT refinePlace rc=$rc"
  checkPlace $R/me_checkPlace.txt
  save_stage 05m_eco_pre
  set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
  setEcoMode -reset
}
verify_drc -limit 100000 -report $R/me_drc_1.txt
set d [count_drc $R/me_drc_1.txt]; puts "me_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 5} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/me_drc_$kk.txt; set d [count_drc $R/me_drc_$kk.txt]; puts "me_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/me_antenna.txt -error 100000
timeDesign -postRoute -outDir $R/me_setup
timeDesign -postRoute -hold -outDir $R/me_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/me_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/me_view_${v}_hold.txt }
}
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/me_pdn_special_$n.txt }
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time eco $t0
exit
