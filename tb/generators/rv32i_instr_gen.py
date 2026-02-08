#!/usr/bin/env python3
"""
Random instruction generator for RV32I compliance testing.
Generates constrained random instruction sequences for stress testing.
"""

import random
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sim import riscv_encoder as enc


class GeneratorConfig:
    """Configuration for instruction generation constraints."""

    # Memory layout
    instr_mem_base = 0x00000000
    instr_mem_size = 0x1000  # 4KB instruction memory
    data_mem_base = 0x00001000
    data_mem_size = 0xF000  # 60KB data memory

    # Instruction weighting (Phase 1: only ALU + upper immediate)
    # Phase 2 adds loads/stores, Phase 3 adds branches/jumps
    instruction_classes = {
        "r_type": 1.0,  # R-type ALU
        "i_type_alu": 1.0,  # I-type arithmetic
        "upper": 0.3,  # LUI/AUIPC
        # Phase 2+: 'load': 0.5, 'store': 0.5
        # Phase 3+: 'branch': 0.2, 'jump': 0.1
    }

    # Register constraints
    allow_x0_as_dest = False  # Exclude x0 as destination (writes are no-ops)
    register_pool = list(range(1, 32))  # x1-x31 for destinations

    # Immediate ranges
    imm12_min = -2048
    imm12_max = 2047
    imm20_min = 0
    imm20_max = 0xFFFFF  # 20-bit unsigned
    shamt_max = 31  # 5-bit shift amount

    # Instruction-level biases (for fine-tuned stress testing)
    shift_bias = 1.0  # Multiplier for shift instruction weight in I-type ALU (default: no bias)


class StressTestConfig:
    """Configuration profiles for stress testing.

    Provides predefined instruction distribution profiles for corner case testing.
    Phase 1 constraint: Limited to ALU-only instructions (21/37 RV32I).

    Usage:
        config = GeneratorConfig()
        config.instruction_classes = StressTestConfig.alu_intensive()
        gen = RV32IInstructionGenerator(seed=42, config=config)
    """

    @staticmethod
    def alu_intensive():
        """90% ALU operations (register pressure test).

        Tests heavy register usage and ALU datapath.
        Useful for: Register file stress, ALU verification, bypass logic.

        Returns:
            Dict of instruction class weights (sum to 10.0 for easy percentage)
        """
        return {
            "r_type": 5.0,  # 50% (ADD, SUB, AND, OR, XOR, SLT, SLTU, SLL, SRL, SRA)
            "i_type_alu": 4.0,  # 40% (ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI)
            "upper": 1.0,  # 10% (LUI, AUIPC)
        }

    @staticmethod
    def jump_heavy():
        """40% jump instructions (function call simulation).

        Tests control flow changes and PC management.
        Useful for: JAL/JALR verification, return address stack, branch prediction.

        Note: Phase 1 only supports JAL/JALR (no branches yet).

        Returns:
            Dict of instruction class weights
        """
        return {
            "jump": 4.0,  # 40% (JAL, JALR)
            "r_type": 2.5,  # 25% R-type
            "i_type_alu": 2.5,  # 25% I-type ALU
            "upper": 1.0,  # 10% Upper immediate
        }

    @staticmethod
    def shift_intensive():
        """Heavy shift operations (corner case testing).

        Tests shift unit with various shift amounts.
        Useful for: Shift logic verification, barrel shifter stress.

        Returns:
            Dict of instruction class weights plus shift_bias config override
        """
        return {
            "i_type_alu": 6.0,  # 60% I-type ALU (shift-biased via _shift_bias)
            "r_type": 3.0,  # 30% R-type (includes SLL, SRL, SRA)
            "upper": 1.0,  # 10% Upper immediate
            "_shift_bias": 3.0,  # Bias I-type ALU generation toward shift ops (3x weight)
        }

    @staticmethod
    def immediate_heavy():
        """Heavy immediate value operations.

        Tests immediate generation and sign extension logic.
        Useful for: Immediate generator verification, constant propagation.

        Returns:
            Dict of instruction class weights
        """
        return {
            "i_type_alu": 5.0,  # 50% I-type ALU
            "upper": 4.0,  # 40% Upper immediate (LUI, AUIPC)
            "r_type": 1.0,  # 10% R-type
        }


class RV32IInstructionGenerator:
    """
    Random instruction generator for RV32I.

    Features:
    - Seeded random generation (reproducible)
    - Constraint-based operand generation
    - Configurable instruction distribution
    - EBREAK termination for clean program exit
    """

    def __init__(self, seed=None, config=None):
        """
        Initialize generator.

        Args:
            seed: Random seed (int) for reproducibility
            config: GeneratorConfig instance (uses default if None)
        """
        self.seed = seed if seed is not None else random.randint(0, 1000000)
        self.rng = random.Random(self.seed)
        self.config = config if config is not None else GeneratorConfig()

        # Track current address during generation
        self.current_addr = self.config.instr_mem_base

        # Precompute register initialization values (deterministic from seed)
        self.init_regs = self._compute_init_regs()

    def _compute_init_regs(self):
        """
        Compute initial register values for this test.
        Provides valid base addresses for loads/stores and non-zero values for ALU.

        Returns:
            Dict {reg_num: value} for x1-x31
        """
        init = {}
        for reg in range(1, 32):
            if reg == 2:  # x2 (sp - stack pointer convention)
                init[reg] = self.config.data_mem_base + 0x1000
            elif reg == 3:  # x3 (gp - global pointer convention)
                init[reg] = self.config.data_mem_base + 0x100
            else:
                # Small pseudo-random values (deterministic from seed)
                init[reg] = (reg * 0x100 + self.seed) & 0xFFFF
        return init

    def get_register_init_values(self):
        """Get initial register values for this test."""
        return self.init_regs.copy()

    def generate_program(self, num_instructions=100):
        """
        Generate a complete random instruction sequence.

        Args:
            num_instructions: Number of instructions to generate (excluding EBREAK)

        Returns:
            List of (address, instruction_word) tuples
        """
        program = []
        self.current_addr = self.config.instr_mem_base

        # Generate N-1 random instructions
        for i in range(num_instructions - 1):
            insn = self._generate_instruction()
            program.append((self.current_addr, insn))
            self.current_addr += 4

        # Add EBREAK as final instruction (triggers CPU halt)
        # EBREAK encoding: 0x00100073
        program.append((self.current_addr, 0x00100073))

        return program

    def _generate_instruction(self):
        """
        Generate a single random instruction.

        Returns:
            32-bit instruction word
        """
        # Select instruction class based on weights
        classes = list(self.config.instruction_classes.keys())
        weights = [self.config.instruction_classes[c] for c in classes]
        instr_class = self.rng.choices(classes, weights=weights)[0]

        # Generate instruction based on class
        if instr_class == "r_type":
            return self._generate_r_type()
        elif instr_class == "i_type_alu":
            return self._generate_i_type_alu()
        elif instr_class == "upper":
            return self._generate_upper()
        elif instr_class == "jump":
            return self._generate_jump()
        else:
            raise ValueError(f"Unknown instruction class: {instr_class}")

    def _random_dest_reg(self):
        """Select random destination register (x1-x31)."""
        return self.rng.choice(self.config.register_pool)

    def _random_source_reg(self):
        """Select random source register (x0-x31)."""
        return self.rng.randint(0, 31)

    def _random_imm12(self):
        """Generate random 12-bit signed immediate."""
        return self.rng.randint(self.config.imm12_min, self.config.imm12_max)

    def _random_imm20(self):
        """Generate random 20-bit immediate."""
        return self.rng.randint(self.config.imm20_min, self.config.imm20_max)

    def _random_shamt(self):
        """Generate random shift amount (0-31)."""
        return self.rng.randint(0, self.config.shamt_max)

    def _generate_r_type(self):
        """Generate random R-type instruction."""
        opcodes = [
            ("ADD", enc.ADD),
            ("SUB", enc.SUB),
            ("AND", enc.AND),
            ("OR", enc.OR),
            ("XOR", enc.XOR),
            ("SLT", enc.SLT),
            ("SLTU", enc.SLTU),
            ("SLL", enc.SLL),
            ("SRL", enc.SRL),
            ("SRA", enc.SRA),
        ]
        name, encoder_func = self.rng.choice(opcodes)

        rd = self._random_dest_reg()
        rs1 = self._random_source_reg()
        rs2 = self._random_source_reg()

        return encoder_func(rd, rs1, rs2)

    def _generate_i_type_alu(self):
        """Generate random I-type arithmetic instruction with optional shift bias."""
        # Define shift and non-shift opcodes separately
        shift_ops = [
            ("SLLI", enc.SLLI, self._random_shamt),
            ("SRLI", enc.SRLI, self._random_shamt),
            ("SRAI", enc.SRAI, self._random_shamt),
        ]
        non_shift_ops = [
            ("ADDI", enc.ADDI, self._random_imm12),
            ("SLTI", enc.SLTI, self._random_imm12),
            ("SLTIU", enc.SLTIU, self._random_imm12),
            ("XORI", enc.XORI, self._random_imm12),
            ("ORI", enc.ORI, self._random_imm12),
            ("ANDI", enc.ANDI, self._random_imm12),
        ]

        # Apply shift bias if configured (default 1.0 = no bias)
        shift_bias = getattr(self.config, "shift_bias", 1.0)

        # Create weighted opcode list
        opcodes = shift_ops + non_shift_ops
        weights = [shift_bias] * len(shift_ops) + [1.0] * len(non_shift_ops)

        # Select opcode using weighted random choice
        name, encoder_func, imm_generator = self.rng.choices(opcodes, weights=weights)[0]

        rd = self._random_dest_reg()
        rs1 = self._random_source_reg()
        imm = imm_generator()

        return encoder_func(rd, rs1, imm)

    def _generate_upper(self):
        """Generate random upper immediate instruction (LUI/AUIPC)."""
        opcodes = [
            ("LUI", enc.LUI),
            ("AUIPC", enc.AUIPC),
        ]
        name, encoder_func = self.rng.choice(opcodes)

        rd = self._random_dest_reg()
        imm20 = self._random_imm20()

        return encoder_func(rd, imm20)

    def _generate_jump(self):
        """Generate random jump instruction (JAL/JALR).

        Note: Jump offsets are constrained to stay within instruction memory bounds.
        Phase 1: JALR uses x0 as base (rs1=0) to ensure safe absolute addressing.
        """
        opcodes = [
            ("JAL", enc.JAL, self._random_jump_offset),
            ("JALR", enc.JALR, self._random_jalr_offset),
        ]
        name, encoder_func, imm_generator = self.rng.choice(opcodes)

        rd = self._random_dest_reg()

        if name == "JAL":
            # JAL: rd, offset (PC-relative)
            imm = imm_generator()
            return encoder_func(rd, imm)
        else:  # JALR
            # JALR: rd, x0, offset (base address + offset)
            # Use x0 as base to ensure JALR target = 0 + imm12 stays in instruction memory
            rs1 = 0  # x0 (always 0) for safe absolute addressing
            imm = imm_generator()
            return encoder_func(rd, rs1, imm)

    def _random_jalr_offset(self):
        """Generate random JALR offset constrained to instruction memory.

        Since JALR uses x0 (value=0) as base, offset directly specifies target address.
        Target must be within [instr_mem_base, instr_mem_base + instr_mem_size - 4].

        Returns:
            12-bit signed immediate that results in valid instruction memory address
        """
        # JALR target = rs1 + imm12 = 0 + imm12 (since rs1=x0=0)
        # Valid range: [instr_mem_base, instr_mem_base + instr_mem_size - 4]
        min_target = self.config.instr_mem_base
        max_target = self.config.instr_mem_base + self.config.instr_mem_size - 4

        # Clamp to 12-bit signed immediate range [-2048, 2047]
        min_imm = max(min_target, self.config.imm12_min)
        max_imm = min(max_target, self.config.imm12_max)

        # Generate random offset within valid range
        offset = self.rng.randint(min_imm, max_imm)

        # Align to 4-byte instruction boundary
        offset = (offset // 4) * 4

        return offset

    def _random_jump_offset(self):
        """Generate random jump offset (20-bit signed, 2-byte aligned).

        JAL immediate is 21 bits (sign-extended, bit 0 is always 0).
        Ensures target PC = current_addr + offset stays within instruction memory.
        Ensures offset is never 0 to avoid JAL self-loops.
        """
        # Calculate valid offset range to stay within instruction memory
        min_target = self.config.instr_mem_base
        max_target = self.config.instr_mem_base + self.config.instr_mem_size - 4

        # Calculate offset range from current address
        min_offset = min_target - self.current_addr
        max_offset = max_target - self.current_addr

        # Clamp to ±1KB for Phase 1 testing (avoid extremely large jumps)
        test_max = 1024
        min_offset = max(min_offset, -test_max)
        max_offset = min(max_offset, test_max)

        # Generate random offset
        offset = self.rng.randint(min_offset, max_offset)

        # Align to instruction boundary (4 bytes)
        offset = (offset // 4) * 4

        # Ensure offset is non-zero to avoid self-loops
        if offset == 0:
            # Try to pick a non-zero offset that's still valid
            if max_offset >= 4:
                offset = 4  # Jump forward
            elif min_offset <= -4:
                offset = -4  # Jump backward
            else:
                # If we can't avoid zero (shouldn't happen with 4KB mem), use +4 anyway
                offset = 4

        return offset


# Test harness
if __name__ == "__main__":
    print("RV32I Random Instruction Generator Test")
    print("=" * 70)

    # Test with deterministic seed
    gen = RV32IInstructionGenerator(seed=42)

    print(f"\nTest seed: {gen.seed}")
    print("\nInitial register values:")
    for reg, val in gen.get_register_init_values().items():
        print(f"  x{reg:2d} = 0x{val:08x}")

    print("\nGenerating 10 random instructions:")
    print("=" * 70)
    program = gen.generate_program(10)

    for addr, insn in program:
        print(f"0x{addr:08x}: 0x{insn:08x}")

    # Verify reproducibility
    print("\n" + "=" * 70)
    print("Verifying reproducibility (same seed should generate same program)...")
    gen2 = RV32IInstructionGenerator(seed=42)
    program2 = gen2.generate_program(10)

    if program == program2:
        print("PASS: Programs match (generator is deterministic)")
    else:
        print("FAIL: Programs differ (generator is non-deterministic)")
        for i, ((addr1, insn1), (addr2, insn2)) in enumerate(zip(program, program2)):
            if insn1 != insn2:
                print(f"  Mismatch at index {i}: 0x{insn1:08x} != 0x{insn2:08x}")
