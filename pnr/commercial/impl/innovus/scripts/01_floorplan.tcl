# 01_floorplan.tcl -- Step B5b stage 1: init_design (Genus netlist, original SDC, tt MMMC), floorplan identical to the OpenROAD/ICC2 arms:
#   die 0 0 3600 1800, core 20 20 3580 1780 on the OpenROAD row lattice (x0 20.24, y0 24.48, 7738 sites x 645 rows),
#   503 pins fixed from pin_template.def, 10 SRAMs fixed at macro_placement.cfg.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set init_lef_file [list $PDKREF/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef \
                        $PDKREF/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef \
                        $PDKREF/sky130_sram_macros/lef/${SRAM}.lef]
set init_verilog   $NETLIST
set init_top_cell  $TOP
set init_mmmc_file $SCRIPTDIR/mmmc_tt.tcl
set init_pwr_net   {VPWR}
set init_gnd_net   {VGND}
init_design
common_settings
puts "=== init_design done"
# ---- floorplan: core on the OpenROAD row lattice; die 3600x1800
floorPlan -site unithd -noSnapToGrid -b 0 0 3600 1800 20.24 24.48 3579.72 1778.88 20.24 24.48 3579.72 1778.88
puts "die  : [dbGet top.fPlan.box]"
puts "core : [dbGet top.fPlan.coreBox]"
puts "rows : [llength [dbGet top.fPlan.rows]]  orients: [dbGet top.fPlan.rows.orient -u]  first row: [lindex [dbGet top.fPlan.rows.box] 0]"
# ---- tracks: Innovus' automatic tracks deviate from the tech LEF; restore the LEF pitches (offsets stay Innovus-chosen, recorded)
source $PDKDIR/build/ndm/sky130_tracks_innovus.tcl
# align the preferred-direction start offsets with the tech LEF OFFSETs (met3 y .34, met4 x .46, met5 y 1.7): add_tracks -offsets is accepted but not
# honoured (part-2a finding, reproduced), so the three layers are re-created from a TRACKS-only DEF (offset = first track coordinate)
proc _trk_def {file} {
  set fh [open $file w]
  puts $fh "VERSION 5.8 ;\nDIVIDERCHAR \"/\" ;\nBUSBITCHARS \"\[\]\" ;\nDESIGN rv32i_cpu_top ;\nUNITS DISTANCE MICRONS 1000 ;"
  puts $fh "DIEAREA ( 0 0 ) ( 3600000 1800000 ) ;"
  # layer dir offset pitch.  dir X = vertical tracks (x coordinates).  Preferred direction = LEF OFFSET/PITCH; the other direction keeps
  # the Innovus-chosen start with the LEF pitch (as left by sky130_tracks_innovus.tcl).
  foreach {l d off p} {li1 X 0.23 0.46  li1 Y 0.17 0.34  met1 X 0.23 0.34  met1 Y 0.17 0.34  met2 X 0.23 0.46  met2 Y 0.63 0.46
                       met3 X 0.91 0.68  met3 Y 0.34 0.68  met4 X 0.46 0.92  met4 Y 0.85 0.92  met5 X 4.55 3.4  met5 Y 1.7 3.4} {
    set n [expr {int((($d eq "X" ? 3600.0 : 1800.0) - $off) / $p) + 1}]
    puts $fh "TRACKS $d [expr {int(round($off*1000))}] DO $n STEP [expr {int(round($p*1000))}] LAYER $l ;"
  }
  puts $fh "END DESIGN"
  close $fh
}
_trk_def $RUN/out/tracks.def
defIn $RUN/out/tracks.def
foreach t [get_db track_patterns] { puts "trk [get_db $t .layers] [get_db $t .direction] start=[get_db $t .start] step=[get_db $t .step] num=[get_db $t .num_tracks]" }
# ---- pins from the template DEF (the same file the OpenROAD arm applies via FP_DEF_TEMPLATE), then fixed
defIn $REPO/pnr/sky130/cpu/pin_template.def
dbSet top.terms.pStatus fixed
puts "PINS: [llength [dbGet top.terms]] fixed: [llength [dbGet -p top.terms.pStatus fixed]] on [dbGet top.terms.pins.allShapes.layer.name -u]"
# ---- macros: map macro_placement.cfg yosys-style names onto the Genus-flattened instance names
set cfg [open $CFGDIR/macro_placement.cfg r]
set nplaced 0
set allsram [dbGet -p2 top.insts.cell.name $SRAM]
foreach i $allsram { puts "SRAMINST [dbGet $i.name]" }
while {[gets $cfg l] >= 0} {
  regsub {#.*} $l {} l; set l [string trim $l]
  if {$l eq ""} continue
  lassign $l nm x y o
  set cache [lindex [split $nm .] 1]      ;# u_icache / u_dcache
  if {[regexp {gen_data_sram\[(\d)\]} $nm -> idx]} { set key "${cache}_gen_data_sram\[$idx\].u_data_sram" } else { set key "${cache}_u_tag_sram" }
  set hit {}
  foreach i $allsram { set n [lindex [dbGet $i.name] 0]; if {$n eq "u_core/$key"} { lappend hit $i } }
  if {[llength $hit] != 1} { error "macro for $nm: key '$key' matched [llength $hit] instances" }
  set inst [lindex $hit 0]
  set iname [lindex [dbGet $inst.name] 0]
  set o [dict get {N R0 S R180 FN MY FS MX} $o]
  placeInstance $iname $x $y $o -fixed
  puts "MACRO $nm -> $iname at ($x,$y) $o"
  incr nplaced
}
close $cfg
puts "MACROS placed: $nplaced of [llength $allsram]"
foreach i [dbGet -p2 top.insts.cell.name $SRAM] { puts "  [lindex [dbGet $i.name] 0] box=[dbGet $i.box] orient=[dbGet $i.orient] status=[dbGet $i.pStatus]" }
# placement halo/blockage: none (OpenROAD: PL_MACRO_HALO unset; macro LEF OBS only)
checkDesign -all -noHtml -outfile $RUN/reports/checkDesign_floorplan.txt
save_stage 01_floorplan
stage_time floorplan $t0
exit
