# 03_place.tcl -- Step B5b stage 3: placement set-up (density 25 %, 4-site cell padding per side, timing + routability driven) and place_opt_design
#   (global place + pre-CTS optimisation + legalisation), input-port protection diodes (DIODE_ON_PORTS=in), pre-CTS timing.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 02_pdn
common_settings
# ---- parasitics for pre-route: LEF-based RC scaled by the capTable when the rc corner has one
setExtractRCMode -engine preRoute
# ---- constants and output-port aliases left by Genus (assign statements / 1'b1 ties)
catch { addTieHiLo -cell sky130_fd_sc_hd__conb_1 -prefix TIE } e ; puts "addTieHiLo: $e"
catch { setDoAssign on -buffer sky130_fd_sc_hd__buf_2 } e ; puts "setDoAssign: $e"
# ---- placement controls (OpenROAD: PL_TARGET_DENSITY_PCT 25, GPL/DPL_CELL_PADDING 4 sites, time- and routability-driven)
setPlaceMode -reset
setPlaceMode -place_global_max_density 0.25 -timingDriven true -place_global_cong_effort auto -place_global_place_io_pins false
# ---- B5c: left-edge placement screen (only when B5C_SCREEN=1; b5b ran without it).  Evidence (DEF census of the b5b result vs OpenROAD / ICC2): Innovus put 536 logic cells in the
#      100 um pocket x<100 beside the tag-SRAM column (OpenROAD 66, ICC2 24) and 370 above it (x<300, y 917-1050; 12 / 7), mostly FE_OFC/FE_PHC port buffers pulled to the left-edge pins;
#      that pocket is a through-route channel for the top/right/bottom-pin nets, and 91 % of the 1,579 b5b DRCs sit there.
if {[info exists ::env(B5C_SCREEN)] && $::env(B5C_SCREEN) == 1} {
  createPlaceBlockage -box {0 0 100 917.5} -type hard
  createPlaceBlockage -box {0 917.5 300 1100} -type partial -density 15
  puts "B5C_SCREEN: hard placement blockage {0 0 100 917.5}; partial (15 %) {0 917.5 300 1100}"
}
# ---- B5d (only when B5D=1): the 3 shorts left in b5c_innovus_s2 are all signal-vs-signal (no PG, no pin access) in the left pocket / its mouth:
#      met4 at (99.8,520) hugging the SW corner of the D-cache tag SRAM, met3 at (96.7,685.6) 3 um from the macro edge, met4 at (1.2,580) on the outermost track at the die edge.
if {[info exists ::env(B5D)] && $::env(B5D) == 1} {
  createPlaceBlockage -box {100 0 120 917.5} -type hard                 ;# hard screen widened from x<100 to x<120 (covers the 100-120 band of the channel/gaps next to the macro edges)
  createPlaceBlockage -box {0 417.5 300 520} -type partial -density 15  ;# thin the cells at the pocket mouth (short 1 sits at its top-right corner)
  createRouteBlk -name b5d_leftedge_met4 -layer met4 -box {0 520 3 700} ;# keep the router off the outermost met4 tracks at the die edge beside the pocket (short 3)
  puts "B5D: hard {100 0 120 917.5}; partial 15 % {0 417.5 300 520}; met4 route blockage {0 520 3 700}"
}
set npad 0
foreach c [dbGet head.allCells.name] {
  set c [lindex $c 0]
  if {[string match *tap* $c] || [string match *decap* $c] || [string match *fill* $c] || [string match *sram* $c] || [string match *diode* $c]} continue
  specifyCellPad $c -left 4 -right 4 ; incr npad
}
puts "PAD: 4 sites per side on $npad lib cells"
setOptMode -fixFanoutLoad true -fixDrc true
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5
set t1 [clock seconds]
place_opt_design -out_dir $RUN/reports/place_opt
stage_time place_opt $t1
# ---- protection diodes on every input port except the clock (DIODE_ON_PORTS=in), placed at the load
set nd 0
foreach t [dbGet top.terms] {
  if {[dbGet $t.isInput] != 1} continue
  set nm [lindex [dbGet $t.name] 0]
  if {$nm eq "clk_i"} continue
  set net [dbGet $t.net]
  if {$net eq "0x0"} continue
  set its [dbGet $net.instTerms]
  if {[llength $its] == 0} continue
  set it [lindex $its 0]
  set in [lindex [dbGet $it.inst.name] 0]; set tn [lindex [dbGet $it.name] 0]
  # instTerm .name is "inst/pin"; attachDiode wants the pin name
  set pin [lindex [split $tn /] end]
  if {[catch { attachDiode -diodeCell sky130_fd_sc_hd__diode_2 -pin [list $in $pin] -prefix PORTDIODE } e]} { puts "attachDiode failed $nm: $e"; continue }
  incr nd
}
puts "PORT DIODES: $nd"
refinePlace
checkPlace $RUN/reports/checkPlace_place.txt
timeDesign -preCTS -outDir $RUN/reports/timing_preCTS
report_area -out_file $RUN/reports/area_place.txt
catch { reportDensityMap }
save_stage 03_place
stage_time place $t0
exit
