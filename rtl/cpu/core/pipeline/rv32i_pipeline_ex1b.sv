// rv32i_pipeline_ex1b.sv
// RV32I Pipeline — Execute Stage 1b (EX1b)
//
// Run-17 mid-EX retiming: second half of the split EX combinational cone.
// This module is purely combinational — no registers.  It consumes the
// ex1a_ex1b_t wire from EX1a and produces ex1_ex2_reg_t for EX2 (the FF).
//
// EX1b responsibilities:
//   - Store byte-align (mem_wdata_aligned, mem_wstrb) using alu_result[1:0]
//   - 8-level trap priority cascade producing pc_redirect / pc_target /
//     trap_valid / trap_cause and the side-effect outputs (trap_entry,
//     mret, dbg_halt_req, fence_i)
//   - Packs all fields into ex1_ex2_reg_t (same type as before the split)
//
// ex_pc_redirect_o / ex_pc_target_o: re-derived here identically to EX1a so
// rv32i_pipeline_ex.sv can simply pass them through from this module's output.
// (Branch/JALR latency is unchanged because the combinational path ex1a→ex1b
// adds no FF boundary — only the EX2 FF separates EX from MEM.)

`default_nettype none

import rv32i_pipeline_pkg::*;
module rv32i_pipeline_ex1b (
    // ── EX1a combinational wire input ─────────────────────────────────────────
    input  ex1a_ex1b_t   ex1a_i,

    // ── EX1b combinational output → EX2 (owns the FF) ────────────────────────
    output ex1_ex2_reg_t ex1_ex2_reg_o,

    // ── PC redirect (combinational, drives IF and hazard unit) ───────────────
    output logic        ex_pc_redirect_o,
    output logic [31:0] ex_pc_target_o,

    // ── Trap entry to CSR file ────────────────────────────────────────────────
    output logic        trap_entry_o,
    output logic [31:0] trap_pc_o,
    output logic [31:0] trap_cause_o,

    // ── MRET to CSR file ─────────────────────────────────────────────────────
    output logic        mret_o,

    // ── Debug halt request (EBREAK) ───────────────────────────────────────────
    output logic        dbg_halt_req_o,

    // ── FENCE.I I-cache invalidation ─────────────────────────────────────────
    output logic        fence_i_o
);

    // =========================================================================
    // Store byte-alignment (uses alu_result[1:0] from EX1a)
    // =========================================================================
    logic [31:0] pre_wdata_aligned;
    logic [3:0]  pre_wstrb;

    always_comb begin
        pre_wstrb         = 4'b1111;
        pre_wdata_aligned = ex1a_i.fwd_store;

        case (ex1a_i.mem_size)
            3'b000: begin  // Byte store
                case (ex1a_i.alu_result[1:0])
                    2'b00: begin pre_wstrb = 4'b0001; pre_wdata_aligned = {24'h0, ex1a_i.fwd_store[7:0]}; end
                    2'b01: begin pre_wstrb = 4'b0010; pre_wdata_aligned = {16'h0, ex1a_i.fwd_store[7:0], 8'h0}; end
                    2'b10: begin pre_wstrb = 4'b0100; pre_wdata_aligned = {8'h0,  ex1a_i.fwd_store[7:0], 16'h0}; end
                    2'b11: begin pre_wstrb = 4'b1000; pre_wdata_aligned = {ex1a_i.fwd_store[7:0], 24'h0}; end
                endcase
            end
            3'b001: begin  // Halfword store
                case (ex1a_i.alu_result[1])
                    1'b0: begin pre_wstrb = 4'b0011; pre_wdata_aligned = {16'h0, ex1a_i.fwd_store[15:0]}; end
                    1'b1: begin pre_wstrb = 4'b1100; pre_wdata_aligned = {ex1a_i.fwd_store[15:0], 16'h0}; end
                endcase
            end
            3'b010: begin  // Word store
                pre_wstrb         = 4'b1111;
                pre_wdata_aligned = ex1a_i.fwd_store;
            end
            default: begin
                pre_wstrb         = 4'b0000;
                pre_wdata_aligned = 32'h0;
            end
        endcase
    end

    // =========================================================================
    // Trap priority and PC redirect logic
    // Priority (highest first): irq > illegal_insn/csr_illegal > ebreak >
    //                           fence_i > mret > jalr > taken-branch
    //
    // Run-18 P1: flat case-mux on pre-encoded trap_type (registered in EX1a).
    // Replaces the 8-level if/else-if priority cascade, removing ~10-12 gate
    // levels from the EX1b combinational cone.
    // =========================================================================
    logic        trap_valid;
    logic [31:0] trap_cause;
    logic [31:0] trap_pc;
    logic        do_redirect;
    logic [31:0] redirect_target;
    logic        is_irq;

    always_comb begin
        // Defaults
        trap_valid      = 1'b0;
        trap_cause      = 32'h0;
        trap_pc         = ex1a_i.pc;
        do_redirect     = 1'b0;
        redirect_target = 32'h0;
        is_irq          = 1'b0;
        dbg_halt_req_o  = 1'b0;
        mret_o          = 1'b0;
        fence_i_o       = 1'b0;

        if (!ex1a_i.valid || ex1a_i.flush_ex_mem) begin
            // Bubble or ghost being killed by registered redirect: suppress all outputs

        end else begin
            // Flat case-mux on pre-encoded trap_type — single gate level select
            unique case (ex1a_i.trap_type)
                TRAP_IRQ: begin
                    // Interrupt (highest priority)
                    trap_valid      = 1'b1;
                    trap_cause      = ex1a_i.irq_cause;
                    trap_pc         = ex1a_i.pc;   // mepc = squashed instruction's PC
                    do_redirect     = 1'b1;
                    redirect_target = ex1a_i.mtvec;
                    is_irq          = 1'b1;
                end
                TRAP_ILLEGAL: begin
                    // Illegal instruction (mcause=2)
                    trap_valid      = 1'b1;
                    trap_cause      = 32'h0000_0002;
                    do_redirect     = 1'b1;
                    redirect_target = ex1a_i.mtvec;
                end
                TRAP_EBREAK: begin
                    // EBREAK: mcause=3, redirect to mtvec, request debug halt
                    trap_valid      = 1'b1;
                    trap_cause      = 32'h0000_0003;
                    do_redirect     = 1'b1;
                    redirect_target = ex1a_i.mtvec;
                    dbg_halt_req_o  = 1'b1;
                end
                TRAP_FENCEI: begin
                    // FENCE.I: redirect to PC+4, invalidate I-cache
                    do_redirect     = 1'b1;
                    redirect_target = ex1a_i.pc + 32'd4;
                    fence_i_o       = 1'b1;
                end
                TRAP_MRET: begin
                    // MRET: restore PC from mepc, restore MIE
                    do_redirect     = 1'b1;
                    redirect_target = ex1a_i.mret_pc;
                    mret_o          = 1'b1;
                end
                TRAP_JALR: begin
                    // JALR: target = (rs1 + imm) & ~1
                    do_redirect     = 1'b1;
                    redirect_target = {ex1a_i.alu_result[31:1], 1'b0};
                end
                TRAP_BRANCH: begin
                    // Taken branch
                    do_redirect     = 1'b1;
                    redirect_target = ex1a_i.pc + ex1a_i.immediate;
                end
                default: ; // TRAP_NONE — no redirect, all defaults hold
            endcase
        end
    end

    // Trap entry signals to CSR file
    assign trap_entry_o = trap_valid && ex1a_i.valid;
    assign trap_pc_o    = trap_pc;
    assign trap_cause_o = trap_cause;

    // PC redirect to IF stage and hazard unit
    assign ex_pc_redirect_o = do_redirect && ex1a_i.valid && !ex1a_i.flush_ex_mem;
    assign ex_pc_target_o   = redirect_target;

    // =========================================================================
    // EX1b combinational output — drives ex1_ex2_reg_o (EX2 owns the FF)
    // =========================================================================
    always_comb begin
        ex1_ex2_reg_o = ex1_ex2_nop();

        if (!ex1a_i.valid || ex1a_i.flush_ex_mem) begin
            // Bubble or ghost killed by registered redirect — output NOP
            if (ex1a_i.valid && trap_valid && !ex1a_i.flush_ex_mem) begin
                ex1_ex2_reg_o.pc          = ex1a_i.pc;
                ex1_ex2_reg_o.instruction = ex1a_i.instruction;
                ex1_ex2_reg_o.trap_valid  = 1'b1;
                ex1_ex2_reg_o.trap_cause  = trap_cause;
                ex1_ex2_reg_o.pc_redirect = do_redirect;
                ex1_ex2_reg_o.pc_target   = redirect_target;
                ex1_ex2_reg_o.valid       = 1'b1;
            end
        end else if (trap_valid) begin
            ex1_ex2_reg_o.pc          = ex1a_i.pc;
            ex1_ex2_reg_o.instruction = ex1a_i.instruction;
            ex1_ex2_reg_o.trap_valid  = 1'b1;
            ex1_ex2_reg_o.trap_cause  = trap_cause;
            ex1_ex2_reg_o.pc_redirect = do_redirect;
            ex1_ex2_reg_o.pc_target   = redirect_target;
            ex1_ex2_reg_o.valid       = 1'b1;
        end else begin
            ex1_ex2_reg_o.pc                = ex1a_i.pc;
            ex1_ex2_reg_o.instruction       = ex1a_i.instruction;
            ex1_ex2_reg_o.alu_result        = ex1a_i.alu_result;
            ex1_ex2_reg_o.mem_wdata_aligned = pre_wdata_aligned;
            ex1_ex2_reg_o.mem_wstrb         = pre_wstrb;
            ex1_ex2_reg_o.csr_rdata         = ex1a_i.csr_rdata;
            ex1_ex2_reg_o.rd_addr           = ex1a_i.rd_addr;
            ex1_ex2_reg_o.reg_wr_en         = ex1a_i.reg_wr_en;
            ex1_ex2_reg_o.mem_rd            = ex1a_i.mem_rd;
            ex1_ex2_reg_o.mem_wr            = ex1a_i.mem_wr;
            ex1_ex2_reg_o.mem_size          = ex1a_i.mem_size;
            ex1_ex2_reg_o.mem_unsigned      = ex1a_i.mem_unsigned;
            ex1_ex2_reg_o.csr_access        = ex1a_i.csr_access;
            ex1_ex2_reg_o.csr_addr          = ex1a_i.csr_addr;
            ex1_ex2_reg_o.csr_wdata         = ex1a_i.csr_wd;
            ex1_ex2_reg_o.jump              = ex1a_i.jump;
            ex1_ex2_reg_o.jalr              = ex1a_i.jalr;
            ex1_ex2_reg_o.pc_redirect       = do_redirect;
            ex1_ex2_reg_o.pc_target         = redirect_target;
            ex1_ex2_reg_o.trap_valid        = 1'b0;
            ex1_ex2_reg_o.trap_cause        = 32'h0;
            ex1_ex2_reg_o.valid             = 1'b1;
        end
    end

endmodule

`default_nettype wire
