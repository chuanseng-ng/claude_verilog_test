"""
test_pll_regs.py — Phase 7 (M-c) PLL AXI-Lite register interface test.

DUT: tb_soc_pll (wraps soc_top with PLL_IMPL="STUB")

Register map (pll_axil_regs at AXIL_PLL=6, base 0x2000_7000):
  0x2000_7000  CONTROL [RW]
                 [0]    pll_enable   (1 = de-assert PLL reset)
                 [7:4]  div_n[3:0]
                 [9:8]  post_div_sel
  0x2000_7004  STATUS  [RO]
                 [0]    locked       (mirrors pll_locked_o)

Tests:
  test_pll_regs_status_locked
      After boot-up (lock asserted), read STATUS at 0x2000_7004 via
      AXI-Lite BFM; confirm bit[0]==1 (locked bit mirrors pll_locked_o).

  test_pll_regs_control_write_readback
      Write CONTROL with a non-trivial value (pll_enable=1, div_n=0xA,
      post_div_sel=2'b01); read back; confirm the written bits are reflected
      (only writable bits per WMASK = 0x000003F1).

  test_pll_regs_status_readonly
      Write to STATUS address; confirm the value does NOT change (RO register).

  test_pll_regs_slave_index_6
      Issue a write+read to 0x2000_7000 explicitly verifying the AXI-Lite
      interconnect decodes AXIL_PLL=6 at base 0x2000_7000 correctly (DECERR
      would indicate a missing or mis-indexed decode entry).

AXI-Lite access path:
  cocotb → external AXI4 master → soc_top.u_xbar (S2 periph) →
  axi4_to_axilite → axi_lite_interconnect → pll_axil_regs

Because tb_soc_pll does not expose AXI master ports directly, this test
drives the PLL reg space via a firmware-less approach: the AXI4-Lite master
BFM is wired to the soc_top internal net u_soc.periph_axil_* using
Verilator's --public-flat-rw hierarchy.  The standard pattern used for
test_timer.py / test_irq_ctrl.py is applied: instantiate AXI4LiteMaster
using a flat-hierarchy signal prefix.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.axi4lite_master import AXI4LiteMaster

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2       # 500 MHz

# PLL AXI-Lite slave base (soc_periph_map_pkg.sv AXIL_PLL_BASE)
PLL_BASE         = 0x2000_7000
PLL_CTRL_OFFSET  = 0x000        # CONTROL register
PLL_STAT_OFFSET  = 0x004        # STATUS  register

CTRL_ADDR = PLL_BASE + PLL_CTRL_OFFSET
STAT_ADDR = PLL_BASE + PLL_STAT_OFFSET

# CONTROL writable bit mask (from pll_axil_regs.sv WMASK[0] = 32'h0000_03F1)
#   bit[0]    = pll_enable
#   bits[7:4] = div_n (feedback_div)
#   bits[9:8] = post_div_sel
CTRL_WMASK = 0x0000_03F1

# Stub lock budget (STUB_LOCK_CYCLES=16 + margin)
LOCK_TIMEOUT_CYCLES = 60

# AXI-Lite transaction timeout
AXIL_TIMEOUT_CYCLES = 200

# ---------------------------------------------------------------------------
# Module-level task handle list
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _start_clock_and_reset(dut) -> None:
    """
    Start clock, initialise tie-off inputs, assert then release reset.

    Bootstrap: pll_enable is forced to 1 before releasing rst_n_i so the PLL
    lock counter can run.  Without this, pll_rst_n = rst_n_i & pll_enable = 0
    forever because pll_axil_regs (which drives pll_enable) is held in reset
    by core_rst_n = rst_n_i & pll_locked (chicken-and-egg).

    Once pll_locked fires, core_rst_n releases and pll_axil_regs comes out of
    reset.  The AXI-Lite tests then exercise the full reg-interface path from
    the periph_axil_ bridge into pll_axil_regs.

    Verilator flat name (--public-flat-rw):
      dut.u_soc__DOT__pll_enable  (CData, 1-bit)
    """
    clk_task = await cocotb.start(Clock(dut.clk_i, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n_i.value       = 0
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1
    dut.spi_miso_i.value    = 0
    # Bootstrap pll_enable before reset release
    dut.u_soc.pll_enable.value = 1
    await ClockCycles(dut.clk_i, 8)
    dut.rst_n_i.value = 1


async def _wait_for_lock(dut, timeout: int) -> bool:
    for _ in range(timeout):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.pll_locked_o.value) == 1:
            return True
    return False


def _make_axil_bfm(dut) -> AXI4LiteMaster:
    """
    Build an AXI4LiteMaster BFM targeting the pll_axil_regs slave via the
    full SoC AXI-Lite interconnect.

    The AXI4-Lite interconnect slave ports are exposed as flat signals by
    Verilator --public-flat-rw under the hierarchy:
      tb_soc_pll.u_soc.u_axil_ic.s_axil_*[AXIL_PLL]

    However, Verilator flattens unpacked-array indices to signal_N naming
    (e.g. axil_s_awvalid_6).  Rather than relying on internals, we drive the
    AXI4-to-AXI4-Lite bridge master port directly through the public hierarchy:
      tb_soc_pll.u_soc.periph_axil_*

    This is identical to the approach used in test_soc_coherency.py and
    test_cpu_gpu_irq.py which also use internal SoC nets for stimulus.
    The periph_axil_* nets are the output of the axi4_to_axilite adapter and
    the input to axi_lite_interconnect — a single-master / N-slave fabric.
    Driving these nets exercises the full decode path through the interconnect
    to pll_axil_regs.
    """
    # Drive through soc_top's periph_axil_* nets (axi4_to_axilite output, single-master
    # input to axi_lite_interconnect).  AXI4LiteMaster does getattr(dut, f"{prefix}{sig}")
    # so we pass dut.u_soc as the DUT handle and "periph_axil_" as the prefix.
    # This resolves to dut.u_soc.periph_axil_awvalid etc. — the same hierarchical
    # pattern used by test_boot.py (dut.u_soc.u_boot_rom.mem / dut.u_soc.u_sram.mem).
    return AXI4LiteMaster(dut.u_soc, "periph_axil_", dut.clk_i)


async def _axil_write(bfm: AXI4LiteMaster, addr: int, data: int,
                      timeout: int = AXIL_TIMEOUT_CYCLES,
                      clock=None) -> int:
    """
    Issue one AXI4-Lite write; return bresp.
    The BFM's write() method drives both AW and W simultaneously and
    waits for B channel — matches the axi_lite_register_bank flow.
    """
    resp = await bfm.write(addr, data)
    return resp


async def _axil_read(bfm: AXI4LiteMaster, addr: int,
                     timeout: int = AXIL_TIMEOUT_CYCLES) -> tuple:
    """Issue one AXI4-Lite read; return (data, rresp)."""
    data, resp = await bfm.read(addr)
    return data, resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_pll_regs_status_locked(dut):
    """
    STATUS[0] (locked bit) must read 1 after pll_locked_o has asserted.

    Flow:
      1. Start clock + reset.
      2. Wait for pll_locked_o via top-level port (up to LOCK_TIMEOUT_CYCLES).
      3. Read STATUS register via AXI-Lite BFM through the full periph path.
      4. Assert bit[0] == 1 and rresp == OKAY (0).
    """
    _kill_active_tasks()

    await _start_clock_and_reset(dut)

    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, (
        f"pll_locked_o did not assert within {LOCK_TIMEOUT_CYCLES} cycles; "
        "cannot verify STATUS register"
    )
    dut._log.info("pll_locked_o asserted — proceeding to STATUS read")

    # Give pll_axil_regs one more cycle to push hw_wdata[STATUS] = {31b0, 1}
    # (hw_wen[1]=1 always; latches on next rising edge of clk_i / core_clk).
    await ClockCycles(dut.clk_i, 4)

    bfm = _make_axil_bfm(dut)
    data, rresp = await _axil_read(bfm, STAT_ADDR)

    assert rresp == 0, f"STATUS read returned non-OKAY rresp={rresp}"
    assert (data & 0x1) == 1, (
        f"STATUS[0] (locked) expected 1 after lock, got STATUS=0x{data:08x}"
    )
    dut._log.info(f"STATUS=0x{data:08x}: locked={data & 1} — PASS")


@cocotb.test()
async def test_pll_regs_control_write_readback(dut):
    """
    Write CONTROL with pll_enable=1, div_n=0xA, post_div_sel=2'b01;
    read back and verify only the writable bits (WMASK=0x03F1) are stored.

    Written value: 0x0000_02A1
      bit[0]    = 1  (pll_enable)
      bits[7:4] = 0xA (div_n)
      bits[9:8] = 0x1 (post_div_sel = /2)

    Expected readback: written_value & WMASK = 0x02A1.
    Bits outside WMASK must read back as 0 (not writable).
    """
    _kill_active_tasks()

    await _start_clock_and_reset(dut)

    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, "pll_locked_o did not assert; skipping reg test"

    await ClockCycles(dut.clk_i, 4)

    bfm = _make_axil_bfm(dut)

    wr_val = (1 << 0) | (0xA << 4) | (0x1 << 8)   # = 0x000002A1
    expected = wr_val & CTRL_WMASK                  # = 0x000002A1 (all bits in mask)

    bresp = await _axil_write(bfm, CTRL_ADDR, wr_val)
    assert bresp == 0, f"CONTROL write returned non-OKAY bresp={bresp}"
    dut._log.info(f"CONTROL write 0x{wr_val:08x} accepted (bresp=OKAY)")

    # Allow one cycle for register bank to latch
    await ClockCycles(dut.clk_i, 2)

    data, rresp = await _axil_read(bfm, CTRL_ADDR)
    assert rresp == 0, f"CONTROL readback rresp={rresp} != OKAY"

    actual = data & CTRL_WMASK
    assert actual == expected, (
        f"CONTROL readback mismatch: "
        f"wrote 0x{wr_val:08x}, expected masked 0x{expected:08x}, "
        f"got raw 0x{data:08x} (masked 0x{actual:08x})"
    )
    dut._log.info(
        f"CONTROL readback 0x{data:08x}: "
        f"pll_enable={data & 1}, div_n=0x{(data >> 4) & 0xF:X}, "
        f"post_div_sel={(data >> 8) & 3} — PASS"
    )


@cocotb.test()
async def test_pll_regs_status_readonly(dut):
    """
    STATUS is RO: writing any value to it must have no effect.
    Read STATUS before and after a write attempt; both reads must agree.
    bresp for the write must still be OKAY (AXI-Lite does not error on RO
    writes; the write is silently discarded by the register bank).
    """
    _kill_active_tasks()

    await _start_clock_and_reset(dut)

    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, "pll_locked_o did not assert; skipping RO test"

    await ClockCycles(dut.clk_i, 4)

    bfm = _make_axil_bfm(dut)

    data_before, rresp1 = await _axil_read(bfm, STAT_ADDR)
    assert rresp1 == 0, f"STATUS pre-write read rresp={rresp1}"
    dut._log.info(f"STATUS before write: 0x{data_before:08x}")

    # Attempt to write all-ones to STATUS — should be silently discarded
    bresp = await _axil_write(bfm, STAT_ADDR, 0xFFFF_FFFF)
    assert bresp == 0, f"STATUS write bresp={bresp} (expected OKAY even for RO)"

    await ClockCycles(dut.clk_i, 2)

    data_after, rresp2 = await _axil_read(bfm, STAT_ADDR)
    assert rresp2 == 0, f"STATUS post-write read rresp={rresp2}"
    dut._log.info(f"STATUS after write attempt: 0x{data_after:08x}")

    assert data_after == data_before, (
        f"STATUS changed after write attempt: "
        f"before=0x{data_before:08x}, after=0x{data_after:08x} — "
        "register bank WMASK[STATUS]=0 must suppress all SW writes"
    )
    dut._log.info("STATUS RO property confirmed — write was discarded")


@cocotb.test()
async def test_pll_regs_slave_index_6(dut):
    """
    Explicit decode verification: write+read CONTROL at full absolute address
    0x2000_7000 and confirm the AXI-Lite interconnect decodes slave index 6
    (AXIL_PLL) without DECERR.

    A DECERR (rresp or bresp == 3) would indicate the interconnect's
    AXIL_N_SLAVES was not extended from 6 to 7, or the PLL base address
    was not added to the AXIL_SLV_BASE/AXIL_SLV_LIMIT arrays.
    """
    _kill_active_tasks()

    await _start_clock_and_reset(dut)

    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, "pll_locked_o did not assert; skipping decode test"

    await ClockCycles(dut.clk_i, 4)

    bfm = _make_axil_bfm(dut)

    # Write a distinguishable value: pll_enable=1 only
    wr_val = 0x0000_0001
    bresp = await _axil_write(bfm, CTRL_ADDR, wr_val)
    assert bresp != 3, (
        f"CONTROL write at 0x{CTRL_ADDR:08x} returned DECERR (bresp=3) — "
        "AXIL_PLL slave index 6 is not decoded by the interconnect. "
        "Check soc_periph_map_pkg.sv AXIL_N_SLAVES and AXIL_SLV_BASE[6]."
    )
    assert bresp == 0, (
        f"CONTROL write at 0x{CTRL_ADDR:08x} returned bresp={bresp} (not OKAY)"
    )
    dut._log.info(f"Write to 0x{CTRL_ADDR:08x}: bresp=OKAY (slave index 6 decoded)")

    await ClockCycles(dut.clk_i, 2)

    data, rresp = await _axil_read(bfm, CTRL_ADDR)
    assert rresp != 3, (
        f"CONTROL read at 0x{CTRL_ADDR:08x} returned DECERR (rresp=3) — "
        "AXI-Lite interconnect decode failure for AXIL_PLL=6."
    )
    assert rresp == 0, (
        f"CONTROL read at 0x{CTRL_ADDR:08x} returned rresp={rresp}"
    )
    assert (data & 0x1) == (wr_val & 0x1), (
        f"Readback mismatch: wrote pll_enable=1, got CONTROL=0x{data:08x}"
    )
    dut._log.info(
        f"Read from 0x{CTRL_ADDR:08x}: data=0x{data:08x}, rresp=OKAY — "
        "AXIL_PLL=6 decode PASS"
    )
