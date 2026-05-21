// rv32i_cache_arbiter.sv
// Phase 3 — Cache-to-Memory AXI4-Lite Arbiter
//
// Multiplexes I-cache (read-only) and D-cache (read + write) onto a single
// AXI4-Lite master port.
//
// Priority policy: D-cache always takes priority over I-cache.
//   - D-cache write (writeback) has highest priority
//   - D-cache read (refill) has next priority
//   - I-cache read (refill) gets the bus when D-cache is idle
//
// Grant is held for the duration of an AXI transaction (not per-beat).
// With AXI4-Lite (no burst), each grant covers a single AR→R or AW+W→B.

module rv32i_cache_arbiter (
    input  logic        clk,
    input  logic        rst_n,

    // ── I-cache read channel ──────────────────────────────────────────────────
    input  logic [31:0] ic_araddr_i,
    input  logic        ic_arvalid_i,
    output logic        ic_arready_o,
    output logic [31:0] ic_rdata_o,
    output logic [1:0]  ic_rresp_o,
    output logic        ic_rvalid_o,
    input  logic        ic_rready_i,

    // ── D-cache read channel (refill) ────────────────────────────────────────
    input  logic [31:0] dc_araddr_i,
    input  logic        dc_arvalid_i,
    output logic        dc_arready_o,
    output logic [31:0] dc_rdata_o,
    output logic [1:0]  dc_rresp_o,
    output logic        dc_rvalid_o,
    input  logic        dc_rready_i,

    // ── D-cache write channel (writeback) ────────────────────────────────────
    input  logic [31:0] dc_awaddr_i,
    input  logic        dc_awvalid_i,
    output logic        dc_awready_o,
    input  logic [31:0] dc_wdata_i,
    input  logic [3:0]  dc_wstrb_i,
    input  logic        dc_wvalid_i,
    output logic        dc_wready_o,
    output logic        dc_bvalid_o,
    output logic [1:0]  dc_bresp_o,
    input  logic        dc_bready_i,

    // ── AXI4-Lite master (to memory) ─────────────────────────────────────────
    output logic [31:0] axi_araddr_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,
    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    output logic        axi_rready_o,

    output logic [31:0] axi_awaddr_o,
    output logic        axi_awvalid_o,
    input  logic        axi_awready_i,
    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,
    input  logic        axi_bvalid_i,
    input  logic [1:0]  axi_bresp_i,
    output logic        axi_bready_o
);

    // =========================================================================
    // Grant register
    //   2'b00 = idle (no grant)
    //   2'b01 = I-cache has bus (AR+R in progress)
    //   2'b10 = D-cache has bus for read (AR+R in progress)
    //   2'b11 = D-cache has bus for write (AW+W+B in progress)
    // =========================================================================
    typedef enum logic [1:0] {
        GRANT_NONE   = 2'b00,
        GRANT_IC_RD  = 2'b01,
        GRANT_DC_RD  = 2'b10,
        GRANT_DC_WR  = 2'b11
    } grant_t;

    grant_t grant_q;

    // Transaction complete signals
    logic ic_rd_done, dc_rd_done, dc_wr_done;
    assign ic_rd_done = (grant_q == GRANT_IC_RD) && axi_rvalid_i && axi_rready_o;
    assign dc_rd_done = (grant_q == GRANT_DC_RD) && axi_rvalid_i && axi_rready_o;
    assign dc_wr_done = (grant_q == GRANT_DC_WR) && axi_bvalid_i && axi_bready_o;

    // =========================================================================
    // Grant FSM
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            grant_q <= GRANT_NONE;
        end else begin
            case (grant_q)
                GRANT_NONE: begin
                    // Priority: D$ write > D$ read > I$ read
                    if (dc_awvalid_i || dc_wvalid_i) begin
                        grant_q <= GRANT_DC_WR;
                    end else if (dc_arvalid_i) begin
                        grant_q <= GRANT_DC_RD;
                    end else if (ic_arvalid_i) begin
                        grant_q <= GRANT_IC_RD;
                    end
                end
                GRANT_IC_RD:  if (ic_rd_done) grant_q <= GRANT_NONE;
                GRANT_DC_RD:  if (dc_rd_done) grant_q <= GRANT_NONE;
                GRANT_DC_WR:  if (dc_wr_done) grant_q <= GRANT_NONE;
                default:      grant_q <= GRANT_NONE;
            endcase
        end
    end

    // =========================================================================
    // AXI master mux (combinational)
    // =========================================================================

    // --- Read address channel ---
    always_comb begin
        axi_araddr_o  = '0;
        axi_arvalid_o = 1'b0;
        ic_arready_o  = 1'b0;
        dc_arready_o  = 1'b0;

        case (grant_q)
            GRANT_IC_RD: begin
                axi_araddr_o  = ic_araddr_i;
                axi_arvalid_o = ic_arvalid_i;
                ic_arready_o  = axi_arready_i;
            end
            GRANT_DC_RD: begin
                axi_araddr_o  = dc_araddr_i;
                axi_arvalid_o = dc_arvalid_i;
                dc_arready_o  = axi_arready_i;
            end
            GRANT_NONE: begin
                // Do NOT forward AR beats during GRANT_NONE.
                // The read-data routing (ic_rvalid_o / dc_rvalid_o) is gated
                // on grant_q, so any AR that completes while grant_q==GRANT_NONE
                // would produce rdata with no valid destination.  Wait one cycle
                // for the FSM to register the grant before forwarding AR.
            end
            default: ;
        endcase
    end

    // --- Read data channel (broadcast to winner) ---
    assign axi_rready_o = (grant_q == GRANT_IC_RD) ? ic_rready_i :
                          (grant_q == GRANT_DC_RD) ? dc_rready_i : 1'b1;

    assign ic_rdata_o  = axi_rdata_i;
    assign ic_rresp_o  = axi_rresp_i;
    assign ic_rvalid_o = (grant_q == GRANT_IC_RD) && axi_rvalid_i;

    assign dc_rdata_o  = axi_rdata_i;
    assign dc_rresp_o  = axi_rresp_i;
    assign dc_rvalid_o = (grant_q == GRANT_DC_RD) && axi_rvalid_i;

    // --- Write address channel ---
    assign axi_awaddr_o  = dc_awaddr_i;
    assign axi_awvalid_o = (grant_q == GRANT_DC_WR) && dc_awvalid_i;
    assign dc_awready_o  = (grant_q == GRANT_DC_WR) && axi_awready_i;

    // Allow grant when arbitrating (GRANT_NONE → GRANT_DC_WR same cycle)
    // Handled by registering grant; the first cycle with GRANT_NONE will not
    // issue AW yet; next cycle grant_q=GRANT_DC_WR and AW can proceed.

    // --- Write data channel ---
    assign axi_wdata_o  = dc_wdata_i;
    assign axi_wstrb_o  = dc_wstrb_i;
    assign axi_wvalid_o = (grant_q == GRANT_DC_WR) && dc_wvalid_i;
    assign dc_wready_o  = (grant_q == GRANT_DC_WR) && axi_wready_i;

    // --- Write response channel ---
    assign dc_bvalid_o = (grant_q == GRANT_DC_WR) && axi_bvalid_i;
    assign dc_bresp_o  = axi_bresp_i;
    assign axi_bready_o = (grant_q == GRANT_DC_WR) && dc_bready_i;

endmodule
