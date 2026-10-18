// BUFGCE.v -- SIMULATION / LINT STUB of the Xilinx 7-series BUFGCE primitive (bead hlrm.2). NOT for synthesis.
//
// Never add this directory to a Vivado file list: Vivado must bind `BUFGCE` to the unisim primitive, and a user module
// of the same name would shadow it and synthesise to a fabric latch + AND (the exact LUT clock gate this arm replaces).
// It lives in rtl/fpga/sim/, not rtl/fpga/, so `ls rtl/fpga/*.sv` (tools/fpga/stage0_filelist.sh) cannot pick it up.
//
// Behaviour = the existing behavioural arm of rv32i_clock_gate: CE is captured while I is low, O = I & captured CE.
// (The real primitive matches this contract; the one difference is that real O is held low until the first I low phase.)
`timescale 1ns / 1ps
/* verilator lint_off UNOPTFLAT */
module BUFGCE (
    input  wire I,
    input  wire CE,
    output wire O
);
    reg ce_latch;
    /* verilator lint_off LATCH */
    always @* if (!I) ce_latch = CE;
    /* verilator lint_on LATCH */
    assign O = I & ce_latch;
endmodule
/* verilator lint_on UNOPTFLAT */
