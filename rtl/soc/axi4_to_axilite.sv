// axi4_to_axilite.sv
// AXI4 slave to AXI4-Lite master bridge for the peripheral ring.
//
// The CPU D-cache issues AXI4 bursts to any address, including the peripheral
// window. The bridge sits between the crossbar peripheral slave port and the
// axi_lite_interconnect master port. It splits a burst into single-beat
// AXI4-Lite transactions, one outstanding transaction per direction.
//   * Write: latch AW, accept W beats one at a time, send one AXI-Lite write
//     per beat, reply one B with the worst response (DECERR over SLVERR over
//     OKAY) of the forwarded beats.
//   * Read: latch AR, send one AXI-Lite read per beat, forward each R beat
//     with its own response and rlast on the final beat.
//   * The write and read FSMs are independent. awid/arid reflect on bid/rid.
//
// Beat address (AxBURST, AxSIZE), as the byte address of the beat:
//   * FIXED (0): every beat at the start address.
//   * INCR (1): first beat at the start address, then the address aligned
//     down to the beat size plus the beat size.
//   * WRAP (2): as INCR inside a window of (AxLEN+1) * beat size bytes. AXI4
//     allows 2, 4, 8 or 16 beats; other lengths give an undefined window.
//   * Reserved AxBURST=3 is treated as INCR. AxSIZE above 2 (wider than the
//     32-bit bus) is treated as 4 bytes.
//   * WDATA, WSTRB and read data pass through, so narrow lanes stay in place.
//
// Write burst end (WLAST against AWLEN):
//   * WLAST on a forwarded beat ends the burst after the AXI-Lite response of
//     that beat, also when AWLEN announced more beats.
//   * With the AWLEN count used up and no WLAST seen, WVALID is sampled after
//     the last AXI-Lite response. A further beat offered then means the
//     master sends more beats than AWLEN: they are accepted, not forwarded,
//     and B follows the beat with WLAST. No beat offered means WLAST was
//     omitted and the burst ends on the count.
//   * Late beats add no error to B. A late beat not yet offered at the sample
//     cannot be told from a missing WLAST. A late burst that never gets WLAST
//     stays in the sink state.
//
// Doc: tm:mod:axi4-to-axilite
//
// AXI4-Lite master ports use full 32-bit address (m_axil_awaddr/araddr).
// Peripheral slaves only decode their local 12-bit offset; upper bits ignored.

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
    input  logic [2:0]      s_awsize,
    input  logic [1:0]      s_awburst,
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
    input  logic [2:0]      s_arsize,
    input  logic [1:0]      s_arburst,
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
    // Beat address generation (shared by the write and read paths)
    // =========================================================================
    localparam int unsigned MW = LENW + 3;  // wrap window mask width

    // Beat size as log2 bytes: 0, 1 or 2. AxSIZE above 2 means 4 bytes.
    function automatic logic [1:0] size_eff(input logic [2:0] sz);
        return (sz[2] || sz[1]) ? 2'd2 : {1'b0, sz[0]};
    endfunction

    // Wrap window minus one: (len + 1) << size, less 1. The shift is a
    // three-way case so that no variable shifter is built.
    function automatic logic [MW-1:0] wrap_mask(input logic [LENW-1:0] len,
                                                input logic [1:0]      sz);
        logic [LENW:0]   beats;
        logic [MW-1:0]   bytes;
        beats = {1'b0, len} + 1'b1;
        unique case (sz)
            2'd0:    bytes = {2'b00, beats};
            2'd1:    bytes = {1'b0, beats, 1'b0};
            default: bytes = {beats, 2'b00};
        endcase
        return bytes - 1'b1;
    endfunction

    // Address of the beat that follows the one at addr.
    function automatic logic [AW-1:0] next_addr(input logic [AW-1:0] addr,
                                                input logic [1:0]    sz,
                                                input logic          fixed,
                                                input logic          wrap,
                                                input logic [MW-1:0] wmask);
        logic [AW-1:0] step;
        logic [AW-1:0] aligned;
        logic [AW-1:0] incr;
        logic [AW-1:0] wm;
        unique case (sz)
            2'd0:    step = AW'(1);
            2'd1:    step = AW'(2);
            default: step = AW'(4);
        endcase
        aligned = addr & ~(step - AW'(1));
        incr    = aligned + step;
        wm      = AW'(wmask);
        if (fixed)     return addr;
        else if (wrap) return (addr & ~wm) | (incr & wm);
        else           return incr;
    endfunction

    // =========================================================================
    // WRITE path FSM
    // =========================================================================
    typedef enum logic [2:0] {
        WS_IDLE,    // waiting for AXI4 AW
        WS_DATA,    // accepting one AXI4 W beat
        WS_REQ,     // driving AXI-Lite AW + W until both handshake
        WS_B,       // waiting for AXI-Lite B
        WS_SINK,    // accepting W beats beyond AWLEN without forwarding them
        WS_RESP     // sending AXI4 B back to master
    } ws_e;

    ws_e            ws_q;
    logic [IW-1:0]  w_id_q;
    logic [AW-1:0]  w_addr_q;       // current beat address
    logic [LENW-1:0] w_rem_q;       // beats remaining after current
    logic [1:0]     w_resp_q;       // accumulated worst-case response
    logic [1:0]     w_size_q;       // beat size, log2 bytes
    logic           w_fixed_q;      // FIXED burst
    logic           w_wrap_q;       // WRAP burst
    logic [MW-1:0]  w_wmask_q;      // wrap window minus one
    logic           w_last_q;       // WLAST seen on the beat now forwarded
    // Per-beat write data latch (captured on the AXI4 W handshake only).
    logic [DW-1:0]  wdata_q;
    logic [SW-1:0]  wstrb_q;
    // Track which AXI-Lite request channels have completed this beat.
    logic           aw_done_q;
    logic           w_done_q;

    // AW handshake: accept only when IDLE
    assign s_awready = (ws_q == WS_IDLE);

    // W handshake: accept one beat in WS_DATA, or sink beats beyond AWLEN in
    // WS_SINK. No other state asserts s_wready, so data is never consumed
    // without a real handshake.
    assign s_wready  = (ws_q == WS_DATA) || (ws_q == WS_SINK);

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
            w_size_q  <= '0;
            w_fixed_q <= 1'b0;
            w_wrap_q  <= 1'b0;
            w_wmask_q <= '0;
            w_last_q  <= 1'b0;
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
                        w_size_q  <= size_eff(s_awsize);
                        w_fixed_q <= (s_awburst == 2'd0);
                        w_wrap_q  <= (s_awburst == 2'd2);
                        w_wmask_q <= wrap_mask(s_awlen, size_eff(s_awsize));
                        ws_q     <= WS_DATA;
                    end
                end
                WS_DATA: begin
                    // Capture the W beat only on a genuine AXI4 W handshake.
                    if (s_wvalid && s_wready) begin
                        wdata_q   <= s_wdata;
                        wstrb_q   <= s_wstrb;
                        w_last_q  <= s_wlast;
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
                        if (w_last_q || (w_rem_q == '0 && !s_wvalid)) begin
                            // WLAST seen, or the AWLEN count is used up and
                            // no further beat is offered.
                            ws_q <= WS_RESP;
                        end else if (w_rem_q == '0) begin
                            // Count used up, no WLAST, more beats offered.
                            ws_q <= WS_SINK;
                        end else begin
                            // More beats: advance address, accept next W beat
                            w_addr_q <= next_addr(w_addr_q, w_size_q, w_fixed_q,
                                                  w_wrap_q, w_wmask_q);
                            w_rem_q  <= w_rem_q - 1'b1;
                            ws_q     <= WS_DATA;
                        end
                    end
                end
                WS_SINK: begin
                    // Beats beyond AWLEN: accept, do not forward. B follows
                    // the beat that carries WLAST.
                    if (s_wvalid && s_wready && s_wlast) begin
                        ws_q <= WS_RESP;
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
    logic [1:0]      r_size_q;       // beat size, log2 bytes
    logic            r_fixed_q;      // FIXED burst
    logic            r_wrap_q;       // WRAP burst
    logic [MW-1:0]   r_wmask_q;      // wrap window minus one
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
            r_size_q  <= '0;
            r_fixed_q <= 1'b0;
            r_wrap_q  <= 1'b0;
            r_wmask_q <= '0;
            rdata_q  <= '0;
            rresp_q  <= AXI_RESP_OKAY;
        end else begin
            unique case (rs_q)
                RS_IDLE: begin
                    if (s_arvalid && s_arready) begin
                        r_id_q   <= s_arid;
                        r_addr_q <= s_araddr;
                        r_rem_q  <= s_arlen;
                        r_size_q  <= size_eff(s_arsize);
                        r_fixed_q <= (s_arburst == 2'd0);
                        r_wrap_q  <= (s_arburst == 2'd2);
                        r_wmask_q <= wrap_mask(s_arlen, size_eff(s_arsize));
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
                            r_addr_q <= next_addr(r_addr_q, r_size_q, r_fixed_q,
                                              r_wrap_q, r_wmask_q);
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
