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
#                               [6]=framing_error (sticky; cleared on UART_RX read)
#   0x0C  UART_CTRL   RW [4:0]  [0]=tx_en [1]=rx_en [2]=irq_tx_empty_en
#                               [3]=irq_rx_valid_en [4]=loopback
#   0x10  UART_BAUD   RW [15:0] D: 1 oversample tick = (D+1) clocks
#                               1 bit = 16 os_ticks = 16*(D+1) clocks
#
# A4 TIMING (BREAKING CHANGE):
#   BAUD register now sets the OVERSAMPLE period, not the bit period.
#   With D=0: os_tick every 1 clock; 1 bit = 16 clocks.
#   1 frame = 10 bits × 16 = 160 clocks (D=0).
#   All tests in this file use D=0 (BAUD=0) unless otherwise noted.
#   WAIT_FRAME_D0 = 200 (generous margin over 160 clocks at D=0).

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge

from bfm.axi4lite_master import AXI4LiteMaster

# ── Register byte addresses ───────────────────────────────────────────────────
REG_UART_TX     = 0x00
REG_UART_RX     = 0x04
REG_UART_STATUS = 0x08
REG_UART_CTRL   = 0x0C
REG_UART_BAUD   = 0x10

# UART_STATUS bit positions (matching RTL bit assignments)
STATUS_TX_BUSY       = (1 << 0)
STATUS_TX_FULL       = (1 << 1)
STATUS_TX_EMPTY      = (1 << 2)
STATUS_RX_EMPTY      = (1 << 3)
STATUS_RX_FULL       = (1 << 4)
STATUS_RX_VALID      = (1 << 5)
STATUS_FRAMING_ERROR = (1 << 6)   # A3 — new sticky framing-error bit

# UART_CTRL bit positions
CTRL_TX_EN         = (1 << 0)
CTRL_RX_EN         = (1 << 1)
CTRL_IRQ_TX_EMPTY  = (1 << 2)
CTRL_IRQ_RX_VALID  = (1 << 3)
CTRL_LOOPBACK      = (1 << 4)

# AXI response codes
RESP_OKAY = 0b00

# A4: With BAUD=0, 1 bit = 16 clocks, 1 frame (8N1, 10 bits) = 160 clocks.
# WAIT_FRAME_D0: generous margin (200 clocks) for a single frame at D=0.
BAUD_D0        = 0     # D=0: os_tick every clock; 16 clocks/bit
WAIT_FRAME_D0  = 200   # > 160 clocks (10 bits × 16 clocks)
# For loopback tests: TX starts after first bit_tick from idle (≤16 clocks
# from CTRL write), then 10 bits × 16 clocks, + RX_DONE push. 250 is safe.
WAIT_LOOPBACK_D0 = 300


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


# ── Helper: drive a raw 8N1 frame directly on uart_rx_i ──────────────────────

async def _drive_rx_frame(dut, byte_val, bit_clocks=16, stop_bit=1,
                          glitch_bit=None, glitch_phase=None):
    """Drive a raw 8N1 UART frame on uart_rx_i at `bit_clocks` clocks per bit.

    byte_val   : 8-bit data byte to transmit (LSB first)
    bit_clocks : clocks per bit (= 16*(D+1) for baud register value D)
    stop_bit   : 0 to inject a framing error (STOP=0 instead of 1)
    glitch_bit : data bit index (0-7) on which to inject a 1-clock glitch
    glitch_phase: clock offset within the bit period at which to inject glitch
                  (only used when glitch_bit is not None)
    """
    # Bits: START(0), D0..D7 (LSB first), STOP(stop_bit)
    bits = [0]  # START bit
    for i in range(8):
        bits.append((byte_val >> i) & 1)
    bits.append(stop_bit)  # STOP bit

    for bit_idx, bit_val in enumerate(bits):
        # Drive bit for bit_clocks - 1 cycles, then one more
        for clk_phase in range(bit_clocks):
            val = bit_val
            # Inject glitch: flip for exactly 1 cycle at glitch_phase
            # Only on the selected data bit (glitch_bit 0..7 → bits index 1..8)
            if (glitch_bit is not None and
                    bit_idx == glitch_bit + 1 and
                    clk_phase == glitch_phase):
                val = 1 - bit_val
            dut.uart_rx_i.value = val
            await RisingEdge(dut.clk)


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
    """After reset: tx_empty=1, rx_empty=1, tx_busy=0, rx_valid=0, framing_error=0."""
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
    assert (data & STATUS_FRAMING_ERROR) == 0, (
        f"STATUS framing_error should be 0 after reset: STATUS={data:#010x}"
    )
    dut._log.info(f"test_status_reset PASS  STATUS={data:#010x}")


# ── Test 3: TX transfer completes (A4 updated) ────────────────────────────────

@cocotb.test()
async def test_tx_transfer(dut):
    """BAUD=0 (16 clk/bit); tx_en=1; write TX; observe tx_empty after frame.
    A4 update: frame = 10 bits × 16 clocks = 160 clocks. WAIT=200 clocks."""
    m = await _setup(dut)

    # A4: D=0 → 16 clocks/bit; frame = 10 bits × 16 = 160 clocks
    WAIT = WAIT_FRAME_D0  # 200 — generous margin

    await m.write(REG_UART_BAUD, BAUD_D0)
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


# ── Test 4: Loopback RX receives TX byte (A4 updated) ─────────────────────────

@cocotb.test()
async def test_loopback_rx(dut):
    """BAUD=0 (16 clk/bit), loopback+tx_en+rx_en; write 0xA5; read back.
    A4 update: total wait = WAIT_LOOPBACK_D0 = 300 clocks."""
    m = await _setup(dut)

    await m.write(REG_UART_BAUD, BAUD_D0)
    # Enable TX, RX, and loopback
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_LOOPBACK)

    resp = await m.write(REG_UART_TX, 0xA5)
    assert resp == RESP_OKAY

    # Wait for TX frame to complete and RX to capture byte
    # A4: frame = 160 clocks; TX may start up to 16 clocks after CTRL write;
    # RX_DONE takes 1 extra cycle to push. 300 clocks is sufficient.
    await ClockCycles(dut.clk, WAIT_LOOPBACK_D0)

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


# ── Test 5: IRQ rx_valid asserts and clears (A4 updated) ─────────────────────

@cocotb.test()
async def test_irq_rx_valid(dut):
    """IRQ_RX_VALID_EN set; after loopback receive irq_o=1; read RX → irq_o=0.
    A4 update: uses BAUD=0 and WAIT_LOOPBACK_D0."""
    m = await _setup(dut)

    await m.write(REG_UART_BAUD, BAUD_D0)
    # tx_en | rx_en | irq_rx_valid_en | loopback
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_IRQ_RX_VALID | CTRL_LOOPBACK)

    await m.write(REG_UART_TX, 0x7E)

    await ClockCycles(dut.clk, WAIT_LOOPBACK_D0)

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


# ── Test 6: TX FIFO fills to depth 4 and tx_full asserts (A4 updated) ─────────

@cocotb.test()
async def test_fifo_full(dut):
    """BAUD=0xFFFF (very slow TX); push 4 bytes → tx_full=1; 5th push ignored.
    BAUD=0xFFFF means os_tick every 65536 clocks — FIFO cannot drain during pushes."""
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


# ── Test 7 (new): Async RX — raw pin, loopback=0 ─────────────────────────────

@cocotb.test()
async def test_async_rx_raw_pin(dut):
    """Drive raw 8N1 UART frame directly on uart_rx_i (loopback off).
    Verify the assembled byte appears in RX FIFO and reads back correctly.
    Tests the 16x oversample RX engine (A4) end-to-end on the async path."""
    m = await _setup(dut)

    TEST_BYTE = 0xB7
    BIT_CLOCKS = 16  # D=0: 16 clocks per bit

    # Configure: rx_en only (no TX, no loopback)
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN)

    # uart_rx_i is already driven to 1 (idle) by _setup.
    # Wait one idle bit_tick boundary to ensure the RX FSM is fully in IDLE.
    await ClockCycles(dut.clk, 20)

    # Drive the 8N1 frame asynchronously: START + 8 data bits + STOP
    await _drive_rx_frame(dut, TEST_BYTE, bit_clocks=BIT_CLOCKS)

    # Return line to idle after frame
    dut.uart_rx_i.value = 1

    # Wait for RX to push the byte (RX_DONE→rx_push, then FIFO write)
    # Frame = 10 bits × 16 clks = 160 clks; we're already past that.
    # Give a few extra cycles for the FIFO write and AXI readback.
    await ClockCycles(dut.clk, 20)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"rx_valid should be 1 after async RX frame: STATUS={status:#010x}"
    )
    # No framing error expected (well-formed frame)
    assert (status & STATUS_FRAMING_ERROR) == 0, (
        f"framing_error should be 0 for valid frame: STATUS={status:#010x}"
    )

    data, resp = await m.read(REG_UART_RX)
    assert resp == RESP_OKAY
    assert (data & 0xFF) == TEST_BYTE, (
        f"UART_RX: expected 0x{TEST_BYTE:02X}, got {data:#010x}"
    )
    dut._log.info(f"test_async_rx_raw_pin PASS  received=0x{data & 0xFF:02X}")


# ── Test 8 (new): Oversample noise immunity — glitch and edge skew ────────────

@cocotb.test()
async def test_oversample_noise_immunity(dut):
    """Drive 8N1 frame with a 1-cycle glitch mid-bit (os_phase 4) on bit 0.
    The 2-of-3 majority vote at phases 7/8/9 must still recover the correct byte.
    Also tests a ±1 os_tick edge skew by delivering START one phase late
    (uart_rx_i stays high 1 extra clock before START); verify same result."""
    m = await _setup(dut)

    BIT_CLOCKS = 16

    # ---- Glitch test ----
    GLITCH_BYTE = 0xA5
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN)
    await ClockCycles(dut.clk, 20)

    # Inject glitch at phase 4 of bit 0 (well outside the majority-vote window
    # at phases 7/8/9 — should be ignored by the RX engine).
    await _drive_rx_frame(dut, GLITCH_BYTE, bit_clocks=BIT_CLOCKS,
                          glitch_bit=0, glitch_phase=4)
    dut.uart_rx_i.value = 1
    await ClockCycles(dut.clk, 20)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[glitch] rx_valid should be 1: STATUS={status:#010x}"
    )
    data, _ = await m.read(REG_UART_RX)
    assert (data & 0xFF) == GLITCH_BYTE, (
        f"[glitch] UART_RX expected 0x{GLITCH_BYTE:02X}, got {data:#010x}"
    )
    dut._log.info(f"[glitch] byte recovered correctly: 0x{data & 0xFF:02X}")

    # Allow FIFO to empty before next subtest
    await RisingEdge(dut.clk)

    # ---- Edge-skew test: START 1 clock late (uart_rx_i stays high 1 extra clock) ----
    # This means the RX FSM detects START one os_tick later than ideal.
    # With 16-phase majority vote, a 1-tick alignment error is negligible.
    SKEW_BYTE = 0x3C
    await ClockCycles(dut.clk, 20)

    # Hold idle for 1 extra clock to skew the START detection by 1 phase
    dut.uart_rx_i.value = 1
    await RisingEdge(dut.clk)  # 1 extra idle clock = 1-phase skew

    await _drive_rx_frame(dut, SKEW_BYTE, bit_clocks=BIT_CLOCKS)
    dut.uart_rx_i.value = 1
    await ClockCycles(dut.clk, 20)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[skew] rx_valid should be 1: STATUS={status:#010x}"
    )
    data, _ = await m.read(REG_UART_RX)
    assert (data & 0xFF) == SKEW_BYTE, (
        f"[skew] UART_RX expected 0x{SKEW_BYTE:02X}, got {data:#010x}"
    )
    dut._log.info(f"test_oversample_noise_immunity PASS  glitch=0x{GLITCH_BYTE:02X} skew=0x{SKEW_BYTE:02X}")


# ── Test 9 (new): Framing error — STOP=0 sets STATUS[6], clears on RX read ───

@cocotb.test()
async def test_framing_error(dut):
    """Drive a frame with STOP bit = 0 (bad stop).
    Verify STATUS[6] (framing_error) sets.
    Verify byte is still pushed to FIFO (byte-push-on-error behaviour).
    Verify read of UART_RX clears framing_error (read-to-clear).
    Then send a well-formed frame; verify framing_error stays 0."""
    m = await _setup(dut)

    BAD_BYTE   = 0x5A  # data value (arbitrary; stop bit will be forced to 0)
    BIT_CLOCKS = 16

    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN)
    await ClockCycles(dut.clk, 20)

    # Drive frame with STOP=0 (framing error)
    await _drive_rx_frame(dut, BAD_BYTE, bit_clocks=BIT_CLOCKS, stop_bit=0)

    # Return to idle (the stop-bit low may have caused the RX to see it
    # as a new START; hold idle high long enough to settle)
    dut.uart_rx_i.value = 1
    await ClockCycles(dut.clk, 40)

    # STATUS[6] must be set
    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_FRAMING_ERROR) != 0, (
        f"framing_error should be 1 after bad stop: STATUS={status:#010x}"
    )
    # Byte must still be in FIFO (rx_valid=1)
    assert (status & STATUS_RX_VALID) != 0, (
        f"rx_valid should be 1 even with framing error: STATUS={status:#010x}"
    )

    # Read UART_RX — this pops the FIFO and clears framing_error
    data, resp = await m.read(REG_UART_RX)
    assert resp == RESP_OKAY
    assert (data & 0xFF) == BAD_BYTE, (
        f"UART_RX expected 0x{BAD_BYTE:02X} even with framing error, got {data:#010x}"
    )

    # After rx_pop, framing_error must be cleared (read-to-clear)
    await RisingEdge(dut.clk)
    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_FRAMING_ERROR) == 0, (
        f"framing_error should be 0 after UART_RX read: STATUS={status:#010x}"
    )

    # ---- Well-formed frame: framing_error must stay 0 ----
    await ClockCycles(dut.clk, 20)
    GOOD_BYTE = 0x3C
    await _drive_rx_frame(dut, GOOD_BYTE, bit_clocks=BIT_CLOCKS, stop_bit=1)
    dut.uart_rx_i.value = 1
    await ClockCycles(dut.clk, 20)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_FRAMING_ERROR) == 0, (
        f"framing_error should remain 0 for good frame: STATUS={status:#010x}"
    )
    assert (status & STATUS_RX_VALID) != 0, (
        f"rx_valid should be 1 after good frame: STATUS={status:#010x}"
    )

    # Pop good byte to leave FIFO clean
    gdata, _ = await m.read(REG_UART_RX)
    assert (gdata & 0xFF) == GOOD_BYTE, (
        f"good frame: UART_RX expected 0x{GOOD_BYTE:02X}, got {gdata:#010x}"
    )

    dut._log.info("test_framing_error PASS")


# ── Test 10 (new): Reset IRQ — tx_empty_en before any push must not fire ──────

@cocotb.test()
async def test_reset_irq_tx_empty(dut):
    """A2 verification: enabling irq_tx_empty_en at reset (no TX push yet)
    must NOT assert irq_o (tx_was_nonempty_q prevents false fire).
    Then push one byte, let TX drain to empty → irq_o must assert."""
    m = await _setup(dut)

    await m.write(REG_UART_BAUD, BAUD_D0)

    # Enable tx_en + irq_tx_empty_en WITHOUT pushing any byte
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_IRQ_TX_EMPTY)

    # Wait well past one full frame period — irq_o must stay 0
    await ClockCycles(dut.clk, WAIT_FRAME_D0)

    assert dut.irq_o.value == 0, (
        f"irq_o expected 0 before any TX push (A2), got {dut.irq_o.value}"
    )

    # Now push a byte
    resp = await m.write(REG_UART_TX, 0xCC)
    assert resp == RESP_OKAY

    # Wait for TX to drain (FIFO empty, engine returns to IDLE)
    # tx_was_nonempty_q is now set; when TX becomes empty irq should fire.
    await ClockCycles(dut.clk, WAIT_FRAME_D0)

    # tx_empty should be 1 now
    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_TX_EMPTY) != 0, (
        f"tx_empty should be 1 after TX drain: STATUS={status:#010x}"
    )
    assert (status & STATUS_TX_BUSY) == 0, (
        f"tx_busy should be 0 after TX drain: STATUS={status:#010x}"
    )

    # irq_o must be asserted (tx_was_nonempty_q is now set and tx_empty=1)
    assert dut.irq_o.value == 1, (
        f"irq_o expected 1 after TX drains to empty (A2), got {dut.irq_o.value}"
    )

    dut._log.info("test_reset_irq_tx_empty PASS")


# ── Test 11 (new): Byte-lane snoop — write on non-zero AXI byte lane ─────────

@cocotb.test()
async def test_byte_lane_snoop(dut):
    """A1 verification: write UART_TX with data byte on a non-zero byte lane
    (wdata[15:8]=val, wstrb=0b0010) and verify that val is received in loopback.
    Also verify normal full-word write (wstrb=0b0001, data on lane 0) still works."""
    m = await _setup(dut)

    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_LOOPBACK)

    # ---- Lane 1 test: byte on wdata[15:8], wstrb=0b0010 ----
    LANE1_BYTE = 0xD5
    tx_word   = LANE1_BYTE << 8   # value in byte lane 1

    # Use the BFM's write with explicit strobe on byte lane 1 (strb=0b0010)
    resp = await m.write(REG_UART_TX, tx_word, strb=0b0010)
    assert resp == RESP_OKAY, f"lane-1 write RESP={resp}"

    await ClockCycles(dut.clk, WAIT_LOOPBACK_D0)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[lane1] rx_valid should be 1: STATUS={status:#010x}"
    )
    data, _ = await m.read(REG_UART_RX)
    assert (data & 0xFF) == LANE1_BYTE, (
        f"[lane1] expected 0x{LANE1_BYTE:02X}, got {data:#010x} "
        f"(A1 byte-lane snoop must select lane 1 when wstrb[1]=1)"
    )
    dut._log.info(f"[lane1] byte-lane snoop PASS  rx=0x{data & 0xFF:02X}")

    # Allow FIFO to empty
    await RisingEdge(dut.clk)

    # ---- Normal full-word write: lane 0 (wstrb=0b0001) ----
    LANE0_BYTE = 0x91
    await ClockCycles(dut.clk, 10)

    resp = await m.write(REG_UART_TX, LANE0_BYTE, strb=0b0001)
    assert resp == RESP_OKAY, f"lane-0 write RESP={resp}"

    await ClockCycles(dut.clk, WAIT_LOOPBACK_D0)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) != 0, (
        f"[lane0] rx_valid should be 1: STATUS={status:#010x}"
    )
    data, _ = await m.read(REG_UART_RX)
    assert (data & 0xFF) == LANE0_BYTE, (
        f"[lane0] expected 0x{LANE0_BYTE:02X}, got {data:#010x}"
    )
    dut._log.info(f"test_byte_lane_snoop PASS  lane0=0x{LANE0_BYTE:02X} lane1=0x{LANE1_BYTE:02X}")
