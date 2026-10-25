# 04_cts.tcl -- Step B5b stage 4: clock tree synthesis (ccopt) with CTS_CLK_BUFFERS clkbuf_2/4/8/16 (root buffer clkbuf_16), post-CTS setup + hold optimisation.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
restore_stage 03_place
common_settings
setExtractRCMode -engine preRoute
setOptMode -fixFanoutLoad true -fixDrc true
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
report_ccopt_clock_trees -file $RUN/reports/cts_clock_trees.txt
report_ccopt_skew_groups -file $RUN/reports/cts_skew_groups.txt
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
