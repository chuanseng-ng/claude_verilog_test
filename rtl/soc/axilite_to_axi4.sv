// axilite_to_axi4.sv
// Phase 5 (M8) — AXI4-Lite read master → AXI4 read-only master adapter.
//
// Purpose: the GPU ifetch port (m_axil_if_*) is a pure AXI4-Lite read
// channel.  This adapter presents it to the AXI4 crossbar as a full AXI4
// read master (arlen=0, arsize=4B, arburst=INCR, arid=const=0).
// Write channels are tied off: awvalid=0, wvalid=0, bready=1.
//
// AXI4 handshake buffering (Phase 5 M9 fix):
//   The GPU compute unit asserts m_axil_if_arvalid for exactly one cycle
//   (driven by warp_issue_i which is a single-cycle scheduler pulse).
//   AXI4 rule A3-38 requires arvalid to remain asserted until arready is
//   seen.  If arready does not arrive that same cycle (e.g. the downstream
//   crossbar is registering its R_IDLE→R_AR transition), the GPU CU drops
//   arvalid, the crossbar AR channel is abandoned, and the fetch stalls.
//
//   Fix: a one-entry AR skid buffer.  When s_axil_arvalid rises and we are
//   not already holding a pending request (ar_hold_q==0), we capture araddr
//   and assert m_axi_arvalid immediately (combinatorially) AND latch both
//   into ar_hold_q / ar_addr_q on the same rising edge.  We de-assert
//   m_axi_arvalid (and clear the buffer) only when m_axi_arready is seen.
//   s_axil_arready is returned to the GPU CU only on the accepting cycle
//   so the CU does not re-issue the same address.
//
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

    // ── AR skid buffer: hold arvalid until arready (AXI4 A3-38) ─────────────
    // ar_hold_q=1 means we have a pending AR transaction the crossbar has not
    // yet accepted.  ar_addr_q holds the buffered address.
    logic             ar_hold_q;
    logic [AW-1:0]    ar_addr_q;

    // Combinatorial: present arvalid to crossbar from either the live slave
    // input (new request) or the buffer (held request).
    logic ar_pending;
    assign ar_pending = ar_hold_q | s_axil_arvalid;

    assign m_axi_arid    = IW'(MASTER_ID);
    assign m_axi_araddr  = ar_hold_q ? ar_addr_q : s_axil_araddr;
    assign m_axi_arlen   = '0;                  // single beat
    assign m_axi_arsize  = AXI_SIZE_4B;         // 4 bytes
    assign m_axi_arburst = AXI_BURST_INCR;
    assign m_axi_arvalid = ar_pending;

    // arready back to GPU CU: only on the cycle we accept a NEW request
    // (buffer was empty and we got arready simultaneously), or on the cycle
    // we drain the buffer (arready fires while ar_hold_q=1).
    // In both cases arready fires the cycle m_axi_arready fires.
    assign s_axil_arready = m_axi_arready & ar_pending;

    // AR skid buffer state machine
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ar_hold_q <= 1'b0;
            ar_addr_q <= '0;
        end else begin
            if (ar_pending && !m_axi_arready) begin
                // Crossbar not ready yet — latch/hold the address.
                ar_hold_q <= 1'b1;
                if (!ar_hold_q)
                    ar_addr_q <= s_axil_araddr;   // capture new address
                // else: ar_addr_q already holds the buffered address
            end else if (ar_pending && m_axi_arready) begin
                // Crossbar accepted the transaction — clear buffer.
                ar_hold_q <= 1'b0;
                ar_addr_q <= '0;
            end
        end
    end

    // ── Read channel pass-through (no buffering needed on R channel) ─────────
    assign s_axil_rdata  = m_axi_rdata;
    assign s_axil_rresp  = m_axi_rresp;
    assign s_axil_rvalid = m_axi_rvalid;
    assign m_axi_rready  = s_axil_rready;

    // ── Suppress unused port warning on write-channel inputs ─────────────────
    // m_axi_awready and m_axi_wready are inputs driven by crossbar — accepted
    // silently (awvalid=0 so awready is irrelevant; wvalid=0 so wready ignored)

endmodule : axilite_to_axi4
