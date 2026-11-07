# pt_synth_probe.tcl -- Step 1 of the v2 synthesis task: time the three SYNTHESIS netlists (Yosys/ABC, DC-NXT v1, Genus v1)
# at nom_tt and nom_ss with the SAME treatment: ideal clock, NO parasitics (no wire load, no SPEF), shared SDC (md5 asserted).
# One pt_shell session loops over all (netlist, lib) pairs.  env: ROOT OUT   NETLISTS="tag=path tag=path ..."  LIBS="tt ss"
set ROOT $::env(ROOT); set OUT $::env(OUT)
set DB $ROOT/pnr/commercial/pdk/sky130/build/db
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set SRAMDB sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
set SDC $ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc
set md5 [lindex [exec md5sum $SDC] 0]
if {$md5 ne "3c69635042a9d65cb87e71a9db713e4e"} { puts "FATAL sdc md5 $md5"; exit 3 }
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
set_app_var search_path [list $DB]
file mkdir $OUT
set fh [open $OUT/probe_metrics.tsv w]
puts $fh "arm\tlib\tleaf_cells\tsetup_wns\tsetup_tns\tsetup_viol\tr2r_wns\tr2r_tns\tr2r_viol\tr2r_endpoints\thold_wns\tworst_start\tworst_end"
flush $fh
proc ep_stats {dt} {
  set vp [get_timing_paths -delay_type $dt -max_paths 1000000 -nworst 1 -slack_lesser_than 0]
  array unset worst
  foreach_in_collection p $vp {
    set e [get_object_name [get_attribute $p endpoint]]; set s [get_attribute $p slack]
    if {![info exists worst($e)] || $s < $worst($e)} { set worst($e) $s }
  }
  set tns 0.0; set n 0
  foreach e [array names worst] { set tns [expr {$tns + $worst($e)}]; incr n }
  return [list $tns $n]
}
proc r2r_stats {dt} {
  set vp [get_timing_paths -delay_type $dt -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1000000 -nworst 1]
  array unset worst
  foreach_in_collection p $vp {
    set e [get_object_name [get_attribute $p endpoint]]; set sl [get_attribute $p slack]
    if {![info exists worst($e)] || $sl < $worst($e)} { set worst($e) $sl }
  }
  set wns 1e9; set tns 0.0; set n 0
  foreach e [array names worst] { if {$worst($e) < $wns} { set wns $worst($e) }; if {$worst($e) < 0} { set tns [expr {$tns + $worst($e)}]; incr n } }
  return [list $wns $tns $n [array size worst]]
}
foreach spec $::env(NETLISTS) {
  lassign [split $spec =] arm nl
  foreach lib $::env(LIBS) {
    set tag ${arm}_$lib
    puts "=== $tag : $nl"
    if {[catch {
      remove_design -all
      set_app_var link_path [list * $LIBN($lib).db $SRAMDB]
      read_verilog $nl
      current_design rv32i_cpu_top
      link_design
      read_sdc $SDC     ;# clocks stay IDEAL (no set_propagated_clock), no read_parasitics
      update_timing
      set wp [get_timing_paths -delay_type max -max_paths 1]
      set wns [get_attribute $wp slack]
      lassign [ep_stats max] tns n
      lassign [r2r_stats max] rw rt rn rtot
      set hp [get_timing_paths -delay_type min -max_paths 1]
      set hw [get_attribute $hp slack]
      puts $fh "$arm\t$lib\t[sizeof_collection [get_cells -hier -quiet -filter {is_hierarchical==false}]]\t$wns\t$tns\t$n\t$rw\t$rt\t$rn\t$rtot\t$hw\t[get_object_name [get_attribute $wp startpoint]]\t[get_object_name [get_attribute $wp endpoint]]"
      flush $fh
      redirect -file $OUT/worst_$tag.txt { report_timing -delay_type max -max_paths 1 -path_type full_clock_expanded -input_pins -transition_time }
      redirect -file $OUT/worst_r2r_$tag.txt { report_timing -delay_type max -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -input_pins }
      redirect -file $OUT/check_timing_$tag.txt { check_timing -verbose }
    } err]} { puts "PROBE_FAILED $tag: $err"; puts $fh "$arm\t$lib\tFAILED\t$err" ; flush $fh }
  }
}
close $fh
puts "PROBE_DONE"
exit
