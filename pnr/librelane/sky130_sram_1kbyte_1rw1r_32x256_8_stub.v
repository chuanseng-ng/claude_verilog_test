// sky130_sram_1kbyte_1rw1r_32x256_8_stub.v
// Synthesis black-box stub for the Sky130 1KB SRAM macro.
//
// The full behavioral simulation model is at:
//   $PDK_ROOT/sky130A/libs.ref/sky130_sram_macros/verilog/sky130_sram_1kbyte_1rw1r_32x256_8.v
//
// This stub provides only the port declarations so that Yosys/synlig can
// elaborate the design without ingesting the non-synthesizable simulation
// model (which contains $display, delays, etc.).
//
// The EXTRA_LEFS entry provides physical geometry for P&R.
// The EXTRA_LIBS entry provides timing arcs for STA.

(* blackbox *)
module sky130_sram_1kbyte_1rw1r_32x256_8 (
    // Port 0: RW
    input         clk0,
    input         csb0,    // active-low chip select
    input         web0,    // active-low write enable
    input  [3:0]  wmask0,  // byte write mask
    input  [7:0]  addr0,
    input  [31:0] din0,
    output [31:0] dout0,
    // Port 1: R
    input         clk1,
    input         csb1,
    input  [7:0]  addr1,
    output [31:0] dout1
);
endmodule
