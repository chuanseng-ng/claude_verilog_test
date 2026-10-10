// rv32i_clock_gate.sv
// Glitch-free integrated clock gate for SRAM clk0 power reduction.
//
// Synthesis (__pnr__ defined by LibreLane Yosys steps): directly instantiates
// ICGx1_ASAP7_75t_R from the ASAP7 RVT SEQ liberty.  Pins: CLK (source
// clock), ENA (active-high enable, latched on low phase), SE (scan/test
// enable, = test_en), GCLK (gated output).
//
// DFT (bead claude_verilog_test-j41m.2, docs/design/DFT_ARCHITECTURE.md sec.4
// item 5): test_en forces the gate open.  In test mode every flop behind the
// gate must see the (test) clock whatever the functional enable says, or it
// is unreachable by scan and un-capturable by ATPG.  The behavioural arm
// latches (en | test_en) on the clock-low phase, i.e. the OR is in front of
// the latch exactly as in a library ICG with a scan-enable pin, so test_en
// inherits the same glitch-free guarantee as en.  test_en is quasi-static
// (a test-mode level, never toggled while the clock is running); tie it to
// 1'b0 where the gated clock feeds no scannable flop (SRAM-macro clocks).
//
// Simulation / lint (__pnr__ not defined): behavioral latch-AND model that is
// cycle-accurate and glitch-free.  Verilator LATCH warning suppressed here.

/* verilator lint_off UNOPTFLAT */
module rv32i_clock_gate (
    input  logic en,
    input  logic test_en,
    input  logic clk,
    output logic gclk
);
`ifdef USE_ICG_CELL
    // USE_ICG_CELL is in VERILOG_DEFINES (Yosys) but not LINTER_DEFINES (Verilator).
    ICGx1_ASAP7_75t_R u_icg (.CLK(clk), .ENA(en), .SE(test_en), .GCLK(gclk));
`else
    logic en_latch;
    /* verilator lint_off LATCH */
    always_latch if (!clk) en_latch = en | test_en;
    /* verilator lint_on LATCH */
    assign gclk = clk & en_latch;
`endif
endmodule
/* verilator lint_on UNOPTFLAT */
