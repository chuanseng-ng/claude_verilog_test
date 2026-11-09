# 07m_eco.tcl -- Innovus b7 ECO round on the b6 final pre-fill label (05m_eco), ONE combined pass (the b6 arm stays untouched).  Env: DOUTLIST (pt-name cap lines), ANTLIST (tcl `set PINS`), FROM_LABEL (05m_eco), OUT_LABEL (07_eco)
#   D  #6  SRAM dout0 max-cap: one buffer (buf_4 >= 0.05 pF else buf_2) next to every dout0 pin of DOUTLIST whose SRAM has legal row sites near its pins.  The five icache SRAMs have their dout0 pins on the macro's bottom edge
#          (y 20 um) OUTSIDE the row lattice (rows start at y 24.48 and the macro covers them): no site within 139 um => filtered out (see docs), only the dcache pin(s) are buffered.
#   A  #5  deck antenna: the 2 side-area nets of the b6 deck report (ANTLIST = ant_to_pins.py output): the long wire ends on a gate of 0.252 um2 (dfrtn_1 RESET_B); a buf_6 (A gate 0.495 um2) in front of the sink pin
#          doubles the gate the wire charges, ratio 457/581 -> 232/296 < 400.  The existing B6ANT diodes stay.
#   then ecoRoute + DRC loop, re-time all views, antenna, PDN connectivity, save, dump the pre-fill DEF to out_pre/.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05m_eco"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "07_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
proc view_slacks {tag} {
  global R
  foreach v [all_analysis_views] {
    catch { report_timing -view $v -max_paths 1 -path_type summary > $R/e7_${tag}_view_${v}_setup.txt }
    catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/e7_${tag}_view_${v}_hold.txt }
  }
}
puts "HELP_ECOADD: [catch {help ecoAddRepeater} hh] $hh"
verify_drc -limit 100000 -report $R/e7_drc_0.txt; puts "E7_DRC_0: [count_drc $R/e7_drc_0.txt]"
view_slacks pre
# pt-name "u_core/u_dcache_u_tag_sram/dout0[28]" -> {inst pin}
proc split_pt {pn} { set k [string last "/" $pn]; return [list [string range $pn 0 [expr {$k-1}]] [string range $pn [expr {$k+1}] end]] }
proc term_pt {inst pin} {
  set i [lindex [dbGet -p top.insts.name [string map {[ \\[ ] \\]} $inst]] 0]
  set it [dbGet -p $i.instTerms.name "*/[string map {[ \\[ ] \\]} $pin]"]
  set pt {}
  catch { set pt [lindex [dbGet $it.pt] 0] }
  return [list $i $it $pt]
}
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
set made 0; set fail 0
# ---- D: dout0
if {[info exists ::env(DOUTLIST)] && [file exists $::env(DOUTLIST)]} {
  set fh [open $::env(DOUTLIST) r]
  set filt dcache; if {[info exists ::env(B7_DOUT_FILTER)]} { set filt $::env(B7_DOUT_FILTER) }
  while {[gets $fh l] >= 0} {
    if {[llength $l] != 2} continue
    lassign $l pn cap
    if {$filt ne "all" && ![string match *$filt* $pn]} { puts "D_SKIP (no legal site near the pin) $pn"; continue }
    lassign [split_pt $pn] inst pin
    lassign [term_pt $inst $pin] i it pt
    puts "D_TERM $pn inst=$i term=$it pt=$pt"
    set cell [expr {$cap >= 0.05 ? "sky130_fd_sc_hd__buf_4" : "sky130_fd_sc_hd__buf_2"}]
    lassign $pt px py
    set loc [list [expr {$px - 1.0}] [expr {$py - 4.0}]]
    set termname "[string map {[ \\[ ] \\]} $inst]/[string map {[ \\[ ] \\]} $pin]"
    set rc [catch { ecoAddRepeater -term $termname -cell $cell -loc $loc -name DB7_$made } e]
    puts "D_ADD $pn rc=$rc $e"
    if {$rc} { incr fail } else { incr made }
  }
  close $fh
}
# ---- A: antenna sinks
if {[info exists ::env(ANTLIST)] && [file exists $::env(ANTLIST)]} {
  source $::env(ANTLIST)
  set k 0
  foreach p $PINS {
    lassign $p inst pin
    set i [lindex [dbGet -p top.insts.name $inst] 0]
    set it [dbGet -p $i.instTerms.name "*/$pin"]
    set pt {}; catch { set pt [lindex [dbGet $it.pt] 0] }
    lassign $pt px py
    set termname "$inst/$pin"
    set rc [catch { ecoAddRepeater -term $termname -cell sky130_fd_sc_hd__buf_6 -loc [list [expr {$px - 2.0}] $py] -name AB7_$k } e]
    puts "A_ADD $termname pt=$pt rc=$rc $e"
    if {$rc} { incr fail } else { incr made }
    incr k
  }
}
puts "E7_ADDED: made=$made fail=$fail"
set rc [catch { refinePlace } e]; puts "refinePlace rc=$rc"
checkPlace $R/e7_checkPlace.txt
save_stage 07_eco_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
setEcoMode -reset
verify_drc -limit 100000 -report $R/e7_drc_1.txt
set d [count_drc $R/e7_drc_1.txt]; puts "E7_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 5} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/e7_drc_$kk.txt; set d [count_drc $R/e7_drc_$kk.txt]; puts "E7_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/e7_antenna.txt -error 100000
timeDesign -postRoute -outDir $R/e7_setup
timeDesign -postRoute -hold -outDir $R/e7_hold
view_slacks post
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/e7_pdn_special_$n.txt }
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time eco7 $t0
exit
