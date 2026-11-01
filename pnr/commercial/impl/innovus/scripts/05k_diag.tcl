# 05k_diag.tcl -- why do the new b5k views (av_ff_*, av_tt_max) not see the clk_io network latency 3.295?  env FROM_LABEL (default 05k_mc)
source [file join [file dirname [file normalize [info script]]] common.tcl]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "05k_mc"}]
restore_stage $FL
common_settings
set R $RUN/reports
foreach v [all_analysis_views] {
  puts "DIAG view $v"
  catch { report_clocks -view $v > $R/diag_clocks_$v.txt }
  catch { report_clock_timing -type latency -clock clk_io -view $v > $R/diag_cliolat_$v.txt }
  catch { report_timing -view $v -early -from [get_ports {axi_rdata_i[1]}] -path_type full_clock -max_paths 1 > $R/diag_hold_$v.txt }
}
catch { get_db analysis_views .name } e; puts "DIAG views: $e"
foreach v [all_analysis_views] { catch { puts "DIAG latency_file $v: [get_db [get_db analysis_views -if {.name==$v}] .constraint_mode.name]" } }
exit
