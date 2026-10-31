#######################################################
#                                                     
#  Innovus Command Logging File                     
#  Created on Sat Oct 31 10:14:42 2026                
#                                                     
#######################################################

#@(#)CDS: Innovus v23.14-s088_1 (64bit) 02/28/2025 12:25 (Linux 3.10.0-693.el7.x86_64)
#@(#)CDS: NanoRoute 23.14-s088_1 NR250219-0822/23_14-UB (database version 18.20.661) {superthreading v2.20}
#@(#)CDS: AAE 23.14-s018 (64bit) 02/28/2025 (Linux 3.10.0-693.el7.x86_64)
#@(#)CDS: CTE 23.14-s036_1 () Feb 22 2025 01:17:26 ( )
#@(#)CDS: SYNTECH 23.14-s010_1 () Feb 19 2025 23:56:49 ( )
#@(#)CDS: CPE v23.14-s082
#@(#)CDS: IQuantus/TQuantus 23.1.1-s336 (64bit) Mon Jan 20 22:11:00 PST 2025 (Linux 3.10.0-693.el7.x86_64)

set_global _enable_mmmc_by_default_flow      $CTE::mmmc_default
suppressMessage ENCEXT-2799
getVersion
setMultiCpuUsage -localCpu 2
restoreDesign /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/impl/innovus/runs/b5g_innovus/dbs/06_finish.enc.dat rv32i_cpu_top
setMultiCpuUsage -localCpu 2
setDesignMode -process 130 -bottomRoutingLayer met1 -topRoutingLayer met4
setAnalysisMode -analysisType onChipVariation -cppr both
setExtractRCMode -engine postRoute -effortLevel low
extractRC
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -early -from {axi_rdata_i[13]} -to {u_core/u_icache_data_din_q_reg[13]/D} -path_type full_clock > $d/path_hold_axi13.txt
report_timing -from {axi_rdata_i[11]} -to {u_core/u_dcache_gen_data_sram[0].u_data_sram/din0[11]} -path_type full_clock > $d/path_setup_axi11.txt
report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_setup_r2r.txt
report_timing -early -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_hold_r2r.txt
report_timing -to {apb_pslverr_o} -path_type full_clock > $d/path_setup_pslverr.txt
getDelayCalMode
setDelayCalMode -siAware false
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -early -from {axi_rdata_i[13]} -to {u_core/u_icache_data_din_q_reg[13]/D} -path_type full_clock > $d/path_hold_axi13.txt
report_timing -from {axi_rdata_i[11]} -to {u_core/u_dcache_gen_data_sram[0].u_data_sram/din0[11]} -path_type full_clock > $d/path_setup_axi11.txt
report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_setup_r2r.txt
report_timing -early -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_hold_r2r.txt
report_timing -to {apb_pslverr_o} -path_type full_clock > $d/path_setup_pslverr.txt
all_constraint_modes -active
set_interactive_constraint_modes [all_constraint_modes -active]
set_clock_latency -source -early -max -rise $late_rise [get_ports clk_i] -clock clk_i
set_clock_latency -source -early -max -fall $late_fall [get_ports clk_i] -clock clk_i
set_clock_latency -source -late  -max -rise $late_rise [get_ports clk_i] -clock clk_i
set_clock_latency -source -late  -max -fall $late_fall [get_ports clk_i] -clock clk_i
set_interactive_constraint_modes {}
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -early -from {axi_rdata_i[13]} -to {u_core/u_icache_data_din_q_reg[13]/D} -path_type full_clock > $d/path_hold_axi13.txt
report_timing -from {axi_rdata_i[11]} -to {u_core/u_dcache_gen_data_sram[0].u_data_sram/din0[11]} -path_type full_clock > $d/path_setup_axi11.txt
report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_setup_r2r.txt
report_timing -early -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_hold_r2r.txt
report_timing -to {apb_pslverr_o} -path_type full_clock > $d/path_setup_pslverr.txt
spefIn -rc_corner rc_nom /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -early -from {axi_rdata_i[13]} -to {u_core/u_icache_data_din_q_reg[13]/D} -path_type full_clock > $d/path_hold_axi13.txt
report_timing -from {axi_rdata_i[11]} -to {u_core/u_dcache_gen_data_sram[0].u_data_sram/din0[11]} -path_type full_clock > $d/path_setup_axi11.txt
report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_setup_r2r.txt
report_timing -early -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_hold_r2r.txt
report_timing -to {apb_pslverr_o} -path_type full_clock > $d/path_setup_pslverr.txt
set_default_switching_activity -input_activity 0.1 -seq_activity 0.1
report_power -outfile /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g/innovus_b/n2_star_latOFF_siOff/power_act01.txt
set_default_switching_activity -input_activity 0.2 -seq_activity 0.2
report_power -outfile /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g/innovus_b/n2_star_latOFF_siOff/power_act02.txt
all_constraint_modes -active
set_interactive_constraint_modes [all_constraint_modes -active]
set_clock_latency -source -early -max -rise $late_rise [get_ports clk_i] -clock clk_i
set_clock_latency -source -early -max -fall $late_fall [get_ports clk_i] -clock clk_i
set_clock_latency -source -late  -max -rise $late_rise [get_ports clk_i] -clock clk_i
set_clock_latency -source -late  -max -fall $late_fall [get_ports clk_i] -clock clk_i
set_interactive_constraint_modes {}
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag {*}$args -max_paths 1 
report_timing -collection {*}$flag -max_paths 1
report_timing -early -from {axi_rdata_i[13]} -to {u_core/u_icache_data_din_q_reg[13]/D} -path_type full_clock > $d/path_hold_axi13.txt
report_timing -from {axi_rdata_i[11]} -to {u_core/u_dcache_gen_data_sram[0].u_data_sram/din0[11]} -path_type full_clock > $d/path_setup_axi11.txt
report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_setup_r2r.txt
report_timing -early -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1 -path_type full_clock > $d/path_hold_r2r.txt
report_timing -to {apb_pslverr_o} -path_type full_clock > $d/path_setup_pslverr.txt
