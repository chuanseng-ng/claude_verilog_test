#=============================================
# Phase 1: Single-cycle RV32I CPU - Enhanced SDC
# Target: 100 MHz (10ns period)
# File: phase1_cpu_enhanced.sdc
# Description: Comprehensive timing constraints with full port coverage
#=============================================

#---------------------------------------------
# Design Information
#---------------------------------------------
# Top module: rv32i_cpu_top
# Clock domain: Single clock (clk)
# Interfaces: AXI4-Lite (master), APB3 (slave), Commit (verification)
# Architecture: Single-cycle with AXI stalls

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Create primary clock (100 MHz target)
create_clock -name clk -period 10.0 [get_ports clk]

# Clock uncertainty (pre-CTS estimate: 5% of period)
# This accounts for jitter and skew before clock tree synthesis
set_clock_uncertainty 0.5 [get_clocks clk]

# Clock source latency (external PLL to chip boundary)
set_clock_latency -source 1.0 [get_clocks clk]

# Clock transition time (slew rate at clock port)
# Assuming clean external clock source
set_clock_transition 0.1 [get_clocks clk]

#---------------------------------------------
# Input Constraints - AXI4-Lite Slave Signals
#---------------------------------------------

# AXI4-Lite Read Address Channel (slave to master responses)
# External memory controller provides these signals
# Setup requirement: 2ns, Hold requirement: 0.5ns

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

# Write address ready (memory accepts write address)
set_input_delay -clock clk -max 2.0 [get_ports axi_awready]
set_input_delay -clock clk -min 0.5 [get_ports axi_awready]

# Write data ready (memory accepts write data)
set_input_delay -clock clk -max 2.0 [get_ports axi_wready]
set_input_delay -clock clk -min 0.5 [get_ports axi_wready]

# Write response channel (memory to CPU)
set_input_delay -clock clk -max 2.0 [get_ports {axi_bresp[1] axi_bresp[0]}]
set_input_delay -clock clk -max 2.0 [get_ports axi_bvalid]

set_input_delay -clock clk -min 0.5 [get_ports {axi_bresp[1] axi_bresp[0]}]
set_input_delay -clock clk -min 0.5 [get_ports axi_bvalid]

#---------------------------------------------
# Input Constraints - APB3 Master Signals
#---------------------------------------------

# APB3 debug interface (less timing critical, relaxed constraints)
# Debug operations don't affect CPU performance

# Address and control signals
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

# AXI4-Lite outputs must meet external memory timing
# Assume external memory has 2ns setup requirement

# Write address channel (CPU to memory)
set_output_delay -clock clk -max 2.0 [get_ports axi_awaddr[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_awvalid]
set_output_delay -clock clk -min 0.5 [get_ports axi_awaddr[*]]
set_output_delay -clock clk -min 0.5 [get_ports axi_awvalid]

# Write data channel (CPU to memory)
set_output_delay -clock clk -max 2.0 [get_ports axi_wdata[*]]
set_output_delay -clock clk -max 2.0 [get_ports {axi_wstrb[3] axi_wstrb[2] axi_wstrb[1] axi_wstrb[0]}]
set_output_delay -clock clk -max 2.0 [get_ports axi_wvalid]
set_output_delay -clock clk -min 0.5 [get_ports axi_wdata[*]]
set_output_delay -clock clk -min 0.5 [get_ports {axi_wstrb[3] axi_wstrb[2] axi_wstrb[1] axi_wstrb[0]}]
set_output_delay -clock clk -min 0.5 [get_ports axi_wvalid]

# Write response ready (CPU to memory)
set_output_delay -clock clk -max 2.0 [get_ports axi_bready]
set_output_delay -clock clk -min 0.5 [get_ports axi_bready]

# Read address channel (CPU to memory)
set_output_delay -clock clk -max 2.0 [get_ports axi_araddr[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_arvalid]
set_output_delay -clock clk -min 0.5 [get_ports axi_araddr[*]]
set_output_delay -clock clk -min 0.5 [get_ports axi_arvalid]

# Read data ready (CPU to memory)
set_output_delay -clock clk -max 2.0 [get_ports axi_rready]
set_output_delay -clock clk -min 0.5 [get_ports axi_rready]

#---------------------------------------------
# Output Constraints - APB3 Slave Signals
#---------------------------------------------

# APB3 debug interface outputs (relaxed timing)
set_output_delay -clock clk -max 3.0 [get_ports apb_prdata[*]]
set_output_delay -clock clk -max 3.0 [get_ports apb_pready]
set_output_delay -clock clk -max 3.0 [get_ports apb_pslverr]

set_output_delay -clock clk -min 0.5 [get_ports apb_prdata[*]]
set_output_delay -clock clk -min 0.5 [get_ports apb_pready]
set_output_delay -clock clk -min 0.5 [get_ports apb_pslverr]

#---------------------------------------------
# Output Constraints - Commit Interface
#---------------------------------------------

# Commit interface is for verification observability only
# Very relaxed timing, does not affect functional paths
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

# Asynchronous reset (no timing relationship with clock)
set_false_path -from [get_ports rst_n]

# Debug <-> AXI paths are independent (debug doesn't affect memory timing)
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]
set_false_path -from [get_ports axi_*] -to [get_ports apb_*]

# Commit interface is verification-only (doesn't affect functional paths)
set_false_path -to [get_ports commit_*]
set_false_path -to [get_ports trap_*]

#---------------------------------------------
# Critical Internal Paths (Optional)
#---------------------------------------------

# These constraints ensure critical internal paths meet timing
# Uncomment if synthesis struggles with specific paths

# PC update path (critical for single-cycle timing)
# set_max_delay 9.0 -from [get_pins u_core/pc_reg*] -to [get_pins u_core/pc_next*]

# ALU path (critical for single-cycle execution)
# set_max_delay 8.0 -from [get_pins u_core/u_alu/operand_*] -to [get_pins u_core/u_alu/result*]

# Register file read to ALU (critical datapath)
# set_max_delay 9.0 -from [get_pins u_core/u_regfile/rd_data*] -to [get_pins u_core/u_alu/result*]

#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------

# Output load capacitance (assume 50fF external load)
set_load 0.05 [all_outputs]

# Input drive strength (assume BUF_X1 cell from PDK driving inputs)
# Uncomment and update library name when PDK is selected
# set_driving_cell -lib_cell BUF_X1 -library sky130_fd_sc_hd [all_inputs]

# Alternative: specify input transition time directly
set_input_transition 0.2 [all_inputs]

#---------------------------------------------
# Area and Power Constraints
#---------------------------------------------

# No specific area constraint (optimize for timing first)
set_max_area 0

#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------

# Maximum transition time (slew rate) on all nets
# Prevents signal integrity issues
set_max_transition 0.5 [current_design]

# Maximum capacitance on output ports
set_max_capacitance 0.1 [all_outputs]

# Maximum fanout (number of loads per net)
set_max_fanout 16 [current_design]

#---------------------------------------------
# Operating Conditions and Libraries
#---------------------------------------------

# Operating conditions (update when PDK is integrated)
# Typical corner for initial timing analysis
# set_operating_conditions -max typical -min typical

# For multi-corner analysis, specify corner-specific conditions
# SS corner (worst setup):
# set_operating_conditions -max ss_1p0v_125c -library sky130_fd_sc_hd__ss_1p0v_125c

# FF corner (worst hold):
# set_operating_conditions -min ff_1p1v_n40c -library sky130_fd_sc_hd__ff_1p1v_n40c

#---------------------------------------------
# Case Analysis (Optional)
#---------------------------------------------

# If certain signals are tied to constants in test mode
# Example: set_case_analysis 0 [get_ports test_mode]

#---------------------------------------------
# End of SDC
#---------------------------------------------
# Generated for Phase 1 RV32I CPU
# Last updated: 2026-01-22
