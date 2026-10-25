# reload.tcl -- cheap re-assertion of the per-design settings after open_stage in stages 04+ (they are saved with the block; this guards against drift)
set_ignored_layers -min_routing_layer met1 -max_routing_layer met4
set_attribute [get_lib_cells -quiet */sky130_fd_sc_hd__diode_2] dont_use false
set_app_options -name opt.common.max_fanout -value 16
set_app_options -name opt.port.eliminate_verilog_assign -value true
catch {set_voltage 1.8 -object_list [get_nets VPWR]}
catch {set_voltage 0 -object_list [get_nets VGND]}
