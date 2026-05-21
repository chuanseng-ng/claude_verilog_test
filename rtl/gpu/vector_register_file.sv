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

    // Storage: [warp][reg][lane]
    logic [N_WARPS-1:0][N_REGS-1:0][N_LANES-1:0][REG_WIDTH-1:0] regfile;

    // Synchronous write — r0 writes are silently discarded via mask
    always_ff @(posedge clk) begin
        if (wr_en_i && (wr_reg_i != '0)) begin
            for (int lane = 0; lane < N_LANES; lane++) begin
                if (wr_mask_i[lane]) begin
                    regfile[wr_warp_i][wr_reg_i][lane] <= wr_data_i[lane];
                end
            end
        end
    end

    // Combinational read port A — r0 always returns 0
    always_comb begin
        if (rda_reg_i == '0) begin
            rda_data_o = '0;
        end else begin
            rda_data_o = regfile[rda_warp_i][rda_reg_i];
        end
    end

    // Combinational read port B — r0 always returns 0
    always_comb begin
        if (rdb_reg_i == '0) begin
            rdb_data_o = '0;
        end else begin
            rdb_data_o = regfile[rdb_warp_i][rdb_reg_i];
        end
    end

endmodule

`default_nettype wire
