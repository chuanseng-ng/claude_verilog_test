# b9_06c_eco.tcl -- ICC2 b9 (= b8 ECO round 3) on label 06b_eco of the b8 database copy (runs/b9_icc2).  Root-cause fix for the two b8 input-port max-cap nets plus the max-fanout violators.
#   P  axi_rdata_i[15]/[16]: the port diodes PORTDIODE__29711 / __29710 sit EAST of the I-cache SRAM 2 (x 2528, the only legal sites near the port, which lies under the macro: macro x 2039..2519, y 20..417),
#      while the loads are WEST of it (x ~2000).  The router reaches the diode through a 2-3 mm detour (met4 up to y 412 / 1070): 571 / 368 fF against a 561 fF (nom_tt) / 353 fF (max_ss) limit.  Fix = move each diode
#      next to the load pins (the port wire already runs along the bottom strip, met1 y 11, to the west side) and re-route.  (A buffer cannot help: the nearest legal site to the port is the same far-away spot.)
#   F  max-fanout: clock-tree leaf buffers (176 ZCTSBUF + 1 ZBUF) driving 17..25 sinks against set_max_fanout 16.  Each gets one parallel clone of the same lib cell (same input net) that takes the excess sinks
#      (the farthest from the driver, n-16 of them), placed at the centroid of the moved sinks.  Env B9_NO_FANOUT=1 skips this part, B9_NO_PORT=1 skips the diode move.
#   Then the same halo / route_eco / check loop as b8_06b_eco, halos off, checks, soft-DRC location, save as 06c_eco, dump pre-fill DEF.
source [file join [file dirname [info script]] b8_common.tcl]
set t0 [clock seconds]
open_stage 06b_eco 06c_eco
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
proc near_pin {nm pin dx dy} {
  set pb [get_attribute $pin bbox]
  set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0 + $dx}]; set cy [expr {([lindex $pb 0 1] + [lindex $pb 1 1]) / 2.0 + $dy}]
  set_cell_location [get_cells $nm] -coordinates [list $cx $cy]
  return [list $cx $cy]
}
proc ctr {pins} { set sx 0.0; set sy 0.0; set n 0; foreach p $pins { set bb [get_attribute $p bbox]; set sx [expr {$sx+([lindex $bb 0 0]+[lindex $bb 1 0])/2.0}]; set sy [expr {$sy+([lindex $bb 0 1]+[lindex $bb 1 1])/2.0}]; incr n }; return [list [expr {$sx/$n}] [expr {$sy/$n}]] }
# ---- P: port diodes next to the west loads
if {![info exists ::env(B9_NO_PORT)]} {
  foreach {dn ld} {PORTDIODE__29711 HFSBUF_903_3753/A PORTDIODE__29710 ZBUF_476_inst_13525/A} {
    set c [get_cells $dn]; set p [get_pins $ld]
    set pb [get_attribute $p bbox]; set cx [expr {([lindex $pb 0 0]+[lindex $pb 1 0])/2.0 - 3.0}]; set cy [expr {([lindex $pb 0 1]+[lindex $pb 1 1])/2.0 + 3.0}]
    puts "P_MOVE $dn from [get_attribute $c bbox] to ($cx,$cy)"
    catch { set_placement_status placed $c }
    set_cell_location $c -coordinates [list $cx $cy]
    lappend newcells $dn
  }
}
# ---- F: fanout clones
set nclone 0; set fanfail 0
if {![info exists ::env(B9_NO_FANOUT)]} {
  foreach l [read_list $RUN/eco_in/fanout_viol.txt] {
    lassign $l pn fo
    set dp [get_pins -quiet [list $pn]]
    if {[sizeof_collection $dp] == 0} { puts "F_WARN no pin $pn"; incr fanfail; continue }
    set dc [get_cells -of_objects $dp]; set dname [get_object_name $dc]; set ref [get_attribute $dc ref_name]
    set net [get_nets -of_objects $dp]
    set inp [get_pins -quiet "$dname/A"]
    if {[sizeof_collection $inp] != 1} { puts "F_SKIP $pn: no single A pin ($ref)"; incr fanfail; continue }
    set innet [get_nets -of_objects $inp]
    set sinks [get_pins -quiet -of_objects $net -filter "direction==in"]
    set n [sizeof_collection $sinks]
    if {$n <= 16} { puts "F_SKIP $pn: only $n sinks"; continue }
    set db [get_attribute $dc bbox]; set dx [expr {([lindex $db 0 0]+[lindex $db 1 0])/2.0}]; set dy [expr {([lindex $db 0 1]+[lindex $db 1 1])/2.0}]
    set lst {}
    foreach_in_collection s $sinks { set sb [get_attribute $s bbox]; set sx [expr {([lindex $sb 0 0]+[lindex $sb 1 0])/2.0}]; set sy [expr {([lindex $sb 0 1]+[lindex $sb 1 1])/2.0}]; lappend lst [list [expr {abs($sx-$dx)+abs($sy-$dy)}] [get_object_name $s]] }
    set lst [lsort -real -decreasing -index 0 $lst]
    set mv [lrange $lst 0 [expr {$n-16-1}]]
    set mvp {}; foreach e $mv { lappend mvp [get_pins [lindex $e 1]] }
    set cn B9FAN_$nclone; set nn B9FANN_$nclone
    set rc [catch {
      create_cell $cn sky130_hd_mcmm/$ref
      create_net $nn
      foreach p $mvp { disconnect_net -net $net $p; connect_net -net $nn $p }
      connect_net -net $innet [get_pins $cn/A]
      connect_net -net $nn [get_pins $cn/X]
    } msg]
    if {$rc} { puts "F_FAIL $pn: $msg"; incr fanfail; continue }
    set ct [ctr $mvp]
    set_cell_location [get_cells $cn] -coordinates [list [expr {([lindex $ct 0]+$dx)/2.0}] [expr {([lindex $ct 1]+$dy)/2.0}]]
    lappend newcells $cn
    incr nclone
  }
  puts "E9_FANOUT_CLONES: $nclone made, $fanfail failed/skipped"
}
puts "E7_NEWCELLS: [llength $newcells]"
if {[llength $newcells] > 0} {
  legalize_placement -cells [get_cells $newcells]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
  foreach dn {PORTDIODE__29711 PORTDIODE__29710} { catch { puts "P_AFTER $dn [get_attribute [get_cells $dn] bbox]" } }
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
# ---- A: residual deck-antenna sinks: one buf_6 (gate area 0.495 um2) in front of each listed sink pin
set na 0
if {[file exists $RUN/eco_in/ant_buf_pins_r3.txt]} {
  foreach pn [read_list $RUN/eco_in/ant_buf_pins_r3.txt] {
    set p [get_pins -quiet [list $pn]]
    if {[sizeof_collection $p] == 0} { puts "B_WARN: no pin $pn"; continue }
    if {[catch { insert_buffer -new_cell_names AB8R_$na -new_net_names AB8RN_$na $p sky130_hd_mcmm/sky130_fd_sc_hd__buf_6 } msg]} { puts "B_FAIL $pn: $msg"; continue }
    set c [get_cells -quiet *AB8R_$na]; near_pin [get_object_name $c] $p -1.0 0; lappend newcells [get_object_name $c]; incr na
  }
  puts "E7_ANT_BUFFERS: $na inserted"
  if {[llength $newcells] > 0} {
    legalize_placement -cells [get_cells $newcells]
    connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
    connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
    connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
    connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
  }
}
route_eco -max_detail_route_iterations 60
set r [chk A0]
for {set i 1} {$i <= 6} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chk A$i]
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
# native DRC detail (b8 round 1 left 1 DRC on met3/met4 that KLayout does not flag)
catch { foreach_in_collection e [get_drc_errors -error_data zroute.err] { puts "DRC_DETAIL [get_attribute $e type_name] [get_attribute $e bbox]" } } dmsg
puts "DRC_DETAIL_MSG: $dmsg"

# ---- locate the soft DRC (Min-max layer): report_soft_drc_separately on, error data opened
catch { set_app_options -name route.detail.report_soft_drc_separately -value true }
redirect -file $R/e9_soft_drc_check.txt { check_routes -drc true -antenna false -open_net false -report_all_open_nets false }
catch { foreach ed [get_object_name [get_drc_error_data -all]] { puts "E9_EDATA $ed" } } m
catch { open_drc_error_data -name zroute.err } m; puts "E9_OPEN: $m"
catch { foreach_in_collection e [get_drc_errors -error_data zroute.err] { puts "E9_DRC [get_attribute $e type_name] [get_attribute $e bbox] [get_attribute $e layer_name]" } } m; puts "E9_DRC_MSG: $m"
save_stage 06c_eco
stage_time eco7 $t0
exit
