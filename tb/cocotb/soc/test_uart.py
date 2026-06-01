# test_uart.py
# Phase 5 (M4) — cocotb directed-test suite for uart_controller.sv
#
# DUT:  uart_controller  (TOPLEVEL=uart_controller)
# BFM:  AXI4LiteMaster (bfm/axi4lite_master.py) drives s_axil_* registers
# Side-inputs: uart_rx_i driven to idle (1) before reset
#
# Register byte addresses
#   0x00  UART_TX     WO [7:0]  write pushes byte to TX FIFO via snoop
#   0x04  UART_RX     RO [7:0]  RX FIFO head; read pops
#   0x08  UART_STATUS RO        [0]=tx_busy [1]=tx_full [2]=tx_empty
#                               [3]=rx_empty [4]=rx_full [5]=rx_valid
#   0x0C  UART_CTRL   RW [4:0]  [0]=tx_en [1]=rx_en [2]=irq_tx_empty_en
#                               [3]=irq_rx_valid_en [4]=loopback
#   0x10  UART_BAUD   RW [15:0] D: 1 bit = (D+1) clocks
#
# Timing note:
#   BAUD=1 → 2 clocks/bit → 1 frame = 10 bits × 2 = 20 clocks.
#   Tests use generous wait windows (3× frame + AXI overhead) for reliability.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from bfm.axi4lite_master import AXI4LiteMaster

# ── Register byte addresses ───────────────────────────────────────────────────
REG_UART_TX     = 0x00
REG_UART_RX     = 0x04
REG_UART_STATUS = 0x08
REG_UART_CTRL   = 0x0C
REG_UART_BAUD   = 0x10

# UART_STATUS bit positions
STATUS_TX_BUSY  = (1 << 0)
STATUS_TX_FULL  = (1 << 1)
STATUS_TX_EMPTY = (1 << 2)
STATUS_RX_EMPTY = (1 << 3)
STATUS_RX_FULL  = (1 << 4)
STATUS_RX_VALID = (1 << 5)

# UART_CTRL bit positions
CTRL_TX_EN         = (1 << 0)
CTRL_RX_EN         = (1 << 1)
CTRL_IRQ_TX_EMPTY  = (1 << 2)
CTRL_IRQ_RX_VALID  = (1 << 3)
CTRL_LOOPBACK      = (1 << 4)

# AXI response codes
RESP_OKAY = 0b00


# ── Setup helper ──────────────────────────────────────────────────────────────

async def _setup(dut):
    """Start 2 ns clock, drive uart_rx_i=1 (idle), apply 5-cycle reset,
    wait 2 idle cycles. Returns an AXI4LiteMaster."""
    cocotb.start_soon(Clock(dut.clk, 2, units="ns").start())

    m = AXI4LiteMaster(dut, "s_axil_", dut.clk)

    # Drive side-input to idle HIGH (UART line idle = 1) before reset
    dut.uart_rx_i.value = 1

    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)

    return m


# ── Test 1: RW register round-trip + WMASK enforcement ───────────────────────

@cocotb.test()
async def test_reg_rw_wmask(dut):
    """Write CTRL and BAUD; read back; verify WMASK enforcement on high bits."""
    m = await _setup(dut)

    # CTRL: write all 5 writable bits
    resp = await m.write(REG_UART_CTRL, 0x1F)
    assert resp == RESP_OKAY, f"write CTRL RESP={resp}"

    data, resp = await m.read(REG_UART_CTRL)
    assert resp == RESP_OKAY
    assert (data & 0x1F) == 0x1F, f"CTRL readback: got {data:#010x}, expected [4:0]=0x1F"
    assert (data & ~0x1F) == 0, f"CTRL bits above [4:0] should be 0: {data:#010x}"

    # BAUD: write lower 16 bits
    resp = await m.write(REG_UART_BAUD, 0xABCD)
    assert resp == RESP_OKAY
    data, resp = await m.read(REG_UART_BAUD)
    assert resp == RESP_OKAY
    assert (data & 0xFFFF) == 0xABCD, f"BAUD readback: got {data:#010x}, expected 0xABCD"

    # BAUD: high bits must be masked out even when written.
    # Writing 0xFFFF_0000 with WMASK=0xFFFF → effective write = 0 into [15:0]
    # (mask clears low bits), high bits still zero.
    resp = await m.write(REG_UART_BAUD, 0xFFFF_0000)
    assert resp == RESP_OKAY
    data, resp = await m.read(REG_UART_BAUD)
    assert resp == RESP_OKAY
    assert (data & 0xFFFF_0000) == 0, (
        f"BAUD high bits should be 0 (WMASK=0xFFFF): got {data:#010x}"
    )

    # TX write: WMASK=0 so data not stored; AXI must still accept
    resp = await m.write(REG_UART_TX, 0x42)
    assert resp == RESP_OKAY, f"write TX RESP={resp}"

    dut._log.info("test_reg_rw_wmask PASS")


# ── Test 2: STATUS reset values ───────────────────────────────────────────────

@cocotb.test()
async def test_status_reset(dut):
    """After reset: tx_empty=1, rx_empty=1, tx_busy=0, rx_valid=0."""
    m = await _setup(dut)

    # Wait an extra cycle for HW-driven STATUS to stabilise
    await RisingEdge(dut.clk)

    data, resp = await m.read(REG_UART_STATUS)
    assert resp == RESP_OKAY

    assert (data & STATUS_TX_EMPTY) != 0, (
        f"STATUS tx_empty should be 1 after reset: STATUS={data:#010x}"
    )
    assert (data & STATUS_RX_EMPTY) != 0, (
        f"STATUS rx_empty should be 1 after reset: STATUS={data:#010x}"
    )
    assert (data & STATUS_TX_BUSY) == 0, (
        f"STATUS tx_busy should be 0 after reset: STATUS={data:#010x}"
    )
    assert (data & STATUS_TX_FULL) == 0, (
        f"STATUS tx_full should be 0 after reset: STATUS={data:#010x}"
    )
    assert (data & STATUS_RX_VALID) == 0, (
        f"STATUS rx_valid should be 0 after reset: STATUS={data:#010x}"
    )
    dut._log.info(f"test_status_reset PASS  STATUS={data:#010x}")


# ── Test 3: TX transfer completes ────────────────────────────────────────────

@cocotb.test()
async def test_tx_transfer(dut):
    """Set BAUD=1 (2 clk/bit), tx_en=1, write TX; observe tx_empty after frame."""
    m = await _setup(dut)

    BAUD = 1   # 2 clocks/bit; frame = 10 bits × 2 = 20 clocks
    WAIT = 100  # generous margin

    await m.write(REG_UART_BAUD, BAUD)
    await m.write(REG_UART_CTRL, CTRL_TX_EN)

    resp = await m.write(REG_UART_TX, 0x55)
    assert resp == RESP_OKAY

    # Wait for frame to complete
    await ClockCycles(dut.clk, WAIT)

    # tx_busy must be 0 and tx_empty must be 1
    data, _ = await m.read(REG_UART_STATUS)
    assert (data & STATUS_TX_BUSY) == 0, (
        f"tx_busy should be 0 after frame: STATUS={data:#010x}"
    )
    assert (data & STATUS_TX_EMPTY) != 0, (
        f"tx_empty should be 1 after frame: STATUS={data:#010x}"
    )

    # uart_tx_o should return to idle (1) after STOP bit
    assert dut.uart_tx_o.value == 1, (
        f"uart_tx_o should be 1 (idle) after frame, got {dut.uart_tx_o.value}"
    )
    dut._log.info("test_tx_transfer PASS")


# ── Test 4: Loopback RX receives TX byte ─────────────────────────────────────

@cocotb.test()
async def test_loopback_rx(dut):
    """BAUD=1, loopback+tx_en+rx_en; write 0xA5; read back from UART_RX."""
    m = await _setup(dut)

    BAUD = 1
    WAIT = 120  # enough for 10-bit frame at 2 clk/bit + margin

    await m.write(REG_UART_BAUD, BAUD)
    # Enable TX, RX, and loopback
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_LOOPBACK)

    resp = await m.write(REG_UART_TX, 0xA5)
    assert resp == RESP_OKAY

    # Wait for TX frame to complete and RX to capture byte
    await ClockCycles(dut.clk, WAIT)

    # Check rx_valid (rx_empty must be 0)
    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"rx_valid should be 1 after loopback: STATUS={status:#010x}"
    )

    # Read UART_RX — this pops the FIFO
    data, resp = await m.read(REG_UART_RX)
    assert resp == RESP_OKAY
    assert (data & 0xFF) == 0xA5, (
        f"UART_RX: expected 0xA5, got {data:#010x}"
    )

    # After pop, rx_empty should be 1
    await RisingEdge(dut.clk)
    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_EMPTY) != 0, (
        f"rx_empty should be 1 after FIFO pop: STATUS={status:#010x}"
    )
    dut._log.info(f"test_loopback_rx PASS  received=0x{data & 0xFF:02X}")


# ── Test 5: IRQ rx_valid asserts and clears ───────────────────────────────────

@cocotb.test()
async def test_irq_rx_valid(dut):
    """IRQ_RX_VALID_EN set; after loopback receive irq_o=1; read RX → irq_o=0."""
    m = await _setup(dut)

    BAUD = 1
    WAIT = 120

    await m.write(REG_UART_BAUD, BAUD)
    # tx_en | rx_en | irq_rx_valid_en | loopback
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_IRQ_RX_VALID | CTRL_LOOPBACK)

    await m.write(REG_UART_TX, 0x7E)

    await ClockCycles(dut.clk, WAIT)

    # IRQ should be asserted
    assert dut.irq_o.value == 1, (
        f"irq_o expected 1 after rx_valid, got {dut.irq_o.value}"
    )

    # Read UART_RX pops the byte → rx_valid drops → irq clears
    data, _ = await m.read(REG_UART_RX)
    assert (data & 0xFF) == 0x7E, f"UART_RX expected 0x7E, got {data:#010x}"

    # Allow 1 extra cycle for combinational IRQ to update
    await RisingEdge(dut.clk)

    assert dut.irq_o.value == 0, (
        f"irq_o expected 0 after RX pop, got {dut.irq_o.value}"
    )
    dut._log.info("test_irq_rx_valid PASS")


# ── Test 6: TX FIFO fills to depth 4 and tx_full asserts ─────────────────────

@cocotb.test()
async def test_fifo_full(dut):
    """BAUD=0xFFFF (very slow TX); push 4 bytes → tx_full=1; 5th push ignored."""
    m = await _setup(dut)

    # Very long bit period so TX engine can't drain the FIFO during the pushes
    await m.write(REG_UART_BAUD, 0xFFFF)
    await m.write(REG_UART_CTRL, CTRL_TX_EN)

    # Push 4 bytes (FIFO depth = 4)
    for byte_val in [0x11, 0x22, 0x33, 0x44]:
        resp = await m.write(REG_UART_TX, byte_val)
        assert resp == RESP_OKAY
        await RisingEdge(dut.clk)

    # Allow STATUS to update (HW-driven combinational)
    await RisingEdge(dut.clk)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_TX_FULL) != 0, (
        f"tx_full should be 1 after 4 pushes: STATUS={status:#010x}"
    )

    # 5th push: AXI completes OKAY but FIFO does not grow (guarded by !tx_full)
    resp = await m.write(REG_UART_TX, 0x55)
    assert resp == RESP_OKAY

    await RisingEdge(dut.clk)
    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_TX_FULL) != 0, (
        f"tx_full should still be 1 after overflow push: STATUS={status:#010x}"
    )
    dut._log.info(f"test_fifo_full PASS  STATUS={status:#010x}")
