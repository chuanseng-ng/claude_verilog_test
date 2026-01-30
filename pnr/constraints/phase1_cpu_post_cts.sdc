#=============================================
# Phase 1: Single-cycle RV32I CPU - Post-CTS SDC
# Target: 100 MHz (10ns period)
# File: phase1_cpu_post_cts.sdc
# Description: Updated constraints after clock tree synthesis
#=============================================

#---------------------------------------------
# Design Information
#---------------------------------------------
# Top module: rv32i_cpu_top
# Clock domain: Single clock (clk)
# Status: Post-CTS (clock tree has been synthesized)
# Use this file after CTS for more accurate timing analysis

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Create primary clock (100 MHz)
create_clock -name clk -period 10.0 [get_ports clk]

# Post-CTS clock uncertainty (much tighter than pre-CTS)
# After CTS, the clock tree is built and skew is known
# Uncertainty now mainly accounts for jitter (1-2% of period)
set_clock_uncertainty -setup 0.1 [get_clocks clk]
set_clock_uncertainty -hold 0.05 [get_clocks clk]

# Clock source latency (external PLL to chip boundary)
set_clock_latency -source 1.0 [get_clocks clk]

# NOTE: Network latency is now modeled by the actual clock tree
# Do NOT set clock_latency for network after CTS (it's in the netlist)

# Clock transition time (updated based on CTS results)
# This will be overridden by actual clock tree buffers
set_clock_transition 0.1 [get_clocks clk]

#---------------------------------------------
# Input Constraints - AXI4-Lite Slave Signals
#---------------------------------------------

# Read address ready (memory accepts address)
set_input_delay -clock clk -max 2.0 [get_ports axi_arready]
set_input_delay -clock clk -min 0.5 [get_ports axi_arready]

# Read data channel (memory to CPU)
set_input_delay -clock clk -max 2.0 [get_ports axi_rdata[*]]
set_input_delay -clock clk -max 2.0 [get_ports {axi_rresp[1] axi_rresp[0]}]
set_input_delay -clock clk -max 2.0 [get_ports axi_rvalid]

set_input_delay -clock clk -min 0.5 [get_ports axi_rdata[*]]
set_input_delay -clock clk -min 0.5 [get_ports {axi_rresp[1] axi_rresp[0]}]
set_input_delay -clock clk -min 0.5 [get_ports axi_rvalid]

# Write address ready
set_input_delay -clock clk -max 2.0 [get_ports axi_awready]
set_input_delay -clock clk -min 0.5 [get_ports axi_awready]

# Write data ready
set_input_delay -clock clk -max 2.0 [get_ports axi_wready]
set_input_delay -clock clk -min 0.5 [get_ports axi_wready]

# Write response channel
set_input_delay -clock clk -max 2.0 [get_ports {axi_bresp[1] axi_bresp[0]}]
set_input_delay -clock clk -max 2.0 [get_ports axi_bvalid]

set_input_delay -clock clk -min 0.5 [get_ports {axi_bresp[1] axi_bresp[0]}]
set_input_delay -clock clk -min 0.5 [get_ports axi_bvalid]

#---------------------------------------------
# Input Constraints - APB3 Master Signals
#---------------------------------------------

# APB3 debug interface
set_input_delay -clock clk -max 3.0 [get_ports apb_paddr[*]]
set_input_delay -clock clk -max 3.0 [get_ports apb_psel]
set_input_delay -clock clk -max 3.0 [get_ports apb_penable]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwrite]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwdata[*]]

set_input_delay -clock clk -min 1.0 [get_ports apb_paddr[*]]
set_input_delay -clock clk -min 1.0 [get_ports apb_psel]
set_input_delay -clock clk -min 1.0 [get_ports apb_penable]
set_input_delay -clock clk -min 1.0 [get_ports apb_pwrite]
set_input_delay -clock clk -min 1.0 [get_ports apb_pwdata[*]]

#---------------------------------------------
# Output Constraints - AXI4-Lite Master Signals
#---------------------------------------------

# Write address channel
set_output_delay -clock clk -max 2.0 [get_ports axi_awaddr[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_awvalid]
set_output_delay -clock clk -min 0.5 [get_ports axi_awaddr[*]]
set_output_delay -clock clk -min 0.5 [get_ports axi_awvalid]

# Write data channel
set_output_delay -clock clk -max 2.0 [get_ports axi_wdata[*]]
set_output_delay -clock clk -max 2.0 [get_ports {axi_wstrb[3] axi_wstrb[2] axi_wstrb[1] axi_wstrb[0]}]
set_output_delay -clock clk -max 2.0 [get_ports axi_wvalid]
set_output_delay -clock clk -min 0.5 [get_ports axi_wdata[*]]
set_output_delay -clock clk -min 0.5 [get_ports {axi_wstrb[3] axi_wstrb[2] axi_wstrb[1] axi_wstrb[0]}]
set_output_delay -clock clk -min 0.5 [get_ports axi_wvalid]

# Write response ready
set_output_delay -clock clk -max 2.0 [get_ports axi_bready]
set_output_delay -clock clk -min 0.5 [get_ports axi_bready]

# Read address channel
set_output_delay -clock clk -max 2.0 [get_ports axi_araddr[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_arvalid]
set_output_delay -clock clk -min 0.5 [get_ports axi_araddr[*]]
set_output_delay -clock clk -min 0.5 [get_ports axi_arvalid]

# Read data ready
set_output_delay -clock clk -max 2.0 [get_ports axi_rready]
set_output_delay -clock clk -min 0.5 [get_ports axi_rready]

#---------------------------------------------
# Output Constraints - APB3 Slave Signals
#---------------------------------------------

set_output_delay -clock clk -max 3.0 [get_ports apb_prdata[*]]
set_output_delay -clock clk -max 3.0 [get_ports apb_pready]
set_output_delay -clock clk -max 3.0 [get_ports apb_pslverr]

set_output_delay -clock clk -min 0.5 [get_ports apb_prdata[*]]
set_output_delay -clock clk -min 0.5 [get_ports apb_pready]
set_output_delay -clock clk -min 0.5 [get_ports apb_pslverr]

#---------------------------------------------
# Output Constraints - Commit Interface
#---------------------------------------------

set_output_delay -clock clk -max 5.0 [get_ports commit_valid]
set_output_delay -clock clk -max 5.0 [get_ports commit_pc[*]]
set_output_delay -clock clk -max 5.0 [get_ports commit_insn[*]]
set_output_delay -clock clk -max 5.0 [get_ports trap_taken]
set_output_delay -clock clk -max 5.0 [get_ports {trap_cause[3] trap_cause[2] trap_cause[1] trap_cause[0]}]

set_output_delay -clock clk -min 0.0 [get_ports commit_valid]
set_output_delay -clock clk -min 0.0 [get_ports commit_pc[*]]
set_output_delay -clock clk -min 0.0 [get_ports commit_insn[*]]
set_output_delay -clock clk -min 0.0 [get_ports trap_taken]
set_output_delay -clock clk -min 0.0 [get_ports {trap_cause[3] trap_cause[2] trap_cause[1] trap_cause[0]}]

#---------------------------------------------
# False Paths
#---------------------------------------------

# Asynchronous reset
set_false_path -from [get_ports rst_n]

# Debug <-> AXI independence
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]
set_false_path -from [get_ports axi_*] -to [get_ports apb_*]

# Commit interface (verification only)
set_false_path -to [get_ports commit_*]
set_false_path -to [get_ports trap_*]

#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------

# Output load capacitance
set_load 0.05 [all_outputs]

# Input transition time
set_input_transition 0.2 [all_inputs]

#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------

# Post-CTS design rules (may be tighter)
set_max_transition 0.4 [current_design]
set_max_capacitance 0.1 [all_outputs]
set_max_fanout 16 [current_design]

#---------------------------------------------
# Clock Skew Analysis
#---------------------------------------------

# After CTS, analyze clock skew to ensure it's acceptable
# Target: < 100ps between any two flops
# Run: report_clock_skew -hold -setup [get_clocks clk]

#---------------------------------------------
# End of Post-CTS SDC
#---------------------------------------------
# Generated for Phase 1 RV32I CPU
# Use this file after clock tree synthesis
# Last updated: 2026-01-22
