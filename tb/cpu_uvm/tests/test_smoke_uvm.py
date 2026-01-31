"""Smoke tests for RV32I CPU using pyuvm.

This module implements smoke tests using the pyuvm framework.
It wraps the directed sequences from Phase D in cocotb test functions.

Features:
- ADDI instruction test
- Branch taken/not taken tests
- JAL (jump and link) test
- UVM-based test infrastructure
- Scoreboard validation
"""

import cocotb
from cocotb.clock import Clock

from .base_test import BaseTest
from ..sequences.directed_sequences import (
    SimpleADDISequence,
    BranchTakenSequence,
    BranchNotTakenSequence,
    JALSequence
)


class ADDITest(BaseTest):
    """Test ADDI instructions using SimpleADDISequence."""

    async def run_phase(self):
        """Run ADDI test sequence."""
        self.logger.info("Running ADDI test")

        # Create and run sequence
        seq = SimpleADDISequence("addi_seq")
        seq.env = self.env
        await seq.body()

        # Wait for completion
        await self.wait_for_completion()

        # Verify results via APB
        apb_driver = self.env.apb_agent.driver
        x1 = await apb_driver.read_gpr(1)
        x2 = await apb_driver.read_gpr(2)

        assert x1 == 42, f"Expected x1=42, got {x1}"
        assert x2 == 50, f"Expected x2=50, got {x2}"

        self.logger.info("✓ ADDI test passed")


class BranchTakenTest(BaseTest):
    """Test branch taken using BranchTakenSequence."""

    async def run_phase(self):
        """Run branch taken test sequence."""
        self.logger.info("Running branch taken test")

        # Create and run sequence
        seq = BranchTakenSequence("branch_taken_seq")
        seq.env = self.env
        await seq.body()

        # Wait for completion
        await self.wait_for_completion()

        # Verify results
        apb_driver = self.env.apb_agent.driver
        x1 = await apb_driver.read_gpr(1)
        x2 = await apb_driver.read_gpr(2)
        x3 = await apb_driver.read_gpr(3)

        assert x1 == 10, f"Expected x1=10, got {x1}"
        assert x2 == 10, f"Expected x2=10, got {x2}"
        assert x3 == 2, f"Expected x3=2 (branch taken), got {x3}"

        self.logger.info("✓ Branch taken test passed")


class BranchNotTakenTest(BaseTest):
    """Test branch not taken using BranchNotTakenSequence."""

    async def run_phase(self):
        """Run branch not taken test sequence."""
        self.logger.info("Running branch not taken test")

        # Create and run sequence
        seq = BranchNotTakenSequence("branch_not_taken_seq")
        seq.env = self.env
        await seq.body()

        # Wait for completion
        await self.wait_for_completion()

        # Verify results
        apb_driver = self.env.apb_agent.driver
        x1 = await apb_driver.read_gpr(1)
        x2 = await apb_driver.read_gpr(2)
        x3 = await apb_driver.read_gpr(3)

        assert x1 == 10, f"Expected x1=10, got {x1}"
        assert x2 == 20, f"Expected x2=20, got {x2}"
        assert x3 == 1, f"Expected x3=1 (branch not taken), got {x3}"

        self.logger.info("✓ Branch not taken test passed")


class JALTest(BaseTest):
    """Test JAL (jump and link) using JALSequence."""

    async def run_phase(self):
        """Run JAL test sequence."""
        self.logger.info("Running JAL test")

        # Create and run sequence
        seq = JALSequence("jal_seq")
        seq.env = self.env
        await seq.body()

        # Wait for completion
        await self.wait_for_completion()

        # Verify results
        apb_driver = self.env.apb_agent.driver
        x1 = await apb_driver.read_gpr(1)
        x2 = await apb_driver.read_gpr(2)

        assert x1 == 0x4, f"Expected x1=0x4 (return addr), got 0x{x1:x}"
        assert x2 == 2, f"Expected x2=2 (jumped over), got {x2}"

        self.logger.info("✓ JAL test passed")


# cocotb test wrappers
@cocotb.test()
async def test_addi_uvm(dut):
    """Test ADDI instruction (pyuvm version)."""
    dut._log.info("=== Test: ADDI (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test
    test = ADDITest("addi_test", None, dut)
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
async def test_branch_taken_uvm(dut):
    """Test branch taken (pyuvm version)."""
    dut._log.info("=== Test: Branch Taken (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test
    test = BranchTakenTest("branch_taken_test", None, dut)
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
async def test_branch_not_taken_uvm(dut):
    """Test branch not taken (pyuvm version)."""
    dut._log.info("=== Test: Branch Not Taken (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test
    test = BranchNotTakenTest("branch_not_taken_test", None, dut)
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
async def test_jal_uvm(dut):
    """Test JAL (jump and link) instruction (pyuvm version)."""
    dut._log.info("=== Test: JAL (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test
    test = JALTest("jal_test", None, dut)
    test.build_phase()
    test.connect_phase()
    test.end_of_elaboration_phase()

    # Reset and run
    await test.reset_dut()
    await test.run_phase()

    # Report results
    test.env.scoreboard.report_phase()
    assert test.env.scoreboard.mismatches == 0, "Scoreboard validation failed"
