// async_axi_fifo.sv
// GH #91 — Dual-clock AXI4 CDC bridge (epic #90, child 1 of 4).
//
// Purely STRUCTURAL: 5x cdc_gray_fifo (AW/W/B/AR/R) + payload concat/slice +
// 2x cdc_reset_sync. No sequential logic of its own — every register lives
// inside cdc_gray_fifo or cdc_reset_sync. See docs/3PLL_CDC_EVALUATION.md
// (DECIDED 2026-06-27) for why this is the SoC's one intentional CDC
// boundary: CPU @ ~1282 MHz on one side, GPU+bus+peripherals @ 571 MHz on
// the other, meeting at crossbar M0.
//
// !!! s_clk_i is the CPU DOMAIN, NOT sys_clk — the name is confusable !!!
//   s_clk_i / s_rst_n_i — CPU domain (`cpu_clk` in #93). The s_* face is the
//     AXI SLAVE port that the CPU's AXI master attaches to (this module is a
//     slave from the CPU's point of view).
//   m_clk_i / m_rst_n_i — fabric domain (`sys_clk`). The m_* face is the AXI
//     MASTER port that drives crossbar M0 (this module is a master from the
//     fabric's point of view).
// Field names/widths on both faces mirror rtl/cpu/rv32i_cpu_top.sv:19-51 and
// rtl/soc/axi4_crossbar.sv:55-86 1:1 so GH #93's wiring is mechanical.
//
// ID-LESS on both faces: the crossbar's master-facing port has no id field
// (axi4_crossbar.sv:55-86; ids only exist slave-side, tagged internally by
// master index). This bridge never carries an id.
//
// Channel payload packing (MSB..LSB), s->m direction unless noted:
//   AW payload[44:0] = {addr[31:0], len[7:0], size[2:0], burst[1:0]}
//   W  payload[36:0] = {data[31:0], strb[3:0], last}
//   B  payload[1:0]  = {resp[1:0]}                                (m->s)
//   AR payload[44:0] = {addr[31:0], len[7:0], size[2:0], burst[1:0]}
//   R  payload[34:0] = {data[31:0], resp[1:0], last}               (m->s)
//
// !!! mem_q read-domain combinational read path (per fifo instance) !!!
// Each cdc_gray_fifo's storage array is read combinationally in its
// destination clock domain and is safe only because the gray pointer has
// already propagated through SYNC_STAGES receiving flops (see
// cdc_gray_fifo.sv header). GH #94 MUST add `set_max_delay -datapath_only`
// on that path AND on the two gray-pointer crossings, in EACH of the 5
// instances below.
//
// ── Reset strategy: hard flush, common root, both domains always together ──
// assign rst_both_n = s_rst_n_i & m_rst_n_i; feeds BOTH cdc_reset_sync
// instances. Rationale (failure being designed against): if only one side
// reset, its pointers would clear while the other's did not, and the read
// side would then pop 2**PTR_W-N entries of garbage into the crossbar (or
// the write side would wedge full) once the un-reset side resumed. Tying
// both domains' resets to the AND of both inputs makes that scenario
// structurally impossible — both pointer sets always clear together.
//
// Reset here is a HARD FLUSH, not a graceful abort: any buffered beats are
// discarded, there is no synthesized wlast, and no SLVERR is fabricated on
// B. A burst can be left half-transferred at both faces. Both s_rst_n_i and
// m_rst_n_i MUST therefore share a common root that ALSO resets the
// attached master and the fabric — this bridge cannot recover an
// in-flight transaction across a reset event on its own.
//
// Each rst_n_i (s_rst_n_i, m_rst_n_i) must be held low for >= SYNC_STAGES+1
// periods of the OTHER clock for a clean synchronised deassertion (see
// cdc_reset_sync.sv). Satisfied trivially while both derive from
// `rst_n_i & pll_locked` upstream; a future integrator must not wire a
// short pulsed reset here.
//
// While a domain is held in reset, both its ready and valid outputs are 0,
// so it backpressures the attached master/slave rather than emitting
// garbage.
//
// Performance note (not fixed here, for #93's budget): each channel costs
// ~SYNC_STAGES+2 receiving-domain cycles per traversal.
//
// No bypass/passthrough parameter: the FIFO is already correct at a 1:1
// clock ratio, which matters because PLL_IMPL="STUB" gives
// core_clk == clk_i (rtl/soc/pll/pll_subsystem.sv:19-21).
//
// Coding rules: no sequential logic in this file — structural instantiation
// + payload assign only (docs/development/CODING_GUIDELINES.md).
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module async_axi_fifo #(
    // ── Bus geometry (defaults from axi_pkg, scope-resolved — no file-scope
    //    import; see rtl/soc/axi4_crossbar.sv:40-46) ─────────────────────────
    parameter int unsigned AW    = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW    = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW    = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned LENW  = axi_pkg::AXI_LEN_WIDTH,
    parameter int unsigned SIZEW = axi_pkg::AXI_SIZE_WIDTH,

    // ── Per-channel FIFO depths (power of two, >= 4 each) ────────────────────
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
        .clk_i   (s_clk_i),
        .rst_n_i (rst_both_n),
        .rst_n_o (s_rst_sync_n)
    );

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_M)
    ) u_m_rst_sync (
        .clk_i   (m_clk_i),
        .rst_n_i (rst_both_n),
        .rst_n_o (m_rst_sync_n)
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
