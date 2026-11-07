# icc2_pwell_probe.tcl -- measurement only: re-run check_pg_drc on a COPY of the ICC2 library and list where the "shorts on pwell" are.
# env: REPO PDKDIR RUN (RUN = directory holding a copy of rv32i.dlib) PROBE_LABEL (default 06_finish)
source $::env(REPO)/pnr/commercial/impl/icc2/scripts/common.tcl
set lbl 06_finish
if {[info exists ::env(PROBE_LABEL)]} { set lbl $::env(PROBE_LABEL) }
view_stage $lbl
puts "PROBE_LABEL: $lbl"
redirect -variable out { check_pg_drc }
puts $out
catch {open_drc_error_data DRC_report_by_check_pg_drc} r1
puts "OPEN: $r1"
catch {report_drc_errors -error_data DRC_report_by_check_pg_drc} r2
puts "REPORT: $r2"
set errs [get_drc_errors -quiet -error_data DRC_report_by_check_pg_drc]
puts "N_ERRORS: [sizeof_collection $errs]"
set k 0
foreach_in_collection e $errs {
  incr k
  set bb [get_attribute $e bbox]
  set objs [get_attribute $e objects]
  set d {}
  catch {
    foreach_in_collection o $objs {
      set oc [get_attribute $o object_class]
      set nm ""
      catch {set nm [get_attribute $o full_name]}
      set nt ""
      catch {set nt [get_attribute $o net_name]}
      set ly ""
      catch {set ly [get_attribute $o layer_name]}
      lappend d "$oc:$nm:net=$nt:lay=$ly"
    }
  } er
  puts "ERR $k | $bb | [join $d { ; }] | $er"
}
exit
