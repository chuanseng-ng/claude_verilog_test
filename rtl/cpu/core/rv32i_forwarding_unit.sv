// rv32i_forwarding_unit.sv
// RV32I Pipeline Forwarding Unit (Phase 2)
//
// Purely combinational. Implements the forwarding mux trees for ALU
// operands and store data using the fwd_*_sel signals from the hazard unit.
//
// Forwarding encoding (fwd_*_sel):
//   2'b00 = register file output (no forwarding)
//   2'b01 = EX/MEM alu_result    (EX→EX path)
//   2'b10 = MEM/WB writeback data (MEM→EX path; selects mem_rdata / csr_rdata / alu_result)

module rv32i_forwarding_unit (
    // Forwarding selects from hazard unit
    input  logic [1:0]  fwd_a_sel,         // ALU A forwarding select
    input  logic [1:0]  fwd_b_sel,         // ALU B forwarding select
    input  logic [1:0]  fwd_store_sel,     // Store data forwarding select

    // ID/EX pipeline register data (direct register file reads)
    input  logic [31:0] id_ex_rs1_data,    // rs1 from register file
    input  logic [31:0] id_ex_rs2_data,    // rs2 from register file

    // EX/MEM register data (for EX→EX forwarding)
    input  logic [31:0] ex_mem_alu_result, // ALU result forwarded from EX/MEM

    // MEM/WB register data (for MEM→EX forwarding)
    input  logic [31:0] mem_wb_alu_result, // ALU result in MEM/WB
    input  logic [31:0] mem_wb_mem_rdata,  // Loaded data in MEM/WB
    input  logic [31:0] mem_wb_csr_rdata,  // CSR read data in MEM/WB
    input  logic [31:0] mem_wb_pc,         // Instruction PC in MEM/WB (for PC+4)
    input  logic        mem_wb_mem_rd,     // MEM/WB is a load → use mem_rdata
    input  logic        mem_wb_csr_access, // MEM/WB is a CSR → use csr_rdata
    input  logic        mem_wb_jump,       // MEM/WB is a jump → use PC+4

    // Forwarded outputs
    output logic [31:0] fwd_rs1,           // Forwarded rs1 value (for ALU operand A)
    output logic [31:0] fwd_rs2,           // Forwarded rs2 value (for ALU operand B)
    output logic [31:0] fwd_store          // Forwarded store data (rs2 as store write data)
);

    // =========================================================================
    // MEM/WB write-back data selection
    // Mirrors the WB stage write-data mux; used as the MEM→EX forwarding value.
    // =========================================================================
    logic [31:0] mem_wb_rd_data;

    always_comb begin
        if (mem_wb_mem_rd) begin
            mem_wb_rd_data = mem_wb_mem_rdata;        // Load result
        end else if (mem_wb_csr_access) begin
            mem_wb_rd_data = mem_wb_csr_rdata;        // CSR read result
        end else if (mem_wb_jump) begin
            mem_wb_rd_data = mem_wb_pc + 32'd4;       // JAL/JALR return address
        end else begin
            mem_wb_rd_data = mem_wb_alu_result;       // Default: ALU result
        end
    end

    // =========================================================================
    // Forwarded rs1 (ALU operand A mux input)
    // =========================================================================
    always_comb begin
        case (fwd_a_sel)
            2'b01:   fwd_rs1 = ex_mem_alu_result;   // EX→EX
            2'b10:   fwd_rs1 = mem_wb_rd_data;       // MEM→EX
            default: fwd_rs1 = id_ex_rs1_data;       // No forwarding (2'b00 or unused)
        endcase
    end

    // =========================================================================
    // Forwarded rs2 (ALU operand B mux input)
    // =========================================================================
    always_comb begin
        case (fwd_b_sel)
            2'b01:   fwd_rs2 = ex_mem_alu_result;
            2'b10:   fwd_rs2 = mem_wb_rd_data;
            default: fwd_rs2 = id_ex_rs2_data;
        endcase
    end

    // =========================================================================
    // Forwarded store data (rs2 as store write data)
    // =========================================================================
    always_comb begin
        case (fwd_store_sel)
            2'b01:   fwd_store = ex_mem_alu_result;
            2'b10:   fwd_store = mem_wb_rd_data;
            default: fwd_store = id_ex_rs2_data;
        endcase
    end

endmodule
