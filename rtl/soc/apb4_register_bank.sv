// apb4_register_bank.sv
// Phase 5 (APB migration PR-1) — APB4 slave drop-in for axi_lite_register_bank.
//
// Functionally identical register semantics to axi_lite_register_bank.sv:
//   * Same parameters (N_REGS, ADDR_W, DW, SW, RESET_VAL, WMASK).
//   * Same hw_wen_i / hw_wdata_i per-register HW-write bypass (bypasses WMASK).
//   * Same regs_o output array.
//   * Same write priority: SW write wins over HW write on the same clock edge.
//   * Same out-of-range policy: writes dropped (pslverr=0), reads return 0 (pslverr=0).
//   * Same strb_expand / WMASK masking logic — ported verbatim.
//
// APB4 protocol (ARM IHI0024C):
//   SETUP phase  : psel=1, penable=0 — address/control set up.
//   ACCESS phase : psel=1, penable=1 — transfer completes when pready=1.
//   This module drives pready=1 every ACCESS phase (zero wait states); there is
//   no pipelining — one transfer per SETUP/ACCESS pair.
//
// Clock / reset: pclk / presetn (active-low, synchronous deassertion assumed).
// Data width: 32-bit (DW=32, SW=4) — validated in an initial block.
//
// Lint note: paddr[1:0] are unused (word-aligned register file); they are
// bracketed with a targeted lint_off to keep -Wall clean.

`default_nettype none

module apb4_register_bank #(
    parameter int unsigned N_REGS    = 16,
    parameter int unsigned ADDR_W    = 12,           // local byte address width
    parameter int unsigned DW        = 32,           // data width — must be 32
    parameter int unsigned SW        = 4,            // strobe width — must be 4
    parameter logic [31:0] RESET_VAL [N_REGS] = '{default: '0},
    // Per-register writable-bit mask (1 = SW-writable).  All-0 = read-only.
    parameter logic [31:0] WMASK     [N_REGS] = '{default: '1}
) (
    input  logic pclk,
    input  logic presetn,           // active-low synchronous reset

    // ══ APB4 slave port ══════════════════════════════════════════════════════
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] paddr,   // byte address; [1:0] unused (word-aligned)
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [DW-1:0]     pwdata,
    input  logic [SW-1:0]     pstrb,   // APB4 byte strobes
    output logic [DW-1:0]     prdata,
    output logic              pready,
    output logic              pslverr,

    // ══ Hardware side ═════════════════════════════════════════════════════════
    output logic [31:0] regs_o    [N_REGS],  // current register values
    input  logic        hw_wen_i  [N_REGS],  // hardware write enable (per reg)
    input  logic [31:0] hw_wdata_i[N_REGS]   // hardware write data (bypasses WMASK)
);

    // Static width checks.
    initial begin
        if (DW != 32) $fatal(1, "apb4_register_bank requires DW == 32");
        if (SW != 4)  $fatal(1, "apb4_register_bank requires SW == 4");
    end

    // Word index widths: WORDW spans the full ADDR_W slot; IDXW indexes N_REGS.
    localparam int unsigned WORDW = ADDR_W - 2;
    localparam int unsigned IDXW  = (N_REGS > 1) ? $clog2(N_REGS) : 1;

    logic [31:0] regs [N_REGS];
    assign regs_o = regs;

    // ── Byte-strobe to bit-mask expansion (identical to axi_lite_register_bank) ──
    function automatic logic [31:0] strb_expand(input logic [SW-1:0] strb);
        for (int unsigned b = 0; b < SW; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    // ── Word address from byte address ────────────────────────────────────────
    logic [WORDW-1:0] addr_word;
    assign addr_word = paddr[ADDR_W-1:2];

    // ── ACCESS phase pulse: valid APB transfer completing this cycle ───────────
    // psel=1, penable=1, pready=1.  We always drive pready=1 in ACCESS so this
    // is equivalent to: psel & penable.
    logic access;
    assign access  = psel & penable;
    assign pready  = 1'b1;          // zero wait states
    assign pslverr = 1'b0;          // no error conditions (OOR = OKAY + drop/0)

    // ── Register file ────────────────────────────────────────────────────────
    always_ff @(posedge pclk) begin
        if (!presetn) begin
            for (int unsigned r = 0; r < N_REGS; r++) regs[r] <= RESET_VAL[r];
        end else begin
            // 1. HW-side writes (bypass WMASK).  Applied every cycle.
            for (int unsigned r = 0; r < N_REGS; r++)
                if (hw_wen_i[r]) regs[r] <= hw_wdata_i[r];

            // 2. SW write on ACCESS phase of a write transfer.
            //    SW write priority: overrides HW write on same-cycle collision.
            //    GH #87: zero-extend addr_word to 32 b before comparing with N_REGS
            //    so that N_REGS == 2**WORDW does not wrap to 0 (truncating cast bug).
            if (access && pwrite) begin
                if ({{(32-WORDW){1'b0}}, addr_word} < N_REGS) begin
                    automatic logic [IDXW-1:0] ci = addr_word[IDXW-1:0];
                    automatic logic [31:0]     m  = WMASK[ci] & strb_expand(pstrb);
                    regs[ci] <= (regs[ci] & ~m) | (pwdata & m);
                end
                // Out-of-range: write silently dropped, pslverr=0.
            end
        end
    end

    // ── Read data ─────────────────────────────────────────────────────────────
    // APB read: prdata is sampled by the master at the end of the ACCESS phase
    // (when pready is high).  We drive it combinatorially — valid whenever psel
    // is asserted (covers both SETUP and ACCESS), which is safe and conventional.
    always_comb begin
        if (!pwrite && {{(32-WORDW){1'b0}}, addr_word} < N_REGS)
            prdata = regs[addr_word[IDXW-1:0]];
        else
            prdata = '0;
    end

endmodule : apb4_register_bank

`default_nettype wire
