// sram_1rw_256x32_asap7_stub.v
// True blackbox stub for LibreLane ASAP7 synthesis.
// Yosys treats modules with (* blackbox *) as externally-defined black boxes —
// the port interface is preserved for netlist connectivity but no logic is
// synthesized from the body.
//
// Replace with OpenRAM-compiled sram_1rw_256x32_asap7.v once OpenRAM v2.x
// ASAP7 characterisation is available.
//
// Port map (identical to sram_1rw_256x32_freepdk45):
//   clk0  — clock (posedge active)
//   csb0  — chip select bar (active low)
//   web0  — write enable bar (active low = write, high = read)
//   addr0 — 8-bit address [7:0]
//   din0  — 32-bit write data [31:0]
//   dout0 — 32-bit read data [31:0] (registered, available next cycle)

`timescale 1ns/1ps

(* blackbox *)
module sram_1rw_256x32_asap7 (
    input  wire        clk0,
    input  wire        csb0,
    input  wire        web0,
    input  wire [ 7:0] addr0,
    input  wire [31:0] din0,
    output wire [31:0] dout0
);
endmodule
