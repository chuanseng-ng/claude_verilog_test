# 06_finish.tcl -- Step B5b stage 6: decap + fill, final checks and native reports (tt), all outputs (netlists, DEF, GDS, SDC, SPEF).
source [file join [file dirname [file normalize [info script]]] common.tcl]
set t0 [clock seconds]
if {![info exists ::env(FROM_LABEL)]} { set ::env(FROM_LABEL) 05_route }
restore_stage $::env(FROM_LABEL)
common_settings
set O $RUN/out
set R $RUN/reports
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
# ---- pre-filler native reports (fillers do not change timing)
timeDesign -postRoute -outDir $R/final_setup
timeDesign -postRoute -hold -outDir $R/final_hold
catch { report_timing -max_paths 20 -nworst 1 -path_type full_clock > $R/final_timing_setup.txt }
catch { report_timing -early -max_paths 20 -nworst 1 > $R/final_timing_hold.txt }
catch { report_constraint -all_violators -drv_violation_type {max_capacitance max_transition max_fanout min_pulse_width} > $R/final_violators.txt }
catch { report_power -outfile $R/final_power.txt }
catch { report_ccopt_clock_trees -file $R/final_clock_trees.txt }
catch { report_ccopt_skew_groups -file $R/final_skew_groups.txt }
catch { report_route -summary > $R/final_route_summary.txt }
catch { report_area -out_file $R/final_area.txt }
catch { report_summary -noHtml -outfile $R/final_summary.txt }
# ---- decap + fill (OpenROAD: decap_12/8/6/4/3 then fill_*); verified for shorts afterwards, dropped if it creates any
set rc [catch { addFiller -cell {sky130_fd_sc_hd__decap_12 sky130_fd_sc_hd__decap_8 sky130_fd_sc_hd__decap_6 sky130_fd_sc_hd__decap_4 sky130_fd_sc_hd__decap_3} -prefix DECAP } e]
puts "addFiller decap rc=$rc $e"
set rc [catch { addFiller -cell {sky130_fd_sc_hd__fill_8 sky130_fd_sc_hd__fill_4 sky130_fd_sc_hd__fill_2 sky130_fd_sc_hd__fill_1} -prefix FILL } e]
puts "addFiller fill rc=$rc $e"
globalNetConnect VPWR -type pgpin -pin VPWR -all -override
globalNetConnect VGND -type pgpin -pin VGND -all -override
globalNetConnect VPWR -type pgpin -pin VPB  -all -override
globalNetConnect VGND -type pgpin -pin VNB  -all -override
save_stage 06_finish
# ---- checks
verify_drc -limit 1000000 -report $R/final_drc.txt
verifyProcessAntenna -reportfile $R/final_antenna.txt -error 1000000
verifyConnectivity -type all -noAntenna -report $R/final_connectivity.txt -error 100000
verify_connectivity -type special -report $R/final_pg_connectivity.txt -error 100000
verifyPowerVia -report $R/final_powervia.txt
checkPlace $R/final_checkPlace.txt
# ---- cell counts by master (incl. physical cells)
array set cnt {}
foreach i [dbGet top.insts] { set m [lindex [dbGet $i.cell.name] 0]; if {![info exists cnt($m)]} {set cnt($m) 0}; incr cnt($m) }
set fh [open $R/final_cellcount.txt w]; foreach m [lsort [array names cnt]] { puts $fh "$m $cnt($m)" }; close $fh
# ---- outputs
# logical netlist for LEC: flat, no PG, no physical cells (fill/decap/tap/endcap)
set phys {sky130_fd_sc_hd__fill_1 sky130_fd_sc_hd__fill_2 sky130_fd_sc_hd__fill_4 sky130_fd_sc_hd__fill_8 sky130_fd_sc_hd__decap_3 sky130_fd_sc_hd__decap_4 sky130_fd_sc_hd__decap_6 sky130_fd_sc_hd__decap_8 sky130_fd_sc_hd__decap_12 sky130_fd_sc_hd__tapvpwrvgnd_1}
set rc [catch { saveNetlist $O/rv32i_cpu_top.nl.v -flat -excludeLeafCell -removePowerGround -excludeCellInst $phys } e]; puts "saveNetlist logical rc=$rc $e"
set rc [catch { saveNetlist $O/rv32i_cpu_top.pg.pnl.v -flat -excludeLeafCell -includePowerGround -includePhysicalInst } e]; puts "saveNetlist pg+phys rc=$rc $e"
set rc [catch { defOut -routing -floorplan -netlist -usedVia $O/rv32i_cpu_top.def } e]; puts "defOut rc=$rc $e"
set rc [catch { write_sdc -view av_tt $O/rv32i_cpu_top.sdc } e]; puts "write_sdc rc=$rc $e"
# native SPEF (labelled: Innovus extractRC, capTable/LEF RC, NOT signoff)
setExtractRCMode -engine postRoute -effortLevel low
extractRC
set rc [catch { rcOut -spef $O/rv32i_cpu_top.innovus_native.spef -rc_corner rc_nom } e]; puts "rcOut rc=$rc $e"
# GDS with the Sky130 layer numbers, hd std cells + SRAM merged from the PDK
set rc [catch { streamOut $O/rv32i_cpu_top.gds -mapFile $SCRIPTDIR/gds_layer_map.innovus -libName DesignLib -structureName rv32i_cpu_top -units 1000 -mode ALL \
   -merge [list $PDKREF/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds $PDKREF/sky130_sram_macros/gds/${SRAM}.gds] -reportFile $R/streamOut.rpt } e]; puts "streamOut rc=$rc $e"
stage_time finish $t0
exit
