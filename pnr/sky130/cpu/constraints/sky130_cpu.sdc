# sky130_cpu.sdc - Timing constraints for rv32i_cpu_top standalone on Sky130 (Stage 1, clock clk_i)
#
# Scope: pnr/sky130/cpu/config.json sets PNR_SDC_FILE (and the sign-off SDC keys) to this file.
#   sta_load_sky130_soc.tcl uses it as the default SDC for the CPU macro.
# Contents: it extends phase3_cache.sdc with the AXI4 burst ports added in Phase 5 (arlen, arsize, arburst, rlast,
#   awlen, awsize, awburst, wlast). Also clock clk_i and the AXI4 and APB3 delays.
#   The design is the five-stage pipeline with the EX sub-stages, two 4 KB caches, a cache arbiter and the performance counters.
# Inputs: none. All time values in this file are in ns.
# User rules:
#   Constrain every port. The real DRC and LVS run needs all ports constrained for a clean sign-off STA.
#   Sky130 limits this pipeline topology to a documented frequency ceiling. See tm:pd:sky130-cpu-sdc.
# Doc: tm:pd:sky130-cpu-sdc
# Primary clock.
create_clock -name clk_i -period 13.333 [get_ports clk_i]

# Clock uncertainty: setup and hold.
set_clock_uncertainty        0.5 [get_clocks clk_i]
set_clock_uncertainty -hold  0.2 [get_clocks clk_i]

# Clock latency (source: external oscillator or SoC PLL)
set_clock_latency -source 1.0 [get_clocks clk_i]


#---------------------------------------------
# Input Constraints — AXI4 channels
#---------------------------------------------
# A generous max input delay at the target frequency.

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

set_false_path -from [get_ports scan_mode_i]
set_false_path -from [get_ports scan_en_i]
set_false_path -from [get_ports {scan_in_i[*]}]
set_false_path -to   [get_ports {scan_out_o[*]}]

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
set_false_path -to [get_ports debug_pc_src_o]
set_false_path -to [get_ports {debug_state_o[*]}]
set_false_path -to [get_ports debug_ebreak_o]


#---------------------------------------------
# Path Groups — pipeline critical paths
#---------------------------------------------
group_path -name PIPELINE -from [get_clocks clk_i] -to [get_clocks clk_i]


#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------
# Input drive: sky130_fd_sc_hd__buf_4 models a typical upstream driver strength.
# Without this, OpenROAD STA computes zero input slew which over-optimises
# hold margins and under-estimates input-path delay on setup.
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [all_inputs]
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
