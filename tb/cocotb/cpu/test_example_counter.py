"""
Example cocotb test to demonstrate infrastructure is working.

This tests a simple counter module and serves as a sanity check
that cocotb is properly installed and configured.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


@cocotb.test()
async def test_counter_basic(dut):
    """Test basic counter functionality."""
    log = dut._log

    # Create a 10ns period clock (100MHz)
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.enable.value = 0
    dut.rst_n.value = 0
    await Timer(20, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    log.info("Reset complete")

    # Check initial value
    assert dut.count.value == 0, (
        f"Counter should be 0 after reset, got {dut.count.value}"
    )
    log.info(f"✓ Initial count = {dut.count.value}")

    # Enable counter
    dut.enable.value = 1
    await RisingEdge(dut.clk)

    # Check counter increments
    for expected in range(1, 10):
        await RisingEdge(dut.clk)
        actual = int(dut.count.value)
        assert actual == expected, f"Expected count={expected}, got {actual}"
        log.info(f"✓ Count = {actual}")

    log.info("TEST PASSED: Counter increments correctly")


@cocotb.test()
async def test_counter_disable(dut):
    """Test counter stops when disabled."""
    log = dut._log

    # Create clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.enable.value = 0
    dut.rst_n.value = 0
    await Timer(20, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Enable and count to 5
    dut.enable.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)

    # Wait for the last increment to complete
    await RisingEdge(dut.clk)
    current_count = int(dut.count.value)
    log.info(f"Count reached {current_count}")

    # Disable counter (disable takes effect on next edge)
    dut.enable.value = 0

    # Wait one more edge for disable to take effect
    await RisingEdge(dut.clk)

    # Now check count stays frozen
    frozen_count = int(dut.count.value)
    log.info(f"Checking count stays at {frozen_count}")

    for _ in range(10):
        await RisingEdge(dut.clk)
        assert int(dut.count.value) == frozen_count, (
            f"Counter should stay at {frozen_count} when disabled"
        )

    log.info(f"✓ Count held at {frozen_count} when disabled")
    log.info("TEST PASSED: Counter stops when disabled")


@cocotb.test()
async def test_counter_reset(dut):
    """Test counter resets correctly."""
    log = dut._log

    # Create clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initial reset
    dut.enable.value = 1
    dut.rst_n.value = 0
    await Timer(20, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    # Count to some value
    for _ in range(10):
        await RisingEdge(dut.clk)

    log.info(f"Count before reset: {dut.count.value}")

    # Reset again
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Check counter is back to 0
    assert int(dut.count.value) == 0, (
        f"Counter should be 0 after reset, got {dut.count.value}"
    )

    log.info(f"✓ Count after reset: {dut.count.value}")
    log.info("TEST PASSED: Counter resets correctly")
