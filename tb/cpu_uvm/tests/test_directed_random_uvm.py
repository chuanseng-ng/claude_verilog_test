"""Directed random instruction tests for RV32I CPU using pyuvm.

This module implements directed random testing - random instruction generation
with custom instruction distribution weights. This allows focused testing of
specific instruction types while maintaining randomness within those types.

Features:
- Custom instruction distribution via GeneratorConfig
- Multiple test scenarios (ALU-focused, immediate-heavy, etc.)
- Seed-based reproducibility
- Scoreboard validation against reference model
- Automatic waveform capture on failures

Test Scenarios:
1. ALU-focused: 70% ALU operations, 30% upper immediate
2. Immediate-heavy: 80% I-type and upper immediate instructions
3. R-type dominant: 90% R-type ALU instructions
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

from tb.generators.rv32i_instr_gen import GeneratorConfig

from ..sequences.random_instr_sequence import RandomInstructionSequence
from .base_test import BaseTest


class DirectedRandomTest(BaseTest):
    """Test random instruction sequences with custom distribution."""

    def __init__(self, name, parent, dut, num_instructions=100, seed=None, config=None):
        """Initialize directed random test.

        Args:
            name: Test name
            parent: Parent component
            dut: Device under test
            num_instructions: Number of instructions to generate
            seed: Random seed (None = random)
            config: GeneratorConfig with custom instruction weights
        """
        super().__init__(name, parent, dut)
        self.num_instructions = num_instructions
        self.seed = seed
        self.config = config

    async def run_phase(self):
        """Run directed random instruction test."""
        self.logger.info(
            f"Running directed random test (seed={self.seed}, instructions={self.num_instructions})"
        )

        # Create and run sequence with custom config
        seq = RandomInstructionSequence(
            f"directed_random_seq_seed{self.seed}",
            num_instructions=self.num_instructions,
            seed=self.seed,
            config=self.config,  # Pass custom config
        )
        seq.env = self.env

        # Run sequence lifecycle: pre_body -> body -> post_body
        await seq.pre_body()
        await seq.body()
        await seq.post_body()

        # Wait for completion
        await self.wait_for_completion(timeout_cycles=self.num_instructions * 20)

        self.logger.info("✓ Directed random test completed")


# ============================================================================
# Directed Random Test Scenarios
# ============================================================================


@cocotb.test()
async def test_directed_alu_focused(dut):
    """Test ALU-focused instruction mix (70% ALU, 30% upper immediate).

    Custom distribution:
    - 70% ALU operations (35% R-type + 35% I-type ALU)
    - 30% upper immediate (LUI/AUIPC)

    Useful for:
    - Focused ALU validation
    - Reduced noise from other instruction types
    - Testing ALU corner cases with random operands

    Test configuration:
    - 100 seeds × 200 instructions = 20,000 total instructions
    - Deterministic seed sequence (1000-1099)
    - Scoreboard validation against reference model
    - Automatic waveform capture on failures
    """
    dut._log.info("=== Test: Directed Random - ALU Focused (70% ALU, 30% upper) ===")

    # Create custom config with 70% ALU bias
    custom_config = GeneratorConfig()
    custom_config.instruction_classes = {
        "r_type": 3.5,  # 35% (R-type ALU: ADD, SUB, AND, OR, XOR, SLT, SLTU, SLL, SRL, SRA)
        "i_type_alu": 3.5,  # 35% (I-type ALU: ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI)
        "upper": 3.0,  # 30% (Upper immediate: LUI, AUIPC)
    }

    # Test parameters
    num_seeds = 100
    num_instructions = 200
    total_instructions = num_seeds * num_instructions
    dut._log.info(
        f"Configuration: {num_seeds} seeds × {num_instructions} instr = "
        f"{total_instructions:,} total"
    )

    # Create waveform directory for failure captures
    waveform_dir = "results/waveforms"
    os.makedirs(waveform_dir, exist_ok=True)

    # Start clock
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Track failures across all seeds
    failed_seeds = []

    for seed_idx in range(num_seeds):
        seed = 1000 + seed_idx  # Deterministic seed sequence
        dut._log.info(f"\n{'=' * 60}")
        dut._log.info(f"Seed {seed_idx + 1}/{num_seeds}: {seed}")
        dut._log.info(f"{'=' * 60}\n")

        # Create and run test
        test = DirectedRandomTest(
            f"alu_focused_seed{seed}",
            None,
            dut,
            num_instructions=num_instructions,
            seed=seed,
            config=custom_config,
        )
        test.build_phase()
        test.connect_phase()
        test.end_of_elaboration_phase()

        # Start background tasks for all components
        cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
        cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
        cocotb.start_soon(test.env.commit_monitor.run_phase())
        cocotb.start_soon(test.env.scoreboard.run_phase())

        # Give background tasks a chance to start
        await ClockCycles(dut.clk_i, 2)

        # Reset and run
        await test.reset_dut()
        await test.run_phase()

        # Check results
        if test.env.scoreboard.mismatches > 0:
            dut._log.error(f"Seed {seed} failed with {test.env.scoreboard.mismatches} errors")
            test.env.scoreboard.report_phase()

            # Save waveform for debugging
            waveform_file = os.path.join(waveform_dir, f"alu_focused_seed_{seed}_failure.vcd")
            if os.path.exists("dump.vcd"):
                shutil.copy("dump.vcd", waveform_file)
                dut._log.info(f"Waveform saved to {waveform_file}")

            # Track failure but continue testing other seeds
            failed_seeds.append((seed, test.env.scoreboard.mismatches))
        else:
            dut._log.info(
                f"✓ Seed {seed} passed ({test.env.scoreboard.matches} commits validated)\n"
            )

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


@cocotb.test()
async def test_directed_immediate_heavy(dut):
    """Test immediate-heavy instruction mix (80% I-type and upper immediate).

    Custom distribution:
    - 60% I-type ALU (immediate arithmetic and logical operations)
    - 20% upper immediate (LUI/AUIPC)
    - 20% R-type ALU

    Useful for:
    - Testing immediate generation logic
    - Sign extension validation
    - Immediate value corner cases
    - Upper immediate PC-relative addressing

    Test configuration:
    - 100 seeds × 200 instructions = 20,000 total instructions
    - Deterministic seed sequence (2000-2099)
    - Scoreboard validation against reference model
    - Automatic waveform capture on failures
    """
    dut._log.info("=== Test: Directed Random - Immediate Heavy (80% I-type + upper) ===")

    # Create custom config favoring immediate instructions
    custom_config = GeneratorConfig()
    custom_config.instruction_classes = {
        "i_type_alu": 6.0,  # 60% (I-type ALU with immediates)
        "upper": 2.0,  # 20% (LUI/AUIPC with 20-bit immediates)
        "r_type": 2.0,  # 20% (R-type for variety)
    }

    # Test parameters
    num_seeds = 100
    num_instructions = 200
    total_instructions = num_seeds * num_instructions
    dut._log.info(
        f"Configuration: {num_seeds} seeds × {num_instructions} instr = "
        f"{total_instructions:,} total"
    )

    # Create waveform directory for failure captures
    waveform_dir = "results/waveforms"
    os.makedirs(waveform_dir, exist_ok=True)

    # Start clock
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Track failures across all seeds
    failed_seeds = []

    for seed_idx in range(num_seeds):
        seed = 2000 + seed_idx  # Different seed range from ALU-focused test
        dut._log.info(f"\n{'=' * 60}")
        dut._log.info(f"Seed {seed_idx + 1}/{num_seeds}: {seed}")
        dut._log.info(f"{'=' * 60}\n")

        # Create and run test
        test = DirectedRandomTest(
            f"immediate_heavy_seed{seed}",
            None,
            dut,
            num_instructions=num_instructions,
            seed=seed,
            config=custom_config,
        )
        test.build_phase()
        test.connect_phase()
        test.end_of_elaboration_phase()

        # Start background tasks for all components
        cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
        cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
        cocotb.start_soon(test.env.commit_monitor.run_phase())
        cocotb.start_soon(test.env.scoreboard.run_phase())

        # Give background tasks a chance to start
        await ClockCycles(dut.clk_i, 2)

        # Reset and run
        await test.reset_dut()
        await test.run_phase()

        # Check results
        if test.env.scoreboard.mismatches > 0:
            dut._log.error(f"Seed {seed} failed with {test.env.scoreboard.mismatches} errors")
            test.env.scoreboard.report_phase()

            # Save waveform for debugging
            waveform_file = os.path.join(waveform_dir, f"immediate_heavy_seed_{seed}_failure.vcd")
            if os.path.exists("dump.vcd"):
                shutil.copy("dump.vcd", waveform_file)
                dut._log.info(f"Waveform saved to {waveform_file}")

            # Track failure but continue testing other seeds
            failed_seeds.append((seed, test.env.scoreboard.mismatches))
        else:
            dut._log.info(
                f"✓ Seed {seed} passed ({test.env.scoreboard.matches} commits validated)\n"
            )

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


@cocotb.test()
async def test_directed_rtype_dominant(dut):
    """Test R-type dominant instruction mix (90% R-type, 10% other).

    Custom distribution:
    - 90% R-type ALU (register-register operations)
    - 10% I-type ALU (for register initialization)

    Useful for:
    - Testing register-register data paths
    - Validating ALU operations with varied operands
    - Stress testing register file read/write ports
    - Checking for register hazards

    Test configuration:
    - 100 seeds × 200 instructions = 20,000 total instructions
    - Deterministic seed sequence (3000-3099)
    - Scoreboard validation against reference model
    - Automatic waveform capture on failures
    """
    dut._log.info("=== Test: Directed Random - R-type Dominant (90% R-type) ===")

    # Create custom config heavily biased toward R-type
    custom_config = GeneratorConfig()
    custom_config.instruction_classes = {
        "r_type": 9.0,  # 90% (R-type ALU operations)
        "i_type_alu": 1.0,  # 10% (I-type for variety and initialization)
    }

    # Test parameters
    num_seeds = 100
    num_instructions = 200
    total_instructions = num_seeds * num_instructions
    dut._log.info(
        f"Configuration: {num_seeds} seeds × {num_instructions} instr = "
        f"{total_instructions:,} total"
    )

    # Create waveform directory for failure captures
    waveform_dir = "results/waveforms"
    os.makedirs(waveform_dir, exist_ok=True)

    # Start clock
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Track failures across all seeds
    failed_seeds = []

    for seed_idx in range(num_seeds):
        seed = 3000 + seed_idx  # Different seed range
        dut._log.info(f"\n{'=' * 60}")
        dut._log.info(f"Seed {seed_idx + 1}/{num_seeds}: {seed}")
        dut._log.info(f"{'=' * 60}\n")

        # Create and run test
        test = DirectedRandomTest(
            f"rtype_dominant_seed{seed}",
            None,
            dut,
            num_instructions=num_instructions,
            seed=seed,
            config=custom_config,
        )
        test.build_phase()
        test.connect_phase()
        test.end_of_elaboration_phase()

        # Start background tasks for all components
        cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
        cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
        cocotb.start_soon(test.env.commit_monitor.run_phase())
        cocotb.start_soon(test.env.scoreboard.run_phase())

        # Give background tasks a chance to start
        await ClockCycles(dut.clk_i, 2)

        # Reset and run
        await test.reset_dut()
        await test.run_phase()

        # Check results
        if test.env.scoreboard.mismatches > 0:
            dut._log.error(f"Seed {seed} failed with {test.env.scoreboard.mismatches} errors")
            test.env.scoreboard.report_phase()

            # Save waveform for debugging
            waveform_file = os.path.join(waveform_dir, f"rtype_dominant_seed_{seed}_failure.vcd")
            if os.path.exists("dump.vcd"):
                shutil.copy("dump.vcd", waveform_file)
                dut._log.info(f"Waveform saved to {waveform_file}")

            # Track failure but continue testing other seeds
            failed_seeds.append((seed, test.env.scoreboard.mismatches))
        else:
            dut._log.info(
                f"✓ Seed {seed} passed ({test.env.scoreboard.matches} commits validated)\n"
            )

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
