# b6_03a_mcmmtest.tcl -- quick MCMM sanity test on the 02_pdn block (NOT saved): scenarios, PVT-to-library mapping, per-scenario worst paths with the libraries named.
source [file join [file dirname [info script]] b6_common.tcl]
view_stage 02_pdn
source [file join $SCRIPTDIR b6_setup_mcmm.tcl]
catch {check_timing}
foreach s {func_ss func_tt func_ff} {
  current_scenario $s
  puts "=== $s"
  catch {report_pvt}
  catch {report_timing -scenarios $s -delay_type max -max_paths 1 -significant_digits 3}
  catch {report_timing -scenarios $s -delay_type min -max_paths 1 -significant_digits 3}
}
puts "STAGE_SAVED: test-not-saved"
exit
