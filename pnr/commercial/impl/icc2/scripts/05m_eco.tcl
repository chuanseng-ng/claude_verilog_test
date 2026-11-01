# 05m_eco.tcl -- Step B5m: in-place ECO round 2 on b5i's pre-fill block (label 05i_eco), no re-place / re-CTS.  Sections, each saved as its own label and guarded:
#   P  PDN strap-end trim (user-approved): VGND met4 strap start x 1738.69-1741.79, y 942.93 -> 943.03 (m4.5ab 0.4 um to the via-stack pad edge at y 942.63)
#   A  antenna: eco_in/ant_pins.txt = "<net> <sink pin>" violators of the signoff OpenROAD check_antennas run on the b5i DEF; one sky130_fd_sc_hd__diode_2 per
#      violating sink pin (placed at the pin's cell row, legalised), route_eco for the new pins (met4 halo blockages as in 05i_eco)
#   B  max-transition / max-capacitance (native tt): upsize the driver of every violating net (get_alternative_lib_cells, largest drive), legalise, route_eco; 3 passes
#   C  tt hold (the -1.6 ps b5i path): delay buffer on the violating endpoints (only if tt setup stays >= 0)
#   E  netlist export hygiene: change_names -case_insensitive on nets (case-colliding names); write_verilog -exclude supply_statements is done in 07_write_verilog_m
# Every section is wrapped in catch; labels 05m_pdn 05m_ant 05m_drv 05m_hold 05m_exp are written as they complete.  Env: B5M_SECTIONS (default "P A B C E").
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 05i_eco 05m_eco
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
set SECT {P A B C E}
if {[info exists ::env(B5M_SECTIONS)]} { set SECT $::env(B5M_SECTIONS) }
set R $RUN/reports
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }; close $fh; return $n }
proc count_short {f} { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr n } }; close $fh; return $n }
proc count_open {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of open nets is (\d+)} $l -> n }; close $fh; return $n }
proc chk {tag} {
  global RUN
  redirect -file $RUN/reports/m_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/m_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/m_checks_$tag.txt]; set s [count_short $RUN/reports/m_lvs_$tag.txt]; set o [count_open $RUN/reports/m_lvs_$tag.txt]
  puts "M_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
proc halo_on {} {
  global RUN
  set fh [open $RUN/eco_in/m4_straps.txt r]; set blk {}
  while {[gets $fh l] >= 0} {
    if {[llength $l] != 4} continue
    lassign $l x1 y1 x2 y2
    set blk [add_to_collection $blk [create_routing_blockage -layers met4 -boundary [list [list [expr {$x1-0.1}] $y1] [list [expr {$x2+0.1}] $y2]]]]
  }
  close $fh
  return $blk
}
proc route_clean {tag} {
  # route_eco for the nets edited, then incremental route_detail passes until the net-net checks are clean
  set blk [halo_on]
  route_eco -max_detail_route_iterations 60
  set r [chk ${tag}0]
  for {set i 1} {$i <= 4} {incr i} {
    if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
    route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
    set r [chk ${tag}$i]
  }
  remove_routing_blockages $blk
  return $r
}
proc snapshot {label} {
  # label = copy of the current (saved) block, so the section result survives a later failure
  global TOP
  save_block; save_lib
  set rc [catch {copy_block -from_block ${TOP}/05m_eco -to_block ${TOP}/$label} e]
  puts "M_LABEL $label rc=$rc $e"
  catch {save_lib}
}
proc tim {tag} {
  global RUN
  foreach {dt nm} {max SETUP min HOLD} {
    catch {
      set p [get_timing_paths -delay_type $dt -max_paths 1]
      puts "M_TIMING $tag $nm worst_slack=[get_attribute $p slack]"
    }
  }
  redirect -file $RUN/reports/m_constraints_$tag.txt { report_constraints -all_violators -max_transition -max_capacitance }
  set fh [open $RUN/reports/m_constraints_$tag.txt r]; set mt -1; set mc -1
  while {[gets $fh l] >= 0} { regexp {Number of max_transition violation\(s\): (\d+)} $l -> mt; regexp {Number of max_capacitance violation\(s\): (\d+)} $l -> mc }
  close $fh
  puts "M_DRV $tag: max_transition=$mt max_capacitance=$mc"
  return [list $mt $mc]
}
puts "M_START sections=$SECT"
chk 0
tim 0

# ============================================================ P: PDN strap-end trim
if {"P" in $SECT} { if {[catch {
  redirect -file $R/m_pgdrc_before.txt { check_pg_drc }
  redirect -file $R/m_pgconn_before.txt { check_pg_connectivity -check_std_cell_pins none }
  set target {}
  foreach_in_collection s [get_shapes -quiet -intersect {{1739.0 942.8} {1741.5 943.2}}] {
    if {[get_attribute $s layer_name] eq "met4" && [get_attribute $s shape_use] eq "stripe"} { lappend target $s }
  }
  puts "P_FOUND: [llength $target] met4 stripe shape(s) at the strap start"
  foreach s $target { puts "P_SHAPE: net=[get_attribute [get_attribute $s owner] full_name] bbox=[get_attribute $s bbox]" }
  if {[llength $target] == 1} {
    set s [lindex $target 0]; set bb [get_attribute $s bbox]
    set x1 [lindex $bb 0 0]; set y1 [lindex $bb 0 1]; set x2 [lindex $bb 1 0]; set y2 [lindex $bb 1 1]
    set net [get_attribute [get_attribute $s owner] full_name]
    if {abs($y1 - 942.93) < 0.01 && abs($x1 - 1738.69) < 0.01} {
      remove_shapes $s
      set n [create_shape -shape_type rect -layer met4 -net [get_nets $net] -shape_use stripe -boundary [list [list $x1 943.03] [list $x2 $y2]]]
      puts "P_TRIMMED: $net met4 stripe {$x1 $y1 $x2 $y2} -> {$x1 943.03 $x2 $y2}, new shape [sizeof_collection $n]"
    } else { puts "P_SKIP: the matched stripe is not the expected one" }
  }
  redirect -file $R/m_pgdrc_after.txt { check_pg_drc }
  redirect -file $R/m_pgconn_after.txt { check_pg_connectivity -check_std_cell_pins none }
  chk P
  snapshot 05m_pdn
} e]} { puts "M_ERR section P: $e" } }

# ============================================================ A: antenna diodes
if {"A" in $SECT} { if {[catch {
  set fh [open $RUN/eco_in/ant_pins.txt r]; set pairs {}
  while {[gets $fh l] >= 0} { if {[llength $l] == 2} { lappend pairs [lindex $l 0] [lindex $l 1] } }
  close $fh
  set diode [get_lib_cells */sky130_fd_sc_hd__diode_2]
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
    set c [create_cell $name $diode]
    connect_net $nn [get_pins $name/DIODE]
    set_cell_location $name -coordinates [list [expr {$cx - 0.23}] $oy] -orientation $orient
    lappend made $name
    incr k
  }
  puts "A_DIODES: $k created, $nf pins not found"
  legalize_placement -cells [get_cells $made]
  redirect -file $R/m_legality_A.txt { check_legality -verbose }
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO_*/VPWR]
  connect_pg_net -net VPWR [get_pins -hierarchical ANTDIO_*/VPB]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO_*/VGND]
  connect_pg_net -net VGND [get_pins -hierarchical ANTDIO_*/VNB]
  set r [route_clean A]
  puts "A_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
  tim A
  snapshot 05m_ant
} e]} { puts "M_ERR section A: $e" } }

# ============================================================ B: max-transition / max-capacitance
if {"B" in $SECT} { if {[catch {
  proc viol_nets {f} {
    # report_constraints rows: "  <net>   <required> <actual> <slack> (VIOLATED)" for nets (followed by "PIN :" rows)
    set fh [open $f r]; set names {}
    while {[gets $fh l] >= 0} {
      if {[regexp {^\s+(\S+)\s+[-0-9.e+]+\s+[-0-9.e+]+\s+-[0-9.e+]+\s+\(VIOLATED\)} $l -> n] && ![string match "PIN*" $n]} { lappend names $n }
    }
    close $fh
    return [lsort -unique $names]
  }
  for {set pass 1} {$pass <= 3} {incr pass} {
    redirect -file $R/m_drv_in_$pass.txt { report_constraints -all_violators -max_transition -max_capacitance }
    set names [viol_nets $R/m_drv_in_$pass.txt]
    puts "B_PASS $pass: [llength $names] violating nets"
    if {[llength $names] == 0} break
    set nsz 0
    foreach n $names {
      set net [get_nets -quiet [list $n]]
      if {[sizeof_collection $net] == 0} continue
      set drv [get_pins -quiet -of_objects $net -filter "direction==out"]
      if {[sizeof_collection $drv] != 1} continue
      set cell [get_cells -of_objects $drv]
      if {[get_attribute $cell is_physical_only] eq "true"} continue
      set cur [get_attribute [get_attribute $cell lib_cell] name]
      regexp {^(.*)_(\d+)$} $cur -> base curd
      set best $cur; set bestd $curd
      foreach lc [get_attribute [get_alternative_lib_cells $cell -quiet] name] {
        set lcn [lindex [split $lc /] end]
        if {[regexp {^(.*)_(\d+)$} $lcn -> b d] && $b eq $base && $d > $bestd} { set best $lcn; set bestd $d }
      }
      if {$best ne $cur} { if {![catch {size_cell $cell [get_lib_cells */$best]} e]} { incr nsz } }
    }
    puts "B_SIZED $pass: $nsz drivers upsized"
    if {$nsz == 0} break
    legalize_placement
    route_clean B$pass
    tim B$pass
  }
  tim Bfinal
  snapshot 05m_drv
} e]} { puts "M_ERR section B: $e" } }

# ============================================================ C: tt hold
if {"C" in $SECT} { if {[catch {
  set ps [get_timing_paths -delay_type min -max_paths 50 -slack_lesser_than 0.0]
  set eps {}
  foreach_in_collection p $ps { lappend eps [get_attribute [get_attribute $p endpoint] full_name] }
  set eps [lsort -unique $eps]
  puts "C_HOLD: [llength $eps] violating hold endpoints: $eps"
  set nb 0
  foreach ep $eps {
    set pin [get_pins -quiet [list $ep]]
    if {[sizeof_collection $pin] == 0} continue
    if {![catch {add_buffer -new_cell_names HOLDBUF_$nb -new_net_names HOLDNET_$nb -lib_cell [get_lib_cells */sky130_fd_sc_hd__dlygate4sd1_1] $pin} e]} { incr nb } else { puts "C_WARN: $ep: $e" }
  }
  puts "C_BUFFERS: $nb"
  if {$nb > 0} {
    legalize_placement
    route_clean C
  }
  tim C
  snapshot 05m_hold
} e]} { puts "M_ERR section C: $e" } }

# ============================================================ E: net-name hygiene (case-insensitive collisions)
if {"E" in $SECT} { if {[catch {
  define_name_rules m5_net -type net -case_insensitive
  redirect -file $R/m_change_names.txt { change_names -rules m5_net -verbose }
  puts "E_NAMES: change_names done (see reports/m_change_names.txt)"
  snapshot 05m_exp
} e]} { puts "M_ERR section E: $e" } }

# ---- final state
set r [chk final]
puts "M_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
tim final
save_stage 05m_eco
stage_time m_eco $t0
exit
