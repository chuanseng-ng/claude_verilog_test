# b8_06_eco.tcl (b6_06_eco + b7 ECO set, flipped I-cache floorplan) -- original header: b6 stage 6: antenna diode ECO (violators taken from OpenROAD check_antennas on the b6_05 DEF: eco_in/ant_pins.txt, one sky130_fd_sc_hd__diode_2 per violating sink pin),
#   re-route with the met4 halos still active, then remove the halos, final checks, net-name hygiene (change_names -case_insensitive).  No tt-only hold/DRV ECO (b5m lesson): hold + DRV were fixed
#   by place_opt/clock_opt/route_opt over the ff/ss/tt scenarios.  Env: B6_BASE (default 05_route).
source [file join [file dirname [info script]] b8_common.tcl]
set t0 [clock seconds]
set BASE 05_route
if {[info exists ::env(B6_BASE)]} { set BASE $::env(B6_BASE) }
open_stage $BASE 06_eco
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
  redirect -file $RUN/reports/e_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/e_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/e_checks_$tag.txt]; set s [count_short $RUN/reports/e_lvs_$tag.txt]; set o [count_open $RUN/reports/e_lvs_$tag.txt]
  puts "E_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
proc tim {tag} {
  global RUN
  foreach s [get_object_name [all_scenarios]] {
    current_scenario $s
    foreach {dt nm} {max SETUP min HOLD} {
      catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "E_TIMING $tag $s $nm worst_slack=[get_attribute $p slack]" }
    }
  }
  current_scenario func_tt
  redirect -file $RUN/reports/e_constraints_$tag.txt { report_constraints -all_violators -max_transition -max_capacitance }
}
puts "B6_HALO_PRESENT: [sizeof_collection [get_routing_blockages -quiet]] routing blockages"
chk 0
tim 0

# ============================================================ S: residual net-net shorts of the b6_05 repair loop (b5: a macro-gap column at x 1900-1960 um needs a re-solve of the region)
proc short_info {f} {
  set nets {}; set boxes {}
  set fh [open $f r]
  while {[gets $fh l] >= 0} {
    if {![string match "*Detected short violation*" $l] || [string match "*Blockage*" $l]} continue
    if {[regexp {Net1: (\S+)\. Net2: (\S+)\. BBox: \(([-0-9.]+) ([-0-9.]+)\)\(([-0-9.]+) ([-0-9.]+)\)} $l -> n1 n2 x1 y1 x2 y2]} {
      lappend nets $n1 $n2; lappend boxes [list $x1 $y1 $x2 $y2]
    }
  }
  close $fh
  return [list [lsort -unique $nets] $boxes]
}
proc nets_of {names} {
  set c {}
  foreach n $names { set x [get_nets -quiet [list $n]]; if {[sizeof_collection $x]} { set c [add_to_collection $c $x] } else { puts "S_WARN: net $n not found" } }
  return $c
}
proc nets_near {boxes m} {
  set names {}
  foreach b $boxes {
    lassign $b x1 y1 x2 y2
    catch {
      foreach_in_collection sh [get_shapes -quiet -intersect [list [list [expr {$x1-$m}] [expr {$y1-$m}]] [list [expr {$x2+$m}] [expr {$y2+$m}]]]] {
        set o [get_attribute $sh owner]
        if {$o ne ""} { lappend names [get_attribute $o full_name] }
      }
    }
  }
  return [lsort -unique $names]
}
if {"S" in {S}} {
  lassign [short_info $R/e_lvs_0.txt] snets sboxes
  puts "S_START: [llength $snets] shorted nets $snets at [llength $sboxes] boxes"
  if {[llength $snets] > 0} {
    set rr [list 0 0 0]
    foreach {pass margin} {S2 4 S4 4} {
      set names $snets
      if {$margin > 0} { set names [lsort -unique [concat $snets [nets_near $sboxes $margin]]] }
      set names [lsearch -all -inline -not -glob $names {VPWR}]
      set names [lsearch -all -inline -not -glob $names {VGND}]
      set nn [nets_of $names]
      puts "S_$pass: rip up and reroute [sizeof_collection $nn] nets (margin $margin um)"
      if {$pass eq "S4"} {
        # the long (>100 um) shorted nets are forced off met1/met2 (min layer met3, pin access allowed): their long vertical runs go to met4 (halos keep it clear of the PG straps)
        foreach n $snets {
          set net [get_nets -quiet [list $n]]
          if {[sizeof_collection $net] == 0} continue
          set ys {}
          foreach_in_collection p [get_pins -quiet -of_objects $net] { lappend ys [lindex [get_attribute $p bbox] 0 1] }
          if {[llength $ys] > 1 && ([tcl::mathfunc::max {*}$ys] - [tcl::mathfunc::min {*}$ys]) > 100} {
            set rc [catch {set_routing_rule -min_routing_layer met3 -min_layer_mode allow_pin_connection $net} e]
            puts "S_S4_RULE $n rc=$rc $e"
          }
        }
      }
      remove_routes -nets $nn -detail_route -global_route
      route_eco -max_detail_route_iterations 60
      set rr [chk ${pass}_0]
      for {set i 1} {$i <= 2} {incr i} {
        if {[lindex $rr 0] == 0 && [lindex $rr 1] == 0 && [lindex $rr 2] == 0} break
        route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
        set rr [chk ${pass}_$i]
      }
      puts "S_$pass RESULT: DRCs=[lindex $rr 0] shorts=[lindex $rr 1] opens=[lindex $rr 2]"
      if {[lindex $rr 0] == 0 && [lindex $rr 1] == 0 && [lindex $rr 2] == 0} break
    }
    tim S
  }
}
# ============================================================ H/D/B: b7 ECO set (hold buffers, dout0 buffers on EVERY max-cap pin, antenna-sink buffers)
proc read_list {f} { set fh [open $f r]; set L {}; while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne ""} { lappend L $l } }; close $fh; return $L }
# place cell $nm at pin bbox centre + (dx dy)
proc near_pin {nm pin dx dy} {
  set pb [get_attribute $pin bbox]
  set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0 + $dx}]; set cy [expr {([lindex $pb 0 1] + [lindex $pb 1 1]) / 2.0 + $dy}]
  set_cell_location [get_cells $nm] -coordinates [list $cx $cy]
  return [list $cx $cy]
}
set newcells {}; set dloc {}
set SRAMCELLS [get_cells -hierarchical -filter "ref_name==$SRAM"]
if {[file exists $RUN/eco_in/hold_endpoints.txt]} {
  set i 0
  foreach e [read_list $RUN/eco_in/hold_endpoints.txt] {
    set p [get_pins -quiet [list $e]]
    if {[sizeof_collection $p] == 0} { puts "H_WARN: no pin $e"; continue }
    if {[catch { insert_buffer -new_cell_names HB8_$i -new_net_names HB8N_$i $p sky130_hd_mcmm/sky130_fd_sc_hd__buf_1 } msg]} { puts "H_FAIL $e: $msg"; continue }
    set c [get_cells -quiet *HB8_$i]; near_pin [get_object_name $c] $p -1.0 0; lappend newcells [get_object_name $c]; incr i
  }
  puts "E8_HOLD_BUFFERS: $i inserted"
}
if {[file exists $RUN/eco_in/dout0_all.txt]} {
  set i 0
  foreach l [read_list $RUN/eco_in/dout0_all.txt] {
    lassign $l pn cap
    set p [get_pins -quiet [list $pn]]
    if {[sizeof_collection $p] == 0} { puts "D_WARN: no pin $pn"; continue }
    set lc [expr {$cap >= 0.05 ? "sky130_hd_mcmm/sky130_fd_sc_hd__buf_4" : "sky130_hd_mcmm/sky130_fd_sc_hd__buf_2"}]
    if {[catch { insert_buffer -new_cell_names DB8_$i -new_net_names DB8N_$i $p $lc } msg]} { puts "D_FAIL $pn: $msg"; continue }
    set c [get_cells -quiet *DB8_$i]
    # channel side: pin on the macro's top half => buffer above, else below
    set mc [get_cells -of_objects $p]; set mb [get_attribute $mc bbox]; set pb [get_attribute $p bbox]
    set pyc [expr {([lindex $pb 0 1] + [lindex $pb 1 1]) / 2.0}]; set myc [expr {([lindex $mb 0 1] + [lindex $mb 1 1]) / 2.0}]
    set dy [expr {$pyc > $myc ? 4.0 : -4.0}]
    set xy [near_pin [get_object_name $c] $p -1.0 $dy]
    lappend newcells [get_object_name $c]; dict set dloc [get_object_name $c] [list $pn $xy]; incr i
  }
  puts "E8_DOUT_BUFFERS: $i inserted"
}
set na 0
if {[file exists $RUN/eco_in/ant_buf_pins.txt]} {
  foreach pn [read_list $RUN/eco_in/ant_buf_pins.txt] {
    set p [get_pins -quiet [list $pn]]
    if {[sizeof_collection $p] == 0} { puts "B_WARN: no pin $pn"; continue }
    if {[catch { insert_buffer -new_cell_names AB8_$na -new_net_names AB8N_$na $p sky130_hd_mcmm/sky130_fd_sc_hd__buf_6 } msg]} { puts "B_FAIL $pn: $msg"; continue }
    set c [get_cells -quiet *AB8_$na]; near_pin [get_object_name $c] $p -1.0 0; lappend newcells [get_object_name $c]; incr na
  }
  puts "E8_ANT_BUFFERS: $na inserted"
}
puts "E8_NEWCELLS: [llength $newcells]"
if {[llength $newcells] > 0} {
  legalize_placement -cells [get_cells $newcells]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical -quiet */VPB]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VGND]
  connect_pg_net -net VGND [get_pins -hierarchical -quiet */VNB]
  set fh [open $R/e8_dout_buf_displacement.txt w]
  dict for {c v} $dloc {
    lassign $v pn xy
    set bb [get_attribute [get_cells $c] bbox]; set bx [lindex $bb 0 0]; set by [lindex $bb 0 1]
    set pp [get_attribute [get_pins $pn] bbox]; set px [lindex $pp 0 0]; set py [lindex $pp 0 1]
    puts $fh "$c $pn pin=($px,$py) buf=($bx,$by) manhattan=[expr {abs($bx-$px)+abs($by-$py)}] ref=[get_attribute [get_cells $c] ref_name]"
  }
  close $fh
  route_eco -max_detail_route_iterations 60
  set r [chk B0]
  for {set i 1} {$i <= 6} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk B$i]
  }
  puts "B_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
  tim B
}
# ============================================================ A: antenna diodes
if {[file exists $RUN/eco_in/ant_pins.txt]} {
  set fh [open $RUN/eco_in/ant_pins.txt r]; set pairs {}
  while {[gets $fh l] >= 0} { if {[llength $l] == 2} { lappend pairs [lindex $l 0] [lindex $l 1] } }
  close $fh
  set diode [get_lib_cells sky130_hd_mcmm/sky130_fd_sc_hd__diode_2]
  set k 0; set nf 0; set made {}
  foreach {net pn} $pairs {
    set p [get_pins -quiet [list $pn]]
    if {[sizeof_collection $p] == 0} { incr nf; puts "A_WARN: no pin $pn"; continue }
    set cell [get_cells -of_objects $p]
    set cb [get_attribute $cell bbox]; set pb [get_attribute $p bbox]
    set cx [expr {([lindex $pb 0 0] + [lindex $pb 1 0]) / 2.0}]
    set oy [lindex $cb 0 1]
    set orient [get_attribute $cell orientation]
    set nn [get_nets -of_objects $p]
    set name ANTDIO_$k
    create_cell $name $diode
    connect_net $nn [get_pins $name/DIODE]
    set_cell_location $name -coordinates [list [expr {$cx - 0.23}] $oy] -orientation $orient
    lappend made $name
    incr k
  }
  puts "A_DIODES: $k created, $nf pins not found"
  legalize_placement -cells [get_cells $made]
  redirect -file $R/e_legality_A.txt { check_legality -verbose }
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO_*/VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO_*/VPB]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO_*/VGND]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO_*/VNB]
  route_eco -max_detail_route_iterations 60
  set r [chk A0]
  for {set i 1} {$i <= 6} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk A$i]
  }
  puts "A_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
  tim A
} else { puts "A_SKIP: no eco_in/ant_pins.txt" }
# ============================================================ halos off, final checks
remove_routing_blockages [get_routing_blockages -quiet]
puts "B6_HALO_REMOVED: [sizeof_collection [get_routing_blockages -quiet]] routing blockages left"
# ============================================================ E: net-name hygiene (case-insensitive collisions)
define_name_rules b6_net -type net -case_insensitive
redirect -file $R/e_change_names.txt { change_names -rules b6_net -verbose }
puts "E_NAMES: change_names done (reports/e_change_names.txt)"
set r [chk final]
puts "E_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
tim final
redirect -file $R/e_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/e_pg_drc.txt { check_pg_drc }
catch { write_def $RUN/out/pre_ant.def }
save_stage 06_eco
stage_time eco $t0
exit
