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

import random

import cocotb
from bfm.axi4_master import RESP_OKAY, AXI4Master
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, with_timeout
from cocotb.utils import get_sim_time

CLK_PERIOD_NS = 2
RESP_SLVERR = 0b10
SIZE_4B = 0b010
BURST_FIXED = 0b00
BURST_INCR = 0b01
BURST_WRAP = 0b10

SRAM_BASE  = 0x0000_2000
SRAM_LIMIT = 0x0FFF_FFFF   # inclusive top of SRAM window
OOR_ADDR   = 0x0000_1000   # below SRAM window -> SLVERR


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
    collects B-channel response.

    GH #104 fix (fr_null_20260724_051800_00) hardening: every poll now checks
    its ready/valid signal via `await ReadOnly()` **before** advancing to a
    new `RisingEdge` -- the same check-then-advance order the AXI4Master BFM
    uses (`await ReadOnly(); if ready: break; await edge()`), NOT
    `await RisingEdge(); await ReadOnly(); if ready: ...`. Those two orderings
    are not equivalent for a combinationally-immediate responder like this
    FSM: awready/arready/wready/bvalid/rvalid can drop back to 0 in the very
    same cycle a request is accepted (the FSM has already advanced state), so
    checking *after* crossing that accept edge sees the post-accept 0 and
    never recognises the (already-completed) handshake -- an infinite poll.
    Checking via ReadOnly() *before* advancing samples the signal as it
    stands for the cycle the request is actually live in, matching AXI4's
    same-cycle valid&ready semantics. (This was a bug in an earlier revision
    of this helper reached while investigating fr_null_20260724_051800_00 --
    it hung indefinitely, not an RTL deadlock; see knowledge.md.)
    """
    # AW channel
    dut.s_awid.value    = axid
    dut.s_awaddr.value  = addr
    dut.s_awlen.value   = 0        # single beat
    dut.s_awsize.value  = SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_awready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_awvalid.value = 0

    # W channel — wready goes high once FSM reaches W_DATA (next cycle)
    dut.s_wdata.value  = data
    dut.s_wstrb.value  = strb
    dut.s_wlast.value  = 1
    dut.s_wvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_wready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_wvalid.value = 0
    dut.s_wlast.value  = 0

    # B channel
    dut.s_bready.value = 1
    while True:
        await ReadOnly()
        if dut.s_bvalid.value:
            break
        await RisingEdge(dut.clk)
    bresp = int(dut.s_bresp.value)
    bid   = int(dut.s_bid.value)
    await RisingEdge(dut.clk)
    dut.s_bready.value = 0
    return bresp, bid


async def _read_with_id(dut, addr, axid):
    """Manual single-beat read that drives a non-zero ARID. Returns (data, rresp, rid).

    See _write_with_id's docstring for why every poll below checks via
    ReadOnly() *before* advancing to a new RisingEdge (GH #104
    fr_null_20260724_051800_00 hardening).
    """
    # AR channel
    dut.s_arid.value    = axid
    dut.s_araddr.value  = addr
    dut.s_arlen.value   = 0        # single beat
    dut.s_arsize.value  = SIZE_4B
    dut.s_arburst.value = BURST_INCR
    dut.s_arvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_arready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_arvalid.value = 0

    # R channel
    dut.s_rready.value = 1
    while True:
        await ReadOnly()
        if dut.s_rvalid.value:
            break
        await RisingEdge(dut.clk)
    data  = int(dut.s_rdata.value)
    rresp = int(dut.s_rresp.value)
    rid   = int(dut.s_rid.value)
    rlast = int(dut.s_rlast.value)
    await RisingEdge(dut.clk)
    dut.s_rready.value = 0
    assert rlast == 1, "single-beat read must assert RLAST"
    return data, rresp, rid


def _apply_strb(old, new, strb):
    """Byte-merge `old` and `new` per a 4-bit WSTRB mask (bit i -> byte i,
    LSB-first) -- the same semantics as sram_controller.sv's stage-3 write
    (`mem[GIDX][b*8 +: 8] <= grp_wdata_q[...][b*8 +: 8]` gated per-byte by
    grp_we_q[...][b]). Used to compute expected readback values without
    hand-deriving bitmasks per test (a frequent source of test-authoring
    bugs, not DUT bugs)."""
    result = 0
    for b in range(4):
        byte = (new >> (b * 8)) & 0xFF if (strb >> b) & 1 else (old >> (b * 8)) & 0xFF
        result |= byte << (b * 8)
    return result


async def _manual_write_burst(dut, base_addr, beats, burst=BURST_INCR, awid=0):
    """Manual burst write with independent per-beat WSTRB and optional WVALID
    idle gaps between beats. `beats` is a list of (data, strb) or (data,
    strb, gap_cycles) tuples -- `gap_cycles` idle (WVALID=0) cycles are
    driven immediately before that beat's data is presented. Returns
    (bresp, bid).

    WREADY is unconditional whenever wstate==W_DATA (never gated on this
    pipeline's own occupancy -- see sram_controller.sv's write-pipeline
    header comment), so there is never a "beat presented but not yet
    accepted" case to model here: once WVALID is asserted for a beat it is
    accepted on that same cycle, exactly like every other manual write
    helper in this file (_write_with_id, test_fixed_burst_write).
    """
    n = len(beats)
    dut.s_awid.value    = awid
    dut.s_awaddr.value  = base_addr
    dut.s_awlen.value   = n - 1
    dut.s_awsize.value  = SIZE_4B
    dut.s_awburst.value = burst
    dut.s_awvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_awready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_awvalid.value = 0

    for i, beat in enumerate(beats):
        data, strb = beat[0], beat[1]
        gap = beat[2] if len(beat) > 2 else 0
        for _ in range(gap):
            dut.s_wvalid.value = 0
            await RisingEdge(dut.clk)
        dut.s_wdata.value  = data
        dut.s_wstrb.value  = strb
        dut.s_wlast.value  = 1 if i == n - 1 else 0
        dut.s_wvalid.value = 1
        while True:
            await ReadOnly()
            if dut.s_wready.value:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
    dut.s_wvalid.value = 0
    dut.s_wlast.value  = 0

    dut.s_bready.value = 1
    while True:
        await ReadOnly()
        if dut.s_bvalid.value:
            break
        await RisingEdge(dut.clk)
    bresp = int(dut.s_bresp.value)
    bid   = int(dut.s_bid.value)
    await RisingEdge(dut.clk)
    dut.s_bready.value = 0
    return bresp, bid


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


# ── Test 2b: RLAST position conformance ──────────────────────────────────────
# The cache refill FSMs (rv32i_icache/rv32i_dcache) complete a refill on
# rvalid && rlast and trust the slave to deliver exactly ARLEN+1 beats: an
# early RLAST would silently validate a partially-filled line.  This test pins
# the slave side of that contract — RLAST exactly on the final beat, never
# earlier, for every burst length the SoC uses.

@cocotb.test()
async def test_rlast_position(dut):
    """RLAST asserts on beat ARLEN and only there, for ARLEN = 0..7.

    The BFM's read() collects beats until the first RLAST, so the returned
    list length pins RLAST's position exactly: shorter than arlen+1 means an
    early RLAST, a hang (caught by with_timeout) means a late/missing one.
    """
    m = await _setup(dut)
    base = SRAM_BASE + 0x400
    # Seed 8 words so every burst length reads known data.
    words = [0xA000_0000 + i for i in range(8)]
    bresp = await m.write(base, words)
    assert bresp == RESP_OKAY

    for arlen in range(8):
        data, rresp = await with_timeout(m.read(base, length=arlen + 1), 2, "us")
        assert rresp == RESP_OKAY, f"arlen={arlen}: rresp {rresp:#x}"
        assert len(data) == arlen + 1, (
            f"arlen={arlen}: RLAST after {len(data)} beats, expected {arlen + 1} "
            f"(early RLAST would silently truncate cache refills)"
        )
        assert data == words[: arlen + 1], (
            f"arlen={arlen}: data {[hex(d) for d in data]}"
        )
    dut._log.info("test_rlast_position PASS")


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


# ── Test 7: INCR burst that crosses SRAM_LIMIT returns SLVERR ────────────────

@cocotb.test()
async def test_burst_crosses_limit_slverr(dut):
    """4-beat INCR burst starting near SRAM_LIMIT whose last beat exceeds the
    window boundary must return SLVERR on both write and read.

    Start address: SRAM_LIMIT - 0xB, aligned down to 4 B = 0x0FFF_FFF4.
      Beat 0: 0x0FFF_FFF4  (inside  window)
      Beat 1: 0x0FFF_FFF8  (inside  window)
      Beat 2: 0x0FFF_FFFC  (inside  window)
      Beat 3: 0x1000_0000  (OUTSIDE window -> burst crosses limit)
    The RTL full-span check (last_addr = base + len*4) must catch this and
    assert w_err / r_err, producing SLVERR on the B and R channels.
    """
    m = await _setup(dut)

    # Word-aligned start address inside the SRAM window, close to the top.
    # last beat byte address = start + 3*4 = 0x0FFF_FFF4 + 0xC = 0x1000_0000
    # which exceeds SRAM_LIMIT (0x0FFF_FFFF).
    start = (SRAM_LIMIT - 0xB) & ~0x3   # 0x0FFF_FFF4

    dut._log.info(
        f"test_burst_crosses_limit_slverr: start=0x{start:08X} "
        f"last_beat=0x{start + 3*4:08X} SRAM_LIMIT=0x{SRAM_LIMIT:08X}"
    )

    # Write: 4-beat INCR burst crossing the window end -> expect SLVERR.
    bresp = await m.write(start, [0xDEAD_0001, 0xDEAD_0002, 0xDEAD_0003, 0xDEAD_0004])
    assert bresp == RESP_SLVERR, (
        f"crossing-burst write resp {bresp:#x} != SLVERR (0x{RESP_SLVERR:x}); "
        "RTL full-span range check may be missing"
    )

    # Read: same burst -> expect SLVERR.
    _, rresp = await m.read(start, length=4)
    assert rresp == RESP_SLVERR, (
        f"crossing-burst read resp {rresp:#x} != SLVERR (0x{RESP_SLVERR:x}); "
        "RTL full-span range check may be missing"
    )

    dut._log.info("test_burst_crosses_limit_slverr PASS")


# ── Test 8: R-channel backpressure — no dropped/duplicated/early beats ───────
# GH #104 Sky130 SoC Stage-2: added to close the one gap the existing suite
# left uncovered for the SRAM_SKY130 rework -- the AXI4Master BFM's read()
# only supports a single `ready_delay` *before* the burst starts, never
# toggles RREADY *within* a burst.  That leaves the read FSM's single-entry
# skid buffer (rd_dv_q / r_issue_now in the SRAM_SKY130 branch -- the pending
# beat must be held, and no new macro address issued, until the AXI master
# actually consumes it) completely unexercised.  This test manually drives an
# irregular RREADY pattern (including idle cycles immediately after the AR
# handshake, before any data could possibly be valid) and checks, cycle by
# cycle:
#   1. AXI4 VALID-stability rule: once RVALID=1 and RREADY=0 (beat pending,
#      not consumed), RVALID must stay 1 and RDATA must not change on the
#      next cycle -- no silent withdrawal.
#   2. Exactly ARLEN+1 beats are ever captured (valid&ready) -- no drops, no
#      duplicates.
#   3. RLAST asserts exactly on the last captured beat, never earlier.
# Runs unchanged under both the default flat-array model and SRAM_SKY130 (no
# latency assumption is hardcoded -- only the AXI4 protocol invariants are
# checked), so it doubles as a same-suite baseline/SKY130 comparison point.

@cocotb.test()
async def test_read_backpressure_no_drop_no_dup(dut):
    """Irregular RREADY under a burst read must not drop, duplicate, or
    early-terminate beats, and RVALID/RDATA must hold stable while pending."""
    m = await _setup(dut)
    base = SRAM_BASE + 0x600
    words = [0xC000_0000 + i for i in range(6)]
    bresp = await m.write(base, words)
    assert bresp == RESP_OKAY, f"seed write resp {bresp:#x}"

    # Manual AR (BFM has no per-beat RREADY control).
    dut.s_arid.value    = 0
    dut.s_araddr.value  = base
    dut.s_arlen.value   = len(words) - 1
    dut.s_arsize.value  = SIZE_4B
    dut.s_arburst.value = BURST_INCR
    dut.s_arvalid.value = 1
    await RisingEdge(dut.clk)
    while not dut.s_arready.value:
        await RisingEdge(dut.clk)
    dut.s_arvalid.value = 0

    # Irregular RREADY: 2 idle cycles right after AR-accept (stresses "no
    # macro address issued while nothing can be consumed yet"), then a mixed
    # on/off pattern across the burst, settling to always-ready to drain.
    ready_pattern = [0, 0, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1]

    got = []
    pending = False       # RVALID was 1 last cycle and NOT consumed (rready=0)
    pending_data = None
    cyc = 0
    timeout_cycles = 200
    while len(got) < len(words) and cyc < timeout_cycles:
        rr = ready_pattern[cyc] if cyc < len(ready_pattern) else 1
        dut.s_rready.value = rr
        await RisingEdge(dut.clk)
        # NOTE: no explicit ReadOnly() here -- unlike the single-shot
        # _read_with_id/BFM helpers, this loop must write s_rready again on
        # the very next iteration, and cocotb forbids scheduling a write
        # while parked in the ReadOnly phase. Verilator evaluates the whole
        # design to a fixed point before returning control from RisingEdge,
        # so the combinational R-channel outputs (rvalid/rdata/rlast/rresp)
        # are already settled here.
        rvalid = int(dut.s_rvalid.value)
        rdata  = int(dut.s_rdata.value)
        rlast  = int(dut.s_rlast.value)
        rresp  = int(dut.s_rresp.value)

        if pending:
            assert rvalid == 1, (
                f"cycle {cyc}: RVALID dropped a pending (unconsumed) beat "
                f"under backpressure -- violates AXI4 VALID-stability rule"
            )
            assert rdata == pending_data, (
                f"cycle {cyc}: RDATA changed ({rdata:#010x} != "
                f"{pending_data:#010x}) while a pending beat was held "
                f"under backpressure -- violates AXI4 stability rule"
            )

        transfer_now = bool(rvalid) and bool(rr)
        if transfer_now:
            assert rresp == RESP_OKAY, f"cycle {cyc}: rresp {rresp:#x}"
            got.append(rdata)
            if len(got) == len(words):
                assert rlast == 1, f"cycle {cyc}: RLAST missing on final beat"
            else:
                assert rlast == 0, (
                    f"cycle {cyc}: early RLAST at beat {len(got)}/{len(words)}"
                )

        pending = bool(rvalid) and not rr
        pending_data = rdata
        cyc += 1

    dut.s_rready.value = 0
    assert len(got) == len(words), (
        f"timeout after {cyc} cycles: only {len(got)}/{len(words)} beats "
        f"captured (dropped beats or stuck FSM)"
    )
    assert got == words, (
        f"backpressure readback mismatch (dropped/duplicated/reordered "
        f"beats):\n  got {[hex(d) for d in got]}\n  exp {[hex(w) for w in words]}"
    )
    dut._log.info("test_read_backpressure_no_drop_no_dup PASS")


# ── Test 9: read-after-write to the same address, back-to-back (no gap) ─────
# Highest-risk scenario for the SRAM_SKY130 rework per GH #104: a read issued
# immediately after the write that produced its data, with zero idle cycles
# in between, must observe the write.  This is where a stale-macro-latency
# assumption (e.g. treating the write as visible 0 cycles after WLAST instead
# of after the macro's negedge-launched commit) would most likely surface as
# a readback of old/garbage data.

@cocotb.test()
async def test_read_after_write_no_gap(dut):
    """Read issued the cycle immediately after a write's BVALID/BREADY
    handshake (no idle gap) must return the just-written data, repeated for
    several distinct addresses back-to-back."""
    m = await _setup(dut)
    base = SRAM_BASE + 0x700
    for i in range(4):
        addr = base + i * 4
        pattern = 0xD00D_0000 + i
        bresp = await m.write(addr, [pattern])
        assert bresp == RESP_OKAY, f"i={i}: write resp {bresp:#x}"
        # No extra idle RisingEdge inserted here -- m.read() drives ARVALID
        # on the very next edge after write() returns (which itself returns
        # the edge right after BVALID&BREADY).
        data, rresp = await m.read(addr, length=1)
        assert rresp == RESP_OKAY, f"i={i}: read resp {rresp:#x}"
        assert data[0] == pattern, (
            f"i={i}: read-after-write (no gap) got {data[0]:#010x}, "
            f"expected {pattern:#010x}"
        )
    dut._log.info("test_read_after_write_no_gap PASS")


# ── Test 11: burst-read throughput -- 1 beat/cycle once primed, no every-  ──
# ── other-cycle degradation from the SRAM_SKY130 skid-buffer pipeline    ──
# GH #104 fr_null_20260724_051800_00 fix review: the RTL fix adds pipeline
# depth (rd_pend_q stage + 2-entry output skid buffer) to correct the
# read-latency bug. The RTL orchestrator's claim is that steady-state
# continuous-RREADY throughput is UNCHANGED at 1 beat/cycle once the pipeline
# is primed (only burst *start* latency grows, from 1 cycle to 3). This test
# does not take that on faith -- it manually drives an 8-beat INCR burst with
# RREADY held high throughout and records the simulation time of every beat,
# then asserts every inter-beat gap AFTER the first beat is exactly one clock
# period (2 ns / 1 cycle). A degraded implementation (e.g. one that
# accidentally gates issuance on the full buffer being empty, rather than on
# just slot 1 having room) would show every-other-cycle (4 ns) gaps instead
# once the buffer's second slot is needed for the skid function.

@cocotb.test()
async def test_burst_read_throughput_1_beat_per_cycle(dut):
    """8-beat INCR burst, RREADY held high throughout: after the initial
    fill latency, every beat must land exactly 1 clock cycle after the
    previous one -- no every-other-cycle throughput degradation."""
    m = await _setup(dut)
    base = SRAM_BASE + 0x800
    length = 8
    words = [0xB0B0_0000 + i for i in range(length)]
    bresp = await m.write(base, words)
    assert bresp == RESP_OKAY, f"seed write resp {bresp:#x}"

    # Manual AR (need per-beat cocotb-time timestamps, which m.read() does
    # not expose).
    dut.s_arid.value    = 0
    dut.s_araddr.value  = base
    dut.s_arlen.value   = length - 1
    dut.s_arsize.value  = SIZE_4B
    dut.s_arburst.value = BURST_INCR
    dut.s_arvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_arready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_arvalid.value = 0

    dut.s_rready.value = 1
    beat_times_ns = []
    got = []
    cyc = 0
    timeout_cycles = 200
    # Check-before-advance (ReadOnly() first, THEN RisingEdge): this loop makes
    # no assumption about how many cycles elapse between the AR-accept edge
    # and the first RVALID -- burst-start latency is an implementation detail
    # of the read FSM, not a protocol guarantee (bead ydw, 2026-09-17:
    # registering the flat array's read mux raised the default build's
    # burst-start latency from 1 cycle to 2; SRAM_SKY130 pays 3 for its own,
    # unrelated, macro-latency reason -- see sram_controller.sv's read-FSM
    # header comment for both timing diagrams). Checking via ReadOnly()
    # *before* advancing to a new RisingEdge (rather than
    # RisingEdge-then-ReadOnly, as an earlier revision of this test did)
    # guarantees the very first cycle RVALID becomes true is sampled no
    # matter which cycle that turns out to be -- an off-by-one here would
    # silently drop whichever beat lands first.
    while len(got) < length and cyc < timeout_cycles:
        await ReadOnly()
        if dut.s_rvalid.value:
            beat_times_ns.append(float(get_sim_time(units="ns")))
            got.append(int(dut.s_rdata.value))
        await RisingEdge(dut.clk)
        cyc += 1
    dut.s_rready.value = 0

    assert len(got) == length, (
        f"timeout after {cyc} cycles: only {len(got)}/{length} beats captured"
    )
    assert got == words, (
        f"throughput-test readback mismatch:\n  got {[hex(d) for d in got]}\n"
        f"  exp {[hex(w) for w in words]}"
    )

    gaps = [beat_times_ns[i + 1] - beat_times_ns[i] for i in range(len(beat_times_ns) - 1)]
    dut._log.info(
        f"beat arrival times (ns): {beat_times_ns}; inter-beat gaps (ns): {gaps}"
    )
    bad_gaps = [(i, g) for i, g in enumerate(gaps) if g != CLK_PERIOD_NS]
    assert not bad_gaps, (
        f"throughput degraded: expected every inter-beat gap == "
        f"{CLK_PERIOD_NS} ns (1 beat/cycle) once primed, but got gaps "
        f"{gaps} (bad: {bad_gaps}) -- pipeline is stalling beyond the "
        f"documented 3-cycle fill latency"
    )
    dut._log.info(
        f"test_burst_read_throughput_1_beat_per_cycle PASS: {length} beats, "
        f"all inter-beat gaps == {CLK_PERIOD_NS} ns (1 beat/cycle)"
    )


# ── Test 12: FIXED burst read -- address never advances ─────────────────────
# bead ydw follow-up (verification-orchestrator targeted-coverage task): every
# prior burst test uses BURST_INCR only. AXI_BURST_FIXED (2'b00) is a
# supported burst type per both the write and read FSMs (`w_incr`/`r_incr`
# gate the index increment on `s_awburst`/`s_arburst == AXI_BURST_INCR`) and
# was never exercised. The BFM's write()/read() hardcode INCR, so this test
# drives AR manually.

@cocotb.test()
async def test_fixed_burst_read(dut):
    """FIXED burst re-reads the same address every beat -- AxADDR never
    advances, so every beat returns the one word stored there."""
    m = await _setup(dut)
    addr = SRAM_BASE + 0x900
    bresp = await m.write(addr, [0xF00D_CAFE])
    assert bresp == RESP_OKAY, f"seed write resp {bresp:#x}"

    length = 4
    dut.s_arid.value    = 0
    dut.s_araddr.value  = addr
    dut.s_arlen.value   = length - 1
    dut.s_arsize.value  = SIZE_4B
    dut.s_arburst.value = BURST_FIXED
    dut.s_arvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_arready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_arvalid.value = 0

    dut.s_rready.value = 1
    got = []
    cyc = 0
    timeout_cycles = 200
    while len(got) < length and cyc < timeout_cycles:
        await ReadOnly()
        if dut.s_rvalid.value:
            assert int(dut.s_rresp.value) == RESP_OKAY, (
                f"cyc={cyc}: rresp {int(dut.s_rresp.value):#x}"
            )
            got.append(int(dut.s_rdata.value))
            if len(got) == length:
                assert int(dut.s_rlast.value) == 1, "RLAST missing on final FIXED beat"
            else:
                assert int(dut.s_rlast.value) == 0, f"early RLAST at beat {len(got)}"
        await RisingEdge(dut.clk)
        cyc += 1
    dut.s_rready.value = 0

    assert len(got) == length, (
        f"timeout after {cyc} cycles: only {len(got)}/{length} FIXED beats captured"
    )
    assert got == [0xF00D_CAFE] * length, (
        f"FIXED burst must re-read the same address every beat: got "
        f"{[hex(d) for d in got]}, expected 4x 0xf00dcafe"
    )
    dut._log.info("test_fixed_burst_read PASS")


# ── Test 13: FIXED burst write -- only the last beat's data survives ────────

@cocotb.test()
async def test_fixed_burst_write(dut):
    """FIXED burst write re-targets the same address every beat -- each beat
    overwrites the previous one, so only the LAST beat's data survives."""
    m = await _setup(dut)
    addr = SRAM_BASE + 0xA00
    beats = [0x1111_1111, 0x2222_2222, 0x3333_3333, 0x4444_4444]

    dut.s_awid.value    = 0
    dut.s_awaddr.value  = addr
    dut.s_awlen.value   = len(beats) - 1
    dut.s_awsize.value  = SIZE_4B
    dut.s_awburst.value = BURST_FIXED
    dut.s_awvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_awready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_awvalid.value = 0

    for i, beat in enumerate(beats):
        dut.s_wdata.value  = beat
        dut.s_wstrb.value  = 0xF
        dut.s_wlast.value  = 1 if i == len(beats) - 1 else 0
        dut.s_wvalid.value = 1
        while True:
            await ReadOnly()
            if dut.s_wready.value:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
    dut.s_wvalid.value = 0
    dut.s_wlast.value  = 0

    dut.s_bready.value = 1
    while True:
        await ReadOnly()
        if dut.s_bvalid.value:
            break
        await RisingEdge(dut.clk)
    bresp = int(dut.s_bresp.value)
    await RisingEdge(dut.clk)
    dut.s_bready.value = 0
    assert bresp == RESP_OKAY, f"FIXED burst write resp {bresp:#x}"

    data, rresp = await m.read(addr, length=1)
    assert rresp == RESP_OKAY
    assert data[0] == beats[-1], (
        f"FIXED burst write must leave only the LAST beat's data at the "
        f"address: got {data[0]:#010x}, expected {beats[-1]:#010x}"
    )
    dut._log.info("test_fixed_burst_write PASS")


# ── Test 14: burst spanning the MEM_WORDS index wraparound ──────────────────
# word_index() masks the byte offset to IDX_W = $clog2(MEM_WORDS) bits, so the
# realised backing store aliases every 2**IDX_W words -- a burst whose index
# crosses that boundary must wrap cleanly (word MEM_WORDS-1 -> word 0), not
# corrupt or drop the wrapped beats. Uses a byte offset of -2 words (mod any
# power-of-two MEM_WORDS) so the SAME hardcoded address exercises the wrap
# identically for both the flat-array default build (MEM_WORDS=4096) and the
# SRAM_SKY130 build (MEM_WORDS=1024, via -GMEM_WORDS=1024) -- 1024 divides
# 4096, so offset -2 mod 4096 is also -2 mod 1024; no reflection on the
# DUT's MEM_WORDS parameter is needed.

@cocotb.test()
async def test_mem_words_wraparound_burst(dut):
    """A 4-beat INCR burst starting 2 words before the backing store's
    index wraparound must land its last 2 beats at word index 0/1, not
    corrupt/drop them and not alias onto the wrong words."""
    m = await _setup(dut)
    wrap_off_words = 4094  # == -2 mod 4096 == -2 mod 1024 == -2 mod 2**k for any k<=12
    base = SRAM_BASE + wrap_off_words * 4

    # Sentinel writes to the two low-index words BEFORE the wrapped burst --
    # if the wrap silently missed (dropped the beat instead of writing word
    # 0/1), the readback below would still see these sentinels, not garbage.
    sentinel = 0xBAD0_0000
    assert await m.write(SRAM_BASE + 0 * 4, [sentinel | 0]) == RESP_OKAY
    assert await m.write(SRAM_BASE + 1 * 4, [sentinel | 1]) == RESP_OKAY

    words = [0xFEED_0000 + i for i in range(4)]
    bresp = await m.write(base, words)
    assert bresp == RESP_OKAY, f"wraparound burst write resp {bresp:#x}"

    data, rresp = await m.read(base, length=4)
    assert rresp == RESP_OKAY, f"wraparound burst read resp {rresp:#x}"
    assert data == words, (
        f"wraparound burst readback mismatch:\n  got {[hex(d) for d in data]}\n"
        f"  exp {[hex(w) for w in words]}"
    )

    # Direct, non-wrapped single-beat reads of the two low-index words must
    # now show the wrapped burst's beats 2/3 -- confirms the wrapped write
    # really landed at word index 0/1 (not silently dropped or misaliased).
    d0, r0 = await m.read(SRAM_BASE + 0 * 4, length=1)
    d1, r1 = await m.read(SRAM_BASE + 1 * 4, length=1)
    assert r0 == RESP_OKAY and r1 == RESP_OKAY
    assert d0[0] == words[2], (
        f"wrapped word index 0: got {d0[0]:#010x}, expected {words[2]:#010x} "
        f"(seeing the sentinel {sentinel:#010x} would mean the wrap missed)"
    )
    assert d1[0] == words[3], (
        f"wrapped word index 1: got {d1[0]:#010x}, expected {words[3]:#010x}"
    )
    dut._log.info("test_mem_words_wraparound_burst PASS")


# ── Test 15: randomised R-channel backpressure, scoreboard-checked ──────────
# Generalises test_read_backpressure_no_drop_no_dup's single fixed RREADY
# pattern to genuinely randomised stimulus across multiple burst lengths and
# seeds, per the V-plan's constrained-random guidance (>= several distinct
# seeds before declaring a class covered). Same protocol invariants checked
# per cycle: VALID-stability while pending, no drop/dup, RLAST exactly on the
# final beat -- plus a full-burst scoreboard compare against the written data.

@cocotb.test()
async def test_read_backpressure_random(dut):
    """Randomised RREADY (8 seeds, burst lengths 2..8) must never drop,
    duplicate, or early-terminate a beat; RVALID/RDATA must hold stable
    while a beat is pending; final data must match a per-seed scoreboard."""
    m = await _setup(dut)
    base = SRAM_BASE + 0xC00

    for seed in range(8):
        length = 2 + (seed % 7)   # burst lengths 2..8
        addr = base + seed * 0x40
        words = [0xE000_0000 + (seed << 8) + i for i in range(length)]
        bresp = await m.write(addr, words)
        assert bresp == RESP_OKAY, f"seed={seed}: seed write resp {bresp:#x}"

        rng = random.Random(seed)

        dut.s_arid.value    = 0
        dut.s_araddr.value  = addr
        dut.s_arlen.value   = length - 1
        dut.s_arsize.value  = SIZE_4B
        dut.s_arburst.value = BURST_INCR
        dut.s_arvalid.value = 1
        while True:
            await ReadOnly()
            if dut.s_arready.value:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        dut.s_arvalid.value = 0

        got = []
        pending = False
        pending_data = None
        cyc = 0
        timeout_cycles = 300
        while len(got) < length and cyc < timeout_cycles:
            rr = rng.random() < 0.6
            dut.s_rready.value = int(rr)
            await RisingEdge(dut.clk)
            rvalid = int(dut.s_rvalid.value)
            rdata  = int(dut.s_rdata.value)
            rlast  = int(dut.s_rlast.value)
            rresp  = int(dut.s_rresp.value)

            if pending:
                assert rvalid == 1, (
                    f"seed={seed} cyc={cyc}: RVALID dropped a pending "
                    f"(unconsumed) beat under random backpressure"
                )
                assert rdata == pending_data, (
                    f"seed={seed} cyc={cyc}: RDATA changed ({rdata:#010x} != "
                    f"{pending_data:#010x}) while a pending beat was held"
                )

            transfer_now = bool(rvalid) and rr
            if transfer_now:
                assert rresp == RESP_OKAY, f"seed={seed} cyc={cyc}: rresp {rresp:#x}"
                got.append(rdata)
                if len(got) == length:
                    assert rlast == 1, (
                        f"seed={seed} cyc={cyc}: RLAST missing on final beat"
                    )
                else:
                    assert rlast == 0, (
                        f"seed={seed} cyc={cyc}: early RLAST at beat "
                        f"{len(got)}/{length}"
                    )

            pending = bool(rvalid) and not rr
            pending_data = rdata
            cyc += 1

        dut.s_rready.value = 0
        assert len(got) == length, (
            f"seed={seed}: timeout after {cyc} cycles, only {len(got)}/{length} "
            f"beats captured"
        )
        assert got == words, (
            f"seed={seed}: random-backpressure readback mismatch (dropped/"
            f"duplicated/reordered beats):\n  got {[hex(d) for d in got]}\n"
            f"  exp {[hex(w) for w in words]}"
        )
        await RisingEdge(dut.clk)   # let the FSM settle back to IDLE before the next seed

    dut._log.info("test_read_backpressure_random PASS (8 seeds, lengths 2..8)")


# ── Test 16: BVALID must never precede the write's actual landing in mem[] ──
# bead rvb targeted coverage (verification-orchestrator, full regression task):
# pins the write pipeline's central ordering guarantee as a regression, not
# just a design-review claim.
#
# Two checks, for two different reasons:
#
#  1. A WHITEBOX check (only meaningful on the flat-array build, guarded by
#     `hasattr(dut, "mem")`): the very cycle BVALID is first observed,
#     directly peek `dut.mem[]` at the burst's last-beat word and require it
#     already equals the NEW data. This is the check that is actually
#     DECISIVE for this specific DUT: a black-box AR-based check (below)
#     turns out to be structurally unable to distinguish correct W_DRAIN
#     timing from a "skip W_DRAIN, assert BVALID immediately" mutation for
#     this particular design, because of a coincidence of latencies --
#     worked out below -- so the whitebox check is what actually makes the
#     bead rvb mutation check ("mutate B to skip W_DRAIN... confirm test (a)
#     fails") meaningful. It is skipped (not failed) on the SRAM_SKY130
#     build, where `mem` does not exist as a flat array and where the
#     property does not apply in the same form (that FSM never enters
#     W_DRAIN at all -- see sram_controller.sv's write-FSM header comment).
#
#  2. A BLACK-BOX check via an actual AR/R transaction, issued at the
#     earliest opportunity a cocotb driver can react to observing BVALID
#     (one clock edge of reaction lag is unavoidable: a registered response
#     to a just-sampled registered signal always costs >=1 additional edge,
#     and this codebase's cocotb version forbids writing a signal while
#     parked in the ReadOnly() phase -- see test_read_backpressure_no_drop_
#     no_dup's header note). For THIS DUT specifically, the reactive lag
#     (1 cycle) plus the flat-array read FSM's own AR-accept-to-fetch
#     latency (2 cycles) sum to exactly the write pipeline's own
#     WLAST-accept-to-landing latency (3 cycles) -- so a read issued this
#     way can never observe the in-flight window regardless of whether
#     BVALID's timing is correct or mutated 2 cycles early; it fetches
#     mem[] on a LATER clock edge than either landing edge in both cases.
#     Confirmed empirically: this check alone still PASSED against the
#     "skip W_DRAIN" mutant. It is kept anyway -- as protocol-level
#     regression coverage for the general read-after-write path (it would
#     still catch e.g. a shortened read-FSM latency, or a write landing
#     later than documented) -- but check 1 above is what the mutation
#     check in this session's task actually depends on.

@cocotb.test()
async def test_bvalid_never_precedes_write_landing(dut):
    """Peek mem[] (flat-array build only) at the cycle BVALID is first
    observed -- must already hold the NEW data. Also issue AR to the
    burst's last-beat address at the earliest reactive opportunity after
    BVALID is first observed, as general read-after-write protocol
    coverage (see the module-level analysis above for why this second
    check is not, by itself, sufficient to catch a "BVALID too early"
    class of bug in this specific design)."""
    m = await _setup(dut)
    base = SRAM_BASE + 0xE00
    last_addr = base + 4
    last_word_idx = (last_addr - SRAM_BASE) // 4
    old_vals = [0xAAAA_AAAA, 0xBBBB_BBBB]
    new_vals = [0x1234_5678, 0xDEAD_BEEF]
    for i, v in enumerate(old_vals):
        assert await m.write(base + i * 4, [v]) == RESP_OKAY

    # Manual AW.
    dut.s_awid.value    = 0
    dut.s_awaddr.value  = base
    dut.s_awlen.value   = len(new_vals) - 1
    dut.s_awsize.value  = SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_awready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_awvalid.value = 0

    # Manual W beats.
    for i, v in enumerate(new_vals):
        dut.s_wdata.value  = v
        dut.s_wstrb.value  = 0xF
        dut.s_wlast.value  = 1 if i == len(new_vals) - 1 else 0
        dut.s_wvalid.value = 1
        while True:
            await ReadOnly()
            if dut.s_wready.value:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
    dut.s_wvalid.value = 0
    dut.s_wlast.value  = 0

    # BREADY deliberately held LOW: s_bvalid == (wstate == W_RESP) is
    # unconditional on bready (sram_controller.sv), so BVALID's assertion
    # timing is observed independent of our own response-channel handshake,
    # and it stays stably asserted (wstate cannot leave W_RESP) until we
    # choose to drain it below.
    dut.s_bready.value = 0

    dut.s_arid.value    = 0
    dut.s_araddr.value  = last_addr
    dut.s_arlen.value   = 0
    dut.s_arsize.value  = SIZE_4B
    dut.s_arburst.value = BURST_INCR

    # Poll for the FIRST cycle BVALID is observed. No explicit ReadOnly()
    # here (matching test_read_backpressure_no_drop_no_dup's convention) --
    # Verilator has already settled the combinational fixpoint by the time
    # RisingEdge returns control, and this loop must be able to write
    # s_arvalid on the very same iteration it detects s_bvalid, which cocotb
    # forbids while parked in ReadOnly. Arming ARVALID immediately after
    # detecting BVALID (rather than after crossing another edge) is the
    # earliest a cocotb driver can react -- functionally "the same cycle
    # BVALID is first seen" for the purposes of this ordering check.
    has_mem = hasattr(dut, "mem")
    bvalid_seen = False
    cyc = 0
    while not bvalid_seen and cyc < 200:
        await RisingEdge(dut.clk)
        cyc += 1
        if int(dut.s_bvalid.value) == 1:
            bvalid_seen = True
            # Decisive whitebox check (see the module-level note above):
            # right now, the cycle BVALID is first seen, mem[] at the
            # burst's last-beat word must already hold the NEW data.
            if has_mem:
                peeked = int(dut.mem[last_word_idx].value)
                assert peeked == new_vals[-1], (
                    f"mem[{last_word_idx}] read {peeked:#010x} at the exact "
                    f"cycle BVALID was first observed, expected the NEW "
                    f"value {new_vals[-1]:#010x} -- BVALID asserted before "
                    f"the write actually landed in mem[]"
                )
            dut.s_arvalid.value = 1
    assert bvalid_seen, "BVALID never asserted within 200 cycles"

    while True:
        await ReadOnly()
        if dut.s_arready.value:
            break
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.s_arvalid.value = 0

    # Drain B now -- harmless, BVALID has been held stably asserted since
    # the polling loop first observed it.
    dut.s_bready.value = 1

    dut.s_rready.value = 1
    got = None
    cyc = 0
    while got is None and cyc < 200:
        await ReadOnly()
        if dut.s_rvalid.value:
            got = int(dut.s_rdata.value)
            assert int(dut.s_rresp.value) == RESP_OKAY, (
                f"read resp {int(dut.s_rresp.value):#x}"
            )
            assert int(dut.s_rlast.value) == 1, "single-beat read must assert RLAST"
        await RisingEdge(dut.clk)
        cyc += 1
    dut.s_rready.value = 0
    dut.s_bready.value = 0
    assert got is not None, "read never completed within 200 cycles"
    assert got == new_vals[-1], (
        f"read issued at the earliest opportunity after BVALID was first "
        f"seen returned {got:#010x}, expected the NEW value "
        f"{new_vals[-1]:#010x} -- BVALID asserted before the write actually "
        f"landed in mem[]"
    )
    dut._log.info("test_bvalid_never_precedes_write_landing PASS")


# ── Test 17: write burst crossing the GROUP_WORDS boundary and the ──────────
# ── MEM_WORDS wraparound, both with per-beat partial WSTRB ──────────────────
# bead rvb targeted coverage: the stage-2 write pipeline splits MEM_WORDS
# into NGROUPS groups of GROUP_WORDS=32 words, each with its own
# grp_we_q/grp_wdata_q registers (sram_controller.sv). A burst whose beats
# land in two different groups is the one scenario that could expose a
# group-selection bug (e.g. an off-by-one in grp1_sel / local1_onehot)
# that a single-group burst could never surface. Combined with per-beat
# WSTRB (not previously exercised on any multi-group or wraparound burst),
# and combined again with the pre-existing MEM_WORDS index wraparound
# (test_mem_words_wraparound_burst, which never used partial WSTRB).

@cocotb.test()
async def test_write_burst_group_and_wrap_boundary_partial_strb(dut):
    """Group-boundary-crossing and MEM_WORDS-wraparound write bursts, both
    using distinct per-beat WSTRB, must land exactly the selected bytes at
    exactly the selected words and must not disturb neighbouring words."""
    m = await _setup(dut)
    sentinel = 0x5A5A_5A5A

    # ---- Part 1: group-boundary crossing burst (words 30..33) ----
    # GROUP_WORDS=32 -> group 0 is words 0..31, group 1 is words 32..63.
    # This burst's beats land at words 30,31 (group 0) then 32,33 (group 1).
    base_word = 30
    base_addr = SRAM_BASE + base_word * 4
    for w in range(base_word - 1, base_word + 6):
        assert await m.write(SRAM_BASE + w * 4, [sentinel]) == RESP_OKAY

    beats = [
        (0x1111_2222, 0b0011),
        (0x3333_4444, 0b1100),
        (0x0000_00AA, 0b0001),
        (0xFFFF_FFFF, 0b1111),
    ]
    bresp, _ = await _manual_write_burst(dut, base_addr, beats)
    assert bresp == RESP_OKAY, f"group-boundary burst write resp {bresp:#x}"

    for i, (data, strb) in enumerate(beats):
        exp = _apply_strb(sentinel, data, strb)
        got, rresp = await m.read(SRAM_BASE + (base_word + i) * 4, length=1)
        assert rresp == RESP_OKAY
        assert got[0] == exp, (
            f"word{base_word + i}: got {got[0]:#010x}, expected {exp:#010x}"
        )
    # Neighbours outside the burst must be untouched.
    d_lo, _ = await m.read(SRAM_BASE + (base_word - 1) * 4, length=1)
    d_hi, _ = await m.read(SRAM_BASE + (base_word + 5) * 4, length=1)
    assert d_lo[0] == sentinel and d_hi[0] == sentinel, (
        f"group-boundary burst disturbed a neighbouring word outside the "
        f"burst: below={d_lo[0]:#010x} above={d_hi[0]:#010x} (expected "
        f"sentinel {sentinel:#010x} for both)"
    )

    # ---- Part 2: MEM_WORDS wraparound burst, partial WSTRB ----
    # Same wrap offset as test_mem_words_wraparound_burst: -2 mod any
    # power-of-two MEM_WORDS >= 4 (valid for both the default flat-array
    # build, MEM_WORDS=4096, and the SRAM_SKY130 build, MEM_WORDS=1024).
    wrap_off_words = 4094
    wbase = SRAM_BASE + wrap_off_words * 4
    assert await m.write(SRAM_BASE + 0 * 4, [sentinel]) == RESP_OKAY
    assert await m.write(SRAM_BASE + 1 * 4, [sentinel]) == RESP_OKAY

    wbeats = [
        (0xCAFE_0000, 0b1111),
        (0xF000_000D, 0b0001),
        (0x0000_BEEF, 0b0011),  # lands at wrapped word index 0
        (0xABCD_1234, 0b1100),  # lands at wrapped word index 1
    ]
    bresp, _ = await _manual_write_burst(dut, wbase, wbeats)
    assert bresp == RESP_OKAY, f"wrap burst write resp {bresp:#x}"

    exp0 = _apply_strb(sentinel, wbeats[2][0], wbeats[2][1])
    exp1 = _apply_strb(sentinel, wbeats[3][0], wbeats[3][1])
    d0, r0 = await m.read(SRAM_BASE + 0 * 4, length=1)
    d1, r1 = await m.read(SRAM_BASE + 1 * 4, length=1)
    assert r0 == RESP_OKAY and r1 == RESP_OKAY
    assert d0[0] == exp0, f"wrapped word0: got {d0[0]:#010x}, expected {exp0:#010x}"
    assert d1[0] == exp1, f"wrapped word1: got {d1[0]:#010x}, expected {exp1:#010x}"
    dut._log.info("test_write_burst_group_and_wrap_boundary_partial_strb PASS")


# ── Test 18: back-to-back write bursts, no idle gap, interleaved with a ─────
# ── concurrent read on an unrelated address ──────────────────────────────────
# bead rvb targeted coverage: the write and read FSMs are fully independent
# (disjoint AW/W/B vs AR/R signal groups), and the write pipeline's own
# throughput is governed by the W_IDLE <- W_RESP <- W_DRAIN chain -- this
# test drives two write bursts back-to-back (zero added idle cycles, same
# convention as test_back_to_back_bursts) while a concurrent read of a
# THIRD, unrelated, pre-written address runs interleaved on the independent
# AR/R channel, to catch any accidental cross-FSM interference.

@cocotb.test()
async def test_back_to_back_write_bursts_with_interleaved_read(dut):
    """Two zero-gap back-to-back write bursts plus a concurrent read of an
    unrelated address must all complete correctly with no cross-FSM
    interference."""
    m = await _setup(dut)
    a0 = SRAM_BASE + 0x1000
    a1 = SRAM_BASE + 0x1100
    a2 = SRAM_BASE + 0x1200  # read target, primed beforehand
    w0 = [0xC0FF_EE00 + i for i in range(3)]
    w1 = [0xFACE_B000 + i for i in range(3)]
    r2_expected = [0x1CE0_FF00 + i for i in range(5)]

    assert await m.write(a2, r2_expected) == RESP_OKAY

    async def _writes():
        assert await m.write(a0, w0) == RESP_OKAY, "burst0 write SLVERR"
        assert await m.write(a1, w1) == RESP_OKAY, "burst1 write SLVERR"

    write_task = cocotb.start_soon(_writes())
    read_task = cocotb.start_soon(m.read(a2, length=len(r2_expected)))

    await write_task
    r2_data, r2_resp = await read_task
    assert r2_resp == RESP_OKAY, f"interleaved read resp {r2_resp:#x}"
    assert r2_data == r2_expected, (
        f"interleaved read mismatch:\n  got {[hex(d) for d in r2_data]}\n"
        f"  exp {[hex(w) for w in r2_expected]}"
    )

    d0, r0 = await m.read(a0, length=len(w0))
    d1, r1 = await m.read(a1, length=len(w1))
    assert r0 == RESP_OKAY and r1 == RESP_OKAY
    assert d0 == w0, f"burst0 mismatch {[hex(d) for d in d0]}"
    assert d1 == w1, f"burst1 mismatch {[hex(d) for d in d1]}"
    dut._log.info("test_back_to_back_write_bursts_with_interleaved_read PASS")


# ── Test 19: SLVERR write burst writes nothing, B arrives correctly ─────────
# bead rvb targeted coverage: BRESP-SLVERR is driven directly off w_err
# (combinational, unaffected by the write pipeline), but the stage-1 write
# pipeline is ALSO gated by `!w_err` (wr_valid1_q <= beat_accept && !w_err,
# sram_controller.sv) -- an independent gate that could regress separately
# from the response code. Uses a WRAP-type burst (rejected unconditionally,
# regardless of address -- see w_err's `s_awburst == AXI_BURST_WRAP` term)
# at an address well inside the SRAM window, so a bug that let the pipeline
# fire anyway would corrupt data a subsequent in-range read could actually
# observe (an out-of-range address would not give this test anything
# meaningful to read back).

@cocotb.test()
async def test_slverr_write_burst_writes_nothing(dut):
    """A WRAP-type burst must return SLVERR on B and must not modify memory
    at any of its beats' addresses."""
    m = await _setup(dut)
    base = SRAM_BASE + 0x1300
    sentinel = 0x5EED_0000
    words = [sentinel + i for i in range(4)]
    for i in range(4):
        assert await m.write(base + i * 4, [words[i]]) == RESP_OKAY

    new_vals = [0xBAD0_0000 + i for i in range(4)]
    bresp, _ = await _manual_write_burst(
        dut, base, [(v, 0xF) for v in new_vals], burst=BURST_WRAP
    )
    assert bresp == RESP_SLVERR, f"WRAP burst write resp {bresp:#x} != SLVERR"

    for i in range(4):
        data, rresp = await m.read(base + i * 4, length=1)
        assert rresp == RESP_OKAY
        assert data[0] == words[i], (
            f"word{i}: SLVERR burst must write nothing -- got {data[0]:#010x}, "
            f"expected untouched sentinel {words[i]:#010x}"
        )
    dut._log.info("test_slverr_write_burst_writes_nothing PASS")


# ── Test 20: WVALID gaps within a burst (non-contiguous beats) ──────────────
# bead rvb targeted coverage: every prior write-burst test drives WVALID
# contiguously across all beats. WREADY is unconditional in W_DATA (never
# gated on the write pipeline's own occupancy), so the FSM must simply wait
# for WVALID rather than assume back-to-back beats -- this was never
# exercised.

@cocotb.test()
async def test_write_burst_wvalid_gaps(dut):
    """WVALID idle gaps between beats must not corrupt, drop, or reorder
    beats."""
    m = await _setup(dut)
    base = SRAM_BASE + 0x1400
    words = [0x9009_0000 + i for i in range(5)]
    gaps = [0, 3, 0, 5, 1]  # idle WVALID=0 cycles immediately before each beat
    beats = [(w, 0xF, g) for w, g in zip(words, gaps)]

    bresp, _ = await _manual_write_burst(dut, base, beats)
    assert bresp == RESP_OKAY, f"gapped burst write resp {bresp:#x}"

    data, rresp = await m.read(base, length=len(words))
    assert rresp == RESP_OKAY
    assert data == words, (
        f"gapped-WVALID burst readback mismatch:\n  got {[hex(d) for d in data]}\n"
        f"  exp {[hex(w) for w in words]}"
    )
    dut._log.info("test_write_burst_wvalid_gaps PASS")
