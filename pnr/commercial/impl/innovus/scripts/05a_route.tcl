# 05a_route.tcl -- Step B5b stage 5a: NanoRoute (met1..met4 only, timing driven), antenna diode insertion with sky130_fd_sc_hd__diode_2.  Saves label 05a_routed.
#   (This is the routing half of the first-draft 05_route.tcl, split out after the post-route half failed on the capTable/OCV issues; it produced the run's 05a_routed database.)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 04_cts
common_settings
setNanoRouteMode -reset
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5 \
  -routeWithTimingDriven true -routeWithSiDriven false \
  -routeInsertAntennaDiode true -routeAntennaCellName sky130_fd_sc_hd__diode_2 -drouteFixAntenna true \
  -drouteUseMultiCutViaEffort low
routeDesign -globalDetail
stage_time routeDesign $t0
save_stage 05a_routed
verify_drc -limit 100000 -report $RUN/reports/drc_after_route.txt
verifyProcessAntenna -reportfile $RUN/reports/antenna_after_route.txt -error 100000
exit
