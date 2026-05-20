// rv32i_clock_gate.sv
// Glitch-free integrated clock gate for SRAM clk0 power reduction.
//
// Synthesis (__pnr__ defined by LibreLane Yosys steps): directly instantiates
// ICGx1_ASAP7_75t_R from the ASAP7 RVT SEQ liberty.  Pins: CLK (source
// clock), ENA (active-high enable, latched on low phase), SE (scan enable,
// tied 0), GCLK (gated output).
//
// Simulation / lint (__pnr__ not defined): behavioral latch-AND model that is
// cycle-accurate and glitch-free.  Verilator LATCH warning suppressed here.

/* verilator lint_off UNOPTFLAT */
module rv32i_clock_gate (
    input  logic en,
    input  logic clk,
    output logic gclk
);
`ifdef USE_ICG_CELL
    // USE_ICG_CELL is in VERILOG_DEFINES (Yosys) but not LINTER_DEFINES (Verilator).
    ICGx1_ASAP7_75t_R u_icg (.CLK(clk), .ENA(en), .SE(1'b0), .GCLK(gclk));
`else
    logic en_latch;
    /* verilator lint_off LATCH */
    always_latch if (!clk) en_latch = en;
    /* verilator lint_on LATCH */
    assign gclk = clk & en_latch;
`endif
endmodule
/* verilator lint_on UNOPTFLAT */
