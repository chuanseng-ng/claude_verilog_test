# test_uart.py
# Phase 5 (M4) — cocotb directed-test suite for uart_controller.sv
#
# DUT:  uart_controller  (TOPLEVEL=uart_controller)
# BFM:  APB4Master (bfm/apb4_master.py) drives APB4 slave ports
#        APB migration PR-2: converted from AXI4LiteMaster (s_axil_*) to
#        APB4Master (bare psel/penable/pwrite/paddr/pwdata/pstrb/prdata/pready/pslverr).
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

from bfm.apb4_master import APB4Master

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

# APB4 response: APB4Master.write/read return True=OKAY, False=SLVERR.
RESP_OKAY = True

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
    wait 2 idle cycles. Returns an APB4Master.

    APB migration PR-2: BFM changed from AXI4LiteMaster (s_axil_* prefix)
    to APB4Master (bare APB4 ports: psel/penable/pwrite/paddr/pwdata/pstrb/
    prdata/pready/pslverr).  Clock and reset wiring are unchanged.
    """
    cocotb.start_soon(Clock(dut.clk, 2, units="ns").start())

    # APB4Master with empty prefix drives bare psel/penable/... DUT ports.
    m = APB4Master(dut, "", dut.clk)

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

    # ---- wstrb==0 no-op check (A1/wstrb gate): a zero-strobe write to ----
    # UART_TX must NOT push a byte to the TX FIFO.  After the write we wait
    # one full loopback frame and confirm rx_valid is still 0.
    await ClockCycles(dut.clk, 10)

    # Drain any residual RX byte from the lane-0 subtest
    st, _ = await m.read(REG_UART_STATUS)
    if st & STATUS_RX_VALID:
        await m.read(REG_UART_RX)  # pop

    # Issue zero-strobe write — must be a no-op
    resp = await m.write(REG_UART_TX, 0xDE, strb=0b0000)
    assert resp == RESP_OKAY, f"wstrb=0 write RESP={resp}"

    await ClockCycles(dut.clk, WAIT_LOOPBACK_D0)

    status, _ = await m.read(REG_UART_STATUS)
    assert (status & STATUS_RX_VALID) == 0, (
        f"[wstrb=0] rx_valid must be 0 after zero-strobe write: STATUS={status:#010x}"
    )
    dut._log.info("test_byte_lane_snoop wstrb=0 no-op PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Bead 05wf — directed gap-closure tests (byte lanes 2/3, FIFO full, RX false
# start, slow-baud os_tick gaps).  Everything below checks documented behaviour
# (UART_STATUS flags, frame timing, FIFO order / drop-newest semantics), not just
# that a line was reached.
# ═════════════════════════════════════════════════════════════════════════════

def _frame_levels(byte_val, bit_clocks, stop_bit=1, invert=()):
    """Per-clock line levels of one 8N1 frame (START, D0..D7 LSB-first, STOP).

    `invert` is a set of absolute clock indices (0 = first START clock) whose
    level is flipped, used to inject 1-clock glitches at an exact position.
    """
    bits = [0] + [(byte_val >> i) & 1 for i in range(8)] + [stop_bit]
    levels = []
    for b in bits:
        levels.extend([b] * bit_clocks)
    return [(1 - v) if i in invert else v for i, v in enumerate(levels)]


async def _drive_levels(dut, levels):
    """Drive `levels` on uart_rx_i, one entry per clock."""
    for v in levels:
        dut.uart_rx_i.value = v
        await RisingEdge(dut.clk)
    dut.uart_rx_i.value = 1


async def _capture_tx_frame(dut, bit_clocks, timeout):
    """Wait for the START falling edge on uart_tx_o, then return the per-clock
    line levels covering exactly one 10-bit frame (index 0 = first low clock)."""
    prev = int(dut.uart_tx_o.value)
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        cur = int(dut.uart_tx_o.value)
        if prev == 1 and cur == 0:
            break
        prev = cur
    else:
        raise AssertionError(f"uart_tx_o never fell within {timeout} clocks")
    levels = [0]
    for _ in range(10 * bit_clocks - 1):
        await RisingEdge(dut.clk)
        levels.append(int(dut.uart_tx_o.value))
    return levels


def _check_tx_frame(levels, byte_val, bit_clocks, tag):
    """Every bit window must be exactly `bit_clocks` wide and hold the 8N1 value."""
    expect = [0] + [(byte_val >> i) & 1 for i in range(8)] + [1]
    for k, want in enumerate(expect):
        win = levels[k * bit_clocks:(k + 1) * bit_clocks]
        assert win == [want] * bit_clocks, (
            f"[{tag}] bit window {k} (0=START, 9=STOP) expected {want} x{bit_clocks}, "
            f"got {win}")


async def _status(m):
    s, _ = await m.read(REG_UART_STATUS)
    return s


# ── 05wf-1: byte lanes 2 and 3 of the UART_TX push (and lowest-lane priority) ─

@cocotb.test()
async def test_byte_lane_2_3_priority(dut):
    """UART_TX push picks the byte from the LOWEST asserted pstrb lane.  Lanes 2
    and 3 were never driven.  Each case carries four distinct decoy bytes so a
    wrong lane is visible; checked end-to-end through loopback and, for the
    lane-3 case, on the uart_tx_o pin itself (framing, LSB-first)."""
    m = await _setup(dut)
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_LOOPBACK)

    # (pstrb, [lane0, lane1, lane2, lane3]) -> expected = lowest set lane
    cases = [
        (0b0100, [0x11, 0x22, 0xB2, 0x44]),   # lane 2 only
        (0b1000, [0x11, 0x22, 0x33, 0xC9]),   # lane 3 only
        (0b1100, [0x55, 0x66, 0x3E, 0x99]),   # lanes 2+3 -> lane 2 wins
        (0b1010, [0x77, 0xD4, 0x88, 0x1B]),   # lanes 1+3 -> lane 1 wins
        (0b0110, [0xAA, 0x6D, 0x2F, 0xEE]),   # lanes 1+2 -> lane 1 wins
        (0b0111, [0x81, 0x42, 0x24, 0x18]),   # lanes 0..2 -> lane 0 wins
        (0b1111, [0x5C, 0xA3, 0x0F, 0xF0]),   # full word -> lane 0
    ]
    for strb, lanes in cases:
        word = lanes[0] | (lanes[1] << 8) | (lanes[2] << 16) | (lanes[3] << 24)
        want = lanes[(strb & -strb).bit_length() - 1]
        assert await m.write(REG_UART_TX, word, strb=strb) == RESP_OKAY
        await ClockCycles(dut.clk, WAIT_LOOPBACK_D0)
        st = await _status(m)
        assert st & STATUS_RX_VALID, f"[strb={strb:04b}] rx_valid=0: STATUS={st:#010x}"
        data, _ = await m.read(REG_UART_RX)
        assert data == want, (
            f"[strb={strb:04b} wdata={word:#010x}] expected lane byte 0x{want:02X}, "
            f"got {data:#010x}")
        st = await _status(m)
        assert st & STATUS_RX_EMPTY, f"[strb={strb:04b}] exactly one byte expected"

    # Lane 3 again, now observed on the pin (loopback off, TX only).
    await m.write(REG_UART_CTRL, CTRL_TX_EN)
    mon = cocotb.start_soon(_capture_tx_frame(dut, 16, 100))
    assert await m.write(REG_UART_TX, 0x6B << 24 | 0x00123456, strb=0b1000) == RESP_OKAY
    _check_tx_frame(await mon, 0x6B, 16, "lane3-pin")
    await ClockCycles(dut.clk, 40)
    st = await _status(m)
    assert st & STATUS_TX_EMPTY and not st & STATUS_TX_BUSY, f"STATUS={st:#010x}"


# ── 05wf-2: byte-strobe writes to RW registers land in the right lanes ───────

@cocotb.test()
async def test_rw_reg_partial_strobe(dut):
    """BAUD/CTRL partial-strobe writes merge into the right byte lane and leave
    the other lanes alone; lanes outside WMASK (BAUD[31:16], CTRL[31:5]) never
    store.  Also proves a strobe-0 write does not modify a register."""
    m = await _setup(dut)

    await m.write(REG_UART_BAUD, 0x0000_00AB)
    await m.write(REG_UART_BAUD, 0x0000_CD00, strb=0b0010)      # lane 1 only
    d, _ = await m.read(REG_UART_BAUD)
    assert d == 0x0000_CDAB, f"BAUD lane-1 merge: {d:#010x}"
    await m.write(REG_UART_BAUD, 0xEEFF_0000, strb=0b1100)      # lanes 2/3: masked
    d, _ = await m.read(REG_UART_BAUD)
    assert d == 0x0000_CDAB, f"BAUD lanes 2/3 must not store: {d:#010x}"
    await m.write(REG_UART_BAUD, 0x0000_0000, strb=0b0000)      # no strobe: no-op
    d, _ = await m.read(REG_UART_BAUD)
    assert d == 0x0000_CDAB, f"BAUD strobe=0 must be a no-op: {d:#010x}"
    await m.write(REG_UART_BAUD, 0x0000_0012, strb=0b0001)      # lane 0 only
    d, _ = await m.read(REG_UART_BAUD)
    assert d == 0x0000_CD12, f"BAUD lane-0 merge: {d:#010x}"

    await m.write(REG_UART_CTRL, 0x1F)
    await m.write(REG_UART_CTRL, 0xFFFF_FF00, strb=0b1110)      # lanes 1-3: outside WMASK
    d, _ = await m.read(REG_UART_CTRL)
    assert d == 0x1F, f"CTRL lanes 1-3 must not store, lane 0 untouched: {d:#010x}"
    await m.write(REG_UART_CTRL, 0x0000_0005, strb=0b0001)
    d, _ = await m.read(REG_UART_CTRL)
    assert d == 0x05, f"CTRL lane-0 write: {d:#010x}"


# ── 05wf-3: RX FIFO full, drop-newest, pointer wrap, IRQ ─────────────────────

@cocotb.test()
async def test_rx_fifo_full_drop_wrap(dut):
    """Receive 5 raw frames without reading.  FIFO depth is 4: rx_full sets only
    on the 4th byte, the 5th is dropped (oldest data preserved, no error flag),
    the first read clears rx_full, a further frame is then accepted (pointer
    wrap) and everything reads back in order.  irq_rx_valid follows rx_valid."""
    m = await _setup(dut)
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN | CTRL_IRQ_RX_VALID)
    await ClockCycles(dut.clk, 20)
    assert dut.irq_o.value == 0

    async def rx_frame(b):
        await _drive_rx_frame(dut, b, bit_clocks=16)
        dut.uart_rx_i.value = 1
        await ClockCycles(dut.clk, 24)

    first4 = [0xFF, 0x00, 0xA5, 0x5A]
    for i, b in enumerate(first4):
        await rx_frame(b)
        st = await _status(m)
        assert st & STATUS_RX_VALID and not st & STATUS_RX_EMPTY, f"#{i}: {st:#010x}"
        assert bool(st & STATUS_RX_FULL) == (i == 3), (
            f"rx_full must be set only once 4 bytes are queued (#{i}): {st:#010x}")
        assert not st & STATUS_FRAMING_ERROR
    assert dut.irq_o.value == 1

    await rx_frame(0x3C)                       # 5th: FIFO full -> dropped
    st = await _status(m)
    assert st & STATUS_RX_FULL and st & STATUS_RX_VALID, f"{st:#010x}"
    assert not st & STATUS_FRAMING_ERROR, "overflow must not raise framing_error"

    d, _ = await m.read(REG_UART_RX)           # pop #1
    assert d == first4[0], f"oldest byte must survive the overflow: {d:#010x}"
    await RisingEdge(dut.clk)
    st = await _status(m)
    assert not st & STATUS_RX_FULL and st & STATUS_RX_VALID, f"{st:#010x}"

    await rx_frame(0x81)                       # accepted: space was freed, wptr wraps
    st = await _status(m)
    assert st & STATUS_RX_FULL, f"FIFO should be full again: {st:#010x}"

    for want in first4[1:] + [0x81]:
        d, _ = await m.read(REG_UART_RX)
        assert d == want, f"FIFO order: expected 0x{want:02X}, got {d:#010x}"
        await RisingEdge(dut.clk)
    st = await _status(m)
    assert st & STATUS_RX_EMPTY and not st & STATUS_RX_VALID, (
        f"5th byte (0x3C) must not be queued: {st:#010x}")
    assert dut.irq_o.value == 0


# ── 05wf-4: TX FIFO full, drop-newest, gating by tx_en, IRQ semantics ────────

@cocotb.test()
async def test_tx_fifo_full_drop_drain(dut):
    """With tx_en=0 nothing is transmitted: 4 pushes fill the FIFO (tx_full,
    !tx_empty), the 5th is dropped.  Enabling TX then sends exactly the 4
    accepted bytes, in order (checked via loopback), clears tx_full on the first
    pop and finally raises the tx-empty IRQ."""
    m = await _setup(dut)
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN | CTRL_LOOPBACK | CTRL_IRQ_TX_EMPTY)

    sent = [0xFF, 0x00, 0xA5, 0x5A]
    for b in sent:
        assert await m.write(REG_UART_TX, b) == RESP_OKAY
    st = await _status(m)
    assert st & STATUS_TX_FULL and not st & STATUS_TX_EMPTY, f"{st:#010x}"
    assert not st & STATUS_TX_BUSY
    await m.write(REG_UART_TX, 0x3C)           # 5th: dropped
    assert dut.irq_o.value == 0, "tx-empty IRQ must stay low while bytes are queued"

    await ClockCycles(dut.clk, 400)            # tx_en=0: no frame may start
    st = await _status(m)
    assert st & STATUS_TX_FULL and not st & STATUS_TX_BUSY and st & STATUS_RX_EMPTY, (
        f"TX engine must be gated by tx_en: {st:#010x}")

    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_LOOPBACK | CTRL_IRQ_TX_EMPTY)
    await ClockCycles(dut.clk, 40)
    st = await _status(m)
    assert st & STATUS_TX_BUSY, f"engine should be mid-frame: {st:#010x}"
    assert not st & STATUS_TX_FULL, f"first pop must clear tx_full: {st:#010x}"

    await ClockCycles(dut.clk, 4 * WAIT_LOOPBACK_D0)
    st = await _status(m)
    assert st & STATUS_TX_EMPTY and not st & STATUS_TX_BUSY, f"{st:#010x}"
    assert st & STATUS_RX_FULL, f"exactly 4 bytes should have looped back: {st:#010x}"
    assert dut.irq_o.value == 1, "tx-empty IRQ after drain"
    for want in sent:
        d, _ = await m.read(REG_UART_RX)
        assert d == want, f"TX order / drop: expected 0x{want:02X}, got {d:#010x}"
        await RisingEdge(dut.clk)
    st = await _status(m)
    assert st & STATUS_RX_EMPTY, f"a 5th byte was transmitted: {st:#010x}"


# ── 05wf-5: RX false-start rejection ─────────────────────────────────────────

@cocotb.test()
async def test_rx_false_start_rejected(dut):
    """A START whose mid-bit samples (phases 7/8/9) are majority HIGH is a noise
    glitch: the receiver must return to idle without queuing a byte or raising
    framing_error, then receive the next genuine frame correctly.  A START with
    ONE high glitch inside the vote window must still be accepted (2-of-3)."""
    m = await _setup(dut)
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN | CTRL_IRQ_RX_VALID)
    await ClockCycles(dut.clk, 20)

    for width in (1, 2, 4):                    # low pulses of N clocks, then idle
        dut.uart_rx_i.value = 0
        for _ in range(width):
            await RisingEdge(dut.clk)
        dut.uart_rx_i.value = 1
        await ClockCycles(dut.clk, 48)         # > one bit period of RX_START
        st = await _status(m)
        assert st & STATUS_RX_EMPTY and not st & STATUS_FRAMING_ERROR, (
            f"glitch width {width}: false start must be rejected: STATUS={st:#010x}")
        assert dut.irq_o.value == 0

    # Receiver recovered: a real frame is still received.
    await _drive_levels(dut, _frame_levels(0xC6, 16))
    await ClockCycles(dut.clk, 24)
    d, _ = await m.read(REG_UART_RX)
    assert d == 0xC6, f"post-glitch frame: {d:#010x}"
    st = await _status(m)
    assert not st & STATUS_FRAMING_ERROR and st & STATUS_RX_EMPTY

    # 2-of-3 vote: a single-clock high glitch anywhere in the START bit, after
    # detection, hits at most one of the three consecutive vote samples at D=0.
    for pos in range(3, 16):
        byte_val = (0x35 + 37 * pos) & 0xFF
        await _drive_levels(dut, _frame_levels(byte_val, 16, invert={pos}))
        await ClockCycles(dut.clk, 24)
        d, _ = await m.read(REG_UART_RX)
        assert d == byte_val, f"START glitch@{pos}: expected 0x{byte_val:02X}, got {d:#010x}"
        st = await _status(m)
        assert not st & STATUS_FRAMING_ERROR and st & STATUS_RX_EMPTY, (
            f"START glitch@{pos}: {st:#010x}")


# ── 05wf-6: stop-bit glitch tolerance ────────────────────────────────────────

@cocotb.test()
async def test_stop_bit_glitch_no_framing_error(dut):
    """A single-clock low glitch in the STOP bit vote window is outvoted (2-of-3)
    and must not set framing_error; the byte is still delivered intact."""
    m = await _setup(dut)
    await m.write(REG_UART_BAUD, BAUD_D0)
    await m.write(REG_UART_CTRL, CTRL_RX_EN)
    await ClockCycles(dut.clk, 20)
    for pos in range(5, 13):
        stop_clk = 9 * 16 + pos
        byte_val = (0x4D + 29 * pos) & 0xFF
        await _drive_levels(dut, _frame_levels(byte_val, 16, invert={stop_clk}))
        await ClockCycles(dut.clk, 24)
        st = await _status(m)
        assert not st & STATUS_FRAMING_ERROR, f"STOP glitch@{pos}: {st:#010x}"
        d, _ = await m.read(REG_UART_RX)
        assert d == byte_val, f"STOP glitch@{pos}: expected 0x{byte_val:02X}, got {d:#010x}"


# ── 05wf-7: slow baud — os_tick low in RX_START / RX_DATA / RX_STOP ──────────

@cocotb.test()
async def test_slow_baud_tx_timing(dut):
    """BAUD=D => 1 bit = 16*(D+1) clocks.  Capture the TX pin and require every
    bit window to be exactly that wide for D = 1, 3, 4."""
    m = await _setup(dut)
    await m.write(REG_UART_CTRL, CTRL_TX_EN)
    for d_val, byte_val in ((1, 0xA5), (3, 0xD3), (4, 0x01)):
        bc = 16 * (d_val + 1)
        await m.write(REG_UART_BAUD, d_val)
        await ClockCycles(dut.clk, 2 * bc)     # let a stale phase wrap before the push
        mon = cocotb.start_soon(_capture_tx_frame(dut, bc, 4 * bc))
        assert await m.write(REG_UART_TX, byte_val) == RESP_OKAY
        _check_tx_frame(await mon, byte_val, bc, f"D={d_val}")
        await ClockCycles(dut.clk, 3 * bc)
        st = await _status(m)
        assert st & STATUS_TX_EMPTY and not st & STATUS_TX_BUSY, f"D={d_val}: {st:#010x}"


@cocotb.test()
async def test_slow_baud_rx_raw_and_framing(dut):
    """Raw-pin RX at D=1 and D=3 (os_tick only every 2 / 4 clocks): data, STOP
    framing error + read-to-clear, a false START (>=1 os_tick long), and
    1-clock glitches swept across one os_tick period of a data bit and the STOP
    bit -- a 1-clock glitch can hit at most one of the 3 spaced vote samples."""
    m = await _setup(dut)
    await m.write(REG_UART_CTRL, CTRL_RX_EN)
    for d_val in (1, 3):
        bc = 16 * (d_val + 1)
        await m.write(REG_UART_BAUD, d_val)
        await ClockCycles(dut.clk, 2 * bc)

        async def rx(levels):
            await _drive_levels(dut, levels)
            await ClockCycles(dut.clk, 2 * bc)

        await rx(_frame_levels(0x96, bc))
        d, _ = await m.read(REG_UART_RX)
        assert d == 0x96, f"D={d_val}: {d:#010x}"
        assert not (await _status(m)) & STATUS_FRAMING_ERROR

        await rx(_frame_levels(0x69, bc, stop_bit=0))
        st = await _status(m)
        assert st & STATUS_FRAMING_ERROR and st & STATUS_RX_VALID, f"D={d_val}: {st:#010x}"
        d, _ = await m.read(REG_UART_RX)
        assert d == 0x69
        assert not (await _status(m)) & STATUS_FRAMING_ERROR, "read-to-clear"

        # False START: low long enough to span an os_tick, then high.
        dut.uart_rx_i.value = 0
        await ClockCycles(dut.clk, d_val + 2)
        dut.uart_rx_i.value = 1
        await ClockCycles(dut.clk, 2 * bc)
        st = await _status(m)
        assert st & STATUS_RX_EMPTY and not st & STATUS_FRAMING_ERROR, (
            f"D={d_val}: false start accepted: {st:#010x}")

        for off in range(d_val + 1):           # one full os_tick period of offsets
            data_clk = (1 + 2) * bc + bc // 2 + off      # mid of data bit 2
            stop_clk = 9 * bc + bc // 2 + off
            byte_val = (0xB1 + 53 * off + d_val) & 0xFF
            await rx(_frame_levels(byte_val, bc, invert={data_clk, stop_clk}))
            st = await _status(m)
            assert not st & STATUS_FRAMING_ERROR, f"D={d_val} off={off}: {st:#010x}"
            d, _ = await m.read(REG_UART_RX)
            assert d == byte_val, (
                f"D={d_val} off={off}: expected 0x{byte_val:02X}, got {d:#010x}")


@cocotb.test()
async def test_slow_baud_loopback(dut):
    """Full TX->RX loopback at D=3 (64 clocks/bit): the shared os_tick generator
    keeps both engines aligned when os_tick is NOT high every clock."""
    m = await _setup(dut)
    await m.write(REG_UART_BAUD, 3)
    await m.write(REG_UART_CTRL, CTRL_TX_EN | CTRL_RX_EN | CTRL_LOOPBACK)
    for byte_val in (0xE1, 0x1E):
        await m.write(REG_UART_TX, byte_val)
        await ClockCycles(dut.clk, 14 * 64)
        d, _ = await m.read(REG_UART_RX)
        assert d == byte_val, f"expected 0x{byte_val:02X}, got {d:#010x}"
        st = await _status(m)
        assert st & STATUS_RX_EMPTY and not st & STATUS_FRAMING_ERROR, f"{st:#010x}"
