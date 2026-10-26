# judge.tcl -- neutral PrimeTime judge, one (arm, RC corner, lib corner) per pt_shell.  Driven by environment:
#   J_ROOT repo root     J_NETLIST routed netlist     J_SPEF SPEF snapshot (run-local copy)
#   J_RC nom|min|max     J_LIB tt|ss|ff               J_POWER 0|1 (PrimePower, vectorless)
#   J_SDC the shared SDC (md5 asserted below)         J_OUT output dir (== cwd)
# SAME settings for every arm: propagated clocks, no derate/OCV, SI off, CRPR on (PT default),
# read_parasitics -format spef with default coupling handling (coupling lumped to ground, factor 1.0).
set ROOT $::env(J_ROOT)
set DB   $ROOT/pnr/commercial/pdk/sky130/build/db
set EXPECT_SDC_MD5 3c69635042a9d65cb87e71a9db713e4e
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set SRAMDB sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db   ;# TT-only SRAM model at EVERY corner (bead o1i)
set lib $::env(J_LIB); set rc $::env(J_RC); set dopower $::env(J_POWER)

set fh [open metrics.tsv w]
proc m {k v} { global fh; puts $fh "$k\t$v"; flush $fh }
m pt_version [get_app_var sh_product_version]
m lib_corner $LIBN($lib)
m rc_corner $rc
m netlist $::env(J_NETLIST)
m spef $::env(J_SPEF)

set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
if {$dopower} { set_app_var power_enable_analysis true; set_app_var power_analysis_mode averaged }
set_app_var search_path [list $DB]
set_app_var link_path [list * $LIBN($lib).db $SRAMDB]
read_verilog $::env(J_NETLIST)
current_design rv32i_cpu_top
link_design
m leaf_cells [sizeof_collection [get_cells -hier -quiet *]]
m nets [sizeof_collection [get_nets -hier -quiet *]]
m nofunction_cells [sizeof_collection [get_cells -hier -quiet -filter "is_black_box==true"]]

# ---- constraints: the ONE shared SDC, md5 asserted
set md5 [lindex [exec md5sum $::env(J_SDC)] 0]
m sdc_md5 $md5
if {$md5 ne $EXPECT_SDC_MD5} { puts "FATAL: SDC md5 $md5 != $EXPECT_SDC_MD5"; m FATAL sdc_md5; close $fh; exit 3 }
read_sdc $::env(J_SDC)
set_propagated_clock [all_clocks]

# ---- parasitics: the arm's StarRC (or OpenRCX) SPEF
read_parasitics -format spef $::env(J_SPEF)
update_timing
redirect -file annot.txt { report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets -max_nets 30 }
# clock-network nets: annotation must be complete
set clkpins [all_fanout -flat -clock_tree]
set clknets [get_nets -quiet -of_objects $clkpins]
m clock_nets [sizeof_collection $clknets]
redirect -file annot_clock.txt { report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets -list_not_annotated -max_nets 30 $clknets }

redirect -file check_timing.txt { check_timing -verbose }
redirect -file global_timing.txt { report_global_timing }

# ---- worst paths and full-precision WNS/TNS/violating endpoints (unique endpoints, worst slack per endpoint)
proc endpoint_stats {dt} {
  set vp [get_timing_paths -delay_type $dt -max_paths 1000000 -nworst 1 -slack_lesser_than 0]
  array unset worst
  foreach_in_collection p $vp {
    set e [get_object_name [get_attribute $p endpoint]]
    set s [get_attribute $p slack]
    if {![info exists worst($e)] || $s < $worst($e)} { set worst($e) $s }
  }
  set tns 0.0; set n 0
  foreach e [array names worst] { set tns [expr {$tns + $worst($e)}]; incr n }
  return [list $tns $n]
}
foreach {dt tag} {max setup min hold} {
  set wp [get_timing_paths -delay_type $dt -max_paths 1]
  m ${tag}_wns [get_attribute $wp slack]
  m ${tag}_worst_start [get_object_name [get_attribute $wp startpoint]]
  m ${tag}_worst_end   [get_object_name [get_attribute $wp endpoint]]
  m ${tag}_worst_group [get_attribute [get_attribute $wp path_group] full_name]
  lassign [endpoint_stats $dt] tns n
  m ${tag}_tns $tns
  m ${tag}_viol $n
  redirect -file worst_${tag}.txt { report_timing -delay_type $dt -max_paths 1 -path_type full_clock_expanded -input_pins -transition_time -capacitance -nets }
}
redirect -file constraint_drv.txt { report_constraint -all_violators -max_transition -max_capacitance -max_fanout -nosplit }
redirect -file qor.txt { report_qor }

# ---- PrimePower, vectorless.  Two activity assumptions, both written out explicitly and identical for every arm:
#   A "pt_default": PT defaults = toggle 0.1 / static prob 0.5 on primary inputs, activity PROPAGATED through registers and logic.
#   B "matched":    A plus toggle 0.1 / prob 0.5 asserted on every register output.  OpenSTA's default (what the OpenROAD native
#                   number uses) does not derive register-output activity from D, and B reproduces OpenSTA's native
#                   comb/clock/macro split to within ~2 % (see reports/pt_judge_summary.md, scripts/power_diag.tcl).  B is the headline.
if {$dopower} {
  set_app_var power_default_toggle_rate 0.1
  set_app_var power_default_static_probability 0.5
  m power_toggle_rate [get_app_var power_default_toggle_rate]
  m power_static_prob [get_app_var power_default_static_probability]
  m power_toggle_ref  [get_app_var power_default_toggle_rate_reference_clock]
  update_power
  redirect -file power_A.txt { report_power -nosplit }
  set rq [all_registers -output_pins]
  m power_B_register_output_pins [sizeof_collection $rq]
  set_switching_activity -toggle_rate 0.1 -static_probability 0.5 -base_clock clk_i $rq
  update_power
  redirect -file power_B.txt { report_power -nosplit }
  redirect -file power_B_hier.txt { report_power -nosplit -hierarchy -levels 1 }
}
close $fh
exit
