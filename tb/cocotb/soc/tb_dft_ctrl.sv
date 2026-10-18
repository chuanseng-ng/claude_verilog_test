// tb_dft_ctrl.sv
// Bead claude_verilog_test-j41m.3 (DFT Stage 1b): cocotb wrapper for dft_ctrl.
//
//   * u_dut  the TAP-driven dft_ctrl under test;
//   * u_ref  a Stage 1a dft_ctrl_ports fed by the SAME four pin inputs: the golden reference for
//            "with the TAP idle, bit-identical to 1a" (outputs prefixed ref_);
//   * tap_state_o, tap_serial_o: hierarchical probes of the TAP's state and its serial flag so the
//     suite can name the TAP state at every TCK edge (dft_ctrl itself exports neither).

module tb_dft_ctrl (
    input  logic scan_mode_i,
    input  logic scan_en_i,
    input  logic scan_rst_ni,
    input  logic scan_clk_i,

    input  logic tck_i,
    input  logic tms_i,
    input  logic tdi_i,
    input  logic trst_ni,
    output logic tdo_o,
    output logic tdo_oe_o,

    output logic scan_mode_o,
    output logic scan_en_o,
    output logic scan_rst_no,
    output logic test_en_o,
    output logic test_clk_o,

    output logic ref_scan_mode_o,
    output logic ref_scan_en_o,
    output logic ref_scan_rst_no,
    output logic ref_test_en_o,
    output logic ref_test_clk_o,

    output logic [3:0] tap_state_o,
    output logic       tap_serial_o,

    // the glitch-free test-clock switch (dft_clk_switch u_clk_sw): its A input (the TAP's gated
    // TCK) and its two internal enable latches, so the suite can apply the same pulse analysis
    // to dft_ctrl as to the switch alone
    output logic       tck_gated_o,
    output logic       en_a_o,
    output logic       en_b_o,

    // MBIST hooks of dft_ctrl (Stage 4); inputs idle at 0 = FIFO ready, status 0
    output logic [28:0]  mbist_ctl_o,
    output logic         mbist_wr_o,
    output logic         mbist_force_o,
    output logic         mbist_rst_tck_n_o,
    input  logic         mbist_not_ready_i,
    input  logic [138:0] mbist_status_i
);

    dft_ctrl u_dut (
        .scan_mode_i (scan_mode_i),
        .scan_en_i   (scan_en_i),
        .scan_rst_ni (scan_rst_ni),
        .scan_clk_i  (scan_clk_i),
        .tck_i       (tck_i),
        .tms_i       (tms_i),
        .tdi_i       (tdi_i),
        .trst_ni     (trst_ni),
        .tdo_o       (tdo_o),
        .tdo_oe_o    (tdo_oe_o),
        .scan_mode_o (scan_mode_o),
        .scan_en_o   (scan_en_o),
        .scan_rst_no (scan_rst_no),
        .test_en_o   (test_en_o),
        .test_clk_o  (test_clk_o),
        .mbist_ctl_o       (mbist_ctl_o),
        .mbist_wr_o        (mbist_wr_o),
        .mbist_force_o     (mbist_force_o),
        .mbist_rst_tck_n_o (mbist_rst_tck_n_o),
        .mbist_wr_ready_i  (~mbist_not_ready_i),
        .mbist_status_i    (mbist_status_i)
    );

    dft_ctrl_ports u_ref (
        .scan_mode_i (scan_mode_i),
        .scan_en_i   (scan_en_i),
        .scan_rst_ni (scan_rst_ni),
        .scan_clk_i  (scan_clk_i),
        .scan_mode_o (ref_scan_mode_o),
        .scan_en_o   (ref_scan_en_o),
        .scan_rst_no (ref_scan_rst_no),
        .test_en_o   (ref_test_en_o),
        .test_clk_o  (ref_test_clk_o)
    );

    assign tap_state_o  = u_dut.tap_state;
    assign tap_serial_o = u_dut.tap_serial;
    assign tck_gated_o  = u_dut.tck_scan_gated;
    assign en_a_o       = u_dut.u_clk_sw.en_a_q;
    assign en_b_o       = u_dut.u_clk_sw.en_b_q;

endmodule : tb_dft_ctrl
