# b9_vc_probe.tcl -- diagnose the verifyConnectivity hang on the b7/b8 databases (doc caveat 8, item 17).  View-only: restores a saved db, runs ONE check variant, never saves.
#   env VC_LABEL (default 08b_eco), VC_STEP: all (the original -type all call of 06m_finish) | allsmall (-type all -error 100) | pg (regular -net VPWR / VGND) | regular (all nets, -error 100) | special | sigsample (VC_N signal nets one by one, per-net wall time) | eco (only the nets of the ECO cells DB8_*/B8ANT*/AB8*)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set LBL [expr {[info exists ::env(VC_LABEL)] ? $::env(VC_LABEL) : "08b_eco"}]
restore_stage $LBL
common_settings
set R $RUN/reports/vcprobe; file mkdir $R
proc tt {m} { global t0; puts "VC_T [expr {[clock seconds]-$t0}] s: $m"; flush stdout }
set step $::env(VC_STEP)
tt "restored $LBL, step=$step"
switch $step {
  pg { foreach n {VPWR VGND} { tt "start regular -net $n"; verifyConnectivity -type regular -net $n -error 100 -noAntenna -report $R/pg_$n.txt; tt "done regular -net $n" } }
  regular { tt "start regular all"; verifyConnectivity -type regular -error 100 -noAntenna -report $R/regular_all.txt; tt "done regular all" }
  all { tt "start all"; verifyConnectivity -type all -noAntenna -error 100000 -report $R/all.txt; tt "done all" }
  allsmall { tt "start all, -error 100"; verifyConnectivity -type all -noAntenna -error 100 -report $R/all_small.txt; tt "done all small" }
  seq {
    # replicate the 06m_finish order in ONE session: verify_drc, verifyProcessAntenna, then verifyConnectivity -type all (the call that hung on b7/b8)
    tt "start verify_drc"; verify_drc -limit 1000000 -report $R/seq_drc.txt; tt "done verify_drc"
    tt "start verifyProcessAntenna"; verifyProcessAntenna -reportfile $R/seq_antenna.txt -error 1000000; tt "done verifyProcessAntenna"
    tt "start verifyConnectivity -type all"; verifyConnectivity -type all -noAntenna -error 100000 -report $R/seq_all.txt; tt "done verifyConnectivity -type all"
  }
  special { tt "start special all"; verify_connectivity -type special -error 100 -report $R/special_all.txt; tt "done special all" }
  sigsample {
    set n 0; set N [expr {[info exists ::env(VC_N)] ? $::env(VC_N) : 300}]
    set nets [dbGet top.nets.name]
    set step_i [expr {[llength $nets] / $N + 1}]
    for {set i 0} {$i < [llength $nets] && $n < $N} {incr i $step_i} {
      set nm [lindex $nets $i]
      if {[string match VPWR $nm] || [string match VGND $nm]} continue
      set a [clock milliseconds]
      verifyConnectivity -type regular -net $nm -error 10 -noAntenna -report $R/s_$n.txt
      set ms [expr {[clock milliseconds]-$a}]
      puts "VC_NET $n $nm ${ms}ms"; flush stdout
      incr n
    }
    tt "sigsample done $n nets"
  }
  eco {
    set nets {}
    foreach pat {DB8_* B8ANT* AB8* ANTBUF* DB7* B7ANT*} { foreach i [dbGet -p2 top.insts.name $pat] { foreach t [dbGet $i.instTerms.net.name] { lappend nets $t } } }
    set nets [lsort -unique $nets]
    tt "eco nets: [llength $nets]"
    foreach nm $nets {
      if {[string match V* $nm]} continue
      set a [clock milliseconds]
      verifyConnectivity -type regular -net $nm -error 10 -noAntenna -report $R/e_tmp.txt
      puts "VC_NET eco $nm [expr {[clock milliseconds]-$a}]ms"; flush stdout
    }
    tt "eco done"
  }
}
tt "end"
exit
