// pll_clkgen_pnr.sv
// Synthesis-only (PnR) substitute for pll_clkgen.sv.
//
// pll_clkgen.sv uses parameter real + parameter string + generate if (string)
// constructs that trigger Synlig/UHDM RTLIL empty-wire bugs in this Yosys
// version (kernel/rtlil.cc:2150 assert).  For PnR synthesis, PLL_IMPL is
// always "STUB" (pll_rnm.sv is not synthesisable and is excluded from
// VERILOG_FILES).  This wrapper removes all non-synthesisable parameters
// and unconditionally instantiates pll_clkgen_stub, which is lint-clean and
// synthesis-safe.
//
// ONLY included in VERILOG_FILES for PnR configs (pnr/asap7/soc/config.json).
// The RTL simulation flow continues to use rtl/soc/pll/pll_clkgen.sv.

`default_nettype none

module pll_clkgen #(
    // Accepted but ignored for synthesisability — PnR always uses STUB mode.
    // PLL_IMPL is int unsigned 0 in PnR (soc_top hides parameter string under
    // __pnr__); accepted here with matching int unsigned type.
    /* verilator lint_off UNUSEDPARAM */
    parameter int unsigned PLL_IMPL        = 0,   // 0 = STUB (only value in PnR)
    parameter int unsigned STUB_LOCK_CYCLES = 16,
    parameter int unsigned N_DIV_DEFAULT  = 13,
    parameter int unsigned LOCK_PERSIST_CYCLES = 5
    /* verilator lint_on  UNUSEDPARAM */
) (
    input  logic       ref_clk_i,
    input  logic       rst_n_i,
    input  logic [3:0] feedback_div,
    input  logic [1:0] post_div_sel,
    output logic       out_clk_o,
    output logic       locked_o
);

    // Unconditionally instantiate the digital stub — no generate, no real types,
    // no string comparisons.  Synthesis will always see STUB behaviour.
    pll_clkgen_stub #(
        .LOCK_CYCLES (STUB_LOCK_CYCLES)
    ) u_stub (
        .ref_clk_i   (ref_clk_i),
        .rst_n_i     (rst_n_i),
        .feedback_div(feedback_div),
        .post_div_sel(post_div_sel),
        .out_clk_o   (out_clk_o),
        .locked_o    (locked_o)
    );

endmodule : pll_clkgen

`default_nettype wire
