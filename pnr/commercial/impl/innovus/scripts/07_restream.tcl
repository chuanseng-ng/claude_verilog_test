# 07_restream.tcl -- B5d-gds: restore the final database (06_finish), re-stream the GDS with the corrected map, then PG connectivity checks per net.  No routing.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 06_finish
common_settings
set O $RUN/out
set R $RUN/reports/gdsfix
file mkdir $R
set rc [catch { streamOut $O/rv32i_cpu_top.gds -mapFile $SCRIPTDIR/gds_layer_map.innovus -libName DesignLib -structureName rv32i_cpu_top -units 1000 -mode ALL \
   -merge [list $PDKREF/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds $PDKREF/sky130_sram_macros/gds/${SRAM}.gds] -reportFile $R/streamOut.rpt } e]
puts "streamOut rc=$rc $e"
stage_time streamOut $t0
if {![info exists ::env(SKIP_CONN)]} {
  foreach n {VPWR VGND} {
    verify_connectivity -type special -net $n -error 1000000 -report $R/special_$n.txt
    puts "special $n done"
  }
  foreach n {VPWR VGND} {
    verifyConnectivity -type regular -net $n -error 1000000 -noAntenna -report $R/regular_$n.txt
    puts "regular $n done"
  }
}
stage_time all $t0
exit
