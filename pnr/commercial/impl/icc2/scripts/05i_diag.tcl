# 05i_diag.tcl -- B5i: dump the geometry around the b5e met1 short (read-only; never save_lib)
source [file join [file dirname [info script]] common.tcl]
view_stage 05y_repair
set box {{1916.5 881.5} {1920.5 884.5}}
puts "DIAG cells:"
foreach_in_collection c [get_cells -quiet -intersect $box -hierarchical -filter "is_hierarchical==false"] {
  puts "  [get_attribute $c full_name] [get_attribute $c ref_name] bbox=[get_attribute $c bbox] orient=[get_attribute $c orientation]"
}
puts "DIAG shapes:"
foreach_in_collection s [get_shapes -quiet -intersect $box] {
  puts "  [get_attribute $s layer_name] net=[get_attribute [get_attribute $s owner] full_name] type=[get_attribute $s shape_type] bbox=[get_attribute $s bbox] route_type=[get_attribute $s route_type]"
}
puts "DIAG vias:"
foreach_in_collection s [get_vias -quiet -intersect $box] {
  puts "  [get_attribute $s via_rule] net=[get_attribute [get_attribute $s owner] full_name] bbox=[get_attribute $s bbox]"
}
puts "DIAG pins of nets:"
foreach n {u_core/ex1c_comb[158] u_core/ex1c_ex1b_reg_q[124]} {
  foreach_in_collection p [get_pins -quiet -of_objects [get_nets [list $n]]] { puts "  $n : [get_attribute $p full_name] [get_attribute $p bbox]" }
}
exit
