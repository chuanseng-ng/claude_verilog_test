// sram_1rw_128x32_asap7_stub.v
// True blackbox stub for LibreLane ASAP7 synthesis of the GPU shared-memory
// banks. Yosys treats (* blackbox *) modules as externally-defined hard macros:
// the port interface is preserved for netlist connectivity but no logic is
// synthesized from the body (the 32 banks become hard macros, not flip-flops).
//
// Physical/timing views: pnr/asap7/sram_1rw_128x32_asap7.lef +
// pnr/asap7/sram_1rw_128x32_asap7_TT_0p7V_25C.lib.
// Simulation view: sim/sram_1rw_128x32_asap7.v (behavioral).
//
// Hand-crafted (depth-128 variant of sram_1rw_256x32_asap7); replace with an
// OpenRAM-compiled macro once OpenRAM ASAP7 characterisation is available.
//
// Port map:
//   clk0  — clock (posedge active)
//   csb0  — chip select bar (active low)
//   web0  — write enable bar (active low = write, high = read)
//   addr0 — 7-bit address [6:0] (128 words)
//   din0  — 32-bit write data [31:0]
//   dout0 — 32-bit read data [31:0] (registered, available next cycle)

`timescale 1ns/1ps

(* blackbox *)
module sram_1rw_128x32_asap7 (
    input  wire        clk0,
    input  wire        csb0,
    input  wire        web0,
    input  wire [ 6:0] addr0,
    input  wire [31:0] din0,
    output wire [31:0] dout0
);
endmodule
