# 09m_eco.tcl -- Innovus b9 ECO round on the b8 final pre-fill db (08b_eco): a post-route optDesign RE-TIME of the setup paths that PT own max_ss reports (apb_paddr_i[*] -> apb_prdata_o_reg[*], b8 -0.112 ns, b6 -0.050 ns)
#   plus the max-transition violators, WITHOUT touching the clock tree (useful skew off, no clock-cell resizing), then ecoRoute / DRC loop, re-time all views, antenna, PDN connectivity, save, dump the pre-fill DEF.
#   env: FROM_LABEL (08b_eco), OUT_LABEL (09_eco), SETUP_TS (setup target slack, ns; default 0.20), DRV (1 = also -drv, default 1), HOLD (1 = -hold afterwards, default 1), MODE (opt | none: none = only measure)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "08b_eco"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "09_eco"}]
set TS [expr {[info exists ::env(SETUP_TS)] ? $::env(SETUP_TS) : 0.20}]   ;# default 0.20; derived from the native apb slack below when SETUP_TS is not given
set DRV [expr {[info exists ::env(DRV)] ? $::env(DRV) : 1}]
set HOLD [expr {[info exists ::env(HOLD)] ? $::env(HOLD) : 1}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
verify_drc -limit 100000 -report $R/e9_drc_0.txt; puts "E9_DRC_0: [count_drc $R/e9_drc_0.txt]"
timeDesign -postRoute -outDir $R/e9_setup0
timeDesign -postRoute -hold -outDir $R/e9_hold0
# ---- derive the native target slack from the apb path (PT own max_ss -0.112 ns on b8): TS = native_slack + 0.112 + 0.05 margin, clamped to [0.05, 0.6]; SETUP_TS in the env overrides
catch { report_timing -view av_ss -from [get_ports {apb_paddr_i[*]}] -to [get_pins {apb_prdata_o_reg*/D}] -max_paths 1 > $R/e9_apb_native0.txt }
set sn ""
catch { set fh [open $R/e9_apb_native0.txt r]; set txt [read $fh]; close $fh; if {[regexp {Slack Time\s+(-?[0-9.]+)} $txt -> sn]} {} }
puts "E9_APB_NATIVE_SLACK_AV_SS: $sn"
if {![info exists ::env(SETUP_TS)] && $sn ne ""} {
  set TS [expr {$sn + 0.162}]
  if {$TS < 0.05} { set TS 0.05 }
  if {$TS > 0.6} { set TS 0.6 }
  puts "E9_TS_DERIVED: $TS"
}
set ncell0 [llength [dbGet top.insts]]
puts "E9_INSTS_BEFORE: $ncell0"
# ---- the clock tree and every ECO cell of b8 stay as they are
foreach pat {CTS_* ZCTSBUF_* *clk_gate* } { catch { set_db [get_db insts $pat] .dont_touch true } }
catch { setOptMode -reset }
setOptMode -addInstancePrefix B9OPT -usefulSkew false -fixFanoutLoad false -fixDrc true -holdTargetSlack 0.0 -setupTargetSlack $TS
catch { setOptMode -usefulSkewPostRoute false }
catch { setOptMode -usefulSkewCCOpt none }
set mode [expr {[info exists ::env(MODE)] ? $::env(MODE) : "opt"}]
if {$mode eq "opt"} {
  set flags "-postRoute -setup"
  if {$DRV} { append flags " -drv" }
  puts "E9_OPT: optDesign $flags (setupTargetSlack $TS)"
  set rc [catch { eval optDesign $flags -outDir $R/e9_opt_setup } e]; puts "E9_OPT_SETUP rc=$rc $e"
  if {$HOLD} { set rc [catch { optDesign -postRoute -hold -outDir $R/e9_opt_hold } e]; puts "E9_OPT_HOLD rc=$rc $e" }
}
set rc [catch { refinePlace } e]; puts "refinePlace rc=$rc"
checkPlace $R/e9_checkPlace.txt
save_stage ${OL}_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
verify_drc -limit 100000 -report $R/e9_drc_1.txt
set d [count_drc $R/e9_drc_1.txt]; puts "E9_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 6} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/e9_drc_$kk.txt; set d [count_drc $R/e9_drc_$kk.txt]; puts "E9_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/e9_antenna.txt -error 100000
timeDesign -postRoute -outDir $R/e9_setup
timeDesign -postRoute -hold -outDir $R/e9_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/e9_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/e9_view_${v}_hold.txt }
}
catch { report_timing -view av_ss -from [get_ports {apb_paddr_i[*]}] -to [get_pins {apb_prdata_o_reg*/D}] -max_paths 6 -path_type summary > $R/e9_apb_paths_ss.txt }
catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout} > $R/e9_violators.txt }
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/e9_pdn_special_$n.txt }
puts "E9_INSTS_AFTER: [llength [dbGet top.insts]] (before $ncell0)"
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time eco9 $t0
exit
