// tb_async_axi_fifo.sv
// GH #91 — standalone cocotb test wrapper for the dual-clock AXI4 CDC bridge
// (rtl/soc/async_axi_fifo.sv).
//
// Re-exports every DUT port as a true top-level port using the BFM naming
// convention (<prefix>_<field>, no _i/_o suffix) so
// AXI4Master(dut,"s",dut.s_clk) and AXI4SlaveModel(dut,"m",dut.m_clk) attach
// unmodified (tb/cocotb/bfm/axi4_master.py, tb/cocotb/soc/axi4_slave_model.py)
// — same standalone wrapper pattern as tb_pmu.sv / tb_pll_apb_regs.sv: cocotb
// drives real top-level input ports, not nets driven by any RTL assign, so
// there is no multiple-driver conflict.
//
// ID SHIM (wrapper-only — async_axi_fifo itself is ID-LESS on both faces,
// mirroring the crossbar's master-facing port; see axi4_crossbar.sv:55-86):
// axi4_slave_model.py unconditionally reads captured awid/arid and writes
// bid/rid. m_awid/m_arid are free-standing wrapper inputs (never connected
// to u_dut, never driven by cocotb — read as 0) purely so the slave model
// has something to sample; m_bid/m_rid are free-standing wrapper outputs
// the slave model writes but that drive nothing further. Do NOT modify
// axi4_slave_model.py — test_crossbar.py / test_dma.py depend on it as-is.
//
// *_depth_o constants mirror the actual DEPTH parameters passed into u_dut
// so depth-boundary tests (exact-depth-full) can never silently drift from
// the RTL defaults.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_async_axi_fifo #(
    parameter int unsigned AW    = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW    = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW    = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned LENW  = axi_pkg::AXI_LEN_WIDTH,
    parameter int unsigned SIZEW = axi_pkg::AXI_SIZE_WIDTH,

    parameter int unsigned AW_DEPTH = 4,
    parameter int unsigned W_DEPTH  = 8,
    parameter int unsigned B_DEPTH  = 4,
    parameter int unsigned AR_DEPTH = 4,
    parameter int unsigned R_DEPTH  = 8,

    parameter int unsigned SYNC_STAGES_TO_S = 2,
    parameter int unsigned SYNC_STAGES_TO_M = 2,

    // Wrapper-only ID shim width — arbitrary, never connected to u_dut.
    parameter int unsigned ID_W = 4
) (
    // ══ s_* face — CPU domain, AXI SLAVE port (AXI4Master("s",...) attaches) ══
    input  logic              s_clk,
    input  logic              s_rst_n,

    input  logic [AW-1:0]     s_awaddr,
    input  logic [LENW-1:0]   s_awlen,
    input  logic [SIZEW-1:0]  s_awsize,
    input  logic [1:0]        s_awburst,
    input  logic              s_awvalid,
    output logic              s_awready,

    input  logic [DW-1:0]     s_wdata,
    input  logic [SW-1:0]     s_wstrb,
    input  logic              s_wlast,
    input  logic              s_wvalid,
    output logic              s_wready,

    output logic [1:0]        s_bresp,
    output logic              s_bvalid,
    input  logic              s_bready,

    input  logic [AW-1:0]     s_araddr,
    input  logic [LENW-1:0]   s_arlen,
    input  logic [SIZEW-1:0]  s_arsize,
    input  logic [1:0]        s_arburst,
    input  logic              s_arvalid,
    output logic              s_arready,

    output logic [DW-1:0]     s_rdata,
    output logic [1:0]        s_rresp,
    output logic              s_rlast,
    output logic              s_rvalid,
    input  logic              s_rready,

    // ══ m_* face — fabric domain, AXI MASTER port (AXI4SlaveModel("m",...) attaches) ══
    input  logic              m_clk,
    input  logic              m_rst_n,

    output logic [AW-1:0]     m_awaddr,
    output logic [LENW-1:0]   m_awlen,
    output logic [SIZEW-1:0]  m_awsize,
    output logic [1:0]        m_awburst,
    output logic              m_awvalid,
    input  logic              m_awready,

    output logic [DW-1:0]     m_wdata,
    output logic [SW-1:0]     m_wstrb,
    output logic              m_wlast,
    output logic              m_wvalid,
    input  logic              m_wready,

    input  logic [1:0]        m_bresp,
    input  logic              m_bvalid,
    output logic              m_bready,

    output logic [AW-1:0]     m_araddr,
    output logic [LENW-1:0]   m_arlen,
    output logic [SIZEW-1:0]  m_arsize,
    output logic [1:0]        m_arburst,
    output logic              m_arvalid,
    input  logic              m_arready,

    input  logic [DW-1:0]     m_rdata,
    input  logic [1:0]        m_rresp,
    input  logic              m_rlast,
    input  logic              m_rvalid,
    output logic              m_rready,

    // ══ ID shim — wrapper-only, unconnected to u_dut (see header) ══════════
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ID_W-1:0]   m_awid,
    input  logic [ID_W-1:0]   m_arid,
    /* verilator lint_on UNUSEDSIGNAL */
    /* verilator lint_off UNDRIVEN */
    output logic [ID_W-1:0]   m_bid,
    output logic [ID_W-1:0]   m_rid,
    /* verilator lint_on UNDRIVEN */

    // ══ Depth constants — mirror u_dut's actual DEPTH params ════════════════
    output logic [31:0]       aw_depth_o,
    output logic [31:0]       w_depth_o,
    output logic [31:0]       b_depth_o,
    output logic [31:0]       ar_depth_o,
    output logic [31:0]       r_depth_o
);

    assign aw_depth_o = 32'(AW_DEPTH);
    assign w_depth_o  = 32'(W_DEPTH);
    assign b_depth_o  = 32'(B_DEPTH);
    assign ar_depth_o = 32'(AR_DEPTH);
    assign r_depth_o  = 32'(R_DEPTH);

    async_axi_fifo #(
        .AW    (AW),
        .DW    (DW),
        .SW    (SW),
        .LENW  (LENW),
        .SIZEW (SIZEW),

        .AW_DEPTH (AW_DEPTH),
        .W_DEPTH  (W_DEPTH),
        .B_DEPTH  (B_DEPTH),
        .AR_DEPTH (AR_DEPTH),
        .R_DEPTH  (R_DEPTH),

        .SYNC_STAGES_TO_S (SYNC_STAGES_TO_S),
        .SYNC_STAGES_TO_M (SYNC_STAGES_TO_M)
    ) u_dut (
        .s_clk_i     (s_clk),
        .s_rst_n_i   (s_rst_n),

        .s_awaddr_i  (s_awaddr),
        .s_awlen_i   (s_awlen),
        .s_awsize_i  (s_awsize),
        .s_awburst_i (s_awburst),
        .s_awvalid_i (s_awvalid),
        .s_awready_o (s_awready),

        .s_wdata_i   (s_wdata),
        .s_wstrb_i   (s_wstrb),
        .s_wlast_i   (s_wlast),
        .s_wvalid_i  (s_wvalid),
        .s_wready_o  (s_wready),

        .s_bresp_o   (s_bresp),
        .s_bvalid_o  (s_bvalid),
        .s_bready_i  (s_bready),

        .s_araddr_i  (s_araddr),
        .s_arlen_i   (s_arlen),
        .s_arsize_i  (s_arsize),
        .s_arburst_i (s_arburst),
        .s_arvalid_i (s_arvalid),
        .s_arready_o (s_arready),

        .s_rdata_o   (s_rdata),
        .s_rresp_o   (s_rresp),
        .s_rlast_o   (s_rlast),
        .s_rvalid_o  (s_rvalid),
        .s_rready_i  (s_rready),

        .m_clk_i     (m_clk),
        .m_rst_n_i   (m_rst_n),

        .m_awaddr_o  (m_awaddr),
        .m_awlen_o   (m_awlen),
        .m_awsize_o  (m_awsize),
        .m_awburst_o (m_awburst),
        .m_awvalid_o (m_awvalid),
        .m_awready_i (m_awready),

        .m_wdata_o   (m_wdata),
        .m_wstrb_o   (m_wstrb),
        .m_wlast_o   (m_wlast),
        .m_wvalid_o  (m_wvalid),
        .m_wready_i  (m_wready),

        .m_bresp_i   (m_bresp),
        .m_bvalid_i  (m_bvalid),
        .m_bready_o  (m_bready),

        .m_araddr_o  (m_araddr),
        .m_arlen_o   (m_arlen),
        .m_arsize_o  (m_arsize),
        .m_arburst_o (m_arburst),
        .m_arvalid_o (m_arvalid),
        .m_arready_i (m_arready),

        .m_rdata_i   (m_rdata),
        .m_rresp_i   (m_rresp),
        .m_rlast_i   (m_rlast),
        .m_rvalid_i  (m_rvalid),
        .m_rready_o  (m_rready)
    );

endmodule : tb_async_axi_fifo

`default_nettype wire
