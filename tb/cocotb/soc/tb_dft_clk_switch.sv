// tb_dft_clk_switch.sv
// Bead claude_verilog_test-j41m.3 (DFT Stage 1b): cocotb wrapper for dft_clk_switch.
//
//   * tck_i / a_en_i   the raw TCK and a clock-gate enable.  The A clock the switch sees is
//                      clk_a_o = tck_i gated by a_en_i through the SAME rv32i_clock_gate dft_ctrl
//                      uses, so A idles low and only ever carries whole TCK pulses, exactly like
//                      the TAP's tck_scan_gated.  A stopped/gated-off A is a_en_i = 0 with tck_i
//                      still running; a stopped TCK is tck_i held constant.
//   * clk_b_i          B, the pin test clock, driven straight from the test.
//   * PLAIN_MUX = 1    replaces the switch by `assign clk_o = sel_a_i ? clk_a_o : clk_b_i`, the
//                      plain 2:1 mux that open question Q-CLK first proposed.  Same ports, so the
//                      SAME suite runs against it as the RED negative control (make target
//                      dft_clk_switch_plainmux, expected to FAIL).
//   * clk_a_o / en_a_o / en_b_o   observation: the A clock as the switch sees it, and the two
//                      internal enable latches (en_a_q, en_b_q), tied 0 in the plain-mux variant.

module tb_dft_clk_switch #(
    parameter bit PLAIN_MUX = 1'b0
) (
    input  logic tck_i,
    input  logic a_en_i,
    input  logic clk_b_i,
    input  logic sel_a_i,
    input  logic rst_n_i,
    output logic clk_a_o,
    output logic clk_o,
    output logic en_a_o,
    output logic en_b_o
);

    rv32i_clock_gate u_a_gate (
        .en      (a_en_i),
        .test_en (1'b0),
        .clk     (tck_i),
        .gclk    (clk_a_o)
    );

    if (PLAIN_MUX) begin : g_plain
        /* verilator lint_off UNUSEDSIGNAL */
        logic unused_rst_n;
        /* verilator lint_on UNUSEDSIGNAL */
        assign unused_rst_n = rst_n_i;
        assign clk_o        = sel_a_i ? clk_a_o : clk_b_i;
        assign en_a_o       = 1'b0;
        assign en_b_o       = 1'b0;
    end else begin : g_sw
        dft_clk_switch u_sw (
            .tck_i   (tck_i),
            .clk_a_i (clk_a_o),
            .clk_b_i (clk_b_i),
            .sel_a_i (sel_a_i),
            .rst_n_i (rst_n_i),
            .clk_o   (clk_o)
        );
        assign en_a_o = u_sw.en_a_q;
        assign en_b_o = u_sw.en_b_q;
    end

endmodule : tb_dft_clk_switch
