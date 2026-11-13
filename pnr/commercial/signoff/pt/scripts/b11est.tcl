# b11est.tcl -- PrimeTime WHAT-IF for the Innovus b11 slew fix (2026-11-13): load the b10 netlist + b10 StarRC SPEF of one (rc, lib) corner with the shared SDC (as judge.tcl),
# then for each variant resize the three b10 repeaters (B10N1, u_core/B10N2, u_core/B10N3) with size_cell (the SPEF wire RC is unchanged, only the pin caps / drive change; a moved or added cell is NOT modelled here)
# and report the transition at every pin of the three nets, the repeater slacks and the full max_transition violator count.  View-only: nothing is written but reports under J_OUT.
# env: J_ROOT J_NETLIST J_SPEF J_RC J_LIB J_SDC J_OUT ; VARIANTS="buf_6 buf_8 buf_12 buf_16" (cell suffix applied to all three) or "N1:buf_12,N2:buf_16,N3:buf_6" per-net
set ROOT $::env(J_ROOT)
set DB $ROOT/pnr/commercial/pdk/sky130/build/db
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set lib $::env(J_LIB)
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
set_app_var search_path [list $DB]
set_app_var link_path [list * $LIBN($lib).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST)
current_design rv32i_cpu_top
link_design
read_sdc $::env(J_SDC)
set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
set REP {B10N1 u_core/B10N2 u_core/B10N3}
set PINS {}
foreach r $REP {
  foreach pn [get_pins -of_objects [get_cells $r]] { lappend PINS [get_object_name $pn] }
  set onet [get_nets -of_objects [get_pins $r/X]]
  foreach pn [get_pins -quiet -leaf -of_objects $onet] { lappend PINS [get_object_name $pn] }
  set inet [get_nets -of_objects [get_pins $r/A]]
  foreach pn [get_pins -quiet -leaf -of_objects $inet] { lappend PINS [get_object_name $pn] }
}
set PINS [lsort -unique $PINS]
proc tr {p} {
  set o [get_pins $p]; set m 0.0
  foreach a {actual_rise_transition_max actual_fall_transition_max} { set v [get_attribute -quiet $o $a]; foreach x $v { if {$x ne "" && $x > $m} { set m $x } } }
  return $m
}
proc count_viol {f} { set n 0; set fh [open $f r]; set in 0; while {[gets $fh l] >= 0} { if {[string match "*max_transition*" $l]} { set in 1 }; if {[string match "*max_fanout*" $l] || [string match "*max_capacitance*" $l]} { set in 0 }; if {$in && [string match "*VIOLATED*" $l]} { incr n } }; close $fh; return $n }
set fo [open $::env(J_OUT)/b11est.txt w]
puts $fo "corner rc=$::env(J_RC) lib=$lib"
foreach v $::env(VARIANTS) {
  array unset sz
  if {[string match "*:*" $v]} { foreach kv [split $v ,] { lassign [split $kv :] k c; set sz($k) $c } } else { foreach k {N1 N2 N3} { set sz($k) $v } }
  foreach {k r} {N1 B10N1 N2 u_core/B10N2 N3 u_core/B10N3} {
    set cur [get_attribute [get_cells $r] ref_name]
    if {$cur ne "sky130_fd_sc_hd__$sz($k)"} { size_cell [get_cells $r] sky130_fd_sc_hd__$sz($k) }
  }
  update_timing
  puts $fo "=== variant $v : [lmap k {N1 N2 N3} {set x "$k=$sz($k)"}]"
  foreach p $PINS {
    set t [tr $p]
    puts $fo [format "  %-50s tran %.4f%s" $p $t [expr {$t > 0.5 ? "  >0.5 VIOL" : ""}]]
  }
  foreach r $REP {
    foreach dt {max min} {
      set wp [get_timing_paths -through [get_pins $r/X] -delay_type $dt -max_paths 1]
      if {[sizeof_collection $wp]} { puts $fo [format "  slack_%s through %s = %.4f" $dt $r [get_attribute $wp slack]] }
    }
  }
  foreach dt {max min} { set wp [get_timing_paths -delay_type $dt -max_paths 1]; puts $fo [format "  global_%s_wns %.4f" $dt [get_attribute $wp slack]] }
  set f $::env(J_OUT)/viol_[string map {: _ , _} $v].txt
  redirect -file $f { report_constraint -all_violators -max_transition -nosplit }
  puts $fo "  MAXTRAN_VIOLATOR_PINS [count_viol $f]"
  flush $fo
}
close $fo
exit
