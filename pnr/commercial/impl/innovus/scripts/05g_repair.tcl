# 05g_repair.tcl -- B5g: in-place repair of b5f (restores the PRE-FILL post-route db 05_route; fill/decap is re-added by 06_finish afterwards).
#   (1) diagnosis of the axi_rdata_i setup paths; (2) ecoAddRepeater (spread buf_8) on the AXI input-port nets whose route is > 2 mm (list in $RUN/g_nets.txt,
#   from scripts/b5g_nets.py on the b5f DEF); (3) ecoRoute of the changed nets; (4) ecoRoute -fix_drc loop (incl. the met1 short at (8.9,923));
#   (5) re-time, antenna, PDN self-check.  No re-placement of the design, no CTS.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
if {![info exists ::env(FROM_LABEL)]} { set ::env(FROM_LABEL) 05_route }
restore_stage $::env(FROM_LABEL)
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} {
  set n -1; set fh [open $f r]
  while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }
  close $fh; return $n
}
proc pieces {f} { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[string match "*has special routes with opens*" $l]} { incr n } }; close $fh; return $n }
# ---- (1) baseline + diagnosis
timeDesign -postRoute -outDir $R/g0_base
set rc [catch { report_timing -max_paths 25 -nworst 1 -fields {net fanout cap slew} > $R/g0_worst25_fields.txt } e]; puts "DIAG report_timing fields rc=$rc $e"
if {$rc} { catch { report_timing -max_paths 25 -nworst 1 -net -fanout > $R/g0_worst25_fields.txt } }
set fh [open $RUN/g_nets.txt r]; set nets {}
while {[gets $fh l] >= 0} { if {[llength $l] >= 1} { lappend nets [lindex $l 0] } }
close $fh
puts "B5G: [llength $nets] port nets selected for repeaters"
# ---- (2) repeaters
setEcoMode -reset
set rc [catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false } e]; puts "setEcoMode rc=$rc $e"
set i 0
foreach n $nets {
  incr i
  set rc [catch { ecoAddRepeater -net $n -cell sky130_fd_sc_hd__buf_8 -firstSpreadDist 40 -spreadDist 600 -spreadPrefix B5G${i}_ } e]
  puts "ECO_REP $n rc=$rc $e"
}
set nrep 0; foreach inst [dbGet top.insts.name B5G*] { incr nrep }
puts "B5G: repeater instances in db: $nrep"
catch { checkPlace $R/g1_checkPlace.txt }
save_stage 05g_pre_eco_route
# ---- (3) route the changed nets
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
# ---- (4) DRC repair loop
for {set k 1} {$k <= 6} {incr k} {
  verify_drc -limit 100000 -report $R/g_drc_$k.txt
  set d [count_drc $R/g_drc_$k.txt]
  puts "REPAIR_PASS $k: DRC=$d"
  if {$d == 0} break
  ecoRoute -fix_drc
}
verify_drc -limit 100000 -report $R/g_drc_final.txt
puts "DRC_FINAL: [count_drc $R/g_drc_final.txt]"
verifyProcessAntenna -reportfile $R/g_antenna.txt -error 100000
save_stage 05g_eco
# ---- (5) timing
timeDesign -postRoute -outDir $R/g1_setup
timeDesign -postRoute -hold -outDir $R/g1_hold
catch { report_timing -max_paths 25 -nworst 1 -fields {net fanout cap slew} > $R/g1_worst25.txt }
foreach n {VPWR VGND} {
  verify_connectivity -type special -net $n -error 100000 -report $R/g_pdn_special_$n.txt
  puts "PDN_SELFCHECK $n: special-wire pieces = [pieces $R/g_pdn_special_$n.txt]"
}
stage_time repair $t0
exit
