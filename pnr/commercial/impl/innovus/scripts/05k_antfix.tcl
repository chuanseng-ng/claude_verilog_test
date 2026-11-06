# 05k_antfix.tcl -- b5k step (4).  Innovus verifyProcessAntenna has NO side-area switch (help: -detailed -error -reportfile only; setAntennaMode does not exist; measured by 05k_ant.tcl), so its native
#   count (1) cannot be reconciled with the deck-style check (OpenROAD check_antennas, ANTENNASIDEAREARATIO): the 8 b5k pre-fill violators are ALL side-area (met2/met3 400..3669, met4 400).
#   Fix = a diode_2 on each violating gate pin (attachDiode, the b5g 05h method), ecoRoute, DRC loop, re-time; the caller re-runs the deck check on the new DEF.  env FROM_LABEL (05k_pin) OUT_LABEL (05k_antfix)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05k_pin"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "05k_antfix"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
set PINS [list \
 {FE_PDC208_mbist_status_o_51 A} {u_core/g424877 B1} {g45325 C2} {u_core/u_icache_gen_data_sram\[0\].u_data_collar_g_cmp.fail0_n_q_reg RESET_B} \
 {u_core/u_dcache_wb_buf_q_reg\[1\]\[25\] CLK} {u_core/g422135 A1} {u_core/g372623 A0} {u_core/g430659 B1}]
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
set k 0; set ok 0
foreach p $PINS {
  lassign $p i pin
  incr k
  set rc [catch { attachDiode -diodeCell sky130_fd_sc_hd__diode_2 -pin $i $pin -prefix B5KANT } e]; puts "K_ANT_ATTACH $i/$pin rc=$rc $e"
  if {!$rc} { incr ok }
}
puts "K_ANT: diodes attached ok=$ok of [llength $PINS]"
# attachDiode drops each diode at an off-grid spot (e.g. 388.26 1393.797) on top of its neighbour: run 1 of b5k had 5 diodes overlapping std cells (KLayout licon/li/difftap hits, LVS nets 35684 vs 35688,
# checkPlace 19 violations vs b5j's 5).  Legalise BEFORE the eco route so the routes follow the final positions.
set rc [catch { refinePlace } e]; puts "K_ANT refinePlace rc=$rc"
checkPlace $R/ka2_checkPlace.txt
save_stage 05k_antfix_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
verify_drc -limit 100000 -report $R/ka2_drc_1.txt
set d [count_drc $R/ka2_drc_1.txt]; puts "ka2_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 5} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/ka2_drc_$kk.txt; set d [count_drc $R/ka2_drc_$kk.txt]; puts "ka2_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/ka2_antenna.txt -error 100000
timeDesign -postRoute -outDir $R/ka2_setup
timeDesign -postRoute -hold -outDir $R/ka2_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/ka2_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/ka2_view_${v}_hold.txt }
}
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/ka2_pdn_special_$n.txt }
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time antfix $t0
exit
