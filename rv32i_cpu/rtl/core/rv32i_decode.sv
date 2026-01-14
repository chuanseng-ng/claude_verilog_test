// RV32I Decoder - Extracts instruction fields and generates control signals
module rv32i_decode
    import rv32i_pkg::*;
(
    input  logic [ILEN-1:0]           instr,

    // Decoded instruction fields
    output logic [REG_ADDR_WIDTH-1:0] rs1_addr,
    output logic [REG_ADDR_WIDTH-1:0] rs2_addr,
    output logic [REG_ADDR_WIDTH-1:0] rd_addr,
    output logic [6:0]                opcode,
    output logic [2:0]                funct3,
    output logic [6:0]                funct7,

    // Control signals
    output ctrl_signals_t             ctrl,

    // Instruction validity
    output logic                      illegal_instr
);

    // Extract instruction fields
    assign opcode   = instr[6:0];
    assign rd_addr  = instr[11:7];
    assign funct3   = instr[14:12];
    assign rs1_addr = instr[19:15];
    assign rs2_addr = instr[24:20];
    assign funct7   = instr[31:25];

    // Default control signals
    ctrl_signals_t ctrl_default;
    assign ctrl_default = '{
        reg_write:  1'b0,
        mem_read:   1'b0,
        mem_write:  1'b0,
        branch:     1'b0,
        jump:       1'b0,
        alu_op:     ALU_OP_ADD,
        alu_src_a:  ALU_SRC_REG,
        alu_src_b:  ALU_SRC_REG,
        wb_src:     WB_SRC_ALU,
        imm_type:   IMM_I,
        funct3:     3'b000
    };

    // Decode logic
    always_comb begin
        ctrl = ctrl_default;
        illegal_instr = 1'b0;

        case (opcode)
            // LUI - Load Upper Immediate
            OP_LUI: begin
                ctrl.reg_write = 1'b1;
                ctrl.alu_src_a = ALU_SRC_ZERO;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.alu_op    = ALU_OP_PASS_B;
                ctrl.wb_src    = WB_SRC_ALU;
                ctrl.imm_type  = IMM_U;
            end

            // AUIPC - Add Upper Immediate to PC
            OP_AUIPC: begin
                ctrl.reg_write = 1'b1;
                ctrl.alu_src_a = ALU_SRC_PC;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.alu_op    = ALU_OP_ADD;
                ctrl.wb_src    = WB_SRC_ALU;
                ctrl.imm_type  = IMM_U;
            end

            // JAL - Jump and Link
            OP_JAL: begin
                ctrl.reg_write = 1'b1;
                ctrl.jump      = 1'b1;
                ctrl.alu_src_a = ALU_SRC_PC;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.alu_op    = ALU_OP_ADD;
                ctrl.wb_src    = WB_SRC_PC4;
                ctrl.imm_type  = IMM_J;
            end

            // JALR - Jump and Link Register
            OP_JALR: begin
                ctrl.reg_write = 1'b1;
                ctrl.jump      = 1'b1;
                ctrl.alu_src_a = ALU_SRC_REG;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.alu_op    = ALU_OP_ADD;
                ctrl.wb_src    = WB_SRC_PC4;
                ctrl.imm_type  = IMM_I;
                ctrl.funct3    = funct3;
                if (funct3 != 3'b000) begin
                    illegal_instr = 1'b1;
                end
            end

            // Branch instructions
            OP_BRANCH: begin
                ctrl.branch    = 1'b1;
                ctrl.alu_src_a = ALU_SRC_REG;
                ctrl.alu_src_b = ALU_SRC_REG;
                ctrl.imm_type  = IMM_B;
                ctrl.funct3    = funct3;

                case (funct3)
                    BR_BEQ, BR_BNE:   ctrl.alu_op = ALU_OP_SUB;
                    BR_BLT, BR_BGE:   ctrl.alu_op = ALU_OP_SLT;
                    BR_BLTU, BR_BGEU: ctrl.alu_op = ALU_OP_SLTU;
                    default: illegal_instr = 1'b1;
                endcase
            end

            // Load instructions
            OP_LOAD: begin
                ctrl.reg_write = 1'b1;
                ctrl.mem_read  = 1'b1;
                ctrl.alu_src_a = ALU_SRC_REG;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.alu_op    = ALU_OP_ADD;
                ctrl.wb_src    = WB_SRC_MEM;
                ctrl.imm_type  = IMM_I;
                ctrl.funct3    = funct3;

                case (funct3)
                    LD_LB, LD_LH, LD_LW, LD_LBU, LD_LHU: ; // Valid
                    default: illegal_instr = 1'b1;
                endcase
            end

            // Store instructions
            OP_STORE: begin
                ctrl.mem_write = 1'b1;
                ctrl.alu_src_a = ALU_SRC_REG;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.alu_op    = ALU_OP_ADD;
                ctrl.imm_type  = IMM_S;
                ctrl.funct3    = funct3;

                case (funct3)
                    ST_SB, ST_SH, ST_SW: ; // Valid
                    default: illegal_instr = 1'b1;
                endcase
            end

            // Immediate ALU operations
            OP_IMM: begin
                ctrl.reg_write = 1'b1;
                ctrl.alu_src_a = ALU_SRC_REG;
                ctrl.alu_src_b = ALU_SRC_IMM;
                ctrl.wb_src    = WB_SRC_ALU;
                ctrl.imm_type  = IMM_I;
                ctrl.funct3    = funct3;

                case (funct3)
                    ALU_ADD_SUB: ctrl.alu_op = ALU_OP_ADD;  // ADDI (no SUBI)
                    ALU_SLL: begin
                        ctrl.alu_op = ALU_OP_SLL;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    ALU_SLT:  ctrl.alu_op = ALU_OP_SLT;
                    ALU_SLTU: ctrl.alu_op = ALU_OP_SLTU;
                    ALU_XOR:  ctrl.alu_op = ALU_OP_XOR;
                    ALU_SRL_SRA: begin
                        if (funct7 == 7'b0000000)
                            ctrl.alu_op = ALU_OP_SRL;
                        else if (funct7 == 7'b0100000)
                            ctrl.alu_op = ALU_OP_SRA;
                        else
                            illegal_instr = 1'b1;
                    end
                    ALU_OR:  ctrl.alu_op = ALU_OP_OR;
                    ALU_AND: ctrl.alu_op = ALU_OP_AND;
                    default: illegal_instr = 1'b1;
                endcase
            end

            // Register ALU operations
            OP_REG: begin
                ctrl.reg_write = 1'b1;
                ctrl.alu_src_a = ALU_SRC_REG;
                ctrl.alu_src_b = ALU_SRC_REG;
                ctrl.wb_src    = WB_SRC_ALU;
                ctrl.funct3    = funct3;

                case (funct3)
                    ALU_ADD_SUB: begin
                        if (funct7 == 7'b0000000)
                            ctrl.alu_op = ALU_OP_ADD;
                        else if (funct7 == 7'b0100000)
                            ctrl.alu_op = ALU_OP_SUB;
                        else
                            illegal_instr = 1'b1;
                    end
                    ALU_SLL: begin
                        ctrl.alu_op = ALU_OP_SLL;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    ALU_SLT: begin
                        ctrl.alu_op = ALU_OP_SLT;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    ALU_SLTU: begin
                        ctrl.alu_op = ALU_OP_SLTU;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    ALU_XOR: begin
                        ctrl.alu_op = ALU_OP_XOR;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    ALU_SRL_SRA: begin
                        if (funct7 == 7'b0000000)
                            ctrl.alu_op = ALU_OP_SRL;
                        else if (funct7 == 7'b0100000)
                            ctrl.alu_op = ALU_OP_SRA;
                        else
                            illegal_instr = 1'b1;
                    end
                    ALU_OR: begin
                        ctrl.alu_op = ALU_OP_OR;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    ALU_AND: begin
                        ctrl.alu_op = ALU_OP_AND;
                        if (funct7 != 7'b0000000) illegal_instr = 1'b1;
                    end
                    default: illegal_instr = 1'b1;
                endcase
            end

            // FENCE (NOP in this implementation)
            OP_FENCE: begin
                // Treat as NOP - no operation needed for single-core
            end

            // System instructions (ECALL, EBREAK)
            OP_SYSTEM: begin
                // For now, treat EBREAK as halt trigger (handled elsewhere)
                // ECALL not implemented
                if (instr[31:7] == 25'b0000000000010000000000000) begin
                    // EBREAK - handled by debug module
                end else if (instr[31:7] == 25'b0) begin
                    // ECALL - not implemented, treat as NOP
                end else begin
                    illegal_instr = 1'b1;
                end
            end

            default: begin
                illegal_instr = 1'b1;
            end
        endcase
    end

endmodule
