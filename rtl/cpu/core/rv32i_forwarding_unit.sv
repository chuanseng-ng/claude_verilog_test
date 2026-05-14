// rv32i_forwarding_unit.sv
// RV32I Pipeline Forwarding Unit (Phase 3 / EX2 retiming)
//
// Purely combinational. Implements the forwarding mux trees for ALU
// operands and store data using fwd_*_sel signals from the hazard unit.
//
// Forwarding encoding (fwd_*_sel):
//   2'b00 = register file output (no forwarding)
//   2'b01 = EX2 result (ex_mem_reg — registered EX1 result, 1 cycle behind EX1)
//   2'b10 = WB  result (mem_wb writeback data — 2 cycles behind EX1)

`default_nettype none
module rv32i_forwarding_unit (
    // Forwarding selects from hazard unit
    input  logic [1:0]  fwd_a_sel,
    input  logic [1:0]  fwd_b_sel,
    input  logic [1:0]  fwd_store_sel,

    // ID/EX pipeline register data (direct register file reads)
    input  logic [31:0] id_ex_rs1_data,
    input  logic [31:0] id_ex_rs2_data,

    // EX/MEM register data (for EX2→EX1 forwarding — registered EX1 result)
    input  logic [31:0] ex_mem_alu_result,
    input  logic [31:0] ex_mem_csr_rdata,
    input  logic [31:0] ex_mem_pc,
    input  logic        ex_mem_csr_access,
    input  logic        ex_mem_jump,

    // MEM/WB register data (for WB→EX1 forwarding)
    input  logic [31:0] mem_wb_alu_result,
    input  logic [31:0] mem_wb_mem_rdata,
    input  logic [31:0] mem_wb_csr_rdata,
    input  logic [31:0] mem_wb_pc,
    input  logic        mem_wb_mem_rd,
    input  logic        mem_wb_csr_access,
    input  logic        mem_wb_jump,

    // Forwarded outputs
    output logic [31:0] fwd_rs1,
    output logic [31:0] fwd_rs2,
    output logic [31:0] fwd_store
);

    // =========================================================================
    // EX/MEM write-back data selection (MEM stage forwarding value)
    // =========================================================================
    logic [31:0] ex_mem_rd_data;

    always_comb begin
        if (ex_mem_csr_access) begin
            ex_mem_rd_data = ex_mem_csr_rdata;
        end else if (ex_mem_jump) begin
            ex_mem_rd_data = ex_mem_pc + 32'd4;
        end else begin
            ex_mem_rd_data = ex_mem_alu_result;
        end
    end

    // =========================================================================
    // MEM/WB write-back data selection (WB stage forwarding value)
    // =========================================================================
    logic [31:0] mem_wb_rd_data;

    always_comb begin
        if (mem_wb_mem_rd) begin
            mem_wb_rd_data = mem_wb_mem_rdata;
        end else if (mem_wb_csr_access) begin
            mem_wb_rd_data = mem_wb_csr_rdata;
        end else if (mem_wb_jump) begin
            mem_wb_rd_data = mem_wb_pc + 32'd4;
        end else begin
            mem_wb_rd_data = mem_wb_alu_result;
        end
    end

    // =========================================================================
    // Forwarded rs1 (ALU operand A)
    // =========================================================================
    always_comb begin
        case (fwd_a_sel)
            2'b01:   fwd_rs1 = ex_mem_rd_data;    // EX2→EX1 (registered result)
            2'b10:   fwd_rs1 = mem_wb_rd_data;    // WB→EX1
            default: fwd_rs1 = id_ex_rs1_data;    // No forwarding
        endcase
    end

    // =========================================================================
    // Forwarded rs2 (ALU operand B)
    // =========================================================================
    always_comb begin
        case (fwd_b_sel)
            2'b01:   fwd_rs2 = ex_mem_rd_data;    // EX2→EX1
            2'b10:   fwd_rs2 = mem_wb_rd_data;    // WB→EX1
            default: fwd_rs2 = id_ex_rs2_data;
        endcase
    end

    // =========================================================================
    // Forwarded store data
    // =========================================================================
    always_comb begin
        case (fwd_store_sel)
            2'b01:   fwd_store = ex_mem_rd_data;  // EX2→EX1
            2'b10:   fwd_store = mem_wb_rd_data;  // WB→EX1
            default: fwd_store = id_ex_rs2_data;
        endcase
    end

endmodule

`default_nettype wire
