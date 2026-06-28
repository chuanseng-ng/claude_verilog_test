#=============================================
# Sky130 Stage 1: rv32i_cpu_top standalone
# Target: 75 MHz (13.333 ns period) — Sky130 130nm, SRAM-based caches
# File: sky130_cpu.sdc
#
# Extends phase3_cache.sdc with:
#   - AXI4 burst ports added in Phase 5 M2 (arlen/arsize/arburst/rlast,
#     awlen/awsize/awburst, wlast) — required for real DRC/LVS run because
#     all ports must be constrained for clean sign-off STA.
#
# Architecture:
#   5-stage pipeline with EX sub-stages (EX1a/EX1b/EX1c/EX2, from ASAP7 runs)
#   I-Cache: 4 KB direct-mapped (rv32i_icache — u_icache)
#   D-Cache: 4 KB write-back/write-allocate (rv32i_dcache — u_dcache)
#   Cache arbiter: single AXI4 burst port, D$ priority (rv32i_cache_arbiter)
#   M7 perf counters: mcycle/minstret/mhpmcounter3-5 in rv32i_csr_file
#
# Sky130 timing characteristics (sky130_fd_sc_hd TT 1.8V 25C):
#   FF setup:       ~0.4–0.6 ns
#   FF hold:        ~0.2–0.3 ns
#   Clock jitter:   ~0.1 ns
#   Documented fmax ceiling: ~100–120 MHz for this pipeline topology
#=============================================

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Primary clock — 75 MHz = 13.333 ns period
create_clock -name clk_i -period 13.333 [get_ports clk_i]

# Clock uncertainty — 0.5 ns setup / 0.2 ns hold
set_clock_uncertainty        0.5 [get_clocks clk_i]
set_clock_uncertainty -hold  0.2 [get_clocks clk_i]

# Clock latency (source: external oscillator or SoC PLL)
set_clock_latency -source 1.0 [get_clocks clk_i]


#---------------------------------------------
# Input Constraints — AXI4 channels
#---------------------------------------------
# 2 ns max input delay (generous at 75 MHz; ~15% of period)

# AXI4-Lite / AXI4 ready signals
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
set_input_delay -clock clk_i -max 2.0 [get_ports {axi_rdata_i[*]}]
set_input_delay -clock clk_i -max 2.0 [get_ports {axi_rresp_i[*]}]
set_input_delay -clock clk_i -max 2.0 [get_ports axi_rvalid_i]
set_input_delay -clock clk_i -min 0.5 [get_ports {axi_rdata_i[*]}]
set_input_delay -clock clk_i -min 0.5 [get_ports {axi_rresp_i[*]}]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_rvalid_i]

# AXI4 burst: rlast (read last beat indicator — input)
set_input_delay -clock clk_i -max 2.0 [get_ports axi_rlast_i]
set_input_delay -clock clk_i -min 0.5 [get_ports axi_rlast_i]


#---------------------------------------------
# Input Constraints — APB3 Debug Interface
#---------------------------------------------
set_input_delay -clock clk_i -max 3.5 [get_ports {apb_paddr_i[*]}]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_psel_i]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_penable_i]
set_input_delay -clock clk_i -max 3.5 [get_ports apb_pwrite_i]
set_input_delay -clock clk_i -max 3.5 [get_ports {apb_pwdata_i[*]}]
set_input_delay -clock clk_i -min 1.0 [get_ports {apb_paddr_i[*]}]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_psel_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_penable_i]
set_input_delay -clock clk_i -min 1.0 [get_ports apb_pwrite_i]
set_input_delay -clock clk_i -min 1.0 [get_ports {apb_pwdata_i[*]}]


#---------------------------------------------
# Output Constraints — AXI4 channels
#---------------------------------------------

# Write address channel
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_awaddr_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_awvalid_o]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_awaddr_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_awvalid_o]

# AXI4 burst: write address channel
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_awlen_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_awsize_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_awburst_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_awlen_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_awsize_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_awburst_o[*]}]

# Write data channel
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_wdata_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_wstrb_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_wvalid_o]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_wdata_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_wstrb_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_wvalid_o]

# AXI4 burst: wlast (write last beat indicator — output)
set_output_delay -clock clk_i -max 2.0 [get_ports axi_wlast_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_wlast_o]

# Write response ready
set_output_delay -clock clk_i -max 2.0 [get_ports axi_bready_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_bready_o]

# Read address channel
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_araddr_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports axi_arvalid_o]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_araddr_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_arvalid_o]

# AXI4 burst: read address channel
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_arlen_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_arsize_o[*]}]
set_output_delay -clock clk_i -max 2.0 [get_ports {axi_arburst_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_arlen_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_arsize_o[*]}]
set_output_delay -clock clk_i -min 0.5 [get_ports {axi_arburst_o[*]}]

# Read data ready
set_output_delay -clock clk_i -max 2.0 [get_ports axi_rready_o]
set_output_delay -clock clk_i -min 0.5 [get_ports axi_rready_o]


#---------------------------------------------
# Output Constraints — APB3 Debug Interface
#---------------------------------------------
set_output_delay -clock clk_i -max 3.5 [get_ports {apb_prdata_o[*]}]
set_output_delay -clock clk_i -max 3.5 [get_ports apb_pready_o]
set_output_delay -clock clk_i -max 3.5 [get_ports apb_pslverr_o]
set_output_delay -clock clk_i -min 1.0 [get_ports {apb_prdata_o[*]}]
set_output_delay -clock clk_i -min 1.0 [get_ports apb_pready_o]
set_output_delay -clock clk_i -min 1.0 [get_ports apb_pslverr_o]


#---------------------------------------------
# Multicycle Paths — APB3 Debug Interface
#---------------------------------------------
set_multicycle_path -setup 2 -to   [get_ports apb_pready_o]
set_multicycle_path -hold  1 -to   [get_ports apb_pready_o]
set_multicycle_path -setup 2 -from [get_ports {apb_paddr_i[*]}] -to [get_ports apb_pslverr_o]
set_multicycle_path -hold  1 -from [get_ports {apb_paddr_i[*]}] -to [get_ports apb_pslverr_o]


#---------------------------------------------
# False Paths
#---------------------------------------------

# Asynchronous reset
set_false_path -from [get_ports rst_n_i]

# Interrupt inputs (synchronisation is inside interrupt_ctrl)
set_false_path -from [get_ports ext_irq_i]
set_false_path -from [get_ports timer_irq_i]

# Verification observability outputs
set_false_path -to [get_ports commit_valid_o]
set_false_path -to [get_ports {commit_pc_o[*]}]
set_false_path -to [get_ports {commit_insn_o[*]}]
set_false_path -to [get_ports trap_taken_o]
set_false_path -to [get_ports {trap_cause_o[*]}]

# Debug observability outputs
set_false_path -to [get_ports {debug_rs1_data_o[*]}]
set_false_path -to [get_ports {debug_rs2_data_o[*]}]
set_false_path -to [get_ports debug_branch_taken_o]
set_false_path -to [get_ports debug_take_branch_jump_o]
set_false_path -to [get_ports {debug_pc_src_o[*]}]
set_false_path -to [get_ports {debug_state_o[*]}]
set_false_path -to [get_ports debug_ebreak_o]


#---------------------------------------------
# Path Groups — pipeline critical paths
#---------------------------------------------
group_path -name PIPELINE -from [get_clocks clk_i] -to [get_clocks clk_i]


#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------
set_load 0.05 [all_outputs]
set_max_area 0


#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------
set_max_transition  0.5  [current_design]
set_max_capacitance 0.1  [all_outputs]
set_max_fanout      16   [current_design]

#---------------------------------------------
# End of SDC
#---------------------------------------------
