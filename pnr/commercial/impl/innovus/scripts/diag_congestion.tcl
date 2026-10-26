# diag_congestion.tcl -- B5c diagnosis (read only): global-route congestion of the 04_cts (pre-route) and 05a_routed databases in the left-edge window.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set RUNB $::env(RUN_B5B)
restoreDesign $RUNB/dbs/04_cts.enc.dat $TOP
setDesignMode -process 130 -bottomRoutingLayer met1 -topRoutingLayer met4
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5
earlyGlobalRoute
report_congestion -grc_report $RUN/reports/grc_cts.txt -hotspot
exit
