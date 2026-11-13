// async_axi_fifo - dual-clock AXI4 bridge between the CPU domain and the fabric domain.
//
// Function: The module has five cdc_gray_fifo instances (AW, W, B, AR, R) and two cdc_reset_sync instances.
//   It has no other sequential logic. Neither face carries an id.
//   The s_* face is an AXI slave port on s_clk_i and s_rst_n_i. It is the CPU domain, not sys_clk.
//   The m_* face is an AXI master port on m_clk_i and m_rst_n_i. It drives crossbar master 0.
// Parameters: AW, DW, SW, LENW and SIZEW set the bus geometry. They default from axi_pkg.
//   AW_DEPTH, W_DEPTH, B_DEPTH, AR_DEPTH and R_DEPTH set the FIFO depths.
//   SYNC_STAGES_TO_S and SYNC_STAGES_TO_M set the synchroniser stages.
// Clocks and resets: s_rst_n_i and m_rst_n_i are active low. rst_both_n is s_rst_n_i & m_rst_n_i.
//   It feeds both cdc_reset_sync instances. While a domain is in reset, its ready and valid outputs are 0.
// Caller rules:
//   - Reset is a hard flush, not a graceful abort. Buffered beats are lost. No wlast and no SLVERR is made.
//   - s_rst_n_i and m_rst_n_i must share a common root that also resets the master and the fabric.
//   - Hold each reset low for at least SYNC_STAGES+1 periods of the other clock. Do not wire a short pulse.
//   - STA must set set_max_delay -datapath_only on the mem_q read path and on both gray-pointer crossings
//     in each of the five FIFO instances.
//   - Connect scanmode_i and scan_rst_ni at every instance. Both reach the two cdc_reset_sync instances.
//   - Each channel costs about SYNC_STAGES+2 receiving-domain cycles per traversal.
//   - The module has no bypass parameter.
// Doc: ds:mod:async-axi-fifo, tm:mod:async-axi-fifo

module async_axi_fifo #(
    // Bus geometry. The defaults come from axi_pkg.
    parameter int unsigned AW    = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW    = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW    = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned LENW  = axi_pkg::AXI_LEN_WIDTH,
    parameter int unsigned SIZEW = axi_pkg::AXI_SIZE_WIDTH,

    // ── Per-channel FIFO depths (power of two; validated at >= 4 only -- cdc_gray_fifo itself accepts 2 since 3snb, not validated here) ──
    parameter int unsigned AW_DEPTH = 4,
    parameter int unsigned W_DEPTH  = 8,
    parameter int unsigned B_DEPTH  = 4,
    parameter int unsigned AR_DEPTH = 4,
    parameter int unsigned R_DEPTH  = 8,

    // ── Synchroniser stage counts, split so a future change (#96) can raise
    //    the CPU (s) side to 3 for MTBF without changing the fabric (m)
    //    side default. Applied per-instance to the whole cdc_gray_fifo (both
    //    of its internal pointer-sync directions) since cdc_gray_fifo itself
    //    exposes a single SYNC_STAGES — see the design-decision note in the
    //    delivery report for the precise mapping and its limitation. ───────
    parameter int unsigned SYNC_STAGES_TO_S = 2,
    parameter int unsigned SYNC_STAGES_TO_M = 2
) (
    // DFT scan bypass. scanmode_i and scan_rst_ni go to both internal cdc_reset_sync instances. Connect them at every instance.
    input  logic               scanmode_i,
    input  logic               scan_rst_ni,

    // ══ s_* face — CPU domain, AXI SLAVE port (CPU's AXI master attaches here) ══
    input  logic              s_clk_i,
    input  logic              s_rst_n_i,

    // Write address channel
    input  logic [AW-1:0]     s_awaddr_i,
    input  logic [LENW-1:0]   s_awlen_i,
    input  logic [SIZEW-1:0]  s_awsize_i,
    input  logic [1:0]        s_awburst_i,
    input  logic              s_awvalid_i,
    output logic              s_awready_o,
    // Write data channel
    input  logic [DW-1:0]     s_wdata_i,
    input  logic [SW-1:0]     s_wstrb_i,
    input  logic              s_wlast_i,
    input  logic              s_wvalid_i,
    output logic              s_wready_o,
    // Write response channel
    output logic [1:0]        s_bresp_o,
    output logic              s_bvalid_o,
    input  logic              s_bready_i,
    // Read address channel
    input  logic [AW-1:0]     s_araddr_i,
    input  logic [LENW-1:0]   s_arlen_i,
    input  logic [SIZEW-1:0]  s_arsize_i,
    input  logic [1:0]        s_arburst_i,
    input  logic              s_arvalid_i,
    output logic              s_arready_o,
    // Read data channel
    output logic [DW-1:0]     s_rdata_o,
    output logic [1:0]        s_rresp_o,
    output logic              s_rlast_o,
    output logic              s_rvalid_o,
    input  logic              s_rready_i,

    // ══ m_* face — fabric domain, AXI MASTER port (drives crossbar M0) ══════
    input  logic              m_clk_i,
    input  logic              m_rst_n_i,

    // Write address channel
    output logic [AW-1:0]     m_awaddr_o,
    output logic [LENW-1:0]   m_awlen_o,
    output logic [SIZEW-1:0]  m_awsize_o,
    output logic [1:0]        m_awburst_o,
    output logic              m_awvalid_o,
    input  logic              m_awready_i,
    // Write data channel
    output logic [DW-1:0]     m_wdata_o,
    output logic [SW-1:0]     m_wstrb_o,
    output logic              m_wlast_o,
    output logic              m_wvalid_o,
    input  logic              m_wready_i,
    // Write response channel
    input  logic [1:0]        m_bresp_i,
    input  logic              m_bvalid_i,
    output logic              m_bready_o,
    // Read address channel
    output logic [AW-1:0]     m_araddr_o,
    output logic [LENW-1:0]   m_arlen_o,
    output logic [SIZEW-1:0]  m_arsize_o,
    output logic [1:0]        m_arburst_o,
    output logic              m_arvalid_o,
    input  logic              m_arready_i,
    // Read data channel
    input  logic [DW-1:0]     m_rdata_i,
    input  logic [1:0]        m_rresp_i,
    input  logic              m_rlast_i,
    input  logic              m_rvalid_i,
    output logic              m_rready_o
);

    // ── Reset: common root feeding both per-domain synchronisers ────────────
    logic rst_both_n;
    assign rst_both_n = s_rst_n_i & m_rst_n_i;

    logic s_rst_sync_n;
    logic m_rst_sync_n;

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_S)
    ) u_s_rst_sync (
        .clk_i       (s_clk_i),
        .rst_n_i     (rst_both_n),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (s_rst_sync_n)
    );

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_M)
    ) u_m_rst_sync (
        .clk_i       (m_clk_i),
        .rst_n_i     (rst_both_n),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (m_rst_sync_n)
    );

    // ══ AW channel (s -> m) ═══════════════════════════════════════════════════
    localparam int unsigned AW_PAYLOAD_W = AW + LENW + SIZEW + 2;
    logic [AW_PAYLOAD_W-1:0] aw_wr_data, aw_rd_data;

    assign aw_wr_data = {s_awaddr_i, s_awlen_i, s_awsize_i, s_awburst_i};
    assign {m_awaddr_o, m_awlen_o, m_awsize_o, m_awburst_o} = aw_rd_data;

    cdc_gray_fifo #(
        .WIDTH       (AW_PAYLOAD_W),
        .DEPTH       (AW_DEPTH),
        .SYNC_STAGES (SYNC_STAGES_TO_M)
    ) u_aw_fifo (
        .wr_clk_i   (s_clk_i),
        .wr_rst_n_i (s_rst_sync_n),
        .wr_data_i  (aw_wr_data),
        .wr_valid_i (s_awvalid_i),
        .wr_ready_o (s_awready_o),

        .rd_clk_i   (m_clk_i),
        .rd_rst_n_i (m_rst_sync_n),
        .rd_data_o  (aw_rd_data),
        .rd_valid_o (m_awvalid_o),
        .rd_ready_i (m_awready_i)
    );

    // ══ W channel (s -> m) ════════════════════════════════════════════════════
    localparam int unsigned W_PAYLOAD_W = DW + SW + 1;
    logic [W_PAYLOAD_W-1:0] w_wr_data, w_rd_data;

    assign w_wr_data = {s_wdata_i, s_wstrb_i, s_wlast_i};
    assign {m_wdata_o, m_wstrb_o, m_wlast_o} = w_rd_data;

    cdc_gray_fifo #(
        .WIDTH       (W_PAYLOAD_W),
        .DEPTH       (W_DEPTH),
        .SYNC_STAGES (SYNC_STAGES_TO_M)
    ) u_w_fifo (
        .wr_clk_i   (s_clk_i),
        .wr_rst_n_i (s_rst_sync_n),
        .wr_data_i  (w_wr_data),
        .wr_valid_i (s_wvalid_i),
        .wr_ready_o (s_wready_o),

        .rd_clk_i   (m_clk_i),
        .rd_rst_n_i (m_rst_sync_n),
        .rd_data_o  (w_rd_data),
        .rd_valid_o (m_wvalid_o),
        .rd_ready_i (m_wready_i)
    );

    // ══ B channel (m -> s) ════════════════════════════════════════════════════
    localparam int unsigned B_PAYLOAD_W = 2;
    logic [B_PAYLOAD_W-1:0] b_wr_data, b_rd_data;

    assign b_wr_data = m_bresp_i;
    assign s_bresp_o = b_rd_data;

    cdc_gray_fifo #(
        .WIDTH       (B_PAYLOAD_W),
        .DEPTH       (B_DEPTH),
        .SYNC_STAGES (SYNC_STAGES_TO_S)
    ) u_b_fifo (
        .wr_clk_i   (m_clk_i),
        .wr_rst_n_i (m_rst_sync_n),
        .wr_data_i  (b_wr_data),
        .wr_valid_i (m_bvalid_i),
        .wr_ready_o (m_bready_o),

        .rd_clk_i   (s_clk_i),
        .rd_rst_n_i (s_rst_sync_n),
        .rd_data_o  (b_rd_data),
        .rd_valid_o (s_bvalid_o),
        .rd_ready_i (s_bready_i)
    );

    // ══ AR channel (s -> m) ═══════════════════════════════════════════════════
    localparam int unsigned AR_PAYLOAD_W = AW + LENW + SIZEW + 2;
    logic [AR_PAYLOAD_W-1:0] ar_wr_data, ar_rd_data;

    assign ar_wr_data = {s_araddr_i, s_arlen_i, s_arsize_i, s_arburst_i};
    assign {m_araddr_o, m_arlen_o, m_arsize_o, m_arburst_o} = ar_rd_data;

    cdc_gray_fifo #(
        .WIDTH       (AR_PAYLOAD_W),
        .DEPTH       (AR_DEPTH),
        .SYNC_STAGES (SYNC_STAGES_TO_M)
    ) u_ar_fifo (
        .wr_clk_i   (s_clk_i),
        .wr_rst_n_i (s_rst_sync_n),
        .wr_data_i  (ar_wr_data),
        .wr_valid_i (s_arvalid_i),
        .wr_ready_o (s_arready_o),

        .rd_clk_i   (m_clk_i),
        .rd_rst_n_i (m_rst_sync_n),
        .rd_data_o  (ar_rd_data),
        .rd_valid_o (m_arvalid_o),
        .rd_ready_i (m_arready_i)
    );

    // ══ R channel (m -> s) ════════════════════════════════════════════════════
    localparam int unsigned R_PAYLOAD_W = DW + 2 + 1;
    logic [R_PAYLOAD_W-1:0] r_wr_data, r_rd_data;

    assign r_wr_data = {m_rdata_i, m_rresp_i, m_rlast_i};
    assign {s_rdata_o, s_rresp_o, s_rlast_o} = r_rd_data;

    cdc_gray_fifo #(
        .WIDTH       (R_PAYLOAD_W),
        .DEPTH       (R_DEPTH),
        .SYNC_STAGES (SYNC_STAGES_TO_S)
    ) u_r_fifo (
        .wr_clk_i   (m_clk_i),
        .wr_rst_n_i (m_rst_sync_n),
        .wr_data_i  (r_wr_data),
        .wr_valid_i (m_rvalid_i),
        .wr_ready_o (m_rready_o),

        .rd_clk_i   (s_clk_i),
        .rd_rst_n_i (s_rst_sync_n),
        .rd_data_o  (r_rd_data),
        .rd_valid_o (s_rvalid_o),
        .rd_ready_i (s_rready_i)
    );

endmodule : async_axi_fifo
