# b9_probe.tcl -- view-only probe of b8 06b_eco: (1) locate the native soft DRC (Min-max layer), (2) inspect the axi_rdata_i[15]/[16] port nets.  Never saves.
source [file join [file dirname [info script]] b8_common.tcl]
view_stage 06b_eco
source [file join $SCRIPTDIR reload.tcl]
# (1) native DRC
set_app_options -name route.detail.report_soft_drc_separately -value true
redirect -file $RUN/reports/b9_probe_check_routes.txt { check_routes -drc true -antenna false -open_net false -report_all_open_nets false }
foreach ed [get_object_name [get_drc_error_data -all]] {
  set n 0; catch { set n [sizeof_collection [get_drc_errors -error_data $ed -quiet]] }
  puts "P_EDATA $ed n=$n"
}
foreach ed {zroute.err} { catch { foreach_in_collection e [get_drc_errors -error_data $ed] { puts "P_ERR type=[get_attribute $e type_name] bbox=[get_attribute $e bbox] layer=[get_attribute $e layer_name] objs=[get_attribute $e objects]" } } m; puts "P_ERRMSG $m" }
# shapes on layers outside the allowed range
foreach L {li1 met5} { puts "P_SHAPES $L [sizeof_collection [get_shapes -quiet -filter "layer_name==$L"]]" }
foreach L {li1 met5} { foreach_in_collection s [get_shapes -quiet -filter "layer_name==$L && shape_use!=stripe && shape_use!=follow_pin"] { puts "P_SHAPE $L [get_attribute $s bbox] net=[get_object_name [get_attribute $s owner]] use=[get_attribute $s shape_use]" } }
foreach_in_collection s [get_shapes -quiet -filter "layer_name==met4 && shape_use==wire"] { set n [get_attribute $s owner]; if {[get_attribute $n name] eq "axi_rdata_i[15]"} { puts "P_M4 [get_attribute $s bbox]" } }
# nets with explicit layer limits
foreach a {min_routing_layer max_routing_layer} { catch { puts "P_NETS_$a [get_object_name [get_nets -quiet -hier -filter "$a!=\"\""]]" } m }
# (2) the two port nets
foreach pn {axi_rdata_i[15] axi_rdata_i[16]} {
  set net [get_nets $pn]
  puts "P_NET $pn loads=[sizeof_collection [all_connected $net -leaf]] "
  foreach_in_collection p [all_connected $net -leaf] { puts "P_PIN $pn [get_object_name $p] cell=[get_attribute [get_cells -of_objects $p -quiet] ref_name] bbox=[get_attribute $p bbox]" }
  set port [get_ports $pn]; puts "P_PORT $pn bbox=[get_attribute $port bbox]"
  catch { report_net_fanout -connections $net } m
}
redirect -file $RUN/reports/b9_probe_net.txt { foreach pn {axi_rdata_i[15] axi_rdata_i[16]} { report_net -connections -verbose [get_nets $pn] } }
puts "P_DONE"
exit
