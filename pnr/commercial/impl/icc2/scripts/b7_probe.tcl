# b7_probe.tcl -- view-only probe of the b6 06c_eco3 label (never save_lib): SRAM / dout0 pin geometry, a violator net's routing, hold endpoint cells.
source [file join [file dirname [info script]] b6_common.tcl]
view_stage 06c_eco3
foreach sr [get_cells -hierarchical -filter "ref_name==$SRAM"] {
  puts "SRAM [get_attribute $sr full_name] bbox=[get_attribute $sr bbox] orient=[get_attribute $sr orientation]"
}
set sr [get_cells -hierarchical -filter "ref_name==$SRAM && full_name=~*icache_gen_data_sram_0*"]
puts "PROBE_SRAM [get_attribute $sr full_name]"
foreach i {0 1 2 15 30 31} {
  set p [get_pins -quiet "[get_attribute $sr full_name]/dout0\[$i\]"]
  if {[sizeof_collection $p]} {
    puts "DOUT $i bbox=[get_attribute $p bbox]"
    foreach_in_collection s [get_shapes -of_objects $p -quiet] { puts "  shape [get_attribute $s layer_name] [get_attribute $s bbox]" }
    set n [get_nets -of_objects $p]
    puts "  net [get_attribute $n full_name] fanout pins: [get_object_name [get_pins -of_objects $n -filter {direction==in}]] len=[get_attribute $n route_length]"
  }
}
puts "DIE [get_attribute [current_design] boundary_bbox]"
foreach f {halo} { }
set p [get_pins u_core_u_dcache/data_dout_r_reg_2__26_/D]
set n [get_nets -of_objects $p]
puts "N3594 [get_object_name $n] drv=[get_object_name [get_pins -of_objects $n -filter {direction==out}]] loads=[get_object_name [get_pins -of_objects $n -filter {direction==in}]]"
foreach_in_collection s [get_shapes -of_objects $n -quiet] { puts "  N3594 shape [get_attribute $s layer_name] [get_attribute $s bbox]" }
foreach_in_collection s [get_vias -of_objects $n -quiet] { puts "  N3594 via [get_attribute $s via_def_name] [get_attribute $s bbox]" }
puts "ANTDIO: [get_object_name [get_cells -quiet ANTDIO*]]"
exit
