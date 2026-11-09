source [file join [file dirname [info script]] b8_common.tcl]
view_stage 06f_eco
source [file join $SCRIPTDIR reload.tcl]
set fh [open $RUN/reports/f6_moves.txt r]; set mv {}; while {[gets $fh l] >= 0} { lappend mv [lindex $l 1] }; close $fh
foreach sc {func_ff func_tt} {
  set ps [get_timing_paths -scenarios $sc -delay_type min -max_paths 12 -nworst 1]
  foreach_in_collection p $ps {
    set s [get_object_name [get_attribute $p startpoint]]; set e [get_object_name [get_attribute $p endpoint]]
    set es [string map {/D /CLK} $e]
    puts "S_PATH $sc slack=[get_attribute $p slack] start=$s end=$e start_moved=[expr {[lsearch $mv $s/CLK]>=0}] end_moved=[expr {[lsearch $mv $es]>=0}]"
  }
}
puts "S_DONE"
exit
