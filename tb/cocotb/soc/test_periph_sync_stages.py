"""
test_periph_sync_stages.py -- bead claude_verilog_test-xtaa.

One cheap test per peripheral family proving that the SYNC_STAGES pass-through
reaches the cdc_sync inside the peripheral: with SYNC_STAGES=EXPECT_STAGES
(default 3) an input change becomes visible on the synchronised internal net
after exactly EXPECT_STAGES clock edges, not one sooner, and the reset value of
that net is held during reset.

The DUT is chosen by the make target (TOPLEVEL); this module dispatches on the
top-level name:
  uart_controller      uart_rx_i     -> uart_rx_sync_q        (reset value 1, idle-high)
  interrupt_controller irq_src_i[0]  -> irq_src_sync_q[0]     (reset value 0)
  spi_controller       spi_miso_i    -> spi_miso_sync_q       (reset value 0)
  tb_gpio              gpio_in_i[0]  -> u_dut.gpio_in_sync_q[0] (reset value 0)

Run via `make periph_sync_stages` (four sub-makes, each its own sim_build as
-GSYNC_STAGES is part of the build key). The default-depth (2) behaviour of
every peripheral is covered by that peripheral's own existing suite.
"""

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

CLK_PERIOD_NS = 10
SETTLE_NS = 1

# name -> (input handle path, sync handle path, bit index, reset value)
_DUTS = {
    "uart_controller": ("uart_rx_i", "uart_rx_sync_q", None, 1),
    "interrupt_controller": ("irq_src_i", "irq_src_sync_q", 0, 0),
    "spi_controller": ("spi_miso_i", "spi_miso_sync_q", None, 0),
    "tb_gpio": ("gpio_in_i", "u_dut.gpio_in_sync_q", 0, 0),
}


def _handle(dut, path):
    h = dut
    for part in path.split("."):
        h = getattr(h, part)
    return h


def _bit(handle, idx):
    v = int(handle.value)
    return v if idx is None else (v >> idx) & 1


def _drive(handle, idx, bit):
    if idx is None:
        handle.value = bit
    else:
        cur = int(handle.value)
        handle.value = (cur & ~(1 << idx)) | (bit << idx)


@cocotb.test()
async def test_sync_stages_latency(dut):
    name = os.environ.get("SYNC_PERIPH", "")
    assert name in _DUTS, f"set SYNC_PERIPH to one of {sorted(_DUTS)} (got {name!r})"
    expect = int(os.environ.get("EXPECT_STAGES", "3"))
    in_path, sync_path, idx, rst_val = _DUTS[name]
    in_h, sync_h = _handle(dut, in_path), _handle(dut, sync_path)

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())

    # Quiesce everything the peripheral exposes, input at its reset/idle level.
    for sig in ("psel", "penable", "pwrite", "paddr", "pwdata", "pstrb"):
        if hasattr(dut, sig):
            getattr(dut, sig).value = 0
    if idx is None:
        in_h.value = rst_val
    else:
        in_h.value = 0
    dut.rst_n.value = 0

    for _ in range(6):
        await RisingEdge(dut.clk)
    await Timer(SETTLE_NS, units="ns")
    assert _bit(sync_h, idx) == rst_val, f"{name}: reset value {rst_val} not held, got {_bit(sync_h, idx)}"

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(expect + 2):  # let the chain settle to the idle level
        await RisingEdge(dut.clk)
    await Timer(SETTLE_NS, units="ns")
    idle = _bit(sync_h, idx)

    # Flip the input away from the idle level on a falling edge, count rising edges.
    await FallingEdge(dut.clk)
    _drive(in_h, idx, 1 - idle)
    seen = None
    for edge in range(1, expect + 4):
        await RisingEdge(dut.clk)
        await Timer(SETTLE_NS, units="ns")
        if _bit(sync_h, idx) != idle:
            seen = edge
            break
    assert seen == expect, f"{name}: SYNC_STAGES latency {seen} edges, expected {expect}"
