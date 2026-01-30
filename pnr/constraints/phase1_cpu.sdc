#=============================================
# Phase 1: Single-cycle RV32I CPU
# Target: 100 MHz (10ns period)
# File: phase1_cpu.sdc
#=============================================

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Create primary clock
create_clock -name clk -period 10.0 [get_ports clk]

# Clock uncertainty (pre-CTS estimate)
set_clock_uncertainty 0.5 [get_clocks clk]

# Clock latency (source: external PLL)
set_clock_latency -source 1.0 [get_clocks clk]

# Clock transition time (slew)
set_clock_transition 0.1 [get_clocks clk]

#---------------------------------------------
# Input Constraints
#---------------------------------------------

# AXI4-Lite input delays (based on protocol timing)
# Assume external memory controller with 2ns setup, 0.5ns hold
set_input_delay -clock clk -max 2.0 [get_ports axi_*ready]
set_input_delay -clock clk -max 2.0 [get_ports axi_rdata]
set_input_delay -clock clk -max 2.0 [get_ports axi_rresp]
set_input_delay -clock clk -max 2.0 [get_ports axi_rvalid]
set_input_delay -clock clk -max 2.0 [get_ports axi_bvalid]
set_input_delay -clock clk -max 2.0 [get_ports axi_bresp]

set_input_delay -clock clk -min 0.5 [get_ports axi_*ready]
set_input_delay -clock clk -min 0.5 [get_ports axi_rdata]
set_input_delay -clock clk -min 0.5 [get_ports axi_rresp]
set_input_delay -clock clk -min 0.5 [get_ports axi_rvalid]
set_input_delay -clock clk -min 0.5 [get_ports axi_bvalid]
set_input_delay -clock clk -min 0.5 [get_ports axi_bresp]

# APB3 input delays (debug interface, less critical)
set_input_delay -clock clk -max 3.0 [get_ports apb_paddr]
set_input_delay -clock clk -max 3.0 [get_ports apb_psel]
set_input_delay -clock clk -max 3.0 [get_ports apb_penable]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwrite]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwdata]

set_input_delay -clock clk -min 1.0 [get_ports apb_*]

#---------------------------------------------
# Output Constraints
#---------------------------------------------

# AXI4-Lite output delays
set_output_delay -clock clk -max 2.0 [get_ports axi_awaddr]
set_output_delay -clock clk -max 2.0 [get_ports axi_awvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_wdata]
set_output_delay -clock clk -max 2.0 [get_ports axi_wstrb]
set_output_delay -clock clk -max 2.0 [get_ports axi_wvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_araddr]
set_output_delay -clock clk -max 2.0 [get_ports axi_arvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_rready]
set_output_delay -clock clk -max 2.0 [get_ports axi_bready]

set_output_delay -clock clk -min 0.5 [all_outputs]

# APB3 output delays
set_output_delay -clock clk -max 3.0 [get_ports apb_prdata]
set_output_delay -clock clk -max 3.0 [get_ports apb_pready]
set_output_delay -clock clk -max 3.0 [get_ports apb_pslverr]

# Commit interface (verification only, relaxed)
set_output_delay -clock clk -max 5.0 [get_ports commit_*]
set_output_delay -clock clk -max 5.0 [get_ports trap_*]

#---------------------------------------------
# False Paths
#---------------------------------------------

# Asynchronous reset
set_false_path -from [get_ports rst_n]

# Debug paths don't affect AXI timing
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]
set_false_path -from [get_ports axi_*] -to [get_ports apb_*]

# Commit interface is for verification only
set_false_path -to [get_ports commit_*]
set_false_path -to [get_ports trap_*]

#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------

# Output load (assume 50fF capacitance)
set_load 0.05 [all_outputs]

# Input drive (assume BUF_X1 driving inputs)
# NOTE: Update library name based on actual PDK
# set_driving_cell -lib_cell BUF_X1 -library sky130_fd_sc_hd [all_inputs]

#---------------------------------------------
# Area Constraint (for synthesis)
#---------------------------------------------

# No specific area constraint (optimize for timing)
set_max_area 0

#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------

# Max transition time (slew rate)
set_max_transition 0.5 [current_design]

# Max capacitance
set_max_capacitance 0.1 [all_outputs]

# Max fanout
set_max_fanout 16 [current_design]

#---------------------------------------------
# End of SDC
#---------------------------------------------
