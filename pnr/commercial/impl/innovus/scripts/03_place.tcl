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
