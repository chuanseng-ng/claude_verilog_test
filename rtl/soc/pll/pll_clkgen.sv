// pll_clkgen - PDK-agnostic PLL clock generator wrapper.
//
// Function: PLL_IMPL selects the implementation at elaboration. The port list is the same for both.
//   "STUB" (default): pll_clkgen_stub. It is digital and synthesisable. locked_o asserts after STUB_LOCK_CYCLES ref_clk_i edges.
//   out_clk_o is ref_clk_i. Use it for synthesis, lint and the digital tests.
//   "RNM": pll_rnm, a real-number model with vtune settling and a phase accumulator.
//   It needs a simulator with SV real types. It is not synthesisable.
// Main parameters: PLL_IMPL and STUB_LOCK_CYCLES. The RNM model constants are parameters of pll_rnm.
// Caller rules:
//   - The wrapper has no logic. The unused branch elaborates and is pruned.
//   - Lint with the STUB branch only. pll_rnm.sv is not in the lint source list.
// Doc: ds:mod:pll-clkgen
// Doc: cr:mod:pll-clkgen

module pll_clkgen #(
    // Implementation selector — "STUB" (default, synth-safe) or "RNM" (cosim)
    parameter string   PLL_IMPL        = "STUB",

    // ── STUB parameters (ignored when PLL_IMPL=="RNM") ──────────────────────
    // Number of ref_clk_i rising edges before locked_o asserts
    parameter int unsigned STUB_LOCK_CYCLES = 16,

    // ── RNM parameters (ignored when PLL_IMPL=="STUB") ──────────────────────
    // These mirror pll_rnm.sv defaults; override here to tune the model.
    // Suppressed: unused in STUB mode (the g_rnm branch is pruned by generate).
    /* verilator lint_off UNUSEDPARAM */
    parameter real F_REF_HZ              = 100.0e6,
    parameter int  N_DIV_DEFAULT         = 13,
    parameter real F_VCO_NOM_HZ          = 1.3e9,
    parameter real KVCO_HZ_V             = 80.0e6,
    parameter real VTUNE_NOM_V           = 0.35,
    parameter real LOCK_WINDOW_V         = 0.005,
    parameter int  LOCK_PERSIST_CYCLES   = 5,
    parameter real VTUNE_RESET_V         = 0.0
    /* verilator lint_on  UNUSEDPARAM */
) (
    input  logic       ref_clk_i,    // reference clock, F_REF_HZ (crystal / XO)
    input  logic       rst_n_i,      // active-low async reset
    input  logic [3:0] feedback_div, // N divider (4'h0 → N=N_DIV_DEFAULT=13)
    input  logic [1:0] post_div_sel, // post-divider: 00→/1 01→/2 10→/4
    output logic       out_clk_o,    // PLL output clock
    output logic       locked_o      // lock indicator
);

    generate
        if (PLL_IMPL == "RNM") begin : g_rnm
            pll_rnm #(
                .F_REF_HZ           (F_REF_HZ),
                .N_DIV_DEFAULT      (N_DIV_DEFAULT),
                .F_VCO_NOM_HZ       (F_VCO_NOM_HZ),
                .KVCO_HZ_V          (KVCO_HZ_V),
                .VTUNE_NOM_V        (VTUNE_NOM_V),
                .LOCK_WINDOW_V      (LOCK_WINDOW_V),
                .LOCK_PERSIST_CYCLES(LOCK_PERSIST_CYCLES),
                .VTUNE_RESET_V      (VTUNE_RESET_V)
            ) u_rnm (
                .ref_clk_i   (ref_clk_i),
                .rst_n_i     (rst_n_i),
                .feedback_div(feedback_div),
                .post_div_sel(post_div_sel),
                .out_clk_o   (out_clk_o),
                .locked_o    (locked_o)
            );
        end else begin : g_stub   // default: "STUB"
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
        end
    endgenerate

endmodule : pll_clkgen
