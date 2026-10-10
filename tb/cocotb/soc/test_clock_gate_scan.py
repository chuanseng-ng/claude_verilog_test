"""
test_clock_gate_scan.py -- bead claude_verilog_test-j41m.2 (DFT Stage 1a).

DUT: tb_clock_gate_scan -> rv32i_clock_gate (rtl/mem/rv32i_clock_gate.sv).

The only new behaviour is the scan test-enable: the latch input becomes
`en | test_en`, so with test_en=1 the gate passes the clock whatever `en` is
(a gated-off clock would leave every flop behind it unreachable by scan).
With test_en=0 the module must be the old glitch-free latch+AND gate.

The clock is driven by hand (Timer) rather than cocotb's Clock so each test
can change en / test_en at an exact point in the clock phase.

Tests:
  test_test_en_passes_clock_with_en_low   test_en=1, en=0: gclk toggles
  test_test_en_low_is_the_old_gate        test_en=0: gclk follows clk iff en
  test_test_en_does_not_glitch            test_en changing while clk is HIGH
                                          must not create a runt / early edge
  test_en_still_glitch_free               en changing while clk is HIGH (old
                                          behaviour, regression guard)
"""

import cocotb
from cocotb.triggers import Timer

HALF_NS = 5


async def _tick(dut, n=1):
    """n full clock cycles (low -> high -> low), returning with clk low."""
    for _ in range(n):
        dut.clk.value = 1
        await Timer(HALF_NS, units="ns")
        dut.clk.value = 0
        await Timer(HALF_NS, units="ns")


async def _count_gclk_rises(dut, n):
    """Run n cycles, count gclk rising edges (sampled at each phase)."""
    rises = 0
    for _ in range(n):
        before = int(dut.gclk.value)
        dut.clk.value = 1
        await Timer(HALF_NS, units="ns")
        if int(dut.gclk.value) and not before:
            rises += 1
        dut.clk.value = 0
        await Timer(HALF_NS, units="ns")
    return rises


async def _idle(dut, en, test_en):
    dut.clk.value = 0
    dut.en.value = en
    dut.test_en.value = test_en
    await Timer(HALF_NS, units="ns")


@cocotb.test()
async def test_test_en_passes_clock_with_en_low(dut):
    """test_en=1 forces the gate open regardless of en."""
    await _idle(dut, en=0, test_en=1)
    await _tick(dut, 2)  # let the low-phase latch capture
    assert await _count_gclk_rises(dut, 8) == 8, "gclk must toggle every cycle with test_en=1, en=0"


@cocotb.test()
async def test_test_en_low_is_the_old_gate(dut):
    """test_en=0: gclk follows clk iff en (the pre-scan behaviour)."""
    await _idle(dut, en=0, test_en=0)
    await _tick(dut, 2)
    assert await _count_gclk_rises(dut, 8) == 0, "en=0, test_en=0 must hold gclk low"
    dut.en.value = 1
    await _tick(dut, 2)
    assert await _count_gclk_rises(dut, 8) == 8, "en=1, test_en=0 must pass the clock"
    dut.en.value = 0
    await _tick(dut, 2)
    assert await _count_gclk_rises(dut, 8) == 0, "dropping en must close the gate again"


@cocotb.test()
async def test_test_en_does_not_glitch(dut):
    """Switching test_en while clk is HIGH must not change gclk this cycle."""
    await _idle(dut, en=0, test_en=0)
    await _tick(dut, 2)
    # Raise clk, then assert test_en mid-high-phase: the latch is opaque, so
    # gclk must stay low for the rest of this cycle and only start next cycle.
    dut.clk.value = 1
    await Timer(1, units="ns")
    dut.test_en.value = 1
    await Timer(1, units="ns")
    assert int(dut.gclk.value) == 0, "test_en rising while clk high must not glitch gclk high"
    await Timer(HALF_NS - 2, units="ns")
    dut.clk.value = 0
    await Timer(HALF_NS, units="ns")
    assert await _count_gclk_rises(dut, 4) == 4, "gate must be open from the next cycle"
    # Drop test_en while clk is high with gclk currently high: gclk must stay
    # high for the rest of this high phase (no early fall / runt pulse).
    dut.clk.value = 1
    await Timer(1, units="ns")
    assert int(dut.gclk.value) == 1
    dut.test_en.value = 0
    await Timer(2, units="ns")
    assert int(dut.gclk.value) == 1, "test_en falling while clk high must not truncate the pulse"


@cocotb.test()
async def test_en_still_glitch_free(dut):
    """Regression guard: `en` changes while clk is high are still ignored."""
    await _idle(dut, en=0, test_en=0)
    await _tick(dut, 2)
    dut.clk.value = 1
    await Timer(1, units="ns")
    dut.en.value = 1
    await Timer(2, units="ns")
    assert int(dut.gclk.value) == 0, "en rising while clk high must not glitch gclk"
