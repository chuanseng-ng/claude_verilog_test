//-----------------------------------------------------------------------------
// RV32I UVM Verification Package
// Common types, parameters, and utilities for UVM testbench
//-----------------------------------------------------------------------------

package rv32i_uvm_pkg;
    import uvm_pkg::*;
    `include "uvm_macros.svh"

    import rv32i_pkg::*;
    import axi4lite_pkg::*;

    //-------------------------------------------------------------------------
    // Testbench Parameters
    //-------------------------------------------------------------------------
    parameter int unsigned TB_CLK_PERIOD   = 10;      // ns
    parameter int unsigned TB_MEM_SIZE     = 65536;   // 64KB
    parameter int unsigned TB_MEM_BASE     = 32'h0000_0000;
    parameter int unsigned TB_TIMEOUT      = 100000;  // cycles

    //-------------------------------------------------------------------------
    // RV32I Instruction Types for Generation
    //-------------------------------------------------------------------------
    typedef enum bit [2:0] {
        INSTR_TYPE_R,    // R-type: ADD, SUB, SLL, etc.
        INSTR_TYPE_I,    // I-type: ADDI, SLTI, LW, etc.
        INSTR_TYPE_S,    // S-type: SW, SH, SB
        INSTR_TYPE_B,    // B-type: BEQ, BNE, BLT, etc.
        INSTR_TYPE_U,    // U-type: LUI, AUIPC
        INSTR_TYPE_J     // J-type: JAL, JALR
    } instr_type_e;

    //-------------------------------------------------------------------------
    // ALU Operations for Random Generation
    //-------------------------------------------------------------------------
    typedef enum bit [3:0] {
        RGEN_ADD  = 4'b0000,
        RGEN_SUB  = 4'b1000,
        RGEN_SLL  = 4'b0001,
        RGEN_SLT  = 4'b0010,
        RGEN_SLTU = 4'b0011,
        RGEN_XOR  = 4'b0100,
        RGEN_SRL  = 4'b0101,
        RGEN_SRA  = 4'b1101,
        RGEN_OR   = 4'b0110,
        RGEN_AND  = 4'b0111
    } alu_func_e;

    //-------------------------------------------------------------------------
    // Branch Operations
    //-------------------------------------------------------------------------
    typedef enum bit [2:0] {
        BR_BEQ  = 3'b000,
        BR_BNE  = 3'b001,
        BR_BLT  = 3'b100,
        BR_BGE  = 3'b101,
        BR_BLTU = 3'b110,
        BR_BGEU = 3'b111
    } branch_func_e;

    //-------------------------------------------------------------------------
    // Load/Store Width
    //-------------------------------------------------------------------------
    typedef enum bit [2:0] {
        MEM_BYTE   = 3'b000,
        MEM_HALF   = 3'b001,
        MEM_WORD   = 3'b010,
        MEM_BYTE_U = 3'b100,
        MEM_HALF_U = 3'b101
    } mem_width_e;

    //-------------------------------------------------------------------------
    // Transaction Types
    //-------------------------------------------------------------------------
    typedef enum bit [1:0] {
        TXN_READ,
        TXN_WRITE
    } txn_type_e;

    //-------------------------------------------------------------------------
    // Debug Commands
    //-------------------------------------------------------------------------
    typedef enum bit [3:0] {
        DBG_CMD_HALT     = 4'b0001,
        DBG_CMD_RESUME   = 4'b0010,
        DBG_CMD_STEP     = 4'b0100,
        DBG_CMD_RESET    = 4'b1000
    } dbg_cmd_e;

    //-------------------------------------------------------------------------
    // Instruction Encoding Helper Functions
    //-------------------------------------------------------------------------

    // Encode R-type instruction
    function automatic logic [31:0] encode_r_type(
        input logic [6:0] funct7,
        input logic [4:0] rs2,
        input logic [4:0] rs1,
        input logic [2:0] funct3,
        input logic [4:0] rd,
        input logic [6:0] opcode
    );
        return {funct7, rs2, rs1, funct3, rd, opcode};
    endfunction

    // Encode I-type instruction
    function automatic logic [31:0] encode_i_type(
        input logic [11:0] imm,
        input logic [4:0]  rs1,
        input logic [2:0]  funct3,
        input logic [4:0]  rd,
        input logic [6:0]  opcode
    );
        return {imm, rs1, funct3, rd, opcode};
    endfunction

    // Encode S-type instruction
    function automatic logic [31:0] encode_s_type(
        input logic [11:0] imm,
        input logic [4:0]  rs2,
        input logic [4:0]  rs1,
        input logic [2:0]  funct3,
        input logic [6:0]  opcode
    );
        return {imm[11:5], rs2, rs1, funct3, imm[4:0], opcode};
    endfunction

    // Encode B-type instruction
    function automatic logic [31:0] encode_b_type(
        input logic [12:0] imm,
        input logic [4:0]  rs2,
        input logic [4:0]  rs1,
        input logic [2:0]  funct3,
        input logic [6:0]  opcode
    );
        return {imm[12], imm[10:5], rs2, rs1, funct3, imm[4:1], imm[11], opcode};
    endfunction

    // Encode U-type instruction
    function automatic logic [31:0] encode_u_type(
        input logic [19:0] imm,
        input logic [4:0]  rd,
        input logic [6:0]  opcode
    );
        return {imm, rd, opcode};
    endfunction

    // Encode J-type instruction
    function automatic logic [31:0] encode_j_type(
        input logic [20:0] imm,
        input logic [4:0]  rd,
        input logic [6:0]  opcode
    );
        return {imm[20], imm[10:1], imm[11], imm[19:12], rd, opcode};
    endfunction

    //-------------------------------------------------------------------------
    // Specific Instruction Encoders
    //-------------------------------------------------------------------------

    // NOP instruction (ADDI x0, x0, 0)
    function automatic logic [31:0] encode_nop();
        return encode_i_type(12'h000, 5'd0, 3'b000, 5'd0, OPCODE_OP_IMM);
    endfunction

    // ADDI rd, rs1, imm
    function automatic logic [31:0] encode_addi(
        input logic [4:0]  rd,
        input logic [4:0]  rs1,
        input logic [11:0] imm
    );
        return encode_i_type(imm, rs1, 3'b000, rd, OPCODE_OP_IMM);
    endfunction

    // ADD rd, rs1, rs2
    function automatic logic [31:0] encode_add(
        input logic [4:0] rd,
        input logic [4:0] rs1,
        input logic [4:0] rs2
    );
        return encode_r_type(7'b0000000, rs2, rs1, 3'b000, rd, OPCODE_OP);
    endfunction

    // SUB rd, rs1, rs2
    function automatic logic [31:0] encode_sub(
        input logic [4:0] rd,
        input logic [4:0] rs1,
        input logic [4:0] rs2
    );
        return encode_r_type(7'b0100000, rs2, rs1, 3'b000, rd, OPCODE_OP);
    endfunction

    // LW rd, offset(rs1)
    function automatic logic [31:0] encode_lw(
        input logic [4:0]  rd,
        input logic [4:0]  rs1,
        input logic [11:0] offset
    );
        return encode_i_type(offset, rs1, 3'b010, rd, OPCODE_LOAD);
    endfunction

    // SW rs2, offset(rs1)
    function automatic logic [31:0] encode_sw(
        input logic [4:0]  rs2,
        input logic [4:0]  rs1,
        input logic [11:0] offset
    );
        return encode_s_type(offset, rs2, rs1, 3'b010, OPCODE_STORE);
    endfunction

    // LUI rd, imm
    function automatic logic [31:0] encode_lui(
        input logic [4:0]  rd,
        input logic [19:0] imm
    );
        return encode_u_type(imm, rd, OPCODE_LUI);
    endfunction

    // JAL rd, offset
    function automatic logic [31:0] encode_jal(
        input logic [4:0]  rd,
        input logic [20:0] offset
    );
        return encode_j_type(offset, rd, OPCODE_JAL);
    endfunction

    // BEQ rs1, rs2, offset
    function automatic logic [31:0] encode_beq(
        input logic [4:0]  rs1,
        input logic [4:0]  rs2,
        input logic [12:0] offset
    );
        return encode_b_type(offset, rs2, rs1, 3'b000, OPCODE_BRANCH);
    endfunction

    // EBREAK (halt CPU)
    function automatic logic [31:0] encode_ebreak();
        return 32'h00100073;
    endfunction

    //-------------------------------------------------------------------------
    // Reference Model Types
    //-------------------------------------------------------------------------
    typedef struct {
        logic [31:0] pc;
        logic [31:0] regs [32];
        logic [31:0] next_pc;
    } cpu_state_t;

endpackage
