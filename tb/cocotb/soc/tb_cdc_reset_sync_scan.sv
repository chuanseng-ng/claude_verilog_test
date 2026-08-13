// tb_cdc_reset_sync_scan.sv
// Bead claude_verilog_test-07n — directed testbench for cdc_reset_sync's DFT
// scan bypass mux (scanmode_i / scan_rst_ni).
//
// Directly instantiates cdc_reset_sync and re-exports every port flat, so
// cocotb can drive scanmode_i / scan_rst_ni independently of rst_n_i and
// prove the mux actually SELECTS between the two sources -- not merely that
// the ports exist and are tied off inert, which is all soc_top's current
// (no-DFT-flow) usage exercises.
//
// This project has no DFT/scan flow yet -- this testbench is a unit-level
// proof that the new primitive behaviour is real, not a DFT integration
// test.

module tb_cdc_reset_sync_scan #(
    parameter int unsigned STAGES = 2
) (
    input  logic clk_i,
    input  logic rst_n_i,
    input  logic scanmode_i,
    input  logic scan_rst_ni,
    output logic rst_n_o
);

    cdc_reset_sync #(
        .STAGES (STAGES)
    ) u_dut (
        .clk_i       (clk_i),
        .rst_n_i     (rst_n_i),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (rst_n_o)
    );

endmodule : tb_cdc_reset_sync_scan
