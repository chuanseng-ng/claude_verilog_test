# 04_cts.tcl -- Step B5a stage 4: clock tree synthesis + clock routing + post-CTS optimisation (clock_opt).
#   CTS_CLK_BUFFERS clkbuf_2/4/8/16 (CTS_ROOT_BUFFER clkbuf_16: ICC2 has no root-cell option, recorded), sink cluster size 25 (cts.common.max_fanout).
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
open_stage 03_place 04_cts
source [file join $SCRIPTDIR reload.tcl]
set cts_cells [get_lib_cells -quiet {sky130_hd_tt/sky130_fd_sc_hd__clkbuf_2 sky130_hd_tt/sky130_fd_sc_hd__clkbuf_4 sky130_hd_tt/sky130_fd_sc_hd__clkbuf_8 sky130_hd_tt/sky130_fd_sc_hd__clkbuf_16}]
puts "CTS cells: [get_object_name $cts_cells]"
set_lib_cell_purpose -exclude cts [get_lib_cells sky130_hd_tt/*]
set_lib_cell_purpose -include cts $cts_cells
set_app_options -name cts.common.max_fanout -value 25
report_clock_tree_options
redirect -file $RUN/reports/clock_pre_cts.txt { report_clocks; report_clock_tree_options }
set t1 [clock seconds]
clock_opt
stage_time clock_opt $t1
redirect -file $RUN/reports/cts_clock_qor.txt { report_clock_qor -type summary; report_clock_qor -type structure; report_clock_qor -type latency; report_clock_qor -type local_skew }
redirect -file $RUN/reports/cts_timing.txt { report_timing -max_paths 5 -delay_type max; report_timing -max_paths 5 -delay_type min }
redirect -file $RUN/reports/cts_qor.txt { report_qor -summary; report_qor }
redirect -file $RUN/reports/cts_legality.txt { check_legality -verbose }
save_stage 04_cts
# B5e: clock routing happens in clock_opt, so audit li1 use right here (DEF dump -> scripts/li1_audit.py offline)
file mkdir $RUN/probe
write_def $RUN/probe/cts.def
stage_time cts $t0
exit
