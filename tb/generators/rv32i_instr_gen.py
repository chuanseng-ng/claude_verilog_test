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
    data_mem_size = 0xF000   # 60KB data memory

    # Instruction weighting (Phase 1: only ALU + upper immediate)
    # Phase 2 adds loads/stores, Phase 3 adds branches/jumps
    instruction_classes = {
        'r_type': 1.0,      # R-type ALU
        'i_type_alu': 1.0,  # I-type arithmetic
        'upper': 0.3,       # LUI/AUIPC
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
        if instr_class == 'r_type':
            return self._generate_r_type()
        elif instr_class == 'i_type_alu':
            return self._generate_i_type_alu()
        elif instr_class == 'upper':
            return self._generate_upper()
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
            ('ADD', enc.ADD), ('SUB', enc.SUB),
            ('AND', enc.AND), ('OR', enc.OR), ('XOR', enc.XOR),
            ('SLT', enc.SLT), ('SLTU', enc.SLTU),
            ('SLL', enc.SLL), ('SRL', enc.SRL), ('SRA', enc.SRA)
        ]
        name, encoder_func = self.rng.choice(opcodes)

        rd = self._random_dest_reg()
        rs1 = self._random_source_reg()
        rs2 = self._random_source_reg()

        return encoder_func(rd, rs1, rs2)

    def _generate_i_type_alu(self):
        """Generate random I-type arithmetic instruction."""
        opcodes = [
            ('ADDI', enc.ADDI, self._random_imm12),
            ('SLTI', enc.SLTI, self._random_imm12),
            ('SLTIU', enc.SLTIU, self._random_imm12),
            ('XORI', enc.XORI, self._random_imm12),
            ('ORI', enc.ORI, self._random_imm12),
            ('ANDI', enc.ANDI, self._random_imm12),
            ('SLLI', enc.SLLI, self._random_shamt),
            ('SRLI', enc.SRLI, self._random_shamt),
            ('SRAI', enc.SRAI, self._random_shamt),
        ]
        name, encoder_func, imm_generator = self.rng.choice(opcodes)

        rd = self._random_dest_reg()
        rs1 = self._random_source_reg()
        imm = imm_generator()

        return encoder_func(rd, rs1, imm)

    def _generate_upper(self):
        """Generate random upper immediate instruction (LUI/AUIPC)."""
        opcodes = [
            ('LUI', enc.LUI),
            ('AUIPC', enc.AUIPC),
        ]
        name, encoder_func = self.rng.choice(opcodes)

        rd = self._random_dest_reg()
        imm20 = self._random_imm20()

        return encoder_func(rd, imm20)


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
