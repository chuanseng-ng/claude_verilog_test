# fm_lec.tcl -- Step B4a: Synopsys Formality LEC, RTL (reference) == DC-NXT netlist (implementation), Sky130 rv32i_cpu_top.
#   fm_shell -f fm_lec.tcl      env: REPO PDKDIR RUN IMPL (netlist path) SVF (svf path, or "none") RTL_LIST TAG
# Reference  : the 28 native-SV files + 5 defines DC read (rtl_list.sh); the SRAM stub is never read.
# Implementation: DC's rv32i_cpu_top.nl.v + hd tt .db + SRAM .db.
# Every non-default setting below carries its reason.
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set IMPL   $::env(IMPL)
set SVFF   $::env(SVF)
set TOP    rv32i_cpu_top
set B      $PDKDIR/build/db
set SRAMDB $B/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
set STDDB  $B/sky130_fd_sc_hd__tt_025C_1v80.db
file mkdir $RUN

# Host rule: <= 2 cores (VMware guest hard-locks under full vCPU load).
set_host_options -max_cores 2

# --- documented settings -------------------------------------------------------------------------
# DC elaborated native SV; Formality must see the same defines.  Defines passed on read_sverilog below.
# Unresolved module references would silently become black boxes and hide a missing RTL file; keep the
# default (error) so only the SRAM, supplied via .db below, is a black box.
set_app_var hdlin_unresolved_modules error
# Memory .db cells: DC treats the SRAM as a dont_touch library macro.  Formality reads the same .db in BOTH
# containers, so reference and implementation SRAM instances are the same library cell and are matched by
# instance name with their pins compared as compare points (black-box semantics, outputs unconstrained).
# Report ALL failing points (default limit is 20) so a non-equivalence is fully characterised.
set_app_var verification_failing_point_limit 0
# Conservative on constants: do NOT enable verification_set_undriven_signals / constant propagation hacks.

# --- SVF (guidance from DC: ungroup, change_names, rename, constant regs, inversions) ---------------
if {$SVFF ne "none"} { set_svf $SVFF } else { puts "NO SVF (ablation run)" }

# --- reference: RTL (SRAM .db read first so the 10 sram instances resolve as library black boxes)
read_db -container r -technology_library $SRAMDB
set files {}
set fh [open $::env(RTL_LIST) r]
while {[gets $fh l] >= 0} { if {[string trim $l] ne ""} { lappend files [string trim $l] } }
close $fh
foreach f $files { if {[string match *stub* $f]} { error "SRAM stub must not be read: $f" } }
set defines {PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130}
read_sverilog -container r -libname WORK -define $defines $files
set_top r:/WORK/$TOP

# --- implementation: libs + DC netlist -----------------------------------------------------------------
# Order matters (measured): the implementation .db files are read AFTER the reference top is set.  Reading the
# std-cell .db into 'i' while 'r' held only the SRAM library raised FM-236 ("top not linked in 'r'") and left every
# library cell unlinked in the netlist (FE-LINK-2).  -technology_library = cells are leaf library cells with their
# Liberty functions.  The SRAM .db is read in both containers so the 10 macros are the same black box on both sides.
read_db -container i -technology_library $STDDB
read_db -container i -technology_library $SRAMDB

read_verilog -container i -libname WORK -netlist $IMPL
set_top i:/WORK/$TOP

# --- match / verify ----------------------------------------------------------------------------------
match
redirect -file $RUN/unmatched_points.txt {report_unmatched_points}
redirect -file $RUN/black_boxes.txt {report_black_boxes -all}
redirect -file $RUN/svf_operations.txt {report_svf_operation}
redirect -file $RUN/matched_points.txt {report_matched_points}
puts "MATCH_DONE"
set rc [verify]
puts "VERIFY_RESULT: $rc"
redirect -file $RUN/failing_points.txt {report_failing_points}
redirect -file $RUN/aborted_points.txt {report_aborted_points}
redirect -file $RUN/unverified_points.txt {report_unverified_points}
redirect -file $RUN/passing_points.txt {report_passing_points}
puts "FM_DONE"
exit
