# 05_route.tcl -- Step B5b stage 5 (post-route part): post-route RC, timing and setup/hold optimisation on the routed (and DRC-repaired) database.
#   The routing itself ran in the first version of this script and is now saved as 05a_routed (see 05b_repair.tcl for the DRC repair).
#   The capTable from generateCapTbl was REJECTED by Innovus (IMPEXT-3548: layer M6 missing = li1 is a LEF routing layer, the table has M1..M5; IMPEXT-2715
#   syntax error line 96), so post-route RC is the tech-LEF RC, like stages 01-04.  Post-route stages need OCV analysis mode (IMPOPT-7027).
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
if {![info exists ::env(FROM_LABEL)]} { set ::env(FROM_LABEL) 05b_repair }
restore_stage $::env(FROM_LABEL)
common_settings
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true
setAnalysisMode -analysisType onChipVariation -cppr both
# ---- post-route RC (capTable-based when the rc corner has one) + optimisation
setExtractRCMode -engine postRoute -effortLevel low
set t2 [clock seconds]
timeDesign -postRoute -outDir $RUN/reports/timing_postRoute_pre_opt
timeDesign -postRoute -hold -outDir $RUN/reports/timing_postRoute_pre_opt_hold
optDesign -postRoute -outDir $RUN/reports/opt_postRoute
optDesign -postRoute -hold -outDir $RUN/reports/opt_postRoute_hold
stage_time postRoute_opt $t2
timeDesign -postRoute -outDir $RUN/reports/timing_postRoute
timeDesign -postRoute -hold -outDir $RUN/reports/timing_postRoute_hold
verify_drc -limit 100000 -report $RUN/reports/drc_post_opt.txt
verifyProcessAntenna -reportfile $RUN/reports/antenna_post_opt.txt -error 100000
save_stage 05_route
stage_time route $t0
exit
