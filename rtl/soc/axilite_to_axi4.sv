// axilite_to_axi4.sv
// Phase 5 (M8) — AXI4-Lite read master → AXI4 read-only master adapter.
//
// Purpose: the GPU ifetch port (m_axil_if_*) is a pure AXI4-Lite read
// channel.  This adapter presents it to the AXI4 crossbar as a full AXI4
// read master (arlen=0, arsize=4B, arburst=INCR, arid=const=0).
// Write channels are tied off: awvalid=0, wvalid=0, bready=rst_n.
//
// AXI4 handshake buffering:
//   AXI4 rule A3-38 requires arvalid to remain asserted until arready is seen.
//   The GPU compute unit keeps m_axil_if_arvalid and its address stable until
//   s_axil_arready, so it is a conforming AXI4-Lite master.  A master that
//   pulses arvalid for one cycle and does not repeat it needs the buffer below.
//
//   A one-entry AR skid buffer covers such a master.  When s_axil_arvalid rises
//   with the buffer empty (ar_hold_q==0), m_axi_arvalid is asserted
//   combinatorially and araddr is latched into ar_addr_q on the same edge.  The
//   buffer is cleared only when m_axi_arready is seen.  s_axil_arready returns to
//   the master only on the accepting cycle, so a master that holds arvalid does
//   not issue the same address twice.
//
// Reset: m_axi_arvalid and s_axil_arready are low while rst_n is low or gpu_rst_i is high.
//
// GPU power cycle (Doc: ds:mod:pmu):
//   gpu_rst_i clears the AR skid buffer, so a request of the old GPU does not outlive
//   its reset.  rd_out_q marks a read in flight and is cleared by rst_n only.  While
//   gpu_off_i is high, and after it fell with that read still in flight (stale_q), the
//   adapter takes the R beat itself: m_axi_rready is forced high and s_axil_rvalid is
//   masked.  A read issued after gpu_off_i falls is not stale.  Tie both inputs to 0
//   for an instance with no GPU power cycle.
//
// Signals added / tied:
//   arid   = 0
//   arlen  = 0       (single-beat)
//   arsize = 3'b010  (4 bytes, AXI_SIZE_4B)
//   arburst= 2'b01   (INCR, AXI_BURST_INCR)
// Write channels fully tied off: awvalid = wvalid = 0, bready = rst_n, all other outputs 0.
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
    input  logic clk,
    input  logic rst_n,       // fabric reset: clears every flop
    input  logic gpu_rst_i,   // 1 = GPU domain in reset: clears the AR skid buffer only
    input  logic gpu_off_i,   // 1 = GPU domain off: a read in flight is drained

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
    assign m_axi_bready  = rst_n;  // no B is outstanding, so ready only drops in reset

    // ── AR skid buffer: hold arvalid until arready (AXI4 A3-38) ─────────────
    // ar_hold_q=1 means we have a pending AR transaction the crossbar has not
    // yet accepted.  ar_addr_q holds the buffered address.
    logic             ar_hold_q;
    logic [AW-1:0]    ar_addr_q;

    // Reset of the skid buffer: the fabric reset or the GPU domain reset.
    logic skid_rst_n;
    assign skid_rst_n = rst_n & ~gpu_rst_i;

    // Combinatorial: present arvalid to crossbar from either the live slave
    // input (new request) or the buffer (held request); none in reset.
    logic ar_pending;
    assign ar_pending = (ar_hold_q | s_axil_arvalid) & skid_rst_n;

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
    always_ff @(posedge clk or negedge skid_rst_n) begin
        if (!skid_rst_n) begin
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

    // ── Read channel: pass-through, with a drain of a read the GPU no longer waits for ──
    // rd_out_q: one read in flight (AR accepted, R beat not yet taken).  The crossbar
    // read engine of a slave takes one read at a time, so one flag is enough.  A new AR
    // and an R beat in one cycle keep the flag set.
    logic ar_hs, r_hs, rd_out_q, stale_q, r_drain;
    assign ar_hs   = m_axi_arvalid & m_axi_arready;
    assign r_hs    = m_axi_rvalid  & m_axi_rready;
    assign r_drain = rd_out_q & (gpu_off_i | stale_q);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_out_q <= 1'b0;
            stale_q  <= 1'b0;
        end else begin
            if (ar_hs)        rd_out_q <= 1'b1;
            else if (r_hs)    rd_out_q <= 1'b0;
            // stale_q keeps the drain on after gpu_off_i falls, until the beat is taken.
            if (r_hs)         stale_q  <= 1'b0;
            else if (r_drain) stale_q  <= 1'b1;
        end
    end

    assign s_axil_rdata  = m_axi_rdata;
    assign s_axil_rresp  = m_axi_rresp;
    assign s_axil_rvalid = m_axi_rvalid & ~r_drain;
    assign m_axi_rready  = s_axil_rready | r_drain;

    // ── Suppress unused port warning on write-channel inputs ─────────────────
    // m_axi_awready and m_axi_wready are inputs driven by crossbar — accepted
    // silently (awvalid=0 so awready is irrelevant; wvalid=0 so wready ignored)

endmodule : axilite_to_axi4
