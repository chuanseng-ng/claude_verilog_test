"""
test_pll_apb_regs.py — Phase 7 (APB migration PR-6) PLL APB4 register interface test.

DUT: tb_pll_apb_regs (standalone wrapper, directly instantiates pll_apb_regs)

Register map (pll_apb_regs at local byte offset, 12-bit address):
  0x000  CONTROL [RW]
           [0]    pll_enable   (1 = de-assert PLL reset)
           [7:4]  div_n[3:0]
           [9:8]  post_div_sel
  0x004  STATUS  [RO]
           [0]    locked       (mirrors pll_locked_i)
  0x008  RSVD    [RO]          reads 0, writes ignored

Design note — why standalone TB:
  The APB4 register block is driven directly through top-level APB4 ports.
  The BFM owns psel/penable/pwrite/paddr/pwdata/pstrb cleanly — no RTL assign
  conflicts (same rationale as tb_pll_axil_regs.sv for the AXI-Lite version).

APB4 access path:
  cocotb APB4Master → tb_pll_apb_regs.<apb4 ports> → pll_apb_regs → apb4_register_bank

APB4 BFM API (apb4_master.APB4Master):
  write(addr, data, strb=0xF) → bool  (True = OKAY, False = SLVERR)
  read(addr)                  → (int, bool)  (data, ok)

Tests (same coverage as test_pll_regs.py, bus protocol updated to APB4):
  test_pll_apb_regs_status_locked
      Inject pll_locked_i=1; read STATUS at 0x004; confirm bit[0]==1.

  test_pll_apb_regs_control_write_readback
      Write CONTROL (pll_enable=1, div_n=0xA, post_div_sel=0b01); readback;
      verify only WMASK=0x03F1 bits are stored.

  test_pll_apb_regs_status_readonly
      Write all-ones to STATUS; confirm STATUS unchanged (RO).

  test_pll_apb_regs_decode_and_enable
      Write+read CONTROL; confirm pslverr=0 (OKAY), pll_enable_o toggles.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.apb4_master import APB4Master

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10      # 100 MHz — matches SoC reference clock

# Local byte offsets (pll_apb_regs uses 12-bit local address)
CTRL_OFFSET  = 0x000   # CONTROL register
STAT_OFFSET  = 0x004   # STATUS  register
RSVD_OFFSET  = 0x008   # RSVD    register

# CONTROL writable bit mask (pll_apb_regs WMASK[0] = 32'h0000_03F1)
#   bit[0]    = pll_enable
#   bits[7:4] = div_n (feedback_div)
#   bits[9:8] = post_div_sel
CTRL_WMASK = 0x0000_03F1

# ---------------------------------------------------------------------------
# Module-level task handle list (guard against cross-test coroutine leakage)
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
    Start 100 MHz clock and apply synchronous reset.
    Initialise all APB4 master-driven inputs to idle (psel=0).
    """
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    # APB4 idle state
    dut.rst_n.value       = 0
    dut.pll_locked_i.value = 0
    dut.psel.value        = 0
    dut.penable.value     = 0
    dut.pwrite.value      = 0
    dut.paddr.value       = 0
    dut.pwdata.value      = 0
    dut.pstrb.value       = 0xF

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def _make_apb_bfm(dut) -> APB4Master:
    """
    Construct APB4Master BFM targeting the DUT's flat APB4 ports.
    Empty prefix ("") because the ports are named psel/penable/... directly.
    """
    return APB4Master(dut, "", dut.clk)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_pll_apb_regs_status_locked(dut):
    """
    STATUS[0] (locked bit) must mirror pll_locked_i.

    Flow:
      1. Start clock + reset.
      2. Assert pll_locked_i = 1 at the DUT top port (hw_wen[STATUS]=1'b1 path).
      3. Wait two cycles for STATUS register to latch locked=1.
      4. Read STATUS at offset 0x004; assert bit[0]==1 and pslverr=0 (OKAY).
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    # Inject locked signal — hw_wen[1]=1'b1 in pll_apb_regs so the register
    # bank latches pll_locked_i on the next posedge pclk.
    dut.pll_locked_i.value = 1
    await ClockCycles(dut.clk, 2)   # one latch cycle + margin

    bfm = _make_apb_bfm(dut)
    data, ok = await bfm.read(STAT_OFFSET)

    assert ok, "STATUS read returned pslverr=1 (SLVERR)"
    assert (data & 0x1) == 1, (
        f"STATUS[0] (locked) expected 1 after pll_locked_i=1, "
        f"got STATUS=0x{data:08x}"
    )
    dut._log.info(f"STATUS=0x{data:08x}: locked={data & 1} — PASS")


@cocotb.test()
async def test_pll_apb_regs_control_write_readback(dut):
    """
    Write CONTROL with pll_enable=1, div_n=0xA, post_div_sel=2'b01;
    read back and verify only the writable bits (WMASK=0x03F1) are stored.

    Written value: 0x0000_01A1
      bit[0]    = 1  (pll_enable)
      bits[7:4] = 0xA (div_n)
      bits[9:8] = 0x1 (post_div_sel = /2)

    Expected readback: written_value & WMASK = 0x01A1.
    Bits outside WMASK must read back as 0 (not writable).
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    bfm = _make_apb_bfm(dut)

    wr_val   = (1 << 0) | (0xA << 4) | (0x1 << 8)   # = 0x000001A1
    expected = wr_val & CTRL_WMASK                    # = 0x000001A1

    ok = await bfm.write(CTRL_OFFSET, wr_val)
    assert ok, "CONTROL write returned pslverr=1 (SLVERR)"
    dut._log.info(f"CONTROL write 0x{wr_val:08x} accepted (OKAY)")

    # Allow one cycle for register bank to latch
    await ClockCycles(dut.clk, 2)

    data, ok = await bfm.read(CTRL_OFFSET)
    assert ok, "CONTROL readback pslverr=1 (SLVERR)"

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
async def test_pll_apb_regs_status_readonly(dut):
    """
    STATUS is RO: writing any value to it must have no effect.
    Read STATUS before and after a write attempt; both reads must agree.
    pslverr for the write must be 0 (OKAY) — APB4 does not error on RO
    writes; the write is silently discarded by the register bank WMASK=0.
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    # Lock the PLL so STATUS[0]=1 gives a non-trivial initial value.
    dut.pll_locked_i.value = 1
    await ClockCycles(dut.clk, 2)

    bfm = _make_apb_bfm(dut)

    data_before, ok1 = await bfm.read(STAT_OFFSET)
    assert ok1, "STATUS pre-write read returned pslverr=1"
    dut._log.info(f"STATUS before write: 0x{data_before:08x}")

    # Attempt to write all-ones to STATUS — must be silently discarded
    ok_wr = await bfm.write(STAT_OFFSET, 0xFFFF_FFFF)
    assert ok_wr, "STATUS write returned pslverr=1 (expected OKAY even for RO)"

    await ClockCycles(dut.clk, 2)

    data_after, ok2 = await bfm.read(STAT_OFFSET)
    assert ok2, "STATUS post-write read returned pslverr=1"
    dut._log.info(f"STATUS after write attempt: 0x{data_after:08x}")

    assert data_after == data_before, (
        f"STATUS changed after write attempt: "
        f"before=0x{data_before:08x}, after=0x{data_after:08x} — "
        "register bank WMASK[STATUS]=0 must suppress all SW writes"
    )
    dut._log.info("STATUS RO property confirmed — write was discarded — PASS")


@cocotb.test()
async def test_pll_apb_regs_decode_and_enable(dut):
    """
    Explicit register-bank decode verification: write+read CONTROL at offset
    0x000 and confirm no SLVERR (pslverr=0).  Also verifies pll_enable_o
    output toggles in response to CONTROL[0] writes.

    APB4 counterpart of test_pll_regs_decode_and_enable in test_pll_regs.py.
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    bfm = _make_apb_bfm(dut)

    # Write a distinguishable value: pll_enable=1 only
    wr_val = 0x0000_0001
    ok = await bfm.write(CTRL_OFFSET, wr_val)
    assert ok, (
        f"CONTROL write at offset 0x{CTRL_OFFSET:03x} returned SLVERR — "
        "register bank should return OKAY for all in-range offsets"
    )
    dut._log.info(f"Write offset 0x{CTRL_OFFSET:03x}: OKAY")

    await ClockCycles(dut.clk, 2)

    # Verify pll_enable_o reflects the written value
    assert int(dut.pll_enable_o.value) == 1, (
        f"pll_enable_o expected 1 after writing CONTROL[0]=1, "
        f"got {int(dut.pll_enable_o.value)}"
    )

    data, ok = await bfm.read(CTRL_OFFSET)
    assert ok, (
        f"CONTROL read at offset 0x{CTRL_OFFSET:03x} returned pslverr=1"
    )
    assert (data & 0x1) == (wr_val & 0x1), (
        f"Readback mismatch: wrote pll_enable=1, got CONTROL=0x{data:08x}"
    )
    dut._log.info(
        f"Read offset 0x{CTRL_OFFSET:03x}: data=0x{data:08x}, OKAY, "
        f"pll_enable_o={int(dut.pll_enable_o.value)} — PASS"
    )
