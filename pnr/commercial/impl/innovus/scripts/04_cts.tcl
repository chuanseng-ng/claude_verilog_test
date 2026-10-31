# 04_cts.tcl -- Step B5b stage 4: clock tree synthesis (ccopt) with CTS_CLK_BUFFERS clkbuf_2/4/8/16 (root buffer clkbuf_16), post-CTS setup + hold optimisation.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
set FROM_RAW [expr {[info exists ::env(FROM_RAW)] && $::env(FROM_RAW) == 1}]   ;# resume from the saved raw CTS (04a_cts_raw), skipping clock_opt_design
if {$FROM_RAW} { restore_stage 04a_cts_raw } else { restore_stage 03_place }
common_settings
setExtractRCMode -engine preRoute
setOptMode -fixFanoutLoad true -fixDrc true
if {!$FROM_RAW} {
# constants: tie cells (the placed netlist still has the Genus 1'b0/1'b1 assigns; stage 03's addTieHiLo call was rejected)
if {[catch { addTieHiLo -cell sky130_fd_sc_hd__conb_1 -prefix TIE } e]} { puts "addTieHiLo: $e" } else { puts "addTieHiLo OK: [llength [dbGet -p2 top.insts.cell.name sky130_fd_sc_hd__conb_1]] tie cells" }
refinePlace
set cts [list sky130_fd_sc_hd__clkbuf_2 sky130_fd_sc_hd__clkbuf_4 sky130_fd_sc_hd__clkbuf_8 sky130_fd_sc_hd__clkbuf_16]
set_ccopt_property buffer_cells $cts
# no inverters: TritonCTS (OpenROAD arm) and the ICC2 arm use buffers only
if {[catch { set_ccopt_property inverter_cells {} } e]} { puts "inverter_cells {}: $e" }
# root buffer clkbuf_16 (CTS_ROOT_BUFFER): set_ccopt_property buffer_cells has no per-net-type form here (IMPCCOPT-2069); the root buffer cannot be forced - recorded as a limitation
# sink cluster size 25 (OpenROAD CTS_CLUSTER_SIZE default; ICC2 arm cts.common.max_fanout 25)
if {[catch { set_ccopt_property max_fanout 25 } e]} { puts "max_fanout 25: $e" }
create_ccopt_clock_tree_spec -file $RUN/out/ccopt.spec
puts "ccopt buffer_cells: [get_ccopt_property buffer_cells]"
set t1 [clock seconds]
clock_opt_design -cts
stage_time ccopt_cts $t1
save_stage 04a_cts_raw
}
report_ccopt_clock_trees -file $RUN/reports/cts_clock_trees.txt
report_ccopt_skew_groups -file $RUN/reports/cts_skew_groups.txt
if {$B5H} {
  # ---- B5h: symmetric, SDC-visible I/O latency = measured mean clock insertion delay (Avg ID of the early skew-group row, = mean of rise/fall sink arrival, excluding the 1.0 ns source latency)
  set fh [open $RUN/reports/cts_skew_groups.txt r]; set LIO ""
  while {[gets $fh l] >= 0} { if {[regexp {^dc_tt:both\.early\s+clk_i/func\s+\S+\s+(\S+)\s+(\S+)\s+(\S+)} $l -> mn mx av]} { if {$LIO eq ""} { set LIO $av } } }
  close $fh
  if {$LIO eq ""} { error "B5H: could not parse Avg ID from cts_skew_groups.txt" }
  puts "B5H: mean clock insertion delay (Avg ID) = $LIO ns -> clk_io network latency"
  exec python3 -I $REPO/pnr/commercial/constraints/gen_innovus_io_sdc.py $LIO $RUN/out/sky130_cpu_innovus_post.sdc --propagated
  update_constraint_mode -name func -sdc_files [list $RUN/out/sky130_cpu_innovus_post.sdc]
  # Innovus re-applies the session's stored latency (clk_io network latency 0, written at the previous save) AFTER the SDC, so the SDC value is overridden: set it explicitly as well.
  # This is an SDC-visible network latency on the virtual clock (write_sdc exports it); verified against the exported SDC in 06_finish / the b5h report.
  set_interactive_constraint_modes func
  set_clock_latency $LIO [get_clocks clk_io]
  set_interactive_constraint_modes {}
  set_ccopt_property update_io_latency false
  catch { report_clocks > $RUN/reports/b5h_clocks_postcts.txt }
  catch { report_clock_timing -type latency -clock clk_i > $RUN/reports/b5h_clock_latency_postcts.txt }
  catch { report_timing -from [get_ports {axi_rdata_i[10]}] -early -path_type full_clock -max_paths 1 > $RUN/reports/b5h_spot_input_hold_postcts.txt }
}
timeDesign -postCTS -outDir $RUN/reports/timing_postCTS
timeDesign -postCTS -hold -outDir $RUN/reports/timing_postCTS_hold
set t2 [clock seconds]
optDesign -postCTS -outDir $RUN/reports/opt_postCTS
optDesign -postCTS -hold -outDir $RUN/reports/opt_postCTS_hold
stage_time postCTS_opt $t2
timeDesign -postCTS -outDir $RUN/reports/timing_postCTS_opt
timeDesign -postCTS -hold -outDir $RUN/reports/timing_postCTS_opt_hold
checkPlace $RUN/reports/checkPlace_cts.txt
save_stage 04_cts
stage_time cts $t0
exit
