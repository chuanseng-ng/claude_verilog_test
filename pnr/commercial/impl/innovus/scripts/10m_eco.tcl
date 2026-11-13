# 10m_eco.tcl -- Innovus b10 ECO round on the b9 final pre-fill db (09_eco): root-cause fix of the max-transition regression that the b8 I-cache flip brought in (b9 data, PrimeTime judge, shared SDC):
#   (a) apb_prdata_o[7/17/21]: the last driver (clkbuf_16, x = 550..770 um) is 3.2..3.6 mm from the output port on the right die edge (x = 3598 um)  -> RC-dominated slew 0.87 ns (nom_ss); NOT fixable by repeaters (see below)
#   (b) three nets whose loads are spread over 0.6..1.4 mm around a driver that sits 0.5 mm off the load cluster: FE_OFN19232_n (9 of 10 a22o A2 loads at x=650..770,y=920..970, driver at 1058,450),
#       u_core/FE_OFN18305_n_12617 (4 far loads at x>=1916), u_core/FE_OFN4695_n_12583 (2 loads at y=300 plus the cluster at y=855..940): one repeater takes the far loads off the driver.  Geometry (DEF): the D-cache SRAMs (y 520..917) and I-cache SRAMs (y 20..417) are 480 um wide with ~200 um gaps (x 1160..1360, 1840..2039, ...), so every net runs through a gap column: the repeater is put in the gap near the middle of the ROUTED path (attempt B at the load centroid, inside/over the macro, left the first segment as long as before: native sink slew at the repeater input 0.35 ns, unchanged: reports/attemptB_centroid).
#   Nothing else is touched (no optDesign, CTS and all earlier ECO cells dont_touch).  Then ecoRoute / DRC loop, re-time all views, antenna, PDN connectivity, save, dump the pre-fill DEF.
#   env: FROM_LABEL (09_eco), OUT_LABEL (10_eco)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "09_eco"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "10_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
verify_drc -limit 100000 -report $R/e10_drc_0.txt; puts "E10_DRC_0: [count_drc $R/e10_drc_0.txt]"
timeDesign -postRoute -outDir $R/e10_setup0
timeDesign -postRoute -hold -outDir $R/e10_hold0
set ncell0 [llength [dbGet top.insts]]
puts "E10_INSTS_BEFORE: $ncell0"
foreach pat {CTS_* ZCTSBUF_* *clk_gate* } { catch { set_db [get_db insts $pat] .dont_touch true } }
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
set cell sky130_fd_sc_hd__buf_8
proc rep_net {n cell tag} {
  set rc [catch { ecoAddRepeater -net $n -cell $cell -firstSpreadDist 1100 -spreadDist 1100 -spreadPrefix ${tag}_ } e]
  if {$rc} { set rc [catch { ecoAddRepeater -net [string map {[ {\[} ] {\]}} $n] -cell $cell -firstSpreadDist 1100 -spreadDist 1100 -spreadPrefix ${tag}_ } e] }
  puts "E10_REP_NET $n rc=$rc $e"
}
proc rep_terms {n terms loc cell name} {
  set rc [catch { ecoAddRepeater -term $terms -cell $cell -loc $loc -name $name } e]
  puts "E10_REP_TERMS $n ($name) rc=$rc $e"
}
# (a) long output-port nets: NOT repeated.  Attempt A (spread buf_8 every 1.1 mm on apb_prdata_o[7/17/21]) took the native av_ss setup WNS from +0.071 to -0.966 ns (those paths close to +0.07 ns in b9, the three repeater
#     chains cost +1.0 ns each): reports/attemptA_port_repeaters.  The three port nets stay as in b9 (they violate in b6 too).
# (b) scattered-load nets
rep_terms FE_OFN19232_n {g46310/A2 g46301/A2 g46268/A2 g46251/A2 g46203/A2 g46169/A2 g46161/A2 g46154/A2 g46138/A2} {1260 900} sky130_fd_sc_hd__buf_6 B10N1
rep_terms u_core/FE_OFN18305_n_12617 {u_core/g372543/B u_core/g372541/B u_core/FE_OFC8791_n_12617/A u_core/FE_OFC8792_n_12617/A} {1900 850} sky130_fd_sc_hd__buf_6 B10N2
rep_terms u_core/FE_OFN4695_n_12583 {u_core/g372600/B u_core/g372593/B} {1950 620} sky130_fd_sc_hd__buf_6 B10N3
set nrep 0; foreach i [dbGet top.insts.name B10*] { incr nrep }
puts "E10_REPEATERS_IN_DB: $nrep"
setEcoMode -reset
refinePlace
checkPlace $R/e10_checkPlace.txt
save_stage ${OL}_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
verify_drc -limit 100000 -report $R/e10_drc_1.txt
set d [count_drc $R/e10_drc_1.txt]; puts "E10_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 6} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/e10_drc_$kk.txt; set d [count_drc $R/e10_drc_$kk.txt]; puts "E10_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/e10_antenna.txt -error 100000
extractRC
timeDesign -postRoute -outDir $R/e10_setup
timeDesign -postRoute -hold -outDir $R/e10_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/e10_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/e10_view_${v}_hold.txt }
}
catch { report_timing -view av_ss -from [get_ports {apb_paddr_i[*]}] -to [get_pins {apb_prdata_o_reg*/D}] -max_paths 6 -path_type summary > $R/e10_apb_paths_ss.txt }
catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout} > $R/e10_violators.txt }
foreach n {{apb_prdata_o[7]} {apb_prdata_o[17]} {apb_prdata_o[21]} FE_OFN19232_n u_core/FE_OFN18305_n_12617 u_core/FE_OFN4695_n_12583} {
  set nn [string map {/ _ [ _ ] _} $n]; catch { report_net -net $n > $R/e10_net_$nn.txt }
}
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/e10_pdn_special_$n.txt }
puts "E10_INSTS_AFTER: [llength [dbGet top.insts]] (before $ncell0)"
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time eco10 $t0
exit
