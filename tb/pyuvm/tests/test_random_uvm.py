"""Random instruction tests for RV32I CPU using pyuvm.

This module implements random instruction testing using the pyuvm framework.
It uses the RandomInstructionSequence to generate and execute random programs.

Features:
- Single random test (100 instructions)
- Multi-seed random testing (10 seeds for Phase E demo)
- Seed-based reproducibility
- Scoreboard validation
"""

import cocotb
from cocotb.clock import Clock

from .base_test import BaseTest
from ..sequences.random_instr_sequence import RandomInstructionSequence


class RandomTest(BaseTest):
    """Test random instruction sequences."""

    def __init__(self, name, parent, dut, num_instructions=100, seed=None):
        """Initialize random test.

        Args:
            name: Test name
            parent: Parent component
            dut: Device under test
            num_instructions: Number of instructions to generate
            seed: Random seed (None = random)
        """
        super().__init__(name, parent, dut)
        self.num_instructions = num_instructions
        self.seed = seed

    async def run_phase(self):
        """Run random instruction test."""
        self.logger.info(f"Running random test (seed={self.seed}, "
                        f"instructions={self.num_instructions})")

        # Create and run sequence
        seq = RandomInstructionSequence(
            f"random_seq_seed{self.seed}",
            num_instructions=self.num_instructions,
            seed=self.seed
        )
        seq.env = self.env
        await seq.body()

        # Wait for completion
        await self.wait_for_completion(timeout_cycles=self.num_instructions * 20)

        self.logger.info("✓ Random test completed")


# cocotb test wrappers
@cocotb.test()
async def test_random_single_uvm(dut):
    """Test single random instruction sequence (pyuvm version)."""
    dut._log.info("=== Test: Random Instructions (100) (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test with fixed seed for reproducibility
    test = RandomTest("random_test_single", None, dut,
                     num_instructions=100, seed=42)
    test.build_phase()
    test.connect_phase()
    test.end_of_elaboration_phase()

    # Reset and run
    await test.reset_dut()
    await test.run_phase()

    # Report results
    test.env.scoreboard.report_phase()
    assert test.env.scoreboard.mismatches == 0, "Scoreboard validation failed"


@cocotb.test()
async def test_random_multi_seed_uvm(dut):
    """Test multiple random seeds (pyuvm version).

    Tests 10 different seeds with 100 instructions each.
    This is a reduced version of the full 100-seed test for Phase E demonstration.
    The full 100-seed test can be enabled in Phase F.
    """
    dut._log.info("=== Test: Random Multi-Seed (10 seeds × 100 instr) (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Test multiple seeds (reduced to 10 for Phase E)
    num_seeds = 10
    num_instructions = 100

    for seed_idx in range(num_seeds):
        seed = 1000 + seed_idx  # Deterministic seed sequence
        dut._log.info(f"\n{'='*60}")
        dut._log.info(f"Seed {seed_idx + 1}/{num_seeds}: {seed}")
        dut._log.info(f"{'='*60}\n")

        # Create and run test
        test = RandomTest(f"random_test_seed{seed}", None, dut,
                         num_instructions=num_instructions, seed=seed)
        test.build_phase()
        test.connect_phase()
        test.end_of_elaboration_phase()

        # Reset and run
        await test.reset_dut()
        await test.run_phase()

        # Check results
        if test.env.scoreboard.mismatches > 0:
            dut._log.error(f"Seed {seed} failed with {test.env.scoreboard.mismatches} errors")
            test.env.scoreboard.report_phase()
            assert False, f"Seed {seed} failed validation"

        dut._log.info(f"✓ Seed {seed} passed ({test.env.scoreboard.matches} commits validated)\n")

    dut._log.info(f"\n{'='*60}")
    dut._log.info(f"All {num_seeds} seeds passed!")
    dut._log.info(f"{'='*60}\n")
