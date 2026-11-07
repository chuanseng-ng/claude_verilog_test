# fm_lec_or_frontend.tcl -- B2 OpenROAD arm, hop 1: RTL (the 28 SV files + 5 defines, as in fm_lec_icc2.tcl REFMODE=rtl) == the sv2v output
# (pnr/sky130/cpu/rv32i_cpu_top_sv2v.v, Verilog-2005) that LibreLane/Yosys actually synthesised (USE_SYNLIG=false).  Needed because Yosys names its flops by the
# flattened packed-struct bit index (u_core.ex1a_ex1b_reg_q[310]) and cells anonymously (_NNNNN_), so an RTL-vs-netlist compare cannot be matched by name
# (see report); sv2v keeps those bit-index names, so hop 2 (sv2v vs Yosys/OpenROAD netlist) is matched by name.
#   env: REPO PDKDIR RUN SV2V   (RTL_LIST from rtl_list.sh).  Same rules as fm_lec_icc2.tcl: no set_constant / set_dont_verify / user_match / waivers.
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set SV2V   $::env(SV2V)
set TOP    rv32i_cpu_top
set B      $PDKDIR/build/db
set SRAMDB $B/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
file mkdir $RUN
set_host_options -max_cores 2
set_app_var hdlin_unresolved_modules error
set_app_var verification_failing_point_limit 0
puts "NO SVF"
read_db -container r -technology_library $SRAMDB
set files {}
set fh [open $::env(RTL_LIST) r]
while {[gets $fh l] >= 0} { if {[string trim $l] ne ""} { lappend files [string trim $l] } }
close $fh
foreach f $files { if {[string match *stub* $f]} { error "SRAM stub must not be read: $f" } }
set defines {PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130}
read_sverilog -container r -libname WORK -define $defines $files
set_top r:/WORK/$TOP
read_db -container i -technology_library $SRAMDB
read_sverilog -container i -libname WORK $SV2V
set_top i:/WORK/$TOP
match
redirect -file $RUN/unmatched_points.txt {report_unmatched_points}
redirect -file $RUN/black_boxes.txt {report_black_boxes -all}
puts "MATCH_DONE"
set rc [verify]
puts "VERIFY_RESULT: $rc"
redirect -file $RUN/failing_points.txt {report_failing_points}
redirect -file $RUN/aborted_points.txt {report_aborted_points}
redirect -file $RUN/unverified_points.txt {report_unverified_points}
puts "FM_DONE"
exit
