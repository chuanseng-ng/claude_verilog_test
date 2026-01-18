"""
Clock and reset utilities for cocotb testbenches.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def setup_clock(dut, clock_period_ns: int = 10):
    """
    Setup clock for DUT.

    Args:
        dut: Device under test
        clock_period_ns: Clock period in nanoseconds (default 10ns = 100MHz)

    Returns:
        Clock coroutine
    """
    clock = Clock(dut.clk, clock_period_ns, units="ns")
    cocotb.start_soon(clock.start())
    return clock


async def reset_dut(dut, duration_cycles: int = 10):
    """
    Apply reset to DUT.

    Assumes active-low reset signal named 'rst_n'.

    Args:
        dut: Device under test
        duration_cycles: Number of clock cycles to hold reset (default 10)
    """
    dut.rst_n.value = 0  # Assert reset (active-low)

    # Wait for specified cycles
    for _ in range(duration_cycles):
        await RisingEdge(dut.clk)

    dut.rst_n.value = 1  # Deassert reset

    # Wait a few cycles after reset
    for _ in range(2):
        await RisingEdge(dut.clk)


async def wait_cycles(dut, num_cycles: int):
    """
    Wait for a specified number of clock cycles.

    Args:
        dut: Device under test
        num_cycles: Number of cycles to wait
    """
    for _ in range(num_cycles):
        await RisingEdge(dut.clk)


async def wait_for_signal(dut, signal_name: str, value: int, timeout_cycles: int = 1000):
    """
    Wait for a signal to reach a specific value.

    Args:
        dut: Device under test
        signal_name: Name of signal to monitor
        value: Expected value
        timeout_cycles: Maximum cycles to wait before timeout

    Raises:
        TimeoutError: If signal doesn't reach expected value within timeout
    """
    signal = getattr(dut, signal_name)
    cycles = 0

    while int(signal.value) != value:
        await RisingEdge(dut.clk)
        cycles += 1

        if cycles >= timeout_cycles:
            raise TimeoutError(
                f"Signal '{signal_name}' did not reach value {value} "
                f"within {timeout_cycles} cycles (current value: {signal.value})"
            )
