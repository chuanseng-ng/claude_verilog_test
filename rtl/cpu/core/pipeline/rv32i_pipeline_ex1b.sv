// rv32i_pipeline_ex1b.sv
// RV32I Pipeline — Execute Stage 1b (EX1b)
//
// Run-31: simplified field-pack stage — the 8-way case-mux has been removed.
// EX1c now pre-decodes all trap outputs into dec_* fields registered in
// ex1c_ex1b_reg_q.  EX1b reads those fields directly (1 gate each) instead
// of re-computing from trap_type, eliminating the NOR5/NAND5 bottleneck
// (~20 gate levels, 812 ps data arrival) that was the dominant timing violator
// on the ex1c_ex1b_reg_q → EX2 path.
//
// EX1b is still purely combinational — no registers.  It consumes
// ex1a_ex1b_t (now carrying the dec_* fields from EX1c) and produces
// ex1_ex2_reg_t for EX2 (the FF).
//
// Branch/JALR redirect penalty: unchanged at 4 cycles.  The redirect fires
// combinationally from EX1b using the registered dec_do_redirect /
// dec_redirect_target rather than a case-mux derived value.

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

