# test_sram_controller.py
# Phase 5 (M6) — cocotb unit suite for the behavioral AXI4-slave SRAM controller.
#
# Drives the slave directly with the AXI4 master BFM (signal prefix "s", the
# controller's slave-port prefix).  Covers single + burst read/write, byte
# strobes, ID echo, out-of-range SLVERR, and back-to-back bursts.
#
# BFM API (axi4_master.AXI4Master):
#   await m.write(addr, data_list, strb=0xF)  -> bresp (int)
#   await m.read(addr, length=N)              -> (data_list, rresp)
# There is NO write_word / read_word helper — use single-element lists.
#
# The BFM drives no AxID fields (the crossbar tags them internally).  ID-echo
# tests use the manual _write_with_id / _read_with_id helpers below.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly

from bfm.axi4_master import AXI4Master, RESP_OKAY

CLK_PERIOD_NS = 2
RESP_SLVERR = 0b10
SIZE_4B = 0b010
BURST_INCR = 0b01

SRAM_BASE = 0x0000_2000
OOR_ADDR  = 0x0000_1000   # below SRAM window -> SLVERR


async def _setup(dut):
    """Start clock, apply reset, return an AXI4 master bound to the slave port."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    m = AXI4Master(dut, "s", dut.clk)
    # BFM initialises all master-driven signals except AxID (BFM has no id field).
    # Initialise the ID inputs the BFM leaves untouched.
    dut.s_awid.value = 0
    dut.s_arid.value = 0
    # Assert reset for 5 cycles, then release.
    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    return m


async def _write_with_id(dut, addr, data, axid, strb=0xF):
    """Manual single-beat write that drives a non-zero AWID. Returns (bresp, bid).

    Does not use the BFM so we can set AxID freely.
    Timing: drives AW and polls awready; then drives W and polls wready; then
    collects B-channel response.  All polls are RisingEdge-based (safe for
    registered-ready responders like this FSM).
    """
    # AW channel
    dut.s_awid.value    = axid
    dut.s_awaddr.value  = addr
    dut.s_awlen.value   = 0        # single beat
    dut.s_awsize.value  = SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    await RisingEdge(dut.clk)
    while not dut.s_awready.value:
        await RisingEdge(dut.clk)
    dut.s_awvalid.value = 0

    # W channel — wready goes high once FSM reaches W_DATA (next cycle)
    dut.s_wdata.value  = data
    dut.s_wstrb.value  = strb
    dut.s_wlast.value  = 1
    dut.s_wvalid.value = 1
    await RisingEdge(dut.clk)
    while not dut.s_wready.value:
        await RisingEdge(dut.clk)
    dut.s_wvalid.value = 0
    dut.s_wlast.value  = 0

    # B channel
    dut.s_bready.value = 1
    await RisingEdge(dut.clk)
    while not dut.s_bvalid.value:
        await RisingEdge(dut.clk)
    await ReadOnly()
    bresp = int(dut.s_bresp.value)
    bid   = int(dut.s_bid.value)
    await RisingEdge(dut.clk)
    dut.s_bready.value = 0
    return bresp, bid


async def _read_with_id(dut, addr, axid):
    """Manual single-beat read that drives a non-zero ARID. Returns (data, rresp, rid)."""
    # AR channel
    dut.s_arid.value    = axid
    dut.s_araddr.value  = addr
    dut.s_arlen.value   = 0        # single beat
    dut.s_arsize.value  = SIZE_4B
    dut.s_arburst.value = BURST_INCR
    dut.s_arvalid.value = 1
    await RisingEdge(dut.clk)
    while not dut.s_arready.value:
        await RisingEdge(dut.clk)
    dut.s_arvalid.value = 0

    # R channel
    dut.s_rready.value = 1
    await RisingEdge(dut.clk)
    while not dut.s_rvalid.value:
        await RisingEdge(dut.clk)
    await ReadOnly()
    data  = int(dut.s_rdata.value)
    rresp = int(dut.s_rresp.value)
    rid   = int(dut.s_rid.value)
    rlast = int(dut.s_rlast.value)
    await RisingEdge(dut.clk)
    dut.s_rready.value = 0
    assert rlast == 1, "single-beat read must assert RLAST"
    return data, rresp, rid


# ── Test 1: single-beat write then read-back ─────────────────────────────────

@cocotb.test()
async def test_single_write_read(dut):
    """Single-beat write then read-back returns the same word."""
    m = await _setup(dut)
    addr = SRAM_BASE + 0x40
    bresp = await m.write(addr, [0xDEAD_BEEF])
    assert bresp == RESP_OKAY, f"write resp {bresp:#x} != OKAY"
    data, rresp = await m.read(addr, length=1)
    assert rresp == RESP_OKAY, f"read resp {rresp:#x} != OKAY"
    assert data[0] == 0xDEAD_BEEF, f"readback {data[0]:#010x} != 0xDEADBEEF"
    dut._log.info("test_single_write_read PASS")


# ── Test 2: 4-beat INCR burst write then burst read-back ─────────────────────

@cocotb.test()
async def test_burst_write_read(dut):
    """4-beat INCR burst write then 4-beat burst read-back — all words match."""
    m = await _setup(dut)
    base  = SRAM_BASE + 0x100
    words = [0x1111_0000, 0x2222_0001, 0x3333_0002, 0x4444_0003]
    bresp = await m.write(base, words)
    assert bresp == RESP_OKAY, f"burst write resp {bresp:#x}"
    data, rresp = await m.read(base, length=4)
    assert rresp == RESP_OKAY, f"burst read resp {rresp:#x}"
    assert data == words, \
        f"burst readback mismatch:\n  got {[hex(d) for d in data]}\n  exp {[hex(w) for w in words]}"
    dut._log.info("test_burst_write_read PASS")


# ── Test 3: WSTRB partial-byte write ─────────────────────────────────────────

@cocotb.test()
async def test_wstrb_partial(dut):
    """WSTRB byte enables update only the selected lanes."""
    m = await _setup(dut)
    addr = SRAM_BASE + 0x200
    # Prime the word with all-ones.
    bresp = await m.write(addr, [0xFFFF_FFFF])
    assert bresp == RESP_OKAY
    # Write 0xAA to the lowest byte only (strb=0b0001).
    bresp = await m.write(addr, [0x0000_00AA], strb=0b0001)
    assert bresp == RESP_OKAY
    data, rresp = await m.read(addr, length=1)
    assert rresp == RESP_OKAY
    # Bytes [3:1] unchanged (0xFF each); byte 0 updated to 0xAA.
    assert data[0] == 0xFFFF_FFAA, \
        f"strb result {data[0]:#010x} != 0xFFFFFFAA"
    dut._log.info("test_wstrb_partial PASS")


# ── Test 4: BID / RID echo non-zero AWID / ARID ──────────────────────────────

@cocotb.test()
async def test_id_echo(dut):
    """BID echoes AWID and RID echoes ARID for non-zero IDs."""
    m = await _setup(dut)   # noqa: F841 — clock/reset needed
    addr = SRAM_BASE + 0x300

    # Write with AWID=0xA, verify BID=0xA.
    bresp, bid = await _write_with_id(dut, addr, 0xCAFE_F00D, axid=0xA)
    assert bresp == RESP_OKAY, f"write resp {bresp:#x}"
    assert bid == 0xA, f"BID echo got {bid:#x}, expected 0xA"

    # Read back with ARID=0x5, verify RID=0x5 and data.
    data, rresp, rid = await _read_with_id(dut, addr, axid=0x5)
    assert rresp == RESP_OKAY, f"read resp {rresp:#x}"
    assert rid == 0x5, f"RID echo got {rid:#x}, expected 0x5"
    assert data == 0xCAFE_F00D, f"readback {data:#010x}"
    dut._log.info("test_id_echo PASS")


# ── Test 5: out-of-range address returns SLVERR ───────────────────────────────

@cocotb.test()
async def test_out_of_range_slverr(dut):
    """Address below SRAM_BASE (0x0000_1000) returns SLVERR on write and read."""
    m = await _setup(dut)
    # Out-of-range write.
    bresp = await m.write(OOR_ADDR, [0x1234_5678])
    assert bresp == RESP_SLVERR, \
        f"OOR write resp {bresp:#x} != SLVERR (0x{RESP_SLVERR:x})"
    # Out-of-range read.
    _, rresp = await m.read(OOR_ADDR, length=1)
    assert rresp == RESP_SLVERR, \
        f"OOR read resp {rresp:#x} != SLVERR (0x{RESP_SLVERR:x})"
    dut._log.info("test_out_of_range_slverr PASS")


# ── Test 6: back-to-back bursts, no idle gap ─────────────────────────────────

@cocotb.test()
async def test_back_to_back_bursts(dut):
    """Two consecutive 4-beat bursts with no idle gap preserve data integrity."""
    m = await _setup(dut)
    a0 = SRAM_BASE + 0x400
    a1 = SRAM_BASE + 0x500
    w0 = [0x0A00 + i for i in range(4)]
    w1 = [0x0B00 + i for i in range(4)]

    # Back-to-back writes.
    assert await m.write(a0, w0) == RESP_OKAY, "burst0 write SLVERR"
    assert await m.write(a1, w1) == RESP_OKAY, "burst1 write SLVERR"

    # Read back and verify both.
    d0, r0 = await m.read(a0, length=4)
    d1, r1 = await m.read(a1, length=4)
    assert r0 == RESP_OKAY and r1 == RESP_OKAY, \
        f"read resps {r0:#x}, {r1:#x}"
    assert d0 == w0, f"burst0 mismatch {[hex(d) for d in d0]}"
    assert d1 == w1, f"burst1 mismatch {[hex(d) for d in d1]}"
    dut._log.info("test_back_to_back_bursts PASS")
