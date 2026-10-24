// sram_macros_sky130_bbox.sv - port-only black boxes for the SRAM_SKY130 arm.
// See sram_macros_bbox.sv for why the SRAM macros are black boxes in the DQC flow.
module sky130_sram_1kbyte_1rw1r_32x256_8 (
    input  logic        clk0,
    input  logic        csb0,
    input  logic        web0,
    input  logic [3:0]  wmask0,
    input  logic [7:0]  addr0,
    input  logic [31:0] din0,
    output logic [31:0] dout0,
    input  logic        clk1,
    input  logic        csb1,
    input  logic [7:0]  addr1,
    output logic [31:0] dout1
);
endmodule

module sky130_sram_4kbyte_1rw1r_32x1024_8 (
    input  logic        clk0,
    input  logic        csb0,
    input  logic        web0,
    input  logic [3:0]  wmask0,
    input  logic [9:0]  addr0,
    input  logic [31:0] din0,
    output logic [31:0] dout0,
    input  logic        clk1,
    input  logic        csb1,
    input  logic [9:0]  addr1,
    output logic [31:0] dout1
);
endmodule
