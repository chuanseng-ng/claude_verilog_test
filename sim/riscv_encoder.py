#!/usr/bin/env python3
"""
RISC-V RV32I instruction encoder utility.
Generates correct 32-bit encodings for all RV32I instructions.
"""

def encode_r_type(funct7, rs2, rs1, funct3, rd, opcode=0b0110011):
    """Encode R-type instruction: ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU"""
    insn = (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
    return insn

def encode_i_type(imm12, rs1, funct3, rd, opcode):
    """Encode I-type instruction: ADDI, SLTI, SLTIU, XORI, ORI, ANDI, loads, JALR"""
    insn = ((imm12 & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
    return insn

def encode_s_type(imm12, rs2, rs1, funct3, opcode=0b0100011):
    """Encode S-type instruction: SB, SH, SW"""
    imm_11_5 = (imm12 >> 5) & 0x7F
    imm_4_0 = imm12 & 0x1F
    insn = (imm_11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm_4_0 << 7) | opcode
    return insn

def encode_b_type(imm13, rs2, rs1, funct3, opcode=0b1100011):
    """Encode B-type instruction: BEQ, BNE, BLT, BGE, BLTU, BGEU"""
    imm_12 = (imm13 >> 12) & 0x1
    imm_10_5 = (imm13 >> 5) & 0x3F
    imm_4_1 = (imm13 >> 1) & 0xF
    imm_11 = (imm13 >> 11) & 0x1
    insn = (imm_12 << 31) | (imm_10_5 << 25) | (rs2 << 20) | (rs1 << 15) | \
           (funct3 << 12) | (imm_4_1 << 8) | (imm_11 << 7) | opcode
    return insn

def encode_u_type(imm20, rd, opcode):
    """Encode U-type instruction: LUI, AUIPC"""
    insn = ((imm20 & 0xFFFFF) << 12) | (rd << 7) | opcode
    return insn

def encode_j_type(imm21, rd, opcode=0b1101111):
    """Encode J-type instruction: JAL"""
    imm_20 = (imm21 >> 20) & 0x1
    imm_10_1 = (imm21 >> 1) & 0x3FF
    imm_11 = (imm21 >> 11) & 0x1
    imm_19_12 = (imm21 >> 12) & 0xFF
    insn = (imm_20 << 31) | (imm_19_12 << 12) | (imm_11 << 20) | (imm_10_1 << 21) | (rd << 7) | opcode
    return insn

# Specific instruction encoders
def ADD(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b000, rd)

def SUB(rd, rs1, rs2):
    return encode_r_type(0b0100000, rs2, rs1, 0b000, rd)

def AND(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b111, rd)

def OR(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b110, rd)

def XOR(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b100, rd)

def SLL(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b001, rd)

def SRL(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b101, rd)

def SRA(rd, rs1, rs2):
    return encode_r_type(0b0100000, rs2, rs1, 0b101, rd)

def SLT(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b010, rd)

def SLTU(rd, rs1, rs2):
    return encode_r_type(0b0000000, rs2, rs1, 0b011, rd)

# I-type arithmetic instructions
def ADDI(rd, rs1, imm12):
    """ADDI rd, rs1, imm12"""
    return encode_i_type(imm12, rs1, 0b000, rd, 0b0010011)

def SLTI(rd, rs1, imm12):
    """SLTI rd, rs1, imm12"""
    return encode_i_type(imm12, rs1, 0b010, rd, 0b0010011)

def SLTIU(rd, rs1, imm12):
    """SLTIU rd, rs1, imm12"""
    return encode_i_type(imm12, rs1, 0b011, rd, 0b0010011)

def XORI(rd, rs1, imm12):
    """XORI rd, rs1, imm12"""
    return encode_i_type(imm12, rs1, 0b100, rd, 0b0010011)

def ORI(rd, rs1, imm12):
    """ORI rd, rs1, imm12"""
    return encode_i_type(imm12, rs1, 0b110, rd, 0b0010011)

def ANDI(rd, rs1, imm12):
    """ANDI rd, rs1, imm12"""
    return encode_i_type(imm12, rs1, 0b111, rd, 0b0010011)

def SLLI(rd, rs1, shamt):
    """SLLI rd, rs1, shamt (shamt is 5-bit)"""
    return encode_i_type(shamt & 0x1F, rs1, 0b001, rd, 0b0010011)

def SRLI(rd, rs1, shamt):
    """SRLI rd, rs1, shamt (shamt is 5-bit)"""
    return encode_i_type(shamt & 0x1F, rs1, 0b101, rd, 0b0010011)

def SRAI(rd, rs1, shamt):
    """SRAI rd, rs1, shamt (shamt is 5-bit with bit[10]=1)"""
    return encode_i_type(0x400 | (shamt & 0x1F), rs1, 0b101, rd, 0b0010011)

# Upper immediate instructions
def LUI(rd, imm20):
    """LUI rd, imm20"""
    return encode_u_type(imm20, rd, 0b0110111)

def AUIPC(rd, imm20):
    """AUIPC rd, imm20"""
    return encode_u_type(imm20, rd, 0b0010111)

# Print test cases for verification
if __name__ == "__main__":
    print("R-Type Instruction Encodings:")
    print("="*60)

    # ADD x6, x3, x4
    add_insn = ADD(6, 3, 4)
    print(f"ADD  x6, x3, x4 = 0x{add_insn:08x}")

    # SUB x3, x1, x2
    sub_insn = SUB(3, 1, 2)
    print(f"SUB  x3, x1, x2 = 0x{sub_insn:08x}")

    # AND x3, x1, x2
    and_insn = AND(3, 1, 2)
    print(f"AND  x3, x1, x2 = 0x{and_insn:08x}")

    # OR x3, x1, x2
    or_insn = OR(3, 1, 2)
    print(f"OR   x3, x1, x2 = 0x{or_insn:08x}")

    # XOR x3, x1, x2
    xor_insn = XOR(3, 1, 2)
    print(f"XOR  x3, x1, x2 = 0x{xor_insn:08x}")

    # SRL x3, x1, x2
    srl_insn = SRL(3, 1, 2)
    print(f"SRL  x3, x1, x2 = 0x{srl_insn:08x}")

    # SRA x3, x1, x2
    sra_insn = SRA(3, 1, 2)
    print(f"SRA  x3, x1, x2 = 0x{sra_insn:08x}")

    # SLT x3, x1, x2
    slt_insn = SLT(3, 1, 2)
    print(f"SLT  x3, x1, x2 = 0x{slt_insn:08x}")

    # SLTU x3, x1, x2
    sltu_insn = SLTU(3, 1, 2)
    print(f"SLTU x3, x1, x2 = 0x{sltu_insn:08x}")

    print("\nI-Type Arithmetic Instruction Encodings:")
    print("="*60)

    # ADDI x1, x0, 0
    addi_insn = ADDI(1, 0, 0)
    print(f"ADDI x1, x0, 0     = 0x{addi_insn:08x}")

    # ADDI x5, x3, 100
    addi_insn2 = ADDI(5, 3, 100)
    print(f"ADDI x5, x3, 100   = 0x{addi_insn2:08x}")

    # SLTI x2, x1, -1
    slti_insn = SLTI(2, 1, -1)
    print(f"SLTI x2, x1, -1    = 0x{slti_insn:08x}")

    # SLTIU x2, x1, 10
    sltiu_insn = SLTIU(2, 1, 10)
    print(f"SLTIU x2, x1, 10   = 0x{sltiu_insn:08x}")

    # XORI x2, x1, 0xFF
    xori_insn = XORI(2, 1, 0xFF)
    print(f"XORI x2, x1, 0xFF  = 0x{xori_insn:08x}")

    # ORI x2, x1, 0x10
    ori_insn = ORI(2, 1, 0x10)
    print(f"ORI  x2, x1, 0x10  = 0x{ori_insn:08x}")

    # ANDI x2, x1, 0xF
    andi_insn = ANDI(2, 1, 0xF)
    print(f"ANDI x2, x1, 0xF   = 0x{andi_insn:08x}")

    # SLLI x2, x1, 4
    slli_insn = SLLI(2, 1, 4)
    print(f"SLLI x2, x1, 4     = 0x{slli_insn:08x}")

    # SRLI x2, x1, 4
    srli_insn = SRLI(2, 1, 4)
    print(f"SRLI x2, x1, 4     = 0x{srli_insn:08x}")

    # SRAI x2, x1, 4
    srai_insn = SRAI(2, 1, 4)
    print(f"SRAI x2, x1, 4     = 0x{srai_insn:08x}")

    print("\nU-Type Instruction Encodings:")
    print("="*60)

    # LUI x1, 0x12345
    lui_insn = LUI(1, 0x12345)
    print(f"LUI   x1, 0x12345  = 0x{lui_insn:08x}")

    # AUIPC x2, 0x1000
    auipc_insn = AUIPC(2, 0x1000)
    print(f"AUIPC x2, 0x1000   = 0x{auipc_insn:08x}")
