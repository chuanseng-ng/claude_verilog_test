// rv32i_pipeline_ex.sv
// RV32I Pipeline — Execute Stage 1a (EX1a)
//
// Run-17 mid-EX retiming: the former monolithic EX combinational cone is split
// into two halves separated by the ex1a_ex1b_t wire (combinational, no FF).
// EX1b (rv32i_pipeline_ex1b.sv) handles the second half (store byte-align +
// trap priority cascade) and drives ex1_ex2_reg_t into EX2 (the FF stage).
//
// EX1a responsibilities:
//   - ALU computation (all ops including SLT/SLTU comparators)
//   - Branch comparator result
//   - JALR target: {alu_result[31:1], 1'b0}
//   - CSR write data
//   - Packs all fields into ex1a_ex1b_t, which rv32i_core.sv registers and
//     feeds to rv32i_pipeline_ex1b (instantiated in core, not here).
//
// NOTE: ex_pc_redirect / trap / mret / fence_i / dbg_halt come from EX1b
// (rv32i_pipeline_ex1b, instantiated in rv32i_core.sv).  Branch misprediction
// penalty is 3 cycles (2→3 accepted for Run 17 timing gain).

`default_nettype none

import rv32i_pipeline_pkg::*;
module rv32i_pipeline_ex(
    input  logic        clk,
    input  logic        rst_n,

    // ── Hazard unit controls ──────────────────────────────────────────────────
    input  logic        flush_ex_mem,   // Squash EX output (MEM-stage misalign trap wins)

    // ── ID/EX pipeline register input ────────────────────────────────────────
    input  id_ex_reg_t  id_ex_reg_i,

    // ── Forwarded operands (from forwarding unit) ─────────────────────────────
    input  logic [31:0] fwd_rs1,        // Forwarded rs1 (ALU src A before A-mux)
    input  logic [31:0] fwd_rs2,        // Forwarded rs2 (ALU src B before B-mux)
    input  logic [31:0] fwd_store,      // Forwarded store data

    // ── CSR file interface (combinational reads happen here) ──────────────────
    input  logic [31:0] csr_rdata_i,    // CSR read data (pre-write, from csr_file)

    // ── Interrupt controller ──────────────────────────────────────────────────
    input  logic        irq_valid_i,    // Enabled interrupt is pending
    input  logic [31:0] irq_cause_i,    // mcause for interrupt

    // ── CSR trap/MRET redirect values ────────────────────────────────────────
    input  logic [31:0] mtvec_i,        // Trap handler base address
    input  logic [31:0] mret_pc_i,      // mepc value for MRET

    // ── CSR write-enable to CSR file ─────────────────────────────────────────
    output logic        csr_wr_en_o,    // CSR file write enable
    output logic [31:0] csr_wdata_o,    // CSR write data (forwarded rs1 or imm)
    output logic [11:0] csr_addr_o,     // CSR address
    output logic [2:0]  csr_op_o,       // CSR operation
    output logic [4:0]  rs1_addr_o,     // rs1 address (for write-suppress)

    // ── EX1a packed output (registered by rv32i_core.sv → fed to EX1b) ──────
    output ex1a_ex1b_t  ex1a_ex1b_o
);

    // =========================================================================
    // ALU operand selection
    // =========================================================================
    logic [31:0] alu_a, alu_b;

    always_comb begin
        // src_a mux: 00=rs1, 01=PC, 10=zero
        case (id_ex_reg_i.alu_src_a)
            2'b01:   alu_a = id_ex_reg_i.pc;
            2'b10:   alu_a = 32'h0;
            default: alu_a = fwd_rs1;
        endcase

        // src_b mux: 0=rs2, 1=imm
        alu_b = id_ex_reg_i.alu_src_b ? id_ex_reg_i.immediate : fwd_rs2;
    end

    // =========================================================================
    // ALU instance
    // =========================================================================
    logic [31:0] alu_result;

    rv32i_alu u_alu (
        .operand_a (alu_a),
        .operand_b (alu_b),
        .alu_op    (id_ex_reg_i.alu_op),
        .result    (alu_result)
    );

    // =========================================================================
    // Branch comparator instance
    // =========================================================================
    logic branch_taken;

    rv32i_branch_comp u_branch_comp (
        .rs1_data    (fwd_rs1),
        .rs2_data    (fwd_rs2),
        .branch_op   (id_ex_reg_i.branch_op),
        .branch_taken(branch_taken)
    );

    // =========================================================================
    // CSR write data
    // For immediate variants (funct3[2]=1), CSR write data is the zero-extended
    // 5-bit immediate already in id_ex_reg.immediate.
    // For register variants, write data is the forwarded rs1.
    // =========================================================================
    logic [31:0] csr_wd;
    assign csr_wd = id_ex_reg_i.csr_op[2] ? id_ex_reg_i.immediate : fwd_rs1;

    // CSR outputs to csr_file
    assign csr_wr_en_o = id_ex_reg_i.csr_access && id_ex_reg_i.valid && !id_ex_reg_i.csr_illegal;
    assign csr_wdata_o = csr_wd;
    assign csr_addr_o  = id_ex_reg_i.csr_addr;
    assign csr_op_o    = id_ex_reg_i.csr_op;
    assign rs1_addr_o  = id_ex_reg_i.rs1_addr;

    // =========================================================================
    // Register irq_valid one cycle to remove the interrupt controller
    // combinational fan-in from the EX setup critical path.
    // =========================================================================
    logic irq_valid_r;
    always_ff @(posedge clk)
        if (!rst_n) irq_valid_r <= 1'b0;
        else        irq_valid_r <= irq_valid_i;

    // =========================================================================
    // EX1a combinational output — pack ex1a_ex1b_t wire for EX1b
    // =========================================================================
    ex1a_ex1b_t ex1a_to_ex1b;

    always_comb begin
        ex1a_to_ex1b = ex1a_ex1b_nop();

        ex1a_to_ex1b.alu_result   = alu_result;
        ex1a_to_ex1b.branch_taken = branch_taken;
        ex1a_to_ex1b.fwd_store    = fwd_store;
        ex1a_to_ex1b.csr_wd       = csr_wd;

        ex1a_to_ex1b.pc           = id_ex_reg_i.pc;
        ex1a_to_ex1b.instruction  = id_ex_reg_i.instruction;
        ex1a_to_ex1b.rd_addr      = id_ex_reg_i.rd_addr;
        ex1a_to_ex1b.reg_wr_en    = id_ex_reg_i.reg_wr_en;
        ex1a_to_ex1b.mem_rd       = id_ex_reg_i.mem_rd;
        ex1a_to_ex1b.mem_wr       = id_ex_reg_i.mem_wr;
        ex1a_to_ex1b.mem_size     = id_ex_reg_i.mem_size;
        ex1a_to_ex1b.mem_unsigned = id_ex_reg_i.mem_unsigned;
        ex1a_to_ex1b.csr_access   = id_ex_reg_i.csr_access;
        ex1a_to_ex1b.csr_addr     = id_ex_reg_i.csr_addr;
        ex1a_to_ex1b.csr_rdata    = csr_rdata_i;
        ex1a_to_ex1b.jump         = id_ex_reg_i.jump;
        ex1a_to_ex1b.jalr         = id_ex_reg_i.jalr;
        ex1a_to_ex1b.branch       = id_ex_reg_i.branch;
        ex1a_to_ex1b.immediate    = id_ex_reg_i.immediate;
        ex1a_to_ex1b.ebreak       = id_ex_reg_i.ebreak;
        ex1a_to_ex1b.mret         = id_ex_reg_i.mret;
        ex1a_to_ex1b.fence_i      = id_ex_reg_i.fence_i;
        ex1a_to_ex1b.illegal      = id_ex_reg_i.illegal;
        ex1a_to_ex1b.csr_illegal  = id_ex_reg_i.csr_illegal;
        ex1a_to_ex1b.valid        = id_ex_reg_i.valid;
        ex1a_to_ex1b.irq_valid_r  = irq_valid_r;
        ex1a_to_ex1b.irq_cause    = irq_cause_i;
        ex1a_to_ex1b.mtvec        = mtvec_i;
        ex1a_to_ex1b.mret_pc      = mret_pc_i;
        ex1a_to_ex1b.flush_ex_mem = flush_ex_mem;
        ex1a_to_ex1b.rs1_addr     = id_ex_reg_i.rs1_addr;
        ex1a_to_ex1b.rs2_addr     = id_ex_reg_i.rs2_addr;

        // Priority-encode trap_type in EX1a before the ex1a_ex1b_reg_q FF.
        // EX1b replaces the 8-level if/else-if cascade with a flat case-mux
        // on this registered field — removes ~10-12 gate levels from EX1b cone.
        // Priority order matches the EX1b cascade (IRQ highest).
        if (id_ex_reg_i.valid && irq_valid_r)
            ex1a_to_ex1b.trap_type = TRAP_IRQ;
        else if (id_ex_reg_i.valid && (id_ex_reg_i.illegal || id_ex_reg_i.csr_illegal))
            ex1a_to_ex1b.trap_type = TRAP_ILLEGAL;
        else if (id_ex_reg_i.valid && id_ex_reg_i.ebreak)
            ex1a_to_ex1b.trap_type = TRAP_EBREAK;
        else if (id_ex_reg_i.valid && id_ex_reg_i.fence_i)
            ex1a_to_ex1b.trap_type = TRAP_FENCEI;
        else if (id_ex_reg_i.valid && id_ex_reg_i.mret)
            ex1a_to_ex1b.trap_type = TRAP_MRET;
        else if (id_ex_reg_i.valid && id_ex_reg_i.jump && id_ex_reg_i.jalr)
            ex1a_to_ex1b.trap_type = TRAP_JALR;
        else if (id_ex_reg_i.valid && id_ex_reg_i.branch && branch_taken)
            ex1a_to_ex1b.trap_type = TRAP_BRANCH;
        else
            ex1a_to_ex1b.trap_type = TRAP_NONE;

        // =====================================================================
        // Run-19 P1: Store byte-align pre-computed in EX1a before ex1a_ex1b_reg_q FF.
        // EX1b reads ex1a_i.pre_wdata_aligned / ex1a_i.pre_wstrb directly, removing
        // the ~8-10 gate byte-align mux tree from the EX1b combinational cone.
        // All inputs (alu_result[1:0], mem_size, fwd_store) are available in EX1a.
        // =====================================================================
        ex1a_to_ex1b.pre_wstrb         = 4'b1111;
        ex1a_to_ex1b.pre_wdata_aligned = fwd_store;

        case (id_ex_reg_i.mem_size)
            3'b000: begin  // Byte store
                case (alu_result[1:0])
                    2'b00: begin
                        ex1a_to_ex1b.pre_wstrb         = 4'b0001;
                        ex1a_to_ex1b.pre_wdata_aligned = {24'h0, fwd_store[7:0]};
                    end
                    2'b01: begin
                        ex1a_to_ex1b.pre_wstrb         = 4'b0010;
                        ex1a_to_ex1b.pre_wdata_aligned = {16'h0, fwd_store[7:0], 8'h0};
                    end
                    2'b10: begin
                        ex1a_to_ex1b.pre_wstrb         = 4'b0100;
                        ex1a_to_ex1b.pre_wdata_aligned = {8'h0, fwd_store[7:0], 16'h0};
                    end
                    2'b11: begin
                        ex1a_to_ex1b.pre_wstrb         = 4'b1000;
                        ex1a_to_ex1b.pre_wdata_aligned = {fwd_store[7:0], 24'h0};
                    end
                endcase
            end
            3'b001: begin  // Halfword store
                case (alu_result[1])
                    1'b0: begin
                        ex1a_to_ex1b.pre_wstrb         = 4'b0011;
                        ex1a_to_ex1b.pre_wdata_aligned = {16'h0, fwd_store[15:0]};
                    end
                    1'b1: begin
                        ex1a_to_ex1b.pre_wstrb         = 4'b1100;
                        ex1a_to_ex1b.pre_wdata_aligned = {fwd_store[15:0], 16'h0};
                    end
                endcase
            end
            3'b010: begin  // Word store — defaults already set above
            end
            default: begin
                ex1a_to_ex1b.pre_wstrb         = 4'b0000;
                ex1a_to_ex1b.pre_wdata_aligned = 32'h0;
            end
        endcase
    end

    // EX1a combinational output — registered in rv32i_core.sv, then fed to EX1b
    assign ex1a_ex1b_o = ex1a_to_ex1b;

endmodule

`default_nettype wire
