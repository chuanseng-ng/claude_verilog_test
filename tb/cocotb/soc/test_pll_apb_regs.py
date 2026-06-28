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
      Write CONTROL (div_n=0xA, post_div_sel=0b01); readback; verify
      SW-writable bits (WMASK=0x03F0, bits[9:4]) are stored correctly.
      GH #89 sub-check: write CONTROL=0x0000 (clear attempt on bit[0]);
      assert bit[0] stays 1 and pll_enable_o stays asserted (non-clearable).

  test_pll_apb_regs_status_readonly
      Write all-ones to STATUS; confirm STATUS unchanged (RO).

  test_pll_apb_regs_decode_and_enable
      Write+read CONTROL; confirm pslverr=0 (OKAY), pll_enable_o always 1
      (non-clearable by design, GH #89 anti-brick).
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

# CONTROL software-writable bit mask (pll_apb_regs WMASK[0] = 32'h0000_03F0, GH #89)
#   bit[0]    = pll_enable — NOT in WMASK; non-clearable by design (GH #89 anti-brick).
#               RESET_VAL[0]=1, WMASK[0]=0 → firmware writes to this bit are ignored;
#               pll_enable stays 1 at all times so firmware cannot deadlock the SoC.
#   bits[7:4] = div_n (feedback_div)   — writable
#   bits[9:8] = post_div_sel           — writable
CTRL_WMASK = 0x0000_03F0

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
    Write CONTROL with div_n=0xA, post_div_sel=2'b01 and verify:
      (a) SW-writable bits (WMASK=0x03F0: bits[9:4]) are stored correctly.
      (b) GH #89 non-clearable invariant: bit[0] (pll_enable) stays 1
          even when firmware writes 0 to it (WMASK[0]=0, RESET_VAL[0]=1).

    Pass 1 — write with bit[0]=1 (div_n=0xA, post_div_sel=/2):
      Written value : 0x0000_01A1
      SW-writable portion (CTRL_WMASK=0x03F0): 0x01A0
      bit[0] stays 1 regardless → raw readback = 0x01A1

    Pass 2 — write all-zeros (attempt to clear pll_enable):
      Written value : 0x0000_0000
      SW-writable portion: 0x0000 (div_n=0, post_div_sel=/1)
      bit[0] non-clearable → raw readback = 0x0001 (pll_enable locked high)
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    bfm = _make_apb_bfm(dut)

    # --- Pass 1: writable-field round-trip ---
    wr_val   = (1 << 0) | (0xA << 4) | (0x1 << 8)   # = 0x000001A1
    expected = wr_val & CTRL_WMASK                    # = 0x000001A0 (bit[0] excluded)

    ok = await bfm.write(CTRL_OFFSET, wr_val)
    assert ok, "CONTROL write (pass 1) returned pslverr=1 (SLVERR)"
    dut._log.info(f"CONTROL write 0x{wr_val:08x} accepted (OKAY)")

    await ClockCycles(dut.clk, 2)

    data, ok = await bfm.read(CTRL_OFFSET)
    assert ok, "CONTROL readback (pass 1) returned pslverr=1 (SLVERR)"

    actual = data & CTRL_WMASK
    assert actual == expected, (
        f"CONTROL writable-field mismatch: "
        f"wrote 0x{wr_val:08x}, expected SW-writable portion 0x{expected:08x}, "
        f"got raw 0x{data:08x} (masked 0x{actual:08x})"
    )
    # bit[0] must still be 1 (non-clearable reset value)
    assert (data & 0x1) == 1, (
        f"GH #89: pll_enable (bit[0]) not 1 after pass-1 write; CONTROL=0x{data:08x}"
    )
    dut._log.info(
        f"Pass 1 CONTROL readback 0x{data:08x}: "
        f"pll_enable={data & 1}, div_n=0x{(data >> 4) & 0xF:X}, "
        f"post_div_sel={(data >> 8) & 3} — PASS"
    )

    # --- Pass 2: GH #89 non-clearable invariant ---
    # Writing all-zeros tries to clear pll_enable. WMASK[0]=0 must suppress the
    # clear; bit[0] must remain 1 (RESET_VAL); pll_enable_o must stay asserted.
    ok2 = await bfm.write(CTRL_OFFSET, 0x0000_0000)
    assert ok2, "CONTROL write-zero (pass 2) returned pslverr=1 (SLVERR)"
    dut._log.info("CONTROL write 0x00000000 (clear attempt) accepted (OKAY)")

    await ClockCycles(dut.clk, 2)

    data2, ok3 = await bfm.read(CTRL_OFFSET)
    assert ok3, "CONTROL readback (pass 2) returned pslverr=1 (SLVERR)"

    assert (data2 & 0x1) == 1, (
        f"GH #89 VIOLATION: pll_enable (CONTROL[0]) was cleared by a firmware write — "
        f"WMASK[0]=0 must preserve reset value 1; "
        f"got CONTROL=0x{data2:08x}"
    )
    assert int(dut.pll_enable_o.value) == 1, (
        f"GH #89 VIOLATION: pll_enable_o dropped to 0 after write-zero — "
        "pll_enable_o must always be 1 (non-clearable)"
    )
    dut._log.info(
        f"Pass 2 CONTROL readback 0x{data2:08x}: "
        f"pll_enable={data2 & 1} (non-clearable confirmed), "
        f"pll_enable_o={int(dut.pll_enable_o.value)} — GH #89 PASS"
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
    0x000 and confirm no SLVERR (pslverr=0).  Verifies pll_enable_o is always
    1 (non-clearable by design, GH #89 anti-brick): WMASK[0]=0 means firmware
    writes to CONTROL[0] are ignored; pll_enable_o stays 1 regardless of what
    value is written to bit[0].

    APB4 counterpart of test_pll_regs_decode_and_enable in test_pll_regs.py.
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    bfm = _make_apb_bfm(dut)

    # Write CONTROL[0]=1 (same as reset value — OKAY, SLVERR must not fire)
    wr_val = 0x0000_0001
    ok = await bfm.write(CTRL_OFFSET, wr_val)
    assert ok, (
        f"CONTROL write at offset 0x{CTRL_OFFSET:03x} returned SLVERR — "
        "register bank should return OKAY for all in-range offsets"
    )
    dut._log.info(f"Write offset 0x{CTRL_OFFSET:03x}: OKAY")

    await ClockCycles(dut.clk, 2)

    # pll_enable_o must be 1 (non-clearable; stays at reset value)
    assert int(dut.pll_enable_o.value) == 1, (
        f"pll_enable_o expected 1 (non-clearable reset value), "
        f"got {int(dut.pll_enable_o.value)}"
    )

    data, ok = await bfm.read(CTRL_OFFSET)
    assert ok, (
        f"CONTROL read at offset 0x{CTRL_OFFSET:03x} returned pslverr=1"
    )
    assert (data & 0x1) == 1, (
        f"CONTROL[0] (pll_enable) expected 1 (non-clearable), "
        f"got CONTROL=0x{data:08x}"
    )
    dut._log.info(
        f"Read offset 0x{CTRL_OFFSET:03x}: data=0x{data:08x}, OKAY, "
        f"pll_enable_o={int(dut.pll_enable_o.value)} (non-clearable) — PASS"
    )
