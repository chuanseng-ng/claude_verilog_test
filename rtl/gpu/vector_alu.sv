// 8-lane vector ALU. All operations are single-cycle combinational.
// Inactive lanes (active_mask bit = 0) produce 0 on result_o and branch_taken_o.
// VMUL produces the lower 32 bits of the 64-bit product (no pipeline stage in Phase 4).
`default_nettype none

module vector_alu
    import gpu_pkg::*;
(
    input  gpu_opcode_t                       opcode_i,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [2:0]                        funct3_i,  // reserved for future R-type sub-encoding
    input  logic [6:0]                        funct7_i,  // reserved for future R-type sub-encoding
    /* verilator lint_on UNUSEDSIGNAL */

    input  logic [N_LANES-1:0][REG_WIDTH-1:0] rs1_i,
    input  logic [N_LANES-1:0][REG_WIDTH-1:0] rs2_i,
    input  logic [11:0]                       imm_i,      // sign-extended by caller

    input  logic [N_LANES-1:0]               active_mask_i,

    output logic [N_LANES-1:0][REG_WIDTH-1:0] result_o,
    output logic [N_LANES-1:0]               branch_taken_o
);

    // Sign-extended immediate (12 → 32 bits)
    logic [REG_WIDTH-1:0] imm_sext;
    assign imm_sext = {{20{imm_i[11]}}, imm_i};

    // Per-lane computation
    for (genvar lane = 0; lane < N_LANES; lane++) begin : g_lane
        logic [REG_WIDTH-1:0] a, b, res;
        logic                 taken;

        assign a = rs1_i[lane];
        assign b = rs2_i[lane];

        always_comb begin
            res   = '0;
            taken = 1'b0;

            if (active_mask_i[lane]) begin
                unique case (opcode_i)
                    // R-type arithmetic
                    VADD:  res = a + b;
                    VSUB:  res = a - b;
                    VMUL:  res = REG_WIDTH'(a * b);   // lower 32 bits
                    VAND:  res = a & b;
                    VOR:   res = a | b;
                    VXOR:  res = a ^ b;
                    VSLL:  res = a << b[4:0];
                    VSRL:  res = a >> b[4:0];
                    VSRA:  res = REG_WIDTH'($signed(a) >>> b[4:0]);

                    // I-type arithmetic (immediate operand)
                    VADDI: res = a + imm_sext;
                    VANDI: res = a & imm_sext;
                    VORI:  res = a | imm_sext;
                    VXORI: res = a ^ imm_sext;

                    // Branch conditions — result unused; taken drives branch logic
                    VBEQ:  taken = (a == b);
                    VBNE:  taken = (a != b);
                    VBLT:  taken = ($signed(a) <  $signed(b));
                    VBGE:  taken = ($signed(a) >= $signed(b));

                    default: begin
                        res   = '0;
                        taken = 1'b0;
                    end
                endcase
            end
        end

        assign result_o[lane]       = res;
        assign branch_taken_o[lane] = taken;
    end : g_lane

endmodule

`default_nettype wire
