# test_spi.py
# Phase 5 (M4) — cocotb directed-test suite for spi_controller.sv
#
# DUT:  spi_controller  (TOPLEVEL=spi_controller)
# BFM:  APB4Master (bfm/apb4_master.py) drives APB4 slave ports.
#        APB migration PR-3: converted from AXI4LiteMaster (s_axil_* prefix)
#        to APB4Master (bare psel/penable/pwrite/paddr/pwdata/pstrb/prdata/
#        pready/pslverr).  No test logic or assertions changed.
# Side-inputs: spi_miso_i driven to 0 before reset (loopback tests use loopback)
#
# Register byte addresses
#   0x00  SPI_TX      WO [7:0]  write pushes byte to TX FIFO via snoop
#   0x04  SPI_RX      RO [7:0]  RX FIFO head; read pops
#   0x08  SPI_STATUS  RO        [0]=busy [1]=tx_full [2]=tx_empty
#                               [3]=rx_empty [4]=rx_valid [5]=rx_full
#   0x0C  SPI_CTRL    RW [4:0]  [0]=enable [1]=CPOL [2]=CPHA
#                               [3]=irq_done_en [4]=loopback
#   0x10  SPI_CLK_DIV RW [15:0] half-period = (DIV+1) clocks
#   0x14  SPI_CS_CTRL RW [0]    cs_n level (0=assert, 1=deassert)

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from bfm.apb4_master import APB4Master

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
STATUS_RX_FULL  = (1 << 5)   # SPI_STATUS[5]=rx_full (RTL bit 5)

# SPI_CTRL bit positions
CTRL_ENABLE     = (1 << 0)
CTRL_CPOL       = (1 << 1)
CTRL_CPHA       = (1 << 2)
CTRL_IRQ_DONE   = (1 << 3)
CTRL_LOOPBACK   = (1 << 4)

# APB4 response: APB4Master.write/read return True=OKAY, False=SLVERR.
RESP_OKAY = True

# Cycles to wait for an 8-bit SPI transfer with CLK_DIV=0 (half-period=1 clk):
# 16 SCLK edges × 1 clk each = 16 clocks + margin.
TRANSFER_WAIT_DIV0 = 60

# CLK_DIV >= 7 recommended for real external-slave CPHA=0 sampling (per RTL comment).
# We use CLK_DIV=7 for the external MISO tests to honour this guidance.
CLK_DIV_EXT = 7                         # half-period = 8 clocks
TRANSFER_WAIT_EXT = 16 * 2 * (CLK_DIV_EXT + 1) + 40  # 16 edges × 16 clks + margin


# ── Setup helper ──────────────────────────────────────────────────────────────

async def _setup(dut):
    """Start 2 ns clock, drive spi_miso_i=0, apply 5-cycle reset,
    wait 2 idle cycles. Returns an APB4Master.

    APB migration PR-3: BFM changed from AXI4LiteMaster (s_axil_* prefix)
    to APB4Master (bare APB4 ports: psel/penable/pwrite/paddr/pwdata/pstrb/
    prdata/pready/pslverr).  Clock and reset wiring are unchanged.
    """
    cocotb.start_soon(Clock(dut.clk, 2, units="ns").start())

    # APB4Master with empty prefix drives bare psel/penable/... DUT ports.
    m = APB4Master(dut, "", dut.clk)

    # Drive side-input to known state before reset
    dut.spi_miso_i.value = 0

    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)

    return m


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


# ── Test 11 (new): Real spi_miso_i pin, loopback=0, Mode 0 ──────────────────

@cocotb.test()
async def test_real_miso_mode0(dut):
    """Drive spi_miso_i externally (loopback=0) in Mode 0 (CPOL=0, CPHA=0).
    CPHA=0: DUT samples MISO on the LEADING (rising) edge of SCLK.
    Uses CLK_DIV=7 (half-period=8 clocks) as recommended for external slaves.

    Implementation note: Verilator updates spi_sclk_o synchronously on posedge
    clk, so observing spi_sclk_o after RisingEdge(clk) reads the value
    registered at that edge (i.e. the NEW value after the FF update).  Detecting
    edge transitions therefore requires comparing current vs previous sample.

    MISO driving strategy (CPHA=0, CPOL=0):
      - Sample on RISING SCLK edges (sclk_q: 0→1 transitions)
      - Shift on FALLING SCLK edges (sclk_q: 1→0 transitions)
      - MSB (bit 7) must be valid before the first rising edge
      - Bits 6..0 must be updated after each falling edge (and before the
        next rising edge, i.e. within the same HALF=8 clock window)

    We poll spi_sclk_o each system clock and track transitions, updating
    MISO immediately after each FALLING transition is detected.  With HALF=8
    there are 7 system clocks between the falling edge detection and the next
    rising edge, which is ample setup margin.
    """
    m = await _setup(dut)

    TX_BYTE   = 0x00          # TX value irrelevant; we're checking RX
    MISO_BYTE = 0xC3          # byte to receive MSB-first: 1100_0011
    HALF      = CLK_DIV_EXT + 1   # 8 clocks per SCLK half-period

    # Configure Mode 0 (CPOL=0, CPHA=0), CLK_DIV=7, loopback=0
    await m.write(REG_SPI_CLK_DIV, CLK_DIV_EXT)
    await m.write(REG_SPI_CTRL, CTRL_ENABLE)

    # Pre-drive bit 7 (MSB) before the transfer starts
    dut.spi_miso_i.value = (MISO_BYTE >> 7) & 1

    # Trigger transfer via AXI write
    resp = await m.write(REG_SPI_TX, TX_BYTE)
    assert resp == RESP_OKAY

    # Poll sclk_o for transitions.
    # - On the first RISING edge (0→1): bit 7 is being sampled (already pre-driven).
    # - On each subsequent FALLING edge (1→0): update MISO to the next bit.
    # We need to process 7 falling edges (to drive bits 6..0).
    falling_count = 0
    target_falling = 7      # bits 6..0
    prev_sclk = 0           # SCLK idle = 0 for CPOL=0
    first_rising_seen = False

    # Generous timeout: 16 edges × 8 clocks each + AXI overhead
    timeout = HALF * 16 * 2 + 60
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        curr_sclk = int(dut.spi_sclk_o.value)

        if not first_rising_seen and prev_sclk == 0 and curr_sclk == 1:
            # First rising edge: bit 7 is being sampled now (MISO already set)
            first_rising_seen = True

        if first_rising_seen and prev_sclk == 1 and curr_sclk == 0:
            # Falling edge: DUT just shifted; update MISO to next bit
            bit_idx = 6 - falling_count   # bits 6, 5, 4, 3, 2, 1, 0
            dut.spi_miso_i.value = (MISO_BYTE >> bit_idx) & 1
            falling_count += 1
            if falling_count == target_falling:
                break

        prev_sclk = curr_sclk

    assert falling_count == target_falling, (
        f"[miso_mode0] only saw {falling_count} falling edges (need {target_falling})"
    )
    # Do NOT set MISO to idle yet — bit 0 was just driven and the final rising
    # edge (sampling of bit 0) has not happened yet.  Wait for the final rising
    # edge (8th rising edge overall) before driving idle, so bit 0 is stable.
    for _ in range(HALF + 4):
        await RisingEdge(dut.clk)
        curr_sclk = int(dut.spi_sclk_o.value)
        if prev_sclk == 0 and curr_sclk == 1:
            break  # 8th rising edge: bit 0 sampled
        prev_sclk = curr_sclk
    dut.spi_miso_i.value = 0  # safe to return to idle now

    # Wait for transfer to complete and rx_push to propagate
    await ClockCycles(dut.clk, HALF * 4)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[miso_mode0] rx_valid should be 1 after transfer: STATUS={status:#010x}"
    )

    data, resp = await m.read(REG_SPI_RX)
    assert resp == RESP_OKAY
    assert (data & 0xFF) == MISO_BYTE, (
        f"[miso_mode0] expected 0x{MISO_BYTE:02X}, got {data:#010x}"
    )
    dut._log.info(f"test_real_miso_mode0 PASS  rx=0x{data & 0xFF:02X}")


# ── Test 12 (new): RX FIFO overflow — 5 transfers, 4 valid, 5th dropped ──────

@cocotb.test()
async def test_rx_fifo_overflow(dut):
    """Perform 5 SPI loopback transfers WITHOUT draining SPI_RX between them.
    After all 5 transfers:
      - SPI_STATUS[4]=rx_valid should be 1
      - SPI_STATUS[5]=rx_full  should be 1 (FIFO depth=4 is full after 4 entries)
      - Reading 4 bytes from SPI_RX recovers all 4 valid bytes correctly.
      - 5th byte is dropped (FIFO was full at push time).
    Uses CLK_DIV=0 (fastest) and loopback to maximise throughput."""
    m = await _setup(dut)

    TX_BYTES = [0x11, 0x22, 0x33, 0x44, 0x55]  # 5 bytes; 5th must be dropped

    await m.write(REG_SPI_CLK_DIV, 0)
    await m.write(REG_SPI_CTRL, CTRL_ENABLE | CTRL_LOOPBACK)

    # Issue all 5 transfers sequentially; each waits for the previous to complete
    # before issuing the next so the SPI engine is free.
    for i, byte_val in enumerate(TX_BYTES):
        resp = await m.write(REG_SPI_TX, byte_val)
        assert resp == RESP_OKAY, f"TX write #{i} failed: resp={resp}"
        # Wait for this transfer to finish (engine returns to IDLE)
        await ClockCycles(dut.clk, TRANSFER_WAIT_DIV0)

    # After 5 transfers:
    # - First 4 should be in the RX FIFO (depth=4)
    # - 5th is dropped because rx_full was asserted at push time
    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"rx_valid should be 1 (4 bytes in FIFO): STATUS={status:#010x}"
    )
    assert (status & STATUS_RX_FULL) != 0, (
        f"rx_full should be 1 (FIFO full after 4 entries): STATUS={status:#010x}"
    )

    # Drain the 4 valid bytes and verify values
    for expected_byte in TX_BYTES[:4]:
        data, resp = await m.read(REG_SPI_RX)
        assert resp == RESP_OKAY
        assert (data & 0xFF) == expected_byte, (
            f"RX FIFO: expected 0x{expected_byte:02X}, got {data:#010x}"
        )
        await RisingEdge(dut.clk)  # Allow FIFO pointer to update

    # After draining 4 bytes, FIFO must be empty (5th byte was dropped)
    await RisingEdge(dut.clk)
    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_EMPTY) != 0, (
        f"rx_empty should be 1 after draining 4 bytes (5th was dropped): STATUS={status:#010x}"
    )
    assert (status & STATUS_RX_VALID) == 0, (
        f"rx_valid should be 0 after full drain: STATUS={status:#010x}"
    )

    dut._log.info("test_rx_fifo_overflow PASS  4 valid + 1 dropped confirmed")


# ── Test 13 (new): SPI byte-lane snoop — write on non-zero byte lane ─────────

@cocotb.test()
async def test_byte_lane_snoop(dut):
    """A1 verification: write SPI_TX with data byte on a non-zero AXI byte lane
    (wdata[15:8]=val, wstrb=0b0010) and verify val is received in loopback.
    Also verifies normal full-word write (wstrb=0b0001, lane 0) still works."""
    m = await _setup(dut)

    await m.write(REG_SPI_CLK_DIV, 0)
    await m.write(REG_SPI_CTRL, CTRL_ENABLE | CTRL_LOOPBACK)

    # ---- Lane 1 test: byte on wdata[15:8], wstrb=0b0010 ----
    LANE1_BYTE = 0xF0
    tx_word   = LANE1_BYTE << 8   # value in byte lane 1

    resp = await m.write(REG_SPI_TX, tx_word, strb=0b0010)
    assert resp == RESP_OKAY, f"lane-1 write RESP={resp}"

    await ClockCycles(dut.clk, TRANSFER_WAIT_DIV0)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[lane1] rx_valid should be 1: STATUS={status:#010x}"
    )
    data, _ = await m.read(REG_SPI_RX)
    assert (data & 0xFF) == LANE1_BYTE, (
        f"[lane1] expected 0x{LANE1_BYTE:02X}, got {data:#010x} "
        f"(A1 byte-lane snoop must select lane 1 when wstrb[1]=1)"
    )
    dut._log.info(f"[lane1] SPI byte-lane snoop PASS  rx=0x{data & 0xFF:02X}")

    await RisingEdge(dut.clk)

    # ---- Normal full-word write: lane 0 (wstrb=0b0001) ----
    LANE0_BYTE = 0x37
    await ClockCycles(dut.clk, 5)

    resp = await m.write(REG_SPI_TX, LANE0_BYTE, strb=0b0001)
    assert resp == RESP_OKAY, f"lane-0 write RESP={resp}"

    await ClockCycles(dut.clk, TRANSFER_WAIT_DIV0)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[lane0] rx_valid should be 1: STATUS={status:#010x}"
    )
    data, _ = await m.read(REG_SPI_RX)
    assert (data & 0xFF) == LANE0_BYTE, (
        f"[lane0] expected 0x{LANE0_BYTE:02X}, got {data:#010x}"
    )
    dut._log.info(f"test_byte_lane_snoop PASS  lane0=0x{LANE0_BYTE:02X} lane1=0x{LANE1_BYTE:02X}")

    # ---- wstrb==0 no-op check (A1/wstrb gate): a zero-strobe write to ----
    # SPI_TX must NOT push a byte to the TX FIFO.  After the write we wait
    # one full transfer window and confirm rx_valid is still 0.
    await ClockCycles(dut.clk, 5)

    # Drain any residual RX byte from the lane-0 subtest
    st, _ = await m.read(REG_SPI_STATUS)
    if st & STATUS_RX_VALID:
        await m.read(REG_SPI_RX)  # pop

    # Issue zero-strobe write — must be a no-op
    resp = await m.write(REG_SPI_TX, 0xDE, strb=0b0000)
    assert resp == RESP_OKAY, f"wstrb=0 write RESP={resp}"

    await ClockCycles(dut.clk, TRANSFER_WAIT_DIV0)

    status, _ = await m.read(REG_SPI_STATUS)
    assert (status & STATUS_RX_VALID) == 0, (
        f"[wstrb=0] rx_valid must be 0 after zero-strobe write: STATUS={status:#010x}"
    )
    dut._log.info("test_byte_lane_snoop wstrb=0 no-op PASS")
