// RV32I Immediate Generator - Extracts and sign-extends immediates from instructions
module rv32i_imm_gen
    import rv32i_pkg::*;
(
    input  logic [ILEN-1:0]  instr,
    input  imm_type_e        imm_type,
    output logic [XLEN-1:0]  imm
);

    // Instruction fields for immediate extraction
    logic [11:0] imm_i;
    logic [11:0] imm_s;
    logic [12:0] imm_b;
    logic [31:0] imm_u;
    logic [20:0] imm_j;

    // I-type immediate: instr[31:20]
    assign imm_i = instr[31:20];

    // S-type immediate: {instr[31:25], instr[11:7]}
    assign imm_s = {instr[31:25], instr[11:7]};

    // B-type immediate: {instr[31], instr[7], instr[30:25], instr[11:8], 1'b0}
    assign imm_b = {instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};

    // U-type immediate: {instr[31:12], 12'b0}
    assign imm_u = {instr[31:12], 12'b0};

    // J-type immediate: {instr[31], instr[19:12], instr[20], instr[30:21], 1'b0}
    assign imm_j = {instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};

    // Immediate selection and sign extension
    always_comb begin
        case (imm_type)
            IMM_I: begin
                // Sign-extend 12-bit I-type immediate
                imm = {{20{imm_i[11]}}, imm_i};
            end

            IMM_S: begin
                // Sign-extend 12-bit S-type immediate
                imm = {{20{imm_s[11]}}, imm_s};
            end

            IMM_B: begin
                // Sign-extend 13-bit B-type immediate (already includes LSB=0)
                imm = {{19{imm_b[12]}}, imm_b};
            end

            IMM_U: begin
                // U-type immediate (already 32 bits with lower 12 bits = 0)
                imm = imm_u;
            end

            IMM_J: begin
                // Sign-extend 21-bit J-type immediate (already includes LSB=0)
                imm = {{11{imm_j[20]}}, imm_j};
            end

            default: begin
                imm = '0;
            end
        endcase
    end

endmodule
