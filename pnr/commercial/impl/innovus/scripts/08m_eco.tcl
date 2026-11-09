# 08m_eco.tcl -- Innovus b8 ECO round on the post-route db (05_route) of the FLIPPED-I-cache floorplan; lists come from the b8 DRAFT finish (deck KLayout + OpenROAD antenna) and the judge on the draft:
#   (1) KLayout m3.6 pin stubs (STUBLIST, add_shape), (2) antenna diodes (ANTLIST, attachDiode, as 05m_eco), (3) dout0 max-cap buffers on EVERY pin of DOUTLIST ("pt-name cap" lines; buf_4 when cap >= 0.05 pF else buf_2), placed
#   next to the pin on its channel side (the flipped I-cache pins face the channel, so all 10 SRAMs are bufferable), (4) deck-antenna sinks a diode does not cure (ANTBUFLIST, ant_to_pins.py format): one buf_6 in front of the
#   sink pin (A gate 0.495 um2 vs 0.252 for dfrtn_1 RESET_B), then ecoRoute + DRC loop, re-time all views, antenna, PDN connectivity, save, dump the pre-fill DEF.
#   env: STUBLIST ANTLIST DOUTLIST ANTBUFLIST (files, any may be absent), FROM_LABEL (05_route), OUT_LABEL (08_eco)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05_route"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "08_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
proc esc {s} { return [string map {[ \\[ ] \\]} $s] }
proc inst_of {name} { return [lindex [dbGet -p top.insts.name [esc $name]] 0] }
proc term_pt {inst pin} {
  set i [inst_of $inst]
  set it [dbGet -p $i.instTerms.name "*/[esc $pin]"]
  set pt {}; catch { set pt [lindex [dbGet $it.pt] 0] }
  return [list $i $it $pt]
}
verify_drc -limit 100000 -report $R/e8_drc_0.txt; puts "E8_DRC_0: [count_drc $R/e8_drc_0.txt]"
# ---- (1) pin stubs
if {[info exists ::env(STUBLIST)] && [file exists $::env(STUBLIST)]} {
  source $::env(STUBLIST)
  set ok 0; set bad 0
  foreach s $B5K_STUBS {
    lassign $s net x0 y0 x1 y1 side
    if {[catch { add_shape -layer met3 -net $net -rect [list $x0 $y0 $x1 $y1] } obj] || $obj eq "0x0" || $obj eq ""} { incr bad; puts "M_PIN_FAIL $net: $obj" } else { incr ok }
  }
  puts "M_PIN: stubs ok=$ok bad=$bad of [llength $B5K_STUBS]"
  verify_drc -limit 100000 -report $R/e8_mp_drc.txt; puts "MP_DRC: [count_drc $R/e8_mp_drc.txt]"
}
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
# ---- (2) antenna diodes
if {[info exists ::env(ANTLIST)] && [file exists $::env(ANTLIST)]} {
  source $::env(ANTLIST)
  set k 0; set ok 0
  foreach p $PINS {
    lassign $p i pin
    incr k
    set rc [catch { attachDiode -diodeCell sky130_fd_sc_hd__diode_2 -pin $i $pin -prefix B8ANT } e]; puts "M_ANT_ATTACH $i/$pin rc=$rc $e"
    if {!$rc} { incr ok }
  }
  puts "M_ANT: diodes attached ok=$ok of [llength $PINS]"
}
# ---- (3) dout0 buffers
set made 0; set fail 0
if {[info exists ::env(DOUTLIST)] && [file exists $::env(DOUTLIST)]} {
  set fh [open $::env(DOUTLIST) r]
  while {[gets $fh l] >= 0} {
    if {[llength $l] != 2} continue
    lassign $l pn cap
    set kq [string last "/" $pn]; set inst [string range $pn 0 [expr {$kq-1}]]; set pin [string range $pn [expr {$kq+1}] end]
    lassign [term_pt $inst $pin] i it pt
    lassign $pt px py
    set box [lindex [dbGet $i.box] 0]
    set cy [expr {([lindex $box 1] + [lindex $box 3]) / 2.0}]
    set dy [expr {$py > $cy ? 4.0 : -4.0}]    ;# pin on the macro's top edge => buffer above it, bottom edge => below
    set cell [expr {$cap >= 0.05 ? "sky130_fd_sc_hd__buf_4" : "sky130_fd_sc_hd__buf_2"}]
    set termname "[esc $inst]/[esc $pin]"
    set rc [catch { ecoAddRepeater -term $termname -cell $cell -loc [list [expr {$px - 1.0}] [expr {$py + $dy}]] -name DB8_$made } e]
    if {$rc} { incr fail; puts "D_FAIL $pn rc=$rc $e" } else { incr made; puts "D_ADD $pn pt=$pt dy=$dy $e" }
  }
  close $fh
}
puts "E8_DOUT: made=$made fail=$fail"
# ---- (4) antenna sinks that need a larger gate
set na 0
if {[info exists ::env(ANTBUFLIST)] && [file exists $::env(ANTBUFLIST)]} {
  source $::env(ANTBUFLIST)
  foreach p $PINS {
    lassign $p inst pin
    set it [dbGet -p [inst_of $inst].instTerms.name "*/$pin"]
    set pt {}; catch { set pt [lindex [dbGet $it.pt] 0] }
    lassign $pt px py
    set rc [catch { ecoAddRepeater -term "$inst/$pin" -cell sky130_fd_sc_hd__buf_6 -loc [list [expr {$px - 2.0}] $py] -name AB8_$na } e]
    puts "A_ADD $inst/$pin pt=$pt rc=$rc $e"
    incr na
  }
}
set rc [catch { refinePlace } e]; puts "refinePlace rc=$rc"
checkPlace $R/e8_checkPlace.txt
save_stage ${OL}_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
setEcoMode -reset
verify_drc -limit 100000 -report $R/e8_drc_1.txt
set d [count_drc $R/e8_drc_1.txt]; puts "E8_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 6} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/e8_drc_$kk.txt; set d [count_drc $R/e8_drc_$kk.txt]; puts "E8_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/e8_antenna.txt -error 100000
timeDesign -postRoute -outDir $R/e8_setup
timeDesign -postRoute -hold -outDir $R/e8_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/e8_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/e8_view_${v}_hold.txt }
}
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/e8_pdn_special_$n.txt }
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time eco8 $t0
exit
