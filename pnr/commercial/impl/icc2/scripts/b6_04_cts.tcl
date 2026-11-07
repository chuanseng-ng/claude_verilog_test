# b6_04_cts.tcl -- b6 stage 4: CTS + clock routing + post-CTS optimisation (clock_opt) over all MCMM scenarios (setup ss+tt, hold ff+tt).
source [file join [file dirname [info script]] b6_common.tcl]
set t0 [clock seconds]
open_stage 03_place 04_cts
source [file join $SCRIPTDIR reload.tcl]
set stdlibs {sky130_hd_mcmm/*}
set cts_cells [get_lib_cells -quiet {sky130_hd_mcmm/sky130_fd_sc_hd__clkbuf_2 sky130_hd_mcmm/sky130_fd_sc_hd__clkbuf_4 sky130_hd_mcmm/sky130_fd_sc_hd__clkbuf_8 sky130_hd_mcmm/sky130_fd_sc_hd__clkbuf_16}]
puts "CTS cells ([sizeof_collection $cts_cells]): [get_object_name $cts_cells]"
set_lib_cell_purpose -exclude cts [get_lib_cells $stdlibs]
set_lib_cell_purpose -include cts $cts_cells
set_app_options -name cts.common.max_fanout -value 25
redirect -file $RUN/reports/clock_pre_cts.txt { report_scenarios; report_clocks; report_clock_tree_options }
set t1 [clock seconds]
clock_opt
stage_time clock_opt $t1
redirect -file $RUN/reports/cts_clock_qor.txt { report_clock_qor -type summary; report_clock_qor -type structure; report_clock_qor -type latency; report_clock_qor -type local_skew }
redirect -file $RUN/reports/cts_timing.txt { foreach s [get_object_name [all_scenarios]] { current_scenario $s; report_timing -scenarios $s -max_paths 3 -delay_type max; report_timing -scenarios $s -max_paths 3 -delay_type min }; current_scenario func_tt }
redirect -file $RUN/reports/cts_qor.txt { report_qor -summary; report_qor -scenarios [all_scenarios]; report_qor }
redirect -file $RUN/reports/cts_legality.txt { check_legality -verbose }
save_stage 04_cts
stage_time cts $t0
exit
