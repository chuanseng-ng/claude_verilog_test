// mbist_xing - MBIST control-word crossing from the TCK domain to one functional domain.
//
// Function: wr_valid_i and the write data move through a depth-2 cdc_gray_fifo (write on tck_i, read on clk_dst_i)
//   into the holding register ctl_q. ctl_q drives run_o and cfg_o. rd_ready is tied 1.
// Parameters: CTL_W and DOM_BIT.
// Clocks and resets: tck_i is the write clock. clk_dst_i is the destination clock. It must be an ungated clock.
//   Both FIFO resets derive from trst_ni only, so they share one root. ctl_q and rst_n_o reset from trst_ni
//   and dst_rst_n_i, through a dft_rst_mux scan override (scan_mode_i, scan_rst_ni).
//   trst_ni = 0 holds all of it in reset. run_o is 0.
// Caller rules:
//   - A write while wr_ready_o is low is lost. The caller (jtag_tap) latches a sticky overflow flag from wr_ready_o.
//   - A functional reset leaves MBIST idle (run_o = 0). The tester must rewrite MBIST_CTRL. dst_rst_n_i can never start MBIST.
// Doc: ds:mod:mbist-xing

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

    // The holding register is an instance of its own: it is the ONE place that reads the FIFO's TCK-domain
    // storage combinationally (rd_data_w), so tools/dft/check_scan_clk_rst.py --tck-sink names it (and the
    // FIFO's pointer synchroniser) as the only cells allowed to read a TCK-domain flop.
    logic [CTL_W-1:0] ctl_w;

    mbist_ctl_hold #(
        .CTL_W (CTL_W)
    ) u_hold (
        .clk_i  (clk_dst_i),
        .rst_n_i(rst_n_o),
        .load_i (rd_valid_w),
        .d_i    (rd_data_w),
        .q_o    (ctl_w)
    );

    assign run_o = ctl_w[0] & ctl_w[DOM_BIT];
    assign cfg_o = ctl_w[26:1];

endmodule : mbist_xing
