// axi4_to_axilite.sv
// Phase 5 (M8) — AXI4 slave → AXI4-Lite master bridge for peripheral ring.
//
// Purpose: the CPU D-cache issues AXI4 bursts (arlen/awlen up to 3 for cache
// refill) to any address, including the peripheral window 0x2000_1000–6FFF.
// This bridge sits between the crossbar S2 (SLV_PERIPH) slave port and the
// axi_lite_interconnect master port, serialising multi-beat bursts into N
// sequential single-beat AXI4-Lite transactions.
//
// Design:
//   * One outstanding transaction at a time (depth-1).
//   * Write path: latch AW (id, addr, len), drain W beats one-by-one, send
//     one AXI-Lite write per beat (addr increments by 4 each beat, INCR),
//     collect OKAY/SLVERR responses and reply a single B beat (worst-case
//     SLVERR if any beat errored).
//   * Read path: latch AR (id, addr, len), issue one AXI-Lite read per beat,
//     forward R data beat-by-beat with rlast on the final beat.
//   * Write and read FSMs are independent (AXI4 allows concurrent W+R).
//   * AXI4 IDs: awid/arid stored, reflected on bid/rid.
//
// AXI4-Lite master ports use full 32-bit address (m_axil_awaddr/araddr).
// Peripheral slaves only decode their local 12-bit offset; upper bits ignored.
//
// Lint target: verilator -Wall 0 errors 0 warnings.

`default_nettype none

module axi4_to_axilite
    import axi_pkg::*;
#(
    parameter int unsigned AW   = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW   = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW   = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW   = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW = axi_pkg::AXI_LEN_WIDTH
) (
    input  logic clk,
    input  logic rst_n,

    // ── AXI4 slave (from crossbar SLV_PERIPH port) ──────────────────────────
    // Write address
    input  logic [IW-1:0]   s_awid,
    input  logic [AW-1:0]   s_awaddr,
    input  logic [LENW-1:0] s_awlen,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]      s_awsize,
    input  logic [1:0]      s_awburst,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic            s_awvalid,
    output logic            s_awready,
    // Write data
    input  logic [DW-1:0]   s_wdata,
    input  logic [SW-1:0]   s_wstrb,
    input  logic            s_wlast,
    input  logic            s_wvalid,
    output logic            s_wready,
    // Write response
    output logic [IW-1:0]   s_bid,
    output logic [1:0]      s_bresp,
    output logic            s_bvalid,
    input  logic            s_bready,
    // Read address
    input  logic [IW-1:0]   s_arid,
    input  logic [AW-1:0]   s_araddr,
    input  logic [LENW-1:0] s_arlen,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]      s_arsize,
    input  logic [1:0]      s_arburst,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic            s_arvalid,
    output logic            s_arready,
    // Read data
    output logic [IW-1:0]   s_rid,
    output logic [DW-1:0]   s_rdata,
    output logic [1:0]      s_rresp,
    output logic            s_rlast,
    output logic            s_rvalid,
    input  logic            s_rready,

    // ── AXI4-Lite master (to axi_lite_interconnect) ──────────────────────────
    output logic [AW-1:0]   m_axil_awaddr,
    output logic [2:0]      m_axil_awprot,
    output logic            m_axil_awvalid,
    input  logic            m_axil_awready,
    output logic [DW-1:0]   m_axil_wdata,
    output logic [SW-1:0]   m_axil_wstrb,
    output logic            m_axil_wvalid,
    input  logic            m_axil_wready,
    input  logic [1:0]      m_axil_bresp,
    input  logic            m_axil_bvalid,
    output logic            m_axil_bready,
    output logic [AW-1:0]   m_axil_araddr,
    output logic [2:0]      m_axil_arprot,
    output logic            m_axil_arvalid,
    input  logic            m_axil_arready,
    input  logic [DW-1:0]   m_axil_rdata,
    input  logic [1:0]      m_axil_rresp,
    input  logic            m_axil_rvalid,
    output logic            m_axil_rready
);

    // =========================================================================
    // WRITE path FSM
    // =========================================================================
    typedef enum logic [2:0] {
        WS_IDLE,    // waiting for AXI4 AW
        WS_DATA,    // accepting one AXI4 W beat
        WS_REQ,     // driving AXI-Lite AW + W until both handshake
        WS_B,       // waiting for AXI-Lite B
        WS_RESP     // sending AXI4 B back to master
    } ws_e;

    ws_e            ws_q;
    logic [IW-1:0]  w_id_q;
    logic [AW-1:0]  w_addr_q;       // current beat address
    logic [LENW-1:0] w_rem_q;       // beats remaining after current
    logic [1:0]     w_resp_q;       // accumulated worst-case response
    // Per-beat write data latch (captured on the AXI4 W handshake only).
    logic [DW-1:0]  wdata_q;
    logic [SW-1:0]  wstrb_q;
    // Track which AXI-Lite request channels have completed this beat.
    logic           aw_done_q;
    logic           w_done_q;

    // AW handshake: accept only when IDLE
    assign s_awready = (ws_q == WS_IDLE);

    // W handshake: accept exactly one beat in WS_DATA (the only state that
    // asserts s_wready, so data is never consumed without a real handshake).
    assign s_wready  = (ws_q == WS_DATA);

    // AXI-Lite AW drive (held until it handshakes)
    assign m_axil_awaddr  = w_addr_q;
    assign m_axil_awprot  = 3'b000;
    assign m_axil_awvalid = (ws_q == WS_REQ) && !aw_done_q;

    // AXI-Lite W drive (held until it handshakes)
    assign m_axil_wdata   = wdata_q;
    assign m_axil_wstrb   = wstrb_q;
    assign m_axil_wvalid  = (ws_q == WS_REQ) && !w_done_q;

    // AXI-Lite B accept always when in WS_B
    assign m_axil_bready  = (ws_q == WS_B);

    // AXI4 B response
    assign s_bid    = w_id_q;
    assign s_bresp  = w_resp_q;
    assign s_bvalid = (ws_q == WS_RESP);

    // Response accumulator: preserve DECERR over SLVERR over OKAY.
    function automatic logic [1:0] worse_resp(input logic [1:0] a, input logic [1:0] b);
        if (a == AXI_RESP_DECERR || b == AXI_RESP_DECERR)
            return AXI_RESP_DECERR;
        else if (a == AXI_RESP_SLVERR || b == AXI_RESP_SLVERR)
            return AXI_RESP_SLVERR;
        else
            return AXI_RESP_OKAY;
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ws_q      <= WS_IDLE;
            w_id_q    <= '0;
            w_addr_q  <= '0;
            w_rem_q   <= '0;
            w_resp_q  <= AXI_RESP_OKAY;
            wdata_q   <= '0;
            wstrb_q   <= '0;
            aw_done_q <= 1'b0;
            w_done_q  <= 1'b0;
        end else begin
            unique case (ws_q)
                WS_IDLE: begin
                    if (s_awvalid && s_awready) begin
                        w_id_q   <= s_awid;
                        w_addr_q <= s_awaddr;
                        w_rem_q  <= s_awlen;
                        w_resp_q <= AXI_RESP_OKAY;
                        ws_q     <= WS_DATA;
                    end
                end
                WS_DATA: begin
                    // Capture the W beat only on a genuine AXI4 W handshake.
                    if (s_wvalid && s_wready) begin
                        wdata_q   <= s_wdata;
                        wstrb_q   <= s_wstrb;
                        aw_done_q <= 1'b0;
                        w_done_q  <= 1'b0;
                        ws_q      <= WS_REQ;
                    end
                end
                WS_REQ: begin
                    // AW and W handshake independently; latch each as it fires.
                    if (m_axil_awvalid && m_axil_awready) aw_done_q <= 1'b1;
                    if (m_axil_wvalid  && m_axil_wready)  w_done_q  <= 1'b1;
                    if ((aw_done_q || (m_axil_awvalid && m_axil_awready)) &&
                        (w_done_q  || (m_axil_wvalid  && m_axil_wready))) begin
                        ws_q <= WS_B;
                    end
                end
                WS_B: begin
                    if (m_axil_bvalid && m_axil_bready) begin
                        w_resp_q <= worse_resp(w_resp_q, m_axil_bresp);
                        if (w_rem_q == '0) begin
                            // Last beat done
                            ws_q <= WS_RESP;
                        end else begin
                            // More beats: advance address, accept next W beat
                            w_addr_q <= w_addr_q + 32'd4;
                            w_rem_q  <= w_rem_q - 1'b1;
                            ws_q     <= WS_DATA;
                        end
                    end
                end
                WS_RESP: begin
                    if (s_bvalid && s_bready) begin
                        ws_q <= WS_IDLE;
                    end
                end
                default: ws_q <= WS_IDLE;
            endcase
        end
    end

    // =========================================================================
    // READ path FSM
    // =========================================================================
    typedef enum logic [1:0] {
        RS_IDLE,    // waiting for AR
        RS_AR,      // sending AXI-Lite AR
        RS_R,       // waiting for AXI-Lite R beat
        RS_FWD      // forwarding R beat to AXI4 master
    } rs_e;

    rs_e             rs_q;
    logic [IW-1:0]   r_id_q;
    logic [AW-1:0]   r_addr_q;
    logic [LENW-1:0] r_rem_q;
    // Registered AXI-Lite R beat. Reads always latch (RS_R) then forward
    // (RS_FWD); the beat is never both passed through and replayed.
    logic [DW-1:0]   rdata_q;
    logic [1:0]      rresp_q;

    assign s_arready = (rs_q == RS_IDLE);

    assign m_axil_araddr  = r_addr_q;
    assign m_axil_arprot  = 3'b000;
    assign m_axil_arvalid = (rs_q == RS_AR);

    assign m_axil_rready  = (rs_q == RS_R);

    assign s_rid    = r_id_q;
    assign s_rdata  = rdata_q;
    assign s_rresp  = rresp_q;       // DECERR/SLVERR from interconnect preserved
    assign s_rvalid = (rs_q == RS_FWD);
    assign s_rlast  = (rs_q == RS_FWD) && (r_rem_q == '0);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rs_q     <= RS_IDLE;
            r_id_q   <= '0;
            r_addr_q <= '0;
            r_rem_q  <= '0;
            rdata_q  <= '0;
            rresp_q  <= AXI_RESP_OKAY;
        end else begin
            unique case (rs_q)
                RS_IDLE: begin
                    if (s_arvalid && s_arready) begin
                        r_id_q   <= s_arid;
                        r_addr_q <= s_araddr;
                        r_rem_q  <= s_arlen;
                        rs_q     <= RS_AR;
                    end
                end
                RS_AR: begin
                    if (m_axil_arvalid && m_axil_arready) begin
                        rs_q <= RS_R;
                    end
                end
                RS_R: begin
                    // Latch the AXI-Lite R beat, then forward it on AXI4.
                    if (m_axil_rvalid && m_axil_rready) begin
                        rdata_q <= m_axil_rdata;
                        rresp_q <= m_axil_rresp;
                        rs_q    <= RS_FWD;
                    end
                end
                RS_FWD: begin
                    if (s_rvalid && s_rready) begin
                        if (r_rem_q == '0) begin
                            rs_q <= RS_IDLE;
                        end else begin
                            r_addr_q <= r_addr_q + 32'd4;
                            r_rem_q  <= r_rem_q - 1'b1;
                            rs_q     <= RS_AR;
                        end
                    end
                end
                default: rs_q <= RS_IDLE;
            endcase
        end
    end

endmodule : axi4_to_axilite
