"""Negative control for the sim/Makefile results gate: this suite always fails."""

import cocotb


@cocotb.test()
async def test_always_fails(dut):
    """Fail on purpose; `make -C sim check-exit-propagation` expects the make to exit non-zero."""
    assert False, "deliberate failure: proves a red cocotb suite fails the make"
