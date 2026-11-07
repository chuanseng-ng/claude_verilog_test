# 05h_fix.tcl -- B5g step 2: remove the one repeater that could not be legalised (B5G16__inst_131, overlaps the PG rail -> 2 met1 shorts with VPWR/VGND),
#   attach antenna diodes to the 4 clock-tree pins that violate the antenna rule, ecoRoute, DRC loop, re-time, PDN self-check.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 05g_eco
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
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
set rc [catch { ecoDeleteRepeater -inst B5G16__inst_131 } e]; puts "ECO_DEL B5G16__inst_131 rc=$rc $e"
foreach {i p} {CTS_ccl_buf_00248 A u_core/u_dcache_wb_tag_q_reg[12] CLK u_core/u_icache_data_din_q_reg[5] CLK u_core/u_icache_data_din_q_reg[14] CLK} {
  set rc [catch { attachDiode -diodeCell sky130_fd_sc_hd__diode_2 -pin $i $p -prefix B5GDIODE } e]; puts "ATTACH_DIODE $i/$p rc=$rc $e"
}
save_stage 05h_pre_route
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
for {set k 1} {$k <= 6} {incr k} {
  verify_drc -limit 100000 -report $R/h_drc_$k.txt
  set d [count_drc $R/h_drc_$k.txt]
  puts "REPAIR_PASS $k: DRC=$d"
  if {$d == 0} break
  ecoRoute -fix_drc
}
verify_drc -limit 100000 -report $R/h_drc_final.txt
puts "DRC_FINAL: [count_drc $R/h_drc_final.txt]"
verifyProcessAntenna -reportfile $R/h_antenna.txt -error 100000
save_stage 05h_final
timeDesign -postRoute -outDir $R/h1_setup
timeDesign -postRoute -hold -outDir $R/h1_hold
foreach n {VPWR VGND} {
  verify_connectivity -type special -net $n -error 100000 -report $R/h_pdn_special_$n.txt
  puts "PDN_SELFCHECK $n: special-wire pieces = [pieces $R/h_pdn_special_$n.txt]"
}
stage_time fix $t0
exit
