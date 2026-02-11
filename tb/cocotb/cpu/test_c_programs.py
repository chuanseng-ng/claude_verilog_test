"""
C Program Execution Tests (Placeholder)

This module will test execution of compiled C programs on the RV32I CPU.
Currently a placeholder — full implementation is deferred to a later phase.

Planned test categories:
  - Basic C arithmetic (add, subtract, multiply via software)
  - Control flow (if/else, for, while loops)
  - Function calls and stack usage
  - Memory access patterns (arrays, pointers)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from tb.cocotb.common.clock_reset import reset_dut, wait_cycles


@cocotb.test()
async def test_c_programs_placeholder(dut):
    """Placeholder: C program tests not yet implemented.

    This test always passes and serves as a marker for future work.
    """
    # Start clock and reset
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut._log.info("=" * 60)
    dut._log.info("C Program Tests — PLACEHOLDER (not yet implemented)")
    dut._log.info("=" * 60)
    dut._log.info("Planned tests:")
    dut._log.info("  - Basic C arithmetic programs")
    dut._log.info("  - Control flow programs")
    dut._log.info("  - Function call / stack programs")
    dut._log.info("  - Array / pointer access programs")
    dut._log.info("Skipping — deferred to future phase.")

    await wait_cycles(dut, 5)
