# b9m_probe.tcl -- VIEW-ONLY probe of the b8 final pre-fill db (08b_eco): how does Innovus (av_ss, rc_max) see the apb_paddr_i -> apb_prdata_o_reg paths that PT own max_ss reports at -0.112 ns,
#   and which native max-transition violators exist.  Never saves.  env FROM_LABEL (default 08b_eco).
source [file join [file dirname [file normalize [info script]]] common.tcl]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "08b_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports/b9probe; file mkdir $R
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
extractRC
foreach v [all_analysis_views] { puts "VIEW $v" }
report_timing -view av_ss -from [get_ports {apb_paddr_i[*]}] -to [get_pins {apb_prdata_o_reg*/D}] -max_paths 6 -path_type summary > $R/apb_paths_ss.txt
report_timing -view av_ss -from [get_ports {apb_paddr_i[0]}] -to [get_pins {apb_prdata_o_reg[0]/D}] -max_paths 1 -path_type full_clock > $R/apb0_full_ss.txt
report_timing -view av_ss -from [get_ports {apb_paddr_i[*]}] -to [get_pins {apb_prdata_o_reg*/D}] -max_paths 1 > $R/apb_worst_ss.txt
report_timing -view av_ss -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 10 -path_type summary > $R/r2r_ss.txt
report_timing -view av_tt -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 10 -path_type summary > $R/r2r_tt.txt
report_timing -view av_ss -from [all_inputs] -max_paths 30 -path_type summary > $R/in_ss.txt
foreach v {av_ss av_tt} { catch { report_constraint -view $v -drv_violation_type max_transition -all_violators > $R/tran_$v.txt } }
puts "PROBE_DONE"
exit
