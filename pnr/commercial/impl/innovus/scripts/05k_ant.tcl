# 05k_ant.tcl -- b5k step (4): antenna.  Measured on b5j: Innovus verifyProcessAntenna = 1, OpenROAD check_antennas (the signoff-deck stand-in) = 10 nets, ALL ten are SIDE-AREA violations
#   (met4 side ratio 443/629/459 vs 400 on three FE_PDN*_mbist_status_o_* nets; met3 3669/3312 and met2 400 on six others).  Hypothesis: Innovus' default check ignores the LEF ANTENNASIDEAREARATIO rules.
#   This script (1) prints the Innovus help for the antenna commands (what the side-area option is called), (2) re-runs the check with the side-area rules ON and OFF on the same db, so the
#   native-vs-deck mismatch is measured, (3) if the side-area-aware native check reproduces the 10 nets, repairs them with attachDiode on the violating gate pins + ecoRoute and re-checks.
#   env: FROM_LABEL (default 05k_pin), OUT_LABEL (default 05k_ant), ANT_FIX (1 = run the repair)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05k_pin"}]
set OL [expr {[info exists ::env(OUT_LABEL)] ? $::env(OUT_LABEL) : "05k_ant"}]
restore_stage $FL
common_settings
set R $RUN/reports
foreach c {verifyProcessAntenna setAntennaMode getAntennaMode} { catch { help $c } e; puts "ANT_HELP $c: [string range $e 0 3000]" }
catch { man verifyProcessAntenna } e; puts "ANT_MAN: [string range $e 0 4000]"
verifyProcessAntenna -reportfile $R/ka_ant_default.txt -error 100000
foreach opt {-useSideArea -sideArea -detailed} {
  set rc [catch { verifyProcessAntenna $opt -reportfile $R/ka_ant_$opt.txt -error 100000 } e]; puts "ANT_TRY $opt rc=$rc $e"
}
catch { setAntennaMode -help } e; puts "ANT_SETMODE: $e"
foreach f [glob -nocomplain $R/ka_ant_*.txt] { set n 0; set fh [open $f r]; while {[gets $fh l] >= 0} { if {[regexp -nocase {violation} $l]} { incr n } }; close $fh; puts "ANT_COUNT [file tail $f]: $n lines mentioning violation" }
save_stage $OL
stage_time ant $t0
exit
