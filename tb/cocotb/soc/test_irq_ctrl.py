# test_irq_ctrl.py
# Phase 5 (M4) — cocotb directed-test suite for interrupt_controller.sv
#
# DUT:  interrupt_controller  (TOPLEVEL=interrupt_controller)
# BFM:  AXI4LiteMaster (bfm/axi4lite_master.py) drives s_axil_* registers
# Side-inputs: irq_src_i[4:0] poked directly via dut.irq_src_i.value
#
# Register byte addresses
#   0x00  IRQ_STATUS         RO  raw synced sources
#   0x04  IRQ_MASK           RW  per-source enable
#   0x08  IRQ_PENDING_MASKED RO  STATUS & MASK
#
# Timing note: irq_src_i goes through a 1-FF synchroniser, so after any
# change to irq_src_i we must wait at least 2 rising edges before reading
# status registers or sampling irq_o.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from bfm.axi4lite_master import AXI4LiteMaster

# ── Register byte addresses ───────────────────────────────────────────────────
REG_IRQ_STATUS         = 0x00
REG_IRQ_MASK           = 0x04
REG_IRQ_PENDING_MASKED = 0x08

# AXI response codes
RESP_OKAY = 0b00

# Synchroniser depth: 1 FF → need 2 clock edges to guarantee visibility
SYNC_CYCLES = 2

# ── Setup helper ──────────────────────────────────────────────────────────────

async def _setup(dut):
    """Start 2 ns clock, apply 5-cycle reset, wait 2 idle cycles.
    Returns an AXI4LiteMaster pointed at the DUT slave port.
    """
    cocotb.start_soon(Clock(dut.clk, 2, units="ns").start())

    m = AXI4LiteMaster(dut, "s_axil_", dut.clk)

    # Drive side-input to known idle state before reset
    dut.irq_src_i.value = 0

    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)

    return m


# ── Test 1: IRQ_MASK RW round-trip ───────────────────────────────────────────

@cocotb.test()
async def test_mask_rw(dut):
    """Write IRQ_MASK=0x1F; read back; verify only [4:0] bits stick."""
    m = await _setup(dut)
    dut.irq_src_i.value = 0

    # Write all 5 source bits set
    resp = await m.write(REG_IRQ_MASK, 0x1F)
    assert resp == RESP_OKAY, f"write IRQ_MASK RESP={resp}"

    data, resp = await m.read(REG_IRQ_MASK)
    assert resp == RESP_OKAY, f"read IRQ_MASK RESP={resp}"
    assert (data & 0x1F) == 0x1F, f"IRQ_MASK readback: got {data:#010x}, expected low 5 bits = 0x1F"

    # Write with high bits set — WMASK must suppress bits above [4:0]
    resp = await m.write(REG_IRQ_MASK, 0xFFFF_FFFF)
    assert resp == RESP_OKAY

    data, resp = await m.read(REG_IRQ_MASK)
    assert resp == RESP_OKAY
    assert (data & ~0x1F) == 0, (
        f"IRQ_MASK bits above [4:0] should be zero; got {data:#010x}"
    )
    assert (data & 0x1F) == 0x1F, (
        f"IRQ_MASK low 5 bits should be 0x1F; got {data:#010x}"
    )
    dut._log.info("test_mask_rw PASS")


# ── Test 2: IRQ_STATUS mirrors irq_src_i (after sync) ────────────────────────

@cocotb.test()
async def test_status_mirror(dut):
    """Drive irq_src_i=0b00101; after sync IRQ_STATUS must read 0x05."""
    m = await _setup(dut)
    dut.irq_src_i.value = 0

    dut.irq_src_i.value = 0b00101  # UART + TIMER

    # Wait for 1-FF synchroniser to propagate (need ≥2 edges)
    for _ in range(SYNC_CYCLES):
        await RisingEdge(dut.clk)

    data, resp = await m.read(REG_IRQ_STATUS)
    assert resp == RESP_OKAY
    assert (data & 0x1F) == 0x05, (
        f"IRQ_STATUS expected 0x05, got {data:#010x}"
    )

    # Clear and verify it drops
    dut.irq_src_i.value = 0
    for _ in range(SYNC_CYCLES):
        await RisingEdge(dut.clk)

    data, _ = await m.read(REG_IRQ_STATUS)
    assert (data & 0x1F) == 0x00, (
        f"IRQ_STATUS should be 0 after clear, got {data:#010x}"
    )
    dut._log.info("test_status_mirror PASS")


# ── Test 3: IRQ_PENDING_MASKED = STATUS & MASK ────────────────────────────────

@cocotb.test()
async def test_masked_pending(dut):
    """irq_src_i=0x1F, IRQ_MASK=0x04 → IRQ_PENDING_MASKED==0x04."""
    m = await _setup(dut)
    dut.irq_src_i.value = 0

    # Enable only TIMER (bit 2)
    await m.write(REG_IRQ_MASK, 0x04)

    # Assert all sources
    dut.irq_src_i.value = 0x1F
    for _ in range(SYNC_CYCLES):
        await RisingEdge(dut.clk)

    data, resp = await m.read(REG_IRQ_PENDING_MASKED)
    assert resp == RESP_OKAY
    assert (data & 0x1F) == 0x04, (
        f"IRQ_PENDING_MASKED expected 0x04, got {data:#010x}"
    )

    # Mask everything off → pending should be 0
    await m.write(REG_IRQ_MASK, 0x00)
    for _ in range(SYNC_CYCLES):
        await RisingEdge(dut.clk)

    data, _ = await m.read(REG_IRQ_PENDING_MASKED)
    assert (data & 0x1F) == 0x00, (
        f"IRQ_PENDING_MASKED should be 0 with mask=0, got {data:#010x}"
    )
    dut._log.info("test_masked_pending PASS")


# ── Test 4: per-source sweep — irq_o gated by mask ───────────────────────────

@cocotb.test()
async def test_per_source_sweep(dut):
    """For each of the 5 sources: mask-enable → assert → irq_o=1; mask-disable → irq_o=0."""
    m = await _setup(dut)
    dut.irq_src_i.value = 0

    source_names = ["UART", "SPI", "TIMER", "DMA", "GPU"]

    for i in range(5):
        bit = 1 << i
        dut._log.info(f"  source {i} ({source_names[i]})")

        # Unmask this source only
        await m.write(REG_IRQ_MASK, bit)

        # Assert this source
        dut.irq_src_i.value = bit
        for _ in range(SYNC_CYCLES):
            await RisingEdge(dut.clk)

        assert dut.irq_o.value == 1, (
            f"source {i} ({source_names[i]}): irq_o expected 1, got {dut.irq_o.value}"
        )

        # Mask off → irq_o must deassert immediately (combinational on sync output)
        await m.write(REG_IRQ_MASK, 0x00)
        # After the write completes the mask register is updated; give 1 cycle
        # for the combinational masked path to settle in the simulation delta.
        await RisingEdge(dut.clk)

        assert dut.irq_o.value == 0, (
            f"source {i} ({source_names[i]}): irq_o expected 0 after mask=0, "
            f"got {dut.irq_o.value}"
        )

        # Clear source for next iteration
        dut.irq_src_i.value = 0
        for _ in range(SYNC_CYCLES):
            await RisingEdge(dut.clk)

    dut._log.info("test_per_source_sweep PASS")


# ── Test 5: multi-source OR, then clear ──────────────────────────────────────

@cocotb.test()
async def test_multi_source_or(dut):
    """irq_src_i=0b01010, IRQ_MASK=0x1F → irq_o=1, PENDING=0x0A; clear src → irq_o=0."""
    m = await _setup(dut)
    dut.irq_src_i.value = 0

    # Enable all sources
    await m.write(REG_IRQ_MASK, 0x1F)

    # Assert SPI (1) + DMA (3) = 0b01010 = 0x0A
    dut.irq_src_i.value = 0b01010
    for _ in range(SYNC_CYCLES):
        await RisingEdge(dut.clk)

    assert dut.irq_o.value == 1, (
        f"irq_o expected 1 with multi-source active, got {dut.irq_o.value}"
    )

    data, resp = await m.read(REG_IRQ_PENDING_MASKED)
    assert resp == RESP_OKAY
    assert (data & 0x1F) == 0x0A, (
        f"IRQ_PENDING_MASKED expected 0x0A, got {data:#010x}"
    )

    # Clear all sources → irq_o must deassert
    dut.irq_src_i.value = 0
    for _ in range(SYNC_CYCLES):
        await RisingEdge(dut.clk)

    assert dut.irq_o.value == 0, (
        f"irq_o expected 0 after sources cleared, got {dut.irq_o.value}"
    )

    data, _ = await m.read(REG_IRQ_PENDING_MASKED)
    assert (data & 0x1F) == 0x00, (
        f"IRQ_PENDING_MASKED expected 0 after clear, got {data:#010x}"
    )
    dut._log.info("test_multi_source_or PASS")
