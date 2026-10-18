// sky130_sram_fi_wrappers.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.14): fault-injecting stand-ins that take the module NAMES of the
// real Sky130 macros, so the REAL wrappers (sram_controller, npu_weight_mem) can be simulated with
// +define+SRAM_SKY130 against a macro model whose faults the suite controls. Used in place of
// sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv (test_mbist_tap.py proves sram_fi_core equals that model).
// Fault controls: <instance>.u_core.fi_* (see sram_fi_core.sv).
/* verilator lint_off DECLFILENAME */
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

    sram_fi_core #(.AW(10)) u_core (
        .clk0(clk0), .csb0(csb0), .web0(web0), .wmask0(wmask0), .addr0(addr0), .din0(din0), .dout0(dout0),
        .clk1(clk1), .csb1(csb1), .addr1(addr1), .dout1(dout1)
    );

endmodule : sky130_sram_4kbyte_1rw1r_32x1024_8

// The 1 KB macro of the CPU caches (tag + 4 data per cache): same stand-in, 256 words (c54a).
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

    sram_fi_core #(.AW(8)) u_core (
        .clk0(clk0), .csb0(csb0), .web0(web0), .wmask0(wmask0), .addr0(addr0), .din0(din0), .dout0(dout0),
        .clk1(clk1), .csb1(csb1), .addr1(addr1), .dout1(dout1)
    );

endmodule : sky130_sram_1kbyte_1rw1r_32x256_8
/* verilator lint_on DECLFILENAME */
