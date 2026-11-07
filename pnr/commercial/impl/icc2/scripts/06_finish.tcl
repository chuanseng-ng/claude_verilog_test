# 06_finish.tcl -- Step B5a stage 6: fillers/decaps, final checks and reports (tt, TLU+ nom), all outputs (verilog, def, gds, sdc, spef).
source [file join [file dirname [info script]] common.tcl]
set t0 [clock seconds]
set _fb 05y_repair
if {[info exists ::env(B5E_FINISH_BASE)]} { set _fb $::env(B5E_FINISH_BASE) }
puts "FINISH_BASE: $_fb"
open_stage $_fb 06_finish
source [file join $SCRIPTDIR reload.tcl]
set O $RUN/out
set R $RUN/reports
# ---- pre-filler reports (timing is unaffected by fillers); native RC
catch {redirect -file $R/final_timing_setup.txt { report_timing -delay_type max -max_paths 20 -nworst 1 -transition_time -capacitance -input_pins }}
catch {redirect -file $R/final_timing_hold.txt  { report_timing -delay_type min -max_paths 20 -nworst 1 }}
catch {redirect -file $R/final_qor.txt          { report_qor -summary; report_qor; report_qor -scenarios [all_scenarios] }}
catch {redirect -file $R/final_constraints.txt  { report_constraints -all_violators }}
catch {redirect -file $R/final_power.txt        { report_power }}
catch {redirect -file $R/final_clock_qor.txt    { catch {report_clock_qor -type summary}; catch {report_clock_qor -type latency} }}
catch {redirect -file $R/final_check_timing.txt { check_timing }}
# ---- precise final slacks (report_qor prints 2 digits)
foreach {dt tag} {max SETUP min HOLD} {
  set rc [catch {
    set ps [get_timing_paths -delay_type $dt -max_paths 1000 -slack_lesser_than 0.0]
    set tns 0.0; set n 0; set wns 0.0
    foreach_in_collection p $ps { set sl [get_attribute $p slack]; set tns [expr {$tns + $sl}]; incr n; if {$sl < $wns} {set wns $sl} }
    puts "FINAL_${tag}: violating_paths(<=1000 listed)=$n wns=$wns tns_of_listed=$tns"
    set p1 [get_timing_paths -delay_type $dt -max_paths 1]
    puts "FINAL_${tag}_WORST_SLACK: [get_attribute $p1 slack]"
  } e]
  if {$rc} { puts "FINAL_${tag}: query failed: $e" }
}
# ---- fill: ONLY fill_* cells.  LibreLane places decap cells first, but in ICC2 the decap/fill frames carry a li1 blockage over the whole cell
#      while the router leaves li1 pin-access stubs in free space; decap_8 placed over them gave 13,065 shorts in check_lvs (all Cell1=decap, layer li1).
set fills [get_lib_cells {sky130_hd_phys/sky130_fd_sc_hd__fill_8 sky130_hd_phys/sky130_fd_sc_hd__fill_4 sky130_hd_phys/sky130_fd_sc_hd__fill_2 sky130_hd_phys/sky130_fd_sc_hd__fill_1}]
create_stdcell_fillers -lib_cells $fills -prefix FILL_
connect_pg_net -net VPWR [get_pins -hierarchical */VPWR]
connect_pg_net -net VPWR [get_pins -hierarchical */VPB]
connect_pg_net -net VGND [get_pins -hierarchical */VGND]
connect_pg_net -net VGND [get_pins -hierarchical */VNB]
# ---- fillers that sit on router li1 pin-access stubs are removed again (physical-only cells; leaves small unfilled gaps), up to 4 passes
for {set k 1} {$k <= 4} {incr k} {
  redirect -file $R/filler_lvs_$k.txt { check_lvs -checks short -max_errors 0 }
  set names {}
  set fh [open $R/filler_lvs_$k.txt r]
  while {[gets $fh l] >= 0} { if {[regexp {Cell1: (xofiller\S+?)\. Net2} $l -> nm]} { lappend names $nm } }
  close $fh
  set names [lsort -unique $names]
  puts "FILLER_FIX pass $k: [llength $names] filler cells overlap routed shapes"
  if {[llength $names] == 0} break
  foreach nm $names { catch {remove_cells [get_cells -quiet $nm]} }
}
catch {redirect -file $R/final_check_routes.txt { check_routes -drc true -antenna true -open_net true }}
catch {redirect -file $R/final_check_lvs.txt    { check_lvs -checks all -max_errors 0 }}
catch {redirect -file $R/final_check_legality.txt { check_legality -verbose }}
catch {redirect -file $R/final_pg_drc.txt       { check_pg_drc }}
catch {redirect -file $R/final_pg_conn.txt      { check_pg_connectivity -check_std_cell_pins none }}
catch {redirect -file $R/final_utilization.txt  { report_utilization }}
set fh [open $R/final_cellcount.txt w]
array set cnt {}
foreach_in_collection c [get_cells -hierarchical -filter "is_hierarchical==false"] { set r [get_attribute $c ref_name]; if {![info exists cnt($r)]} {set cnt($r) 0}; incr cnt($r) }
foreach r [lsort [array names cnt]] { puts $fh "$r $cnt($r)" }
close $fh
save_stage 06_finish
# ---- outputs
set rc [catch {write_verilog -exclude {physical_only_cells} $O/rv32i_cpu_top.nl.v} e]; puts "write_verilog logical rc=$rc $e"
set rc [catch {write_verilog -include {pg_netlist} $O/rv32i_cpu_top.full.pnl.v} e]; puts "write_verilog full rc=$rc $e"
set rc [catch {write_def $O/rv32i_cpu_top.def} e]; puts "write_def rc=$rc $e"
set rc [catch {write_sdc -output $O/rv32i_cpu_top.sdc} e]; puts "write_sdc rc=$rc $e"
set rc [catch {write_parasitics -output $O/rv32i_cpu_top.icc2native.spef -format spef} e]; puts "write_parasitics rc=$rc $e"
set pdk $::env(HOME)/pdk/sky130A/libs.ref
set rc [catch {write_gds -layer_map $SCRIPTDIR/gds_layer_map.txt -merge_files "$pdk/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds $pdk/sky130_sram_macros/gds/${SRAM}.gds" -long_names -output_pin all -merge_gds_top_cell $TOP -units 1000 $O/rv32i_cpu_top.gds} e]; puts "write_gds rc=$rc $e"
stage_time finish $t0
exit
