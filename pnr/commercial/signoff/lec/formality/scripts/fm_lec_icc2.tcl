# fm_lec_icc2.tcl -- Step B4c: Formality LEC of the post-route ICC2 netlist.
#   fm_shell -f fm_lec_icc2.tcl     env: REPO PDKDIR RUN IMPL REFMODE=rtl|dc  SVF=<file>|none  [RTL_LIST] [REF_NETLIST]
#   REFMODE=rtl : reference = the 28 SV files + 5 defines (as B4a), optional DC SVF (see report for why it may be useless here)
#   REFMODE=dc  : reference = DC-NXT netlist (itself proven == RTL in B4a), no SVF; netlist-to-netlist hop
# Implementation = ICC2 write_verilog -exclude {pg_netlist physical_only_cells} output: flat, no PG pins, 115 port diodes, no assigns.
# Same rules as B4a: no set_constant / set_dont_verify / user_match / waivers.  Every setting carries its reason.
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set IMPL   $::env(IMPL)
set SVFF   $::env(SVF)
set MODE   $::env(REFMODE)
set TOP    rv32i_cpu_top
set B      $PDKDIR/build/db
set SRAMDB $B/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
set STDDB  $B/sky130_fd_sc_hd__tt_025C_1v80.db
file mkdir $RUN

# Host rule: <= 2 cores (VMware guest; Innovus runs concurrently).
set_host_options -max_cores 2
# Missing RTL/modules must not silently become black boxes (only the SRAM, from its .db, is one).
set_app_var hdlin_unresolved_modules error
# Report all failing points, not 20, to characterise a non-equivalence fully.
set_app_var verification_failing_point_limit 0

if {$SVFF ne "none"} { set_svf $SVFF } else { puts "NO SVF" }

if {$MODE eq "rtl"} {
  # reference = RTL (SRAM .db first so the 10 sram instances resolve as the library macro)
  read_db -container r -technology_library $SRAMDB
  set files {}
  set fh [open $::env(RTL_LIST) r]
  while {[gets $fh l] >= 0} { if {[string trim $l] ne ""} { lappend files [string trim $l] } }
  close $fh
  foreach f $files { if {[string match *stub* $f]} { error "SRAM stub must not be read: $f" } }
  set defines {PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130}
  read_sverilog -container r -libname WORK -define $defines $files
  set_top r:/WORK/$TOP
} else {
  # reference = DC netlist; std-cell + SRAM .db read in 'r' BEFORE its netlist (tech library must precede the design)
  read_db -container r -technology_library $STDDB
  read_db -container r -technology_library $SRAMDB
  read_verilog -container r -libname WORK -netlist $::env(REF_NETLIST)
  set_top r:/WORK/$TOP
}

# implementation libraries after the reference top is set (B4a finding: otherwise FM-236 / FE-LINK-2)
read_db -container i -technology_library $STDDB
read_db -container i -technology_library $SRAMDB
read_verilog -container i -libname WORK -netlist $IMPL
set_top i:/WORK/$TOP

match
redirect -file $RUN/unmatched_points.txt {report_unmatched_points}
redirect -file $RUN/black_boxes.txt {report_black_boxes -all}
redirect -file $RUN/svf_operations.txt {report_svf_operation}
puts "MATCH_DONE"
set rc [verify]
puts "VERIFY_RESULT: $rc"
redirect -file $RUN/failing_points.txt {report_failing_points}
redirect -file $RUN/aborted_points.txt {report_aborted_points}
redirect -file $RUN/unverified_points.txt {report_unverified_points}
puts "FM_DONE"
exit
