// tb_dft_muxes.sv
// Bead claude_verilog_test-j41m.2 (DFT Stage 1a): one wrapper holding the three
// small DFT leaf modules, re-exported flat so a single cocotb module can drive
// each independently.

module tb_dft_muxes (
    // dft_clk_mux
    input  logic cm_func_clk,
    input  logic cm_test_clk,
    input  logic cm_sel,
    output logic cm_clk_o,
    // dft_rst_mux
    input  logic rm_func_rst_n,
    input  logic rm_scan_rst_n,
    input  logic rm_scan_mode,
    output logic rm_rst_n_o,
    // dft_ctrl_ports
    input  logic cp_scan_mode_i,
    input  logic cp_scan_en_i,
    input  logic cp_scan_rst_ni,
    input  logic cp_scan_clk_i,
    output logic cp_scan_mode_o,
    output logic cp_scan_en_o,
    output logic cp_scan_rst_no,
    output logic cp_test_en_o,
    output logic cp_test_clk_o
);

    dft_clk_mux u_cm (
        .func_clk_i (cm_func_clk),
        .scan_clk_i (cm_test_clk),
        .sel_i      (cm_sel),
        .clk_o      (cm_clk_o)
    );

    dft_rst_mux u_rm (
        .func_rst_n_i (rm_func_rst_n),
        .scan_rst_ni  (rm_scan_rst_n),
        .scan_mode_i  (rm_scan_mode),
        .rst_n_o      (rm_rst_n_o)
    );

    dft_ctrl_ports u_cp (
        .scan_mode_i (cp_scan_mode_i),
        .scan_en_i   (cp_scan_en_i),
        .scan_rst_ni (cp_scan_rst_ni),
        .scan_clk_i  (cp_scan_clk_i),
        .scan_mode_o (cp_scan_mode_o),
        .scan_en_o   (cp_scan_en_o),
        .scan_rst_no (cp_scan_rst_no),
        .test_en_o   (cp_test_en_o),
        .test_clk_o  (cp_test_clk_o)
    );

endmodule : tb_dft_muxes
