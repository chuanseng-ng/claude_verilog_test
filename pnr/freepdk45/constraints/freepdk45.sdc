###############################################################################
# freepdk45.sdc — Timing constraints for rv32i_cpu_top on FreePDK45 / nangate45
# Target: 400 MHz (2.500 ns) — 45nm predictive node, OpenRAM SRAM macros
###############################################################################

###############################################################################
# 1. Clock definition
###############################################################################
create_clock -name clk -period 2.500 [get_ports clk_i]

set_clock_uncertainty -setup 0.08 [get_clocks clk]
set_clock_uncertainty -hold  0.10 [get_clocks clk]

set_clock_transition 0.07 [get_clocks clk]

###############################################################################
# 2. AXI4-Lite master port timing (CPU → memory)
###############################################################################
# Input delays on AXI slave-side inputs (address/write channels)
set_input_delay  -max 0.43 -clock clk [get_ports axi_arready_i]
set_input_delay  -min 0.04 -clock clk [get_ports axi_arready_i]

set_input_delay  -max 0.43 -clock clk [get_ports axi_rdata_i[*]]
set_input_delay  -min 0.04 -clock clk [get_ports axi_rdata_i[*]]

set_input_delay  -max 0.43 -clock clk [get_ports axi_rresp_i[*]]
set_input_delay  -min 0.04 -clock clk [get_ports axi_rresp_i[*]]

set_input_delay  -max 0.43 -clock clk [get_ports axi_rvalid_i]
set_input_delay  -min 0.04 -clock clk [get_ports axi_rvalid_i]

set_input_delay  -max 0.43 -clock clk [get_ports axi_awready_i]
set_input_delay  -min 0.04 -clock clk [get_ports axi_awready_i]

set_input_delay  -max 0.43 -clock clk [get_ports axi_wready_i]
set_input_delay  -min 0.04 -clock clk [get_ports axi_wready_i]

set_input_delay  -max 0.43 -clock clk [get_ports axi_bvalid_i]
set_input_delay  -min 0.04 -clock clk [get_ports axi_bvalid_i]

set_input_delay  -max 0.43 -clock clk [get_ports axi_bresp_i[*]]
set_input_delay  -min 0.04 -clock clk [get_ports axi_bresp_i[*]]

# Output delays on AXI master-side outputs
set_output_delay -max 0.43 -clock clk [get_ports axi_araddr_o[*]]
set_output_delay -min -0.1 -clock clk [get_ports axi_araddr_o[*]]

set_output_delay -max 0.43 -clock clk [get_ports axi_arvalid_o]
set_output_delay -min -0.1 -clock clk [get_ports axi_arvalid_o]

set_output_delay -max 0.43 -clock clk [get_ports axi_rready_o]
set_output_delay -min -0.1 -clock clk [get_ports axi_rready_o]

set_output_delay -max 0.43 -clock clk [get_ports axi_awaddr_o[*]]
set_output_delay -min -0.1 -clock clk [get_ports axi_awaddr_o[*]]

set_output_delay -max 0.43 -clock clk [get_ports axi_awvalid_o]
set_output_delay -min -0.1 -clock clk [get_ports axi_awvalid_o]

set_output_delay -max 0.43 -clock clk [get_ports axi_wdata_o[*]]
set_output_delay -min -0.1 -clock clk [get_ports axi_wdata_o[*]]

set_output_delay -max 0.43 -clock clk [get_ports axi_wstrb_o[*]]
set_output_delay -min -0.1 -clock clk [get_ports axi_wstrb_o[*]]

set_output_delay -max 0.43 -clock clk [get_ports axi_wvalid_o]
set_output_delay -min -0.1 -clock clk [get_ports axi_wvalid_o]

set_output_delay -max 0.43 -clock clk [get_ports axi_bready_o]
set_output_delay -min -0.1 -clock clk [get_ports axi_bready_o]

###############################################################################
# 3. APB3 debug slave port timing
###############################################################################
set_input_delay  -max 0.34 -clock clk [get_ports apb_paddr_i[*]]
set_input_delay  -min 0.04 -clock clk [get_ports apb_paddr_i[*]]

set_input_delay  -max 0.34 -clock clk [get_ports apb_psel_i]
set_input_delay  -min 0.04 -clock clk [get_ports apb_psel_i]

set_input_delay  -max 0.34 -clock clk [get_ports apb_penable_i]
set_input_delay  -min 0.04 -clock clk [get_ports apb_penable_i]

set_input_delay  -max 0.34 -clock clk [get_ports apb_pwrite_i]
set_input_delay  -min 0.04 -clock clk [get_ports apb_pwrite_i]

set_input_delay  -max 0.34 -clock clk [get_ports apb_pwdata_i[*]]
set_input_delay  -min 0.04 -clock clk [get_ports apb_pwdata_i[*]]

set_output_delay -max 0.34 -clock clk [get_ports apb_pready_o]
set_output_delay -min -0.1 -clock clk [get_ports apb_pready_o]

set_output_delay -max 0.34 -clock clk [get_ports apb_pslverr_o]
set_output_delay -min -0.1 -clock clk [get_ports apb_pslverr_o]

# APB read data: non-critical debug port — relax via false path
set_false_path -to [get_ports apb_prdata_o[*]]

###############################################################################
# 4. Misc inputs (rst_n_i, irq)
###############################################################################
set_input_delay -max 0.3 -clock clk [get_ports rst_n_i]
set_input_delay -min 0.0 -clock clk [get_ports rst_n_i]
set_input_delay -max 0.3 -clock clk [get_ports ext_irq_i]
set_input_delay -min 0.0 -clock clk [get_ports ext_irq_i]
set_input_delay -max 0.3 -clock clk [get_ports timer_irq_i]
set_input_delay -min 0.0 -clock clk [get_ports timer_irq_i]

###############################################################################
# 5. Environment
###############################################################################
set_max_transition 0.17 [current_design]
set_max_fanout     20   [current_design]

set_driving_cell -lib_cell BUF_X1 -pin Z [all_inputs]
set_load 3.898 [all_outputs]
