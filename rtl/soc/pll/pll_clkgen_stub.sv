// pll_clkgen_stub.sv
// Phase 7 (M-c) — Pure-digital synthesisable PLL stub.
//
// Purpose:
//   Provides a lint- and synthesis-clean placeholder for the PLL so that
//   the SoC can elaborate, pass Verilator -Wall, and run existing digital
//   tests unchanged.  The stub does NOT multiply the reference clock; it
//   passes ref_clk_i straight through to out_clk_o (after the lock window)
//   so that cocotb testbenches continue to receive a valid clock.
//
//   Lock behaviour:
//     A saturating counter runs on ref_clk_i.  When it reaches
//     LOCK_CYCLES-1 it asserts locked_o.  Reset clears it.
//     This models the finite lock-acquisition time without any real arithmetic.
//
//   Clock output:
//     out_clk_o = ref_clk_i (no multiply).
//     post_div_sel and feedback_div are accepted as inputs (no lint error)
//     but do not alter out_clk_o — frequency division is not synthesisable
//     without a PLL primitive.  The RNM variant handles real divide ratios.
//
// Interface is identical to pll_rnm.sv so pll_clkgen.sv can select
// between the two with a single generate statement.
//
// Coding rules:
//   * No #delays, no initial blocks, no real types
//   * All registers synchronous reset (active-low)
//   * No `default_nettype` directive (Spyglass IND, CODING_GUIDELINES.md §1.3)
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module pll_clkgen_stub #(
    // Number of ref_clk_i rising edges to wait before asserting locked_o.
    // Default 16 cycles: small enough for testbenches, large enough to model
    // a plausible acquisition window.
    parameter int unsigned LOCK_CYCLES = 16
) (
    input  logic       ref_clk_i,
    input  logic       rst_n_i,
    // Config inputs — consumed (no UNUSEDSIGNAL) but do not affect stub output
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [3:0] feedback_div,
    input  logic [1:0] post_div_sel,
    /* verilator lint_on  UNUSEDSIGNAL */
    output logic       out_clk_o,
    output logic       locked_o
);

    // Lock counter — counts ref edges until LOCK_CYCLES reached
    localparam int unsigned CNTW = $clog2(LOCK_CYCLES + 1);

    logic [CNTW-1:0] lock_cnt_q;
    logic            locked_q;

    always_ff @(posedge ref_clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            lock_cnt_q <= '0;
            locked_q   <= 1'b0;
        end else begin
            if (lock_cnt_q < CNTW'(LOCK_CYCLES)) begin
                lock_cnt_q <= lock_cnt_q + CNTW'(1);
            end
            locked_q <= (lock_cnt_q >= CNTW'(LOCK_CYCLES - 1));
        end
    end

    assign locked_o   = locked_q;
    // Pass ref clock straight through — no multiplication in digital stub
    assign out_clk_o  = ref_clk_i;

endmodule : pll_clkgen_stub

