# diag_gap.tcl -- DIAGNOSTIC PrimeTime run for the Innovus b5g judge-vs-native gap (one variable per call).
# env: G_ROOT G_NETLIST G_SPEF G_SDC G_LIB(tt) G_OUT G_TOGGLE(0.1) G_POWER(0|1) G_ASSERT_MD5(optional)
set ROOT $::env(G_ROOT)
set DB $ROOT/pnr/commercial/pdk/sky130/build/db
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set lib [expr {[info exists ::env(G_LIB)] ? $::env(G_LIB) : "tt"}]
set fh [open metrics.tsv w]
proc m {k v} { global fh; puts $fh "$k\t$v"; flush $fh }
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
set dopower [expr {[info exists ::env(G_POWER)] ? $::env(G_POWER) : 0}]
if {$dopower} { set_app_var power_enable_analysis true; set_app_var power_analysis_mode averaged }
set_app_var search_path [list $DB]
set_app_var link_path [list * $LIBN($lib).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(G_NETLIST); current_design rv32i_cpu_top; link_design
set md5 [lindex [exec md5sum $::env(G_SDC)] 0]
m sdc $::env(G_SDC); m sdc_md5 $md5; m spef $::env(G_SPEF)
read_sdc $::env(G_SDC)
if {[info exists ::env(G_PROP_ALL)] && $::env(G_PROP_ALL)} { set_propagated_clock [all_clocks] } else { set_propagated_clock [get_clocks clk_i] }
if {[info exists ::env(G_EXTRA_TCL)] && $::env(G_EXTRA_TCL) ne ""} { source $::env(G_EXTRA_TCL) }
read_parasitics -format spef $::env(G_SPEF)
update_timing
redirect -file annot.txt { report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets -max_nets 10 }
redirect -file clock_latency.txt { report_clock_timing -type latency -clock clk_i -nworst 1 -verbose }
redirect -file clock_skew.txt { report_clock_timing -type skew -clock clk_i }

proc stats {dt from to} {
  set vp [get_timing_paths -delay_type $dt -max_paths 1000000 -nworst 1 -slack_lesser_than 1000 {*}[expr {$from eq "" ? {} : [list -from $from]}] {*}[expr {$to eq "" ? {} : [list -to $to]}]]
  array unset worst
  foreach_in_collection p $vp {
    set e [get_object_name [get_attribute $p endpoint]]
    set s [get_attribute $p slack]
    if {$s eq "INFINITY" || $s eq "" } continue
    if {![info exists worst($e)] || $s < $worst($e)} { set worst($e) $s }
  }
  set wns 1e9; set tns 0.0; set n 0
  foreach e [array names worst] { if {$worst($e) < $wns} { set wns $worst($e) }; if {$worst($e) < 0} { set tns [expr {$tns + $worst($e)}]; incr n } }
  return [list $wns $tns $n [array size worst]]
}
set regs [all_registers -clock_pins]
set regd [all_registers -data_pins]
foreach {dt tag} {max setup min hold} {
  lassign [stats $dt "" ""] w t n tot;           m ${tag}_all_wns $w; m ${tag}_all_tns $t; m ${tag}_all_viol $n; m ${tag}_all_ep $tot
  lassign [stats $dt [all_inputs] $regd] w t n tot; m ${tag}_in2reg_wns $w; m ${tag}_in2reg_tns $t; m ${tag}_in2reg_viol $n; m ${tag}_in2reg_ep $tot
  lassign [stats $dt $regs [all_outputs]] w t n tot; m ${tag}_reg2out_wns $w; m ${tag}_reg2out_tns $t; m ${tag}_reg2out_viol $n; m ${tag}_reg2out_ep $tot
  lassign [stats $dt $regs $regd] w t n tot;     m ${tag}_reg2reg_wns $w; m ${tag}_reg2reg_tns $t; m ${tag}_reg2reg_viol $n; m ${tag}_reg2reg_ep $tot
  lassign [stats $dt [all_inputs] [all_outputs]] w t n tot; m ${tag}_in2out_wns $w; m ${tag}_in2out_viol $n; m ${tag}_in2out_ep $tot
  redirect -file worst_${tag}.txt { report_timing -delay_type $dt -max_paths 1 -path_type full_clock_expanded -input_pins -transition_time -capacitance -nets }
  redirect -file worst_${tag}_in2reg.txt { report_timing -delay_type $dt -from [all_inputs] -to $regd -max_paths 1 -path_type full_clock_expanded -input_pins -transition_time -nets }
  redirect -file worst_${tag}_reg2out.txt { report_timing -delay_type $dt -from $regs -to [all_outputs] -max_paths 1 -path_type full_clock_expanded -input_pins -transition_time -nets }
  redirect -file worst_${tag}_reg2reg.txt { report_timing -delay_type $dt -from $regs -to $regd -max_paths 1 -path_type full_clock_expanded -input_pins -transition_time -nets }
}
# per-endpoint worst slack dump (every endpoint) for later joins with native
foreach {dt tag} {max setup min hold} {
  set f [open ep_${tag}.tsv w]
  set vp [get_timing_paths -delay_type $dt -max_paths 1000000 -nworst 1 -slack_lesser_than 1000]
  array unset worst; array unset sp
  foreach_in_collection p $vp {
    set e [get_object_name [get_attribute $p endpoint]]; set s [get_attribute $p slack]
    if {$s eq "INFINITY" || $s eq ""} continue
    if {![info exists worst($e)] || $s < $worst($e)} { set worst($e) $s; set sp($e) [get_object_name [get_attribute $p startpoint]] }
  }
  foreach e [array names worst] { puts $f "$e\t$sp($e)\t$worst($e)" }
  close $f
}
if {$dopower} {
  set tg [expr {[info exists ::env(G_TOGGLE)] ? $::env(G_TOGGLE) : 0.1}]
  set_app_var power_default_toggle_rate $tg
  set_app_var power_default_static_probability 0.5
  m power_toggle_rate $tg
  update_power
  redirect -file power_A.txt { report_power -nosplit }
  set rq [all_registers -output_pins]
  set_switching_activity -toggle_rate $tg -static_probability 0.5 -base_clock clk_i $rq
  update_power
  redirect -file power_B.txt { report_power -nosplit }
}
close $fh
exit
