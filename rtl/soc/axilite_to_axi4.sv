// axilite_to_axi4.sv
// Phase 5 (M8) — AXI4-Lite read master → AXI4 read-only master adapter.
//
// Purpose: the GPU ifetch port (m_axil_if_*) is a pure AXI4-Lite read
// channel.  This adapter presents it to the AXI4 crossbar as a full AXI4
// read master (arlen=0, arsize=4B, arburst=INCR, arid=const=0).
// Write channels are tied off: awvalid=0, wvalid=0, bready=1.
//
// Signals passed through verbatim:
//   araddr, arvalid, arready, rdata, rresp, rvalid, rready
// Signals added / tied:
//   arid   = 0
//   arlen  = 0       (single-beat)
//   arsize = 3'b010  (4 bytes, AXI_SIZE_4B)
//   arburst= 2'b01   (INCR, AXI_BURST_INCR)
// Write channels fully tied off:
//   awvalid = 0,  wvalid = 0,  bready = 1
//   awid/awaddr/awlen/awsize/awburst/wdata/wstrb/wlast all tied 0.
//
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module axilite_to_axi4
    import axi_pkg::*;
#(
    parameter int unsigned AW   = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW   = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW   = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW   = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW = axi_pkg::AXI_LEN_WIDTH,
    // Fixed AXI4 master ID for GPU ifetch channel
    parameter logic [3:0] MASTER_ID = 4'd0
) (
    // Clock and reset (unused in pure combinatorial adapter, kept for
    // structural consistency and future pipeline register insertion)
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic clk,
    input  logic rst_n,
    /* verilator lint_on  UNUSEDSIGNAL */

    // ── AXI4-Lite read slave (from gpu_top m_axil_if_*) ─────────────────────
    input  logic [AW-1:0] s_axil_araddr,
    input  logic          s_axil_arvalid,
    output logic          s_axil_arready,
    output logic [DW-1:0] s_axil_rdata,
    output logic [1:0]    s_axil_rresp,
    output logic          s_axil_rvalid,
    input  logic          s_axil_rready,

    // ── AXI4 read master (to crossbar M1 port) ───────────────────────────────
    // Write address — tied off
    output logic [IW-1:0]   m_axi_awid,
    output logic [AW-1:0]   m_axi_awaddr,
    output logic [LENW-1:0] m_axi_awlen,
    output logic [2:0]      m_axi_awsize,
    output logic [1:0]      m_axi_awburst,
    output logic            m_axi_awvalid,
    input  logic            m_axi_awready,
    // Write data — tied off
    output logic [DW-1:0]   m_axi_wdata,
    output logic [SW-1:0]   m_axi_wstrb,
    output logic            m_axi_wlast,
    output logic            m_axi_wvalid,
    input  logic            m_axi_wready,
    // Write response — accepted, discarded
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [IW-1:0]   m_axi_bid,
    input  logic [1:0]      m_axi_bresp,
    input  logic            m_axi_bvalid,
    /* verilator lint_on  UNUSEDSIGNAL */
    output logic            m_axi_bready,
    // Read address
    output logic [IW-1:0]   m_axi_arid,
    output logic [AW-1:0]   m_axi_araddr,
    output logic [LENW-1:0] m_axi_arlen,
    output logic [2:0]      m_axi_arsize,
    output logic [1:0]      m_axi_arburst,
    output logic            m_axi_arvalid,
    input  logic            m_axi_arready,
    // Read data
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [IW-1:0]   m_axi_rid,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [DW-1:0]   m_axi_rdata,
    input  logic [1:0]      m_axi_rresp,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic            m_axi_rlast,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic            m_axi_rvalid,
    output logic            m_axi_rready
);

    // ── Write channels — fully tied off ─────────────────────────────────────
    assign m_axi_awid    = '0;
    assign m_axi_awaddr  = '0;
    assign m_axi_awlen   = '0;
    assign m_axi_awsize  = '0;
    assign m_axi_awburst = AXI_BURST_INCR;
    assign m_axi_awvalid = 1'b0;
    assign m_axi_wdata   = '0;
    assign m_axi_wstrb   = '0;
    assign m_axi_wlast   = 1'b0;
    assign m_axi_wvalid  = 1'b0;
    assign m_axi_bready  = 1'b1;   // always absorb spurious B beats

    // ── AXI4-Lite awready/wready (not connected from slave side; tie) ────────
    // (No unused signal here — these are outputs driven by the crossbar side)

    // ── Read channel pass-through with AXI4 decorations ─────────────────────
    assign m_axi_arid    = IW'(MASTER_ID);
    assign m_axi_araddr  = s_axil_araddr;
    assign m_axi_arlen   = '0;                 // single beat
    assign m_axi_arsize  = AXI_SIZE_4B;        // 4 bytes
    assign m_axi_arburst = AXI_BURST_INCR;
    assign m_axi_arvalid = s_axil_arvalid;
    assign s_axil_arready = m_axi_arready;

    assign s_axil_rdata  = m_axi_rdata;
    assign s_axil_rresp  = m_axi_rresp;
    assign s_axil_rvalid = m_axi_rvalid;
    assign m_axi_rready  = s_axil_rready;

    // ── Suppress unused port warning on write-channel inputs ─────────────────
    // m_axi_awready and m_axi_wready are inputs driven by crossbar — accepted
    // silently (awvalid=0 so awready is irrelevant; wvalid=0 so wready ignored)

endmodule : axilite_to_axi4
