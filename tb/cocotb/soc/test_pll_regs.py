"""
test_pll_regs.py -- Phase 7 (M-c) PLL AXI-Lite register interface test.

SUPERSEDED by test_pll_apb_regs.py. pll_axil_regs no longer exists, so this file cannot
elaborate and no Make target runs it. The `pll_regs` target is an alias for pll_apb_regs.
Historical DUT:
tb_pll_axil_regs (standalone wrapper, instantiated pll_axil_regs directly).
Register map (local byte offset, 12-bit address): 0x000 CONTROL [RW] ([0] pll_enable, [7:4] div_n,
[9:8] post_div_sel); 0x004 STATUS [RO] ([0] locked, mirrors pll_locked_i); 0x008 RSVD [RO] reads
0, writes ignored. Why a standalone wrapper and not tb_soc_pll: driving the SoC-internal
periph_axil_* nets from the AXI4LiteMaster BFM hangs under Verilator. axi4_to_axilite drives those
nets by continuous assigns (e.g. `assign m_axil_arvalid = (rs_q == RS_AR);`), and RTL evaluation
overrides a cocotb write in the same time step. The BFM wrote arvalid=1, the assign drove it back to
0, the AR handshake never fired, and the BFM's loop spun forever (the test_pll_regs_status_locked
hang). The fix is a standalone wrapper (the pattern of the timer, uart, spi, dma and irq
benches) whose s_axil_* signals are true top-level inputs, so the BFM owns them. A companion RTL
change extended soc_addr_map_pkg.sv PERIPH_LIMIT to 0x2000_7FFF, so CPU reads of the PLL registers
route to the axi4_to_axilite bridge and the AXI4 crossbar does not DECERR them.
Tests: status_locked (inject pll_locked_i=1, read STATUS at 0x004, bit 0 == 1);
control_write_readback (write CONTROL with pll_enable=1, div_n=0xA, post_div_sel=2'b01; only the
WMASK=0x03F1 bits are stored); status_readonly (writing all-ones to STATUS changes nothing);
test_pll_regs_decode_and_enable (renamed from test_pll_regs_slave_index_6: write and read CONTROL at
0x000, bresp and rresp OKAY, no DECERR).
Doc: tm:suite:soc-test-pll-regs
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.axi4lite_master import AXI4LiteMaster

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10      # same as the SoC reference clock

# Local byte offsets (pll_axil_regs uses 12-bit local address)
CTRL_OFFSET  = 0x000   # CONTROL register
STAT_OFFSET  = 0x004   # STATUS  register
RSVD_OFFSET  = 0x008   # RSVD    register

# CONTROL writable bit mask (pll_axil_regs.sv WMASK[0] = 32'h0000_03F1)
#   bit[0]    = pll_enable
#   bits[7:4] = div_n (feedback_div)
#   bits[9:8] = post_div_sel
CTRL_WMASK = 0x0000_03F1

# AXI-Lite transaction timeout (cycles)
AXIL_TIMEOUT_CYCLES = 100

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
    Start clock and run reset.  The standalone DUT has no PLL bootstrap
    dependency — rst_n is a plain synchronous reset for the register bank.
    """
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n.value      = 0
    dut.pll_locked_i.value = 0
    # Initialise BFM-facing inputs to idle
    dut.s_axil_awvalid.value = 0
    dut.s_axil_awaddr.value  = 0
    dut.s_axil_awprot.value  = 0
    dut.s_axil_wvalid.value  = 0
    dut.s_axil_wdata.value   = 0
    dut.s_axil_wstrb.value   = 0xF
    dut.s_axil_bready.value  = 1
    dut.s_axil_arvalid.value = 0
    dut.s_axil_araddr.value  = 0
    dut.s_axil_arprot.value  = 0
    dut.s_axil_rready.value  = 1

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def _make_axil_bfm(dut) -> AXI4LiteMaster:
    """
    BFM drives the DUT's top-level s_axil_* ports directly.
    These are true input ports (not driven by RTL assigns), so the BFM
    owns them cleanly — no multiple-driver conflict with any bridge.
    """
    return AXI4LiteMaster(dut, "s_axil_", dut.clk)


async def _axil_write(bfm: AXI4LiteMaster, addr: int, data: int) -> int:
    """Issue one AXI4-Lite write; return bresp."""
    resp = await bfm.write(addr, data)
    return resp


async def _axil_read(bfm: AXI4LiteMaster, addr: int) -> tuple:
    """Issue one AXI4-Lite read; return (data, rresp)."""
    data, resp = await bfm.read(addr)
    return data, resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_pll_regs_status_locked(dut):
    """
    STATUS[0] (locked bit) must mirror pll_locked_i.

    Flow:
      1. Start clock + reset.
      2. Assert pll_locked_i = 1 at the DUT top port (hw_wen path always ON).
      3. Wait one cycle for STATUS register to latch locked=1.
      4. Read STATUS at offset 0x004; assert bit[0]==1 and rresp==OKAY.
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    # Inject locked signal — hw_wen[STATUS]=1'b1 in pll_axil_regs so the
    # register bank latches this value on the next rising edge.
    dut.pll_locked_i.value = 1
    await ClockCycles(dut.clk, 2)   # one latch cycle + margin

    bfm = _make_axil_bfm(dut)
    data, rresp = await _axil_read(bfm, STAT_OFFSET)

    assert rresp == 0, f"STATUS read returned non-OKAY rresp={rresp}"
    assert (data & 0x1) == 1, (
        f"STATUS[0] (locked) expected 1 after pll_locked_i=1, "
        f"got STATUS=0x{data:08x}"
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

    bfm = _make_axil_bfm(dut)

    wr_val   = (1 << 0) | (0xA << 4) | (0x1 << 8)   # = 0x000002A1
    expected = wr_val & CTRL_WMASK                    # = 0x000002A1

    bresp = await _axil_write(bfm, CTRL_OFFSET, wr_val)
    assert bresp == 0, f"CONTROL write returned non-OKAY bresp={bresp}"
    dut._log.info(f"CONTROL write 0x{wr_val:08x} accepted (bresp=OKAY)")

    # Allow one cycle for register bank to latch
    await ClockCycles(dut.clk, 2)

    data, rresp = await _axil_read(bfm, CTRL_OFFSET)
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
    writes; the write is silently discarded by the register bank WMASK=0).
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    # Lock the PLL so STATUS[0]=1 gives a non-trivial initial value.
    dut.pll_locked_i.value = 1
    await ClockCycles(dut.clk, 2)

    bfm = _make_axil_bfm(dut)

    data_before, rresp1 = await _axil_read(bfm, STAT_OFFSET)
    assert rresp1 == 0, f"STATUS pre-write read rresp={rresp1}"
    dut._log.info(f"STATUS before write: 0x{data_before:08x}")

    # Attempt to write all-ones to STATUS — should be silently discarded
    bresp = await _axil_write(bfm, STAT_OFFSET, 0xFFFF_FFFF)
    assert bresp == 0, f"STATUS write bresp={bresp} (expected OKAY even for RO)"

    await ClockCycles(dut.clk, 2)

    data_after, rresp2 = await _axil_read(bfm, STAT_OFFSET)
    assert rresp2 == 0, f"STATUS post-write read rresp={rresp2}"
    dut._log.info(f"STATUS after write attempt: 0x{data_after:08x}")

    assert data_after == data_before, (
        f"STATUS changed after write attempt: "
        f"before=0x{data_before:08x}, after=0x{data_after:08x} — "
        "register bank WMASK[STATUS]=0 must suppress all SW writes"
    )
    dut._log.info("STATUS RO property confirmed — write was discarded — PASS")


@cocotb.test()
async def test_pll_regs_decode_and_enable(dut):
    """
    Explicit register-bank decode verification: write+read CONTROL at offset
    0x000 and confirm no DECERR (the register bank responds to all in-range
    word offsets with OKAY).  Also verifies pll_enable_o output toggles.

    Previously named test_pll_regs_slave_index_6 (which tested the full SoC
    AXI-Lite interconnect decode of AXIL_PLL=6).  That decode is now verified
    by the companion PERIPH_LIMIT RTL fix (soc_addr_map_pkg.sv) and the
    soc_periph_map_pkg.sv AXIL_SLV_BASE[6] entry.  The register-bank unit test
    here verifies the slave itself does not DECERR in-range accesses.
    """
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    bfm = _make_axil_bfm(dut)

    # Write a distinguishable value: pll_enable=1 only
    wr_val = 0x0000_0001
    bresp = await _axil_write(bfm, CTRL_OFFSET, wr_val)
    assert bresp != 3, (
        f"CONTROL write at offset 0x{CTRL_OFFSET:03x} returned DECERR (bresp=3) — "
        "register bank should return OKAY for all in-range offsets"
    )
    assert bresp == 0, (
        f"CONTROL write at offset 0x{CTRL_OFFSET:03x} returned bresp={bresp} (not OKAY)"
    )
    dut._log.info(f"Write offset 0x{CTRL_OFFSET:03x}: bresp=OKAY")

    await ClockCycles(dut.clk, 2)

    # Verify pll_enable_o reflects the written value
    assert int(dut.pll_enable_o.value) == 1, (
        f"pll_enable_o expected 1 after writing CONTROL[0]=1, "
        f"got {int(dut.pll_enable_o.value)}"
    )

    data, rresp = await _axil_read(bfm, CTRL_OFFSET)
    assert rresp == 0, (
        f"CONTROL read at offset 0x{CTRL_OFFSET:03x} returned rresp={rresp}"
    )
    assert (data & 0x1) == (wr_val & 0x1), (
        f"Readback mismatch: wrote pll_enable=1, got CONTROL=0x{data:08x}"
    )
    dut._log.info(
        f"Read offset 0x{CTRL_OFFSET:03x}: data=0x{data:08x}, rresp=OKAY, "
        f"pll_enable_o={int(dut.pll_enable_o.value)} — PASS"
    )
