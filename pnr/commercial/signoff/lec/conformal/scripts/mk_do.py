#!/usr/bin/env python3
"""mk_do.py <genus lec do-file> <out do-file>
Derive the Conformal do-file used by step B4b from the one Genus wrote (write_do_lec -golden_design rtl).
The Genus-generated file is never edited; each substitution below is asserted to match exactly the expected number
of times, so a regenerated Genus file that no longer fits fails loudly instead of silently running something else.
Reasons:
  S1 log path       : Genus hard-codes out/lec_*.log inside the Genus run dir; we must not write into Genus outputs.
                      The log goes to $env(LEC_RUN)/lec.log.
  S2 impl netlist   : the revised-netlist path becomes $env(IMPL) so the same file serves the real netlist and the
                      negative-control mutants (leg 1 is the only leg that reads the final netlist).
  S3 threads        : host rule (VMware guest hard-locks under full vCPU load) -> at most 2 threads, was 1,4.
  S4 leg-1 verdict  : after leg 1 reports non-PASS Genus' file calls `error`, and `set_dofile_abort exit` ends the
                      session, so leg 2 and the summary never run.  We keep that (a non-equivalence must stop the flow)
                      but print a greppable marker first.
  S5 exit           : the final `exit -f` is kept.
"""
import sys
src, dst = sys.argv[1:3]
t = open(src).read()
def sub(old, new, n):
    global t
    assert t.count(old) == n, (old, t.count(old), n)
    t = t.replace(old, new)
sub("set logfile /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/out/lec_rv32i_cpu_top.log ;# user can modify this name for succeeding runs",
    "# [B4b S1] log goes to the B4b run dir, not into the Genus run's out/ (Genus outputs stay read-only inputs)\nset logfile $env(LEC_RUN)/lec.log", 1)
sub("read_design -verilog95   -revised -lastmod -noelab /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v",
    "# [B4b S2] final netlist taken from $env(IMPL) (real Genus netlist, or a negative-control mutant of it)\nread_design -verilog95   -revised -lastmod -noelab $env(IMPL)", 1)
sub("set_parallel_option -threads 1,4 -norelease_license", "# [B4b S3] host rule: <=2 threads (Genus wrote 1,4)\nset_parallel_option -threads 1,2 -norelease_license", 2)
sub("set_compare_options -threads 1,4", "# [B4b S3] host rule: <=2 threads (Genus wrote 1,4)\nset_compare_options -threads 1,2", 2)
sub('if {![is_pass]} {\n    error "// ERROR: Compare was not equivalent."',
    'if {![is_pass]} {\n    # [B4b S4] greppable marker, then Genus\' own abort (leg 2 does not run on a non-equivalent leg 1)\n    puts "B4B_LEG1_VERDICT: NOT_EQUIVALENT"\n    error "// ERROR: Compare was not equivalent."', 1)
sub("write_verification_information\nreport_verification_information\n\n# Reports how effective the implementation information was.\nreport_implementation_information\n\nreset",
    'puts "B4B_LEG1_VERDICT: EQUIVALENT"\nwrite_verification_information\nreport_verification_information\n\n# Reports how effective the implementation information was.\nreport_implementation_information\n\nreset', 1)
open(dst, "w").write(t)
print("wrote", dst)
