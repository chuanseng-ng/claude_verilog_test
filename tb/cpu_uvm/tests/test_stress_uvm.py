"""Stress tests for RV32I CPU using pyuvm with biased instruction distributions.

This module implements stress testing with configurable instruction bias profiles.
Each profile targets specific corner cases by heavily weighting certain instruction types.

Features:
- ALU-intensive workload (90% ALU operations)
- Jump-heavy workload (40% jump instructions)
- Shift-intensive workload (heavy shift operations)
- Immediate-heavy workload (tests immediate generation)
- Configurable via environment variables
- Seed-based reproducibility
- Scoreboard validation
- Automatic waveform capture on failures

Environment variables:
- STRESS_TEST_SEEDS: Number of seeds per profile (default: 100)
- STRESS_TEST_INSTRS: Instructions per seed (default: 500)
- STRESS_TEST_SMOKE: If set, use smoke test config (10 seeds × 100 instructions)
"""

import os
import shutil
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# Add project root to path for generator import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.generators.rv32i_instr_gen import (
    GeneratorConfig,
    RV32IInstructionGenerator,
    StressTestConfig,
)

from .base_test import BaseTest


async def _run_stress_profile(dut, profile_name, waveform_subdir, seed_base, stress_profile):
    """Common helper for running stress test profiles.

    Args:
        dut: Device under test
        profile_name: Display name for the test profile (e.g., "ALU-Intensive")
        waveform_subdir: Subdirectory for waveforms (e.g., "stress_alu")
        seed_base: Base seed offset (e.g., 2000, 3000, 4000, 5000)
        stress_profile: StressTestConfig profile dictionary
    """
    # Configure test parameters from environment variables
    if os.getenv("STRESS_TEST_SMOKE"):
        num_seeds = 10
        num_instructions = 100
        total_instructions = num_seeds * num_instructions
        dut._log.info(
            f"=== Test: {profile_name} Stress SMOKE TEST "
            f"(10 seeds × 100 instr = 1,000 total) (pyuvm) ==="
        )
    else:
        num_seeds = int(os.getenv("STRESS_TEST_SEEDS", "100"))
        num_instructions = int(os.getenv("STRESS_TEST_INSTRS", "500"))
        total_instructions = num_seeds * num_instructions
        dut._log.info(
            f"=== Test: {profile_name} Stress ({num_seeds} seeds × "
            f"{num_instructions} instr = {total_instructions:,} total) (pyuvm) ==="
        )

    # Determine repository root (absolute path for CI artifact collection)
    # Check GITHUB_WORKSPACE first (CI environment), then compute from file location
    repo_root = os.getenv("GITHUB_WORKSPACE")
    if not repo_root:
        # Compute repo root: this file is at tb/cpu_uvm/tests/test_stress_uvm.py
        # So repo root is 4 levels up
        repo_root = Path(__file__).parent.parent.parent.parent.resolve()
    else:
        repo_root = Path(repo_root)

    # Create waveform directory (absolute path)
    waveform_dir = repo_root / "results" / "waveforms" / waveform_subdir
    os.makedirs(waveform_dir, exist_ok=True)

    # Start clock
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Log stress profile
    dut._log.info(f"Stress profile: {stress_profile}")

    # Track failures
    failed_seeds = []

    for seed_idx in range(num_seeds):
        seed = seed_base + seed_idx
        dut._log.info(f"\n{'=' * 60}")
        dut._log.info(f"{profile_name} Seed {seed_idx + 1}/{num_seeds}: {seed}")
        dut._log.info(f"{'=' * 60}\n")

        # Create and run test
        test = StressTest(
            f"stress_{waveform_subdir}_seed{seed}",
            None,
            dut,
            num_instructions=num_instructions,
            seed=seed,
            stress_profile=stress_profile,
        )
        test.build_phase()
        test.connect_phase()
        test.end_of_elaboration_phase()

        # Start background tasks (track for cleanup)
        bg_tasks = []
        bg_tasks.append(cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler()))
        bg_tasks.append(cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler()))
        bg_tasks.append(cocotb.start_soon(test.env.commit_monitor.run_phase()))
        bg_tasks.append(cocotb.start_soon(test.env.scoreboard.run_phase()))

        await ClockCycles(dut.clk_i, 2)

        # Reset and run
        await test.reset_dut()
        await test.run_phase()

        # Terminate background tasks before moving to next seed
        for task in bg_tasks:
            task.kill()
        # Assert reset to stop CPU and prevent stale commits reaching next seed's monitor
        dut.rst_n_i.value = 0
        await ClockCycles(dut.clk_i, 2)  # Hold reset to flush in-flight commits

        # Check results
        if test.env.scoreboard.mismatches > 0:
            dut._log.error(
                f"{profile_name} Seed {seed} failed with {test.env.scoreboard.mismatches} errors"
            )
            test.env.scoreboard.report_phase()

            # Save waveform
            waveform_file = os.path.join(waveform_dir, f"seed_{seed}_failure.vcd")
            if os.path.exists("dump.vcd"):
                shutil.copy("dump.vcd", waveform_file)
                dut._log.info(f"Waveform saved to {waveform_file}")

            failed_seeds.append((seed, test.env.scoreboard.mismatches))
        else:
            dut._log.info(
                f"✓ {profile_name} Seed {seed} passed "
                f"({test.env.scoreboard.matches} commits validated)\n"
            )

    # Report results
    dut._log.info(f"\n{'=' * 60}")
    if failed_seeds:
        dut._log.error(f"{profile_name}: {len(failed_seeds)} seed(s) failed out of {num_seeds}:")
        for seed, mismatch_count in failed_seeds:
            dut._log.error(f"  - Seed {seed}: {mismatch_count} mismatches")
        dut._log.info(f"{'=' * 60}\n")
        assert False, (
            f"{profile_name}: {len(failed_seeds)} seed(s) failed (see waveforms in {waveform_dir})"
        )
    else:
        dut._log.info(f"{profile_name}: All {num_seeds} seeds passed!")
        dut._log.info(f"{'=' * 60}\n")


class StressTest(BaseTest):
    """Test stress instruction sequences with biased distributions."""

    def __init__(self, name, parent, dut, num_instructions=500, seed=None, stress_profile=None):
        """Initialize stress test.

        Args:
            name: Test name
            parent: Parent component
            dut: Device under test
            num_instructions: Number of instructions to generate
            seed: Random seed (None = random)
            stress_profile: Dict of instruction class weights (from StressTestConfig)
        """
        super().__init__(name, parent, dut)
        self.num_instructions = num_instructions
        self.seed = seed
        self.stress_profile = stress_profile

    async def run_phase(self):
        """Run stress test with custom instruction distribution."""
        self.logger.info(
            f"Running stress test (seed={self.seed}, "
            f"instructions={self.num_instructions}, profile={self.stress_profile})"
        )

        # Create custom generator config with stress profile
        config = GeneratorConfig()
        if self.stress_profile is not None:
            # Extract instruction class weights (filter out config overrides starting with _)
            config.instruction_classes = {
                k: v for k, v in self.stress_profile.items() if not k.startswith("_")
            }

            # Apply config overrides (special keys starting with _)
            if "_shift_bias" in self.stress_profile:
                config.shift_bias = self.stress_profile["_shift_bias"]
                self.logger.info(f"Applying shift bias: {config.shift_bias}x")

        # Create instruction generator with custom config
        generator = RV32IInstructionGenerator(seed=self.seed, config=config)

        # Generate program
        self.logger.info(f"Generating {self.num_instructions} instructions with stress profile...")
        program = generator.generate_program(self.num_instructions)
        init_regs = generator.get_register_init_values()

        # Load program into memory
        self.logger.info("Loading program into instruction memory...")
        axi_driver = self.env.axi_agent.driver
        for addr, insn in program:
            axi_driver.write_word(addr, insn)

        # Initialize registers
        self.logger.info("Initializing CPU registers...")
        apb_driver = self.env.apb_agent.driver
        await apb_driver.halt_cpu()
        for reg_num, value in init_regs.items():
            await apb_driver.write_gpr(reg_num, value)
        await apb_driver.write_pc(0x00000000)

        # Start execution
        self.logger.info("Starting CPU execution...")
        await apb_driver.resume_cpu()

        # Wait for completion
        await self.wait_for_completion(timeout_cycles=self.num_instructions * 20)

        self.logger.info("✓ Stress test completed")


# cocotb test wrappers
@cocotb.test()
async def test_stress_alu_intensive(dut):
    """Test ALU-intensive workload (90% ALU operations).

    This stress profile tests:
    - Heavy register usage (register file pressure)
    - ALU datapath stress (all arithmetic/logic operations)
    - Register bypass logic
    - Write-back contention

    Configuration: 50% R-type + 40% I-type ALU + 10% Upper
    """
    await _run_stress_profile(
        dut=dut,
        profile_name="ALU-Intensive",
        waveform_subdir="stress_alu",
        seed_base=2000,
        stress_profile=StressTestConfig.alu_intensive(),
    )


@cocotb.test()
async def test_stress_jump_heavy(dut):
    """Test jump-heavy workload (40% jump instructions).

    This stress profile tests:
    - Control flow changes (PC management)
    - JAL/JALR instruction execution
    - Return address handling
    - Branch prediction (when implemented)

    Configuration: 40% Jumps + 25% R-type + 25% I-type ALU + 10% Upper
    """
    await _run_stress_profile(
        dut=dut,
        profile_name="Jump-Heavy",
        waveform_subdir="stress_jump",
        seed_base=3000,
        stress_profile=StressTestConfig.jump_heavy(),
    )


@cocotb.test()
async def test_stress_shift_intensive(dut):
    """Test shift-intensive workload (heavy shift operations).

    This stress profile tests:
    - Shift unit with various shift amounts
    - Barrel shifter stress (if implemented)
    - Left/right shift correctness
    - Arithmetic vs logical right shift

    Configuration: 60% I-type ALU (shift-biased) + 30% R-type + 10% Upper
    """
    await _run_stress_profile(
        dut=dut,
        profile_name="Shift-Intensive",
        waveform_subdir="stress_shift",
        seed_base=4000,
        stress_profile=StressTestConfig.shift_intensive(),
    )


@cocotb.test()
async def test_stress_immediate_heavy(dut):
    """Test immediate-heavy workload (tests immediate generation).

    This stress profile tests:
    - Immediate generation logic
    - Sign extension correctness
    - Upper immediate instructions (LUI, AUIPC)
    - Constant propagation patterns

    Configuration: 50% I-type ALU + 40% Upper + 10% R-type
    """
    await _run_stress_profile(
        dut=dut,
        profile_name="Immediate-Heavy",
        waveform_subdir="stress_immediate",
        seed_base=5000,
        stress_profile=StressTestConfig.immediate_heavy(),
    )
