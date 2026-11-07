# reload.tcl -- cheap re-assertion of the per-design settings after open_stage in stages 04+ (they are saved with the block; this guards against drift)
set_ignored_layers -min_routing_layer met1 -max_routing_layer met4
set_attribute [get_lib_cells -quiet */sky130_fd_sc_hd__diode_2] dont_use false
set_app_options -name opt.common.max_fanout -value 16
set_app_options -name opt.port.eliminate_verilog_assign -value true
catch {set_voltage 1.8 -object_list [get_nets VPWR]}
catch {set_voltage 0 -object_list [get_nets VGND]}
# B5e: the router must never use li1 (set in sky130_tech_setup.tcl; stored with the block).  Stop here if it is not in force.
set _gm [get_app_option_value -name route.common.global_min_layer_mode]
puts "ROUTE_GLOBAL_MIN_LAYER_MODE: $_gm"
if {$_gm ne "hard"} { error "B5e: route.common.global_min_layer_mode is '$_gm', expected hard (li1 would be routable)" }
