// rv32i_pipeline_ex1b - Execute stage 1b: combinational field pack, PC redirect and trap side effects.
//
// Function: Purely combinational. It has no registers.
//   It reads ex1a_i (ex1a_ex1b_t). The dec_* fields in ex1a_i are pre-decoded by EX1c and registered in ex1c_ex1b_reg_q.
//   It builds ex1_ex2_reg_o (ex1_ex2_reg_t) for EX2. EX2 owns the flop.
//   ex_pc_redirect_o = dec_do_redirect && valid && !flush_ex_mem. ex_pc_target_o = dec_redirect_target.
//   ex_pc_redirect_o drives IF and the hazard unit.
//   trap_entry_o = dec_trap_valid && valid. trap_pc_o = ex1a_i.pc. trap_cause_o = dec_trap_cause.
//   mret_o, dbg_halt_req_o (EBREAK) and fence_i_o are dec_mret, dec_dbg_halt and dec_fence_i, each gated with valid && !flush_ex_mem.
//   ex1_ex2_reg_o is a NOP bubble when valid is 0 or flush_ex_mem is 1.
//   Otherwise, with dec_trap_valid set, ex1_ex2_reg_o carries pc, instruction, trap_valid, trap_cause, pc_redirect, pc_target and valid.
//   Otherwise it carries pc, instruction, alu_result, mem_wdata_aligned, mem_wstrb, csr_rdata, rd_addr, reg_wr_en, mem_rd, mem_wr,
//   mem_size, mem_unsigned, csr_access, csr_addr, csr_wdata, jump, jalr, pc_redirect, pc_target and valid. trap_valid and trap_cause are 0.
//   The branch and JALR redirect penalty is 4 cycles.
// Parameters: none.
// Clocks and resets: none. The module has no clock and no reset.
// Caller rules:
//   - ex1a_i must carry the registered dec_* fields of EX1c. EX1b does not recompute them from trap_type.
// Doc: ds:mod:rv32i-pipeline-ex1b, tm:mod:rv32i-pipeline-ex1b

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
    // PC redirect (now directly from registered EX1c decoded output — 1 gate)
    // =========================================================================
    assign ex_pc_redirect_o = ex1a_i.dec_do_redirect && ex1a_i.valid && !ex1a_i.flush_ex_mem;
    assign ex_pc_target_o   = ex1a_i.dec_redirect_target;

    // =========================================================================
    // Trap entry signals — use pre-registered trap_valid and trap_cause
    // trap_pc_o is always the instruction's own PC (mepc = faulting/squashed PC)
    // =========================================================================
    assign trap_entry_o = ex1a_i.dec_trap_valid && ex1a_i.valid;
    assign trap_pc_o    = ex1a_i.pc;
    assign trap_cause_o = ex1a_i.dec_trap_cause;

    // =========================================================================
    // Side effects (1 gate each — direct from registered decode)
    // =========================================================================
    assign mret_o         = ex1a_i.dec_mret     && ex1a_i.valid && !ex1a_i.flush_ex_mem;
    assign dbg_halt_req_o = ex1a_i.dec_dbg_halt && ex1a_i.valid && !ex1a_i.flush_ex_mem;
    assign fence_i_o      = ex1a_i.dec_fence_i  && ex1a_i.valid && !ex1a_i.flush_ex_mem;

    // =========================================================================
    // EX1b combinational output — drives ex1_ex2_reg_o (EX2 owns the FF)
    // =========================================================================
    always_comb begin
        ex1_ex2_reg_o = ex1_ex2_nop();

        if (!ex1a_i.valid || ex1a_i.flush_ex_mem) begin
            // NOP bubble — but preserve trap info if this instruction was already
            // committed to a trap before being squashed
            if (ex1a_i.valid && ex1a_i.dec_trap_valid && !ex1a_i.flush_ex_mem) begin
                ex1_ex2_reg_o.pc          = ex1a_i.pc;
                ex1_ex2_reg_o.instruction = ex1a_i.instruction;
                ex1_ex2_reg_o.trap_valid  = 1'b1;
                ex1_ex2_reg_o.trap_cause  = ex1a_i.dec_trap_cause;
                ex1_ex2_reg_o.pc_redirect = ex1a_i.dec_do_redirect;
                ex1_ex2_reg_o.pc_target   = ex1a_i.dec_redirect_target;
                ex1_ex2_reg_o.valid       = 1'b1;
            end
        end else if (ex1a_i.dec_trap_valid) begin
            ex1_ex2_reg_o.pc          = ex1a_i.pc;
            ex1_ex2_reg_o.instruction = ex1a_i.instruction;
            ex1_ex2_reg_o.trap_valid  = 1'b1;
            ex1_ex2_reg_o.trap_cause  = ex1a_i.dec_trap_cause;
            ex1_ex2_reg_o.pc_redirect = ex1a_i.dec_do_redirect;
            ex1_ex2_reg_o.pc_target   = ex1a_i.dec_redirect_target;
            ex1_ex2_reg_o.valid       = 1'b1;
        end else begin
            ex1_ex2_reg_o.pc                = ex1a_i.pc;
            ex1_ex2_reg_o.instruction       = ex1a_i.instruction;
            ex1_ex2_reg_o.alu_result        = ex1a_i.alu_result;
            ex1_ex2_reg_o.mem_wdata_aligned = ex1a_i.pre_wdata_aligned;
            ex1_ex2_reg_o.mem_wstrb         = ex1a_i.pre_wstrb;
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
            ex1_ex2_reg_o.pc_redirect       = ex1a_i.dec_do_redirect;
            ex1_ex2_reg_o.pc_target         = ex1a_i.dec_redirect_target;
            ex1_ex2_reg_o.trap_valid        = 1'b0;
            ex1_ex2_reg_o.trap_cause        = 32'h0;
            ex1_ex2_reg_o.valid             = 1'b1;
        end
    end

endmodule
