# b8_drc_probe.tcl -- view-only: locate the single native check_routes DRC of the b8 06_eco / 06b_eco labels (met3 or above; the KLayout deck reports 0).  Never saves.
source [file join [file dirname [info script]] b8_common.tcl]
view_stage 06b_eco
redirect -file $RUN/reports/probe_check_routes.txt { check_routes -drc true -antenna false -open_net false -report_all_open_nets false }
set eds [get_drc_error_data -all]
foreach_in_collection ed $eds {
  puts "PROBE_DATA [get_object_name $ed] name=[get_attribute $ed name]"
  catch { foreach_in_collection e [get_drc_errors -error_data $ed] { puts "PROBE_ERR type=[get_attribute $e type_name] bbox=[get_attribute $e bbox] layer=[get_attribute $e layer_name]" } } m
  puts "PROBE_ERRS_MSG $m"
}
puts "PROBE_DONE"
exit
