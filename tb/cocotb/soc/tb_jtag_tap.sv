// tb_jtag_tap.sv
// Bead claude_verilog_test-j41m.3 (DFT Stage 1b): cocotb wrapper for jtag_tap alone.
//
//   * every jtag_tap port re-exported flat;
//   * sys_clk_i / sys_cnt_o: a free-running "system clock" domain that is unrelated to TCK. The
//     TAP has no functional-clock input at all, so this counter proves nothing by itself; it exists
//     so the testbench toggles a genuinely running, coprime clock next to the TAP while the whole
//     unit suite runs, i.e. any accidental coupling (a shared simulator process, a stray net) would
//     show up as a model mismatch. The counter is also read back to prove the clock really ran;
//   * ir_q_o / scan_sel_q_o / scan_rst_q_o: hierarchical probes of the IR update register and the
//     two TDR update registers, so the suite can check the exact instant they change (falling edge
//     of Update-IR / Update-DR) rather than inferring it from readback. If the RTL renames those
//     registers this is the one place to adapt.

module tb_jtag_tap (
    input  logic       tck_i,
    input  logic       tms_i,
    input  logic       tdi_i,
    input  logic       trst_ni,
    output logic       tdo_o,
    output logic       tdo_oe_o,
    output logic [3:0] state_o,
    output logic       scan_mode_o,
    output logic       serial_o,
    output logic       parallel_o,
    output logic       rst_assert_o,
    output logic       scan_en_o,
    output logic       shift_clk_en_o,
    output logic [1:0] chain_grp_o,

    // MBIST (Stage 4): idle inputs 0 = control-word FIFO ready, status 0
    output logic [28:0]  mbist_ctl_o,
    output logic         mbist_wr_o,
    output logic         mbist_force_o,
    input  logic         mbist_not_ready_i,
    input  logic [138:0] mbist_status_i,

    input  logic       sys_clk_i,
    output logic [7:0] sys_cnt_o,

    output logic [3:0] ir_q_o,
    output logic [2:0] scan_sel_q_o,
    output logic       scan_rst_q_o
);

    jtag_tap u_dut (
        .tck_i          (tck_i),
        .tms_i          (tms_i),
        .tdi_i          (tdi_i),
        .trst_ni        (trst_ni),
        .tdo_o          (tdo_o),
        .tdo_oe_o       (tdo_oe_o),
        .state_o        (state_o),
        .scan_mode_o    (scan_mode_o),
        .serial_o       (serial_o),
        .parallel_o     (parallel_o),
        .rst_assert_o   (rst_assert_o),
        .scan_en_o      (scan_en_o),
        .shift_clk_en_o (shift_clk_en_o),
        .chain_grp_o    (chain_grp_o),
        .mbist_ctl_o      (mbist_ctl_o),
        .mbist_wr_o       (mbist_wr_o),
        .mbist_force_o    (mbist_force_o),
        .mbist_wr_ready_i (~mbist_not_ready_i),
        .mbist_status_i   (mbist_status_i)
    );

    // A plain `always` (not always_ff) with a declaration initialiser: an always_ff target may not be
    // written by any other process, and VCS counts both `initial x = 0` and a declaration initialiser as
    // such a process (IEEE 1800-2017 9.2.2.4; Error-[ICPD]/[ICPD_INIT]).  Verilator tolerated the original.
    logic [7:0] sys_cnt_q = 8'd0;
    always @(posedge sys_clk_i) sys_cnt_q <= sys_cnt_q + 8'd1;
    assign sys_cnt_o = sys_cnt_q;

    assign ir_q_o       = u_dut.ir_q;
    assign scan_sel_q_o = u_dut.scan_sel_q;
    assign scan_rst_q_o = u_dut.scan_rst_q;

endmodule : tb_jtag_tap
