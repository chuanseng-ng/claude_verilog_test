# b6_diag_short.tcl -- DIAGNOSTIC (read-only, never saves): what sits at the persistent met2 short HFSNET_4041 x HFSNET_6006 near (1916.3, 879.2)
source [file join [file dirname [info script]] b6_common.tcl]
view_stage 06_eco
foreach n {HFSNET_4041 HFSNET_6006} {
  set net [get_nets $n]
  puts "NET $n: driver=[get_object_name [get_pins -of_objects $net -filter direction==out]] loads=[get_object_name [get_pins -of_objects $net -filter direction==in]]"
  foreach_in_collection p [get_pins -of_objects $net] { puts "  PIN [get_object_name $p] bbox=[get_attribute $p bbox] cell=[get_attribute [get_attribute $p cell] ref_name]" }
  catch { puts "  routing: layers min/max [get_attribute $net route_min_layer_name]/[get_attribute $net route_max_layer_name] rule=[get_attribute $net routing_rule]" }
}
puts "CELLS within 6 um of (1916.3,879.2):"
foreach_in_collection c [get_cells -quiet -hierarchical -intersect {{1910.0 873.0} {1923.0 886.0}}] { puts "  [get_object_name $c] [get_attribute $c ref_name] bbox=[get_attribute $c bbox] status=[get_attribute $c physical_status]" }
catch { foreach_in_collection s [get_net_shapes -quiet -intersect {{1914.5 877.5} {1918.5 881.0}}] { puts "  SHAPE [get_attribute $s layer_name] [get_attribute $s bbox] net=[get_attribute [get_attribute $s owner] full_name]" } } e
puts "net_shapes rc: $e"
exit
