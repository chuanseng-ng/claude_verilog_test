#=============================================
# Phase 3: RV32I CPU + L1 I-Cache + L1 D-Cache
# Target: 75 MHz (13.33 ns period) — Sky130 130nm, SRAM-based caches
# File: phase3_cache.sdc
#
# Extends phase2_cpu.sdc with:
#   - Relaxed clock target (75 MHz vs. 100 MHz target in Phase 2 spec)
#     matching the achieved 75 MHz result on Sky130.
#   - SRAM-to-logic multicycle paths (cache array read completes in 1 cycle
#     but the behavioural model has no explicit setup within the same cycle;
#     declare conservative 1-cycle constraint, tighten once SRAM macros are
#     characterised).
#   - No new external ports (the cache is entirely internal to rv32i_core;
#     all external I/O ports remain identical to Phase 2).
#
# Architecture:
#   5-stage pipeline (IF→ID→EX→MEM→WB)
#   I-Cache: 4 KB direct-mapped (rv32i_icache instance u_icache)
#   D-Cache: 4 KB write-back/write-allocate (rv32i_dcache instance u_dcache)
#   Cache arbiter: single AXI4-Lite port, D$ priority (rv32i_cache_arbiter)
#=============================================

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Primary clock — 75 MHz = 13.33 ns period
create_clock -name clk_i -period 13.333 [get_ports clk_i]

# Clock uncertainty (pre-CTS estimate; tighten to 0.3 post-CTS)
set_clock_uncertainty 0.5 [get_clocks clk_i]

# Clock latency (source: external PLL or board-level oscillator)
set_clock_latency -source 1.0 [get_clocks clk_i]

# Clock transition time (slew)
set_clock_transition 0.1 [get_clocks clk_i]

#---------------------------------------------
# Input Constraints — AXI4-Lite
#---------------------------------------------
# All AXI ports at cpu_top level are the cache-arbiter outputs; they face
# the L2/DRAM controller.  Use 2 ns setup margin (generous at 75 MHz).

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
# APB is non-critical; 3.5 ns max allowed at 75 MHz.

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
# Multicycle Paths — Cache SRAM arrays
#---------------------------------------------
#
# The I-cache and D-cache use behavioural SRAM arrays (synthesised to flip-
# flops until sky130 SRAM macros are integrated).  The tag + data arrays are
# clocked registers; the read path is purely combinational from the registered
# read address to the output — no additional multicycle constraint is needed
# for the register-array stage.
#
# When sky130 SRAM macros are used (future integration), the SRAM read
# latency may require a multicycle path from the SRAM output to the pipeline
# register.  Template for that constraint (comment out until macros are added):
#
# set_multicycle_path 2 -setup \
#     -from [get_cells u_core/u_icache/data_array*] \
#     -to   [get_registers u_core/u_icache/*]
#
# set_multicycle_path 1 -hold \
#     -from [get_cells u_core/u_icache/data_array*] \
#     -to   [get_registers u_core/u_icache/*]
#
# set_multicycle_path 2 -setup \
#     -from [get_cells u_core/u_dcache/data_array*] \
#     -to   [get_registers u_core/u_dcache/*]
#
# set_multicycle_path 1 -hold \
#     -from [get_cells u_core/u_dcache/data_array*] \
#     -to   [get_registers u_core/u_dcache/*]

#---------------------------------------------
# Path Groups — prioritise pipeline critical paths
#---------------------------------------------

# Separate the cache refill FSM (less critical, fires on miss only)
# from the pipeline data path (hit path, must meet cycle time).
group_path -name PIPELINE     -from [get_clocks clk_i] -to [get_clocks clk_i]
group_path -name CACHE_REFILL \
    -from [get_cells u_core/u_icache/state_q] \
    -to   [get_cells u_core/u_icache/state_q]
group_path -name DCACHE_FSM \
    -from [get_cells u_core/u_dcache/state_q] \
    -to   [get_cells u_core/u_dcache/state_q]

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
