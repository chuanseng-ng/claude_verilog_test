// RV32I Package - Defines opcodes, types, and parameters for the RISC-V RV32I processor
package rv32i_pkg;

    // ============================================================================
    // Data Width Parameters
    // ============================================================================
    parameter int XLEN = 32;                    // Data width
    parameter int ILEN = 32;                    // Instruction width
    parameter int REG_ADDR_WIDTH = 5;           // Register address width (32 registers)
    parameter int NUM_REGS = 32;                // Number of registers

    // ============================================================================
    // Opcodes (inst[6:0])
    // ============================================================================
    typedef enum logic [6:0] {
        OP_LUI      = 7'b0110111,   // Load Upper Immediate
        OP_AUIPC    = 7'b0010111,   // Add Upper Immediate to PC
        OP_JAL      = 7'b1101111,   // Jump and Link
        OP_JALR     = 7'b1100111,   // Jump and Link Register
        OP_BRANCH   = 7'b1100011,   // Branch instructions
        OP_LOAD     = 7'b0000011,   // Load instructions
        OP_STORE    = 7'b0100011,   // Store instructions
        OP_IMM      = 7'b0010011,   // Immediate ALU operations
        OP_REG      = 7'b0110011,   // Register ALU operations
        OP_FENCE    = 7'b0001111,   // Fence (memory ordering)
        OP_SYSTEM   = 7'b1110011    // System instructions (ECALL, EBREAK)
    } opcode_e;

    // ============================================================================
    // Funct3 fields for various instruction types
    // ============================================================================

    // Branch funct3
    typedef enum logic [2:0] {
        BR_BEQ  = 3'b000,
        BR_BNE  = 3'b001,
        BR_BLT  = 3'b100,
        BR_BGE  = 3'b101,
        BR_BLTU = 3'b110,
        BR_BGEU = 3'b111
    } branch_funct3_e;

    // Load funct3
    typedef enum logic [2:0] {
        LD_LB   = 3'b000,
        LD_LH   = 3'b001,
        LD_LW   = 3'b010,
        LD_LBU  = 3'b100,
        LD_LHU  = 3'b101
    } load_funct3_e;

    // Store funct3
    typedef enum logic [2:0] {
        ST_SB   = 3'b000,
        ST_SH   = 3'b001,
        ST_SW   = 3'b010
    } store_funct3_e;

    // ALU funct3 (for OP_IMM and OP_REG)
    typedef enum logic [2:0] {
        ALU_ADD_SUB = 3'b000,   // ADD/SUB (SUB when funct7[5]=1)
        ALU_SLL     = 3'b001,   // Shift Left Logical
        ALU_SLT     = 3'b010,   // Set Less Than (signed)
        ALU_SLTU    = 3'b011,   // Set Less Than Unsigned
        ALU_XOR     = 3'b100,   // XOR
        ALU_SRL_SRA = 3'b101,   // Shift Right Logical/Arithmetic
        ALU_OR      = 3'b110,   // OR
        ALU_AND     = 3'b111    // AND
    } alu_funct3_e;

    // ============================================================================
    // ALU Operation Select
    // ============================================================================
    typedef enum logic [3:0] {
        ALU_OP_ADD  = 4'b0000,
        ALU_OP_SUB  = 4'b0001,
        ALU_OP_SLL  = 4'b0010,
        ALU_OP_SLT  = 4'b0011,
        ALU_OP_SLTU = 4'b0100,
        ALU_OP_XOR  = 4'b0101,
        ALU_OP_SRL  = 4'b0110,
        ALU_OP_SRA  = 4'b0111,
        ALU_OP_OR   = 4'b1000,
        ALU_OP_AND  = 4'b1001,
        ALU_OP_PASS_B = 4'b1010  // Pass operand B (for LUI)
    } alu_op_e;

    // ============================================================================
    // Immediate Type Selection
    // ============================================================================
    typedef enum logic [2:0] {
        IMM_I = 3'b000,   // I-type immediate
        IMM_S = 3'b001,   // S-type immediate
        IMM_B = 3'b010,   // B-type immediate
        IMM_U = 3'b011,   // U-type immediate
        IMM_J = 3'b100    // J-type immediate
    } imm_type_e;

    // ============================================================================
    // ALU Source Selection
    // ============================================================================
    typedef enum logic [1:0] {
        ALU_SRC_REG  = 2'b00,   // Source from register file
        ALU_SRC_IMM  = 2'b01,   // Source from immediate
        ALU_SRC_PC   = 2'b10,   // Source from PC
        ALU_SRC_ZERO = 2'b11    // Zero
    } alu_src_e;

    // ============================================================================
    // Writeback Source Selection
    // ============================================================================
    typedef enum logic [1:0] {
        WB_SRC_ALU  = 2'b00,    // Writeback from ALU result
        WB_SRC_MEM  = 2'b01,    // Writeback from memory
        WB_SRC_PC4  = 2'b10,    // Writeback PC+4 (for JAL/JALR)
        WB_SRC_IMM  = 2'b11     // Writeback immediate (for LUI)
    } wb_src_e;

    // ============================================================================
    // CPU State Machine States
    // ============================================================================
    typedef enum logic [2:0] {
        CPU_RESET    = 3'b000,
        CPU_FETCH    = 3'b001,
        CPU_DECODE   = 3'b010,
        CPU_EXECUTE  = 3'b011,
        CPU_MEM_WAIT = 3'b100,
        CPU_WRITEBACK= 3'b101,
        CPU_HALTED   = 3'b110,
        CPU_STEP     = 3'b111
    } cpu_state_e;

    // ============================================================================
    // Debug Halt Cause
    // ============================================================================
    typedef enum logic [3:0] {
        HALT_NONE       = 4'b0000,
        HALT_REQUEST    = 4'b0001,
        HALT_BREAKPOINT = 4'b0010,
        HALT_STEP       = 4'b0011,
        HALT_EBREAK     = 4'b0100
    } halt_cause_e;

    // ============================================================================
    // Instruction Fields Structure
    // ============================================================================
    typedef struct packed {
        logic [6:0]  funct7;
        logic [4:0]  rs2;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [4:0]  rd;
        logic [6:0]  opcode;
    } instr_r_t;

    typedef struct packed {
        logic [11:0] imm;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [4:0]  rd;
        logic [6:0]  opcode;
    } instr_i_t;

    typedef struct packed {
        logic [6:0]  imm_11_5;
        logic [4:0]  rs2;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [4:0]  imm_4_0;
        logic [6:0]  opcode;
    } instr_s_t;

    typedef struct packed {
        logic        imm_12;
        logic [5:0]  imm_10_5;
        logic [4:0]  rs2;
        logic [4:0]  rs1;
        logic [2:0]  funct3;
        logic [3:0]  imm_4_1;
        logic        imm_11;
        logic [6:0]  opcode;
    } instr_b_t;

    typedef struct packed {
        logic [19:0] imm;
        logic [4:0]  rd;
        logic [6:0]  opcode;
    } instr_u_t;

    typedef struct packed {
        logic        imm_20;
        logic [9:0]  imm_10_1;
        logic        imm_11;
        logic [7:0]  imm_19_12;
        logic [4:0]  rd;
        logic [6:0]  opcode;
    } instr_j_t;

    // ============================================================================
    // Control Signals Structure
    // ============================================================================
    typedef struct packed {
        logic        reg_write;      // Write to register file
        logic        mem_read;       // Memory read operation
        logic        mem_write;      // Memory write operation
        logic        branch;         // Branch instruction
        logic        jump;           // Jump instruction (JAL/JALR)
        alu_op_e     alu_op;         // ALU operation
        alu_src_e    alu_src_a;      // ALU source A selection
        alu_src_e    alu_src_b;      // ALU source B selection
        wb_src_e     wb_src;         // Writeback source selection
        imm_type_e   imm_type;       // Immediate type
        logic [2:0]  funct3;         // Memory access size / branch type
    } ctrl_signals_t;

    // ============================================================================
    // Memory Access Size
    // ============================================================================
    typedef enum logic [1:0] {
        MEM_SIZE_BYTE = 2'b00,
        MEM_SIZE_HALF = 2'b01,
        MEM_SIZE_WORD = 2'b10
    } mem_size_e;

    // ============================================================================
    // Debug Register Addresses (APB address space)
    // ============================================================================
    parameter logic [11:0] DBG_CTRL_ADDR      = 12'h000;
    parameter logic [11:0] DBG_STATUS_ADDR    = 12'h004;
    parameter logic [11:0] DBG_PC_ADDR        = 12'h008;
    parameter logic [11:0] DBG_INSTR_ADDR     = 12'h00C;
    parameter logic [11:0] DBG_GPR_BASE_ADDR  = 12'h010;  // GPR[0] at 0x010, GPR[31] at 0x08C
    parameter logic [11:0] DBG_BP0_ADDR_ADDR  = 12'h100;
    parameter logic [11:0] DBG_BP0_CTRL_ADDR  = 12'h104;
    parameter logic [11:0] DBG_BP1_ADDR_ADDR  = 12'h108;
    parameter logic [11:0] DBG_BP1_CTRL_ADDR  = 12'h10C;

    // ============================================================================
    // Helper Functions
    // ============================================================================

    // Sign extension
    function automatic logic [XLEN-1:0] sign_extend;
        input logic [XLEN-1:0] value;
        input int              width;
        begin
            sign_extend = {{(XLEN-width){value[width-1]}}, value[width-1:0]};
        end
    endfunction

endpackage
