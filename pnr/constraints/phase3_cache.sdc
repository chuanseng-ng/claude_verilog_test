# phase3_cache.sdc - Timing constraints for the Phase 3 RV32I CPU with L1 I-cache and D-cache (Sky130, clock clk_i)
#
# Scope: pnr/librelane/config.json sets PNR_SDC_FILE, SIGNOFF_SDC_FILE and FALLBACK_SDC_FILE to this file.
#   pnr/Makefile sets SDC_FILE to it for the OpenROAD stage targets. pnr/openlane1/config.json sets BASE_SDC_FILE to it.
# Contents: it extends phase2_cpu.sdc: clock clk_i; AXI4-Lite and APB3 delays; APB3 multicycle paths; false paths;
#   path groups for the critical pipeline paths; load and drive; area and design-rule constraints.
#   The cache SRAM arrays need no multicycle constraint.
#   There are no new external ports. The caches are internal to rv32i_core, so all external ports are the same as in Phase 2.
# Inputs: none. All time values in this file are in ns.
# User rules:
#   All AXI ports at cpu_top level are the cache-arbiter outputs. They face the L2/DRAM controller.
#   If an asynchronous APB clock is introduced, add a create_clock and a clock group for it (see the APB section).
# Doc: tm:pd:phase3-cache-sdc

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Primary clock.
create_clock -name clk_i -period 13.333 [get_ports clk_i]

# Clock uncertainty: tightened after CTS.
set_clock_uncertainty 0.5 [get_clocks clk_i]
set_clock_uncertainty -hold 0.2 [get_clocks clk_i]

# Clock latency (source: external PLL or board-level oscillator)
set_clock_latency -source 1.0 [get_clocks clk_i]


#---------------------------------------------
# Input Constraints — AXI4-Lite
#---------------------------------------------
# All AXI ports at cpu_top level are the cache-arbiter outputs; they face
# Use a generous setup margin at the target frequency.

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
# APB is non-critical. It gets a larger max input delay.

set_input_delay -clock clk_i -max 3.5 [get_ports apb_paddr_i]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_psel_i]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_penable_i]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_pwrite_i]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_pwdata_i]

set_input_delay -clock clk_i -min 1.0 [get_ports apb_paddr_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_psel_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_penable_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_pwrite_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_pwdata_i]

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

set_output_delay -clock clk_i -max 3.5 [get_ports apb_prdata_o]
set_output_delay -clock clk_i -max 3.5 [get_ports apb_pready_o]
set_output_delay -clock clk_i -max 3.5 [get_ports apb_pslverr_o]

set_output_delay -clock clk_i -min 1.0 [get_ports apb_prdata_o]
set_output_delay -clock clk_i -min 1.0 [get_ports apb_pready_o]
set_output_delay -clock clk_i -min 1.0 [get_ports apb_pslverr_o]

#---------------------------------------------
# Multicycle Paths — APB3 Debug Interface
#---------------------------------------------
# APB slave stretches the bus cycle via PREADY (SETUP→ACCESS takes 2 clocks).
# Apply the multicycle exception to PREADY so the slave's internal latency is
# modelled correctly; PRDATA is constrained at the normal 1-cycle rate.
set_multicycle_path -setup 2 -to [get_ports apb_pready_o]
set_multicycle_path -hold  1 -to [get_ports apb_pready_o]
set_multicycle_path -setup 2 -from [get_ports apb_paddr_i]   -to [get_ports apb_pslverr_o]
set_multicycle_path -hold  1 -from [get_ports apb_paddr_i]   -to [get_ports apb_pslverr_o]

#---------------------------------------------
# False Paths
#---------------------------------------------

# Asynchronous reset
set_false_path -from [get_ports rst_n_i]

# Interrupt inputs (asynchronous; synchronisation is inside interrupt_ctrl)
set_false_path -from [get_ports ext_irq_i]
set_false_path -from [get_ports timer_irq_i]

# Verification observability outputs (commit interface)
set_false_path -to [get_ports commit_valid_o]
set_false_path -to [get_ports commit_pc_o]
set_false_path -to [get_ports commit_insn_o]
set_false_path -to [get_ports trap_taken_o]
set_false_path -to [get_ports trap_cause_o]

# Debug observability outputs
set_false_path -to [get_ports debug_rs1_data_o]
set_false_path -to [get_ports debug_rs2_data_o]
set_false_path -to [get_ports debug_branch_taken_o]
set_false_path -to [get_ports debug_take_branch_jump_o]
set_false_path -to [get_ports debug_pc_src_o]
set_false_path -to [get_ports debug_state_o]
set_false_path -to [get_ports debug_ebreak_o]

# APB and AXI ports share the same clk_i clock domain — no false/cross-domain
# path exceptions are needed here.  The STA tool resolves all timing through
# the normal single-clock path analysis (group_path PIPELINE above).
# If an asynchronous APB clock is introduced in a future phase, add:
#   create_clock -name apb_clk -period <T> [get_ports apb_pclk_i]
#   set_clock_groups -asynchronous -group {clk_i} -group {apb_clk}

#---------------------------------------------
# Multicycle Paths - Cache SRAM arrays. No set_multicycle_path is needed or correct here.
# CS_SRAM_LATCH (rv32i_cache_pkg.sv) registers the SRAM dout buses into tag_dout_r and data_dout_r at posedge N+1.
# CS_TAG_CHECK at posedge N+2 sources all combinational logic from those registers.
# The path from negedge N to tag_dout_r (posedge N+1) is wire-only and fits the half-period window.
# The path from tag_dout_r (posedge N+1) to state_q (posedge N+2) takes a full period.

#---------------------------------------------
# Path Groups — prioritise pipeline critical paths
#---------------------------------------------

# Single path group covering all register-to-register paths.
# The cache FSM group_path constraints were removed because after synthesis
# the state_q flip-flops receive auto-generated cell names and cannot be
# referenced by their pre-synthesis hierarchical name.
group_path -name PIPELINE -from [get_clocks clk_i] -to [get_clocks clk_i]

#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------

set_load 0.05 [all_outputs]

# Input drive (uncomment with PDK cell name during physical implementation):
# set_driving_cell -lib_cell BUF_X1 -library sky130_fd_sc_hd [all_inputs]

#---------------------------------------------
# Area Constraint
#---------------------------------------------

# set_max_area 0 does NOT mean "use zero area".  In standard SDC/Yosys
# semantics a value of 0 means "unconstrained" — the tool is free to use
# as much area as needed and will prioritise timing closure instead.
# To add a hard area limit, replace 0 with the target cell-count or µm².
set_max_area 0

#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------

set_max_transition 0.5 [current_design]
set_max_capacitance 0.1 [all_outputs]
set_max_fanout 16 [current_design]

#---------------------------------------------
# End of SDC
#---------------------------------------------
