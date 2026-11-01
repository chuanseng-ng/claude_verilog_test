# 05i_diag2.tcl -- B5i: why does ICC2 not flag met4 spacing 0.38 to a 3.1 um PG strap?  read-only.
source [file join [file dirname [info script]] common.tcl]
view_stage 05y_repair
puts "DIAG2 met4 layer attributes:"
foreach a [list_attributes -class layer -application] { }
catch { report_attributes -class layer -application [get_layers met4] } e
puts "DIAG2 spacing-ish attrs:"
foreach a [lsort [get_attribute [get_layers met4] -quiet attribute_names]] { puts "  $a" }
foreach a {min_spacing min_width pitch fat_table_threshold fat_table_parallel_length fat_table_spacing} {
  catch {puts "  $a = [get_attribute [get_layers met4] $a]"}
}
set box {{2746.0 1402.0} {2748.0 1430.0}}
puts "DIAG2 shapes near strap/signal marker:"
foreach_in_collection s [get_shapes -quiet -intersect $box] {
  puts "  [get_attribute $s layer_name] net=[get_attribute [get_attribute $s owner] full_name] type=[get_attribute $s shape_type] use=[get_attribute -quiet $s shape_use] w=[get_attribute -quiet $s width] bbox=[get_attribute $s bbox]"
}
puts "DIAG2 check_routes in box:"
catch { check_routes -drc true -open_net false -antenna false -box {{2740.0 1395.0} {2750.0 1435.0}} } e
puts $e
puts "DIAG2 app options route.*spacing*/*wide*/*fat*/*pg*:"
foreach o [get_app_options route.*] { set n [get_attribute $o name]; if {[regexp -nocase {spac|wide|fat|pg|drc} $n]} { puts "  $n = [get_attribute $o value]" } }
exit
