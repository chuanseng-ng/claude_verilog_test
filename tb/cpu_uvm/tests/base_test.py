"""Base Test class for pyuvm CPU tests.

This module provides the base test class that bridges cocotb and pyuvm.
It handles test infrastructure setup, environment creation, and common utilities.

Features:
- UVM test base class
- CPUEnvironment creation and configuration
- Clock management
- Reset handling
- Common test utilities
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from pyuvm import uvm_test
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.models.rv32i_model import RV32IModel
from ..env.cpu_env import CPUEnvironment


class BaseTest(uvm_test):
    """Base class for all CPU UVM tests.

    This test provides common infrastructure for all CPU tests:
    - CPUEnvironment creation with ref model
    - Clock and reset management
    - DUT configuration
    - Common test utilities

    Child classes should override run_phase() to implement test logic,
    typically by running sequences on the environment's agents.

    In cocotb, create a wrapper function that:
    1. Starts the clock
    2. Creates BaseTest or child class
    3. Runs uvm phases
    4. Checks results

    Attributes:
        dut: Device under test (cocotb handle)
        env: CPUEnvironment instance
        ref_model: RV32IModel instance
    """

    def __init__(self, name, parent, dut):
        """Initialize base test.

        Args:
            name: Test name
            parent: Parent component (None for top-level test)
            dut: Device under test (cocotb handle)
        """
        super().__init__(name, parent)
        self.dut = dut
        self.env = None  # Created in build_phase
        self.ref_model = None  # Created in build_phase

    def build_phase(self):
        """UVM build phase - create environment and reference model.

        This phase:
        1. Creates RV32I reference model
        2. Creates CPUEnvironment with DUT and ref model
        3. Recursively builds all child components
        """
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

        # Create reference model
        self.ref_model = RV32IModel()

        # Create CPU environment
        self.env = CPUEnvironment(
            "cpu_env",
            self,
            dut=self.dut,
            ref_model=self.ref_model
        )

        # Build environment and all its child components
        self.env.build_phase()

        # Build agents
        if self.env.axi_agent:
            self.env.axi_agent.build_phase()
        if self.env.apb_agent:
            self.env.apb_agent.build_phase()
        if self.env.commit_monitor:
            self.env.commit_monitor.build_phase()
        if self.env.scoreboard:
            self.env.scoreboard.build_phase()

        self.logger.info("Test build complete")

    async def run_phase(self):
        """UVM run phase - default implementation.

        Child classes should override this to run test sequences.
        The base implementation just waits briefly to allow
        background tasks to run.
        """
        self.logger.info("Test run phase (override in child class)")
        # Default: just wait for environment to initialize
        await ClockCycles(self.dut.clk, 10)

    async def reset_dut(self):
        """Apply reset to DUT.

        Resets all DUT signals to known state:
        - Assert rst_n = 0
        - Initialize AXI/APB signals
        - Wait 5 cycles
        - Deassert rst_n = 1
        - Wait 2 cycles
        """
        self.logger.info("Applying reset")

        # Assert reset and initialize signals
        self.dut.rst_n.value = 0
        self.dut.axi_arready.value = 0
        self.dut.axi_rvalid.value = 0
        self.dut.axi_rdata.value = 0
        self.dut.axi_rresp.value = 0
        self.dut.axi_awready.value = 0
        self.dut.axi_wready.value = 0
        self.dut.axi_bvalid.value = 0
        self.dut.axi_bresp.value = 0
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 0
        self.dut.apb_paddr.value = 0
        self.dut.apb_pwdata.value = 0

        # Hold reset
        await ClockCycles(self.dut.clk, 5)

        # Release reset
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, 2)

        self.logger.info("Reset complete")

    async def wait_for_ebreak(self, timeout_cycles=1000):
        """Wait for EBREAK to halt the CPU.

        Monitors the CPU until it halts (EBREAK instruction),
        or timeout occurs.

        Args:
            timeout_cycles: Maximum cycles to wait (default: 1000)

        Returns:
            True if CPU halted, False if timeout

        Note: This assumes EBREAK triggers halt via debug interface.
        """
        apb_driver = self.env.apb_agent.driver

        for cycle in range(timeout_cycles):
            await ClockCycles(self.dut.clk, 1)

            # Check if CPU is halted
            try:
                status = await apb_driver.apb_read(apb_driver.DBG_STATUS)
                if status & 0x1:  # HALTED bit
                    self.logger.info(f"CPU halted after {cycle} cycles")
                    return True
            except Exception:
                # Might fail if CPU is running, continue waiting
                pass

        self.logger.warning(f"Timeout waiting for EBREAK after {timeout_cycles} cycles")
        return False

    async def wait_for_completion(self, timeout_cycles=1000):
        """Wait for test completion.

        Waits for CPU to halt (EBREAK) and scoreboard to finish validation.

        Args:
            timeout_cycles: Maximum cycles to wait

        Returns:
            True if completed successfully, False if timeout
        """
        # Wait for EBREAK
        halted = await self.wait_for_ebreak(timeout_cycles)
        if not halted:
            return False

        # Give scoreboard time to process final commits
        await ClockCycles(self.dut.clk, 10)

        self.logger.info("Test completion detected")
        return True


# Helper function for cocotb integration
async def run_uvm_test(dut, test_class, test_name="uvm_test"):
    """Run a UVM test within cocotb framework.

    This is a helper function that bridges cocotb and pyuvm:
    1. Starts clock
    2. Creates test instance
    3. Runs UVM phases
    4. Checks scoreboard results

    Args:
        dut: Device under test (cocotb handle)
        test_class: Test class to instantiate (BaseTest or subclass)
        test_name: Test instance name

    Usage:
        @cocotb.test()
        async def test_my_test(dut):
            await run_uvm_test(dut, MyTest, "my_test")
    """
    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test
    test = test_class(test_name, None, dut)

    # Run UVM phases
    test.build_phase()
    test.connect_phase()
    test.end_of_elaboration_phase()

    # Start background tasks for all components
    # AXI driver handlers
    cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
    cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())

    # Commit monitor
    cocotb.start_soon(test.env.commit_monitor.run_phase())

    # Scoreboard
    cocotb.start_soon(test.env.scoreboard.run_phase())

    # Give background tasks a chance to start
    await ClockCycles(dut.clk, 2)

    # Reset DUT
    await test.reset_dut()

    # Run test
    await test.run_phase()

    # Report scoreboard results
    test.env.scoreboard.report_phase()

    # Check for scoreboard errors
    assert test.env.scoreboard.mismatches == 0, \
        f"Scoreboard validation failed: {test.env.scoreboard.mismatches} errors"
