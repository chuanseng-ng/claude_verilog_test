// apb4_register_bank - APB4 slave register bank with software and hardware write paths.
//
// Function: The bank holds N_REGS registers of DW bits behind an APB4 slave port.
//   The module drives pready=1 in every ACCESS phase. It has no wait states and no pipelining.
//   Software writes obey WMASK and the byte strobes. Hardware writes use hw_wen_i and hw_wdata_i and bypass WMASK.
//   regs_o shows the current register values.
// Parameters: N_REGS, ADDR_W, DW, SW, RESET_VAL and WMASK. DW must be 32 and SW must be 4. An initial block checks this.
// Clocks and resets: pclk is the clock. presetn is active low. The design assumes synchronous deassertion.
// Caller rules:
//   - On a same-cycle software and hardware write, software wins inside WMASK and hardware wins outside it.
//     A register with WMASK=0 is owned by hardware.
//   - A write outside the range is dropped. A read outside the range returns 0. pslverr stays 0.
//   - paddr[1:0] are unused.
// Doc: ds:mod:apb4-register-bank, cr:mod:apb4-register-bank

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

    // Static width checks (simulation only — synthesis/lint views never
    // instantiate DW/SW outside 32/4, and $fatal is non-synthesizable).
`ifndef __pnr__
    initial begin
        if (DW != 32) $fatal(1, "apb4_register_bank requires DW == 32");
        if (SW != 4)  $fatal(1, "apb4_register_bank requires SW == 4");
    end
`endif

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
            //    Same-cycle collision: SW wins inside WMASK, HW wins outside it.
            // Zero-extend addr_word to 32 bits before the N_REGS compare.
            if (access && pwrite) begin
                if ({{(32-WORDW){1'b0}}, addr_word} < N_REGS) begin
                    automatic logic [IDXW-1:0] ci = addr_word[IDXW-1:0];
                    automatic logic [31:0]     m  = WMASK[ci] & strb_expand(pstrb);
                    // SW owns the WMASK bits. HW owns the rest. Fold the same-cycle HW write into base.
                    automatic logic [31:0]     base =
                        hw_wen_i[ci] ? hw_wdata_i[ci] : regs[ci];
                    regs[ci] <= (base & ~m) | (pwdata & m);
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
