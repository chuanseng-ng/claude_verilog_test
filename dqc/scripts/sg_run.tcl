# sg_run.tcl - one SpyGlass goal on soc_top.  Driven entirely by environment variables set by
# dqc/Makefile; never run by hand without them.
#
#   DQC_RUN    run directory (holds sources.sgf, incdirs.txt, defines.txt from gen_sourcelist.py)
#   DQC_GOAL   GuideWare goal, e.g. lint/lint_rtl, cdc/cdc_verify_struct, rdc/rdc_verify_struct
#   DQC_TOP    top module (soc_top | a selftest top)
#   DQC_SGDC   space separated SGDC constraint files ("" for none)
#   DQC_AWL    space separated SpyGlass waiver (.awl) files ("" for none)
#   DQC_MTHRESH synthesis memory threshold in bits (default 65536)
#
# A trailing `exit` is mandatory: without it sg_shell sits at its prompt after the script ends.

proc env_or {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}

set run    [env_or DQC_RUN ""]
set goal   [env_or DQC_GOAL ""]
set top    [env_or DQC_TOP soc_top]
set sgdcs  [env_or DQC_SGDC ""]
set awls   [env_or DQC_AWL ""]
set mthr   [env_or DQC_MTHRESH 65536]
if {$run eq "" || $goal eq ""} { puts "sg_run.tcl: DQC_RUN and DQC_GOAL are required"; exit 2 }

set pname [string map {/ _} $goal]
new_project $run/$pname -force

read_file -type sourcelist $run/sources.sgf

set fh [open $run/incdirs.txt r]
foreach d [split [read $fh] "\n"] { if {$d ne ""} { set_option incdir $d } }
close $fh
set fh [open $run/defines.txt r]
foreach d [split [read $fh] "\n"] { if {$d ne ""} { set_option define $d } }
close $fh

set_option top $top
set_option language_mode mixed
set_option enableSV09 yes
set_option sort yes
set_option mthresh $mthr

foreach f $sgdcs { read_file -type sgdc $f }
foreach f $awls  { read_file -type awl  $f }

current_goal $goal -top $top
run_goal
save_project
exit
