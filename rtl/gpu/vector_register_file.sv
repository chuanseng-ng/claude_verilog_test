// Vector register file: 8 warps × 32 registers × 8 lanes × 32 bits.
// r0 is hardwired to zero (reads return 0, writes are discarded).
// Two combinational read ports (A, B) and one synchronous write port.
// Phase 4: synthesised from flip-flops. Phase 5: SRAM macro substitution.
`default_nettype none

module vector_register_file
    import gpu_pkg::*;
(
    input  logic                            clk,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic                            rst_n,   // reserved: async clear for testbench reset flow
    /* verilator lint_on UNUSEDSIGNAL */

    // Read port A (rs1)
    input  logic [WARP_W-1:0]              rda_warp_i,
    input  logic [REG_W-1:0]               rda_reg_i,
    output logic [N_LANES-1:0][REG_WIDTH-1:0] rda_data_o,

    // Read port B (rs2)
    input  logic [WARP_W-1:0]              rdb_warp_i,
    input  logic [REG_W-1:0]               rdb_reg_i,
    output logic [N_LANES-1:0][REG_WIDTH-1:0] rdb_data_o,

    // Write port (single reg per warp per cycle, per-lane masked)
    input  logic                            wr_en_i,
    input  logic [N_LANES-1:0]             wr_mask_i,
    input  logic [WARP_W-1:0]              wr_warp_i,
    input  logic [REG_W-1:0]               wr_reg_i,
    input  logic [N_LANES-1:0][REG_WIDTH-1:0] wr_data_i
);

    // Address: {warp, reg} — 256 entries × 256-bit lane-packed word.
    // Unpacked outer dim so yosys infers a $mem rather than 65 536 discrete DFFs.
    localparam int RF_DEPTH = N_WARPS * N_REGS;     // 256
    localparam int RF_AW    = WARP_W + REG_W;       // 8
    localparam int RF_DW    = N_LANES * REG_WIDTH;  // 256

    logic [RF_DW-1:0] regfile [0:RF_DEPTH-1];

    wire [RF_AW-1:0] wr_addr  = {wr_warp_i,  wr_reg_i};
    wire [RF_AW-1:0] rda_addr = {rda_warp_i, rda_reg_i};
    wire [RF_AW-1:0] rdb_addr = {rdb_warp_i, rdb_reg_i};

    // Synchronous write — r0 writes are silently discarded via mask
    always_ff @(posedge clk) begin
        if (wr_en_i && (wr_reg_i != '0)) begin
            for (int lane = 0; lane < N_LANES; lane++) begin
                if (wr_mask_i[lane]) begin
                    regfile[wr_addr][lane*REG_WIDTH +: REG_WIDTH] <= wr_data_i[lane];
                end
            end
        end
    end

    // Combinational read ports — r0 always returns 0 (downstream mux; does not block $mem inference)
    always_comb rda_data_o = (rda_reg_i == '0) ? '0 : regfile[rda_addr];
    always_comb rdb_data_o = (rdb_reg_i == '0) ? '0 : regfile[rdb_addr];

endmodule

`default_nettype wire
