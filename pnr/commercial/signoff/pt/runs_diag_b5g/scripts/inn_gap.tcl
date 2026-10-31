# inn_gap.tcl -- DIAGNOSTIC Innovus session on the b5g 06_finish database (READ-ONLY: nothing is saved, the b5g run dir is not written).
# env (as run_stage.sh): REPO PDKDIR RUN(=b5g run) TAG HERE ; GOUT = output dir ; STARSPEF = StarRC nom SPEF
source $::env(REPO)/pnr/commercial/impl/innovus/scripts/common.tcl
set GOUT $::env(GOUT)
file mkdir $GOUT
restore_stage 06_finish
common_settings
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low

proc dump_view {tag} {
  global GOUT
  set d $GOUT/$tag; file mkdir $d
  foreach {dt flag nm} {setup {} setup hold -early hold} {
    # partition WNS
    foreach {pn args} [list in2reg [list -from [all_inputs] -to [all_registers -data_pins]] reg2out [list -from [all_registers -clock_pins] -to [all_outputs]] reg2reg [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]] {
      set rc [catch { report_timing -collection {*}$flag {*}$args -max_paths 1 } c]
      if {$rc || [llength $c] == 0} { puts "WNS $tag $nm $pn NONE ($rc)"; continue }
      puts "WNS $tag $nm $pn [get_db [lindex $c 0] .slack]"
    }
    set c [report_timing -collection {*}$flag -max_paths 1]
    puts "WNS $tag $nm ALL [get_db [lindex $c 0] .slack]"
  }
  report_timing -early -from {axi_rdata_i[13]} -to {u_core/u_icache_data_din_q_reg[13]/D} -path_type full_clock > $d/path_hold_axi13.txt
  report_timing -from {axi_rdata_i[11]} -to {u_core/u_dcache_gen_data_sram[0].u_data_sram/din0[11]} -path_type full_clock > $d/path_setup_axi11.txt
  report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_setup_r2r.txt
  report_timing -early -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_hold_r2r.txt
  report_timing -to {apb_pslverr_o} -path_type full_clock > $d/path_setup_pslverr.txt
}
proc set_io_latency {late_rise late_fall} {
  set_interactive_constraint_modes [all_constraint_modes -active]
  # same 4 pin-level lines Innovus wrote into views/av_tt/latency.sdc, with chosen late (-max) values
  set_clock_latency -source -early -max -rise $late_rise [get_ports clk_i] -clock clk_i
  set_clock_latency -source -early -max -fall $late_fall [get_ports clk_i] -clock clk_i
  set_clock_latency -source -late  -max -rise $late_rise [get_ports clk_i] -clock clk_i
  set_clock_latency -source -late  -max -fall $late_fall [get_ports clk_i] -clock clk_i
  set_interactive_constraint_modes {}
}
puts "STEP N0: native as restored (latency file ON, native tech-LEF RC, SI as timeDesign default)"
extractRC
dump_view n0_nat_latON
catch { report_delay_calculation -from {u_core/u_if_if_id_reg_o_reg[instruction][0]/CLK} -to {u_core/FE_OFC11002_if_id_reg_instruction__0/A} > $GOUT/n0_nat_latON/dc_stage.txt }
puts "SIMODE: [catch {getDelayCalMode} e] $e"
puts "STEP N0b: SI-aware delay calc OFF"
catch { setDelayCalMode -siAware false } e; puts "setDelayCalMode: $e"
dump_view n0b_nat_latON_siOff
puts "STEP N1: latency OFF (late latency 1.0 = shared SDC), native RC, SI off"
set_io_latency 1.0 1.0
dump_view n1_nat_latOFF_siOff
puts "STEP N2: latency OFF, StarRC SPEF, SI off"
spefIn -rc_corner rc_nom $::env(STARSPEF)
dump_view n2_star_latOFF_siOff
catch { set_default_switching_activity -input_activity 0.1 -seq_activity 0.1 }
catch { report_power -outfile $GOUT/n2_star_latOFF_siOff/power_act01.txt }
catch { set_default_switching_activity -input_activity 0.2 -seq_activity 0.2 }
catch { report_power -outfile $GOUT/n2_star_latOFF_siOff/power_act02.txt }
puts "STEP N3: latency ON, StarRC SPEF, SI off"
set_io_latency -1.90877 -1.65153
dump_view n3_star_latON_siOff
exit
