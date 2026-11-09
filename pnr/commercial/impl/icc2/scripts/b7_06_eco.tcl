# b7_06_eco.tcl -- ICC2 b7 ECO round on the b6 final pre-finish label (06c_eco3): ONE combined pass, three fixes (the b6 arm itself stays untouched).
#   H  #4  ff reg->reg hold: one sky130_fd_sc_hd__buf_1 in front of every capture D pin in eco_in/hold_endpoints.txt (endpoints with PrimeTime hold slack < +12 ps at nom/min/max ff, judge b6)
#   D  #6  SRAM dout0 max-cap: one buffer (buf_4 when the b6 judge load >= 0.05 pF, else buf_2) on every dout0 pin of eco_in/dout0_violators_b6.txt (union of the 9 judge corners),
#          placed next to the SRAM pin so the macro sees only the short stub + one buffer input (Liberty max_capacitance 0.02756 pF = top of the characterised load table)
#   A  #5  deck antenna: u_core_u_dcache/n3594 (met1 side area 592 vs 400 on the gate-attached met1 island).  The 4 diodes of rounds 1-3 are connected on upper layers, so the deck
#          (OpenROAD check_antennas) does not credit them on that met1 island.  Fix = one buf_6 (gate area 0.495 vs 0.126 um2) at the sink pin, so the long wire ends on a 3.9x larger gate.
# then the same met4 halo / route_eco / check loop as b6_06c_eco3, halos off, checks, save as 07_eco.  Env: B7_NO_HOLD, B7_NO_DOUT, B7_NO_ANT (set to skip a part).
source [file join [file dirname [info script]] b6_common.tcl]
set t0 [clock seconds]
open_stage 06c_eco3 07_eco
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
set R $RUN/reports
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }; close $fh; return $n }
proc count_short {f} { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr n } }; close $fh; return $n }
proc count_open {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of open nets is (\d+)} $l -> n }; close $fh; return $n }
proc chk {tag} {
  global RUN
  redirect -file $RUN/reports/e7_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/e7_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/e7_checks_$tag.txt]; set s [count_short $RUN/reports/e7_lvs_$tag.txt]; set o [count_open $RUN/reports/e7_lvs_$tag.txt]
  puts "E7_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
proc tim {tag} {
  global RUN SRAMPINS
  foreach s [get_object_name [all_scenarios]] {
    foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "E7_TIMING $tag $s $nm worst_slack=[get_attribute $p slack]" } }
    catch { set p [get_timing_paths -scenarios $s -delay_type max -through $SRAMPINS -max_paths 1]; puts "E7_SRAMPATH $tag $s SETUP worst_slack=[get_attribute $p slack] start=[get_object_name [get_attribute $p startpoint]] end=[get_object_name [get_attribute $p endpoint]]" }
  }
  current_scenario func_tt
  redirect -file $RUN/reports/e7_constraints_$tag.txt { report_constraints -all_violators -max_capacitance }
}
set srams [get_cells -hierarchical -filter "ref_name==$SRAM"]
set SRAMPINS [get_pins -of_objects $srams -filter "name=~dout0*"]
puts "E7_SRAM dout0 pins: [sizeof_collection $SRAMPINS]"
# ---- halos on (as b6_06c): all met4 PG straps wider than 3 um
set blk {}
foreach_in_collection s [get_shapes -quiet -filter "layer_name==met4 && shape_use==stripe"] {
  set bb [get_attribute $s bbox]
  set x1 [lindex $bb 0 0]; set y1 [lindex $bb 0 1]; set x2 [lindex $bb 1 0]; set y2 [lindex $bb 1 1]
  if {($x2 - $x1) < 3.0} continue
  set blk [add_to_collection $blk [create_routing_blockage -layers met4 -boundary [list [list [expr {$x1-0.1}] [expr {$y1-0.1}]] [list [expr {$x2+0.1}] [expr {$y2+0.1}]]]]]
}
puts "E7_HALO: [sizeof_collection $blk] halos"
chk 0
tim 0
set newcells {}
proc read_list {f} { set fh [open $f r]; set L {}; while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne ""} { lappend L $l } }; close $fh; return $L }
# place cell $nm centre-left at pin bbox centre + (dx dy) (um)
proc near_pin {nm pin dx dy} {
  set pb [get_attribute $pin bbox]
  set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0 + $dx}]; set cy [expr {([lindex $pb 0 1] + [lindex $pb 1 1]) / 2.0 + $dy}]
  set_cell_location [get_cells $nm] -coordinates [list $cx $cy]
  return [list $cx $cy]
}
# ---- H: hold buffers
if {![info exists ::env(B7_NO_HOLD)]} {
  set i 0
  foreach e [read_list $RUN/eco_in/hold_endpoints.txt] {
    set p [get_pins -quiet [list $e]]
    if {[sizeof_collection $p] == 0} { puts "H_WARN: no pin $e"; continue }
    set rc [catch { insert_buffer -new_cell_names HB7_$i -new_net_names HB7N_$i $p sky130_hd_mcmm/sky130_fd_sc_hd__buf_1 } msg]
    if {$rc} { puts "H_FAIL $e: $msg"; continue }
    set c [get_cells -quiet *HB7_$i]
    near_pin [get_object_name $c] $p -1.0 0
    lappend newcells [get_object_name $c]
    incr i
  }
  puts "E7_HOLD_BUFFERS: $i inserted"
}
# ---- D: dout0 buffers
set dloc {}
if {![info exists ::env(B7_NO_DOUT)]} {
  set i 0
  # FINDING (b7 run 1): the 5 icache SRAMs have their dout0 pins on the bottom edge (y=20 um), outside the row lattice (rows start at y=24.48 and are covered by the macro there):
  # the nearest legal site is 139-340 um away (159 of 159 icache buffers were displaced 100-283 um, median 226 um; ICC2 ss setup went -0.022 -> -0.97 ns).  Only the dcache pins
  # face the 100 um channel (buffers land 4-9 um from the pin).  Default = dcache pins only; B7_DOUT_FILTER=all reproduces the icache experiment.
  set filt dcache; if {[info exists ::env(B7_DOUT_FILTER)]} { set filt $::env(B7_DOUT_FILTER) }
  foreach l [read_list $RUN/eco_in/dout0_violators_b6.txt] {
    lassign $l pn cap
    if {$filt ne "all" && ![string match *$filt* $pn]} { puts "D_SKIP (no legal site near the pin) $pn"; continue }
    set p [get_pins -quiet [list $pn]]
    if {[sizeof_collection $p] == 0} { puts "D_WARN: no pin $pn"; continue }
    set lc [expr {$cap >= 0.05 ? "sky130_hd_mcmm/sky130_fd_sc_hd__buf_4" : "sky130_hd_mcmm/sky130_fd_sc_hd__buf_2"}]
    set rc [catch { insert_buffer -new_cell_names DB7_$i -new_net_names DB7N_$i $p $lc } msg]
    if {$rc} { puts "D_FAIL $pn: $msg"; continue }
    set c [get_cells -quiet *DB7_$i]
    set xy [near_pin [get_object_name $c] $p -1.0 -4.0]
    lappend newcells [get_object_name $c]
    dict set dloc [get_object_name $c] [list $pn $xy]
    incr i
  }
  puts "E7_DOUT_BUFFERS: $i inserted"
}
puts "E7_NEWCELLS: [llength $newcells]"
if {[llength $newcells] > 0} {
  legalize_placement -cells [get_cells $newcells]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
  # displacement of the dout0 buffers from their SRAM pin
  set fh [open $R/e7_dout_buf_displacement.txt w]
  dict for {c v} $dloc {
    lassign $v pn xy
    set bb [get_attribute [get_cells $c] bbox]
    set bx [lindex $bb 0 0]; set by [lindex $bb 0 1]
    set pp [get_attribute [get_pins $pn] bbox]; set px [lindex $pp 0 0]; set py [lindex $pp 0 1]
    puts $fh "$c $pn pin=($px,$py) buf=($bx,$by) manhattan=[expr {abs($bx-$px)+abs($by-$py)}] ref=[get_attribute [get_cells $c] ref_name]"
  }
  close $fh
}
# ---- route the new nets / rerouted nets
route_eco -max_detail_route_iterations 60
set r [chk E0]
for {set i 1} {$i <= 6} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chk E$i]
}
tim afterbuf
# ---- A: n3594 antenna.  MEASURED (b7 run 2): rerouting with hop_layers reproduces the same met1 run (the diode-credit model of the router and the deck differ), so the fix is a larger gate on the long wire:
#      one buf_6 (ANTENNAGATEAREA 0.495 um2 vs the sink flop D 0.126) in front of the violating sink pin, placed next to it; the long met1 island then ends on the buffer input, ratio 592 x 0.126/0.495 = 151 < 400.
if {![info exists ::env(B7_NO_ANT)]} {
  set p [get_pins u_core_u_dcache/data_dout_r_reg_2__26_/D]
  set rc [catch { insert_buffer -new_cell_names AB7_0 -new_net_names AB7N_0 $p sky130_hd_mcmm/sky130_fd_sc_hd__buf_6 } msg]
  puts "A_INSERT rc=$rc $msg"
  set c [get_cells -quiet *AB7_0]
  near_pin [get_object_name $c] $p -1.0 0
  legalize_placement -cells $c
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
  puts "A_BUF [get_object_name $c] bbox=[get_attribute $c bbox] sink=[get_attribute $p bbox]"
  route_eco -max_detail_route_iterations 60
  set r [chk A0]
  for {set i 1} {$i <= 6} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk A$i]
  }
  set n [get_nets -of_objects [get_pins $c/A]]
  foreach_in_collection s [get_shapes -of_objects $n -quiet] { puts "A_SHAPE [get_attribute $s layer_name] [get_attribute $s bbox]" }
}
remove_routing_blockages [get_routing_blockages -quiet]
puts "E7_HALO_REMOVED: [sizeof_collection [get_routing_blockages -quiet]] left"
set r [chk final]
puts "E7_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
tim final
redirect -file $R/e7_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/e7_pg_drc.txt { check_pg_drc }
# net-name hygiene is done by the finish stage; dump the pre-fill DEF for the deck antenna check
catch { write_def $RUN/out/pre_ant.def }
save_stage 07_eco
stage_time eco7 $t0
exit
