# test_spi.py
# Phase 5 (M4) — cocotb directed-test suite for spi_controller.sv
#
# DUT:  spi_controller  (TOPLEVEL=spi_controller)
# BFM:  AXI4LiteMaster (bfm/axi4lite_master.py) drives s_axil_* registers
# Side-inputs: spi_miso_i driven to 0 before reset (loopback tests use loopback)
#
# Register byte addresses
#   0x00  SPI_TX      WO [7:0]  write pushes byte to TX FIFO via snoop
#   0x04  SPI_RX      RO [7:0]  RX FIFO head; read pops
#   0x08  SPI_STATUS  RO        [0]=busy [1]=tx_full [2]=tx_empty
#                               [3]=rx_empty [4]=rx_valid
#   0x0C  SPI_CTRL    RW [4:0]  [0]=enable [1]=CPOL [2]=CPHA
#                               [3]=irq_done_en [4]=loopback
#   0x10  SPI_CLK_DIV RW [15:0] half-period = (DIV+1) clocks
#   0x14  SPI_CS_CTRL RW [0]    cs_n level (0=assert, 1=deassert)

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from bfm.axi4lite_master import AXI4LiteMaster

# ── Register byte addresses ───────────────────────────────────────────────────
REG_SPI_TX      = 0x00
REG_SPI_RX      = 0x04
REG_SPI_STATUS  = 0x08
REG_SPI_CTRL    = 0x0C
REG_SPI_CLK_DIV = 0x10
REG_SPI_CS_CTRL = 0x14

# SPI_STATUS bit positions
STATUS_BUSY     = (1 << 0)
STATUS_TX_FULL  = (1 << 1)
STATUS_TX_EMPTY = (1 << 2)
STATUS_RX_EMPTY = (1 << 3)
STATUS_RX_VALID = (1 << 4)

# SPI_CTRL bit positions
CTRL_ENABLE     = (1 << 0)
CTRL_CPOL       = (1 << 1)
CTRL_CPHA       = (1 << 2)
CTRL_IRQ_DONE   = (1 << 3)
CTRL_LOOPBACK   = (1 << 4)

# AXI response codes
RESP_OKAY = 0b00

# Cycles to wait for an 8-bit SPI transfer with CLK_DIV=0 (half-period=1 clk):
# 16 SCLK edges × 1 clk each = 16 clocks + margin.
TRANSFER_WAIT_DIV0 = 60


# ── Setup helper ──────────────────────────────────────────────────────────────

async def _setup(dut):
    """Start 2 ns clock, drive spi_miso_i=0, apply 5-cycle reset,
    wait 2 idle cycles. Returns an AXI4LiteMaster."""
    cocotb.start_soon(Clock(dut.clk, 2, units="ns").start())

    m = AXI4LiteMaster(dut, "s_axil_", dut.clk)

    # Drive side-input to known state before reset
    dut.spi_miso_i.value = 0

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
    """Write CTRL, CLK_DIV, CS_CTRL; read back; verify WMASK on high bits."""
    m = await _setup(dut)

    # CTRL: all 5 bits writable
    resp = await m.write(REG_SPI_CTRL, 0x1F)
    assert resp == RESP_OKAY
    data, resp = await m.read(REG_SPI_CTRL)
    assert resp == RESP_OKAY
    assert (data & 0x1F) == 0x1F, f"CTRL readback: {data:#010x}"
    assert (data & ~0x1F) == 0,   f"CTRL high bits non-zero: {data:#010x}"

    # CLK_DIV: only [15:0] writable
    resp = await m.write(REG_SPI_CLK_DIV, 0x1234)
    assert resp == RESP_OKAY
    data, resp = await m.read(REG_SPI_CLK_DIV)
    assert resp == RESP_OKAY
    assert (data & 0xFFFF) == 0x1234, f"CLK_DIV readback: {data:#010x}"

    # CLK_DIV high bits must be masked
    resp = await m.write(REG_SPI_CLK_DIV, 0xFFFF_0000)
    assert resp == RESP_OKAY
    data, resp = await m.read(REG_SPI_CLK_DIV)
    assert resp == RESP_OKAY
    assert (data & 0xFFFF_0000) == 0, f"CLK_DIV high bits non-zero: {data:#010x}"

    # CS_CTRL: only bit[0] writable; reset value = 1
    data, resp = await m.read(REG_SPI_CS_CTRL)
    assert resp == RESP_OKAY
    assert (data & 0x1) == 1, f"CS_CTRL reset should be 1: {data:#010x}"

    resp = await m.write(REG_SPI_CS_CTRL, 0x0)
    assert resp == RESP_OKAY
    data, resp = await m.read(REG_SPI_CS_CTRL)
    assert resp == RESP_OKAY
    assert (data & 0x1) == 0, f"CS_CTRL should be 0: {data:#010x}"

    # TX write (WO, WMASK=0): must accept without error
    resp = await m.write(REG_SPI_TX, 0xBE)
    assert resp == RESP_OKAY

    dut._log.info("test_reg_rw_wmask PASS")


# ── Test 2: STATUS reset values ───────────────────────────────────────────────

@cocotb.test()
async def test_status_reset(dut):
    """After reset: tx_empty=1, rx_empty=1, busy=0, rx_valid=0."""
    m = await _setup(dut)

    await RisingEdge(dut.clk)

    data, resp = await m.read(REG_SPI_STATUS)
    assert resp == RESP_OKAY

    assert (data & STATUS_TX_EMPTY) != 0, f"tx_empty should be 1: {data:#010x}"
    assert (data & STATUS_RX_EMPTY) != 0, f"rx_empty should be 1: {data:#010x}"
    assert (data & STATUS_BUSY)     == 0, f"busy should be 0: {data:#010x}"
    assert (data & STATUS_TX_FULL)  == 0, f"tx_full should be 0: {data:#010x}"
    assert (data & STATUS_RX_VALID) == 0, f"rx_valid should be 0: {data:#010x}"
    dut._log.info(f"test_status_reset PASS  STATUS={data:#010x}")


# ── Helper: loopback transfer and verify ─────────────────────────────────────

async def _loopback_transfer(dut, m, ctrl_bits, tx_byte, wait=TRANSFER_WAIT_DIV0):
    """Write ctrl_bits, write tx_byte to SPI_TX, wait, return received byte."""
    await m.write(REG_SPI_CLK_DIV, 0)  # half-period = 1 clock (fastest)
    await m.write(REG_SPI_CTRL, ctrl_bits)

    resp = await m.write(REG_SPI_TX, tx_byte)
    assert resp == RESP_OKAY

    await ClockCycles(dut.clk, wait)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"rx_valid should be 1 after transfer (CTRL={ctrl_bits:#04x}): STATUS={status:#010x}"
    )

    data, resp = await m.read(REG_SPI_RX)
    assert resp == RESP_OKAY
    return data & 0xFF


# ── Test 3: Loopback CPOL=0 CPHA=0 (Mode 0) ──────────────────────────────────

@cocotb.test()
async def test_loopback_mode0(dut):
    """CPOL=0 CPHA=0 loopback: write 0xA5, expect 0xA5 from SPI_RX."""
    m = await _setup(dut)
    rx = await _loopback_transfer(dut, m, CTRL_ENABLE | CTRL_LOOPBACK, 0xA5)
    assert rx == 0xA5, f"Mode0: expected 0xA5, got {rx:#04x}"
    dut._log.info(f"test_loopback_mode0 PASS  rx=0x{rx:02X}")


# ── Test 4: Loopback CPOL=0 CPHA=1 (Mode 1) ──────────────────────────────────

@cocotb.test()
async def test_loopback_mode1(dut):
    """CPOL=0 CPHA=1 loopback: write 0xA5, expect 0xA5."""
    m = await _setup(dut)
    rx = await _loopback_transfer(dut, m, CTRL_ENABLE | CTRL_CPHA | CTRL_LOOPBACK, 0xA5)
    assert rx == 0xA5, f"Mode1: expected 0xA5, got {rx:#04x}"
    dut._log.info(f"test_loopback_mode1 PASS  rx=0x{rx:02X}")


# ── Test 5: Loopback CPOL=1 CPHA=0 (Mode 2) ──────────────────────────────────

@cocotb.test()
async def test_loopback_mode2(dut):
    """CPOL=1 CPHA=0 loopback: write 0xA5, expect 0xA5."""
    m = await _setup(dut)
    rx = await _loopback_transfer(dut, m, CTRL_ENABLE | CTRL_CPOL | CTRL_LOOPBACK, 0xA5)
    assert rx == 0xA5, f"Mode2: expected 0xA5, got {rx:#04x}"
    dut._log.info(f"test_loopback_mode2 PASS  rx=0x{rx:02X}")


# ── Test 6: Loopback CPOL=1 CPHA=1 (Mode 3) ──────────────────────────────────

@cocotb.test()
async def test_loopback_mode3(dut):
    """CPOL=1 CPHA=1 loopback: write 0xA5, expect 0xA5."""
    m = await _setup(dut)
    rx = await _loopback_transfer(dut, m, CTRL_ENABLE | CTRL_CPOL | CTRL_CPHA | CTRL_LOOPBACK, 0xA5)
    assert rx == 0xA5, f"Mode3: expected 0xA5, got {rx:#04x}"
    dut._log.info(f"test_loopback_mode3 PASS  rx=0x{rx:02X}")


# ── Test 7: busy asserts during transfer ──────────────────────────────────────

@cocotb.test()
async def test_busy_asserts(dut):
    """CLK_DIV=3 (half-period=4): busy=1 shortly after TX write; 0 when done."""
    m = await _setup(dut)

    DIV = 3  # half-period = 4 clocks; full transfer = 16 edges × 4 = 64 clocks
    WAIT_BUSY   = 4   # cycles after write before sampling busy
    WAIT_FINISH = 120  # cycles to let transfer complete

    await m.write(REG_SPI_CLK_DIV, DIV)
    await m.write(REG_SPI_CTRL, CTRL_ENABLE | CTRL_LOOPBACK)

    await m.write(REG_SPI_TX, 0x55)

    # Give a few cycles for the FSM to transition from IDLE to ACTIVE
    await ClockCycles(dut.clk, WAIT_BUSY)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_BUSY) != 0, (
        f"busy should be 1 during transfer: STATUS={status:#010x}"
    )

    # Wait for completion
    await ClockCycles(dut.clk, WAIT_FINISH)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_BUSY) == 0, (
        f"busy should be 0 after transfer: STATUS={status:#010x}"
    )
    dut._log.info("test_busy_asserts PASS")


# ── Test 8: IRQ done asserts and clears ───────────────────────────────────────

@cocotb.test()
async def test_irq_done(dut):
    """irq_done_en set; after loopback transfer irq_o=1; read SPI_RX → irq_o=0."""
    m = await _setup(dut)

    await m.write(REG_SPI_CLK_DIV, 0)
    # enable | irq_done_en | loopback
    await m.write(REG_SPI_CTRL, CTRL_ENABLE | CTRL_IRQ_DONE | CTRL_LOOPBACK)

    await m.write(REG_SPI_TX, 0xBE)

    await ClockCycles(dut.clk, TRANSFER_WAIT_DIV0)

    assert dut.irq_o.value == 1, (
        f"irq_o expected 1 after transfer, got {dut.irq_o.value}"
    )

    data, _ = await m.read(REG_SPI_RX)
    assert (data & 0xFF) == 0xBE, f"SPI_RX expected 0xBE, got {data:#010x}"

    await RisingEdge(dut.clk)
    assert dut.irq_o.value == 0, (
        f"irq_o expected 0 after RX pop, got {dut.irq_o.value}"
    )
    dut._log.info("test_irq_done PASS")


# ── Test 9: spi_cs_n_o follows SPI_CS_CTRL ───────────────────────────────────

@cocotb.test()
async def test_cs_n_follows_ctrl(dut):
    """CS_CTRL[0] directly controls spi_cs_n_o (combinational)."""
    m = await _setup(dut)

    # Reset value = 1 (deasserted)
    await RisingEdge(dut.clk)
    assert dut.spi_cs_n_o.value == 1, (
        f"spi_cs_n_o expected 1 at reset, got {dut.spi_cs_n_o.value}"
    )

    # Assert CS (write 0)
    await m.write(REG_SPI_CS_CTRL, 0)
    await RisingEdge(dut.clk)
    assert dut.spi_cs_n_o.value == 0, (
        f"spi_cs_n_o expected 0 after CS_CTRL=0, got {dut.spi_cs_n_o.value}"
    )

    # Deassert CS (write 1)
    await m.write(REG_SPI_CS_CTRL, 1)
    await RisingEdge(dut.clk)
    assert dut.spi_cs_n_o.value == 1, (
        f"spi_cs_n_o expected 1 after CS_CTRL=1, got {dut.spi_cs_n_o.value}"
    )
    dut._log.info("test_cs_n_follows_ctrl PASS")


# ── Test 10: SCLK toggles at expected rate ───────────────────────────────────

@cocotb.test()
async def test_clk_div_rate(dut):
    """CLK_DIV=4 → half-period=5 clks → full SCLK period=10 clks.
    Measure rising-edge spacing on spi_sclk_o during transfer."""
    m = await _setup(dut)

    DIV = 4  # half-period = 5 clocks; full SCLK period = 10 clocks

    await m.write(REG_SPI_CLK_DIV, DIV)
    await m.write(REG_SPI_CTRL, CTRL_ENABLE | CTRL_LOOPBACK)  # CPOL=0

    await m.write(REG_SPI_TX, 0xA5)

    # Wait for transfer to start
    await ClockCycles(dut.clk, 3)

    # Find first rising edge of spi_sclk_o
    TIMEOUT = 200
    found = False
    for _ in range(TIMEOUT):
        await RisingEdge(dut.clk)
        if dut.spi_sclk_o.value == 1:
            found = True
            break
    assert found, "spi_sclk_o never went high during transfer"

    # Count clocks until next rising edge
    prev_val = 1
    count = 0
    for _ in range(TIMEOUT):
        await RisingEdge(dut.clk)
        curr_val = dut.spi_sclk_o.value.integer
        if prev_val == 0 and curr_val == 1:
            break
        prev_val = curr_val
        count += 1

    # Full period = 2 × half-period = 2 × (DIV+1) = 10 clocks
    expected_period = 2 * (DIV + 1)
    assert abs(count - expected_period) <= 2, (
        f"SCLK period: measured {count} clks, expected {expected_period} (DIV={DIV})"
    )
    dut._log.info(f"test_clk_div_rate PASS  period≈{count} clks (expected {expected_period})")
