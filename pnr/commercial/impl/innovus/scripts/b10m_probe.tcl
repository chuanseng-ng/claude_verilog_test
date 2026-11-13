# b10m_probe.tcl -- VIEW-ONLY probe of the b9 final pre-fill db (09_eco, copied to runs/b10_innovus/dbs): for every pin the PrimeTime judge lists as max-transition violator (env PINLIST file, one pin per line)
#   report net, driver cell, fanout, load bounding box (HPWL), routed length, and the native Innovus transition at that pin in av_ss / av_tt / av_ff.  Never saves.  env FROM_LABEL (default 09_eco).
source [file join [file dirname [file normalize [info script]]] common.tcl]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "09_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports/b10probe; file mkdir $R
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
extractRC
set fo [open $R/violator_nets.txt w]
set fh [open $::env(PINLIST) r]
while {[gets $fh p] >= 0} {
  if {$p eq ""} continue
  set net ""; set drv ""; set drvc ""; set nl 0; set hp ""; set wl ""; set loads {}
  if {[catch {
    set ptr [dbGet -p top.insts.instTerms.name $p]
    if {$ptr eq "0x0" || $ptr eq ""} { set pp [dbGet top.terms.name $p -p]; set net [dbGet $pp.net.name] } else { set net [dbGet [dbGet -p top.insts.instTerms.name $p].net.name] }
  } e]} { puts $fo "$p ERR $e"; continue }
  if {$net eq "" || $net eq "0x0"} { puts $fo "$p NONET"; continue }
  set n [dbGetNetByName $net]
  set dt [dbGet $n.instTerms.isOutput 1 -p]
  catch { set drv [dbGet $dt.inst.name]; set drvc [dbGet $dt.inst.cell.name] }
  set its [dbGet $n.instTerms]; set nl [llength $its]
  set xs {}; set ys {}
  foreach it $its { catch { set bx [lindex [dbGet $it.inst.box] 0]; if {[llength $bx] == 4} { lappend xs [lindex $bx 0] [lindex $bx 2]; lappend ys [lindex $bx 1] [lindex $bx 3] } } }
  catch { set xs [lsort -real $xs]; set ys [lsort -real $ys]; set hp [format %.1f [expr {([lindex $xs end]-[lindex $xs 0])+([lindex $ys end]-[lindex $ys 0])}]] }
  catch { set wl [dbGet $n.wires.length -e]; set wl [format %.1f [expr [join $wl +]]] }
  puts $fo "$p net=$net drv=$drv ($drvc) nterm=$nl hpwl=$hp wirelen=$wl"
}
close $fh; close $fo
foreach v {av_ss av_tt av_ff} { catch { report_constraint -view $v -drv_violation_type max_transition -all_violators > $R/native_tran_$v.txt } }
catch { report_net -net FE_OFN19232_n > $R/net_FE_OFN19232_n.txt }
puts "PROBE_DONE"
exit
