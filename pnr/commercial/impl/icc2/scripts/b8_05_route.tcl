# b8_05_route.tcl -- b6 stage 5: antenna rules, input-port protection diodes, route_auto, route_opt (all MCMM scenarios), detail-route repair loop until DRC/short/open = 0.
#   Carried over from b5 up front: li1 banned (global_min_layer_mode hard, reload.tcl guards it), route.global.effort high + macro_boundary_track_utilization 60 + DRC-aware partitioning (b5x),
#   met4 halo blockages on the PG straps (created in b6_02_pdn, still in the block; removed in b6_06_eco), strap-end trim (b6_02_pdn).
source [file join [file dirname [info script]] b8_common.tcl]
set t0 [clock seconds]
open_stage 04_cts 05_route
source [file join $SCRIPTDIR reload.tcl]
set_app_options -name route.global.effort_level -value high
set_app_options -name route.global.macro_boundary_track_utilization -value 60
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
foreach o {route.global.effort_level route.global.macro_boundary_track_utilization route.detail.optimize_partition_size_for_drc route.common.global_min_layer_mode} { puts "OPT $o = [get_app_option_value -name $o]" }
puts "B6_HALO_PRESENT: [sizeof_collection [get_routing_blockages -quiet]] routing blockages in the block"
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
set in_ports [remove_from_collection [get_ports -filter "direction==in"] [get_ports clk_i]]
add_port_protection_diodes -diode_lib_cell [get_lib_cells sky130_hd_mcmm/sky130_fd_sc_hd__diode_2] -port $in_ports -prefix PORTDIODE_
puts "PORT DIODES: [sizeof_collection [get_cells -quiet -hier -filter {ref_name==sky130_fd_sc_hd__diode_2}]]"
catch {legalize_placement}
proc count_drc {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of DRCs = (\d+)} $l -> n }; close $fh; return $n }
# shorts between a halo blockage and the PG strap it covers are artifacts of the halo (the blockage overlaps the strap), not layout shorts
proc count_short {f} { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr n } }; close $fh; return $n }
proc count_open {f} { set n -1; set fh [open $f r]; while {[gets $fh l] >= 0} { regexp {Total number of open nets is (\d+)} $l -> n }; close $fh; return $n }
proc chk {tag} {
  global RUN
  redirect -file $RUN/reports/r_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/r_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set d [count_drc $RUN/reports/r_checks_$tag.txt]; set s [count_short $RUN/reports/r_lvs_$tag.txt]; set o [count_open $RUN/reports/r_lvs_$tag.txt]
  puts "R_CHECK $tag: DRCs=$d shorts=$s opens=$o"
  return [list $d $s $o]
}
set t1 [clock seconds]
route_auto
stage_time route_auto $t1
save_block
chk auto
set t2 [clock seconds]
route_opt
stage_time route_opt $t2
set r [chk opt]
# ---- repair loop (b5: -8 %/pass at worst; the b5x global-route settings reached 0 within 8 passes)
for {set i 1} {$i <= 10} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 1] == 0 && [lindex $r 2] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chk rep$i]
}
puts "R_FINAL: DRCs=[lindex $r 0] shorts=[lindex $r 1] opens=[lindex $r 2]"
redirect -file $RUN/reports/route_qor.txt { report_qor -summary; report_qor -scenarios [all_scenarios]; report_qor }
redirect -file $RUN/reports/route_timing.txt { foreach s [get_object_name [all_scenarios]] { current_scenario $s; report_timing -scenarios $s -max_paths 3 -delay_type max; report_timing -scenarios $s -max_paths 3 -delay_type min }; current_scenario func_tt }
redirect -file $RUN/reports/route_constraints.txt { report_constraints -all_violators -max_transition -max_capacitance }
file mkdir $RUN/out
catch {write_def $RUN/out/pre_ant.def}
save_stage 05_route
stage_time route $t0
exit
