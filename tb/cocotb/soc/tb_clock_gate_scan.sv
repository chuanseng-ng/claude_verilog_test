// tb_clock_gate_scan.sv
// Bead claude_verilog_test-j41m.2 (DFT Stage 1a): standalone wrapper for the
// rv32i_clock_gate test-enable (test_en) added for scan. Re-exports every
// port flat so cocotb can drive en / test_en independently and watch gclk.

module tb_clock_gate_scan (
    input  logic en,
    input  logic test_en,
    input  logic clk,
    output logic gclk
);

    rv32i_clock_gate u_dut (
        .en      (en),
        .test_en (test_en),
        .clk     (clk),
        .gclk    (gclk)
    );

endmodule : tb_clock_gate_scan
