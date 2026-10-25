
# [B4b-flat] FLAT compare instead of Genus' run_hier_compare: no module-boundary constants/equivalences are extracted, so every flop and
# output of the whole design is compared in one model.  Same mapping file and flatten options as Genus.
set_system_mode lec
echo "B4B_FLAT_UNMAPPED_BEGIN"
report_unmapped_points -summary
report_unmapped_points -notmapped
report_unmapped_points -extra
report_unmapped_points -unreachable
echo "B4B_FLAT_UNMAPPED_END"
add_compared_points -all
compare
report_compare_data -class nonequivalent -class abort -class notcompared
report_verification -verbose
report_statistics
if {[get_compare_points -NONequivalent -count] > 0 || [get_compare_points -abort -count] > 0 || [get_compare_points -unknown -count] > 0} {
    puts "B4B_FLAT_VERDICT: NOT_EQUIVALENT"
    write_compared_points noneq.flat.tcl -class noneq -tclmode -replace
    analyze_nonequivalent -source_diagnosis
    report_nonequivalent_analysis > noneq.flat.source_diag.rpt
    report_test_vector -noneq > noneq.flat.test_vector.rpt
} else { puts "B4B_FLAT_VERDICT: EQUIVALENT" }
puts "No of compare points = [get_compare_points -count]"
puts "No of diff points    = [get_compare_points -NONequivalent -count]"
puts "No of abort points   = [get_compare_points -abort -count]"
puts "No of unknown points = [get_compare_points -unknown -count]"
vpxmode   ;# [B4b-flat] leave tclmode: `exit -f` is only valid in the native mode (the Genus do-file does the same)
exit -f
