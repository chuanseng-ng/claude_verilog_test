// rv32i_forwarding_unit.sv
// RV32I Pipeline Forwarding Unit (Phase 3 / EX2 retiming)
//
// Purely combinational. Implements the forwarding mux trees for ALU
// operands and store data using fwd_*_sel and fwd_*_ex1c signals from
// the hazard unit.
//
// Forwarding encoding (fwd_*_sel):
//   2'b00 = register file output (no forwarding) — or EX1c tier when fwd_*_ex1c=1
//   2'b01 = EX2 result (ex_mem_reg — 3 cycles behind EX1a after Run-20 split)
//   2'b10 = WB  result (mem_wb writeback data)
//   2'b11 = EX1c-stage result (ex1a_ex1b_reg — 1 cycle behind EX1a, highest priority)
//           (producer just completed EX1a and is currently passing through EX1c)
//
// fwd_*_ex1c = 1: EX1b-stage result (ex1c_ex1b_reg — 2 cycles behind EX1a)
//   (producer completed EX1c and is currently in EX1b)
//   Priority: between 2'b11 and 2'b01.

`default_nettype none
module rv32i_forwarding_unit (
    // Forwarding selects from hazard unit
    input  logic [1:0]  fwd_a_sel,
    input  logic [1:0]  fwd_b_sel,
    input  logic [1:0]  fwd_store_sel,

    // EX1c forwarding tier (producer in EX1b — ex1c_ex1b_reg)
    input  logic        fwd_a_ex1c,
    input  logic        fwd_b_ex1c,
    input  logic        fwd_store_ex1c,

    // ID/EX pipeline register data (direct register file reads)
    input  logic [31:0] id_ex_rs1_data,
    input  logic [31:0] id_ex_rs2_data,

    // EX1b register data (for EX1c-stage→EX1a forwarding — ex1a_ex1b_reg,
    // producer just completed EX1a and is passing through EX1c combinationally)
    input  logic [31:0] ex1b_alu_result,
    input  logic [31:0] ex1b_csr_rdata,
    input  logic [31:0] ex1b_pc,
    input  logic        ex1b_csr_access,
    input  logic        ex1b_jump,

    // EX1c register data (for EX1b-stage→EX1a forwarding — ex1c_ex1b_reg,
    // producer completed EX1c and is currently in EX1b)
    input  logic [31:0] ex1c_alu_result,
    input  logic [31:0] ex1c_csr_rdata,
    input  logic [31:0] ex1c_pc,
    input  logic        ex1c_csr_access,
    input  logic        ex1c_jump,

    // EX/MEM register data (for EX2→EX1a forwarding)
    input  logic [31:0] ex_mem_alu_result,
    input  logic [31:0] ex_mem_csr_rdata,
    input  logic [31:0] ex_mem_pc,
    input  logic        ex_mem_csr_access,
    input  logic        ex_mem_jump,

    // MEM/WB register data (for WB→EX1a forwarding)
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
    // EX1c-stage write-back data (ex1a_ex1b_reg — producer in EX1c, 1 cycle behind)
    // =========================================================================
    logic [31:0] ex1b_rd_data;

    always_comb begin
        if (ex1b_csr_access) begin
            ex1b_rd_data = ex1b_csr_rdata;
        end else if (ex1b_jump) begin
            ex1b_rd_data = ex1b_pc + 32'd4;
        end else begin
            ex1b_rd_data = ex1b_alu_result;
        end
    end

    // =========================================================================
    // EX1b-stage write-back data (ex1c_ex1b_reg — producer in EX1b, 2 cycles behind)
    // =========================================================================
    logic [31:0] ex1c_rd_data;

    always_comb begin
        if (ex1c_csr_access) begin
            ex1c_rd_data = ex1c_csr_rdata;
        end else if (ex1c_jump) begin
            ex1c_rd_data = ex1c_pc + 32'd4;
        end else begin
            ex1c_rd_data = ex1c_alu_result;
        end
    end

    // =========================================================================
    // EX/MEM write-back data selection (EX2→EX1a forwarding value)
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
    // Priority: EX1c-stage (2'b11) > EX1b-stage (fwd_a_ex1c) > EX2 (2'b01) > WB > regfile
    // =========================================================================
    always_comb begin
        if (fwd_a_sel == 2'b11) begin
            fwd_rs1 = ex1b_rd_data;       // EX1c-stage→EX1a (highest priority)
        end else if (fwd_a_ex1c) begin
            fwd_rs1 = ex1c_rd_data;       // EX1b-stage→EX1a
        end else begin
            case (fwd_a_sel)
                2'b01:   fwd_rs1 = ex_mem_rd_data;    // EX2→EX1a
                2'b10:   fwd_rs1 = mem_wb_rd_data;    // WB→EX1a
                default: fwd_rs1 = id_ex_rs1_data;    // No forwarding
            endcase
        end
    end

    // =========================================================================
    // Forwarded rs2 (ALU operand B)
    // =========================================================================
    always_comb begin
        if (fwd_b_sel == 2'b11) begin
            fwd_rs2 = ex1b_rd_data;       // EX1c-stage→EX1a
        end else if (fwd_b_ex1c) begin
            fwd_rs2 = ex1c_rd_data;       // EX1b-stage→EX1a
        end else begin
            case (fwd_b_sel)
                2'b01:   fwd_rs2 = ex_mem_rd_data;    // EX2→EX1a
                2'b10:   fwd_rs2 = mem_wb_rd_data;    // WB→EX1a
                default: fwd_rs2 = id_ex_rs2_data;
            endcase
        end
    end

    // =========================================================================
    // Forwarded store data
    // =========================================================================
    always_comb begin
        if (fwd_store_sel == 2'b11) begin
            fwd_store = ex1b_rd_data;     // EX1c-stage→EX1a
        end else if (fwd_store_ex1c) begin
            fwd_store = ex1c_rd_data;     // EX1b-stage→EX1a
        end else begin
            case (fwd_store_sel)
                2'b01:   fwd_store = ex_mem_rd_data;  // EX2→EX1a
                2'b10:   fwd_store = mem_wb_rd_data;  // WB→EX1a
                default: fwd_store = id_ex_rs2_data;
            endcase
        end
    end

endmodule

`default_nettype wire
