// rv32i_pipeline_ex1c - Execute stage 1c: trap priority encode, trap pre-decode and store byte alignment.
//
// Function: Purely combinational. ex1a_i is the registered ex1a_ex1b_t (ex1a_ex1b_reg_q in rv32i_core). All inputs already come from a flop.
//   The branch misprediction penalty is 4 cycles.
//   ex1c_o has the same struct type. The caller registers it in ex1c_ex1b_reg_q, and EX1b reads it there.
//   1. Seven parallel trap conditions give a one-hot select sel[6:0]. Each condition includes ex1a_i.valid.
//      Priority, highest first: IRQ, ILLEGAL, EBREAK, FENCEI, MRET, JALR, BRANCH. sel is 0 when no trap applies.
//   2. trap_type is encoded from sel. It is TRAP_NONE when sel is 0.
//   3. A one-hot AND-OR mux on sel drives the dec_* fields. They do not depend on trap_type.
//      When sel is not 0, dec_do_redirect is 1. dec_trap_valid is 1 for IRQ, ILLEGAL and EBREAK.
//      dec_redirect_target is mtvec for IRQ, ILLEGAL and EBREAK. It is pc + 4 for FENCEI and mret_pc for MRET.
//      It is alu_result with bit 0 cleared for JALR, and pc + immediate for BRANCH.
//      dec_trap_cause is irq_cause (IRQ), 2 (ILLEGAL), 3 (EBREAK) and 0 otherwise.
//   4. pre_wstrb and pre_wdata_aligned hold the byte-aligned store strobes and data (mem_size and alu_result[1:0]).
//      pre_wstrb is 4'b0000 for a mem_size other than byte, halfword and word.
//   5. All other fields pass through unchanged.
// Parameters: none.
// Clocks and resets: none. The module has no clock and no reset.
// Caller rules:
//   - none beyond the port semantics.
// Doc: ds:mod:rv32i-pipeline-ex1c, tm:mod:rv32i-pipeline-ex1c, cr:mod:rv32i-pipeline-ex1c

import rv32i_pipeline_pkg::*;
module rv32i_pipeline_ex1c (
    // ── Registered EX1a output (ex1a_ex1b_reg_q from rv32i_core.sv) ──────────
    input  ex1a_ex1b_t  ex1a_i,

    // ── EX1c combinational output (to ex1c_ex1b_reg_q in rv32i_core.sv) ──────
    output ex1a_ex1b_t  ex1c_o
);

    // =========================================================================
    // Stage 1 — Parallel trap conditions (1-2 gate depth from registered inputs)
    //
    // Each condition is computed independently with no inter-dependency, giving
    // the synthesis tool maximum freedom to share fanout and balance loads.
    // Priority order (highest → lowest): IRQ > ILLEGAL > EBREAK > FENCEI >
    //                                    MRET > JALR > BRANCH > NONE
    // =========================================================================
    logic c_irq, c_ill, c_ebk, c_fci, c_mrt, c_jlr, c_bch;
    assign c_irq = ex1a_i.valid & ex1a_i.irq_valid_r;
    assign c_ill = ex1a_i.valid & (ex1a_i.illegal | ex1a_i.csr_illegal);
    assign c_ebk = ex1a_i.valid & ex1a_i.ebreak;
    assign c_fci = ex1a_i.valid & ex1a_i.fence_i;
    assign c_mrt = ex1a_i.valid & ex1a_i.mret;
    assign c_jlr = ex1a_i.valid & ex1a_i.jump & ex1a_i.jalr;
    assign c_bch = ex1a_i.valid & ex1a_i.branch & ex1a_i.branch_taken;

    // =========================================================================
    // Stage 2 — Balanced partial-OR tree (2-3 gate depth from conditions)
    //
    // Pairwise and quad OR reductions give the priority masking terms for sel[]
    // without a sequential carry chain.  2-wide then 4-wide groupings produce a
    // 3-level OR tree for the deepest term (any_012345).
    // =========================================================================
    logic any_01, any_23, any_45, any_0123, any_012345;
    assign any_01     = c_irq | c_ill;               // level 1
    assign any_23     = c_ebk | c_fci;               // level 1
    assign any_45     = c_mrt | c_jlr;               // level 1
    assign any_0123   = any_01   | any_23;            // level 2
    assign any_012345 = any_0123 | any_45;            // level 3

    // =========================================================================
    // Stage 3 — One-hot priority select mask (3-4 gate depth from conditions)
    //
    // sel[k] = cond[k] & ~(any cond with higher priority set).
    // At most one bit of sel is 1; all zero when no trap applies.
    // sel[0] is IRQ (highest priority) and sel[6] is BRANCH (lowest), in the Stage 1 order.
    // =========================================================================
    logic [6:0] sel;
    assign sel[0] = c_irq;
    assign sel[1] = c_ill & ~c_irq;
    assign sel[2] = c_ebk & ~any_01;
    assign sel[3] = c_fci & ~c_ebk  & ~any_01;   // ~(any_01 | c_ebk)
    assign sel[4] = c_mrt & ~any_0123;
    assign sel[5] = c_jlr & ~c_mrt  & ~any_0123; // ~(any_0123 | c_mrt)
    assign sel[6] = c_bch & ~any_012345;

    // =========================================================================
    // Named-signal copies of the struct members that are bit/part-selected below.
    // Selects are taken from these wires, never directly on ex1a_i.<member>
    // (Synlig mis-elaborates that idiom).
    // =========================================================================
    logic [31:0] ex1a_alu_result_w;
    logic [31:0] ex1a_fwd_store_w;
    assign ex1a_alu_result_w = ex1a_i.alu_result;
    assign ex1a_fwd_store_w  = ex1a_i.fwd_store;

    // =========================================================================
    // Output logic
    // =========================================================================
    always_comb begin
        // Passthrough default — overwrite trap-related and pre_w* fields below.
        ex1c_o = ex1a_i;

        // =====================================================================
        // Trap type encode from one-hot sel (2 gate levels above sel).
        // TRAP_* enum values 0-7 map to binary 000-111 corresponding to
        // sel[0]-sel[6] index+1, so trap_type bits factor as 4-wide OR gates.
        // ABC maps this as a 7:3 parallel encoder regardless of if/casez form.
        // =====================================================================
        unique casez (sel)
            // Pattern is 7'b[sel6:sel0] (LSB = sel[0] = rightmost bit)
            7'b??????1: ex1c_o.trap_type = TRAP_IRQ;
            7'b?????10: ex1c_o.trap_type = TRAP_ILLEGAL;
            7'b????100: ex1c_o.trap_type = TRAP_EBREAK;
            7'b???1000: ex1c_o.trap_type = TRAP_FENCEI;
            7'b??10000: ex1c_o.trap_type = TRAP_MRET;
            7'b?100000: ex1c_o.trap_type = TRAP_JALR;
            7'b1000000: ex1c_o.trap_type = TRAP_BRANCH;
            default:    ex1c_o.trap_type = TRAP_NONE;
        endcase

        // =====================================================================
        // Store byte-align (unchanged from Run-20; NOT on the critical path).
        // Reads only registered alu_result[1:0] and mem_size.
        // =====================================================================
        ex1c_o.pre_wstrb         = 4'b1111;
        ex1c_o.pre_wdata_aligned = ex1a_i.fwd_store;

        case (ex1a_i.mem_size)
            3'b000: begin  // Byte store
                case (ex1a_alu_result_w[1:0])
                    2'b00: begin
                        ex1c_o.pre_wstrb         = 4'b0001;
                        ex1c_o.pre_wdata_aligned = {24'h0, ex1a_fwd_store_w[7:0]};
                    end
                    2'b01: begin
                        ex1c_o.pre_wstrb         = 4'b0010;
                        ex1c_o.pre_wdata_aligned = {16'h0, ex1a_fwd_store_w[7:0], 8'h0};
                    end
                    2'b10: begin
                        ex1c_o.pre_wstrb         = 4'b0100;
                        ex1c_o.pre_wdata_aligned = {8'h0, ex1a_fwd_store_w[7:0], 16'h0};
                    end
                    2'b11: begin
                        ex1c_o.pre_wstrb         = 4'b1000;
                        ex1c_o.pre_wdata_aligned = {ex1a_fwd_store_w[7:0], 24'h0};
                    end
                    default: ;  // unreachable (2-bit sel fully enumerated); outputs keep the defaults assigned above
                endcase
            end
            3'b001: begin  // Halfword store
                case (ex1a_alu_result_w[1])
                    1'b0: begin
                        ex1c_o.pre_wstrb         = 4'b0011;
                        ex1c_o.pre_wdata_aligned = {16'h0, ex1a_fwd_store_w[15:0]};
                    end
                    1'b1: begin
                        ex1c_o.pre_wstrb         = 4'b1100;
                        ex1c_o.pre_wdata_aligned = {ex1a_fwd_store_w[15:0], 16'h0};
                    end
                    default: ;  // unreachable (1-bit sel fully enumerated); outputs keep the defaults assigned above
                endcase
            end
            3'b010: ;  // Word store — defaults already set above
            default: begin
                ex1c_o.pre_wstrb         = 4'b0000;
                ex1c_o.pre_wdata_aligned = 32'h0;
            end
        endcase

        // =====================================================================
        // Pre-decoded trap outputs — AND-OR one-hot mux keyed on sel[].
        // All data inputs are registered. This path does not depend on trap_type.
        // =====================================================================
        ex1c_o.dec_trap_valid      = 1'b0;
        ex1c_o.dec_do_redirect     = 1'b0;
        ex1c_o.dec_redirect_target = 32'h0;
        ex1c_o.dec_trap_cause      = 32'h0;
        ex1c_o.dec_is_irq          = 1'b0;
        ex1c_o.dec_mret            = 1'b0;
        ex1c_o.dec_dbg_halt        = 1'b0;
        ex1c_o.dec_fence_i         = 1'b0;

        if (|sel) begin
            // 1-bit outputs: direct from one-hot sel (1-2 levels above sel)
            ex1c_o.dec_do_redirect = 1'b1;
            ex1c_o.dec_trap_valid  = sel[0] | sel[1] | sel[2]; // IRQ/ILLEGAL/EBREAK
            ex1c_o.dec_is_irq      = sel[0];
            ex1c_o.dec_dbg_halt    = sel[2];
            ex1c_o.dec_fence_i     = sel[3];
            ex1c_o.dec_mret        = sel[4];

            // dec_redirect_target: 5-source AND-OR mux (2 gate levels above sel).
            // IRQ/ILLEGAL/EBREAK all redirect to mtvec — combine their selects
            // with a 3-input OR (1 extra level) to reduce AND-OR mux width to 5.
            ex1c_o.dec_redirect_target =
                ((sel[0] | sel[1] | sel[2]) ? ex1a_i.mtvec                     : 32'h0) |
                (sel[3]                     ? (ex1a_i.pc + 32'd4)               : 32'h0) |
                (sel[4]                     ? ex1a_i.mret_pc                    : 32'h0) |
                (sel[5]                     ? {ex1a_alu_result_w[31:1], 1'b0}   : 32'h0) |
                (sel[6]                     ? (ex1a_i.pc + ex1a_i.immediate)    : 32'h0);

            // dec_trap_cause: only IRQ/ILLEGAL/EBREAK set a non-zero cause
            ex1c_o.dec_trap_cause =
                (sel[0] ? ex1a_i.irq_cause : 32'h0) |
                (sel[1] ? 32'h0000_0002    : 32'h0) |
                (sel[2] ? 32'h0000_0003    : 32'h0);
        end
    end

endmodule
