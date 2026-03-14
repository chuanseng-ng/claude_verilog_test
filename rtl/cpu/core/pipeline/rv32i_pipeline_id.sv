// rv32i_pipeline_id.sv
// RV32I Pipeline — Instruction Decode (ID) Stage (Phase 2)
//
// Responsibilities:
//   - Instantiate rv32i_decode and rv32i_imm_gen
//   - Drive register file read ports
//   - Detect JAL in ID stage → generate jal_redirect + JAL target
//   - Load the ID/EX pipeline register

import rv32i_pipeline_pkg::*;

module rv32i_pipeline_id (
    input  logic        clk,
    input  logic        rst_n,

    // ── Hazard unit controls ──────────────────────────────────────────────────
    input  logic        stall_id_ex,   // Hold ID/EX register
    input  logic        flush_id_ex,   // Clear ID/EX (insert NOP bubble)

    // ── IF/ID pipeline register input ────────────────────────────────────────
    input  if_id_reg_t  if_id_reg_i,

    // ── Register file read ports ─────────────────────────────────────────────
    output logic [4:0]  rf_rs1_addr_o,
    input  logic [31:0] rf_rs1_data_i,
    output logic [4:0]  rf_rs2_addr_o,
    input  logic [31:0] rf_rs2_data_i,

    // ── JAL early-resolve output (to IF stage and hazard unit) ───────────────
    output logic        jal_redirect_o, // JAL detected → flush IF
    output logic [31:0] jal_target_o,   // JAL target: if_id_reg.pc + jal_offset

    // ── ID/EX pipeline register output ───────────────────────────────────────
    output id_ex_reg_t  id_ex_reg_o
);

    // =========================================================================
    // Decode outputs
    // =========================================================================
    logic [4:0]  rs1, rs2, rd;
    logic [3:0]  alu_op;
    logic [1:0]  alu_src_a;
    logic        alu_src_b;
    logic [2:0]  imm_fmt;
    logic        reg_wr_en;
    logic        mem_rd, mem_wr;
    logic [2:0]  mem_size;
    logic        mem_unsigned;
    logic        branch;
    logic [2:0]  branch_op;
    logic        jump, jalr;
    logic        pc_src_unused;
    logic        illegal;
    logic        ebreak;
    logic        csr_access;
    logic [11:0] csr_addr;
    logic [2:0]  csr_op;
    logic        mret;
    logic        fence_i;

    logic [31:0] immediate;

    // =========================================================================
    // Instantiate decoder
    // =========================================================================
    /* verilator lint_off PINCONNECTEMPTY */
    rv32i_decode u_decode (
        .instruction  (if_id_reg_i.instruction),
        .rs1          (rs1),
        .rs2          (rs2),
        .rd           (rd),
        .alu_op       (alu_op),
        .alu_src_a    (alu_src_a),
        .alu_src_b    (alu_src_b),
        .imm_fmt      (imm_fmt),
        .reg_wr_en    (reg_wr_en),
        .mem_rd       (mem_rd),
        .mem_wr       (mem_wr),
        .mem_size     (mem_size),
        .mem_unsigned (mem_unsigned),
        .branch       (branch),
        .branch_op    (branch_op),
        .jump         (jump),
        .jalr         (jalr),
        .pc_src       (),       // not used in pipeline
        .illegal      (illegal),
        .ebreak       (ebreak),
        .csr_access   (csr_access),
        .csr_addr     (csr_addr),
        .csr_op       (csr_op),
        .mret         (mret),
        .fence_i      (fence_i)
    );
    /* verilator lint_on PINCONNECTEMPTY */

    // =========================================================================
    // Instantiate immediate generator
    // =========================================================================
    rv32i_imm_gen u_imm_gen (
        .instruction (if_id_reg_i.instruction),
        .imm_fmt     (imm_fmt),
        .immediate   (immediate)
    );

    // =========================================================================
    // Register file address outputs
    // =========================================================================
    assign rf_rs1_addr_o = rs1;
    assign rf_rs2_addr_o = rs2;

    // =========================================================================
    // JAL early resolution (Decision 2: JAL in ID, 1-cycle penalty)
    // JAL: target = PC + J-immediate; does NOT depend on register values
    // Only fire when the IF/ID register holds a valid JAL instruction
    // and we are NOT being flushed this cycle.
    // =========================================================================
    assign jal_redirect_o = if_id_reg_i.valid && jump && !jalr && !flush_id_ex;
    assign jal_target_o   = if_id_reg_i.pc + immediate;

    // =========================================================================
    // ID/EX pipeline register
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            id_ex_reg_o <= id_ex_nop();
        end else if (flush_id_ex) begin
            id_ex_reg_o <= id_ex_nop();
        end else if (!stall_id_ex) begin
            if (!if_id_reg_i.valid) begin
                // Propagate bubble
                id_ex_reg_o <= id_ex_nop();
            end else begin
                id_ex_reg_o.pc          <= if_id_reg_i.pc;
                id_ex_reg_o.instruction <= if_id_reg_i.instruction;
                id_ex_reg_o.rs1_data    <= rf_rs1_data_i;
                id_ex_reg_o.rs2_data    <= rf_rs2_data_i;
                id_ex_reg_o.immediate   <= immediate;
                id_ex_reg_o.rs1_addr    <= rs1;
                id_ex_reg_o.rs2_addr    <= rs2;
                id_ex_reg_o.rd_addr     <= rd;
                id_ex_reg_o.alu_op      <= alu_op;
                id_ex_reg_o.alu_src_a   <= alu_src_a;
                id_ex_reg_o.alu_src_b   <= alu_src_b;
                id_ex_reg_o.reg_wr_en   <= reg_wr_en;
                id_ex_reg_o.mem_rd      <= mem_rd;
                id_ex_reg_o.mem_wr      <= mem_wr;
                id_ex_reg_o.mem_size    <= mem_size;
                id_ex_reg_o.mem_unsigned<= mem_unsigned;
                id_ex_reg_o.branch      <= branch;
                id_ex_reg_o.branch_op   <= branch_op;
                id_ex_reg_o.jump        <= jump;
                id_ex_reg_o.jalr        <= jalr;
                id_ex_reg_o.csr_access  <= csr_access;
                id_ex_reg_o.csr_addr    <= csr_addr;
                id_ex_reg_o.csr_op      <= csr_op;
                id_ex_reg_o.ebreak      <= ebreak;
                id_ex_reg_o.mret        <= mret;
                id_ex_reg_o.fence_i     <= fence_i;
                id_ex_reg_o.illegal     <= illegal;
                id_ex_reg_o.valid       <= 1'b1;
            end
        end
        // else stall_id_ex=1: hold current value
    end

endmodule
