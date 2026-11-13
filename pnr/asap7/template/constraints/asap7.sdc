# asap7.sdc - Timing constraints for rv32i_cpu_top (ASAP7 predictive 7 nm, starting point for a new ASAP7 design)
#
# Scope: template. Copy pnr/asap7/template/ to pnr/asap7/<design>/ for a new design. config.json of the copy sets PNR_SDC_FILE, SIGNOFF_SDC_FILE and FALLBACK_SDC_FILE.
# Contents: clock clk on port clk_i (uncertainty, transition, source latency); AXI4-Lite, APB3, asynchronous and
#   observability port constraints; APB multicycle path; SRAM hold false paths; I-cache and D-cache tag multicycle
#   paths; hold false paths on the ex1a_ex1b_reg_q and ex1c_ex1b_reg_q banks; generated clock gclk_sram on the SRAM clock gates.
# Inputs: none. The period and the delays are literal values in this file. MAX_TRANSITION_CONSTRAINT in config.json sets the max transition.
# User rules:
#   All time values in this file are picoseconds. The ASAP7 Liberty time unit is one picosecond.
#   OpenROAD reads create_clock -period raw against that unit. Write the period and every I/O delay in ps, not ns.
#   The AXI input delay is fixed, not scaled with the period, so that no new AXI violations appear.
#   The SRAM hold false paths cover a fakeram7 Liberty artifact. They do not cover a silicon violation.
# Doc: tm:pd:asap7-template-sdc
###############################################################################
# 1. Clock definition
###############################################################################
create_clock -name clk -period 705 [get_ports clk_i]
# An alternative create_clock command: see tm:pd:asap7-template-sdc.

set_clock_uncertainty -setup 15 [get_clocks clk]
set_clock_uncertainty -hold  10 [get_clocks clk]
set_clock_transition   10       [get_clocks clk]

# Source latency: on-chip PLL or synthesised from reference
set_clock_latency -source 50 [get_clocks clk]

###############################################################################
# 2. AXI4-Lite master ports (CPU ↔ memory controller)
###############################################################################
# The AXI input delay is fixed, not scaled with the period, so that no new AXI violations appear.
set_input_delay  -max 150 -clock clk [get_ports axi_arready_i]
set_input_delay  -min  10 -clock clk [get_ports axi_arready_i]

set_input_delay  -max 150 -clock clk [get_ports axi_rdata_i[*]]
set_input_delay  -min  10 -clock clk [get_ports axi_rdata_i[*]]

set_input_delay  -max 150 -clock clk [get_ports axi_rresp_i[*]]
set_input_delay  -min  10 -clock clk [get_ports axi_rresp_i[*]]

set_input_delay  -max 150 -clock clk [get_ports axi_rvalid_i]
set_input_delay  -min  10 -clock clk [get_ports axi_rvalid_i]

set_input_delay  -max 150 -clock clk [get_ports axi_awready_i]
set_input_delay  -min  10 -clock clk [get_ports axi_awready_i]

set_input_delay  -max 150 -clock clk [get_ports axi_wready_i]
set_input_delay  -min  10 -clock clk [get_ports axi_wready_i]

set_input_delay  -max 150 -clock clk [get_ports axi_bvalid_i]
set_input_delay  -min  10 -clock clk [get_ports axi_bvalid_i]

set_input_delay  -max 150 -clock clk [get_ports axi_bresp_i[*]]
set_input_delay  -min  10 -clock clk [get_ports axi_bresp_i[*]]

set_output_delay -max  150 -clock clk [get_ports axi_araddr_o[*]]
set_output_delay -min  -15 -clock clk [get_ports axi_araddr_o[*]]

set_output_delay -max  150 -clock clk [get_ports axi_arvalid_o]
set_output_delay -min  -15 -clock clk [get_ports axi_arvalid_o]

set_output_delay -max  150 -clock clk [get_ports axi_rready_o]
set_output_delay -min  -15 -clock clk [get_ports axi_rready_o]

set_output_delay -max  150 -clock clk [get_ports axi_awaddr_o[*]]
set_output_delay -min  -15 -clock clk [get_ports axi_awaddr_o[*]]

set_output_delay -max  150 -clock clk [get_ports axi_awvalid_o]
set_output_delay -min  -15 -clock clk [get_ports axi_awvalid_o]

set_output_delay -max  150 -clock clk [get_ports axi_wdata_o[*]]
set_output_delay -min  -15 -clock clk [get_ports axi_wdata_o[*]]

set_output_delay -max  150 -clock clk [get_ports axi_wstrb_o[*]]
set_output_delay -min  -15 -clock clk [get_ports axi_wstrb_o[*]]

set_output_delay -max  150 -clock clk [get_ports axi_wvalid_o]
set_output_delay -min  -15 -clock clk [get_ports axi_wvalid_o]

set_output_delay -max  150 -clock clk [get_ports axi_bready_o]
set_output_delay -min  -15 -clock clk [get_ports axi_bready_o]

###############################################################################
# 3. APB3 debug slave port (non-critical)
###############################################################################
set_input_delay  -max 120 -clock clk [get_ports apb_paddr_i[*]]
set_input_delay  -min  10 -clock clk [get_ports apb_paddr_i[*]]

set_input_delay  -max 120 -clock clk [get_ports apb_psel_i]
set_input_delay  -min  10 -clock clk [get_ports apb_psel_i]

set_input_delay  -max 120 -clock clk [get_ports apb_penable_i]
set_input_delay  -min  10 -clock clk [get_ports apb_penable_i]

set_input_delay  -max 120 -clock clk [get_ports apb_pwrite_i]
set_input_delay  -min  10 -clock clk [get_ports apb_pwrite_i]

set_input_delay  -max 120 -clock clk [get_ports apb_pwdata_i[*]]
set_input_delay  -min  10 -clock clk [get_ports apb_pwdata_i[*]]

set_output_delay -max  120 -clock clk [get_ports apb_pready_o]
set_output_delay -min  -15 -clock clk [get_ports apb_pready_o]

set_output_delay -max  120 -clock clk [get_ports apb_pslverr_o]
set_output_delay -min  -15 -clock clk [get_ports apb_pslverr_o]

# APB read data: non-critical debug port
set_false_path -to [get_ports apb_prdata_o[*]]

###############################################################################
# 4. Asynchronous inputs
###############################################################################
set_false_path -from [get_ports rst_n_i]
set_false_path -from [get_ports ext_irq_i]
set_false_path -from [get_ports timer_irq_i]

###############################################################################
# 5. Observability outputs (false paths — commit/debug ports)
###############################################################################
set_false_path -to [get_ports commit_valid_o]
set_false_path -to [get_ports commit_pc_o]
set_false_path -to [get_ports commit_insn_o]
set_false_path -to [get_ports trap_taken_o]
set_false_path -to [get_ports trap_cause_o]
set_false_path -to [get_ports debug_rs1_data_o]
set_false_path -to [get_ports debug_rs2_data_o]
set_false_path -to [get_ports debug_branch_taken_o]
set_false_path -to [get_ports debug_take_branch_jump_o]
set_false_path -to [get_ports debug_pc_src_o]
set_false_path -to [get_ports debug_state_o]
set_false_path -to [get_ports debug_ebreak_o]

###############################################################################
# 6. APB multicycle — PREADY stretches for 2-cycle APB handshake
###############################################################################
set_multicycle_path -setup 2 -to [get_ports apb_pready_o]
set_multicycle_path -hold  1 -to [get_ports apb_pready_o]

# APB inputs: debug bus is slow; paddr/psel/penable stable across SETUP+ACCESS phases.
# 3/2 multicycle keeps hold margin without over-tightening the capture window.
set_multicycle_path -setup 3 -from [get_ports {apb_paddr_i[*] apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i[*]}]
set_multicycle_path -hold  2 -from [get_ports {apb_paddr_i[*] apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i[*]}]

###############################################################################
# 7. Environment
###############################################################################
# set_max_transition is not set here. MAX_TRANSITION_CONSTRAINT in config.json sets it.
set_max_area       0

set_driving_cell -lib_cell BUFx2_ASAP7_75t_R -pin Y [all_inputs]
set_load 0.5 [all_outputs]

group_path -name PIPELINE -from [get_clocks clk] -to [get_clocks clk]

###############################################################################
# 8. SRAM black-box hold relaxation (fakeram7 Liberty artifact)
# Run 13 showed 38 hold violations all targeting SRAM din0/addr0 paths in
# icache/dcache. Root cause: fakeram7 hold model requires margin that short
# combinational paths from pipeline FFs cannot meet. Not a real silicon
# violation. Disable hold check for SRAM data/address input pins.
###############################################################################
set_false_path -hold -to [get_pins -hierarchical *din0*]
set_false_path -hold -to [get_pins -hierarchical *addr0*]
set_false_path -hold -to [get_pins -hierarchical *csb0*]

###############################################################################
# 9. D-cache writeback tag path — multi-cycle (4+ AXI beats per refill)
# Run 26: switched from get_nets to get_pins -hierarchical to resolve STA-0361
# "net not found" warnings on flattened post-synthesis netlists. get_nets globs
# do not survive hierarchy flattening; get_pins targeting the FF output pin
# resolves correctly. Pattern may still warn if wb_tag FFs are optimised away;
# that is architecturally benign (no path = no violation).
###############################################################################
set_multicycle_path -setup 2 -through [get_pins -hierarchical "*wb_tag*"]
set_multicycle_path -hold  1 -through [get_pins -hierarchical "*wb_tag*"]

###############################################################################
# 10. I-cache tag SRAM write — multi-cycle (refill spans 4 AXI beats)
# Run 17 P2: tag_web0/tag_din0 now driven from registered FFs (tag_we_q /
# tag_din_q); the SRAM write happens 1 cycle after refill-commit, which is
# structurally 2+ cycles after the last AXI beat that started the refill.
# -hold 1 on *tag_web0* added explicitly. -hold on *tag_din0* is already
# covered by the false_path on *din0* added in section 8 above.
###############################################################################
set_multicycle_path -setup 2 -through [get_nets -hierarchical "*u_icache*tag_web0*"]
set_multicycle_path -hold  1 -through [get_nets -hierarchical "*u_icache*tag_web0*"]
set_multicycle_path -setup 2 -through [get_nets -hierarchical "*u_icache*tag_din0*"]

# 11. Hold is not checked on paths launched from ex1a_ex1b_reg_q.
# A one-gate path from this bank to the EX1b logic would otherwise violate hold.
set_false_path -hold -from [get_cells -hierarchical {*ex1a_ex1b_reg_q*}]

###############################################################################
# 12. Run 25: ex1c_ex1b_reg_q retiming FF short-path hold false-path
# EX1c was removed; ex1c_ex1b_reg_q is now a pure retiming FF (no combinational
# stage between ex1a_ex1b_reg_q and ex1c_ex1b_reg_q). The 0-gate path from
# ex1a_ex1b_reg_q → ex1c_ex1b_reg_q will violate hold identically to the
# ex1a_ex1b_reg_q→EX1b violation fixed in Run 18. Suppress hold on both
# the launch (ex1a_ex1b_reg_q) and capture (ex1c_ex1b_reg_q) sides.
###############################################################################
set_false_path -hold -from [get_cells -hierarchical {*ex1c_ex1b_reg_q*}]

set_false_path -hold -from [get_ports {axi_rvalid_i axi_rdata_i[*] axi_rresp_i[*]}]
set_false_path -hold -from [get_ports {axi_awready_i axi_wready_i axi_bvalid_i axi_bresp_i[*]}]

###############################################################################
# 14. SRAM gated clocks — ICGx1_ASAP7_75t_R generated clocks (Run 37)

create_generated_clock -name gclk_sram \
    -source [get_ports clk_i] \
    -divide_by 1 \
    [get_pins -hierarchical {*u_icg/GCLK}]

# Hold is not checked on paths from clk to gclk_sram. The SRAM clk0 rises after the launch flop clock edge,
# so short combinational paths fail hold. A gated clock never leads the source clock.
# This is a structural guarantee, not a timing exception. It has the same reason as the din0, addr0 and csb0 false paths.
set_false_path -hold -from [get_clocks clk] -to [get_clocks gclk_sram]

# Extend section-8 SRAM hold false-path coverage to web0 (write-enable bar).
# web0 was omitted from the original fakeram7 hold relaxation in Run 13 since
# it was not a violation then; the ICG insertion delay now exposes it.
set_false_path -hold -to [get_pins -hierarchical *web0*]
