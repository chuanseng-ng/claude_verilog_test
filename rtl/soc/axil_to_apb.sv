// axil_to_apb.sv
// Phase 5 (APB migration PR-1) — AXI4-Lite slave → APB4 master bridge (depth-1).
//
// Sits between the existing AXI-Lite control ring (driven by axi4_to_axilite.sv)
// and an APB4 peripheral subtree (e.g. apb4_register_bank or future peripherals).
//
// Mapping:
//   AXI-Lite write  (AW+W)  → one APB write transfer  (SETUP → ACCESS).
//   AXI-Lite read   (AR)    → one APB read transfer    (SETUP → ACCESS).
//   Depth-1: one outstanding transfer at a time.
//   Single-beat only (AXI-Lite has no burst).
//   wstrb is forwarded as APB4 pstrb.
//   pslverr → bresp/rresp = AXI_RESP_SLVERR (2'b10).
//
// FSM states (per AXI channel pair):
//   IDLE    — waiting for a valid AW+W (write) or AR (read).
//   SETUP   — APB SETUP phase: psel=1, penable=0, one cycle.
//   ACCESS  — APB ACCESS phase: psel=1, penable=1, held until pready=1.
//   WRESP   — AXI write-response: drive bvalid until bready.
//   RRESP   — AXI read-response:  drive rvalid until rready.
//
// Write path:
//   The module accepts AW and W independently (AXI-Lite does not require them
//   to arrive in the same cycle).  Both are captured; once both are in hand the
//   APB write sequence begins.
//
// Read path:
//   AR is accepted; APB read sequence begins immediately.
//
// AXI4-Lite address/data widths: 32-bit address, 32-bit data, 4-bit strobe.
// APB4 address width must match (tied to AXI ADDR_W).
//
// Lint notes:
//   * axil_awprot / axil_arprot are unused (no APB AxPROT mapping) — supressed.
//   * paddr[1:0] unused on APB side (word-aligned slave) — suppressed in the
//     slave (apb4_register_bank); forwarded verbatim here (bridge is transparent).

`default_nettype none

module axil_to_apb #(
    parameter int unsigned ADDR_W = 32,              // AXI-Lite / APB address width
    parameter int unsigned DW     = 32,              // Data width — must be 32
    parameter int unsigned SW     = 4                // Strobe width — must be 4
) (
    input  logic clk,
    input  logic rst_n,             // active-low synchronous reset

    // ══ AXI4-Lite slave port ═════════════════════════════════════════════════
    // Write address channel
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]        s_axil_awprot,   // unused — no APB protection mapping
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    // Write data channel
    input  logic [DW-1:0]     s_axil_wdata,
    input  logic [SW-1:0]     s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    // Write response channel
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    // Read address channel
    input  logic [ADDR_W-1:0] s_axil_araddr,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]        s_axil_arprot,   // unused — no APB protection mapping
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    // Read data channel
    output logic [DW-1:0]     s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,

    // ══ APB4 master port ═════════════════════════════════════════════════════
    output logic              psel,
    output logic              penable,
    output logic              pwrite,
    output logic [ADDR_W-1:0] paddr,
    output logic [DW-1:0]     pwdata,
    output logic [SW-1:0]     pstrb,
    input  logic [DW-1:0]     prdata,
    input  logic              pready,
    input  logic              pslverr
);

    import axi_pkg::*;

    // Static width checks.
    initial begin
        if (DW != 32) $fatal(1, "axil_to_apb requires DW == 32");
        if (SW != 4)  $fatal(1, "axil_to_apb requires SW == 4");
    end

    // ── FSM ──────────────────────────────────────────────────────────────────
    typedef enum logic [2:0] {
        S_IDLE,     // waiting for AXI transaction
        S_SETUP,    // APB SETUP phase (psel=1, penable=0)
        S_ACCESS,   // APB ACCESS phase (psel=1, penable=1), wait for pready
        S_WRESP,    // drive AXI write response (bvalid)
        S_RRESP     // drive AXI read response  (rvalid)
    } state_e;

    state_e state_q, state_d;

    // Captured AXI fields.
    logic [ADDR_W-1:0] addr_q;     // captured address (write or read)
    logic [DW-1:0]     wdata_q;    // captured write data
    logic [SW-1:0]     wstrb_q;    // captured write strobes
    logic              is_write_q; // 1 = write transfer in flight

    // AW/W arrive independently; track which halves have been captured.
    logic              aw_cap_q, w_cap_q;

    // Both halves of the write arrived — ready to start APB write.
    logic              wr_ready;
    assign wr_ready = (aw_cap_q || (s_axil_awvalid && s_axil_awready)) &&
                      (w_cap_q  || (s_axil_wvalid  && s_axil_wready));

    // Captured APB response.
    logic [DW-1:0] prdata_q;
    logic          pslverr_q;

    // ── AXI ready signals ────────────────────────────────────────────────────
    // Accept AW/W only in IDLE (before we start the APB sequence).
    assign s_axil_awready = (state_q == S_IDLE) && !aw_cap_q;
    assign s_axil_wready  = (state_q == S_IDLE) && !w_cap_q;

    // Accept AR only in IDLE and only when no write is being assembled.
    // GH #85: also gate on !s_axil_awvalid && !s_axil_wvalid so that a
    // concurrent AR + AW + W presented in S_IDLE cannot handshake AR in the same
    // always_ff evaluation as the AW+W capture, which would overwrite addr_q with
    // the read address and clear is_write_q=0 before the write APB transfer starts.
    assign s_axil_arready = (state_q == S_IDLE) && !aw_cap_q && !w_cap_q &&
                            !s_axil_awvalid && !s_axil_wvalid;

    // ── AXI response outputs ─────────────────────────────────────────────────
    assign s_axil_bvalid = (state_q == S_WRESP);
    assign s_axil_bresp  = pslverr_q ? AXI_RESP_SLVERR : AXI_RESP_OKAY;

    assign s_axil_rvalid = (state_q == S_RRESP);
    assign s_axil_rdata  = prdata_q;
    assign s_axil_rresp  = pslverr_q ? AXI_RESP_SLVERR : AXI_RESP_OKAY;

    // ── APB outputs ──────────────────────────────────────────────────────────
    // Drive APB signals combinatorially from FSM state and captured registers.
    always_comb begin
        psel    = 1'b0;
        penable = 1'b0;
        pwrite  = is_write_q;
        paddr   = addr_q;
        pwdata  = wdata_q;
        pstrb   = wstrb_q;
        unique case (state_q)
            S_SETUP:  begin psel = 1'b1; penable = 1'b0; end
            S_ACCESS: begin psel = 1'b1; penable = 1'b1; end
            default:  begin psel = 1'b0; penable = 1'b0; end
        endcase
    end

    // ── Next-state logic ─────────────────────────────────────────────────────
    always_comb begin
        state_d = state_q;
        unique case (state_q)
            S_IDLE: begin
                if (wr_ready)
                    state_d = S_SETUP;          // write: both AW+W captured
                else if (s_axil_arvalid && s_axil_arready)
                    state_d = S_SETUP;          // read: AR accepted
            end
            S_SETUP:  state_d = S_ACCESS;       // SETUP is always one cycle
            S_ACCESS: if (pready) state_d = is_write_q ? S_WRESP : S_RRESP;
            S_WRESP:  if (s_axil_bready) state_d = S_IDLE;
            S_RRESP:  if (s_axil_rready) state_d = S_IDLE;
            default:  state_d = S_IDLE;
        endcase
    end

    // ── Registered state and data capture ────────────────────────────────────
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q    <= S_IDLE;
            aw_cap_q   <= 1'b0;
            w_cap_q    <= 1'b0;
            is_write_q <= 1'b0;
            addr_q     <= '0;
            wdata_q    <= '0;
            wstrb_q    <= '0;
            prdata_q   <= '0;
            pslverr_q  <= 1'b0;
        end else begin
            state_q <= state_d;

            // ── Write address capture ─────────────────────────────────────
            if (s_axil_awvalid && s_axil_awready) begin
                aw_cap_q   <= 1'b1;
                addr_q     <= s_axil_awaddr;
                is_write_q <= 1'b1;
            end

            // ── Write data capture ────────────────────────────────────────
            if (s_axil_wvalid && s_axil_wready) begin
                w_cap_q  <= 1'b1;
                wdata_q  <= s_axil_wdata;
                wstrb_q  <= s_axil_wstrb;
            end

            // ── Read address capture ──────────────────────────────────────
            if (s_axil_arvalid && s_axil_arready) begin
                addr_q     <= s_axil_araddr;
                is_write_q <= 1'b0;
                // wstrb not meaningful for reads; leave at reset value.
            end

            // ── APB response capture (ACCESS → response state) ───────────
            if (state_q == S_ACCESS && pready) begin
                prdata_q  <= prdata;
                pslverr_q <= pslverr;
            end

            // ── Clear capture flags once the APB sequence starts ──────────
            // On the IDLE→SETUP transition both halves are in hand; clear so
            // the next transaction can start capturing in the subsequent IDLE.
            if (state_q == S_IDLE && state_d == S_SETUP) begin
                aw_cap_q <= 1'b0;
                w_cap_q  <= 1'b0;
            end

            // ── Clear is_write on return to IDLE ─────────────────────────
            if (state_d == S_IDLE && state_q != S_IDLE)
                is_write_q <= 1'b0;
        end
    end

endmodule : axil_to_apb

`default_nettype wire
