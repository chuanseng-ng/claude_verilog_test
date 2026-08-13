"""
test_cdc_reset_sync_scan.py — bead claude_verilog_test-07n cocotb
verification for cdc_reset_sync's DFT scan bypass mux
(rtl/soc/cdc/cdc_reset_sync.sv), via the standalone wrapper
tb_cdc_reset_sync_scan.sv.

DUT: tb_cdc_reset_sync_scan (STAGES=2, re-exports cdc_reset_sync's ports
flat: clk_i, rst_n_i, scanmode_i, scan_rst_ni, rst_n_o).

This module's ONLY new behaviour vs. the pre-07n RTL is the async-clear
source mux:
    rst_n_async = scanmode_i ? scan_rst_ni : rst_n_i
feeding every `negedge` in the STAGES-deep flop chain (see the RTL header
for why the chain is one always_ff per stage). Every test below is a
DIRECTED proof of one edge of that mux, not a CDC/metastability test --
there is no clock-domain crossing in this module, just an async-assert /
sync-deassert chain.

Tests:
  test_functional_reset_baseline
      scanmode_i=0 (scan inactive): rst_n_i alone controls rst_n_o exactly
      as before this bead (async assert, STAGES-cycle sync deassert). Proves
      the mux is a transparent pass-through in the default (no-DFT-flow)
      tie-off configuration used at every soc_top call site today.
  test_scan_rst_controls_when_scanmode_asserted
      scanmode_i=1, rst_n_i held HIGH (functional reset inactive) the whole
      time: scan_rst_ni alone asserts/deasserts rst_n_o. Proves scan_rst_ni
      is a REAL, live async clear source under scanmode_i, not decorative.
  test_rst_n_i_ignored_when_scanmode_asserted
      scanmode_i=1, scan_rst_ni held HIGH (scan reset inactive): pulsing
      rst_n_i low must NOT clear rst_n_o. Proves rst_n_i is genuinely
      bypassed while scanmode_i=1, not just OR'd/AND'd with scan_rst_ni.
  test_mux_reverts_when_scanmode_deasserted
      Enter scan mode, confirm scan_rst_ni control, drop scanmode_i back to
      0 with rst_n_i already low: rst_n_o must clear immediately (async),
      proving control reverts cleanly to rst_n_i the instant scanmode_i
      deasserts.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer, with_timeout

CLK_PERIOD_NS = 10  # 100 MHz, arbitrary — no CDC in this DUT
STAGES = 2
SETTLE_NS = 1  # small delta after driving an async control signal


async def _start(dut, *, rst_n_i=1, scanmode_i=0, scan_rst_ni=1):
    """Start the clock and drive all inputs to a known idle state."""
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n_i.value = rst_n_i
    dut.scanmode_i.value = scanmode_i
    dut.scan_rst_ni.value = scan_rst_ni
    await Timer(SETTLE_NS, units="ns")


@cocotb.test()
async def test_functional_reset_baseline(dut):
    """scanmode_i=0: rst_n_i alone drives rst_n_o (mux is a pass-through)."""
    await with_timeout(_run_functional_reset_baseline(dut), 10, "us")


async def _run_functional_reset_baseline(dut):
    # Start already in reset, scan tied inert (the soc_top tie-off shape).
    await _start(dut, rst_n_i=0, scanmode_i=0, scan_rst_ni=1)
    assert dut.rst_n_o.value == 0, "rst_n_o must be asserted (0) out of reset"

    # Deassert rst_n_i: rst_n_o must stay 0 until STAGES clean clock edges
    # have re-timed the deassertion, then read 1.
    dut.rst_n_i.value = 1
    for _ in range(STAGES):
        await RisingEdge(dut.clk_i)
        # Still settling for the first STAGES-1 edges.
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "rst_n_o must deassert after STAGES clean edges"

    # Re-assert rst_n_i: rst_n_o must clear ASYNCHRONOUSLY (no clock edge
    # needed) — this is the same assertion the pre-07n test coverage relied
    # on implicitly; kept here so a scan-mux regression that broke the
    # functional path would fail this test too.
    dut.rst_n_i.value = 0
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 0, "rst_n_o must async-assert on rst_n_i falling"


@cocotb.test()
async def test_scan_rst_controls_when_scanmode_asserted(dut):
    """scanmode_i=1, rst_n_i held high: scan_rst_ni alone must control rst_n_o."""
    await with_timeout(_run_scan_rst_controls(dut), 10, "us")


async def _run_scan_rst_controls(dut):
    # Boot out of functional reset first (STAGES edges with rst_n_i=1,
    # scan inactive) so we start from a known rst_n_o=1 state.
    await _start(dut, rst_n_i=1, scanmode_i=0, scan_rst_ni=1)
    await ClockCycles(dut.clk_i, STAGES + 1)
    assert dut.rst_n_o.value == 1, "precondition: must start deasserted"

    # Enter scan mode with scan_rst_ni already inactive (1): nothing should
    # change yet — mux selects scan_rst_ni=1, chain stays deasserted.
    dut.scanmode_i.value = 1
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "entering scan mode with scan_rst_ni=1 must not reset"

    # Drive scan_rst_ni low while rst_n_i stays HIGH the entire time: this
    # is only possible to observe if scan_rst_ni, not rst_n_i, is the live
    # async clear source.
    dut.rst_n_i.value = 1
    dut.scan_rst_ni.value = 0
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 0, (
        "scan_rst_ni falling must async-assert rst_n_o under scanmode_i=1 "
        "even though rst_n_i is held high"
    )

    # Release scan_rst_ni: rst_n_o must deassert after STAGES clean edges,
    # same sync-deassert contract as the functional path.
    dut.scan_rst_ni.value = 1
    for _ in range(STAGES):
        await RisingEdge(dut.clk_i)
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "rst_n_o must deassert after STAGES edges under scan_rst_ni release"


@cocotb.test()
async def test_rst_n_i_ignored_when_scanmode_asserted(dut):
    """scanmode_i=1, scan_rst_ni held high: pulsing rst_n_i must NOT reset the chain."""
    await with_timeout(_run_rst_n_i_ignored(dut), 10, "us")


async def _run_rst_n_i_ignored(dut):
    await _start(dut, rst_n_i=1, scanmode_i=0, scan_rst_ni=1)
    await ClockCycles(dut.clk_i, STAGES + 1)
    assert dut.rst_n_o.value == 1, "precondition: must start deasserted"

    dut.scanmode_i.value = 1
    dut.scan_rst_ni.value = 1
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "precondition: scan reset inactive, chain stays deasserted"

    # Pulse rst_n_i low then high again while scanmode_i=1/scan_rst_ni=1:
    # if rst_n_i were still in control (mux bug / stuck mux), rst_n_o would
    # drop to 0 here. It must not move at all.
    dut.rst_n_i.value = 0
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "rst_n_i falling must be IGNORED while scanmode_i=1"

    await ClockCycles(dut.clk_i, STAGES + 1)
    assert dut.rst_n_o.value == 1, "rst_n_o must remain deasserted throughout the ignored rst_n_i pulse"

    dut.rst_n_i.value = 1
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "rst_n_o must remain deasserted after the ignored rst_n_i pulse ends"


@cocotb.test()
async def test_mux_reverts_when_scanmode_deasserted(dut):
    """Dropping scanmode_i back to 0 must hand control back to rst_n_i immediately."""
    await with_timeout(_run_mux_reverts(dut), 10, "us")


async def _run_mux_reverts(dut):
    # Enter with scanmode_i=1, both resets inactive, chain deasserted.
    await _start(dut, rst_n_i=1, scanmode_i=1, scan_rst_ni=1)
    await ClockCycles(dut.clk_i, STAGES + 1)
    assert dut.rst_n_o.value == 1, "precondition: must start deasserted under scan mode"

    # Lower rst_n_i (functional reset requested) while STILL in scan mode
    # with scan_rst_ni inactive: rst_n_o must not move (rst_n_i is bypassed).
    dut.rst_n_i.value = 0
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "rst_n_i must still be bypassed here (scanmode_i=1)"

    # Now drop scanmode_i back to 0 with rst_n_i already low: control must
    # revert to rst_n_i IMMEDIATELY (async), asserting rst_n_o with no
    # clock edge required.
    dut.scanmode_i.value = 0
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 0, (
        "rst_n_o must async-assert the instant scanmode_i deasserts, given "
        "rst_n_i was already low"
    )

    # Recovery sanity: releasing rst_n_i now behaves exactly like the
    # functional-path baseline again.
    dut.rst_n_i.value = 1
    for _ in range(STAGES):
        await RisingEdge(dut.clk_i)
    await Timer(SETTLE_NS, units="ns")
    assert dut.rst_n_o.value == 1, "normal functional deassert must work again post-scan-mode"
