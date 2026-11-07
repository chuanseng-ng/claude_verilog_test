# b6_probe.tcl -- probe on the 02_pdn db: how to switch the per-view latency files post-CTS (update_analysis_view) and whether clk_io 3.295 reaches every view.
source [file join [file dirname [file normalize [info script]]] common.tcl]
restore_stage 02_pdn
common_settings
puts "PROBE views: [all_analysis_views]"
catch { help update_analysis_view } e; puts "PROBE help: [string range $e 0 800]"
set LATF $REPO/pnr/commercial/constraints/sky130_cpu_innovus_b5k_latency.sdc
proc spot {tag} {
  foreach v [all_analysis_views] {
    set md [expr {[lsearch [all_hold_analysis_views] $v] >= 0 ? "-early" : "-late"}]
    if {[catch { eval report_timing -view $v -from [get_ports {axi_rdata_i[10]}] $md -path_type full_clock -max_paths 1 > $::RUN/reports/probe_${tag}_$v.txt } e]} { puts "PROBE rt fail $v: $e"; continue }
    set fh [open $::RUN/reports/probe_${tag}_$v.txt r]; set s [read $fh]; close $fh
    set lat "?"; foreach l [split $s "\n"] { if {[regexp -nocase {(insertion delay|clk_io).*$} $l] && [regexp -nocase {latency|insertion} $l]} { puts "PROBE($tag,$v): $l" } }
  }
}
spot before
update_constraint_mode -name func -sdc_files [list $REPO/pnr/commercial/constraints/sky130_cpu_innovus_b5k_post.sdc]
spot after_ucm
foreach v [all_analysis_views] { set rc [catch { update_analysis_view -name $v -latency_file $LATF } e]; puts "PROBE update_analysis_view $v rc=$rc $e" }
spot after_uav
set_interactive_constraint_modes func
set_clock_latency 3.295 [get_clocks clk_io]
set_interactive_constraint_modes {}
spot after_scl
foreach v [all_analysis_views] { catch { report_clocks -view $v > $RUN/reports/probe_clocks_$v.txt } }
exit
