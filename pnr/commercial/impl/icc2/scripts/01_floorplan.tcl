# 01_floorplan.tcl -- Step B5a stage 1: library, netlist, floorplan identical to the OpenROAD arm.
#   die 0 0 3600 1800, core 20 20 3580 1780, row lattice of the OR DEF (x0 20.24, y0 24.48), 503 fixed pins from pin_template.def,
#   10 SRAMs fixed at macro_placement.cfg.  Netlist = Formality-proven DC-NXT netlist (b3a_dc_tt).
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
file delete -force $DLIB
create_lib -technology $B/ndm/sky130_hd.tf \
  -ref_libs [list $B/ndm/sky130_hd_tt.ndm $B/ndm/sky130_hd_phys.ndm $B/ndm/${SRAM}.ndm] $DLIB
read_verilog -top $TOP $NETLIST
current_block $TOP
link_block
source $B/ndm/sky130_tech_setup.tcl
# flatten DC's 3-module hierarchy (OpenROAD arm is flat); instance names become u_core/u_dcache/...
ungroup_cells -all -flatten
puts "FLAT cells: [sizeof_collection [get_cells -hier -filter is_hierarchical==false]] hier: [sizeof_collection [get_cells -hier -filter is_hierarchical==true]]"

# ---- die/core + rows + pins from the DEF the DC arm already used (mk_fp_def.py; rows on the OR lattice)
exec python3 -I $REPO/pnr/commercial/syn/dc/scripts/mk_fp_def.py $REPO $RUN/out/fp.def
# core boundary = the OpenROAD row lattice (x 20.24..3579.72 = 7738 sites, y 24.48..1778.88 = 645 rows); offsets bring the die to 0 0 3600 1800
initialize_floorplan -boundary {{20.24 24.48} {3579.72 1778.88}} -core_offset {20.24 24.48 20.28 21.12} -site_def unithd -flip_first_row true
read_def -include {ports} $RUN/out/fp.def
puts "ROWS: [sizeof_collection [get_site_rows]]  TRACKS: [sizeof_collection [get_tracks]]"
puts "BOUNDARY: [get_attribute [current_block] boundary_bounding_box]  CORE: [get_attribute [current_block] core_area_bbox]"
foreach_in_collection t [get_tracks] { puts "trk [get_attribute $t layer_name] dir=[get_attribute $t direction] space=[get_attribute $t space] offset=[get_attribute $t offset]" }
puts "PORTS placed: [sizeof_collection [get_ports -filter physical_status==fixed]] of [sizeof_collection [get_ports]]"
# ---- macros
set cfg [open $CFGDIR/macro_placement.cfg r]
set nplaced 0
while {[gets $cfg l] >= 0} {
  regsub {#.*} $l {} l; set l [string trim $l]; if {$l eq ""} continue
  lassign $l nm x y o
  # yosys-style "u_core.u_icache.gen_data_sram[0].u_data_sram" -> flat DC name "u_core/u_icache_gen_data_sram_0__u_data_sram"
  set p [split $nm .]
  set idx ""; if {[regexp {gen_data_sram\[(\d)\]} $nm -> idx]} { set leaf "gen_data_sram_${idx}__u_data_sram" } else { set leaf [lindex $p end] }
  set cache [lindex $p 1]
  set cands [list "u_core/${cache}/${leaf}" "u_core/${cache}_${leaf}"]
  set c ""
  foreach cand $cands { set cc [get_cells -quiet $cand]; if {[sizeof_collection $cc] == 1} { set c $cc; break } }
  if {$c eq ""} { error "macro for $nm not found (tried $cands)" }
  set_cell_location -coordinates [list $x $y] -orientation $o -fixed $c
  incr nplaced
}
close $cfg
puts "MACROS placed: $nplaced"
foreach_in_collection c [get_cells -hier -filter "ref_name==$SRAM"] {
  puts "  [get_object_name $c] bbox=[get_attribute $c bbox] orient=[get_attribute $c orientation] status=[get_attribute $c physical_status]"
}
catch {check_design -checks physical_constraints}
save_block -as ${TOP}/01_floorplan
save_lib
puts "STAGE_SAVED: 01_floorplan"
stage_time floorplan $t0
exit
