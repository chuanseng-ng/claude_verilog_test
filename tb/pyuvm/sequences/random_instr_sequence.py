"""Random Instruction Sequence for pyuvm CPU tests.

This module implements a sequence that generates and executes random
instruction programs using the RV32I instruction generator.

Features:
- Integration with RV32IInstructionGenerator
- Program loading via AXI memory
- Register initialization via APB debug
- Configurable instruction count
- Seeded random generation (reproducible tests)
"""

import sys
from pathlib import Path

# Add project root to path for generator import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.generators.rv32i_instr_gen import RV32IInstructionGenerator
from .base_sequence import BaseSequence


class RandomInstructionSequence(BaseSequence):
    """Sequence that generates and executes random RV32I instructions.

    This sequence performs the following steps:
    1. Generate random instruction program (using RV32IInstructionGenerator)
    2. Load program into instruction memory (via AXI agent)
    3. Initialize CPU registers (via APB agent)
    4. Start CPU execution
    5. Wait for completion (EBREAK halts CPU)

    The sequence is seeded for reproducibility - same seed produces
    same instruction sequence.

    Configuration:
    - num_instructions: Number of instructions to generate (default: 100)
    - seed: Random seed for reproducibility (default: random)
    - env: CPU environment reference (for accessing agents)

    Usage:
        seq = RandomInstructionSequence("random_test")
        seq.num_instructions = 1000
        seq.seed = 42
        seq.env = cpu_env
        await seq.body()

    Attributes:
        num_instructions: Number of instructions to generate
        seed: Random seed
        env: Reference to CPUEnvironment (for agent access)
        generator: RV32IInstructionGenerator instance
    """

    def __init__(self, name, num_instructions=100, seed=None):
        """Initialize random instruction sequence.

        Args:
            name: Sequence name
            num_instructions: Number of instructions to generate (default: 100)
            seed: Random seed for reproducibility (None = random)
        """
        super().__init__(name)
        self.num_instructions = num_instructions
        self.seed = seed
        self.env = None  # Set by test before running
        self.generator = None  # Created in pre_body

    async def pre_body(self):
        """Pre-body phase - generate instruction program.

        This phase:
        1. Creates instruction generator with seed
        2. Generates random instruction program
        3. Computes initial register values
        """
        await super().pre_body()

        # Validate environment reference
        if self.env is None:
            raise RuntimeError(
                "RandomInstructionSequence requires env to be set before running"
            )

        # Create instruction generator
        self.generator = RV32IInstructionGenerator(seed=self.seed)

        # Log test info
        print(f"\n{'='*60}")
        print("Random Instruction Test")
        print(f"{'='*60}")
        print(f"Seed: {self.generator.seed}")
        print(f"Instructions: {self.num_instructions}")
        print(f"{'='*60}\n")

    async def body(self):
        """Body phase - load program and execute.

        This phase:
        1. Generates random instructions
        2. Loads program into memory via AXI
        3. Initializes registers via APB
        4. Starts CPU execution
        5. Waits for completion
        """
        # Step 1: Generate random instruction program
        print(f"Generating {self.num_instructions} random instructions...")
        program = self.generator.generate_program(self.num_instructions)
        print(f"Generated {len(program)} instructions (including EBREAK)")

        # Step 2: Load program into memory via AXI driver
        print("Loading program into instruction memory...")
        axi_driver = self.env.axi_agent.driver
        for addr, insn in program:
            axi_driver.write_word(addr, insn)
        print(f"Loaded {len(program)} instructions")

        # Step 3: Initialize registers via APB debug
        print("Initializing CPU registers...")
        apb_driver = self.env.apb_agent.driver
        init_regs = self.generator.get_register_init_values()

        # Halt CPU before modifying registers
        await apb_driver.halt_cpu()

        # Initialize all registers (x1-x31, x0 is hardwired to 0)
        for reg_num, value in init_regs.items():
            await apb_driver.write_gpr(reg_num, value)

        # Set PC to start of program
        await apb_driver.write_pc(0x00000000)

        print(f"Initialized {len(init_regs)} registers")

        # Step 4: Resume CPU execution
        print("Starting CPU execution...")
        await apb_driver.resume_cpu()

        # Step 5: Wait for completion
        # The scoreboard will validate each commit against the reference model
        # The test will handle waiting for EBREAK and final validation
        print("CPU executing (scoreboard will validate commits)...")

    async def post_body(self):
        """Post-body phase - cleanup.

        Note: Actual completion checking is done by the test class,
        as it needs to wait for the scoreboard to finish validation.
        """
        await super().post_body()
        print("Random instruction sequence complete")
