################################################################################
#
# Design name:  rv32i_cpu_top
#
# Created by icc2 write_sdc on Sat Nov  7 02:32:47 2026
#
################################################################################

set sdc_version 2.2
set_units -time ns -resistance kOhm -capacitance pF -voltage V -current mA

################################################################################
#
# Units
# time_unit               : 1e-09
# resistance_unit         : 1000
# capacitive_load_unit    : 1e-12
# voltage_unit            : 1
# current_unit            : 0.001
# power_unit              : 1e-09
################################################################################


# Mode: func
# Corner: tt
# Scenario: func_tt

# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 30; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 37
create_clock -name clk_i -period 13.333 -waveform {0 6.6665} [get_ports {clk_i}]
set_propagated_clock [get_clocks {clk_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 207
group_path -name PIPELINE -from [get_clocks {clk_i}] -to [get_clocks {clk_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 154; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 155
set_multicycle_path 1 -hold -to [get_ports {apb_pready_o}]
set_multicycle_path 2 -setup -to [get_ports {apb_pready_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 156; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 157
set_multicycle_path 1 -hold -from [get_ports {apb_paddr_i[11] apb_paddr_i[10] \
    apb_paddr_i[9] apb_paddr_i[8] apb_paddr_i[7] apb_paddr_i[6] apb_paddr_i[5] \
    apb_paddr_i[4] apb_paddr_i[3] apb_paddr_i[2] apb_paddr_i[1] \
    apb_paddr_i[0]}] -to [get_ports {apb_pslverr_o}]
set_multicycle_path 2 -setup -from [get_ports {apb_paddr_i[11] apb_paddr_i[10] \
    apb_paddr_i[9] apb_paddr_i[8] apb_paddr_i[7] apb_paddr_i[6] apb_paddr_i[5] \
    apb_paddr_i[4] apb_paddr_i[3] apb_paddr_i[2] apb_paddr_i[1] \
    apb_paddr_i[0]}] -to [get_ports {apb_pslverr_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 165
set_false_path -from [get_ports {rst_n_i ext_irq_i timer_irq_i scan_mode_i \
    scan_en_i scan_in_i[1] scan_in_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 185
set_false_path -to [get_ports {commit_valid_o commit_pc_o[31] commit_pc_o[30] \
    commit_pc_o[29] commit_pc_o[28] commit_pc_o[27] commit_pc_o[26] \
    commit_pc_o[25] commit_pc_o[24] commit_pc_o[23] commit_pc_o[22] \
    commit_pc_o[21] commit_pc_o[20] commit_pc_o[19] commit_pc_o[18] \
    commit_pc_o[17] commit_pc_o[16] commit_pc_o[15] commit_pc_o[14] \
    commit_pc_o[13] commit_pc_o[12] commit_pc_o[11] commit_pc_o[10] \
    commit_pc_o[9] commit_pc_o[8] commit_pc_o[7] commit_pc_o[6] commit_pc_o[5] \
    commit_pc_o[4] commit_pc_o[3] commit_pc_o[2] commit_pc_o[1] commit_pc_o[0] \
    commit_insn_o[31] commit_insn_o[30] commit_insn_o[29] commit_insn_o[28] \
    commit_insn_o[27] commit_insn_o[26] commit_insn_o[25] commit_insn_o[24] \
    commit_insn_o[23] commit_insn_o[22] commit_insn_o[21] commit_insn_o[20] \
    commit_insn_o[19] commit_insn_o[18] commit_insn_o[17] commit_insn_o[16] \
    commit_insn_o[15] commit_insn_o[14] commit_insn_o[13] commit_insn_o[12] \
    commit_insn_o[11] commit_insn_o[10] commit_insn_o[9] commit_insn_o[8] \
    commit_insn_o[7] commit_insn_o[6] commit_insn_o[5] commit_insn_o[4] \
    commit_insn_o[3] commit_insn_o[2] commit_insn_o[1] commit_insn_o[0] \
    trap_taken_o trap_cause_o[3] trap_cause_o[2] trap_cause_o[1] \
    trap_cause_o[0] debug_rs1_data_o[31] debug_rs1_data_o[30] \
    debug_rs1_data_o[29] debug_rs1_data_o[28] debug_rs1_data_o[27] \
    debug_rs1_data_o[26] debug_rs1_data_o[25] debug_rs1_data_o[24] \
    debug_rs1_data_o[23] debug_rs1_data_o[22] debug_rs1_data_o[21] \
    debug_rs1_data_o[20] debug_rs1_data_o[19] debug_rs1_data_o[18] \
    debug_rs1_data_o[17] debug_rs1_data_o[16] debug_rs1_data_o[15] \
    debug_rs1_data_o[14] debug_rs1_data_o[13] debug_rs1_data_o[12] \
    debug_rs1_data_o[11] debug_rs1_data_o[10] debug_rs1_data_o[9] \
    debug_rs1_data_o[8] debug_rs1_data_o[7] debug_rs1_data_o[6] \
    debug_rs1_data_o[5] debug_rs1_data_o[4] debug_rs1_data_o[3] \
    debug_rs1_data_o[2] debug_rs1_data_o[1] debug_rs1_data_o[0] \
    debug_rs2_data_o[31] debug_rs2_data_o[30] debug_rs2_data_o[29] \
    debug_rs2_data_o[28] debug_rs2_data_o[27] debug_rs2_data_o[26] \
    debug_rs2_data_o[25] debug_rs2_data_o[24] debug_rs2_data_o[23] \
    debug_rs2_data_o[22] debug_rs2_data_o[21] debug_rs2_data_o[20] \
    debug_rs2_data_o[19] debug_rs2_data_o[18] debug_rs2_data_o[17] \
    debug_rs2_data_o[16] debug_rs2_data_o[15] debug_rs2_data_o[14] \
    debug_rs2_data_o[13] debug_rs2_data_o[12] debug_rs2_data_o[11] \
    debug_rs2_data_o[10] debug_rs2_data_o[9] debug_rs2_data_o[8] \
    debug_rs2_data_o[7] debug_rs2_data_o[6] debug_rs2_data_o[5] \
    debug_rs2_data_o[4] debug_rs2_data_o[3] debug_rs2_data_o[2] \
    debug_rs2_data_o[1] debug_rs2_data_o[0] debug_branch_taken_o \
    debug_take_branch_jump_o debug_pc_src_o debug_state_o[3] debug_state_o[2] \
    debug_state_o[1] debug_state_o[0] debug_ebreak_o scan_out_o[1] scan_out_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[31]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[30]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[29]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[28]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[27]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[26]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[25]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[24]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[23]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[22]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[21]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[20]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[19]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[18]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[17]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[16]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[15]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[14]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[13]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[12]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[11]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[10]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[9]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[8]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[7]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[6]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[5]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[4]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[3]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_awaddr_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[7]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[6]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[5]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[4]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[3]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_awlen_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_awsize_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_awsize_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_awsize_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_awburst_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_awburst_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_awvalid_o}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[31]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[30]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[29]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[28]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[27]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[26]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[25]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[24]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[23]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[22]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[21]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[20]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[19]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[18]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[17]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[16]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[15]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[14]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[13]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[12]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[11]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[10]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[9]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[8]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[7]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[6]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[5]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[4]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[3]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_wdata_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_wstrb_o[3]}]
set_load -pin_load 0.05 [get_ports {axi_wstrb_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_wstrb_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_wstrb_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_wlast_o}]
set_load -pin_load 0.05 [get_ports {axi_wvalid_o}]
set_load -pin_load 0.05 [get_ports {axi_bready_o}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[31]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[30]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[29]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[28]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[27]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[26]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[25]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[24]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[23]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[22]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[21]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[20]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[19]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[18]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[17]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[16]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[15]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[14]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[13]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[12]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[11]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[10]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[9]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[8]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[7]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[6]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[5]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[4]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[3]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_araddr_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[7]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[6]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[5]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[4]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[3]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_arlen_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_arsize_o[2]}]
set_load -pin_load 0.05 [get_ports {axi_arsize_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_arsize_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_arburst_o[1]}]
set_load -pin_load 0.05 [get_ports {axi_arburst_o[0]}]
set_load -pin_load 0.05 [get_ports {axi_arvalid_o}]
set_load -pin_load 0.05 [get_ports {axi_rready_o}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[31]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[30]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[29]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[28]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[27]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[26]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[25]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[24]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[23]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[22]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[21]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[20]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[19]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[18]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[17]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[16]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[15]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[14]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[13]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[12]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[11]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[10]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[9]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[8]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[7]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[6]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[5]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[4]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[3]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[2]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[1]}]
set_load -pin_load 0.05 [get_ports {apb_prdata_o[0]}]
set_load -pin_load 0.05 [get_ports {apb_pready_o}]
set_load -pin_load 0.05 [get_ports {apb_pslverr_o}]
set_load -pin_load 0.05 [get_ports {commit_valid_o}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[31]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[30]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[29]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[28]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[27]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[26]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[25]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[24]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[23]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[22]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[21]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[20]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[19]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[18]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[17]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[16]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[15]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[14]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[13]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[12]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[11]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[10]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[9]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[8]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[7]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[6]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[5]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[4]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[3]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[2]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[1]}]
set_load -pin_load 0.05 [get_ports {commit_pc_o[0]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[31]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[30]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[29]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[28]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[27]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[26]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[25]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[24]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[23]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[22]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[21]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[20]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[19]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[18]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[17]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[16]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[15]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[14]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[13]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[12]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[11]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[10]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[9]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[8]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[7]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[6]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[5]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[4]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[3]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[2]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[1]}]
set_load -pin_load 0.05 [get_ports {commit_insn_o[0]}]
set_load -pin_load 0.05 [get_ports {trap_taken_o}]
set_load -pin_load 0.05 [get_ports {trap_cause_o[3]}]
set_load -pin_load 0.05 [get_ports {trap_cause_o[2]}]
set_load -pin_load 0.05 [get_ports {trap_cause_o[1]}]
set_load -pin_load 0.05 [get_ports {trap_cause_o[0]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[31]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[30]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[29]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[28]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[27]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[26]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[25]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[24]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[23]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[22]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[21]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[20]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[19]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[18]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[17]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[16]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[15]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[14]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[13]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[12]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[11]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[10]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[9]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[8]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[7]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[6]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[5]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[4]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[3]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[2]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[1]}]
set_load -pin_load 0.05 [get_ports {debug_rs1_data_o[0]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[31]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[30]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[29]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[28]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[27]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[26]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[25]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[24]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[23]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[22]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[21]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[20]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[19]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[18]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[17]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[16]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[15]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[14]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[13]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[12]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[11]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[10]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[9]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[8]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[7]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[6]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[5]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[4]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[3]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[2]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[1]}]
set_load -pin_load 0.05 [get_ports {debug_rs2_data_o[0]}]
set_load -pin_load 0.05 [get_ports {debug_branch_taken_o}]
set_load -pin_load 0.05 [get_ports {debug_take_branch_jump_o}]
set_load -pin_load 0.05 [get_ports {debug_pc_src_o}]
set_load -pin_load 0.05 [get_ports {debug_state_o[3]}]
set_load -pin_load 0.05 [get_ports {debug_state_o[2]}]
set_load -pin_load 0.05 [get_ports {debug_state_o[1]}]
set_load -pin_load 0.05 [get_ports {debug_state_o[0]}]
set_load -pin_load 0.05 [get_ports {debug_ebreak_o}]
set_load -pin_load 0.05 [get_ports {scan_out_o[1]}]
set_load -pin_load 0.05 [get_ports {scan_out_o[0]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[68]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[67]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[66]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[65]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[64]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[63]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[62]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[61]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[60]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[59]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[58]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[57]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[56]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[55]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[54]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[53]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[52]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[51]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[50]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[49]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[48]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[47]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[46]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[45]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[44]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[43]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[42]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[41]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[40]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[39]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[38]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[37]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[36]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[35]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[34]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[33]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[32]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[31]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[30]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[29]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[28]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[27]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[26]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[25]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[24]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[23]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[22]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[21]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[20]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[19]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[18]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[17]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[16]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[15]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[14]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[13]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[12]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[11]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[10]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[9]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[8]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[7]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[6]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[5]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[4]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[3]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[2]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[1]}]
set_load -pin_load 0.05 [get_ports {mbist_status_o[0]}]
# Warning: Libcell power domain derates are skipped!

set_clock_latency -source 1 [get_clocks {clk_i}]
# Set latency for io paths.
# -origin useful_skew
set_clock_latency 1.88164 [get_clocks {clk_i}]
# Set propagated on clock sources to avoid removing latency for IO paths.
set_propagated_clock  [get_ports {clk_i}]
set_clock_uncertainty -setup 0.5 [get_clocks {clk_i}]
set_clock_uncertainty -hold 0.2 [get_clocks {clk_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports {clk_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports {rst_n_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_awready_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_wready_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_bresp_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_bresp_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_bvalid_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_arready_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rdata_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rresp_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rresp_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rvalid_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {axi_rlast_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_paddr_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_psel_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_penable_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwrite_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {apb_pwdata_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports {ext_irq_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {timer_irq_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {scan_mode_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports {scan_en_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {scan_in_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {scan_in_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_run_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 216
set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X [get_ports \
    {mbist_cfg_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[31]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[30]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[29]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[28]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[27]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[26]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[25]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[24]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[23]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[22]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[21]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[20]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[19]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[18]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[17]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[16]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[15]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[14]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[13]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[12]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[11]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[10]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[9]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[8]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[7]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[6]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[5]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[4]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 92; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 94
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awaddr_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awaddr_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[7]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[6]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[5]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[4]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 98; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 101
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awlen_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awlen_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 99; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 102
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awsize_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awsize_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 99; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 102
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awsize_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awsize_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 99; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 102
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awsize_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awsize_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 100; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 103
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awburst_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awburst_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 100; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 103
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awburst_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_awburst_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 93; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 95
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_awvalid_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awvalid_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 46; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 49
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_awready_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_awready_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[31]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[30]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[29]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[28]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[27]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[26]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[25]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[24]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[23]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[22]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[21]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[20]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[19]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[18]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[17]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[16]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[15]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[14]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[13]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[12]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[11]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[10]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_wdata_o[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[9]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[8]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[7]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[6]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[5]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[4]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 106; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 109
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wdata_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wdata_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 107; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 110
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wstrb_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wstrb_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 107; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 110
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wstrb_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wstrb_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 107; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 110
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wstrb_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wstrb_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 107; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 110
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_wstrb_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wstrb_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 114; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 115
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_wlast_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wlast_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 108; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 111
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_wvalid_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wvalid_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 47; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 50
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_wready_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_wready_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 54; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 56
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_bresp_i[1]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_bresp_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 54; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 56
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_bresp_i[0]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_bresp_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 55; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 57
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_bvalid_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_bvalid_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 118; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 119
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_bready_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_bready_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[31]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[30]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[29]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[28]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[27]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[26]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[25]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[24]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[23]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[22]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[21]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[20]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[19]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[18]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[17]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[16]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[15]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[14]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[13]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[12]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[11]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[10]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[9]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[8]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[7]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[6]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[5]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[4]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 122; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 124
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_araddr_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_araddr_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[7]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[6]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[5]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[4]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 128; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 131
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arlen_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arlen_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 129; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 132
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arsize_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_arsize_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 129; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 132
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arsize_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_arsize_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 129; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 132
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arsize_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_arsize_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 130; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 133
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arburst_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_arburst_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 130; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 133
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arburst_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports \
    {axi_arburst_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 123; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 125
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_arvalid_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arvalid_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 48; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 51
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_arready_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_arready_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[31]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[30]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[29]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[28]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[27]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[26]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[25]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[24]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[23]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[22]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[21]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[20]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[19]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[18]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[17]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[16]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[15]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[14]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[13]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[12]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[11]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[10]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[9]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[8]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[7]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[6]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[5]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[4]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[3]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[2]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[1]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 60; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 63
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rdata_i[0]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rdata_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 61; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 64
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rresp_i[1]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rresp_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 61; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 64
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports \
    {axi_rresp_i[0]}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rresp_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 62; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 65
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_rvalid_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rvalid_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 68; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 69
set_input_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_rlast_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rlast_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 136; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 137
set_output_delay -clock [get_clocks {clk_i}] -min 0.5 [get_ports {axi_rready_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 2 [get_ports {axi_rready_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[11]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[10]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[9]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[8]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[7]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[6]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[5]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[4]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[3]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[2]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[1]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 75; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 80
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_paddr_i[0]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_paddr_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 76; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 81
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_psel_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports {apb_psel_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 77; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 82
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_penable_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports {apb_penable_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 78; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 83
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwrite_i}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports {apb_pwrite_i}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[31]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[30]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[29]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[28]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[27]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[26]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[25]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[24]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[23]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[22]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[21]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[20]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[19]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[18]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[17]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[16]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[15]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[14]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[13]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[12]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[11]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_pwdata_i[10]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[9]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[8]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[7]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[6]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[5]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[4]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[3]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[2]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[1]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 79; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 84
set_input_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pwdata_i[0]}]
set_input_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pwdata_i[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[31]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[31]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[30]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[30]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[29]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[29]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[28]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[28]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[27]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[27]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[26]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[26]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[25]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[25]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[24]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[24]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[23]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[23]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[22]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[22]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[21]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[21]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[20]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[20]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[19]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[19]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[18]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[18]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[17]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[17]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[16]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[16]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[15]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[15]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[14]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[14]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[13]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[13]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[12]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[12]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[11]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[11]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[10]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[10]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[9]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[9]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[8]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[8]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[7]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[7]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[6]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[6]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[5]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[5]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[4]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[4]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[3]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[3]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[2]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[2]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[1]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[1]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 143; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 146
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports \
    {apb_prdata_o[0]}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_prdata_o[0]}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 144; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 147
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pready_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports {apb_pready_o}]
# /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 145; \
#   /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc, \
#   line 148
set_output_delay -clock [get_clocks {clk_i}] -min 1 [get_ports {apb_pslverr_o}]
set_output_delay -clock [get_clocks {clk_i}] -max 3.5 [get_ports \
    {apb_pslverr_o}]
set_max_transition 0.5 [current_design]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[31]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[30]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[29]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[28]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[27]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[26]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[25]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[24]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[23]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[22]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[21]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[20]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[19]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[18]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[17]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[16]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[15]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[14]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[13]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[12]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[11]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[10]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[9]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[8]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[7]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[6]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[5]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[4]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[3]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_awaddr_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[7]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[6]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[5]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[4]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[3]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_awlen_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_awsize_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_awsize_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_awsize_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_awburst_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_awburst_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_awvalid_o}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[31]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[30]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[29]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[28]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[27]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[26]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[25]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[24]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[23]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[22]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[21]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[20]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[19]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[18]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[17]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[16]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[15]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[14]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[13]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[12]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[11]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[10]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[9]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[8]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[7]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[6]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[5]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[4]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[3]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_wdata_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_wstrb_o[3]}]
set_max_capacitance 0.1 [get_ports {axi_wstrb_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_wstrb_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_wstrb_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_wlast_o}]
set_max_capacitance 0.1 [get_ports {axi_wvalid_o}]
set_max_capacitance 0.1 [get_ports {axi_bready_o}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[31]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[30]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[29]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[28]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[27]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[26]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[25]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[24]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[23]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[22]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[21]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[20]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[19]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[18]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[17]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[16]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[15]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[14]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[13]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[12]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[11]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[10]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[9]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[8]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[7]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[6]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[5]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[4]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[3]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_araddr_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[7]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[6]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[5]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[4]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[3]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_arlen_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_arsize_o[2]}]
set_max_capacitance 0.1 [get_ports {axi_arsize_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_arsize_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_arburst_o[1]}]
set_max_capacitance 0.1 [get_ports {axi_arburst_o[0]}]
set_max_capacitance 0.1 [get_ports {axi_arvalid_o}]
set_max_capacitance 0.1 [get_ports {axi_rready_o}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[31]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[30]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[29]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[28]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[27]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[26]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[25]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[24]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[23]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[22]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[21]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[20]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[19]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[18]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[17]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[16]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[15]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[14]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[13]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[12]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[11]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[10]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[9]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[8]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[7]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[6]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[5]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[4]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[3]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[2]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[1]}]
set_max_capacitance 0.1 [get_ports {apb_prdata_o[0]}]
set_max_capacitance 0.1 [get_ports {apb_pready_o}]
set_max_capacitance 0.1 [get_ports {apb_pslverr_o}]
set_max_capacitance 0.1 [get_ports {commit_valid_o}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[31]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[30]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[29]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[28]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[27]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[26]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[25]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[24]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[23]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[22]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[21]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[20]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[19]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[18]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[17]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[16]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[15]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[14]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[13]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[12]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[11]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[10]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[9]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[8]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[7]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[6]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[5]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[4]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[3]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[2]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[1]}]
set_max_capacitance 0.1 [get_ports {commit_pc_o[0]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[31]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[30]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[29]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[28]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[27]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[26]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[25]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[24]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[23]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[22]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[21]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[20]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[19]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[18]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[17]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[16]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[15]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[14]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[13]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[12]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[11]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[10]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[9]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[8]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[7]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[6]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[5]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[4]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[3]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[2]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[1]}]
set_max_capacitance 0.1 [get_ports {commit_insn_o[0]}]
set_max_capacitance 0.1 [get_ports {trap_taken_o}]
set_max_capacitance 0.1 [get_ports {trap_cause_o[3]}]
set_max_capacitance 0.1 [get_ports {trap_cause_o[2]}]
set_max_capacitance 0.1 [get_ports {trap_cause_o[1]}]
set_max_capacitance 0.1 [get_ports {trap_cause_o[0]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[31]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[30]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[29]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[28]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[27]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[26]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[25]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[24]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[23]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[22]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[21]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[20]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[19]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[18]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[17]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[16]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[15]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[14]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[13]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[12]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[11]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[10]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[9]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[8]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[7]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[6]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[5]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[4]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[3]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[2]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[1]}]
set_max_capacitance 0.1 [get_ports {debug_rs1_data_o[0]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[31]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[30]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[29]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[28]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[27]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[26]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[25]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[24]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[23]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[22]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[21]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[20]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[19]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[18]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[17]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[16]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[15]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[14]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[13]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[12]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[11]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[10]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[9]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[8]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[7]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[6]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[5]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[4]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[3]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[2]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[1]}]
set_max_capacitance 0.1 [get_ports {debug_rs2_data_o[0]}]
set_max_capacitance 0.1 [get_ports {debug_branch_taken_o}]
set_max_capacitance 0.1 [get_ports {debug_take_branch_jump_o}]
set_max_capacitance 0.1 [get_ports {debug_pc_src_o}]
set_max_capacitance 0.1 [get_ports {debug_state_o[3]}]
set_max_capacitance 0.1 [get_ports {debug_state_o[2]}]
set_max_capacitance 0.1 [get_ports {debug_state_o[1]}]
set_max_capacitance 0.1 [get_ports {debug_state_o[0]}]
set_max_capacitance 0.1 [get_ports {debug_ebreak_o}]
set_max_capacitance 0.1 [get_ports {scan_out_o[1]}]
set_max_capacitance 0.1 [get_ports {scan_out_o[0]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[68]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[67]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[66]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[65]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[64]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[63]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[62]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[61]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[60]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[59]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[58]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[57]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[56]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[55]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[54]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[53]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[52]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[51]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[50]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[49]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[48]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[47]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[46]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[45]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[44]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[43]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[42]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[41]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[40]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[39]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[38]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[37]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[36]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[35]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[34]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[33]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[32]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[31]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[30]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[29]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[28]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[27]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[26]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[25]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[24]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[23]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[22]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[21]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[20]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[19]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[18]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[17]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[16]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[15]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[14]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[13]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[12]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[11]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[10]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[9]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[8]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[7]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[6]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[5]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[4]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[3]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[2]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[1]}]
set_max_capacitance 0.1 [get_ports {mbist_status_o[0]}]
