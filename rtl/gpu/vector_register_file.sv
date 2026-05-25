// Vector register file: 8 warps × 32 registers × 8 lanes × 32 bits.
// r0 is hardwired to zero (reads return 0, writes are discarded).
// Two combinational read ports (A, B) and one synchronous write port.
//
// SYNTHESIS NOTE: Split into N_LANES separate per-lane memories (each
// 256×32-bit, address = {warp, reg}).  Each lane has a simple whole-word
// write enable so yosys infers a $mem cell for every lane.  A single
// monolithic 256×256-bit array with per-lane sub-word write-enables blocks
// $mem inference and causes a 65 536-DFF explosion in TECHMAP/ABC.
`default_nettype none

module vector_register_file
    import gpu_pkg::*;
(
    input  logic                               clk,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic                               rst_n,  // reserved for tb reset
    /* verilator lint_on UNUSEDSIGNAL */

    // Read port A (rs1)
    input  logic [WARP_W-1:0]                 rda_warp_i,
    input  logic [REG_W-1:0]                  rda_reg_i,
    output logic [N_LANES-1:0][REG_WIDTH-1:0] rda_data_o,

    // Read port B (rs2)
    input  logic [WARP_W-1:0]                 rdb_warp_i,
    input  logic [REG_W-1:0]                  rdb_reg_i,
    output logic [N_LANES-1:0][REG_WIDTH-1:0] rdb_data_o,

    // Write port (single reg per warp per cycle, per-lane mask)
    input  logic                               wr_en_i,
    input  logic [N_LANES-1:0]                wr_mask_i,
    input  logic [WARP_W-1:0]                 wr_warp_i,
    input  logic [REG_W-1:0]                  wr_reg_i,
    input  logic [N_LANES-1:0][REG_WIDTH-1:0] wr_data_i
);

    // Address space: {warp_id, reg_id} → 256 entries per lane
    localparam int RF_DEPTH = N_WARPS * N_REGS;  // 8 × 32 = 256
    localparam int RF_AW    = WARP_W + REG_W;    // 3 + 5 = 8

    wire [RF_AW-1:0] wr_addr  = {wr_warp_i, wr_reg_i};
    wire [RF_AW-1:0] rda_addr = {rda_warp_i, rda_reg_i};
    wire [RF_AW-1:0] rdb_addr = {rdb_warp_i, rdb_reg_i};

    // One independent 256×32-bit memory per lane.
    // Each has a simple whole-word WE = wr_en_i & wr_mask_i[lane].
    // Yosys infers a $mem for each lane (no sub-word masking).
    generate
        genvar lane;
        for (lane = 0; lane < N_LANES; lane++) begin : g_lane
            // Unpacked outer dimension — reliable $mem inference in yosys.
            logic [REG_WIDTH-1:0] rf [0:RF_DEPTH-1];

            // Synchronous write; r0 discarded (wr_reg_i != 0 guard)
            always_ff @(posedge clk) begin
                if (wr_en_i && wr_mask_i[lane] && (wr_reg_i != '0))
                    rf[wr_addr] <= wr_data_i[lane];
            end

            // Asynchronous read; r0 always returns 0
            assign rda_data_o[lane] = (rda_reg_i == '0) ? '0 : rf[rda_addr];
            assign rdb_data_o[lane] = (rdb_reg_i == '0) ? '0 : rf[rdb_addr];
        end
    endgenerate

endmodule

`default_nettype wire
