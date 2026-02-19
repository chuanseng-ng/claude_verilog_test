#=============================================
# Phase 2: 5-stage Pipelined RV32I CPU
# Target: 100 MHz (10ns period)
# File: phase2_cpu.sdc
#
# Architecture: IF -> ID -> EX -> MEM -> WB
# New in Phase 2: interrupt inputs (ext_irq_i, timer_irq_i),
#                 per-port _i/_o suffix naming convention
#=============================================

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Primary clock on clk_i port (renamed from Phase 1 "clk")
create_clock -name clk_i -period 10.0 [get_ports clk_i]

# Clock uncertainty (pre-CTS estimate)
set_clock_uncertainty 0.5 [get_clocks clk_i]

# Clock latency (source: external PLL or board-level source)
set_clock_latency -source 1.0 [get_clocks clk_i]

# Clock transition time (slew)
set_clock_transition 0.1 [get_clocks clk_i]

#---------------------------------------------
# Input Constraints — AXI4-Lite
#---------------------------------------------
# Slave-side ready and response signals driven by external memory controller.
# Assume 2ns max setup relative to clk_i, 0.5ns min hold.

# Ready signals
set_input_delay -clock clk_i -max 2.0 [get_ports axi_awready_i]
set_input_delay -clock clk_i -max 2.0 [get_ports axi_wready_i]
set_input_delay -clock clk_i -max 2.0 [get_ports axi_arready_i]

set_input_delay -clock clk_i -min 0.5 [get_ports axi_awready_i]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_wready_i]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_arready_i]

# Write response channel
set_input_delay -clock clk_i -max 2.0 [get_ports axi_bresp_i]
set_input_delay -clock clk_i -max 2.0 [get_ports axi_bvalid_i]

set_input_delay -clock clk_i -min 0.5 [get_ports axi_bresp_i]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_bvalid_i]

# Read data channel
set_input_delay -clock clk_i -max 2.0 [get_ports axi_rdata_i]
set_input_delay -clock clk_i -max 2.0 [get_ports axi_rresp_i]
set_input_delay -clock clk_i -max 2.0 [get_ports axi_rvalid_i]

set_input_delay -clock clk_i -min 0.5 [get_ports axi_rdata_i]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_rresp_i]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_rvalid_i]

#---------------------------------------------
# Input Constraints — APB3 Debug Interface
#---------------------------------------------
# APB is less timing-critical than AXI; 3ns max allowed.

set_input_delay -clock clk_i -max 3.0 [get_ports apb_paddr_i]
set_input_delay -clock clk_i -max 3.0 [get_ports apb_psel_i]
set_input_delay -clock clk_i -max 3.0 [get_ports apb_penable_i]
set_input_delay -clock clk_i -max 3.0 [get_ports apb_pwrite_i]
set_input_delay -clock clk_i -max 3.0 [get_ports apb_pwdata_i]

set_input_delay -clock clk_i -min 1.0 [get_ports apb_paddr_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_psel_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_penable_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_pwrite_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_pwdata_i]

#---------------------------------------------
# Interrupt inputs are handled as false paths
# (see False Paths section below)
#---------------------------------------------

#---------------------------------------------
# Output Constraints — AXI4-Lite
#---------------------------------------------

# Write address channel
set_output_delay -clock clk_i -max 2.0 [get_ports axi_awaddr_o]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_awvalid_o]

set_output_delay -clock clk_i -min 0.5 [get_ports axi_awaddr_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_awvalid_o]

# Write data channel
set_output_delay -clock clk_i -max 2.0 [get_ports axi_wdata_o]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_wstrb_o]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_wvalid_o]

set_output_delay -clock clk_i -min 0.5 [get_ports axi_wdata_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_wstrb_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_wvalid_o]

# Write response ready
set_output_delay -clock clk_i -max 2.0 [get_ports axi_bready_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_bready_o]

# Read address channel
set_output_delay -clock clk_i -max 2.0 [get_ports axi_araddr_o]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_arvalid_o]

set_output_delay -clock clk_i -min 0.5 [get_ports axi_araddr_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_arvalid_o]

# Read data ready
set_output_delay -clock clk_i -max 2.0 [get_ports axi_rready_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_rready_o]

#---------------------------------------------
# Output Constraints — APB3 Debug Interface
#---------------------------------------------

set_output_delay -clock clk_i -max 3.0 [get_ports apb_prdata_o]
set_output_delay -clock clk_i -max 3.0 [get_ports apb_pready_o]
set_output_delay -clock clk_i -max 3.0 [get_ports apb_pslverr_o]

set_output_delay -clock clk_i -min 1.0 [get_ports apb_prdata_o]
set_output_delay -clock clk_i -min 1.0 [get_ports apb_pready_o]
set_output_delay -clock clk_i -min 1.0 [get_ports apb_pslverr_o]

#---------------------------------------------
# False Paths
#---------------------------------------------

# Asynchronous reset — not a synchronous path
set_false_path -from [get_ports rst_n_i]

# Interrupt inputs: ext_irq_i and timer_irq_i are asynchronous external
# signals. Synchronization is handled internally (the interrupt controller
# latches these at the WB stage). STA should not attempt to close timing
# across this async boundary.
set_false_path -from [get_ports ext_irq_i]
set_false_path -from [get_ports timer_irq_i]

# Commit interface: verification-only observability outputs.
# Not part of any performance-critical downstream path.
set_false_path -to [get_ports commit_valid_o]
set_false_path -to [get_ports commit_pc_o]
set_false_path -to [get_ports commit_insn_o]
set_false_path -to [get_ports trap_taken_o]
set_false_path -to [get_ports trap_cause_o]

# Debug observability outputs: pipeline state exposed for waveform analysis.
# These are not timing-critical and should not constrain synthesis.
set_false_path -to [get_ports debug_rs1_data_o]
set_false_path -to [get_ports debug_rs2_data_o]
set_false_path -to [get_ports debug_branch_taken_o]
set_false_path -to [get_ports debug_take_branch_jump_o]
set_false_path -to [get_ports debug_pc_src_o]
set_false_path -to [get_ports debug_state_o]
set_false_path -to [get_ports debug_ebreak_o]

# APB <-> AXI cross-domain: debug writes do not propagate directly to AXI
# and vice versa within a single clock cycle.
set_false_path -from [get_ports apb_paddr_i]    -to [get_ports axi_araddr_o]
set_false_path -from [get_ports apb_paddr_i]    -to [get_ports axi_awaddr_o]
set_false_path -from [get_ports axi_rdata_i]    -to [get_ports apb_prdata_o]

#---------------------------------------------
# Multicycle Paths
#---------------------------------------------

# The APB3 slave in this design asserts apb_pready_o=1 unconditionally,
# so APB transactions complete in one clock cycle. No multicycle path needed.
#
# The 5-stage pipeline has all register-to-register paths within a single
# clock period. The longest combinational path is through the EX stage
# (forwarding mux -> ALU -> branch comparator -> redirect target), estimated
# at ~6ns, well within the 10ns budget minus 2ns I/O margin = 8ns logic budget.

#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------

# Output load (assume 50fF parasitic capacitance on board-level traces)
set_load 0.05 [all_outputs]

# Input drive strength (uncomment and update with actual PDK cell name)
# set_driving_cell -lib_cell BUF_X1 -library sky130_fd_sc_hd [all_inputs]

#---------------------------------------------
# Area Constraint
#---------------------------------------------

# Optimize for timing; no explicit area cap
set_max_area 0

#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------

# Maximum transition time (slew rate limit for signal integrity)
set_max_transition 0.5 [current_design]

# Maximum capacitance on output nets
set_max_capacitance 0.1 [all_outputs]

# Maximum fanout for internal nets
set_max_fanout 16 [current_design]

#---------------------------------------------
# End of SDC
#---------------------------------------------
