"""Directed Test Sequences for pyuvm CPU tests.

This module implements directed test sequences that verify specific
instruction behaviors with known inputs and expected outputs.

Features:
- Smoke test sequences (ADDI, branches, jumps)
- Predictable instruction patterns
- Targeted functionality testing
- Based on legacy test_smoke.py patterns
"""

import sys
from pathlib import Path

# Add project root to path for encoder import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sim import riscv_encoder as enc
from .base_sequence import BaseSequence


class SimpleADDISequence(BaseSequence):
    """Simple ADDI test sequence.

    Tests:
    - ADDI x1, x0, 42  (x1 = 42)
    - ADDI x2, x1, 8   (x2 = 50)
    - EBREAK          (halt CPU)

    Expected results:
    - x1 = 42
    - x2 = 50
    - PC progresses through all instructions
    """

    def __init__(self, name="simple_addi"):
        """Initialize simple ADDI sequence."""
        super().__init__(name)
        self.env = None  # Set by test

    async def body(self):
        """Load and execute ADDI program."""
        print("\n" + "="*60)
        print("Simple ADDI Test")
        print("="*60)

        # Build program
        program = [
            (0x00000000, enc.ADDI(1, 0, 42)),   # x1 = 0 + 42 = 42
            (0x00000004, enc.ADDI(2, 1, 8)),    # x2 = 42 + 8 = 50
            (0x00000008, 0x00100073),           # EBREAK
        ]

        # Load program
        axi_driver = self.env.axi_agent.driver
        for addr, insn in program:
            axi_driver.write_word(addr, insn)
        print("Loaded 3-instruction program")

        # Initialize APB driver and start execution
        apb_driver = self.env.apb_agent.driver
        await apb_driver.halt_cpu()
        await apb_driver.write_pc(0x00000000)
        print("Starting CPU execution...")
        await apb_driver.resume_cpu()


class BranchNotTakenSequence(BaseSequence):
    """Branch not taken test sequence.

    Tests:
    - ADDI x1, x0, 10  (x1 = 10)
    - ADDI x2, x0, 20  (x2 = 20)
    - BEQ x1, x2, +8   (branch NOT taken, x1 != x2)
    - ADDI x3, x0, 1   (x3 = 1, this executes)
    - EBREAK
    - [branch target]: ADDI x3, x0, 2  (x3 = 2, this SHOULD NOT execute)

    Expected results:
    - x1 = 10
    - x2 = 20
    - x3 = 1 (NOT 2, branch not taken)
    """

    def __init__(self, name="branch_not_taken"):
        """Initialize branch not taken sequence."""
        super().__init__(name)
        self.env = None

    async def body(self):
        """Load and execute branch not taken program."""
        print("\n" + "="*60)
        print("Branch Not Taken Test")
        print("="*60)

        # Build program
        program = [
            (0x00000000, enc.ADDI(1, 0, 10)),      # x1 = 10
            (0x00000004, enc.ADDI(2, 0, 20)),      # x2 = 20
            (0x00000008, enc.BEQ(1, 2, 8)),        # if x1 == x2: pc += 8 (NOT taken)
            (0x0000000C, enc.ADDI(3, 0, 1)),       # x3 = 1 (executed)
            (0x00000010, 0x00100073),              # EBREAK
            (0x00000014, enc.ADDI(3, 0, 2)),       # x3 = 2 (NOT executed)
        ]

        # Load program
        axi_driver = self.env.axi_agent.driver
        for addr, insn in program:
            axi_driver.write_word(addr, insn)
        print("Loaded 6-instruction program")

        # Start execution
        apb_driver = self.env.apb_agent.driver
        await apb_driver.halt_cpu()
        await apb_driver.write_pc(0x00000000)
        print("Starting CPU execution...")
        await apb_driver.resume_cpu()


class BranchTakenSequence(BaseSequence):
    """Branch taken test sequence.

    Tests:
    - ADDI x1, x0, 10  (x1 = 10)
    - ADDI x2, x0, 10  (x2 = 10)
    - BEQ x1, x2, +8   (branch TAKEN, x1 == x2)
    - ADDI x3, x0, 1   (x3 = 1, this SHOULD NOT execute)
    - [branch target]: ADDI x3, x0, 2  (x3 = 2, this executes)
    - EBREAK

    Expected results:
    - x1 = 10
    - x2 = 10
    - x3 = 2 (NOT 1, branch taken)
    """

    def __init__(self, name="branch_taken"):
        """Initialize branch taken sequence."""
        super().__init__(name)
        self.env = None

    async def body(self):
        """Load and execute branch taken program."""
        print("\n" + "="*60)
        print("Branch Taken Test")
        print("="*60)

        # Build program
        program = [
            (0x00000000, enc.ADDI(1, 0, 10)),      # x1 = 10
            (0x00000004, enc.ADDI(2, 0, 10)),      # x2 = 10
            (0x00000008, enc.BEQ(1, 2, 8)),        # if x1 == x2: pc += 8 (TAKEN)
            (0x0000000C, enc.ADDI(3, 0, 1)),       # x3 = 1 (NOT executed)
            (0x00000010, enc.ADDI(3, 0, 2)),       # x3 = 2 (executed)
            (0x00000014, 0x00100073),              # EBREAK
        ]

        # Load program
        axi_driver = self.env.axi_agent.driver
        for addr, insn in program:
            axi_driver.write_word(addr, insn)
        print("Loaded 6-instruction program")

        # Start execution
        apb_driver = self.env.apb_agent.driver
        await apb_driver.halt_cpu()
        await apb_driver.write_pc(0x00000000)
        print("Starting CPU execution...")
        await apb_driver.resume_cpu()


class JALSequence(BaseSequence):
    """JAL (Jump and Link) test sequence.

    Tests:
    - JAL x1, +8       (jump to +8, x1 = return address)
    - ADDI x2, x0, 1   (x2 = 1, SHOULD NOT execute)
    - [jump target]: ADDI x2, x0, 2  (x2 = 2, this executes)
    - EBREAK

    Expected results:
    - x1 = 0x4 (return address = PC + 4)
    - x2 = 2 (NOT 1, jumped over first ADDI)
    """

    def __init__(self, name="jal"):
        """Initialize JAL sequence."""
        super().__init__(name)
        self.env = None

    async def body(self):
        """Load and execute JAL program."""
        print("\n" + "="*60)
        print("JAL (Jump and Link) Test")
        print("="*60)

        # Build program
        program = [
            (0x00000000, enc.JAL(1, 8)),           # jump +8, x1 = 0x4
            (0x00000004, enc.ADDI(2, 0, 1)),       # x2 = 1 (NOT executed)
            (0x00000008, enc.ADDI(2, 0, 2)),       # x2 = 2 (executed)
            (0x0000000C, 0x00100073),              # EBREAK
        ]

        # Load program
        axi_driver = self.env.axi_agent.driver
        for addr, insn in program:
            axi_driver.write_word(addr, insn)
        print("Loaded 4-instruction program")

        # Start execution
        apb_driver = self.env.apb_agent.driver
        await apb_driver.halt_cpu()
        await apb_driver.write_pc(0x00000000)
        print("Starting CPU execution...")
        await apb_driver.resume_cpu()
