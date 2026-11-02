# 05k_defdump.tcl -- write the routed DEF of a saved db (pre-fill) for the signoff antenna check.  env FROM_LABEL (05k_pin), OUTDIR (runs/<tag>/out_pre)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05k_pin"}]
restore_stage $FL
common_settings
set O $RUN/[expr {[info exists ::env(OUTDIR)] ? $::env(OUTDIR) : "out_pre"}]
file mkdir $O
defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def
puts "DEFDUMP done $O"
exit
