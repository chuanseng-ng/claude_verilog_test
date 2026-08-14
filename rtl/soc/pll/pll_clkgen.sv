// pll_clkgen.sv
// Phase 7 (M-c) — PDK-agnostic PLL clock generator wrapper.
//
// Selects between two implementations via the PLL_IMPL string parameter:
//
//   "STUB" (default):
//       Instantiates pll_clkgen_stub — pure-digital, synthesisable,
//       no real types, no #delays.  Lock counter asserts locked_o after
//       STUB_LOCK_CYCLES ref_clk_i edges.  out_clk_o = ref_clk_i.
//       Use for: ASIC synthesis, CI lint, and all existing digital tests.
//
//   "RNM":
//       Instantiates pll_rnm (analog/pll_clkgen/models/pll_rnm.sv) —
//       SystemVerilog Real-Number Model with vtune settling and phase
//       accumulator.  out_clk_o is a 1.282 GHz clock (N=13, /1).
//       Use for: Phase 7 M-c AMS co-simulation with cocotb.
//       Requires simulator that supports SV real types (Verilator 5 +
//       --no-timing, Questa, VCS).  NOT synthesisable.
//
// Port list is shared between both implementations (identical to pll_rnm.sv).
//
// Coding rules:
//   * Top-level wrapper: wiring only, no logic
//   * PLL_IMPL is a compile-time elaboration parameter — no run-time mux
//   * generate/if used to select; unused branch elaborates but is pruned
//
// Lint target: lint-only -Wall -Wno-IMPORTSTAR 0 errors 0 warnings
//   Elaborates with STUB branch only (default PLL_IMPL).
//   The RNM branch is present in the generate block but pruned when
//   PLL_IMPL != "RNM"; pll_rnm.sv is excluded from the lint source list.

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
    input  logic       ref_clk_i,    // 100 MHz reference (crystal / XO)
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

