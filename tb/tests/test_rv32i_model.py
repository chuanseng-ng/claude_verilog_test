"""
Unit tests for RV32IModel.

Tests the RV32I CPU reference model instruction execution.
"""

import sys
from pathlib import Path
import pytest

from tb.models.rv32i_model import RV32IModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestRV32IModel:
    """Test cases for RV32I CPU model."""

    def test_initialization(self):
        """Test CPU model initializes correctly."""
        cpu = RV32IModel()
        assert cpu.pc == 0x0000_0000
        assert len(cpu.regs) == 32
        assert all(r == 0 for r in cpu.regs)
        assert cpu.cycle_count == 0

    def test_reset(self):
        """Test CPU reset."""
        cpu = RV32IModel(reset_pc=0x1000)
        cpu.regs[1] = 42
        cpu.pc = 0x2000
        cpu.cycle_count = 10

        cpu.reset()
        assert cpu.pc == 0x1000
        assert cpu.regs[1] == 0
        assert cpu.cycle_count == 0

    def test_x0_hardwired_zero(self):
        """Test x0 is always zero."""
        cpu = RV32IModel()

        # Try to write to x0: ADDI x0, x0, 1
        insn = 0x00100013
        cpu.step(insn)

        assert cpu.regs[0] == 0, "x0 must remain zero"

    # Arithmetic Instructions
    def test_add_instruction(self):
        """Test ADD instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 10
        cpu.regs[2] = 20

        # ADD x3, x1, x2 (0x002081b3)
        insn = 0x002081B3
        result = cpu.step(insn)

        assert cpu.regs[3] == 30
        assert result["rd"] == 3
        assert result["rd_value"] == 30
        assert result["next_pc"] == 4

    def test_sub_instruction(self):
        """Test SUB instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 30
        cpu.regs[2] = 10

        # SUB x3, x1, x2 (0x402081b3)
        insn = 0x402081B3
        cpu.step(insn)

        assert cpu.regs[3] == 20

    def test_addi_instruction(self):
        """Test ADDI instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 10

        # ADDI x2, x1, 5 (0x00508113)
        insn = 0x00508113
        cpu.step(insn)

        assert cpu.regs[2] == 15

    def test_addi_negative(self):
        """Test ADDI with negative immediate."""
        cpu = RV32IModel()
        cpu.regs[1] = 10

        # ADDI x2, x1, -5 (0xffb08113)
        insn = 0xFFB08113
        cpu.step(insn)

        assert cpu.regs[2] == 5

    # Logical Instructions
    def test_and_instruction(self):
        """Test AND instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0b11001100
        cpu.regs[2] = 0b10101010

        # AND x3, x1, x2 (0x0020f1b3)
        insn = 0x0020F1B3
        cpu.step(insn)

        assert cpu.regs[3] == 0b10001000

    def test_or_instruction(self):
        """Test OR instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0b11001100
        cpu.regs[2] = 0b10101010

        # OR x3, x1, x2 (0x0020e1b3)
        insn = 0x0020E1B3
        cpu.step(insn)

        assert cpu.regs[3] == 0b11101110

    def test_xor_instruction(self):
        """Test XOR instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0b11001100
        cpu.regs[2] = 0b10101010

        # XOR x3, x1, x2 (0x0020c1b3)
        insn = 0x0020C1B3
        cpu.step(insn)

        assert cpu.regs[3] == 0b01100110

    # Shift Instructions
    def test_sll_instruction(self):
        """Test SLL (shift left logical) instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0x00000001
        cpu.regs[2] = 4

        # SLL x3, x1, x2 (0x002091b3)
        insn = 0x002091B3
        cpu.step(insn)

        assert cpu.regs[3] == 0x00000010

    def test_srl_instruction(self):
        """Test SRL (shift right logical) instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0x00000010
        cpu.regs[2] = 2

        # SRL x3, x1, x2 (0x0020d1b3)
        insn = 0x0020D1B3
        cpu.step(insn)

        assert cpu.regs[3] == 0x00000004

    def test_sra_instruction(self):
        """Test SRA (shift right arithmetic) instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0x80000000  # Negative number
        cpu.regs[2] = 4

        # SRA x3, x1, x2 (0x4020d1b3)
        insn = 0x4020D1B3
        cpu.step(insn)

        assert cpu.regs[3] == 0xF8000000  # Sign extended

    # Comparison Instructions
    def test_slt_instruction(self):
        """Test SLT (set less than) instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 5
        cpu.regs[2] = 10

        # SLT x3, x1, x2 (0x0020a1b3)
        insn = 0x0020A1B3
        cpu.step(insn)

        assert cpu.regs[3] == 1  # 5 < 10

    def test_sltu_instruction(self):
        """Test SLTU (set less than unsigned) instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0xFFFFFFFF  # -1 as signed, large as unsigned
        cpu.regs[2] = 1

        # SLTU x3, x1, x2 (0x0020b1b3)
        insn = 0x0020B1B3
        cpu.step(insn)

        assert cpu.regs[3] == 0  # 0xFFFFFFFF > 1 (unsigned)

    # Upper Immediate Instructions
    def test_lui_instruction(self):
        """Test LUI (load upper immediate) instruction."""
        cpu = RV32IModel()

        # LUI x1, 0x12345 (0x123450b7)
        insn = 0x123450B7
        cpu.step(insn)

        assert cpu.regs[1] == 0x12345000

    def test_auipc_instruction(self):
        """Test AUIPC (add upper immediate to PC) instruction."""
        cpu = RV32IModel()
        cpu.pc = 0x1000

        # AUIPC x1, 0x12345 (0x12345097)
        insn = 0x12345097
        cpu.step(insn)

        assert cpu.regs[1] == 0x12345000 + 0x1000

    # Branch Instructions
    def test_beq_taken(self):
        """Test BEQ branch taken."""
        cpu = RV32IModel()
        cpu.regs[1] = 10
        cpu.regs[2] = 10

        # BEQ x1, x2, 8 (0x00208463)
        insn = 0x00208463
        result = cpu.step(insn)

        assert result["next_pc"] == 8  # Branch taken

    def test_beq_not_taken(self):
        """Test BEQ branch not taken."""
        cpu = RV32IModel()
        cpu.regs[1] = 10
        cpu.regs[2] = 20

        # BEQ x1, x2, 8 (0x00208463)
        insn = 0x00208463
        result = cpu.step(insn)

        assert result["next_pc"] == 4  # Not taken

    def test_bne_taken(self):
        """Test BNE branch taken."""
        cpu = RV32IModel()
        cpu.regs[1] = 10
        cpu.regs[2] = 20

        # BNE x1, x2, 8 (0x00209463)
        insn = 0x00209463
        result = cpu.step(insn)

        assert result["next_pc"] == 8  # Branch taken

    def test_blt_taken(self):
        """Test BLT (branch less than) taken."""
        cpu = RV32IModel()
        cpu.regs[1] = 5
        cpu.regs[2] = 10

        # BLT x1, x2, 8 (0x0020c463)
        insn = 0x0020C463
        result = cpu.step(insn)

        assert result["next_pc"] == 8  # Branch taken

    # Jump Instructions
    def test_jal_instruction(self):
        """Test JAL (jump and link) instruction."""
        cpu = RV32IModel()
        cpu.pc = 0x1000

        # JAL x1, 0x100 (offset = 0x100)
        # JAL encoding: imm[20|10:1|11|19:12] rd opcode
        insn = 0x100000EF  # JAL x1, 0x100
        result = cpu.step(insn)

        assert cpu.regs[1] == 0x1004  # Return address
        assert result["next_pc"] == 0x1100  # PC + offset

    def test_jalr_instruction(self):
        """Test JALR (jump and link register) instruction."""
        cpu = RV32IModel()
        cpu.pc = 0x1000
        cpu.regs[2] = 0x2000

        # JALR x1, x2, 0x10 (0x010100e7)
        insn = 0x010100E7
        result = cpu.step(insn)

        assert cpu.regs[1] == 0x1004  # Return address
        assert result["next_pc"] == 0x2010  # rs1 + imm (LSB cleared)

    # Load/Store Instructions
    def test_lw_instruction(self):
        """Test LW (load word) instruction."""
        cpu = RV32IModel()
        cpu.memory.write(0x1000, 0x12345678, 4)
        cpu.regs[1] = 0x1000

        # LW x2, 0(x1) (0x0000a103)
        insn = 0x0000A103
        result = cpu.step(insn)

        assert cpu.regs[2] == 0x12345678
        assert result["mem_addr"] == 0x1000
        assert not result["mem_write"]

    def test_sw_instruction(self):
        """Test SW (store word) instruction."""
        cpu = RV32IModel()
        cpu.regs[1] = 0x1000
        cpu.regs[2] = 0xDEADBEEF

        # SW x2, 0(x1)
        # S-type: imm[11:5] rs2 rs1 funct3 imm[4:0] opcode
        # 0000000 00010 00001 010 00000 0100011 = 0x0020A023
        insn = 0x0020A023
        result = cpu.step(insn)

        assert cpu.memory.read(0x1000, 4) == 0xDEADBEEF
        assert result["mem_addr"] == 0x1000
        assert result["mem_write"]

    def test_lb_instruction(self):
        """Test LB (load byte) instruction with sign extension."""
        cpu = RV32IModel()
        cpu.memory.write(0x1000, 0xFF, 1)  # -1 as signed byte
        cpu.regs[1] = 0x1000

        # LB x2, 0(x1) (0x00008103)
        insn = 0x00008103
        cpu.step(insn)

        assert cpu.regs[2] == 0xFFFFFFFF  # Sign extended

    def test_lbu_instruction(self):
        """Test LBU (load byte unsigned) instruction."""
        cpu = RV32IModel()
        cpu.memory.write(0x1000, 0xFF, 1)
        cpu.regs[1] = 0x1000

        # LBU x2, 0(x1) (0x0000c103)
        insn = 0x0000C103
        cpu.step(insn)

        assert cpu.regs[2] == 0x000000FF  # Zero extended

    # Program execution
    def test_simple_program(self):
        """Test executing a simple program."""
        cpu = RV32IModel()

        program = {
            0x0000: 0x00000093,  # addi x1, x0, 0
            0x0004: 0x00100113,  # addi x2, x0, 1
            0x0008: 0x002081B3,  # add x3, x1, x2
        }

        cpu.load_program(program)

        # Execute first instruction
        cpu.step(cpu.memory.read(cpu.pc, 4))
        assert cpu.regs[1] == 0

        # Execute second instruction
        cpu.step(cpu.memory.read(cpu.pc, 4))
        assert cpu.regs[2] == 1

        # Execute third instruction
        cpu.step(cpu.memory.read(cpu.pc, 4))
        assert cpu.regs[3] == 1

    def test_get_state(self):
        """Test getting CPU state."""
        cpu = RV32IModel()
        cpu.regs[1] = 42
        cpu.pc = 0x1000
        cpu.cycle_count = 5

        state = cpu.get_state()
        assert state["pc"] == 0x1000
        assert state["regs"][1] == 42
        assert state["cycle_count"] == 5

    def test_illegal_instruction(self):
        """Test illegal instruction triggers trap."""
        cpu = RV32IModel()

        # Invalid opcode
        insn = 0xFFFFFFFF
        result = cpu.step(insn)

        assert result["trap"]
        assert result["trap_cause"] == cpu.TRAP_ILLEGAL_INSTRUCTION
        assert cpu.pc == cpu.trap_vector

    def test_misaligned_load(self):
        """Test misaligned load triggers trap."""
        cpu = RV32IModel()
        cpu.regs[1] = 0x1001  # Misaligned address

        # LW x2, 0(x1) - should trap on misaligned access
        insn = 0x0000A103
        result = cpu.step(insn)

        assert result["trap"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
