# Shared setup-mode constraints for the Sky130 SoC fabric in scan mode (sourced by scan.tcl and atpg.tcl).
# Test-mode contract (DFT_ARCHITECTURE sections 9, 14.1, 15.4, 15.9.1):
#   scan_mode_i = 1, TAP held in reset (trst_ni = 0, tck_i = 0, tms_i = 1, tdi_i = 0) so the pin leg of dft_ctrl is the only
#   source of scan control; scan_clk_i is the single shift/capture clock (functional clock roots are muxed to it by
#   dft_clk_mux); scan_rst_ni is the only async reset in scan mode; scan_en_i is the scan enable (stand-in for the internal
#   dft_scan_en net, which equals scan_en_i with the TAP idle).
add_black_boxes -modules {rv32i_cpu_top sky130_sram_4kbyte_1rw1r_32x1024_8}
add_clocks 0 scan_clk_i
add_clocks 1 scan_rst_ni
add_input_constraints scan_mode_i -C1
add_input_constraints {clk_i cpu_clk_i tck_i tdi_i trst_ni} -C0
add_input_constraints {tms_i rst_n_i cpu_rst_n_i} -C1
