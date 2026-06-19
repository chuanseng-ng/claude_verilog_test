"""Random instruction tests for RV32I CPU using pyuvm.

This module implements random instruction testing using the pyuvm framework.
It uses the RandomInstructionSequence to generate and execute random programs.

Features:
- Single random test (100 instructions)
- Multi-seed random testing (configurable via environment variables)
- Seed-based reproducibility
- Scoreboard validation
- Automatic waveform capture on failures
"""

import os
import shutil

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from ..sequences.random_instr_sequence import RandomInstructionSequence
from .base_test import BaseTest


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
        self.logger.info(
            f"Running random test (seed={self.seed}, instructions={self.num_instructions})"
        )

        # Create and run sequence
        seq = RandomInstructionSequence(
            f"random_seq_seed{self.seed}", num_instructions=self.num_instructions, seed=self.seed
        )
        seq.env = self.env

        # Run sequence lifecycle: pre_body -> body -> post_body
        await seq.pre_body()
        await seq.body()
        await seq.post_body()

        # Wait for completion
        await self.wait_for_completion(timeout_cycles=self.num_instructions * 20)

        self.logger.info("✓ Random test completed")


# cocotb test wrappers
@cocotb.test()
async def test_random_single_uvm(dut):
    """Test single random instruction sequence (pyuvm version)."""
    dut._log.info("=== Test: Random Instructions (100) (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk_i, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Create and run test with fixed seed for reproducibility
    test = RandomTest("random_test_single", None, dut, num_instructions=100, seed=42)
    test.build_phase()
    test.connect_phase()
    test.end_of_elaboration_phase()

    # Per MEMORY.md "Stale AXI Signals Between cocotb Tests":
    # Clear AXI signals BEFORE reset, then create handler tasks AFTER reset
    await test.reset_dut()

    # Start background tasks for all components (AFTER reset)
    cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
    cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
    cocotb.start_soon(test.env.commit_monitor.run_phase())
    cocotb.start_soon(test.env.scoreboard.run_phase())

    # Give background tasks a chance to start
    await ClockCycles(dut.clk_i, 2)

    # Run test
    await test.run_phase()

    # Report results
    test.env.scoreboard.report_phase()
    assert test.env.scoreboard.mismatches == 0, "Scoreboard validation failed"


@cocotb.test()
async def test_random_multi_seed_uvm(dut):
    """Test multiple random seeds (pyuvm version).

    Environment variables:
    - RANDOM_TEST_SEEDS: Number of seeds (default: 1000)
    - RANDOM_TEST_INSTRS: Instructions per seed (default: 100)
    - RANDOM_TEST_SMOKE: If set, use smoke test config (10 seeds × 50 instructions)
    - RANDOM_TEST_SEED: Replay exactly one seed value (overrides the seed sweep;
      combine with RANDOM_TEST_INSTRS to match the failing configuration)

    Default configuration: 1000 seeds × 100 instructions = 100,000 total instructions

    Per-seed outcomes are appended to results/random_seed_log.txt so any failing
    seed can be replayed with `make random_uvm SEED=<value> INSTRS=<n>`.
    """
    # Configure test parameters via environment variables
    replay_seed = os.getenv("RANDOM_TEST_SEED")
    if replay_seed is not None:
        seeds = [int(replay_seed)]
        num_instructions = int(os.getenv("RANDOM_TEST_INSTRS", "100"))
        dut._log.info(
            f"=== Test: Random Single-Seed REPLAY (seed={seeds[0]}, "
            f"{num_instructions} instr) (pyuvm) ==="
        )
    elif os.getenv("RANDOM_TEST_SMOKE"):
        num_seeds = 10
        num_instructions = 50
        seeds = [1000 + i for i in range(num_seeds)]
        dut._log.info(
            "=== Test: Random Multi-Seed SMOKE TEST (10 seeds × 50 instr = 500 total) (pyuvm) ==="
        )
    else:
        num_seeds = int(os.getenv("RANDOM_TEST_SEEDS", "1000"))  # Default: 1000 (was 100)
        num_instructions = int(os.getenv("RANDOM_TEST_INSTRS", "100"))  # Default: 100
        seeds = [1000 + i for i in range(num_seeds)]
        total_instructions = num_seeds * num_instructions
        dut._log.info(
            f"=== Test: Random Multi-Seed ({num_seeds} seeds × "
            f"{num_instructions} instr = {total_instructions:,} total) (pyuvm) ==="
        )
    num_seeds = len(seeds)

    # Create waveform directory for failure captures
    waveform_dir = "results/waveforms"
    os.makedirs(waveform_dir, exist_ok=True)
    dut._log.info(f"Waveform directory created: {waveform_dir}")

    # Seed log: one line per seed so failures are replayable after the run
    seed_log_path = "results/random_seed_log.txt"
    with open(seed_log_path, "a", encoding="utf-8") as seed_log:
        seed_log.write(
            f"# run: seeds={num_seeds} instrs_per_seed={num_instructions} "
            f"replay={replay_seed or '-'}\n"
        )

    # Start clock
    clock = Clock(dut.clk_i, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Track failures across all seeds
    failed_seeds = []

    # Track background tasks for cleanup between seeds
    background_tasks = []

    for seed_idx, seed in enumerate(seeds):
        dut._log.info(f"\n{'=' * 60}")
        dut._log.info(f"Seed {seed_idx + 1}/{num_seeds}: {seed}")
        dut._log.info(f"{'=' * 60}\n")

        # Kill old background tasks from previous seed to prevent race conditions
        # Per MEMORY.md: stale RTL commits can reach new monitor if tasks aren't killed
        if background_tasks:
            dut._log.debug("Killing old background tasks from previous seed")
            for task in background_tasks:
                task.kill()
            background_tasks.clear()

            # CRITICAL: Immediately assert reset to stop CPU before starting new monitor
            # Per MEMORY.md: If CPU is stuck in a loop (e.g., backward JAL), it will
            # still commit during ClockCycles wait, reaching the new monitor
            dut.rst_n_i.value = 0
            await ClockCycles(dut.clk_i, 2)

        # Create and run test
        test = RandomTest(
            f"random_test_seed{seed}", None, dut, num_instructions=num_instructions, seed=seed
        )
        test.build_phase()
        test.connect_phase()
        test.end_of_elaboration_phase()

        # Per MEMORY.md "Stale AXI Signals Between cocotb Tests":
        # Clear AXI signals BEFORE reset, then create handler tasks AFTER reset
        # to prevent stale signal values from previous test reaching the new test
        await test.reset_dut()

        # Start background tasks for all components and track them (AFTER reset)
        background_tasks.append(cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler()))
        background_tasks.append(cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler()))
        background_tasks.append(cocotb.start_soon(test.env.commit_monitor.run_phase()))
        background_tasks.append(cocotb.start_soon(test.env.scoreboard.run_phase()))

        # Give background tasks a chance to start
        await ClockCycles(dut.clk_i, 2)

        # Run test
        await test.run_phase()

        # Check results
        if test.env.scoreboard.mismatches > 0:
            dut._log.error(f"Seed {seed} failed with {test.env.scoreboard.mismatches} errors")
            test.env.scoreboard.report_phase()

            # Save waveform for debugging
            # Note: dump.vcd is a cumulative trace, not per-seed isolated
            waveform_file = os.path.join(waveform_dir, f"seed_{seed}_failure.vcd")
            if os.path.exists("dump.vcd"):
                shutil.copy("dump.vcd", waveform_file)
                dut._log.info(f"Waveform (cumulative up to seed {seed}) saved to {waveform_file}")
            else:
                dut._log.warning("No waveform file (dump.vcd) found to save")

            # Track failure but continue testing other seeds
            failed_seeds.append((seed, test.env.scoreboard.mismatches))
            with open(seed_log_path, "a", encoding="utf-8") as seed_log:
                seed_log.write(
                    f"seed={seed} instrs={num_instructions} FAIL "
                    f"mismatches={test.env.scoreboard.mismatches}\n"
                )
        else:
            dut._log.info(
                f"✓ Seed {seed} passed ({test.env.scoreboard.matches} commits validated)\n"
            )
            with open(seed_log_path, "a", encoding="utf-8") as seed_log:
                seed_log.write(f"seed={seed} instrs={num_instructions} PASS\n")

    # Report final results
    dut._log.info(f"\n{'=' * 60}")
    if failed_seeds:
        dut._log.error(f"{len(failed_seeds)} seed(s) failed out of {num_seeds}:")
        for seed, mismatch_count in failed_seeds:
            dut._log.error(f"  - Seed {seed}: {mismatch_count} mismatches")
        dut._log.info(f"{'=' * 60}\n")
        assert False, (
            f"{len(failed_seeds)} seed(s) failed validation (see waveforms in {waveform_dir})"
        )
    else:
        dut._log.info(f"All {num_seeds} seeds passed!")
        dut._log.info(f"{'=' * 60}\n")
