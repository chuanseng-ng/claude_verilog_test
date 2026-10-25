# 03_place.tcl -- Step B5a stage 3: constraints, placement setup, place_opt (coarse place + initial/final opto + legalisation).
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 02_pdn 03_place
source [file join $SCRIPTDIR setup_design.tcl]
puts "SDC_MD5: [exec md5sum $SDC]"
redirect -file $RUN/reports/check_timing_pre.txt { check_timing }
# ---- placement controls (OpenROAD: PL_TARGET_DENSITY_PCT 25, GPL/DPL_CELL_PADDING 4 sites per side, time+routability driven)
set_app_options -name place.coarse.max_density -value 0.25
set pad_cells [remove_from_collection [get_lib_cells sky130_hd_tt/*] [get_lib_cells -quiet {sky130_hd_tt/*tap* sky130_hd_tt/*decap* sky130_hd_tt/*fill* sky130_hd_tt/*diode*}]]
set_placement_spacing_label -name PAD -side both -lib_cells $pad_cells
set_placement_spacing_rule -labels {PAD PAD} {0 7}
puts "PAD label on [sizeof_collection $pad_cells] lib cells, illegal gap 0..7 sites (4 sites per side)"
# ---- constants / output-to-output shorts left by DC (131 assigns): buffer them like OpenROAD's synthesis netlist handling
# ICC2 ignores the SDC set_max_fanout (CSTR-011); the equivalent app option carries the SDC value 16
set_app_options -name opt.common.max_fanout -value 16
set_app_options -name opt.port.eliminate_verilog_assign -value true   ;# ICC2 has no set_fix_multiple_port_nets
catch {check_design -checks pre_placement_stage}
set t1 [clock seconds]
place_opt
stage_time place_opt $t1
catch {legalize_placement}
redirect -file $RUN/reports/place_check_legality.txt { check_legality -verbose }
redirect -file $RUN/reports/place_qor.txt { report_qor -summary; report_qor }
redirect -file $RUN/reports/place_timing.txt { report_timing -max_paths 5 -delay_type max; report_timing -max_paths 5 -delay_type min }
redirect -file $RUN/reports/place_congestion.txt { report_congestion }
redirect -file $RUN/reports/place_utilization.txt { report_utilization }
save_stage 03_place
stage_time place $t0
exit
