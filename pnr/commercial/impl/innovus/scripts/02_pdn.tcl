# 02_pdn.tcl -- Step B5b stage 2: PG connections, endcaps + tapcells, PDN equivalent to the FP_PDN_* keys of pnr/sky130/cpu/config.json.
#   met1 followpin rails; met4 vertical + met5 horizontal straps width 3.1 spacing 1.7 pitch 100 offset 20 (same as the OpenROAD pdn_cfg and the ICC2 arm);
#   SRAM vccd1/vssd1 tied to VPWR/VGND; tapvpwrvgnd_1 every 26 um per row, checkerboard (FP_TAPCELL_DIST 13 x2); decap_3 endcaps.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 01_floorplan
common_settings
# ---- logical PG connections (two pin-name pairs, one pair of nets)
globalNetConnect VPWR -type pgpin -pin VPWR  -all -override
globalNetConnect VPWR -type pgpin -pin VPB   -all -override
globalNetConnect VPWR -type pgpin -pin vccd1 -all -override
globalNetConnect VGND -type pgpin -pin VGND  -all -override
globalNetConnect VGND -type pgpin -pin VNB   -all -override
globalNetConnect VGND -type pgpin -pin vssd1 -all -override
# ---- endcaps and taps
addEndCap -preCap sky130_fd_sc_hd__decap_3 -postCap sky130_fd_sc_hd__decap_3 -prefix ENDCAP
puts "ENDCAPS: [llength [dbGet -p2 top.insts.cell.name sky130_fd_sc_hd__decap_3]]"
addWellTap -cell sky130_fd_sc_hd__tapvpwrvgnd_1 -cellInterval 26 -checkerBoard -prefix TAP
puts "TAPS: [llength [dbGet -p2 top.insts.cell.name sky130_fd_sc_hd__tapvpwrvgnd_1]]"
globalNetConnect VPWR -type pgpin -pin VPWR -all -override
globalNetConnect VGND -type pgpin -pin VGND -all -override
globalNetConnect VPWR -type pgpin -pin VPB  -all -override
globalNetConnect VGND -type pgpin -pin VNB  -all -override
# ---- PDN: met1 followpins, met4/met5 mesh
setAddStripeMode -reset
setAddStripeMode -stacked_via_bottom_layer met1 -stacked_via_top_layer met5 -ignore_nondefault_domains true
sroute -connect corePin -nets {VPWR VGND} -allowJogging 0 -allowLayerChange 0 -corePinLayer met1 -corePinTarget {firstAfterRowEnd}
# B5c step 2 (B5C_STRAP=1): the 31 DRCs left after the placement screen are 22 met4 ParallelRunLength spacings between SIGNAL wires and the VPWR/VGND met4 straps (+ 9 shorts) all at y=519.6,
# i.e. at the D-cache SRAM bottom edge where the macro pins are; keep the met4 straps 25 um away from that edge (the ICC2 arm cut its met4 straps at the macros altogether).
set _blk {}
if {[info exists ::env(B5C_STRAP)] && $::env(B5C_STRAP) == 1} { set _blk [list {20 495 3580 520}]; puts "B5C_STRAP: met4 strap blockage $_blk" }
if {[llength $_blk]} {
  addStripe -layer met4 -direction vertical   -nets {VPWR VGND} -width 3.1 -spacing 1.7 -set_to_set_distance 100 -start_from left   -start_offset 20 -area_blockage $_blk
} else {
  addStripe -layer met4 -direction vertical   -nets {VPWR VGND} -width 3.1 -spacing 1.7 -set_to_set_distance 100 -start_from left   -start_offset 20
}
addStripe -layer met5 -direction horizontal -nets {VPWR VGND} -width 3.1 -spacing 1.7 -set_to_set_distance 100 -start_from bottom -start_offset 20
# SRAM power pins (vccd1/vssd1, met4 ring pins) -> straps
sroute -connect blockPin -nets {VPWR VGND} -blockPin useLef -blockPinTarget {nearestTarget} -allowJogging 0 -allowLayerChange 1 -blockPinLayerRange {met4 met4} -layerChangeRange {met4 met5}
foreach n {VPWR VGND} {
  set net [dbGet -p top.nets.name $n]
  array unset cnt
  foreach l [dbGet $net.sWires.layer.name] { if {![info exists cnt($l)]} {set cnt($l) 0}; incr cnt($l) }
  puts "SWIRES $n by layer: [array get cnt]   vias: [llength [dbGet $net.sVias]]"
}
verify_connectivity -type special -report $RUN/reports/pg_connectivity.txt -error 2000
verifyPowerVia -report $RUN/reports/pg_powervia.txt
catch {report_power_rail -help}
save_stage 02_pdn
stage_time pdn $t0
exit
