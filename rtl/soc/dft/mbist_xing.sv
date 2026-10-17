// mbist_xing.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.10, GH #244): the MBIST control-word crossing,
// TCK domain -> ONE destination functional domain. Specification: docs/design/DFT_ARCHITECTURE.md
// section 16.5 (resolution of the 15 open questions of PR #276).
//
//   TAP (tck_i) --wr_valid/wr_data--> cdc_gray_fifo (DEPTH 2, write tck_i, read UNGATED clk_dst_i)
//                                     --> holding register ctl_q (clk_dst_i) --> run_o / cfg_o
//
// * The read side is the UNGATED destination clock (core_clk / cpu_core_clk), never a gated clock.
// * rd_ready is tied 1: every delivered word is captured into ctl_q on the read edge (rd_data_o is a
//   combinational read of the FIFO storage, valid exactly while rd_valid_o is high).
// * The TAP can never stall: a write attempted while wr_ready_o is low is LOST and the caller (jtag_tap)
//   latches its sticky overflow flag from wr_ready_o.
// * Reset architecture (Q8). Both FIFO resets derive from trst_ni ALONE: write side = rst_tck_n_i (from
//   a TCK-domain trst synchroniser in dft_ctrl), read side = u_rd_rst, a cdc_reset_sync of trst_ni into
//   clk_dst_i (with the scan override). They therefore share one root, so a functional reset can never
//   leave phantom FIFO entries. The holding register and the controller (rst_n_o) are reset by that
//   AND the functional domain reset dst_rst_n_i, through a dft_rst_mux scan override. A functional reset
//   therefore leaves MBIST idle (run_o = 0) and the tester must rewrite MBIST_CTRL; rst_n_i can never
//   start MBIST.
// * trst_ni = 0 (the idle value of every existing suite) holds all of it in reset: run_o = 0.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module mbist_xing #(
    parameter int unsigned CTL_W   = 29,
    parameter int unsigned DOM_BIT = 27      // which MBIST_CTRL bit enables this domain
) (
    // ── TCK (write) side ─────────────────────────────────────────────────────
    input  logic             tck_i,
    input  logic             rst_tck_n_i,    // TCK-domain reset derived from trst_ni
    input  logic             wr_valid_i,
    input  logic [CTL_W-1:0] wr_data_i,
    output logic             wr_ready_o,

    // ── Destination (read) side ──────────────────────────────────────────────
    input  logic             clk_dst_i,
    input  logic             dst_rst_n_i,    // functional domain reset
    input  logic             trst_ni,
    input  logic             scan_mode_i,
    input  logic             scan_rst_ni,
    output logic             rst_n_o,        // controller reset (functional AND trst, scan-overridden)
    output logic             run_o,
    output logic [25:0]      cfg_o
);

    // Read-side reset: trst_ni only, synchronised into the destination clock (async assert, sync release).
    logic fifo_rd_rst_n;

    cdc_reset_sync #(
        .STAGES(2)
    ) u_rd_rst (
        .clk_i       (clk_dst_i),
        .rst_n_i     (trst_ni),
        .scanmode_i  (scan_mode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (fifo_rd_rst_n)
    );

    logic [CTL_W-1:0] rd_data_w;
    logic             rd_valid_w;

    cdc_gray_fifo #(
        .WIDTH       (CTL_W),
        .DEPTH       (2),
        .SYNC_STAGES (2)
    ) u_fifo (
        .wr_clk_i   (tck_i),
        .wr_rst_n_i (rst_tck_n_i),
        .wr_data_i  (wr_data_i),
        .wr_valid_i (wr_valid_i),
        .wr_ready_o (wr_ready_o),
        .rd_clk_i   (clk_dst_i),
        .rd_rst_n_i (fifo_rd_rst_n),
        .rd_data_o  (rd_data_w),
        .rd_valid_o (rd_valid_w),
        .rd_ready_i (1'b1)
    );

    // Controller / holding-register reset: functional AND trst, with the scan override at the net.
    logic func_rst_w;

    assign func_rst_w = dst_rst_n_i & fifo_rd_rst_n;

    dft_rst_mux u_ctl_rst (
        .func_rst_n_i (func_rst_w),
        .scan_rst_ni  (scan_rst_ni),
        .scan_mode_i  (scan_mode_i),
        .rst_n_o      (rst_n_o)
    );

    logic [CTL_W-1:0] ctl_q;

    always_ff @(posedge clk_dst_i or negedge rst_n_o) begin
        if (!rst_n_o) begin
            ctl_q <= '0;
        end else if (rd_valid_w) begin
            ctl_q <= rd_data_w;
        end
    end

    assign run_o = ctl_q[0] & ctl_q[DOM_BIT];
    assign cfg_o = ctl_q[26:1];

endmodule : mbist_xing
