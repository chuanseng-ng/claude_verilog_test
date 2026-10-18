// tb_sram_fi_equiv.sv
// DFT Stage 4: the fault-injecting model with no fault armed vs the REAL 4 KB simulation model
// (sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv), same random traffic; mismatch_o counts every cycle on
// which any output differs.
module tb_sram_fi_equiv (
    input  logic        clk_i,
    input  logic        csb0_i,
    input  logic        web0_i,
    input  logic [3:0]  wmask0_i,
    input  logic [9:0]  addr0_i,
    input  logic [31:0] din0_i,
    input  logic        csb1_i,
    input  logic [9:0]  addr1_i,
    output logic [31:0] dout0_real_o,
    output logic [31:0] dout1_real_o,
    output logic [31:0] dout0_fi_o,
    output logic [31:0] dout1_fi_o,
    output logic [31:0] mismatch_o
);

    sky130_sram_4kbyte_1rw1r_32x1024_8 u_real (
        .clk0(clk_i), .csb0(csb0_i), .web0(web0_i), .wmask0(wmask0_i), .addr0(addr0_i), .din0(din0_i),
        .dout0(dout0_real_o), .clk1(clk_i), .csb1(csb1_i), .addr1(addr1_i), .dout1(dout1_real_o)
    );

    sram_fi_core #(.AW(10)) u_fi (
        .clk0(clk_i), .csb0(csb0_i), .web0(web0_i), .wmask0(wmask0_i), .addr0(addr0_i), .din0(din0_i),
        .dout0(dout0_fi_o), .clk1(clk_i), .csb1(csb1_i), .addr1(addr1_i), .dout1(dout1_fi_o)
    );

    initial mismatch_o = 32'd0;
    // Compare at every posedge (the outputs settled at the preceding negedge).
    always @(posedge clk_i) begin
        if (dout0_real_o !== dout0_fi_o || dout1_real_o !== dout1_fi_o) begin
            mismatch_o <= mismatch_o + 32'd1;
        end
    end

endmodule : tb_sram_fi_equiv
