# test_timer.py
# Phase 5 (M4) — cocotb directed-test suite for timer.sv
#
# DUT:  timer  (TOPLEVEL=timer)
# BFM:  AXI4LiteMaster (bfm/axi4lite_master.py) drives s_axil_* registers
#
# Register byte addresses
#   0x00  TMR_COUNTER  RO         live count (HW-written)
#   0x04  TMR_COMPARE  RW 0xFFFFFFFF
#   0x08  TMR_CTRL     RW [2:0]   [0]=enable [1]=irq_en [2]=auto_clear(edge)
#   0x0C  TMR_PRESCALE RW [15:0]  0 → tick every clock
#
# Timing notes:
#   - TMR_COUNTER is updated every clock; AXI reads have latency of a few
#     cycles, so counter assertions use "strictly increasing" or bounded-delta
#     tolerances rather than exact equality.
#   - Each .write() / .read() consumes multiple clock cycles; the counter
#     advances during transactions.  All tolerance windows account for this.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from bfm.axi4lite_master import AXI4LiteMaster

# ── Register byte addresses ───────────────────────────────────────────────────
REG_TMR_COUNTER  = 0x00
REG_TMR_COMPARE  = 0x04
REG_TMR_CTRL     = 0x08
REG_TMR_PRESCALE = 0x0C

# TMR_CTRL bit positions
CTRL_ENABLE     = (1 << 0)
CTRL_IRQ_EN     = (1 << 1)
CTRL_AUTO_CLEAR = (1 << 2)

# AXI response codes
RESP_OKAY = 0b00

# ── Setup helper ──────────────────────────────────────────────────────────────

async def _setup(dut):
    """Start 2 ns clock, apply 5-cycle reset, wait 2 idle cycles.
    Returns an AXI4LiteMaster pointed at the DUT slave port.
    """
    cocotb.start_soon(Clock(dut.clk, 2, units="ns").start())

    m = AXI4LiteMaster(dut, "s_axil_", dut.clk)

    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)

    return m


# ── Test 1: RW register round-trip ───────────────────────────────────────────

@cocotb.test()
async def test_rw_roundtrip(dut):
    """Write COMPARE, PRESCALE, CTRL then read each back."""
    m = await _setup(dut)

    # Write values
    resp = await m.write(REG_TMR_COMPARE,  0x1000)
    assert resp == RESP_OKAY, f"write COMPARE RESP={resp}"

    resp = await m.write(REG_TMR_PRESCALE, 0x0007)
    assert resp == RESP_OKAY, f"write PRESCALE RESP={resp}"

    # Write CTRL with only [2:0] — disable everything so counter stays idle
    resp = await m.write(REG_TMR_CTRL, 0x2)   # irq_en only, not enabled
    assert resp == RESP_OKAY, f"write CTRL RESP={resp}"

    # Read back COMPARE
    data, resp = await m.read(REG_TMR_COMPARE)
    assert resp == RESP_OKAY
    assert data == 0x1000, f"TMR_COMPARE readback: got {data:#010x}, expected 0x1000"

    # Read back PRESCALE — only [15:0] writable per WMASK 0x0000FFFF
    data, resp = await m.read(REG_TMR_PRESCALE)
    assert resp == RESP_OKAY
    assert (data & 0xFFFF) == 0x0007, (
        f"TMR_PRESCALE readback: got {data:#010x}, expected low 16 bits = 0x0007"
    )

    # Read back CTRL — only [2:0] writable per WMASK 0x7
    data, resp = await m.read(REG_TMR_CTRL)
    assert resp == RESP_OKAY
    assert (data & 0x7) == 0x2, (
        f"TMR_CTRL readback: got {data:#010x}, expected [2:0]=0x2"
    )
    dut._log.info("test_rw_roundtrip PASS")


# ── Test 2: counter increments while enabled ──────────────────────────────────

@cocotb.test()
async def test_counter_increments(dut):
    """PRESCALE=0 (tick every clock), enable=1; counter must advance."""
    m = await _setup(dut)

    # Ensure compare is above any count we'll reach in this short test
    await m.write(REG_TMR_COMPARE,  0xFFFF_FFFF)
    await m.write(REG_TMR_PRESCALE, 0)
    await m.write(REG_TMR_CTRL, CTRL_ENABLE)  # enable only

    # First sample
    count_a, _ = await m.read(REG_TMR_COUNTER)

    # Wait N cycles (counter ticks every cycle)
    N = 20
    for _ in range(N):
        await RisingEdge(dut.clk)

    # Second sample
    count_b, _ = await m.read(REG_TMR_COUNTER)

    assert count_b > count_a, (
        f"Counter did not advance: count_a={count_a} count_b={count_b}"
    )

    # Delta: the counter advances during the two AXI reads themselves too.
    # Each AXI read takes a small number of cycles; allow generous tolerance.
    # The read itself consumes ~4-6 clocks; N waits in between; so delta should
    # be between N and N + ~20 (two read transactions overhead).
    delta = count_b - count_a
    assert delta >= N - 2, (
        f"Counter advanced too slowly: delta={delta}, expected >= {N - 2}"
    )
    assert delta <= N + 30, (
        f"Counter advanced too fast: delta={delta}, expected <= {N + 30}"
    )
    dut._log.info(f"test_counter_increments PASS  delta={delta} cycles")


# ── Test 3: prescaler slows counting ─────────────────────────────────────────

@cocotb.test()
async def test_prescaler(dut):
    """PRESCALE=3 → tick every 4 clocks; observed increment over a fixed
    ClockCycles window must equal WAIT_CYCLES // (PRESCALE + 1) within ±1.

    Samples the internal counter (dut.count_q, exposed by --public-flat-rw)
    directly rather than via AXI reads, so the measurement window is exact
    and free of AXI transaction latency.
    """
    m = await _setup(dut)

    PRESCALE = 3  # tick every (3+1)=4 clocks
    await m.write(REG_TMR_COMPARE,  0xFFFF_FFFF)
    await m.write(REG_TMR_PRESCALE, PRESCALE)
    await m.write(REG_TMR_CTRL,     CTRL_ENABLE)

    # Align to a clock edge, then sample the live counter directly.
    await RisingEdge(dut.clk)
    start_count = dut.count_q.value.integer

    WAIT_CYCLES = 40
    await ClockCycles(dut.clk, WAIT_CYCLES)

    end_count = dut.count_q.value.integer

    # Counter is CNT_W=32-bit; no wrap expected in a 40-cycle window, but mask
    # to the counter width to be safe.
    delta = (end_count - start_count) & 0xFFFF_FFFF
    expected = WAIT_CYCLES // (PRESCALE + 1)  # 40 // 4 = 10

    assert abs(delta - expected) <= 1, (
        f"prescaler rate wrong: PRESCALE={PRESCALE}, window={WAIT_CYCLES} clks, "
        f"delta={delta}, expected≈{expected} (±1)"
    )
    dut._log.info(
        f"test_prescaler PASS  delta={delta} over {WAIT_CYCLES} clks "
        f"(expected {expected}, PRESCALE={PRESCALE})"
    )


# ── Test 4: IRQ on compare match ─────────────────────────────────────────────

@cocotb.test()
async def test_irq_on_compare(dut):
    """COMPARE=5, CTRL=enable|irq_en, PRESCALE=0; irq_o must assert."""
    m = await _setup(dut)

    COMPARE = 5
    TIMEOUT = 100  # cycles to wait for irq_o

    await m.write(REG_TMR_COMPARE,  COMPARE)
    await m.write(REG_TMR_PRESCALE, 0)
    await m.write(REG_TMR_CTRL,     CTRL_ENABLE | CTRL_IRQ_EN)

    # Poll irq_o until asserted (combinational: irq_en & irq_pending_q)
    fired = False
    for _ in range(TIMEOUT):
        await RisingEdge(dut.clk)
        if dut.irq_o.value == 1:
            fired = True
            break

    assert fired, (
        f"irq_o never asserted within {TIMEOUT} cycles "
        f"(COMPARE={COMPARE}, PRESCALE=0)"
    )

    # Verify counter is at or past compare value
    count, _ = await m.read(REG_TMR_COUNTER)
    assert count >= COMPARE, (
        f"irq fired but counter={count} < compare={COMPARE}"
    )
    dut._log.info(f"test_irq_on_compare PASS  count={count} when irq_o asserted")


# ── Test 5: auto_clear clears irq and resets count ───────────────────────────

@cocotb.test()
async def test_auto_clear(dut):
    """After irq fires: pulse auto_clear bit; irq_o goes 0 and count resets."""
    m = await _setup(dut)

    COMPARE = 5
    TIMEOUT = 100

    # Set up timer so IRQ fires
    await m.write(REG_TMR_COMPARE,  COMPARE)
    await m.write(REG_TMR_PRESCALE, 0)
    await m.write(REG_TMR_CTRL,     CTRL_ENABLE | CTRL_IRQ_EN)

    # Wait for irq_o
    fired = False
    for _ in range(TIMEOUT):
        await RisingEdge(dut.clk)
        if dut.irq_o.value == 1:
            fired = True
            break

    assert fired, f"IRQ never fired before auto_clear test (COMPARE={COMPARE})"

    # Pulse auto_clear: write CTRL with bit2 set, then clear bit2.
    # The RTL detects the 0→1 rising edge on CTRL[2] (auto_clear_pulse).
    await m.write(REG_TMR_CTRL, CTRL_ENABLE | CTRL_IRQ_EN | CTRL_AUTO_CLEAR)
    await m.write(REG_TMR_CTRL, CTRL_ENABLE | CTRL_IRQ_EN)  # drop bit2

    # Give a few cycles for irq_pending_q to clear and count to reset
    for _ in range(4):
        await RisingEdge(dut.clk)

    assert dut.irq_o.value == 0, (
        f"irq_o expected 0 after auto_clear, got {dut.irq_o.value}"
    )

    count, _ = await m.read(REG_TMR_COUNTER)
    # After auto_clear the count resets to 0; it will have incremented a few
    # cycles by the time we read it, but must be well below COMPARE.
    assert count < COMPARE + 10, (
        f"count after auto_clear should be near 0, got {count}"
    )
    dut._log.info(f"test_auto_clear PASS  irq_o=0, count={count} after clear")


# ── Test 6: disable freezes counter ──────────────────────────────────────────

@cocotb.test()
async def test_disable_freezes_counter(dut):
    """Enable timer for a while, then disable; two reads must return same value."""
    m = await _setup(dut)

    await m.write(REG_TMR_COMPARE,  0xFFFF_FFFF)
    await m.write(REG_TMR_PRESCALE, 0)
    await m.write(REG_TMR_CTRL,     CTRL_ENABLE)

    # Run for a while so count is non-trivial
    for _ in range(30):
        await RisingEdge(dut.clk)

    # Disable
    await m.write(REG_TMR_CTRL, 0)  # enable=0, irq_en=0

    # Read twice with some cycles in between
    count_a, _ = await m.read(REG_TMR_COUNTER)
    for _ in range(10):
        await RisingEdge(dut.clk)
    count_b, _ = await m.read(REG_TMR_COUNTER)

    assert count_a == count_b, (
        f"Counter advanced while disabled: count_a={count_a}, count_b={count_b}"
    )
    assert count_a > 0, "Counter should be non-zero before disable"
    dut._log.info(f"test_disable_freezes_counter PASS  frozen at count={count_a}")
