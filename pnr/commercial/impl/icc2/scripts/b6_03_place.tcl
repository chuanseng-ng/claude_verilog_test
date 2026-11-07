# b6_03_place.tcl -- b6 stage 3: MCMM setup (b6_setup_mcmm.tcl: scenarios ss/tt/ff, TLU+ max/nom/min, PVT-matched ss/tt/ff libs) then place_opt over all active scenarios.
#   Hold: real delay cells only (dlygate*/dlymetal*/clkdlybuf*) are allowed for hold fixing, so ICC2 does not build chains of weak _1 buffers/inverters (b5: ZBUF/ZINV chains -> max-transition/cap violations).
source [file join [file dirname [info script]] b6_common.tcl]
set t0 [clock seconds]
open_stage 02_pdn 03_place
source [file join $SCRIPTDIR b6_setup_mcmm.tcl]
set stdlibs {sky130_hd_mcmm/*}
set all_std [get_lib_cells -quiet $stdlibs]
set_lib_cell_purpose -exclude hold $all_std
set dly [get_lib_cells -quiet {sky130_hd_mcmm/*dlygate* sky130_hd_mcmm/*dlymetal* sky130_hd_mcmm/*clkdlybuf*}]
set_lib_cell_purpose -include hold $dly
puts "HOLD_CELLS: [sizeof_collection $dly] lib cells : [lsort -unique [lmap c [get_object_name $dly] {lindex [split $c /] end}]]"
redirect -file $RUN/reports/check_timing_pre.txt { check_timing }
# ---- placement controls (OpenROAD: PL_TARGET_DENSITY_PCT 25, GPL/DPL_CELL_PADDING 4 sites per side, time+routability driven) -- as b5
set_app_options -name place.coarse.max_density -value 0.25
set pad_cells [remove_from_collection $all_std [get_lib_cells -quiet {sky130_hd_mcmm/*tap* sky130_hd_mcmm/*decap* sky130_hd_mcmm/*fill* sky130_hd_mcmm/*diode*}]]
set_placement_spacing_label -name PAD -side both -lib_cells $pad_cells
set_placement_spacing_rule -labels {PAD PAD} {0 7}
puts "PAD label on [sizeof_collection $pad_cells] lib cells, illegal gap 0..7 sites (4 sites per side)"
set_app_options -name opt.common.max_fanout -value 16
set_app_options -name opt.port.eliminate_verilog_assign -value true
catch {check_design -checks pre_placement_stage}
redirect -file $RUN/reports/hold_app_options.txt { get_app_options *hold* }
set t1 [clock seconds]
place_opt
stage_time place_opt $t1
catch {legalize_placement}
redirect -file $RUN/reports/place_check_legality.txt { check_legality -verbose }
redirect -file $RUN/reports/place_qor.txt { report_qor -summary; report_qor -scenarios [all_scenarios]; report_qor }
redirect -file $RUN/reports/place_timing.txt { foreach s [get_object_name [all_scenarios]] { current_scenario $s; report_timing -scenarios $s -max_paths 3 -delay_type max; report_timing -scenarios $s -max_paths 3 -delay_type min }; current_scenario func_tt }
redirect -file $RUN/reports/place_congestion.txt { report_congestion }
redirect -file $RUN/reports/place_utilization.txt { report_utilization }
save_stage 03_place
stage_time place $t0
exit
