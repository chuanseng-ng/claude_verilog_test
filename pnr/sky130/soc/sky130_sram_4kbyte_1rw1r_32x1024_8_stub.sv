// sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv
// Blackbox stub for the sky130_sram_4kbyte_1rw1r_32x1024_8 OpenRAM hard
// macro at SoC-top synthesis (GH #104 Sky130 SoC Stage-2). Yosys treats
// (* blackbox *) modules as externally-defined cells; the port interface
// is preserved for netlist connectivity but no logic is synthesised.
// The real implementation (GDS/LEF/LIB/SPICE) is in
// pnr/sky130/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8.{lef,lib} and
// /nobackup/openram_sky130_4kb/macro/sky130_sram_4kbyte_1rw1r_32x1024_8/
// (GDS/SPICE — local/nobackup only, not committed).
//
// Port list must exactly match the OpenRAM-generated
// sky130_sram_4kbyte_1rw1r_32x1024_8.v behavioural model: 1024 words x 32
// bits, 1 RW port (port 0) + 1 R-only port (port 1). USE_POWER_PINS is
// intentionally NOT defined here (matches rtl/soc/sram_controller.sv's
// `ifdef SRAM_SKY130` instantiation of u_sram_macro, and the existing
// sky130_sram_1kbyte_1rw1r_32x256_8 cache-macro convention): vccd1/vssd1
// connectivity is supplied by the LEF + PDN_MACRO_CONNECTIONS at PD time,
// not by RTL-level power ports.

`timescale 1ns/1ps

(* blackbox *)
module sky130_sram_4kbyte_1rw1r_32x1024_8 (
    // Port 0: RW
    clk0, csb0, web0, wmask0, addr0, din0, dout0,
    // Port 1: R
    clk1, csb1, addr1, dout1
);
    parameter NUM_WMASKS = 4;
    parameter DATA_WIDTH = 32;
    parameter ADDR_WIDTH = 10;

    input                     clk0;
    input                     csb0;
    input                     web0;
    input  [NUM_WMASKS-1:0]   wmask0;
    input  [ADDR_WIDTH-1:0]   addr0;
    input  [DATA_WIDTH-1:0]   din0;
    output [DATA_WIDTH-1:0]   dout0;

    input                     clk1;
    input                     csb1;
    input  [ADDR_WIDTH-1:0]   addr1;
    output [DATA_WIDTH-1:0]   dout1;

endmodule : sky130_sram_4kbyte_1rw1r_32x1024_8
