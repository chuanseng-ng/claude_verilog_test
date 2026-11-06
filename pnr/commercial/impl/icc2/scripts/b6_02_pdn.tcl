# b6_02_pdn.tcl -- (b5 02_pdn + b6 up-front fixes: VPWR/VGND met4 strap-end trim of b5m section P, and 0.1 um met4 halo routing blockages on every PG strap, removed in b6_06_eco) Step B5a stage 2: PG nets, endcaps + tapcells, PDN equivalent to the FP_PDN_* keys of pnr/sky130/cpu/config.json.
#   met1 followpin rails 0.48; met4 vertical + met5 horizontal straps: width 3.1, spacing 1.7, pitch 100, offset 20 (OpenROAD pdn_cfg.tcl);
#   SRAM vccd1/vssd1 -> VPWR/VGND (PDN_MACRO_CONNECTIONS); tap tapvpwrvgnd_1 distance 13 (OR checkerboard => 26 um per row, staggered); endcap decap_3.
source [file join [file dirname [info script]] b6_common.tcl]
set t0 [clock seconds]
open_stage 01_floorplan 02_pdn

# ---- PG nets and logical PG connections
create_net -power  VPWR
create_net -ground VGND
connect_pg_net -net VPWR [get_pins -hierarchical */VPWR]
connect_pg_net -net VPWR [get_pins -hierarchical */VPB]
connect_pg_net -net VGND [get_pins -hierarchical */VGND]
connect_pg_net -net VGND [get_pins -hierarchical */VNB]
set srams [get_cells -hierarchical -filter "ref_name==$SRAM"]
connect_pg_net -net VPWR [get_pins -of_objects $srams -filter "name==vccd1"]
connect_pg_net -net VGND [get_pins -of_objects $srams -filter "name==vssd1"]
puts "PG pins on VPWR: [sizeof_collection [get_pins -quiet -physical_context -of_objects [get_nets VPWR]]]"

# ---- endcaps (decap_3 on both row ends) and tapcells
set endcap [get_lib_cells sky130_hd_mcmm/sky130_fd_sc_hd__decap_3]
set tap    [get_lib_cells */sky130_fd_sc_hd__tapvpwrvgnd_1]
puts "endcap lib cell: [get_object_name $endcap]  tap lib cell: [get_object_name $tap]"
create_boundary_cells -left_boundary_cell $endcap -right_boundary_cell $endcap -prefix ENDCAP_
puts "ENDCAPS: [sizeof_collection [get_cells -quiet ENDCAP_*]]"
create_tap_cells -lib_cell $tap -distance 26 -pattern stagger -skip_fixed_cells -prefix TAP_
puts "TAPS: [sizeof_collection [get_cells -quiet TAP_*]]"
# B5e: every row segment (between boundary cells, i.e. also the short ones next to / between macros) must carry a tap, with no tap-free stretch above 26 um.
file mkdir $RUN/probe
write_def $RUN/probe/tap.def
set _o [exec python3 -I $SCRIPTDIR/tap_segments.py $RUN/probe/tap.def 26]
puts "TAP_SEGMENTS:\n$_o"
set fh [open $RUN/reports/tap_segments.txt w]; puts $fh $_o; close $fh
if {![regexp {segments with NO tap: (\d+)} $_o -> _nt] || $_nt != 0} { error "B5e: row segments without a tap: $_nt" }
connect_pg_net -net VPWR [get_pins -hierarchical */VPWR]
connect_pg_net -net VPWR [get_pins -hierarchical */VPB]
connect_pg_net -net VGND [get_pins -hierarchical */VGND]
connect_pg_net -net VGND [get_pins -hierarchical */VNB]

# ---- PDN
remove_pg_strategies -all
remove_pg_patterns -all
# Via masters with explicit cut spacing: the generated .tf carries no cut-to-cut spacing in its ContactCodes, so the default PG via arrays
# overlapped their own cuts (check_pg_drc "Overlap of Via-Cuts").  Spacings are the tech-LEF cut SPACINGs (via 0.17, via2/via3 0.2, via4 0.8).
set_pg_via_master_rule V12 -contact_code via_cc  -cut_spacing {0.17 0.17}
set_pg_via_master_rule V23 -contact_code via2_cc -cut_spacing {0.2 0.2}
set_pg_via_master_rule V34 -contact_code via3_cc -cut_spacing {0.2 0.2}
set_pg_via_master_rule V45 -contact_code via4_cc -cut_spacing {0.8 0.8}
create_pg_mesh_pattern P_mesh -layers {
  {{vertical_layer: met4}   {width: 3.1} {spacing: 1.7} {pitch: 100} {offset: 20}}
  {{horizontal_layer: met5} {width: 3.1} {spacing: 1.7} {pitch: 100} {offset: 20}}
} -via_rule {{intersection: adjacent} {via_master: V45}}
# met4 straps are cut at the SRAM footprints (SRAM LEF obstructs met1/met2 fully, met3/met4 partly); met5 straps run over the macros and
# drop vias onto the SRAM vccd1/vssd1 met4 ring pins, as the OpenROAD macro grid (met4-met5 connect) does.
set_pg_strategy S_mesh -core -pattern {{name: P_mesh} {nets: {VPWR VGND}}} -blockage [list [list "macros: $srams" "layers: {met4}"]]
create_pg_std_cell_conn_pattern P_rail -layers met1 -rail_width 0.48
set_pg_strategy S_rail -core -pattern {{pattern: P_rail} {nets: {VPWR VGND}}}
# one stacked via per crossing: met1 rail x met4 strap (via..via3), met4 x met5 strap (via4), met5 strap x SRAM met4 ring pins; nothing else
set_pg_strategy_via_rule R_all -via_rule {
  {{{strategies: S_rail} {layers: met1}} {{strategies: S_mesh} {layers: met4}} {via_master: {V12 V23 V34}}}
  {{{strategies: S_mesh} {layers: met4}} {{strategies: S_mesh} {layers: met5}} {via_master: V45}}
  {{{strategies: S_mesh} {layers: met5}} {{macro_pins: all} {layers: met4}} {via_master: V45}}
  {{intersection: undefined} {via_master: NIL}}
}
compile_pg -strategies {S_mesh S_rail} -via_rule R_all
puts "PDN shapes: [sizeof_collection [get_shapes -quiet -filter {shape_use==stripe}]] stripes, [sizeof_collection [get_shapes -quiet -filter {shape_use==follow_pin}]] rails, [sizeof_collection [get_vias -quiet]] vias"

# ---- b6 up-front fix 1: strap-end clearance (b5m section P, user-approved there): the met4 PG strap that starts at x 1738.69-1741.79, y 942.93 sits 0.30 um from a via-stack pad edge (m4.5ab needs 0.40):
#      raise its bottom edge by 0.1 um to y 943.03.  Done before any routing so the router sees the final PG geometry.
set target {}
foreach_in_collection s [get_shapes -quiet -intersect {{1739.0 942.8} {1741.5 943.2}}] {
  if {[get_attribute $s layer_name] eq "met4" && [get_attribute $s shape_use] eq "stripe"} { lappend target $s }
}
puts "P_FOUND: [llength $target] met4 stripe shape(s) at the strap start"
if {[llength $target] == 1} {
  set s [lindex $target 0]; set bb [get_attribute $s bbox]
  set x1 [lindex $bb 0 0]; set y1 [lindex $bb 0 1]; set x2 [lindex $bb 1 0]; set y2 [lindex $bb 1 1]
  set net [get_attribute [get_attribute $s owner] full_name]
  if {abs($y1 - 942.93) < 0.01 && abs($x1 - 1738.69) < 0.01} {
    remove_shapes $s
    set n [create_shape -shape_type rect -layer met4 -net [get_nets $net] -shape_use stripe -boundary [list [list $x1 943.03] [list $x2 $y2]]]
    puts "P_TRIMMED: $net met4 stripe {$x1 $y1 $x2 $y2} -> {$x1 943.03 $x2 $y2}, new shape [sizeof_collection $n]"
  } else { puts "P_SKIP: the matched stripe is not the expected one: $bb" }
} else { puts "P_SKIP: expected exactly 1 stripe, found [llength $target]" }
# ---- b6 up-front fix 2: ICC2's router/check_routes do not apply the met4 wide-metal spacing (fat table 0.4 um for width >= 3) against PG straps (b5i m4.5ab).
#      A 0.1 um halo routing blockage on every met4 strap (all four sides) keeps signal wires/via pads >= 0.4 um away.  Removed again by b6_06_eco before the finish.
set blk {}
foreach_in_collection s [get_shapes -quiet -filter "layer_name==met4 && shape_use==stripe"] {
  set bb [get_attribute $s bbox]
  set x1 [lindex $bb 0 0]; set y1 [lindex $bb 0 1]; set x2 [lindex $bb 1 0]; set y2 [lindex $bb 1 1]
  if {($x2 - $x1) < 3.0} continue
  set blk [add_to_collection $blk [create_routing_blockage -layers met4 -boundary [list [list [expr {$x1-0.1}] [expr {$y1-0.1}]] [list [expr {$x2+0.1}] [expr {$y2+0.1}]]]]]
}
puts "B6_HALO: [sizeof_collection $blk] met4 halo routing blockages created (all PG met4 straps wider than 3 um)"
redirect -file $RUN/reports/pg_drc.txt { check_pg_drc }
redirect -file $RUN/reports/pg_missing_vias.txt { check_pg_missing_vias }
redirect -file $RUN/reports/pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
save_stage 02_pdn
stage_time pdn $t0
exit
