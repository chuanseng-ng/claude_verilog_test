//-----------------------------------------------------------------------------
// RV32I Reference Model
// Software model for checking CPU execution
//-----------------------------------------------------------------------------

class rv32i_ref_model extends uvm_component;

    `uvm_component_utils(rv32i_ref_model)

    //-------------------------------------------------------------------------
    // CPU State
    //-------------------------------------------------------------------------
    logic [31:0] pc;
    logic [31:0] regs [32];
    logic [31:0] memory [int];  // Memory model (associative array)
    bit          halted;

    //-------------------------------------------------------------------------
    // Statistics
    //-------------------------------------------------------------------------
    int unsigned instr_count;
    int unsigned load_count;
    int unsigned store_count;
    int unsigned branch_count;
    int unsigned branch_taken;

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    //-------------------------------------------------------------------------
    // Reset State
    //-------------------------------------------------------------------------
    function void reset();
        pc = 32'h0;
        foreach (regs[i]) regs[i] = 32'h0;
        halted = 0;
        instr_count = 0;
        load_count = 0;
        store_count = 0;
        branch_count = 0;
        branch_taken = 0;
    endfunction

    //-------------------------------------------------------------------------
    // Load Program
    //-------------------------------------------------------------------------
    function void load_program(logic [31:0] prog[], int start_addr = 0);
        foreach (prog[i])
            memory[(start_addr >> 2) + i] = prog[i];
    endfunction

    //-------------------------------------------------------------------------
    // Memory Access Functions
    //-------------------------------------------------------------------------
    function logic [31:0] mem_read(logic [31:0] addr);
        int word_addr = addr >> 2;
        if (memory.exists(word_addr))
            return memory[word_addr];
        else
            return 32'h0;
    endfunction

    function void mem_write(logic [31:0] addr, logic [31:0] data, logic [3:0] strb);
        int word_addr = addr >> 2;
        logic [31:0] old_data;

        if (memory.exists(word_addr))
            old_data = memory[word_addr];
        else
            old_data = 32'h0;

        if (strb[0]) old_data[7:0]   = data[7:0];
        if (strb[1]) old_data[15:8]  = data[15:8];
        if (strb[2]) old_data[23:16] = data[23:16];
        if (strb[3]) old_data[31:24] = data[31:24];

        memory[word_addr] = old_data;
    endfunction

    //-------------------------------------------------------------------------
    // Execute Single Instruction
    //-------------------------------------------------------------------------
    function void execute();
        logic [31:0] instr;
        logic [6:0]  opcode;
        logic [4:0]  rd, rs1, rs2;
        logic [2:0]  funct3;
        logic [6:0]  funct7;
        logic [31:0] imm_i, imm_s, imm_b, imm_u, imm_j;
        logic [31:0] rs1_val, rs2_val, result;
        logic [31:0] next_pc;
        logic        branch_taken_flag;

        if (halted) return;

        // Fetch
        instr = mem_read(pc);
        instr_count++;

        // Decode
        opcode = instr[6:0];
        rd     = instr[11:7];
        funct3 = instr[14:12];
        rs1    = instr[19:15];
        rs2    = instr[24:20];
        funct7 = instr[31:25];

        // Immediate decoding
        imm_i = {{20{instr[31]}}, instr[31:20]};
        imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
        imm_b = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
        imm_u = {instr[31:12], 12'h0};
        imm_j = {{11{instr[31]}}, instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};

        // Get register values
        rs1_val = (rs1 == 0) ? 32'h0 : regs[rs1];
        rs2_val = (rs2 == 0) ? 32'h0 : regs[rs2];

        next_pc = pc + 4;
        branch_taken_flag = 0;

        case (opcode)
            // LUI
            7'b0110111: begin
                result = imm_u;
                write_reg(rd, result);
            end

            // AUIPC
            7'b0010111: begin
                result = pc + imm_u;
                write_reg(rd, result);
            end

            // JAL
            7'b1101111: begin
                write_reg(rd, pc + 4);
                next_pc = pc + imm_j;
            end

            // JALR
            7'b1100111: begin
                write_reg(rd, pc + 4);
                next_pc = (rs1_val + imm_i) & ~32'h1;
            end

            // Branch
            7'b1100011: begin
                branch_count++;
                case (funct3)
                    3'b000: branch_taken_flag = (rs1_val == rs2_val);                    // BEQ
                    3'b001: branch_taken_flag = (rs1_val != rs2_val);                    // BNE
                    3'b100: branch_taken_flag = ($signed(rs1_val) < $signed(rs2_val));   // BLT
                    3'b101: branch_taken_flag = ($signed(rs1_val) >= $signed(rs2_val));  // BGE
                    3'b110: branch_taken_flag = (rs1_val < rs2_val);                     // BLTU
                    3'b111: branch_taken_flag = (rs1_val >= rs2_val);                    // BGEU
                    default: ;
                endcase
                if (branch_taken_flag) begin
                    next_pc = pc + imm_b;
                    branch_taken++;
                end
            end

            // Load
            7'b0000011: begin
                load_count++;
                result = execute_load(rs1_val + imm_i, funct3);
                write_reg(rd, result);
            end

            // Store
            7'b0100011: begin
                store_count++;
                execute_store(rs1_val + imm_s, rs2_val, funct3);
            end

            // ALU Immediate
            7'b0010011: begin
                result = execute_alu_imm(rs1_val, imm_i, funct3, funct7);
                write_reg(rd, result);
            end

            // ALU Register
            7'b0110011: begin
                result = execute_alu_reg(rs1_val, rs2_val, funct3, funct7);
                write_reg(rd, result);
            end

            // SYSTEM
            7'b1110011: begin
                if (instr == 32'h00100073) begin  // EBREAK
                    halted = 1;
                    `uvm_info("REF_MODEL", "EBREAK - CPU halted", UVM_MEDIUM)
                end
            end

            default: begin
                `uvm_warning("REF_MODEL", $sformatf("Unknown opcode: 0x%02h at PC=0x%08h", opcode, pc))
            end
        endcase

        pc = next_pc;
    endfunction

    //-------------------------------------------------------------------------
    // ALU Operations
    //-------------------------------------------------------------------------
    function logic [31:0] execute_alu_reg(
        logic [31:0] a, logic [31:0] b, logic [2:0] funct3, logic [6:0] funct7
    );
        case (funct3)
            3'b000: return funct7[5] ? (a - b) : (a + b);  // ADD/SUB
            3'b001: return a << b[4:0];                     // SLL
            3'b010: return {31'h0, $signed(a) < $signed(b)};  // SLT
            3'b011: return {31'h0, a < b};                  // SLTU
            3'b100: return a ^ b;                           // XOR
            3'b101: return funct7[5] ? ($signed(a) >>> b[4:0]) : (a >> b[4:0]);  // SRL/SRA
            3'b110: return a | b;                           // OR
            3'b111: return a & b;                           // AND
            default: return 32'h0;
        endcase
    endfunction

    function logic [31:0] execute_alu_imm(
        logic [31:0] a, logic [31:0] imm, logic [2:0] funct3, logic [6:0] funct7
    );
        case (funct3)
            3'b000: return a + imm;                        // ADDI
            3'b001: return a << imm[4:0];                  // SLLI
            3'b010: return {31'h0, $signed(a) < $signed(imm)};  // SLTI
            3'b011: return {31'h0, a < imm};               // SLTIU
            3'b100: return a ^ imm;                        // XORI
            3'b101: return imm[10] ? ($signed(a) >>> imm[4:0]) : (a >> imm[4:0]);  // SRLI/SRAI
            3'b110: return a | imm;                        // ORI
            3'b111: return a & imm;                        // ANDI
            default: return 32'h0;
        endcase
    endfunction

    //-------------------------------------------------------------------------
    // Load Operations
    //-------------------------------------------------------------------------
    function logic [31:0] execute_load(logic [31:0] addr, logic [2:0] funct3);
        logic [31:0] word = mem_read(addr & ~32'h3);
        logic [1:0] offset = addr[1:0];
        logic [31:0] result;

        case (funct3)
            3'b000: begin  // LB
                case (offset)
                    2'b00: result = {{24{word[7]}}, word[7:0]};
                    2'b01: result = {{24{word[15]}}, word[15:8]};
                    2'b10: result = {{24{word[23]}}, word[23:16]};
                    2'b11: result = {{24{word[31]}}, word[31:24]};
                endcase
            end
            3'b001: begin  // LH
                case (offset[1])
                    1'b0: result = {{16{word[15]}}, word[15:0]};
                    1'b1: result = {{16{word[31]}}, word[31:16]};
                endcase
            end
            3'b010: result = word;  // LW
            3'b100: begin  // LBU
                case (offset)
                    2'b00: result = {24'h0, word[7:0]};
                    2'b01: result = {24'h0, word[15:8]};
                    2'b10: result = {24'h0, word[23:16]};
                    2'b11: result = {24'h0, word[31:24]};
                endcase
            end
            3'b101: begin  // LHU
                case (offset[1])
                    1'b0: result = {16'h0, word[15:0]};
                    1'b1: result = {16'h0, word[31:16]};
                endcase
            end
            default: result = 32'h0;
        endcase
        return result;
    endfunction

    //-------------------------------------------------------------------------
    // Store Operations
    //-------------------------------------------------------------------------
    function void execute_store(logic [31:0] addr, logic [31:0] data, logic [2:0] funct3);
        logic [3:0] strb;
        logic [31:0] aligned_data;
        logic [1:0] offset = addr[1:0];

        case (funct3)
            3'b000: begin  // SB
                case (offset)
                    2'b00: begin strb = 4'b0001; aligned_data = {24'h0, data[7:0]}; end
                    2'b01: begin strb = 4'b0010; aligned_data = {16'h0, data[7:0], 8'h0}; end
                    2'b10: begin strb = 4'b0100; aligned_data = {8'h0, data[7:0], 16'h0}; end
                    2'b11: begin strb = 4'b1000; aligned_data = {data[7:0], 24'h0}; end
                endcase
            end
            3'b001: begin  // SH
                case (offset[1])
                    1'b0: begin strb = 4'b0011; aligned_data = {16'h0, data[15:0]}; end
                    1'b1: begin strb = 4'b1100; aligned_data = {data[15:0], 16'h0}; end
                endcase
            end
            3'b010: begin  // SW
                strb = 4'b1111;
                aligned_data = data;
            end
            default: begin
                strb = 4'b0000;
                aligned_data = 32'h0;
            end
        endcase

        mem_write(addr & ~32'h3, aligned_data, strb);
    endfunction

    //-------------------------------------------------------------------------
    // Register Write
    //-------------------------------------------------------------------------
    function void write_reg(logic [4:0] rd, logic [31:0] value);
        if (rd != 0) regs[rd] = value;
    endfunction

    //-------------------------------------------------------------------------
    // Run Until Halt
    //-------------------------------------------------------------------------
    function void run_to_halt(int max_cycles = 10000);
        int cycles = 0;
        while (!halted && cycles < max_cycles) begin
            execute();
            cycles++;
        end
        if (!halted)
            `uvm_warning("REF_MODEL", $sformatf("Timeout after %0d cycles", max_cycles))
    endfunction

    //-------------------------------------------------------------------------
    // Compare with DUT State
    //-------------------------------------------------------------------------
    function bit compare_state(logic [31:0] dut_pc, logic [31:0] dut_regs[32]);
        bit match = 1;

        if (pc != dut_pc) begin
            `uvm_error("REF_MODEL", $sformatf("PC mismatch: ref=0x%08h, dut=0x%08h", pc, dut_pc))
            match = 0;
        end

        for (int i = 0; i < 32; i++) begin
            if (regs[i] != dut_regs[i]) begin
                `uvm_error("REF_MODEL", $sformatf("x%0d mismatch: ref=0x%08h, dut=0x%08h", i, regs[i], dut_regs[i]))
                match = 0;
            end
        end

        return match;
    endfunction

    //-------------------------------------------------------------------------
    // Print Statistics
    //-------------------------------------------------------------------------
    function void print_stats();
        string stats;
        stats = "\n=== Reference Model Statistics ===\n";
        stats = {stats, $sformatf("  Instructions executed: %0d\n", instr_count)};
        stats = {stats, $sformatf("  Loads: %0d\n", load_count)};
        stats = {stats, $sformatf("  Stores: %0d\n", store_count)};
        stats = {stats, $sformatf("  Branches: %0d (taken: %0d)\n", branch_count, branch_taken)};
        stats = {stats, $sformatf("  Final PC: 0x%08h\n", pc)};
        `uvm_info("REF_MODEL", stats, UVM_LOW)
    endfunction

endclass
