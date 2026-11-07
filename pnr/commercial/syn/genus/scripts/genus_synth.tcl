# genus_synth.tcl -- Step B3b: Cadence Genus 23.14 synthesis of the Sky130 CPU macro rv32i_cpu_top (75 MHz).
#   COMPARISON RUN, NO PPA TARGET: constraints are exactly pnr/sky130/cpu/constraints/sky130_cpu.sdc (via mmmc.tcl); nothing tuned to close.
#   genus -no_gui -files genus_synth.tcl     env: REPO PDKDIR RUN RTL_LIST SCRIPTDIR  [STOP=elab|fp|generic|map|all]  [PHYS=1|0]
# Mirrors scripts of the DC arm (../dc/scripts/dc_synth.tcl): same 28 RTL files + 5 defines, native SV, SRAM stub never read.
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set STOP   [expr {[info exists ::env(STOP)] ? $::env(STOP) : "all"}]
set PHYS   [expr {[info exists ::env(PHYS)] ? $::env(PHYS) : 1}]
set TOP    rv32i_cpu_top
set SRAMC  sky130_sram_1kbyte_1rw1r_32x256_8
set PDKR   $::env(PDK_ROOT)/sky130A/libs.ref
set SDC    $REPO/pnr/sky130/cpu/constraints/sky130_cpu.sdc
file mkdir $RUN/reports $RUN/out
set t_start [clock seconds]

set_db max_cpus_per_server 2
set_db information_level 6
set_db hdl_error_on_blackbox true
set_db hdl_track_filename_row_col true
set_db init_hdl_search_path {}
if {[file exists $PDKDIR/build/qrc/nom/qrcTechFile]} { puts "QRC: qrcTechFile present" } else { puts "QRC: no qrcTechFile -> tech-LEF RC (recorded)" }

# ---- libraries / MMMC (tt view only for synthesis) ----
set ::env(HERE) $PDKDIR
set ::env(SDC) $SDC
read_mmmc $PDKDIR/scripts/mmmc.tcl
# synthesis uses the tt view only (mmmc.tcl defaults to setup {ss tt} / hold {ff tt})
set_analysis_view -setup {av_tt} -hold {av_tt}
read_physical -lef [list $PDKR/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef \
                         $PDKR/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef \
                         $PDKR/sky130_sram_macros/lef/$SRAMC.lef]

# ---- RTL (native SystemVerilog, same list + defines as DC) ----
set defines {PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130}
set files {}
set fh [open $::env(RTL_LIST) r]
while {[gets $fh l] >= 0} { if {[string trim $l] ne ""} { lappend files [string trim $l] } }
close $fh
puts "RTL files: [llength $files]"
foreach f $files { if {![file exists $f]} { error "missing RTL file $f" }; if {[string match *stub* $f]} { error "SRAM stub must not be read: $f" } }
read_hdl -sv -define $defines $files
elaborate $TOP
puts "ELABORATE_DONE"
check_design -unresolved
redirect $RUN/reports/check_design_elab.rpt { check_design -all }
puts "ELAB insts: [llength [get_db insts]]  hinsts: [llength [get_db hinsts]]"
foreach i [get_db insts -if {.base_cell.name==$SRAMC}] { puts "  sram: [get_db $i .name] [get_db $i .base_cell.name]" }
if {$STOP eq "elab"} { puts "STOP=elab"; if {![info exists ::env(NOEXIT)]} {exit} }

# ---- constraints (SDC via mmmc.tcl constraint mode, unchanged) + dont_use + SRAM protection ----
init_design
puts "ANALYSIS VIEWS: setup [get_db analysis_views -if {.is_setup==true} .name] hold [get_db analysis_views -if {.is_hold==true} .name]"
source $PDKDIR/scripts/dont_use.tcl
puts "dont_use cells: [llength [get_db base_cells -if {.dont_use==true}]]"
set srams [get_db insts -if {.base_cell.name==$SRAMC}]
foreach i $srams { set_db $i .preserve true }
puts "SRAM preserve: [llength [get_db insts -if {.base_cell.name==$SRAMC && .preserve==true}]] of [llength $srams], is_dont_touch [llength [get_db insts -if {.base_cell.name==$SRAMC && .is_dont_touch==true}]]"
# routing layers met1..met4 (RT_MAX_LAYER met4 in the OpenROAD arm)
catch {set_db design_bottom_routing_layer met1}
catch {set_db design_top_routing_layer met4}
puts "routing layers: [get_db design_bottom_routing_layer] .. [get_db design_top_routing_layer]"

# ---- floorplan (physical mode): rows + 503 fixed pins from the DC arm's DEF generator, macros from macro_placement.cfg ----
if {$PHYS} {
  exec python3 -I $::env(SCRIPTDIR)/../../dc/scripts/mk_fp_def.py $REPO $RUN/out/fp.def
  read_def $RUN/out/fp.def
  array set mloc {}
  set cfg [open $REPO/pnr/sky130/cpu/macro_placement.cfg r]
  while {[gets $cfg l] >= 0} {
    regsub {#.*} $l {} l; set l [string trim $l]; if {$l eq ""} continue
    lassign $l nm x y o
    # yosys-style "u_core.u_icache.gen_data_sram[0].u_data_sram" -> Genus "u_core/u_icache/gen_data_sram[0].u_data_sram"
    set parts [split $nm .]; set out {}; set k 0
    while {$k < [llength $parts]} {
      set q [lindex $parts $k]
      if {[string match {gen_data_sram\[*\]} $q]} { set q "$q.[lindex $parts [expr {$k+1}]]"; incr k }
      lappend out $q; incr k
    }
    set mloc([join $out /]) [list $x $y $o]
  }
  close $cfg
  # inst .location is read-only in Genus: place the macros through an incremental DEF COMPONENTS section
  set nplaced 0
  set dfh [open $RUN/out/macros.def w]
  puts $dfh "VERSION 5.8 ;\nDIVIDERCHAR \"/\" ;\nBUSBITCHARS \"\[\]\" ;\nDESIGN $TOP ;\nUNITS DISTANCE MICRONS 1000 ;"
  puts $dfh "COMPONENTS [llength $srams] ;"
  foreach i $srams {
    set n [get_db $i .name]
    if {![info exists mloc($n)] && ![info exists mloc(rv32i_cpu_top/$n)]} { error "no placement for macro $n" }
    set v [expr {[info exists mloc($n)] ? $mloc($n) : $mloc(rv32i_cpu_top/$n)}]
    lassign $v x y o
    regsub -all {\[} $n {\\[} en; regsub -all {\]} $en {\\]} en
    puts $dfh "- $en $SRAMC + FIXED ( [expr {int(round($x*1000))}] [expr {int(round($y*1000))}] ) $o ;"
    incr nplaced
  }
  puts $dfh "END COMPONENTS\nEND DESIGN"
  close $dfh
  read_def -incremental $RUN/out/macros.def
  puts "FLOORPLAN: placed $nplaced macros"
  redirect $RUN/reports/floorplan.rpt {
    puts "die/core: [get_db designs .bbox] ; rows [llength [get_db rows]]"
    foreach i $srams { puts "[get_db $i .name] bbox=[get_db $i .bbox] orient=[get_db $i .orient] status=[get_db $i .place_status]" }
    puts "ports placed: [llength [get_db ports -if {.place_status==fixed}]] of [llength [get_db ports]]"
  }
  puts [exec cat $RUN/reports/floorplan.rpt]
}
if {$STOP eq "fp"} { puts "STOP=fp"; if {![info exists ::env(NOEXIT)]} {exit} }

# ---- synthesis ----
# Genus defaults for effort and auto-ungroup (DC arm also used defaults).  No timing/area target tuning.
puts "AUTO_UNGROUP default: [get_db auto_ungroup]"
set t0 [clock seconds]
if {$PHYS} { syn_generic -physical } else { syn_generic }
puts "SYN_GENERIC_DONE [expr {[clock seconds]-$t0}] s"
redirect $RUN/reports/qor_generic.rpt { report_qor }
if {$STOP eq "generic"} { puts "STOP=generic"; if {![info exists ::env(NOEXIT)]} {exit} }
set t1 [clock seconds]
if {$PHYS} { syn_map -physical } else { syn_map }
puts "SYN_MAP_DONE [expr {[clock seconds]-$t1}] s"
redirect $RUN/reports/qor_map.rpt { report_qor }
if {$STOP eq "map"} { puts "STOP=map"; if {![info exists ::env(NOEXIT)]} {exit} }
set t2 [clock seconds]
# iSpatial (syn_opt -spatial) needs probabilistic_extraction + a QRC tech file (PHYS-1015); none exists yet (Techgen still running) -> plain physical-aware syn_opt
syn_opt
puts "SYN_OPT_DONE [expr {[clock seconds]-$t2}] s"
puts "SYN_TOTAL [expr {[clock seconds]-$t0}] s (generic+map+opt)"

# every output / report step is isolated: a failing report must not lose the 12-minute synthesis session
proc try {name script} {
  if {[catch {uplevel 1 $script} err]} { puts "STEP_FAILED $name: $err" } else { puts "STEP_OK $name" }
}
# ---- outputs ----
set O $RUN/out
try db        { write_db -to_file $O/post_opt.db }
try db2       { write_db $O/post_opt_db_dir }
try netlist   { write_hdl > $O/${TOP}.nl.v }
try netlist_lec { write_hdl -lec > $O/${TOP}.lec.nl.v }
try sdc       { write_sdc -view av_tt > $O/${TOP}.sdc }
try def       { write_def -routing -no_std_cells $O/${TOP}.def }
try def2      { write_def -no_special_net $O/${TOP}_all.def }
try do_lec    { write_do_lec -golden_design rtl -revised_design $O/${TOP}.nl.v -top $TOP -log_file $O/lec_${TOP}.log $O/lec_${TOP}.do }

# ---- reports ----
set R $RUN/reports
try qor          { redirect $R/qor.rpt { report_qor } }
try report_summary { report_summary > $R/summary.rpt }
try area         { redirect $R/area.rpt { report_area } }
try timing10     { redirect $R/timing_max10.rpt { report_timing -max_paths 10 -nworst 1 } }
try timing1      { redirect $R/timing_summary.rpt { report_timing -max_paths 1 } }
try timing_hold  { report_timing -early -max_paths 5 > $R/timing_min.rpt }
try timing_hold2 { report_timing -hold -max_paths 5 > $R/timing_min2.rpt }
try timing_hold3 { report_timing -delay_type min -max_paths 5 > $R/timing_min3.rpt }
try help_rt      { help report_timing > $R/help_report_timing.txt }
try help_rp      { help report_power > $R/help_report_power.txt }
try power        { report_power > $R/power.rpt }
try gates        { redirect $R/gates.rpt { report_gates } }
try clock_gating { redirect $R/clock_gating.rpt { report_clock_gating } }
try drv          { redirect $R/design_rules.rpt { report_design_rules } }
try check_design { redirect $R/check_design.rpt { check_design -all } }
try check_timing { redirect $R/check_timing.rpt { check_timing_intent } }
try constraints  { redirect $R/constraints.rpt { report_constraint -all_violators } }
try messages     { redirect $R/messages.rpt { report_messages } }
try hier         { redirect $R/hier.rpt { report_area -depth 3 } }
# census: flops / latches by base cell, negedge + async flops, fwd_b_* flops
set seq [get_db insts -if {.is_sequential==true && .base_cell.is_macro==false && .base_cell.is_memory==false && .base_cell.name!=$SRAMC}]
array set cnt {}
foreach i $seq { set b [get_db $i .base_cell.name]; if {![info exists cnt($b)]} {set cnt($b) 0}; incr cnt($b) }
set fh [open $R/flop_census.txt w]
foreach b [lsort [array names cnt]] { puts $fh "$b $cnt($b)" }
close $fh
set fh [open $R/flops.txt w]
foreach i $seq { puts $fh "[get_db $i .name] [get_db $i .base_cell.name]" }
close $fh
set fb [get_db insts -if {.is_sequential==true && .name==*fwd_b*}]
puts "FWD_B flops: [llength $fb]"; foreach i $fb { puts "  [get_db $i .name] [get_db $i .base_cell.name]" }
set all [get_db insts -if {.is_physical==false}]
puts "CELLCOUNT: leaf=[llength [get_db insts -if {.base_cell.is_physical==false}]] sequential=[llength $seq]"
array unset cc
foreach i [get_db insts] { set b [get_db $i .base_cell.name]; if {![info exists cc($b)]} {set cc($b) 0}; incr cc($b) }
set fh [open $R/cellcount.txt w]
foreach b [lsort [array names cc]] { puts $fh "$b $cc($b)" }
close $fh
puts "SRAM preserved at end: [llength [get_db insts -if {.base_cell.name==$SRAMC && .preserve==true}]]"
puts "HIERARCHY modules at end: [llength [get_db hinsts]] hinsts, designs: [get_db designs .name]"
puts "GENUS_WALL_TOTAL [expr {[clock seconds]-$t_start}] s"
puts "GENUS_DONE"
exit
