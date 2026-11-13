# 11m_eco.tcl -- Innovus b11 ECO round on the b10 final pre-fill db (10_eco): slew fix on the SAME three nets only (user decision 2026-11-13).  b10 judged (PrimeTime, shared SDC) max-transition 28/16/30 pins at nom_ss/min_ss/max_ss vs b6 14/11/29:
#   the three b10 repeaters (buf_6: B10N1 on FE_OFN19232_n, u_core/B10N2 on n_12617, u_core/B10N3 on n_12583) drive 0.5..1.0 mm of wire and are the weak link at ss (B10N1/X 0.529, a22o A2 0.534, u_core/B10N2/X 0.650 ns nom_ss vs 0.5 limit).
#   Fix: resize the three repeaters IN PLACE to sky130_fd_sc_hd__buf_12 (ecoChangeCell, same pins/nets/location), refinePlace, ecoRoute.  Nothing else is touched (the apb_prdata_o port nets, clk_i, CTS and all earlier ECO cells stay as in b10).
#   Pre-flight estimate (PrimeTime what-if on the b10 netlist + b10 StarRC SPEF, size_cell on the same wires; scripts/b11est.tcl): buf_12 -> B10N1/X 0.312, a22o A2 0.318, u_core/B10N2/X 0.388 ns nom_ss; max over the 3 nets 0.394 / 0.357 / 0.435 at nom_ss / min_ss / max_ss;
#   max-tran violator pins 28/16/30 -> 13/11/15 at nom_ss/min_ss/max_ss (b6 14/11/29), tt/ff unchanged.
#   env: FROM_LABEL (10_eco), OUT_LABEL (11_eco), B11CELL (sky130_fd_sc_hd__buf_12)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "10_eco"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "11_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setNanoRouteMode -drouteEndIteration 30
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp {Total Violations\s*:\s*(\d+)} $l -> v]} { set n $v } }; close $fh; if {$n < 0} { set n 0 }; return $n }
verify_drc -limit 100000 -report $R/e11_drc_0.txt; puts "E11_DRC_0: [count_drc $R/e11_drc_0.txt]"
timeDesign -postRoute -outDir $R/e11_setup0
timeDesign -postRoute -hold -outDir $R/e11_hold0
set ncell0 [llength [dbGet top.insts]]
puts "E11_INSTS_BEFORE: $ncell0"
set CELL [expr {[info exists ::env(B11CELL)] ? $::env(B11CELL) : "sky130_fd_sc_hd__buf_12"}]
foreach pat {CTS_* ZCTSBUF_* *clk_gate* } { catch { set_db [get_db insts $pat] .dont_touch true } }
setEcoMode -reset
catch { setEcoMode -refinePlace true -updateTiming false -honorDontTouch false }
# the three b10 repeaters: report before / change / report after (instance box, cell)
foreach inst {B10N1 u_core/B10N2 u_core/B10N3} {
  set p [dbGet -p top.insts.name $inst]
  if {$p eq "0x0" || $p eq ""} { puts "E11_NOINST $inst"; continue }
  puts "E11_BEFORE $inst cell=[dbGet $p.cell.name] box=[dbGet $p.box]"
  set rc [catch { ecoChangeCell -inst $inst -cell $CELL } e]
  puts "E11_CHG $inst rc=$rc $e"
}
foreach inst {B10N1 u_core/B10N2 u_core/B10N3} { set p [dbGet -p top.insts.name $inst]; puts "E11_AFTER $inst cell=[dbGet $p.cell.name] box=[dbGet $p.box] status=[dbGet $p.pStatus]" }
setEcoMode -reset
refinePlace
checkPlace $R/e11_checkPlace.txt
save_stage ${OL}_pre
set rc [catch { ecoRoute } e]; puts "ecoRoute rc=$rc $e"
verify_drc -limit 100000 -report $R/e11_drc_1.txt
set d [count_drc $R/e11_drc_1.txt]; puts "E11_DRC_1: $d"
set kk 1
while {$d > 0 && $kk < 6} { ecoRoute -fix_drc; incr kk; verify_drc -limit 100000 -report $R/e11_drc_$kk.txt; set d [count_drc $R/e11_drc_$kk.txt]; puts "E11_DRC_$kk: $d" }
verifyProcessAntenna -reportfile $R/e11_antenna.txt -error 100000
extractRC
timeDesign -postRoute -outDir $R/e11_setup
timeDesign -postRoute -hold -outDir $R/e11_hold
foreach v [all_analysis_views] {
  catch { report_timing -view $v -max_paths 1 -path_type summary > $R/e11_view_${v}_setup.txt }
  catch { report_timing -view $v -early -max_paths 1 -path_type summary > $R/e11_view_${v}_hold.txt }
}
catch { report_timing -view av_ss -from [get_ports {apb_paddr_i[*]}] -to [get_pins {apb_prdata_o_reg*/D}] -max_paths 6 -path_type summary > $R/e11_apb_paths_ss.txt }
catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout} > $R/e11_violators.txt }
foreach n {{apb_prdata_o[7]} {apb_prdata_o[17]} {apb_prdata_o[21]} FE_OFN19232_n u_core/FE_OFN18305_n_12617 u_core/FE_OFN4695_n_12583} {
  set nn [string map {/ _ [ _ ] _} $n]; catch { report_net -net $n > $R/e11_net_$nn.txt }
}
foreach n {VPWR VGND} { verify_connectivity -type special -net $n -error 100000 -report $R/e11_pdn_special_$n.txt }
puts "E11_INSTS_AFTER: [llength [dbGet top.insts]] (before $ncell0)"
save_stage $OL
set O $RUN/out_pre; file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
stage_time eco11 $t0
exit
