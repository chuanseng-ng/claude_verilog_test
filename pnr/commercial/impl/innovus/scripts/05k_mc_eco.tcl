# 05k_mc_eco.tcl -- b5k round 2, session 1.  In place on b5j's final pre-fill routed db (05j_taps).  NO re-place, NO re-CTS.  env: PHASES (subset of "mc hold drv", default all), FROM_LABEL (default 05j_taps)
#   mc   : (6) mbist input delays in Innovus' own SDC (update_constraint_mode with sky130_cpu_innovus_b5k_post.sdc), (8) rc_min/rc_max (new min/max capTables) + tt/ff delay corners, 4+2 analysis views, baseline timing per view
#   hold : (7) multi-corner hold ECO  optDesign -postRoute -hold  with the ff hold views active (setup views stay tt nom/max; tt setup must stay >= 0), DRC loop
#   drv  : (5) optDesign -postRoute -drv (max_cap / max_tran nets), DRC loop
#   Each phase saves a db (05k_mc, 05k_hold, 05k_drv).  The b5h fixes (capTable, update_io_latency false, clk_io 3.295) are kept: the new SDC carries the same clk_io statements.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set PH [expr {[info exists ::env(PHASES)] ? $::env(PHASES) : "mc hold drv"}]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05j_taps"}]
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
# per-view worst slack (setup: late, hold: early) -> reports/<tag>_view_<view>_<kind>.txt
proc view_slacks {tag} {
  global R
  foreach v [all_analysis_views] {
    catch { report_timing -view $v -max_paths 1 -path_type summary > $R/${tag}_view_${v}_setup.txt }
    catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/${tag}_view_${v}_hold.txt }
  }
}
proc drv_counts {tag} {
  global R
  catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout} > $R/${tag}_drv_violators.txt }
}
if {[lsearch $PH mc] >= 0} {
  # ---- (6) SDC with the mbist input delays
  update_constraint_mode -name func -sdc_files [list $REPO/pnr/commercial/constraints/sky130_cpu_innovus_b5k_post.sdc]
  puts "K_SDC: updated constraint mode func"
  # ---- (8) corners.  rc_nom exists (capTable nom); add rc_min / rc_max from the new capTables; ff / tt-max delay corners.  SRAM Liberty is tt-only in every set (as in pdk mmmc.tcl).
  set CT $REPO/pnr/commercial/impl/innovus/captbl6
  set HDLIB "$::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib"
  set SRAMLIB "$REPO/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib"
  create_library_set -name lib_ff -timing [list $HDLIB/sky130_fd_sc_hd__ff_n40C_1v95.lib $SRAMLIB]
  create_rc_corner -name rc_min -temperature 25 -cap_table $CT/sky130A_min_li1m1.captbl
  create_rc_corner -name rc_max -temperature 25 -cap_table $CT/sky130A_max_li1m1.captbl
  create_delay_corner -name dc_tt_max -library_set lib_tt -rc_corner rc_max
  create_delay_corner -name dc_ff_nom -library_set lib_ff -rc_corner rc_nom
  create_delay_corner -name dc_ff_min -library_set lib_ff -rc_corner rc_min
  create_delay_corner -name dc_ff_max -library_set lib_ff -rc_corner rc_max
  create_analysis_view -name av_tt_max -constraint_mode func -delay_corner dc_tt_max
  create_analysis_view -name av_ff_nom -constraint_mode func -delay_corner dc_ff_nom
  create_analysis_view -name av_ff_min -constraint_mode func -delay_corner dc_ff_min
  create_analysis_view -name av_ff_max -constraint_mode func -delay_corner dc_ff_max
  set_analysis_view -setup {av_tt av_tt_max} -hold {av_tt av_ff_nom av_ff_min av_ff_max}
  puts "K_MMMC: views [all_analysis_views]"
  extractRC
  timeDesign -postRoute -outDir $R/k_mc_setup
  timeDesign -postRoute -hold -outDir $R/k_mc_hold
  view_slacks k_mc
  drv_counts k_mc
  catch { report_timing -from [get_ports {mbist_cfg_i[5]}] -path_type full_clock -max_paths 1 > $R/k_mc_spot_mbist_setup.txt }
  catch { report_timing -from [get_ports {mbist_cfg_i[5]}] -early -path_type full_clock -max_paths 1 > $R/k_mc_spot_mbist_hold.txt }
  catch { report_clock_timing -type latency -clock clk_io > $R/k_mc_clk_io_latency.txt }
  save_stage 05k_mc
  stage_time k_mc $t0
}
if {[lsearch $PH hold] >= 0} {
  setEcoMode -reset
  setOptMode -fixHoldAllowSetupTnsDegrade false
  optDesign -postRoute -hold -outDir $R/k_opt_hold
  drc_loop kh
  timeDesign -postRoute -outDir $R/k_hold_setup
  timeDesign -postRoute -hold -outDir $R/k_hold_hold
  view_slacks k_hold
  drv_counts k_hold
  verifyProcessAntenna -reportfile $R/k_hold_antenna.txt -error 100000
  save_stage 05k_hold
  stage_time k_hold $t0
}
if {[lsearch $PH drv] >= 0} {
  optDesign -postRoute -drv -outDir $R/k_opt_drv
  drc_loop kd
  timeDesign -postRoute -outDir $R/k_drv_setup
  timeDesign -postRoute -hold -outDir $R/k_drv_hold
  view_slacks k_drv
  drv_counts k_drv
  verifyProcessAntenna -reportfile $R/k_drv_antenna.txt -error 100000
  foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/k_pdn_special_$n.txt }
  save_stage 05k_drv
  stage_time k_drv $t0
}
exit
