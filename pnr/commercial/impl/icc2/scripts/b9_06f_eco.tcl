# b9_06f_eco.tcl -- ICC2 b9 round 3d: max-fanout without cloning.  The 177 max-fanout violators (set_max_fanout 16) are CTS leaf buffers driving 17..25 flop clock pins.  Cloning them (b9_06c experiment 1)
#   moved the sinks onto a lightly loaded clone and broke the CTS balance (ff hold +0.011 -> -0.112 ns).  This round moves ONLY the excess sinks of the violators with the smallest excess (B9F_MAXEXC, default 1) onto
#   the nearest SIBLING leaf buffer that still has spare fanout (<= 15 sinks, B9F_DIST um, default 80), so the sink keeps a leaf buffer of the same level / drive and the sibling groups are CTS-balanced already.
#   Input label 06e_eco, output 06f_eco (06e_eco is kept).  The chain keeps 06e_eco as the finish base unless 06f_eco passes (hard DRC 0, shorts 0, opens 0, hold / setup not worse).
source [file join [file dirname [info script]] b8_common.tcl]
set t0 [clock seconds]
open_stage 06e_eco 06f_eco
set_app_options -name route.detail.drc_convergence_effort_level -value high
catch {set_app_options -name route.detail.repair_shorts_over_macros_effort_level -value high}
set_app_options -name route.detail.optimize_wire_via_effort_level -value medium
set_app_options -name route.detail.optimize_partition_size_for_drc -value true
source [file join $SCRIPTDIR reload.tcl]
source [file join $SCRIPTDIR antenna_rules.tcl]
set_app_options -name route.detail.antenna -value true
set_app_options -name route.detail.antenna_fixing_preference -value use_diodes
set_app_options -name route.detail.diode_libcell_names -value {sky130_fd_sc_hd__diode_2}
set_app_options -name route.detail.report_soft_drc_separately -value true
set R $RUN/reports
proc chkq {tag} {
  global RUN
  redirect -file $RUN/reports/d9_checks_$tag.txt { check_routes -drc true -antenna true -open_net true }
  redirect -file $RUN/reports/d9_lvs_$tag.txt { check_lvs -checks all -max_errors 0 }
  set hard -1; set soft -1; set o -1; set s 0
  set fh [open $RUN/reports/d9_checks_$tag.txt r]; while {[gets $fh l] >= 0} { regexp {TOTAL VIOLATIONS =\s*(\d+)} $l -> hard; regexp {TOTAL SOFT VIOLATIONS =\s*(\d+)} $l -> soft } ; close $fh
  set fh [open $RUN/reports/d9_lvs_$tag.txt r]; while {[gets $fh l] >= 0} { if {[string match "*Detected short violation*" $l] && ![string match "*Blockage*" $l]} { incr s }; regexp {Total number of open nets is (\d+)} $l -> o } ; close $fh
  puts "D9_CHECK $tag: hard=$hard soft=$soft shorts=$s opens=$o"
  return [list $hard $soft $s $o]
}
chkq 0
foreach s [get_object_name [all_scenarios]] { foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "D9_TIMING_PRE $s $nm worst_slack=[get_attribute $p slack]" } } }
proc read_list {f} { set fh [open $f r]; set L {}; while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne ""} { lappend L $l } }; close $fh; return $L }
proc ctrxy {obj} { set bb [get_attribute $obj bbox]; return [list [expr {([lindex $bb 0 0]+[lindex $bb 1 0])/2.0}] [expr {([lindex $bb 0 1]+[lindex $bb 1 1])/2.0}]] }
set MAXEXC [expr {[info exists ::env(B9F_MAXEXC)] ? $::env(B9F_MAXEXC) : 1}]
set DIST   [expr {[info exists ::env(B9F_DIST)] ? $::env(B9F_DIST) : 80.0}]
# violators (pin fanout), spare siblings
array set viol {}
foreach l [read_list $RUN/eco_in/fanout_viol.txt] { lassign $l pn fo; set viol([string range $pn 0 [expr {[string last / $pn]-1}]]) $fo }
set spare {}   ;# list of {cellname fanout x y netname}
foreach_in_collection c [get_cells -quiet *ZCTSBUF_*] {
  set cn [get_object_name $c]
  if {[info exists viol($cn)]} continue
  set op [get_pins -quiet "$cn/X"]; if {[sizeof_collection $op] != 1} continue
  set net [get_nets -quiet -of_objects $op]; if {[sizeof_collection $net] != 1} continue
  set sk [get_pins -quiet -of_objects $net -filter "direction==in"]
  set n [sizeof_collection $sk]
  if {$n < 1 || $n > 15} continue
  # leaf only: every sink is a sequential / macro clock pin (no buffer sinks)
  set leaf 1; foreach_in_collection s $sk { if {[string match *ZCTSBUF* [get_object_name $s]] || [string match *HFS* [get_object_name $s]]} { set leaf 0; break } }
  if {!$leaf} continue
  lassign [ctrxy $c] x y
  lappend spare [list $cn $n $x $y [get_object_name $net]]
}
puts "F6_SPARE siblings: [llength $spare]"
set cand {}
foreach cn [array names viol] {
  if {$viol($cn) - 16 > $MAXEXC} continue
  lappend cand [list $viol($cn) $cn]
}
set cand [lsort -integer -index 0 $cand]
puts "F6_CANDIDATES (excess <= $MAXEXC): [llength $cand]"
set moved 0; set fixedbufs 0; set skipped 0
set mvlog [open $R/f6_moves.txt w]
foreach cc $cand {
  lassign $cc fo cn
  set op [get_pins "$cn/X"]; set net [get_nets -of_objects $op]
  set sk [get_pins -of_objects $net -filter "direction==in"]
  set need [expr {[sizeof_collection $sk] - 16}]
  # best (sink, sibling) pairs by distance
  set pairs {}
  foreach_in_collection s $sk {
    if {![string match */CLK [get_object_name $s]]} continue   ;# only flop CLK pins move (a buffer input must never be re-hooked)
    lassign [ctrxy $s] sx sy
    set bi -1; set bd 1e9; set i 0
    foreach sp $spare { lassign $sp scn sn sxx syy snet; if {$sn < 16} { set d [expr {abs($sxx-$sx)+abs($syy-$sy)}]; if {$d < $bd} { set bd $d; set bi $i } }; incr i }
    if {$bi >= 0} { lappend pairs [list $bd [get_object_name $s] $bi] }
  }
  set pairs [lsort -real -index 0 $pairs]
  set done 0
  foreach pr $pairs {
    if {$done >= $need} break
    lassign $pr bd sname bi
    if {$bd > $DIST} break
    set sp [lindex $spare $bi]; lassign $sp scn sn sxx syy snet
    if {$sn >= 16} continue
    set rc [catch { disconnect_net -net $net [get_pins $sname]; connect_net -net [get_nets $snet] [get_pins $sname] } msg]
    if {$rc} { puts "F6_FAIL $cn $sname: $msg"; continue }
    lset spare $bi 1 [expr {$sn+1}]
    puts $mvlog "$cn $sname -> $scn dist=[format %.1f $bd] fanout_old=$fo"
    incr moved; incr done
  }
  if {$done >= $need} { incr fixedbufs } else { incr skipped; if {$done > 0} { puts "F6_PARTIAL $cn: moved $done of $need" } }
}
close $mvlog
puts "F6_RESULT: moved sinks=$moved, buffers now <=16: $fixedbufs, buffers not fixed: $skipped"
set rc [catch { route_eco -max_detail_route_iterations 60 } m]; puts "F6_ROUTE_ECO rc=$rc $m"
set r [chkq 1]
for {set i 2} {$i <= 4} {incr i} {
  if {[lindex $r 0] == 0 && [lindex $r 2] == 0 && [lindex $r 3] == 0} break
  route_detail -incremental true -initial_drc_from_input true -max_number_iterations 60
  set r [chkq $i]
}
catch { open_drc_error_data -name zroute.err } m
catch { foreach_in_collection e [get_drc_errors -error_data zroute.err] { puts "D9_DRC [get_attribute $e type_name] [get_attribute $e bbox]" } } m
redirect -file $R/d9_pg_conn.txt { check_pg_connectivity -check_std_cell_pins none }
redirect -file $R/d9_pg_drc.txt { check_pg_drc }
catch { write_def $RUN/out/pre_ant_06f.def }
foreach s [get_object_name [all_scenarios]] { foreach {dt nm} {max SETUP min HOLD} { catch { set p [get_timing_paths -scenarios $s -delay_type $dt -max_paths 1]; puts "D9_TIMING $s $nm worst_slack=[get_attribute $p slack]" } } }
save_stage 06f_eco
stage_time eco9f $t0
exit
