// rv32i_pipeline_ex.sv
// RV32I Pipeline — Execute (EX) Stage (Phase 2)
//
// Responsibilities:
//   - ALU operation with forwarded operands
//   - Branch comparison and resolution (Decision 1: branches in EX)
//   - JALR target computation (Decision 3)
//   - Interrupt check (Decision 8: at instruction boundaries)
//   - CSR read-data capture from CSR file (combinational)
//   - Generate trap signals (irq, illegal, ebreak, misaligned)
//   - Generate ex_pc_redirect and pc_target
//   - Load EX/MEM pipeline register


import rv32i_pipeline_pkg::*;
module rv32i_pipeline_ex(
    input  logic        clk,
    input  logic        rst_n,

    // ── Hazard unit controls ──────────────────────────────────────────────────
    input  logic        stall_ex_mem,   // Hold EX/MEM register
    // flush_id_ex handled by the ID stage

    // ── ID/EX pipeline register input ────────────────────────────────────────
    input  id_ex_reg_t  id_ex_reg_i,

    // ── Forwarded operands (from forwarding unit) ─────────────────────────────
    input  logic [31:0] fwd_rs1,        // Forwarded rs1 (ALU src A before A-mux)
    input  logic [31:0] fwd_rs2,        // Forwarded rs2 (ALU src B before B-mux)
    input  logic [31:0] fwd_store,      // Forwarded store data

    // ── CSR file interface (combinational reads happen here) ──────────────────
    input  logic [31:0] csr_rdata_i,    // CSR read data (pre-write, from csr_file)
    input  logic        csr_illegal_i,  // CSR address not implemented

    // ── Interrupt controller ──────────────────────────────────────────────────
    input  logic        irq_valid_i,    // Enabled interrupt is pending
    input  logic [31:0] irq_cause_i,    // mcause for interrupt

    // ── CSR trap/MRET redirect values ────────────────────────────────────────
    input  logic [31:0] mtvec_i,        // Trap handler base address
    input  logic [31:0] mret_pc_i,      // mepc value for MRET

    // ── PC redirect output (to IF stage and hazard unit) ─────────────────────
    output logic        ex_pc_redirect_o, // 1 = flush IF+ID and redirect PC
    output logic [31:0] ex_pc_target_o,   // Redirect target

    // ── CSR write-enable to CSR file ─────────────────────────────────────────
    output logic        csr_wr_en_o,    // CSR file write enable
    output logic [31:0] csr_wdata_o,    // CSR write data (forwarded rs1 or imm)
    output logic [11:0] csr_addr_o,     // CSR address
    output logic [2:0]  csr_op_o,       // CSR operation
    output logic [4:0]  rs1_addr_o,     // rs1 address (for write-suppress)

    // ── Trap entry to CSR file ────────────────────────────────────────────────
    output logic        trap_entry_o,   // Trap being taken
    output logic [31:0] trap_pc_o,      // PC to save in mepc
    output logic [31:0] trap_cause_o,   // Cause to write to mcause

    // ── MRET to CSR file ─────────────────────────────────────────────────────
    output logic        mret_o,         // MRET executing

    // ── Debug halt request (EBREAK) ───────────────────────────────────────────
    output logic        dbg_halt_req_o, // EBREAK → request pipeline halt

    // ── FENCE.I I-cache invalidation (Phase 3) ────────────────────────────────
    output logic        fence_i_o,      // Pulse: invalidate I-cache this cycle

    // ── EX/MEM pipeline register output ──────────────────────────────────────
    output ex_mem_reg_t ex_mem_reg_o
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
    // Misalignment detection
    // =========================================================================
    logic misaligned_load, misaligned_store;

    always_comb begin
        misaligned_load  = 1'b0;
        misaligned_store = 1'b0;

        if (id_ex_reg_i.mem_rd) begin
            case (id_ex_reg_i.mem_size)
                3'b001: misaligned_load  = alu_result[0];         // halfword
                3'b010: misaligned_load  = |alu_result[1:0];      // word
                default: misaligned_load = 1'b0;
            endcase
        end

        if (id_ex_reg_i.mem_wr) begin
            case (id_ex_reg_i.mem_size)
                3'b001: misaligned_store  = alu_result[0];
                3'b010: misaligned_store  = |alu_result[1:0];
                default: misaligned_store = 1'b0;
            endcase
        end
    end

    // =========================================================================
    // CSR write data
    // For immediate variants (funct3[2]=1), CSR write data is the zero-extended
    // 5-bit immediate already in id_ex_reg.immediate.
    // For register variants, write data is the forwarded rs1.
    // =========================================================================
    logic [31:0] csr_wd;
    assign csr_wd = id_ex_reg_i.csr_op[2] ? id_ex_reg_i.immediate : fwd_rs1;

    // CSR outputs to csr_file
    assign csr_wr_en_o = id_ex_reg_i.csr_access && id_ex_reg_i.valid && !csr_illegal_i;
    assign csr_wdata_o = csr_wd;
    assign csr_addr_o  = id_ex_reg_i.csr_addr;
    assign csr_op_o    = id_ex_reg_i.csr_op;
    assign rs1_addr_o  = id_ex_reg_i.rs1_addr;

    // =========================================================================
    // Trap priority and PC redirect logic
    // Priority (highest first): irq > illegal_insn/csr_illegal > ebreak >
    //                           misaligned_load > misaligned_store
    //
    // Interrupt check happens at instruction boundaries (start of EX stage).
    // When an interrupt is taken, the instruction currently in EX is SQUASHED
    // (it was not executed) and mepc = EX instruction's PC.
    // =========================================================================
    logic        trap_valid;
    logic [31:0] trap_cause;
    logic [31:0] trap_pc;
    logic        do_redirect;
    logic [31:0] redirect_target;
    logic        is_irq;

    always_comb begin
        trap_valid      = 1'b0;
        trap_cause      = 32'h0;
        trap_pc         = id_ex_reg_i.pc;
        do_redirect     = 1'b0;
        redirect_target = 32'h0;
        is_irq          = 1'b0;
        dbg_halt_req_o  = 1'b0;
        mret_o          = 1'b0;
        fence_i_o       = 1'b0;

        if (!id_ex_reg_i.valid) begin
            // Bubble: nothing to do

        end else if (irq_valid_i) begin
            // Interrupt (highest priority among traps)
            trap_valid      = 1'b1;
            trap_cause      = irq_cause_i;
            trap_pc         = id_ex_reg_i.pc;  // mepc = squashed instruction's PC
            do_redirect     = 1'b1;
            redirect_target = mtvec_i;
            is_irq          = 1'b1;

        end else if (id_ex_reg_i.illegal || (id_ex_reg_i.csr_access && csr_illegal_i)) begin
            // Illegal instruction
            trap_valid      = 1'b1;
            trap_cause      = 32'h0000_0002;   // mcause=2: illegal instruction
            do_redirect     = 1'b1;
            redirect_target = mtvec_i;

        end else if (id_ex_reg_i.ebreak) begin
            // EBREAK: set mcause=3, redirect to mtvec, AND request debug halt
            trap_valid      = 1'b1;
            trap_cause      = 32'h0000_0003;   // mcause=3: breakpoint
            do_redirect     = 1'b1;
            redirect_target = mtvec_i;
            dbg_halt_req_o  = 1'b1;

        end else if (misaligned_load) begin
            trap_valid      = 1'b1;
            trap_cause      = 32'h0000_0004;   // mcause=4: load address misaligned
            do_redirect     = 1'b1;
            redirect_target = mtvec_i;

        end else if (misaligned_store) begin
            trap_valid      = 1'b1;
            trap_cause      = 32'h0000_0006;   // mcause=6: store address misaligned
            do_redirect     = 1'b1;
            redirect_target = mtvec_i;

        end else if (id_ex_reg_i.fence_i) begin
            // FENCE.I: flush pipeline (redirect to PC+4) and invalidate I-cache
            // The redirect flushes speculatively fetched instructions.
            // fence_i_o causes immediate I-cache invalidation this cycle.
            // ic_valid_o=0 in IF this cycle (due to pc_redirect), so no stale
            // instruction is captured from the invalidating cache.
            do_redirect     = 1'b1;
            redirect_target = id_ex_reg_i.pc + 32'd4;
            fence_i_o       = 1'b1;

        end else if (id_ex_reg_i.mret) begin
            // MRET: restore PC from mepc, restore MIE
            do_redirect     = 1'b1;
            redirect_target = mret_pc_i;
            mret_o          = 1'b1;

        end else if (id_ex_reg_i.jump) begin
            // JAL (already handled in ID) or JALR
            if (id_ex_reg_i.jalr) begin
                // JALR: target = (rs1 + imm) & ~1
                do_redirect     = 1'b1;
                redirect_target = {alu_result[31:1], 1'b0};
            end
            // JAL redirect is done in ID; EX doesn't set ex_pc_redirect for JAL

        end else if (id_ex_reg_i.branch && branch_taken) begin
            // Taken branch
            do_redirect     = 1'b1;
            redirect_target = id_ex_reg_i.pc + id_ex_reg_i.immediate;
        end
    end

    // Trap entry signals to CSR file
    assign trap_entry_o = trap_valid && id_ex_reg_i.valid;
    assign trap_pc_o    = trap_pc;
    assign trap_cause_o = trap_cause;

    // PC redirect to IF stage and hazard unit
    assign ex_pc_redirect_o = do_redirect && id_ex_reg_i.valid;
    assign ex_pc_target_o   = redirect_target;

    // =========================================================================
    // EX/MEM Pipeline Register
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ex_mem_reg_o <= ex_mem_nop();
        end else if (!stall_ex_mem) begin
            if (!id_ex_reg_i.valid || trap_valid) begin
                // Trap or bubble: propagate as a trap-only or NOP
                ex_mem_reg_o            <= ex_mem_nop();
                if (id_ex_reg_i.valid && trap_valid) begin
                    ex_mem_reg_o.pc         <= id_ex_reg_i.pc;
                    ex_mem_reg_o.instruction<= id_ex_reg_i.instruction;
                    ex_mem_reg_o.trap_valid <= 1'b1;
                    ex_mem_reg_o.trap_cause <= trap_cause;
                    ex_mem_reg_o.pc_redirect<= do_redirect;
                    ex_mem_reg_o.pc_target  <= redirect_target;
                    ex_mem_reg_o.valid      <= 1'b1;
                end
            end else begin
                ex_mem_reg_o.pc          <= id_ex_reg_i.pc;
                ex_mem_reg_o.instruction <= id_ex_reg_i.instruction;
                ex_mem_reg_o.alu_result  <= alu_result;
                ex_mem_reg_o.rs2_data    <= fwd_store;
                ex_mem_reg_o.csr_rdata   <= csr_rdata_i;
                ex_mem_reg_o.rd_addr     <= id_ex_reg_i.rd_addr;
                ex_mem_reg_o.reg_wr_en   <= id_ex_reg_i.reg_wr_en;
                ex_mem_reg_o.mem_rd      <= id_ex_reg_i.mem_rd;
                ex_mem_reg_o.mem_wr      <= id_ex_reg_i.mem_wr;
                ex_mem_reg_o.mem_size    <= id_ex_reg_i.mem_size;
                ex_mem_reg_o.mem_unsigned<= id_ex_reg_i.mem_unsigned;
                ex_mem_reg_o.csr_access  <= id_ex_reg_i.csr_access;
                ex_mem_reg_o.csr_addr    <= id_ex_reg_i.csr_addr;
                ex_mem_reg_o.csr_wdata   <= csr_wd;
                ex_mem_reg_o.jump        <= id_ex_reg_i.jump;
                ex_mem_reg_o.jalr        <= id_ex_reg_i.jalr;
                ex_mem_reg_o.pc_redirect <= do_redirect;
                ex_mem_reg_o.pc_target   <= redirect_target;
                ex_mem_reg_o.trap_valid  <= 1'b0;
                ex_mem_reg_o.trap_cause  <= 32'h0;
                ex_mem_reg_o.valid       <= 1'b1;
            end
        end
        // else stall_ex_mem=1: hold current value
    end

endmodule
