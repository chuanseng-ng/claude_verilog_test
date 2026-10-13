// tb_cdc_sync.sv
// Bead claude_verilog_test-xtaa -- directed testbench for cdc_sync's
// STAGES and RESET_VAL parameters.
//
// One simulation covers the whole matrix the cocotb test needs:
//   g_m[i], i = 0..5  WIDTH=1, STAGES = 2 + i/2, RESET_VAL = i%2
//                     (STAGES 2,3,4  x  RESET_VAL 0,1)
//   u_mixed           WIDTH=4, STAGES=3, RESET_VAL=4'b1010 (mixed per-bit
//                     pattern, non-default depth)
// All instances share clk_i / rst_n_i; the data inputs are independent.

module tb_cdc_sync (
    input  logic       clk_i,
    input  logic       rst_n_i,

    input  logic [5:0] dm_i,   // matrix instance i takes dm_i[i]
    output logic [5:0] qm_o,

    input  logic [3:0] dx_i,   // mixed-pattern instance
    output logic [3:0] qx_o
);

    genvar i;
    generate
        for (i = 0; i < 6; i++) begin : g_m
            cdc_sync #(
                .WIDTH     (1),
                .STAGES    (2 + i / 2),
                .RESET_VAL (1'(i % 2))
            ) u_dut (
                .clk_i   (clk_i),
                .rst_n_i (rst_n_i),
                .d_i     (dm_i[i]),
                .q_o     (qm_o[i])
            );
        end
    endgenerate

    // Four independent single-bit lines: this wrapper does not claim the
    // lines are coherent (see the primitive's scope warning); it exists to
    // prove each bit takes its own bit of RESET_VAL.
    cdc_sync #(
        .WIDTH     (4),
        .STAGES    (3),
        .RESET_VAL (4'b1010)
    ) u_mixed (
        .clk_i   (clk_i),
        .rst_n_i (rst_n_i),
        .d_i     (dx_i),
        .q_o     (qx_o)
    );

endmodule : tb_cdc_sync
