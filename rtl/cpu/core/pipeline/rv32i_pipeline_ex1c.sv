// rv32i_pipeline_ex1c.sv
// RV32I Pipeline — Execute Stage 1c (EX1c)
//
// Run-20: new purely-combinational stage inserted between ex1a_ex1b_reg_q
// and ex1c_ex1b_reg_q to break the -782 ps timing critical path.
//
// The critical path in Run 19 was:
//   id_ex_reg FF → 22-gate cone (ALU + trap-encode + byte-align) → ex1a_ex1b_reg_q
//
// EX1c reads the REGISTERED ex1a_ex1b_t (all inputs already through a FF) and:
//   1. Re-encodes trap_type using the 8-way priority encoder on registered fields.
//      Note: branch_taken is registered in ex1a_i.branch_taken (not recomputed).
//   2. Computes store byte-alignment using registered alu_result[1:0] and mem_size.
//   3. Passes all other ex1a_ex1b_t fields through unchanged.
//
// Output type is ex1a_ex1b_t (same struct — no new type needed).
// EX1b (rv32i_pipeline_ex1b.sv) reads ex1c_ex1b_reg_q and its logic is unchanged.
//
// Branch misprediction penalty: 4 cycles (accepted for Run 20, was 3 in Run 19).

`default_nettype none

import rv32i_pipeline_pkg::*;
module rv32i_pipeline_ex1c (
    // ── Registered EX1a output (ex1a_ex1b_reg_q from rv32i_core.sv) ──────────
    input  ex1a_ex1b_t  ex1a_i,

    // ── EX1c combinational output (to ex1c_ex1b_reg_q in rv32i_core.sv) ──────
    output ex1a_ex1b_t  ex1c_o
);

    always_comb begin
        // Passthrough all fields — then overwrite trap_type and pre_w* below
        ex1c_o = ex1a_i;

        // =====================================================================
        // Trap type priority encoder (using REGISTERED fields from ex1a_ex1b_reg_q)
        // Priority matches EX1b flat case-mux (IRQ highest):
        //   IRQ > illegal/csr_illegal > ebreak > fence_i > mret > jalr >
        //   taken-branch > none
        // branch_taken is already registered in ex1a_i.branch_taken (computed
        // by branch comparator in EX1a, passed through ex1a_ex1b_reg_q).
        // =====================================================================
        if (ex1a_i.valid && ex1a_i.irq_valid_r)
            ex1c_o.trap_type = TRAP_IRQ;
        else if (ex1a_i.valid && (ex1a_i.illegal || ex1a_i.csr_illegal))
            ex1c_o.trap_type = TRAP_ILLEGAL;
        else if (ex1a_i.valid && ex1a_i.ebreak)
            ex1c_o.trap_type = TRAP_EBREAK;
        else if (ex1a_i.valid && ex1a_i.fence_i)
            ex1c_o.trap_type = TRAP_FENCEI;
        else if (ex1a_i.valid && ex1a_i.mret)
            ex1c_o.trap_type = TRAP_MRET;
        else if (ex1a_i.valid && ex1a_i.jump && ex1a_i.jalr)
            ex1c_o.trap_type = TRAP_JALR;
        else if (ex1a_i.valid && ex1a_i.branch && ex1a_i.branch_taken)
            ex1c_o.trap_type = TRAP_BRANCH;
        else
            ex1c_o.trap_type = TRAP_NONE;

        // =====================================================================
        // Store byte-align (using REGISTERED alu_result[1:0] and mem_size)
        // Same logic as former EX1a Run-19 P1 block, now reading registered inputs.
        // =====================================================================
        ex1c_o.pre_wstrb         = 4'b1111;
        ex1c_o.pre_wdata_aligned = ex1a_i.fwd_store;

        case (ex1a_i.mem_size)
            3'b000: begin  // Byte store
                case (ex1a_i.alu_result[1:0])
                    2'b00: begin
                        ex1c_o.pre_wstrb         = 4'b0001;
                        ex1c_o.pre_wdata_aligned = {24'h0, ex1a_i.fwd_store[7:0]};
                    end
                    2'b01: begin
                        ex1c_o.pre_wstrb         = 4'b0010;
                        ex1c_o.pre_wdata_aligned = {16'h0, ex1a_i.fwd_store[7:0], 8'h0};
                    end
                    2'b10: begin
                        ex1c_o.pre_wstrb         = 4'b0100;
                        ex1c_o.pre_wdata_aligned = {8'h0, ex1a_i.fwd_store[7:0], 16'h0};
                    end
                    2'b11: begin
                        ex1c_o.pre_wstrb         = 4'b1000;
                        ex1c_o.pre_wdata_aligned = {ex1a_i.fwd_store[7:0], 24'h0};
                    end
                endcase
            end
            3'b001: begin  // Halfword store
                case (ex1a_i.alu_result[1])
                    1'b0: begin
                        ex1c_o.pre_wstrb         = 4'b0011;
                        ex1c_o.pre_wdata_aligned = {16'h0, ex1a_i.fwd_store[15:0]};
                    end
                    1'b1: begin
                        ex1c_o.pre_wstrb         = 4'b1100;
                        ex1c_o.pre_wdata_aligned = {ex1a_i.fwd_store[15:0], 16'h0};
                    end
                endcase
            end
            3'b010: begin  // Word store — defaults already set above
            end
            default: begin
                ex1c_o.pre_wstrb         = 4'b0000;
                ex1c_o.pre_wdata_aligned = 32'h0;
            end
        endcase
    end

endmodule

`default_nettype wire
