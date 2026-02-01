"""
ISA Compliance Test Sequences for RV32I Instructions.

This module provides pyuvm sequences for testing individual RV32I instructions
in isolation. Each sequence:
1. Sets up required register values via APB debug interface
2. Loads the target instruction into memory
3. Resumes CPU execution
4. Validates the result

Usage:
    seq = ADDSequence("add_seq", env, rd=5, rs1=1, rs2=2,
                      rs1_val=10, rs2_val=20, expected=30)
    await seq.start()
"""

import sys
from pathlib import Path

# Add project root for imports
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from cocotb.triggers import ClockCycles  # noqa: E402

from sim.riscv_encoder import (  # noqa: E402
    # Arithmetic/Logical R-type
    ADD,
    # Arithmetic/Logical I-type (ADDI also used for register setup)
    ADDI,
    AND,
    ANDI,
    AUIPC,
    # Branch instructions
    BEQ,
    BGE,
    BGEU,
    BLT,
    BLTU,
    BNE,
    # Jump instructions
    JAL,
    JALR,
    # Load instructions
    LB,
    LBU,
    LH,
    LHU,
    # Upper immediate (for large value setup)
    LUI,
    LW,
    OR,
    ORI,
    # Store instructions
    SB,
    SH,
    # Shift R-type
    SLL,
    # Shift I-type
    SLLI,
    SLT,
    SLTI,
    SLTIU,
    SLTU,
    SRA,
    SRAI,
    SRL,
    SRLI,
    SUB,
    SW,
    XOR,
    XORI,
)
from tb.cpu_uvm.sequences.base_sequence import BaseSequence  # noqa: E402


class ISASequenceBase(BaseSequence):
    """
    Base class for ISA compliance test sequences.

    Provides common functionality for single-instruction testing:
    - Register setup via APB debug
    - Program loading
    - Execution and validation
    """

    def __init__(
        self,
        name,
        env,
        instruction,
        setup_regs=None,
        expected_rd=None,
        expected_value=None,
        setup_memory=None,
    ):
        """
        Initialize ISA test sequence.

        Args:
            name: Sequence name
            env: CPUEnvironment reference
            instruction: 32-bit encoded instruction to test
            setup_regs: Dict of {reg_num: value} to initialize before test
            expected_rd: Register number to check after execution
            expected_value: Expected value in rd after execution
            setup_memory: Dict of {addr: value} to initialize memory
        """
        super().__init__(name)  # BaseSequence only takes name
        self.env = env
        self.instruction = instruction
        self.setup_regs = setup_regs or {}
        self.expected_rd = expected_rd
        self.expected_value = expected_value
        self.setup_memory = setup_memory or {}

    async def body(self):
        """Execute single-instruction test."""
        axi_driver = self.env.axi_agent.driver
        apb_driver = self.env.apb_agent.driver

        # NOTE: CPU is already halted by run_isa_test before calling this method

        # Initialize memory if needed (for load/store tests)
        for addr, value in self.setup_memory.items():
            axi_driver.write_word(addr, value)

        # Build test program
        addr = 0x0000
        num_setup_instructions = 0

        # Setup registers using ADDI instructions
        for reg_num, value in self.setup_regs.items():
            if reg_num == 0:
                continue  # Skip x0 (hardwired to zero)

            # ADDI xN, x0, immediate
            # Split large values into multiple ADDI if needed
            if -2048 <= value < 2048:
                # Single ADDI can handle this
                instr = ADDI(reg_num, 0, value & 0xFFF)
                axi_driver.write_word(addr, instr)
                addr += 4
                num_setup_instructions += 1
            else:
                # Need LUI + ADDI for larger values
                # IMPORTANT: ADDI has signed 12-bit immediate, so if bit 11 is set,
                # it will be sign-extended to negative. Compensate by incrementing upper.
                upper = (value >> 12) & 0xFFFFF
                lower = value & 0xFFF

                # If lower >= 0x800, ADDI will sign-extend to negative, so increment upper
                if lower >= 0x800:
                    upper = (upper + 1) & 0xFFFFF

                # LUI xN, upper
                from sim.riscv_encoder import LUI

                axi_driver.write_word(addr, LUI(reg_num, upper))
                addr += 4
                num_setup_instructions += 1

                # ADDI xN, xN, lower (sign-extended)
                if lower != 0:
                    axi_driver.write_word(addr, ADDI(reg_num, reg_num, lower))
                    addr += 4
                    num_setup_instructions += 1

        # Load target instruction
        test_instr_addr = addr
        axi_driver.write_word(addr, self.instruction)
        addr += 4

        # Add EBREAK to halt CPU after test (fall-through path)
        axi_driver.write_word(addr, 0x00100073)  # EBREAK
        addr += 4

        # For branch/jump instructions, also place EBREAK at target to prevent
        # fetching uninitialized memory if branch is taken
        opcode = self.instruction & 0x7F
        if opcode == 0b1100011:  # Branch instruction
            # Extract branch offset (12-bit signed immediate)
            imm_12 = (self.instruction >> 31) & 0x1
            imm_10_5 = (self.instruction >> 25) & 0x3F
            imm_4_1 = (self.instruction >> 8) & 0xF
            imm_11 = (self.instruction >> 7) & 0x1
            imm = (imm_12 << 12) | (imm_11 << 11) | (imm_10_5 << 5) | (imm_4_1 << 1)
            # Sign extend
            if imm & 0x1000:
                imm |= 0xFFFFE000
            target_addr = test_instr_addr + imm
            axi_driver.write_word(target_addr, 0x00100073)  # EBREAK at branch target
        elif opcode == 0b1101111:  # JAL instruction
            # Extract JAL offset (20-bit signed immediate)
            imm_20 = (self.instruction >> 31) & 0x1
            imm_10_1 = (self.instruction >> 21) & 0x3FF
            imm_11 = (self.instruction >> 20) & 0x1
            imm_19_12 = (self.instruction >> 12) & 0xFF
            imm = (imm_20 << 20) | (imm_19_12 << 12) | (imm_11 << 11) | (imm_10_1 << 1)
            # Sign extend
            if imm & 0x100000:
                imm |= 0xFFE00000
            target_addr = test_instr_addr + imm
            axi_driver.write_word(target_addr, 0x00100073)  # EBREAK at JAL target
        # Note: JALR target is computed at runtime, so we cannot pre-place EBREAK
        # JALR tests should ensure the target register points to valid code

        # Set PC to start of program
        await apb_driver.write_pc(0x0000)

        # Resume CPU - it will execute until EBREAK
        await apb_driver.resume_cpu()

        # Wait for execution to complete (EBREAK will halt the CPU)
        num_instructions = num_setup_instructions + 1 + 1  # setup + test + EBREAK
        dut = self.env.axi_agent.driver.dut
        await ClockCycles(dut.clk_i, num_instructions * 10)  # Give plenty of time

        # Verify setup registers were loaded correctly
        for reg_num, expected_val in self.setup_regs.items():
            actual_val = await apb_driver.read_gpr(reg_num)
            if actual_val != expected_val:
                raise AssertionError(
                    f"Setup register x{reg_num} mismatch: "
                    f"expected=0x{expected_val:08x}, actual=0x{actual_val:08x}"
                )

        # Verify result if specified
        if self.expected_rd is not None and self.expected_value is not None:
            actual_value = await apb_driver.read_gpr(self.expected_rd)
            if actual_value != self.expected_value:
                raise AssertionError(
                    f"Result x{self.expected_rd} mismatch: "
                    f"expected=0x{self.expected_value:08x}, "
                    f"actual=0x{actual_value:08x}"
                )


# =============================================================================
# Priority 1: Load/Store Instructions (Memory Operations)
# =============================================================================


class LWSequence(ISASequenceBase):
    """Test LW (Load Word) instruction."""

    def __init__(self, name, env, rd, rs1, offset, base_addr, mem_value, expected_value):
        """
        Test LW instruction.

        Args:
            rd: Destination register
            rs1: Base address register
            offset: Immediate offset
            base_addr: Value to load into rs1
            mem_value: Value to store at [base_addr + offset]
            expected_value: Expected value loaded into rd
        """
        instruction = LW(rd, rs1, offset)
        setup_regs = {rs1: base_addr} if rs1 != 0 else {}
        setup_memory = {base_addr + offset: mem_value}

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
            setup_memory=setup_memory,
        )


class SWSequence(ISASequenceBase):
    """Test SW (Store Word) instruction."""

    def __init__(self, name, env, rs1, rs2, offset, base_addr, store_value):
        """
        Test SW instruction.

        Args:
            rs1: Base address register
            rs2: Source data register
            offset: Immediate offset
            base_addr: Value to load into rs1
            store_value: Value to load into rs2 (to be stored)
        """
        instruction = SW(rs2, rs1, offset)
        setup_regs = {}
        # Only add registers to setup if they're not the zero register
        if rs1 != 0 and rs1 != "x0":
            setup_regs[rs1] = base_addr
        if rs2 != 0 and rs2 != "x0":
            setup_regs[rs2] = store_value

        self.target_addr = base_addr + offset
        self.store_value = store_value

        super().__init__(name, env, instruction, setup_regs=setup_regs)

    async def body(self):
        """Execute SW test and verify memory was written."""
        await super().body()

        # Verify memory was written correctly
        axi_driver = self.env.axi_agent.driver
        actual = axi_driver.read_word(self.target_addr)

        if actual != self.store_value:
            raise AssertionError(
                f"Memory at 0x{self.target_addr:08x} mismatch: "
                f"expected=0x{self.store_value:08x}, actual=0x{actual:08x}"
            )


class LBSequence(ISASequenceBase):
    """Test LB (Load Byte, sign-extended) instruction."""

    def __init__(self, name, env, rd, rs1, offset, base_addr, mem_value, expected_value):
        """Test LB instruction."""
        instruction = LB(rd, rs1, offset)
        setup_regs = {rs1: base_addr} if rs1 != 0 and rs1 != "x0" else {}

        # Compute effective address and place mem_value in correct byte lane
        addr = base_addr + offset
        aligned_addr = addr & ~0x3
        lane = addr & 0x3
        # Create 32-bit word with mem_value in correct byte lane
        word_value = (mem_value & 0xFF) << (lane * 8)
        setup_memory = {aligned_addr: word_value}

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
            setup_memory=setup_memory,
        )


class LBUSequence(ISASequenceBase):
    """Test LBU (Load Byte Unsigned) instruction."""

    def __init__(self, name, env, rd, rs1, offset, base_addr, mem_value, expected_value):
        """Test LBU instruction."""
        instruction = LBU(rd, rs1, offset)
        setup_regs = {rs1: base_addr} if rs1 != 0 and rs1 != "x0" else {}

        # Compute effective address and place mem_value in correct byte lane
        addr = base_addr + offset
        aligned_addr = addr & ~0x3
        lane = addr & 0x3
        # Create 32-bit word with mem_value in correct byte lane
        word_value = (mem_value & 0xFF) << (lane * 8)
        setup_memory = {aligned_addr: word_value}

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
            setup_memory=setup_memory,
        )


class LHSequence(ISASequenceBase):
    """Test LH (Load Halfword, sign-extended) instruction."""

    def __init__(self, name, env, rd, rs1, offset, base_addr, mem_value, expected_value):
        """Test LH instruction."""
        instruction = LH(rd, rs1, offset)
        setup_regs = {rs1: base_addr} if rs1 != 0 and rs1 != "x0" else {}

        # Compute effective address and place mem_value in correct halfword lane
        addr = base_addr + offset
        aligned_addr = addr & ~0x3
        lane = (addr & 0x2) >> 1  # 0 for lower halfword, 1 for upper halfword
        # Create 32-bit word with mem_value in correct halfword lane
        word_value = (mem_value & 0xFFFF) << (lane * 16)
        setup_memory = {aligned_addr: word_value}

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
            setup_memory=setup_memory,
        )


class LHUSequence(ISASequenceBase):
    """Test LHU (Load Halfword Unsigned) instruction."""

    def __init__(self, name, env, rd, rs1, offset, base_addr, mem_value, expected_value):
        """Test LHU instruction."""
        instruction = LHU(rd, rs1, offset)
        setup_regs = {rs1: base_addr} if rs1 != 0 and rs1 != "x0" else {}

        # Compute effective address and place mem_value in correct halfword lane
        addr = base_addr + offset
        aligned_addr = addr & ~0x3
        lane = (addr & 0x2) >> 1  # 0 for lower halfword, 1 for upper halfword
        # Create 32-bit word with mem_value in correct halfword lane
        word_value = (mem_value & 0xFFFF) << (lane * 16)
        setup_memory = {aligned_addr: word_value}

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
            setup_memory=setup_memory,
        )


class SBSequence(ISASequenceBase):
    """Test SB (Store Byte) instruction."""

    def __init__(self, name, env, rs1, rs2, offset, base_addr, store_value):
        """Test SB instruction."""
        instruction = SB(rs2, rs1, offset)
        setup_regs = {}
        # Only add registers to setup if they're not the zero register
        if rs1 != 0 and rs1 != "x0":
            setup_regs[rs1] = base_addr
        if rs2 != 0 and rs2 != "x0":
            setup_regs[rs2] = store_value

        self.target_addr = base_addr + offset
        self.store_value = store_value & 0xFF  # Only byte should be stored

        super().__init__(name, env, instruction, setup_regs=setup_regs)

    async def body(self):
        """Execute SB test and verify byte was written."""
        await super().body()

        # Verify memory byte was written correctly
        axi_driver = self.env.axi_agent.driver
        word = axi_driver.read_word(self.target_addr & 0xFFFFFFFC)
        byte_offset = self.target_addr & 0x3
        actual_byte = (word >> (byte_offset * 8)) & 0xFF

        if actual_byte != self.store_value:
            raise AssertionError(
                f"Byte at 0x{self.target_addr:08x} mismatch: "
                f"expected=0x{self.store_value:02x}, actual=0x{actual_byte:02x}"
            )


class SHSequence(ISASequenceBase):
    """Test SH (Store Halfword) instruction."""

    def __init__(self, name, env, rs1, rs2, offset, base_addr, store_value):
        """Test SH instruction."""
        instruction = SH(rs2, rs1, offset)
        setup_regs = {}
        # Only add registers to setup if they're not the zero register
        if rs1 != 0 and rs1 != "x0":
            setup_regs[rs1] = base_addr
        if rs2 != 0 and rs2 != "x0":
            setup_regs[rs2] = store_value

        self.target_addr = base_addr + offset
        self.store_value = store_value & 0xFFFF  # Only halfword should be stored

        super().__init__(name, env, instruction, setup_regs=setup_regs)

    async def body(self):
        """Execute SH test and verify halfword was written."""
        await super().body()

        # Verify memory halfword was written correctly
        axi_driver = self.env.axi_agent.driver
        word = axi_driver.read_word(self.target_addr & 0xFFFFFFFC)
        half_offset = (self.target_addr & 0x2) >> 1
        actual_half = (word >> (half_offset * 16)) & 0xFFFF

        if actual_half != self.store_value:
            raise AssertionError(
                f"Halfword at 0x{self.target_addr:08x} mismatch: "
                f"expected=0x{self.store_value:04x}, actual=0x{actual_half:04x}"
            )


# =============================================================================
# Priority 2: Arithmetic/Logical Instructions (R-type and I-type)
# =============================================================================


class ADDSequence(ISASequenceBase):
    """Test ADD (Add) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test ADD rd, rs1, rs2."""
        instruction = ADD(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val
        elif rs2 != 0:  # rs2 == rs1, use rs1_val
            pass

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SUBSequence(ISASequenceBase):
    """Test SUB (Subtract) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test SUB rd, rs1, rs2."""
        instruction = SUB(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class ANDSequence(ISASequenceBase):
    """Test AND (Bitwise AND) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test AND rd, rs1, rs2."""
        instruction = AND(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class ORSequence(ISASequenceBase):
    """Test OR (Bitwise OR) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test OR rd, rs1, rs2."""
        instruction = OR(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class XORSequence(ISASequenceBase):
    """Test XOR (Bitwise XOR) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test XOR rd, rs1, rs2."""
        instruction = XOR(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SLTSequence(ISASequenceBase):
    """Test SLT (Set Less Than, signed) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test SLT rd, rs1, rs2."""
        instruction = SLT(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SLTUSequence(ISASequenceBase):
    """Test SLTU (Set Less Than Unsigned) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test SLTU rd, rs1, rs2."""
        instruction = SLTU(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0 and rs2 != rs1:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class ADDISequence(ISASequenceBase):
    """Test ADDI (Add Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, imm, rs1_val, expected_value):
        """Test ADDI rd, rs1, imm."""
        instruction = ADDI(rd, rs1, imm)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SLTISequence(ISASequenceBase):
    """Test SLTI (Set Less Than Immediate, signed) instruction."""

    def __init__(self, name, env, rd, rs1, imm, rs1_val, expected_value):
        """Test SLTI rd, rs1, imm."""
        instruction = SLTI(rd, rs1, imm)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SLTIUSequence(ISASequenceBase):
    """Test SLTIU (Set Less Than Immediate Unsigned) instruction."""

    def __init__(self, name, env, rd, rs1, imm, rs1_val, expected_value):
        """Test SLTIU rd, rs1, imm."""
        instruction = SLTIU(rd, rs1, imm)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class ANDISequence(ISASequenceBase):
    """Test ANDI (AND Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, imm, rs1_val, expected_value):
        """Test ANDI rd, rs1, imm."""
        instruction = ANDI(rd, rs1, imm)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class ORISequence(ISASequenceBase):
    """Test ORI (OR Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, imm, rs1_val, expected_value):
        """Test ORI rd, rs1, imm."""
        instruction = ORI(rd, rs1, imm)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class XORISequence(ISASequenceBase):
    """Test XORI (XOR Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, imm, rs1_val, expected_value):
        """Test XORI rd, rs1, imm."""
        instruction = XORI(rd, rs1, imm)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


# =============================================================================
# Priority 3: Shift Instructions (R-type and I-type)
# =============================================================================


class SLLSequence(ISASequenceBase):
    """Test SLL (Shift Left Logical) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test SLL rd, rs1, rs2 (shift left by rs2[4:0])."""
        instruction = SLL(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SLLISequence(ISASequenceBase):
    """Test SLLI (Shift Left Logical Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, shamt, rs1_val, expected_value):
        """Test SLLI rd, rs1, shamt (shift left by immediate 0-31)."""
        instruction = SLLI(rd, rs1, shamt)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SRLSequence(ISASequenceBase):
    """Test SRL (Shift Right Logical) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test SRL rd, rs1, rs2 (logical right shift by rs2[4:0])."""
        instruction = SRL(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SRLISequence(ISASequenceBase):
    """Test SRLI (Shift Right Logical Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, shamt, rs1_val, expected_value):
        """Test SRLI rd, rs1, shamt (logical right shift by immediate 0-31)."""
        instruction = SRLI(rd, rs1, shamt)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SRASequence(ISASequenceBase):
    """Test SRA (Shift Right Arithmetic) instruction."""

    def __init__(self, name, env, rd, rs1, rs2, rs1_val, rs2_val, expected_value):
        """Test SRA rd, rs1, rs2 (arithmetic right shift by rs2[4:0])."""
        instruction = SRA(rd, rs1, rs2)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class SRAISequence(ISASequenceBase):
    """Test SRAI (Shift Right Arithmetic Immediate) instruction."""

    def __init__(self, name, env, rd, rs1, shamt, rs1_val, expected_value):
        """Test SRAI rd, rs1, shamt (arithmetic right shift by immediate 0-31)."""
        instruction = SRAI(rd, rs1, shamt)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


# =============================================================================
# Priority 4: Branch Instructions (B-type)
# =============================================================================


class BEQSequence(ISASequenceBase):
    """Test BEQ (Branch if Equal) instruction."""

    def __init__(
        self,
        name,
        env,
        rs1,
        rs2,
        rs1_val,
        rs2_val,
        branch_target_offset=8,
        expect_branch_taken=True,
    ):
        """
        Test BEQ rs1, rs2, offset.

        Args:
            branch_target_offset: Byte offset to branch target (must be even, sign-extended 13-bit)
            expect_branch_taken: True if branch should be taken
        """
        instruction = BEQ(rs1, rs2, branch_target_offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        # For branch instructions, we don't check rd, we check PC behavior
        # This will be validated by the scoreboard tracking execution flow
        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=None,  # Branches don't write to rd
            expected_value=None,
        )
        self.expect_branch_taken = expect_branch_taken


class BNESequence(ISASequenceBase):
    """Test BNE (Branch if Not Equal) instruction."""

    def __init__(
        self,
        name,
        env,
        rs1,
        rs2,
        rs1_val,
        rs2_val,
        branch_target_offset=8,
        expect_branch_taken=True,
    ):
        """Test BNE rs1, rs2, offset."""
        instruction = BNE(rs1, rs2, branch_target_offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name, env, instruction, setup_regs=setup_regs, expected_rd=None, expected_value=None
        )
        self.expect_branch_taken = expect_branch_taken


class BLTSequence(ISASequenceBase):
    """Test BLT (Branch if Less Than, signed) instruction."""

    def __init__(
        self,
        name,
        env,
        rs1,
        rs2,
        rs1_val,
        rs2_val,
        branch_target_offset=8,
        expect_branch_taken=True,
    ):
        """Test BLT rs1, rs2, offset (signed comparison)."""
        instruction = BLT(rs1, rs2, branch_target_offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name, env, instruction, setup_regs=setup_regs, expected_rd=None, expected_value=None
        )
        self.expect_branch_taken = expect_branch_taken


class BGESequence(ISASequenceBase):
    """Test BGE (Branch if Greater or Equal, signed) instruction."""

    def __init__(
        self,
        name,
        env,
        rs1,
        rs2,
        rs1_val,
        rs2_val,
        branch_target_offset=8,
        expect_branch_taken=True,
    ):
        """Test BGE rs1, rs2, offset (signed comparison)."""
        instruction = BGE(rs1, rs2, branch_target_offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name, env, instruction, setup_regs=setup_regs, expected_rd=None, expected_value=None
        )
        self.expect_branch_taken = expect_branch_taken


class BLTUSequence(ISASequenceBase):
    """Test BLTU (Branch if Less Than, unsigned) instruction."""

    def __init__(
        self,
        name,
        env,
        rs1,
        rs2,
        rs1_val,
        rs2_val,
        branch_target_offset=8,
        expect_branch_taken=True,
    ):
        """Test BLTU rs1, rs2, offset (unsigned comparison)."""
        instruction = BLTU(rs1, rs2, branch_target_offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name, env, instruction, setup_regs=setup_regs, expected_rd=None, expected_value=None
        )
        self.expect_branch_taken = expect_branch_taken


class BGEUSequence(ISASequenceBase):
    """Test BGEU (Branch if Greater or Equal, unsigned) instruction."""

    def __init__(
        self,
        name,
        env,
        rs1,
        rs2,
        rs1_val,
        rs2_val,
        branch_target_offset=8,
        expect_branch_taken=True,
    ):
        """Test BGEU rs1, rs2, offset (unsigned comparison)."""
        instruction = BGEU(rs1, rs2, branch_target_offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val
        if rs2 != 0:
            setup_regs[rs2] = rs2_val

        super().__init__(
            name, env, instruction, setup_regs=setup_regs, expected_rd=None, expected_value=None
        )
        self.expect_branch_taken = expect_branch_taken


# =============================================================================
# Priority 5: Jump Instructions (J-type and I-type)
# =============================================================================


class JALSequence(ISASequenceBase):
    """Test JAL (Jump and Link) instruction."""

    def __init__(self, name, env, rd, jump_offset, expected_return_addr):
        """
        Test JAL rd, offset.

        Args:
            rd: Destination register for return address (PC+4)
            jump_offset: Signed 21-bit offset (byte offset, must be even)
            expected_return_addr: Expected value in rd (PC of JAL instruction + 4)
        """
        instruction = JAL(rd, jump_offset)
        setup_regs = {}  # JAL doesn't need register setup

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_return_addr,
        )


class JALRSequence(ISASequenceBase):
    """Test JALR (Jump and Link Register) instruction."""

    def __init__(self, name, env, rd, rs1, offset, rs1_val, expected_return_addr):
        """
        Test JALR rd, rs1, offset.

        Args:
            rd: Destination register for return address (PC+4)
            rs1: Base register for jump target
            offset: Signed 12-bit offset added to rs1
            rs1_val: Value in rs1 (base address)
            expected_return_addr: Expected value in rd (PC of JALR instruction + 4)
        """
        instruction = JALR(rd, rs1, offset)
        setup_regs = {}
        if rs1 != 0:
            setup_regs[rs1] = rs1_val

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_return_addr,
        )


# =============================================================================
# Priority 6: Upper Immediate Instructions (U-type)
# =============================================================================


class LUISequence(ISASequenceBase):
    """Test LUI (Load Upper Immediate) instruction."""

    def __init__(self, name, env, rd, imm20, expected_value):
        """
        Test LUI rd, imm20.

        Loads upper 20 bits with imm20, lower 12 bits set to 0.
        Expected value = imm20 << 12
        """
        instruction = LUI(rd, imm20)
        setup_regs = {}  # LUI doesn't need register setup

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


class AUIPCSequence(ISASequenceBase):
    """Test AUIPC (Add Upper Immediate to PC) instruction."""

    def __init__(self, name, env, rd, imm20, pc_at_auipc, expected_value):
        """
        Test AUIPC rd, imm20.

        Adds upper 20 bits (imm20 << 12) to PC.
        Expected value = PC + (imm20 << 12)

        Args:
            pc_at_auipc: PC value when AUIPC executes (usually the instruction address)
            expected_value: pc_at_auipc + (imm20 << 12)
        """
        instruction = AUIPC(rd, imm20)
        setup_regs = {}  # AUIPC doesn't need register setup

        super().__init__(
            name,
            env,
            instruction,
            setup_regs=setup_regs,
            expected_rd=rd,
            expected_value=expected_value,
        )


# =============================================================================
# Instruction List for Test Generation
# =============================================================================

# Priority 1: Load/Store instructions
ISA_LOAD_STORE_SEQUENCES = {
    "LW": LWSequence,
    "SW": SWSequence,
    "LB": LBSequence,
    "LBU": LBUSequence,
    "LH": LHSequence,
    "LHU": LHUSequence,
    "SB": SBSequence,
    "SH": SHSequence,
}

# Priority 2: Arithmetic/Logical instructions
ISA_ARITH_LOGIC_SEQUENCES = {
    # R-type arithmetic
    "ADD": ADDSequence,
    "SUB": SUBSequence,
    "SLT": SLTSequence,
    "SLTU": SLTUSequence,
    # R-type logical
    "AND": ANDSequence,
    "OR": ORSequence,
    "XOR": XORSequence,
    # I-type arithmetic
    "ADDI": ADDISequence,
    "SLTI": SLTISequence,
    "SLTIU": SLTIUSequence,
    # I-type logical
    "ANDI": ANDISequence,
    "ORI": ORISequence,
    "XORI": XORISequence,
}

# Priority 3: Shift instructions
ISA_SHIFT_SEQUENCES = {
    # R-type shifts
    "SLL": SLLSequence,
    "SRL": SRLSequence,
    "SRA": SRASequence,
    # I-type shifts
    "SLLI": SLLISequence,
    "SRLI": SRLISequence,
    "SRAI": SRAISequence,
}

# Priority 4: Branch instructions
ISA_BRANCH_SEQUENCES = {
    "BEQ": BEQSequence,
    "BNE": BNESequence,
    "BLT": BLTSequence,
    "BGE": BGESequence,
    "BLTU": BLTUSequence,
    "BGEU": BGEUSequence,
}

# Priority 5: Jump instructions
ISA_JUMP_SEQUENCES = {
    "JAL": JALSequence,
    "JALR": JALRSequence,
}

# Priority 6: Upper immediate instructions
ISA_UPPER_IMM_SEQUENCES = {
    "LUI": LUISequence,
    "AUIPC": AUIPCSequence,
}
