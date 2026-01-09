//-----------------------------------------------------------------------------
// RV32I Instruction Generator
// Generates random but valid RV32I instruction sequences
//-----------------------------------------------------------------------------

class rv32i_instr_gen extends uvm_object;

    `uvm_object_utils(rv32i_instr_gen)

    //-------------------------------------------------------------------------
    // Configuration
    //-------------------------------------------------------------------------
    int unsigned max_instructions = 100;
    int unsigned data_section_start = 32'h0000_1000;  // Data section offset
    int unsigned stack_pointer_init = 32'h0000_0FFC;  // Initial SP

    // Instruction mix weights
    int unsigned weight_alu_reg   = 20;   // R-type ALU
    int unsigned weight_alu_imm   = 25;   // I-type ALU
    int unsigned weight_load      = 15;   // Load instructions
    int unsigned weight_store     = 15;   // Store instructions
    int unsigned weight_branch    = 15;   // Branch instructions
    int unsigned weight_jump      = 5;    // JAL/JALR
    int unsigned weight_upper     = 5;    // LUI/AUIPC

    // Generated program
    logic [31:0] program_data[$];
    int unsigned program_length;

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name = "rv32i_instr_gen");
        super.new(name);
    endfunction

    //-------------------------------------------------------------------------
    // Generate Random Program
    //-------------------------------------------------------------------------
    function void generate_program(int num_instructions = 0);
        logic [31:0] instr;
        int total_weight;

        if (num_instructions == 0)
            num_instructions = max_instructions;

        program_data.delete();

        // Initialize stack pointer (ADDI sp, x0, stack_init)
        program_data.push_back(encode_addi(5'd2, 5'd0, stack_pointer_init[11:0]));

        // Generate random instructions
        total_weight = weight_alu_reg + weight_alu_imm + weight_load +
                      weight_store + weight_branch + weight_jump + weight_upper;

        for (int i = 1; i < num_instructions - 1; i++) begin
            int rand_val = $urandom_range(0, total_weight - 1);
            int cumulative = 0;

            // Select instruction type based on weights
            cumulative += weight_alu_reg;
            if (rand_val < cumulative) begin
                instr = gen_alu_reg();
            end else begin
                cumulative += weight_alu_imm;
                if (rand_val < cumulative) begin
                    instr = gen_alu_imm();
                end else begin
                    cumulative += weight_load;
                    if (rand_val < cumulative) begin
                        instr = gen_load();
                    end else begin
                        cumulative += weight_store;
                        if (rand_val < cumulative) begin
                            instr = gen_store();
                        end else begin
                            cumulative += weight_branch;
                            if (rand_val < cumulative) begin
                                instr = gen_branch(i, num_instructions);
                            end else begin
                                cumulative += weight_jump;
                                if (rand_val < cumulative) begin
                                    instr = gen_jal(i, num_instructions);
                                end else begin
                                    instr = gen_upper();
                                end
                            end
                        end
                    end
                end
            end

            program_data.push_back(instr);
        end

        // End with EBREAK
        program_data.push_back(encode_ebreak());

        program_length = program_data.size();
        `uvm_info("INSTR_GEN", $sformatf("Generated %0d instructions", program_length), UVM_MEDIUM)
    endfunction

    //-------------------------------------------------------------------------
    // Instruction Generators
    //-------------------------------------------------------------------------

    // Generate R-type ALU instruction
    function logic [31:0] gen_alu_reg();
        logic [4:0] rd, rs1, rs2;
        logic [6:0] funct7;
        logic [2:0] funct3;
        int alu_op;

        rd  = $urandom_range(1, 31);  // Avoid x0
        rs1 = $urandom_range(0, 31);
        rs2 = $urandom_range(0, 31);

        alu_op = $urandom_range(0, 9);
        case (alu_op)
            0: begin funct7 = 7'b0000000; funct3 = 3'b000; end  // ADD
            1: begin funct7 = 7'b0100000; funct3 = 3'b000; end  // SUB
            2: begin funct7 = 7'b0000000; funct3 = 3'b001; end  // SLL
            3: begin funct7 = 7'b0000000; funct3 = 3'b010; end  // SLT
            4: begin funct7 = 7'b0000000; funct3 = 3'b011; end  // SLTU
            5: begin funct7 = 7'b0000000; funct3 = 3'b100; end  // XOR
            6: begin funct7 = 7'b0000000; funct3 = 3'b101; end  // SRL
            7: begin funct7 = 7'b0100000; funct3 = 3'b101; end  // SRA
            8: begin funct7 = 7'b0000000; funct3 = 3'b110; end  // OR
            9: begin funct7 = 7'b0000000; funct3 = 3'b111; end  // AND
        endcase

        return encode_r_type(funct7, rs2, rs1, funct3, rd, OPCODE_OP);
    endfunction

    // Generate I-type ALU instruction
    function logic [31:0] gen_alu_imm();
        logic [4:0] rd, rs1;
        logic [11:0] imm;
        logic [2:0] funct3;
        int alu_op;

        rd  = $urandom_range(1, 31);
        rs1 = $urandom_range(0, 31);

        alu_op = $urandom_range(0, 8);
        case (alu_op)
            0: begin funct3 = 3'b000; imm = $urandom_range(0, 2047) - 1024; end  // ADDI
            1: begin funct3 = 3'b010; imm = $urandom_range(0, 2047) - 1024; end  // SLTI
            2: begin funct3 = 3'b011; imm = $urandom_range(0, 2047); end         // SLTIU
            3: begin funct3 = 3'b100; imm = $urandom_range(0, 4095); end         // XORI
            4: begin funct3 = 3'b110; imm = $urandom_range(0, 4095); end         // ORI
            5: begin funct3 = 3'b111; imm = $urandom_range(0, 4095); end         // ANDI
            6: begin funct3 = 3'b001; imm = {7'b0000000, $urandom_range(0, 31)[4:0]}; end  // SLLI
            7: begin funct3 = 3'b101; imm = {7'b0000000, $urandom_range(0, 31)[4:0]}; end  // SRLI
            8: begin funct3 = 3'b101; imm = {7'b0100000, $urandom_range(0, 31)[4:0]}; end  // SRAI
        endcase

        return encode_i_type(imm, rs1, funct3, rd, OPCODE_OP_IMM);
    endfunction

    // Generate load instruction
    function logic [31:0] gen_load();
        logic [4:0] rd, rs1;
        logic [11:0] offset;
        logic [2:0] funct3;
        int load_type;

        rd  = $urandom_range(1, 31);
        rs1 = 5'd2;  // Use SP as base
        offset = ($urandom_range(0, 63) << 2);  // Word-aligned offset

        load_type = $urandom_range(0, 4);
        case (load_type)
            0: funct3 = 3'b000;  // LB
            1: funct3 = 3'b001;  // LH
            2: funct3 = 3'b010;  // LW
            3: funct3 = 3'b100;  // LBU
            4: funct3 = 3'b101;  // LHU
        endcase

        return encode_i_type(offset, rs1, funct3, rd, OPCODE_LOAD);
    endfunction

    // Generate store instruction
    function logic [31:0] gen_store();
        logic [4:0] rs1, rs2;
        logic [11:0] offset;
        logic [2:0] funct3;
        int store_type;

        rs1 = 5'd2;  // Use SP as base
        rs2 = $urandom_range(0, 31);
        offset = ($urandom_range(0, 63) << 2);

        store_type = $urandom_range(0, 2);
        case (store_type)
            0: funct3 = 3'b000;  // SB
            1: funct3 = 3'b001;  // SH
            2: funct3 = 3'b010;  // SW
        endcase

        return encode_s_type(offset, rs2, rs1, funct3, OPCODE_STORE);
    endfunction

    // Generate branch instruction
    function logic [31:0] gen_branch(int current_idx, int total_instr);
        logic [4:0] rs1, rs2;
        logic [12:0] offset;
        logic [2:0] funct3;
        int target_idx;
        int offset_words;

        rs1 = $urandom_range(0, 31);
        rs2 = $urandom_range(0, 31);

        // Calculate safe branch target (forward only to avoid infinite loops)
        target_idx = $urandom_range(current_idx + 1, total_instr - 1);
        offset_words = target_idx - current_idx;
        offset = (offset_words << 2);  // Convert to bytes

        funct3 = $urandom_range(0, 5);
        case (funct3)
            0: funct3 = 3'b000;  // BEQ
            1: funct3 = 3'b001;  // BNE
            2: funct3 = 3'b100;  // BLT
            3: funct3 = 3'b101;  // BGE
            4: funct3 = 3'b110;  // BLTU
            5: funct3 = 3'b111;  // BGEU
        endcase

        return encode_b_type(offset, rs2, rs1, funct3, OPCODE_BRANCH);
    endfunction

    // Generate JAL instruction
    function logic [31:0] gen_jal(int current_idx, int total_instr);
        logic [4:0] rd;
        logic [20:0] offset;
        int target_idx;
        int offset_words;

        rd = $urandom_range(1, 31);

        // Forward jump only
        target_idx = $urandom_range(current_idx + 1, total_instr - 1);
        offset_words = target_idx - current_idx;
        offset = (offset_words << 2);

        return encode_j_type(offset, rd, OPCODE_JAL);
    endfunction

    // Generate LUI/AUIPC instruction
    function logic [31:0] gen_upper();
        logic [4:0] rd;
        logic [19:0] imm;
        logic [6:0] opcode;

        rd  = $urandom_range(1, 31);
        imm = $urandom_range(0, 20'hFFFFF);
        opcode = $urandom_range(0, 1) ? OPCODE_LUI : OPCODE_AUIPC;

        return encode_u_type(imm, rd, opcode);
    endfunction

    //-------------------------------------------------------------------------
    // Encoding Functions (imported from rv32i_uvm_pkg)
    //-------------------------------------------------------------------------
    function automatic logic [31:0] encode_r_type(
        input logic [6:0] funct7, input logic [4:0] rs2, input logic [4:0] rs1,
        input logic [2:0] funct3, input logic [4:0] rd, input logic [6:0] opcode
    );
        return {funct7, rs2, rs1, funct3, rd, opcode};
    endfunction

    function automatic logic [31:0] encode_i_type(
        input logic [11:0] imm, input logic [4:0] rs1,
        input logic [2:0] funct3, input logic [4:0] rd, input logic [6:0] opcode
    );
        return {imm, rs1, funct3, rd, opcode};
    endfunction

    function automatic logic [31:0] encode_s_type(
        input logic [11:0] imm, input logic [4:0] rs2, input logic [4:0] rs1,
        input logic [2:0] funct3, input logic [6:0] opcode
    );
        return {imm[11:5], rs2, rs1, funct3, imm[4:0], opcode};
    endfunction

    function automatic logic [31:0] encode_b_type(
        input logic [12:0] imm, input logic [4:0] rs2, input logic [4:0] rs1,
        input logic [2:0] funct3, input logic [6:0] opcode
    );
        return {imm[12], imm[10:5], rs2, rs1, funct3, imm[4:1], imm[11], opcode};
    endfunction

    function automatic logic [31:0] encode_u_type(
        input logic [19:0] imm, input logic [4:0] rd, input logic [6:0] opcode
    );
        return {imm, rd, opcode};
    endfunction

    function automatic logic [31:0] encode_j_type(
        input logic [20:0] imm, input logic [4:0] rd, input logic [6:0] opcode
    );
        return {imm[20], imm[10:1], imm[11], imm[19:12], rd, opcode};
    endfunction

    function automatic logic [31:0] encode_addi(
        input logic [4:0] rd, input logic [4:0] rs1, input logic [11:0] imm
    );
        return encode_i_type(imm, rs1, 3'b000, rd, OPCODE_OP_IMM);
    endfunction

    function automatic logic [31:0] encode_ebreak();
        return 32'h00100073;
    endfunction

    //-------------------------------------------------------------------------
    // Get Generated Program
    //-------------------------------------------------------------------------
    function void get_program(ref logic [31:0] prog[]);
        prog = new[program_data.size()];
        foreach (program_data[i])
            prog[i] = program_data[i];
    endfunction

    //-------------------------------------------------------------------------
    // Print Program Disassembly
    //-------------------------------------------------------------------------
    function void print_program();
        string dump_str;
        dump_str = "\n=== Generated Program ===\n";
        foreach (program_data[i]) begin
            dump_str = {dump_str, $sformatf("  0x%04h: 0x%08h\n", i*4, program_data[i])};
        end
        `uvm_info("INSTR_GEN", dump_str, UVM_MEDIUM)
    endfunction

endclass
