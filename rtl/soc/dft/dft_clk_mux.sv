// dft_clk_mux.sv
// DFT Stage 1a (bead claude_verilog_test-j41m.2, GH #244).
//
// Test-clock bypass for one clock root: in scan mode the clock is the tester's
// test clock, otherwise the functional clock, so that every flop below the
// root is clocked from a port during test (docs/design/DFT_ARCHITECTURE.md
// sec.9.3). A module of its own, rather than an inline `?:`, so that
//   * every test-clock mux in the design has one greppable name, and the Stage 2
//     insertion step and the clock/reset controllability check can find them;
//   * CTS and STA see a single, deliberately placed cell per root.
//
// Plain 2:1 mux, deliberately NOT a glitch-free (enable-before-switch)
// switcher. sel_i is quasi-static: it is set while neither clock is running
// and not toggled while either one is, which is how the ATE or the Stage 1b TAP
// uses scan_mode. A synchronised glitch-free switch needs a clock in each source
// domain to retire the old selection and deadlocks when the functional clock is
// stopped; it belongs with the TAP (bead j41m.3), where the select is generated.
//
// Functional mode (sel_i = 0): clk_o === func_clk_i, no logic other than the mux.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module dft_clk_mux (
    input  logic func_clk_i,
    input  logic test_clk_i,
    input  logic sel_i,        // 1 = scan/test mode: use test_clk_i
    output logic clk_o
);

    assign clk_o = sel_i ? test_clk_i : func_clk_i;

endmodule : dft_clk_mux
