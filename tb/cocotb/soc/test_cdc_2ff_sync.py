"""
test_cdc_2ff_sync.py -- bead claude_verilog_test-xtaa cocotb verification for
cdc_2ff_sync's STAGES and RESET_VAL parameters (rtl/soc/cdc/cdc_2ff_sync.sv),
via the standalone wrapper tb_cdc_2ff_sync.sv.

DUT instances (all share clk_i / rst_n_i):
  matrix i = 0..5   WIDTH=1, STAGES = 2 + i//2 (2,3,4), RESET_VAL = i % 2
  mixed             WIDTH=4, STAGES=3, RESET_VAL=4'b1010

The data inputs are driven to the OPPOSITE of each instance's reset value,
so a reset value that leaks (or a latency that is off by one) is visible.

Tests:
  test_reset_value_held_during_reset
      With rst_n_i low every output shows its RESET_VAL, asynchronously at
      time 0 and after several clock edges -- i.e. every one of the STAGES
      ranks resets, not only the first.
  test_latency_after_release
      After release, a change on d_i first appears on q_o exactly STAGES
      rising edges later and not one edge sooner, for every STAGES x
      RESET_VAL combination and for the mixed pattern.
  test_reset_value_is_async_clear
      A mid-cycle assertion of rst_n_i returns every output to its reset
      value with no clock edge in between.
  test_reset_value_reasserted_after_activity
      Drive data through, assert reset again: outputs return to RESET_VAL
      and the next release re-synchronises with the same latency.

The STAGES < 2 elaboration guard (negative control) is checked by the
`cdc_2ff_sync_stages1_neg` Makefile step, since a failed elaboration cannot
be observed from inside a simulation.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer

CLK_PERIOD_NS = 10
SETTLE_NS = 1
N_MATRIX = 6
MIXED_RESET = 0b1010
MIXED_DATA = (~MIXED_RESET) & 0xF
MIXED_STAGES = 3


def _stages(i):
    return 2 + i // 2


def _rv(i):
    return i % 2


def _reset_vec():
    return sum(_rv(i) << i for i in range(N_MATRIX))


def _data_vec():
    return sum((1 - _rv(i)) << i for i in range(N_MATRIX))


def _outs(dut):
    return int(dut.qm_o.value), int(dut.qx_o.value)


async def _start(dut, *, hold_reset=True):
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n_i.value = 0 if hold_reset else 1
    dut.dm_i.value = _data_vec()
    dut.dx_i.value = MIXED_DATA
    await Timer(SETTLE_NS, units="ns")


async def _release(dut):
    """Release reset away from the active edge (falling edge)."""
    await FallingEdge(dut.clk_i)
    dut.rst_n_i.value = 1


async def _measure_latency(dut):
    """Edges after release at which each output reaches its data value."""
    seen = {}
    for edge in range(1, 7):
        await RisingEdge(dut.clk_i)
        await Timer(SETTLE_NS, units="ns")
        qm, qx = _outs(dut)
        for i in range(N_MATRIX):
            if ((qm >> i) & 1) == (1 - _rv(i)) and i not in seen:
                seen[i] = edge
        if qx == MIXED_DATA and "mixed" not in seen:
            seen["mixed"] = edge
    return seen


@cocotb.test()
async def test_reset_value_held_during_reset(dut):
    await _start(dut)
    assert _outs(dut) == (_reset_vec(), MIXED_RESET), f"async reset values wrong: {_outs(dut)}"
    for edge in range(8):
        await RisingEdge(dut.clk_i)
        await Timer(SETTLE_NS, units="ns")
        assert _outs(dut) == (_reset_vec(), MIXED_RESET), f"edge {edge}: left reset: {_outs(dut)}"


@cocotb.test()
async def test_latency_after_release(dut):
    await _start(dut)
    await ClockCycles(dut.clk_i, 3)
    await _release(dut)
    seen = await _measure_latency(dut)
    expected = {i: _stages(i) for i in range(N_MATRIX)}
    expected["mixed"] = MIXED_STAGES
    assert seen == expected, f"latency (edges after release) wrong: {seen} != {expected}"


@cocotb.test()
async def test_reset_value_is_async_clear(dut):
    await _start(dut, hold_reset=False)
    await ClockCycles(dut.clk_i, 8)  # data fully propagated through the deepest chain
    assert _outs(dut) == (_data_vec(), MIXED_DATA), f"pre-condition: {_outs(dut)}"
    await FallingEdge(dut.clk_i)  # no clock edge for half a period
    dut.rst_n_i.value = 0
    await Timer(SETTLE_NS, units="ns")
    assert _outs(dut) == (_reset_vec(), MIXED_RESET), f"not cleared asynchronously: {_outs(dut)}"


@cocotb.test()
async def test_reset_value_reasserted_after_activity(dut):
    await _start(dut, hold_reset=False)
    await ClockCycles(dut.clk_i, 8)
    await FallingEdge(dut.clk_i)
    dut.rst_n_i.value = 0
    await ClockCycles(dut.clk_i, 3)
    assert _outs(dut) == (_reset_vec(), MIXED_RESET), f"reset not re-applied: {_outs(dut)}"
    await _release(dut)
    seen = await _measure_latency(dut)
    expected = {i: _stages(i) for i in range(N_MATRIX)}
    expected["mixed"] = MIXED_STAGES
    assert seen == expected, f"re-sync latency wrong: {seen} != {expected}"
