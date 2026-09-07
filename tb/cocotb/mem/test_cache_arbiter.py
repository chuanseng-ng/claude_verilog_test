"""
rv32i_cache_arbiter unit tests — Phase 5 M2 AXI4 burst arbiter (GH #119 bead 2ft)
DUT: rv32i_cache_arbiter

This block had no standalone unit test before this suite -- `soc_all` only
exercised it indirectly through full-SoC traffic. There is no HLS arm here:
this is a plain standalone testbench for the hand-written RTL.

Contract under test (from the RTL header comment + `always_ff` grant FSM):
  - Priority: D$ write > D$ read > I$ read.
  - A grant is held for the whole burst. Read grants release on RLAST;
    write grants release on the B response (one B per burst) -- NOT on
    WLAST.
  - AR/AW are only forwarded to the memory-side AXI master the cycle AFTER
    the grant register captures the winner (never combinationally out of
    GRANT_NONE), because the read-data/response routing is gated on the
    registered grant.

Tests:
  - I$-only 4-beat read burst
  - D$-only 4-beat read burst (refill)
  - D$ writeback burst (AW + 4 W beats + B)
  - Priority: D$ write beats D$ read + I$ read simultaneously
  - Priority: D$ read beats I$ read (no write contending)
  - Grant hold: I$ mid-burst is not preempted by a D$ read request
  - Write grant releases only on the B response, not on WLAST
  - Read-data routing isolation, both directions (D$ holds / I$ holds)
  - Back-to-back grants: exact, minimal I$-release -> D$-grant latency
  - One-cycle registered-grant AR-forwarding delay out of GRANT_NONE
  - One-cycle registered-grant AW-forwarding delay out of GRANT_NONE
  - rresp/bresp passthrough (pure mux, no remapping)
  - Reset mid-burst clears the grant and the arbiter recovers cleanly
  - Idle bus: no spurious AXI activity with no requester valid

AXI slave modelled directly in Python (no rv32i_cpu_top).

NOTE on cocotbext-axi: the task briefing for this suite asked for
cocotbext-axi's AXI4 slave/RAM model on the memory side. That library's
`AxiRam`/`AxiBus` hard-require id-bearing channels (awid/arid/bid/rid --
see cocotbext/axi/axi_channels.py's `signals=[...]` lists, which are NOT
optional) and `len(bus.awid)` is read unconditionally in AxiSlaveWrite/
AxiSlaveRead. This arbiter's memory-side AXI4 master port has NO id field
by design -- axi_pkg.sv: "Existing Phase 1-4 blocks use flat per-channel
ports with NO id field and (today) single-beat transfers" -- and it IS
burst-capable (arlen/arsize/arburst), so it is neither AxiLite-shaped (no
burst fields) nor full AxiBus-shaped (needs id). cocotbext-axi cannot bind
to this port without an id-synthesizing wrapper. The two closest sibling
suites (test_icache.py, test_dcache.py) hit exactly this and both already
hand-roll their AXI slave in Python instead of using cocotbext-axi; this
suite follows that established, proven pattern (ArbiterAXIMem below is a
direct adaptation of test_dcache.py's SimpleDCacheAXIMem, whose signal
names match this DUT's axi_* port exactly).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

AXI_RESP_OK = 0b00
AXI_RESP_SLVERR = 0b10
AXI_BURST_INCR = 0b01
AXI_SIZE_4B = 0b010
LINE_WORDS = 4  # AXI_LEN_LINE = 3 -> 4 beats


# ---------------------------------------------------------------------------
# Memory-side AXI4 slave (read + write) -- adapted from
# tb/cocotb/mem/test_dcache.py's SimpleDCacheAXIMem. See module docstring for
# why cocotbext-axi cannot bind to this ID-less AXI4 port.
# ---------------------------------------------------------------------------


class ArbiterAXIMem:
    """
    Read/write AXI4 burst slave for the arbiter's single downstream memory
    port. Both cache-side requesters are muxed onto this one channel set by
    the DUT, so this handler never sees more than one in-flight AR/AW at a
    time -- it just services whatever the arbiter currently forwards.
    """

    def __init__(self, dut, rd_latency: int = 0, wr_latency: int = 0):
        self.dut = dut
        self.rd_latency = rd_latency
        self.wr_latency = wr_latency
        self.mem: dict[int, int] = {}  # word_addr -> 32-bit word
        self._rd_task = cocotb.start_soon(self._read_handler())
        self._wr_task = cocotb.start_soon(self._write_handler())

    def write_word(self, byte_addr: int, data: int):
        self.mem[byte_addr >> 2] = data & 0xFFFF_FFFF

    def read_word(self, byte_addr: int) -> int:
        return self.mem.get(byte_addr >> 2, 0)

    def stop(self):
        self._rd_task.cancel()
        self._wr_task.cancel()

    async def _read_handler(self):
        dut = self.dut
        while True:
            while not dut.axi_arvalid_o.value:
                await RisingEdge(dut.clk)

            if self.rd_latency:
                await ClockCycles(dut.clk, self.rd_latency)

            addr = int(dut.axi_araddr_o.value) & ~0x3
            arlen = int(dut.axi_arlen_o.value)
            nbeats = arlen + 1
            dut.axi_arready_i.value = 1
            await RisingEdge(dut.clk)
            dut.axi_arready_i.value = 0

            if self.rd_latency:
                await ClockCycles(dut.clk, self.rd_latency)

            for beat in range(nbeats):
                word_addr = (addr >> 2) + beat
                data = self.mem.get(word_addr, 0xDEAD_BEEF)
                is_last = beat == nbeats - 1

                dut.axi_rvalid_i.value = 1
                dut.axi_rdata_i.value = data
                dut.axi_rresp_i.value = AXI_RESP_OK
                dut.axi_rlast_i.value = 1 if is_last else 0

                await RisingEdge(dut.clk)
                while not dut.axi_rready_o.value:
                    await RisingEdge(dut.clk)

            dut.axi_rvalid_i.value = 0
            dut.axi_rdata_i.value = 0
            dut.axi_rlast_i.value = 0

    async def _write_handler(self):
        dut = self.dut
        while True:
            while not dut.axi_awvalid_o.value:
                await RisingEdge(dut.clk)

            if self.wr_latency:
                await ClockCycles(dut.clk, self.wr_latency)

            aw_addr = int(dut.axi_awaddr_o.value) & ~0x3
            awlen = int(dut.axi_awlen_o.value)
            nbeats = awlen + 1
            dut.axi_awready_i.value = 1
            await RisingEdge(dut.clk)
            dut.axi_awready_i.value = 0

            for beat in range(nbeats):
                while True:
                    await RisingEdge(dut.clk)
                    if dut.axi_wvalid_o.value:
                        break

                if self.wr_latency:
                    await ClockCycles(dut.clk, self.wr_latency)

                wdata = int(dut.axi_wdata_o.value)
                wstrb = int(dut.axi_wstrb_o.value)
                wlast = int(dut.axi_wlast_o.value)

                word_addr = (aw_addr >> 2) + beat
                old = self.mem.get(word_addr, 0)
                merged = 0
                for byte in range(4):
                    if wstrb & (1 << byte):
                        merged |= wdata & (0xFF << (byte * 8))
                    else:
                        merged |= old & (0xFF << (byte * 8))
                self.mem[word_addr] = merged

                dut.axi_wready_i.value = 1
                await RisingEdge(dut.clk)
                dut.axi_wready_i.value = 0

                if wlast:
                    break

            if self.wr_latency:
                await ClockCycles(dut.clk, self.wr_latency)

            dut.axi_bvalid_i.value = 1
            dut.axi_bresp_i.value = AXI_RESP_OK
            await RisingEdge(dut.clk)
            while not dut.axi_bready_o.value:
                await RisingEdge(dut.clk)
            dut.axi_bvalid_i.value = 0


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _reset(dut, cycles: int = 4):
    dut.rst_n.value = 0

    dut.ic_araddr_i.value = 0
    dut.ic_arlen_i.value = 0
    dut.ic_arsize_i.value = AXI_SIZE_4B
    dut.ic_arburst_i.value = AXI_BURST_INCR
    dut.ic_arvalid_i.value = 0
    dut.ic_rready_i.value = 1

    dut.dc_araddr_i.value = 0
    dut.dc_arlen_i.value = 0
    dut.dc_arsize_i.value = AXI_SIZE_4B
    dut.dc_arburst_i.value = AXI_BURST_INCR
    dut.dc_arvalid_i.value = 0
    dut.dc_rready_i.value = 1

    dut.dc_awaddr_i.value = 0
    dut.dc_awlen_i.value = 0
    dut.dc_awsize_i.value = AXI_SIZE_4B
    dut.dc_awburst_i.value = AXI_BURST_INCR
    dut.dc_awvalid_i.value = 0
    dut.dc_wdata_i.value = 0
    dut.dc_wstrb_i.value = 0
    dut.dc_wlast_i.value = 0
    dut.dc_wvalid_i.value = 0
    dut.dc_bready_i.value = 1

    dut.axi_arready_i.value = 0
    dut.axi_rvalid_i.value = 0
    dut.axi_rdata_i.value = 0
    dut.axi_rresp_i.value = 0
    dut.axi_rlast_i.value = 0
    dut.axi_awready_i.value = 0
    dut.axi_wready_i.value = 0
    dut.axi_bvalid_i.value = 0
    dut.axi_bresp_i.value = 0

    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _read_burst(
    dut, prefix, addr, nbeats=LINE_WORDS, timeout=200, order_log=None, order_name=None
):
    """Issue an AXI read burst on ic_* or dc_* and collect all beats."""
    araddr = getattr(dut, f"{prefix}_araddr_i")
    arlen = getattr(dut, f"{prefix}_arlen_i")
    arsize = getattr(dut, f"{prefix}_arsize_i")
    arburst = getattr(dut, f"{prefix}_arburst_i")
    arvalid = getattr(dut, f"{prefix}_arvalid_i")
    arready = getattr(dut, f"{prefix}_arready_o")
    rdata = getattr(dut, f"{prefix}_rdata_o")
    rvalid = getattr(dut, f"{prefix}_rvalid_o")
    rlast = getattr(dut, f"{prefix}_rlast_o")
    rready = getattr(dut, f"{prefix}_rready_i")

    araddr.value = addr
    arlen.value = nbeats - 1
    arsize.value = AXI_SIZE_4B
    arburst.value = AXI_BURST_INCR
    arvalid.value = 1
    rready.value = 1

    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if arvalid.value and arready.value:
            break
    else:
        raise TimeoutError(f"{prefix}: AR handshake never completed")
    arvalid.value = 0
    if order_log is not None:
        order_log.append(order_name or prefix)

    beats = []
    lasts = []
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if rvalid.value and rready.value:
            beats.append(int(rdata.value))
            lasts.append(bool(rlast.value))
            if rlast.value:
                break
    else:
        raise TimeoutError(f"{prefix}: read burst never completed")

    assert len(beats) == nbeats, f"{prefix}: expected {nbeats} beats, got {len(beats)}"
    assert lasts[-1], f"{prefix}: final beat did not assert rlast"
    assert not any(lasts[:-1]), f"{prefix}: rlast asserted before the final beat"
    return beats


async def _write_burst(
    dut, addr, data_words, wstrb=0xF, timeout=200, order_log=None, order_name=None
):
    """Issue a D$ writeback burst (AW + N W beats + B) and return bresp."""
    aw = dut.dc_awaddr_i
    awlen = dut.dc_awlen_i
    awsize = dut.dc_awsize_i
    awburst = dut.dc_awburst_i
    awvalid = dut.dc_awvalid_i
    awready = dut.dc_awready_o
    wdata = dut.dc_wdata_i
    wstrb_sig = dut.dc_wstrb_i
    wlast = dut.dc_wlast_i
    wvalid = dut.dc_wvalid_i
    wready = dut.dc_wready_o
    bvalid = dut.dc_bvalid_o
    bresp = dut.dc_bresp_o
    bready = dut.dc_bready_i

    nbeats = len(data_words)
    aw.value = addr
    awlen.value = nbeats - 1
    awsize.value = AXI_SIZE_4B
    awburst.value = AXI_BURST_INCR
    awvalid.value = 1
    bready.value = 1

    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if awvalid.value and awready.value:
            break
    else:
        raise TimeoutError("dc: AW handshake never completed")
    awvalid.value = 0
    if order_log is not None:
        order_log.append(order_name or "dc_wr")

    for i, data in enumerate(data_words):
        is_last = i == nbeats - 1
        wdata.value = data
        wstrb_sig.value = wstrb
        wlast.value = 1 if is_last else 0
        wvalid.value = 1
        for _ in range(timeout):
            await RisingEdge(dut.clk)
            if wvalid.value and wready.value:
                break
        else:
            raise TimeoutError(f"dc: W beat {i} never accepted")
    wvalid.value = 0
    wlast.value = 0

    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if bvalid.value:
            resp = int(bresp.value)
            break
    else:
        raise TimeoutError("dc: B response never arrived")
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_ic_only_read_burst(dut):
    """I$-only 4-beat read burst: all beats routed to I$, rlast on the last."""
    dut._log.info("=== test_ic_only_read_burst ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut)
    BASE = 0x0000_0000
    words = [0xAAAA_0000 + w for w in range(LINE_WORDS)]
    for w, val in enumerate(words):
        mem.write_word(BASE + w * 4, val)

    await _reset(dut)

    data = await _read_burst(dut, "ic", BASE)
    assert data == words, f"Got {[hex(v) for v in data]}"
    dut._log.info("I$-only burst: PASS")
    mem.stop()


@cocotb.test()
async def test_dc_only_read_burst(dut):
    """D$-only 4-beat read burst (refill)."""
    dut._log.info("=== test_dc_only_read_burst ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut)
    BASE = 0x0000_1000
    words = [0xBBBB_0000 + w for w in range(LINE_WORDS)]
    for w, val in enumerate(words):
        mem.write_word(BASE + w * 4, val)

    await _reset(dut)

    data = await _read_burst(dut, "dc", BASE)
    assert data == words, f"Got {[hex(v) for v in data]}"
    dut._log.info("D$-only burst: PASS")
    mem.stop()


@cocotb.test()
async def test_dc_writeback_burst(dut):
    """D$ writeback burst: AW, 4 W beats (wlast on the last), then B."""
    dut._log.info("=== test_dc_writeback_burst ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut)
    BASE = 0x0000_2000
    words = [0xCCCC_0000 + w for w in range(LINE_WORDS)]

    await _reset(dut)

    resp = await _write_burst(dut, BASE, words)
    assert resp == AXI_RESP_OK
    for w, expected in enumerate(words):
        got = mem.read_word(BASE + w * 4)
        assert got == expected, f"word[{w}]: got {got:#010x}, expected {expected:#010x}"
    dut._log.info("D$ writeback burst: PASS")
    mem.stop()


@cocotb.test()
async def test_priority_dc_write_wins_over_all(dut):
    """D$ write must win the grant when D$ write, D$ read and I$ read all
    assert simultaneously."""
    dut._log.info("=== test_priority_dc_write_wins_over_all ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut)
    WR_BASE, DC_RD_BASE, IC_RD_BASE = 0x0000_3000, 0x0000_4000, 0x0000_5000
    dc_words = [0xD000_0000 + w for w in range(LINE_WORDS)]
    ic_words = [0xE000_0000 + w for w in range(LINE_WORDS)]
    for w in range(LINE_WORDS):
        mem.write_word(DC_RD_BASE + w * 4, dc_words[w])
        mem.write_word(IC_RD_BASE + w * 4, ic_words[w])

    await _reset(dut)

    order = []
    write_data = [0xAAAA_1111 + w for w in range(LINE_WORDS)]

    # All three tasks assert their *valid on the same delta (start_soon runs
    # each coroutine immediately up to its first await), so this is a true
    # simultaneous-request scenario.
    t_wr = cocotb.start_soon(
        _write_burst(dut, WR_BASE, write_data, order_log=order, order_name="dc_wr")
    )
    t_dc = cocotb.start_soon(
        _read_burst(dut, "dc", DC_RD_BASE, order_log=order, order_name="dc_rd")
    )
    t_ic = cocotb.start_soon(
        _read_burst(dut, "ic", IC_RD_BASE, order_log=order, order_name="ic_rd")
    )

    wr_resp = await t_wr
    dc_data = await t_dc
    ic_data = await t_ic

    assert order == ["dc_wr", "dc_rd", "ic_rd"], f"Unexpected grant order: {order}"
    assert wr_resp == AXI_RESP_OK
    assert dc_data == dc_words
    assert ic_data == ic_words
    for w, expected in enumerate(write_data):
        assert mem.read_word(WR_BASE + w * 4) == expected
    dut._log.info(f"Priority order confirmed: {order}")
    mem.stop()


@cocotb.test()
async def test_priority_dc_read_wins_over_ic_read(dut):
    """D$ read must win over I$ read when both assert simultaneously and no
    write is contending."""
    dut._log.info("=== test_priority_dc_read_wins_over_ic_read ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut)
    DC_BASE, IC_BASE = 0x0000_6000, 0x0000_7000
    dc_words = [0xF000_0000 + w for w in range(LINE_WORDS)]
    ic_words = [0xF100_0000 + w for w in range(LINE_WORDS)]
    for w in range(LINE_WORDS):
        mem.write_word(DC_BASE + w * 4, dc_words[w])
        mem.write_word(IC_BASE + w * 4, ic_words[w])

    await _reset(dut)

    order = []
    t_dc = cocotb.start_soon(_read_burst(dut, "dc", DC_BASE, order_log=order, order_name="dc_rd"))
    t_ic = cocotb.start_soon(_read_burst(dut, "ic", IC_BASE, order_log=order, order_name="ic_rd"))

    dc_data = await t_dc
    ic_data = await t_ic

    assert order == ["dc_rd", "ic_rd"], f"Unexpected grant order: {order}"
    assert dc_data == dc_words
    assert ic_data == ic_words
    dut._log.info(f"Priority order confirmed: {order}")
    mem.stop()


@cocotb.test()
async def test_grant_hold_ic_then_dc_waits(dut):
    """A grant is held for the whole burst: once I$ owns the bus, a D$ read
    request must wait until I$'s RLAST before it is granted."""
    dut._log.info("=== test_grant_hold_ic_then_dc_waits ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut, rd_latency=1)
    IC_BASE, DC_BASE = 0x0000_8000, 0x0000_9000
    ic_words = [0x1000_0000 + w for w in range(LINE_WORDS)]
    dc_words = [0x2000_0000 + w for w in range(LINE_WORDS)]
    for w in range(LINE_WORDS):
        mem.write_word(IC_BASE + w * 4, ic_words[w])
        mem.write_word(DC_BASE + w * 4, dc_words[w])

    await _reset(dut)

    order = []
    t_ic = cocotb.start_soon(_read_burst(dut, "ic", IC_BASE, order_log=order, order_name="ic_rd"))

    # Wait until I$ actually owns the grant, then let one beat go by before
    # raising the competing D$ request mid-burst.
    while "ic_rd" not in order:
        await RisingEdge(dut.clk)
    await ClockCycles(dut.clk, 2)

    t_dc = cocotb.start_soon(_read_burst(dut, "dc", DC_BASE, order_log=order, order_name="dc_rd"))

    granted_dc_early = False
    ic_done_seen = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        if dut.ic_rvalid_o.value and dut.ic_rlast_o.value:
            ic_done_seen = True
        if not ic_done_seen and dut.dc_arvalid_i.value and dut.dc_arready_o.value:
            granted_dc_early = True
        if ic_done_seen and "dc_rd" in order:
            break

    assert not granted_dc_early, "D$ AR was accepted before I$'s burst completed -- grant not held"
    assert ic_done_seen, "I$ rlast never observed"
    assert "dc_rd" in order, "D$ was never granted after I$ released the bus"

    ic_data = await t_ic
    dc_data = await t_dc
    assert ic_data == ic_words
    assert dc_data == dc_words
    dut._log.info("Grant hold (I$ then D$): PASS")
    mem.stop()


@cocotb.test()
async def test_write_grant_releases_only_on_bresp(dut):
    """A write grant must not release on WLAST -- only on the B handshake."""
    dut._log.info("=== test_write_grant_releases_only_on_bresp ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut, wr_latency=3)
    WR_BASE, IC_BASE = 0x0000_A000, 0x0000_B000
    mem.write_word(IC_BASE, 0x9999_0000)
    for w in range(1, LINE_WORDS):
        mem.write_word(IC_BASE + w * 4, 0)

    await _reset(dut)

    order = []
    write_data = [0x1111_0000 + w for w in range(LINE_WORDS)]
    t_wr = cocotb.start_soon(
        _write_burst(dut, WR_BASE, write_data, order_log=order, order_name="dc_wr")
    )

    while "dc_wr" not in order:
        await RisingEdge(dut.clk)

    # Wait for the final W beat to reach the memory side (WLAST accepted).
    for _ in range(50):
        await RisingEdge(dut.clk)
        if dut.axi_wvalid_o.value and dut.axi_wready_i.value and dut.axi_wlast_o.value:
            break
    else:
        raise TimeoutError("write burst never reached its last W beat")

    # Raise a pending I$ read right as WLAST completes -- it must NOT be
    # granted until the B response (not WLAST) closes out the write grant.
    t_ic = cocotb.start_soon(_read_burst(dut, "ic", IC_BASE, order_log=order, order_name="ic_rd"))

    granted_before_bresp = False
    bresp_seen = False
    for _ in range(50):
        await RisingEdge(dut.clk)
        if dut.dc_bvalid_o.value and dut.dc_bready_i.value:
            bresp_seen = True
        if not bresp_seen and dut.ic_arvalid_i.value and dut.ic_arready_o.value:
            granted_before_bresp = True
        if bresp_seen and "ic_rd" in order:
            break

    assert bresp_seen, "B response never observed"
    assert not granted_before_bresp, (
        "I$ was granted before the write's B response (released early on WLAST)"
    )

    wr_resp = await t_wr
    ic_data = await t_ic
    assert wr_resp == AXI_RESP_OK
    assert ic_data == [0x9999_0000, 0, 0, 0]
    dut._log.info("Write grant release gated on B, not WLAST: PASS")
    mem.stop()


@cocotb.test()
async def test_read_data_routing_isolation(dut):
    """A response must never be delivered to the wrong requester, in either
    direction: the non-granted read requester must see rvalid stay low for
    the whole time the other one holds the grant."""
    dut._log.info("=== test_read_data_routing_isolation ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut, rd_latency=1)
    DC1, IC1, IC2, DC2 = 0x0000_C000, 0x0000_D000, 0x0000_E000, 0x0000_F000
    dc1_words = [0x3000_0000 + w for w in range(LINE_WORDS)]
    ic1_words = [0x4000_0000 + w for w in range(LINE_WORDS)]
    ic2_words = [0x5000_0000 + w for w in range(LINE_WORDS)]
    dc2_words = [0x6000_0000 + w for w in range(LINE_WORDS)]
    for w in range(LINE_WORDS):
        mem.write_word(DC1 + w * 4, dc1_words[w])
        mem.write_word(IC1 + w * 4, ic1_words[w])
        mem.write_word(IC2 + w * 4, ic2_words[w])
        mem.write_word(DC2 + w * 4, dc2_words[w])

    await _reset(dut)

    order = []

    # Phase A: D$ wins (priority), I$ is pending concurrently -- I$ must
    # never see rvalid while D$ holds the grant.
    t_dc1 = cocotb.start_soon(_read_burst(dut, "dc", DC1, order_log=order, order_name="dc_rd1"))
    t_ic1 = cocotb.start_soon(_read_burst(dut, "ic", IC1, order_log=order, order_name="ic_rd1"))

    ic_leaked = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        if dut.ic_rvalid_o.value:
            ic_leaked = True
        if "ic_rd1" in order:
            break
    assert not ic_leaked, "ic_rvalid_o asserted while D$ held the grant"

    dc1_data = await t_dc1
    ic1_data = await t_ic1
    assert dc1_data == dc1_words
    assert ic1_data == ic1_words

    # Phase B: reverse the roles. I$ requests first (wins, since D$ is
    # idle), then D$ requests mid-burst -- D$ must never see rvalid while
    # I$ holds the grant.
    t_ic2 = cocotb.start_soon(_read_burst(dut, "ic", IC2, order_log=order, order_name="ic_rd2"))
    while "ic_rd2" not in order:
        await RisingEdge(dut.clk)
    await ClockCycles(dut.clk, 1)
    t_dc2 = cocotb.start_soon(_read_burst(dut, "dc", DC2, order_log=order, order_name="dc_rd2"))

    dc_leaked = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        if dut.dc_rvalid_o.value:
            dc_leaked = True
        if "dc_rd2" in order:
            break
    assert not dc_leaked, "dc_rvalid_o asserted while I$ held the grant"

    ic2_data = await t_ic2
    dc2_data = await t_dc2
    assert ic2_data == ic2_words
    assert dc2_data == dc2_words

    dut._log.info("Read-data routing isolation (both directions): PASS")
    mem.stop()


@cocotb.test()
async def test_back_to_back_grants_no_lost_cycles(dut):
    """Pre-arming D$ before I$ releases the bus must yield the arbiter's
    minimum, deterministic hand-off latency -- no extra idle cycles beyond
    the documented registered-grant decode."""
    dut._log.info("=== test_back_to_back_grants_no_lost_cycles ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut)
    IC_BASE, DC_BASE = 0x0001_0000, 0x0001_1000
    ic_words = [0x5000_0000 + w for w in range(LINE_WORDS)]
    dc_words = [0x6000_0000 + w for w in range(LINE_WORDS)]
    for w in range(LINE_WORDS):
        mem.write_word(IC_BASE + w * 4, ic_words[w])
        mem.write_word(DC_BASE + w * 4, dc_words[w])

    await _reset(dut)

    order = []
    t_ic = cocotb.start_soon(_read_burst(dut, "ic", IC_BASE, order_log=order, order_name="ic_rd"))
    while "ic_rd" not in order:
        await RisingEdge(dut.clk)

    # Pre-arm D$ so it is already waiting the instant I$ releases the grant.
    t_dc = cocotb.start_soon(_read_burst(dut, "dc", DC_BASE, order_log=order, order_name="dc_rd"))

    ic_rlast_cycle = None
    dc_grant_cycle = None
    cycle = 0
    for _ in range(200):
        await RisingEdge(dut.clk)
        cycle += 1
        if ic_rlast_cycle is None and dut.ic_rvalid_o.value and dut.ic_rlast_o.value:
            ic_rlast_cycle = cycle
        if dc_grant_cycle is None and dut.dc_arvalid_i.value and dut.dc_arready_o.value:
            dc_grant_cycle = cycle
        if ic_rlast_cycle is not None and dc_grant_cycle is not None:
            break

    assert ic_rlast_cycle is not None, "I$ rlast never observed"
    assert dc_grant_cycle is not None, "D$ was never granted after I$ released the bus"
    gap = dc_grant_cycle - ic_rlast_cycle
    dut._log.info(f"I$-release -> D$-grant gap: {gap} cycle(s)")
    # Deterministic: 2 cycles for the arbiter's registered-grant decode
    # (GRANT_IC_RD -> GRANT_NONE -> GRANT_DC_RD) plus 1 cycle for the memory
    # BFM's own zero-latency AR-accept reaction -- the same constant every
    # fresh, uncontested request pays. Anything more would mean the
    # arbitration itself is burning extra idle bus cycles on the hand-off.
    assert gap == 3, (
        f"D$ took {gap} cycles to be granted after I$'s RLAST -- expected exactly 3 "
        f"(the arbiter's minimum registered-grant hand-off), not extra idle bus cycles"
    )

    ic_data = await t_ic
    dc_data = await t_dc
    assert ic_data == ic_words, "I$ burst dropped or corrupted a beat"
    assert dc_data == dc_words, "D$ burst dropped or corrupted a beat"
    dut._log.info("Back-to-back grants, no lost/dropped beats: PASS")
    mem.stop()


@cocotb.test()
async def test_ar_forward_one_cycle_delay_from_idle(dut):
    """The registered grant means an AR request seen while grant_q==NONE is
    forwarded to the memory side the cycle AFTER it is seen -- never
    combinationally in the same cycle. Assert this explicitly."""
    dut._log.info("=== test_ar_forward_one_cycle_delay_from_idle ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    await _reset(dut)

    await RisingEdge(dut.clk)
    assert not dut.axi_arvalid_o.value, "bus should be idle before the request"

    dut.ic_araddr_i.value = 0x100
    dut.ic_arlen_i.value = LINE_WORDS - 1
    dut.ic_arvalid_i.value = 1

    # Same cycle the request first appears: grant_q is still GRANT_NONE, so
    # the AR mux must NOT forward it yet (RTL: "GRANT_NONE: ;" -- no
    # forwarding out of idle).
    await ReadOnly()
    assert not dut.axi_arvalid_o.value, "AR must not forward combinationally out of GRANT_NONE"
    assert not dut.ic_arready_o.value, "ic_arready_o must not assert until the grant registers"

    # One clock later, the FSM has registered GRANT_IC_RD; AR must now
    # forward with the correct address.
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.axi_arvalid_o.value, "AR should forward the cycle after the grant registers"
    assert int(dut.axi_araddr_o.value) == 0x100

    # Step past the read-only sync phase before driving any more signals.
    await RisingEdge(dut.clk)
    dut.ic_arvalid_i.value = 0
    dut._log.info("One-cycle AR-forwarding delay confirmed")


@cocotb.test()
async def test_aw_forward_one_cycle_delay_from_idle(dut):
    """Same registered-grant delay applies to AW forwarding (RTL comment:
    "GRANT_NONE -> GRANT_DC_WR same cycle... next cycle grant_q=GRANT_DC_WR
    and AW can proceed")."""
    dut._log.info("=== test_aw_forward_one_cycle_delay_from_idle ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    await _reset(dut)

    await RisingEdge(dut.clk)
    assert not dut.axi_awvalid_o.value, "bus should be idle before the request"

    dut.dc_awaddr_i.value = 0x1234
    dut.dc_awlen_i.value = LINE_WORDS - 1
    dut.dc_awvalid_i.value = 1

    await ReadOnly()
    assert not dut.axi_awvalid_o.value, "AW must not forward combinationally out of GRANT_NONE"
    assert not dut.dc_awready_o.value, "dc_awready_o must not assert until the grant registers"

    await RisingEdge(dut.clk)
    await ReadOnly()
    assert dut.axi_awvalid_o.value, "AW should forward the cycle after the grant registers"
    assert int(dut.axi_awaddr_o.value) == 0x1234

    # Step past the read-only sync phase before driving any more signals.
    await RisingEdge(dut.clk)
    dut.dc_awvalid_i.value = 0
    dut._log.info("One-cycle AW-forwarding delay confirmed")


@cocotb.test()
async def test_response_code_passthrough(dut):
    """rresp/bresp are forwarded from the memory unmodified -- the arbiter's
    read-data and write-response assigns are a pure passthrough mux with no
    error remapping."""
    dut._log.info("=== test_response_code_passthrough ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    await _reset(dut)

    # --- Read side: inject SLVERR on the R channel ---
    dut.ic_araddr_i.value = 0x100
    dut.ic_arlen_i.value = 0
    dut.ic_arvalid_i.value = 1
    dut.ic_rready_i.value = 1

    for _ in range(20):
        await RisingEdge(dut.clk)
        if dut.axi_arvalid_o.value:
            break
    else:
        raise TimeoutError("AR never forwarded")
    dut.axi_arready_i.value = 1
    await RisingEdge(dut.clk)
    dut.axi_arready_i.value = 0
    dut.ic_arvalid_i.value = 0

    dut.axi_rvalid_i.value = 1
    dut.axi_rdata_i.value = 0xBAD0_0000
    dut.axi_rresp_i.value = AXI_RESP_SLVERR
    dut.axi_rlast_i.value = 1
    await RisingEdge(dut.clk)
    assert dut.ic_rvalid_o.value, "expected ic_rvalid_o this cycle"
    assert int(dut.ic_rresp_o.value) == AXI_RESP_SLVERR, "rresp not passed through unmodified"
    dut.axi_rvalid_i.value = 0
    dut.axi_rlast_i.value = 0

    await ClockCycles(dut.clk, 3)  # let the read grant fully release

    # --- Write side: inject SLVERR on the B channel ---
    dut.dc_awaddr_i.value = 0x200
    dut.dc_awlen_i.value = 0
    dut.dc_awvalid_i.value = 1
    dut.dc_wdata_i.value = 0xDEAD_0000
    dut.dc_wstrb_i.value = 0xF
    dut.dc_wlast_i.value = 1
    dut.dc_wvalid_i.value = 1
    dut.dc_bready_i.value = 1

    for _ in range(20):
        await RisingEdge(dut.clk)
        if dut.axi_awvalid_o.value:
            break
    else:
        raise TimeoutError("AW never forwarded")
    dut.axi_awready_i.value = 1
    await RisingEdge(dut.clk)
    dut.axi_awready_i.value = 0
    dut.dc_awvalid_i.value = 0

    for _ in range(20):
        await RisingEdge(dut.clk)
        if dut.axi_wvalid_o.value:
            break
    else:
        raise TimeoutError("W never forwarded")
    dut.axi_wready_i.value = 1
    await RisingEdge(dut.clk)
    dut.axi_wready_i.value = 0
    dut.dc_wvalid_i.value = 0

    dut.axi_bvalid_i.value = 1
    dut.axi_bresp_i.value = AXI_RESP_SLVERR
    await RisingEdge(dut.clk)
    assert dut.dc_bvalid_o.value, "expected dc_bvalid_o this cycle"
    assert int(dut.dc_bresp_o.value) == AXI_RESP_SLVERR, "bresp not passed through unmodified"
    dut.axi_bvalid_i.value = 0

    dut._log.info("rresp/bresp passthrough confirmed")


@cocotb.test()
async def test_reset_mid_transaction_clears_grant(dut):
    """Reset applied mid-burst returns the arbiter to GRANT_NONE (the grant
    FSM's reset is checked synchronously in its always_ff), and the arbiter
    must recover cleanly afterward."""
    dut._log.info("=== test_reset_mid_transaction_clears_grant ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = ArbiterAXIMem(dut, rd_latency=1)
    BASE = 0x0001_2000
    for w in range(LINE_WORDS):
        mem.write_word(BASE + w * 4, 0x7000_0000 + w)

    await _reset(dut)

    dut.ic_araddr_i.value = BASE
    dut.ic_arlen_i.value = LINE_WORDS - 1
    dut.ic_arvalid_i.value = 1
    dut.ic_rready_i.value = 1

    beats_before_reset = 0
    for _ in range(50):
        await RisingEdge(dut.clk)
        if dut.ic_rvalid_o.value and dut.ic_rready_i.value:
            beats_before_reset += 1
            if beats_before_reset >= 1:
                break
    assert beats_before_reset >= 1, "burst never started before the reset injection"

    dut.rst_n.value = 0
    dut.ic_arvalid_i.value = 0
    await ClockCycles(dut.clk, 3)
    assert not dut.axi_arvalid_o.value, "AXI AR still active during reset"
    assert not dut.ic_rvalid_o.value, "ic_rvalid_o still active during reset"
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    mem.stop()

    # A fresh, unrelated transaction must acquire the bus cleanly after reset.
    mem2 = ArbiterAXIMem(dut)
    RECOVER_BASE = 0x0001_3000
    mem2.write_word(RECOVER_BASE, 0xABCD_0000)
    for w in range(1, LINE_WORDS):
        mem2.write_word(RECOVER_BASE + w * 4, 0)

    data = await _read_burst(dut, "dc", RECOVER_BASE)
    assert data[0] == 0xABCD_0000
    dut._log.info("Reset mid-transaction recovery: PASS")
    mem2.stop()


@cocotb.test()
async def test_idle_bus_no_spurious_activity(dut):
    """With no requester valid, the arbiter must present no AXI activity at
    all on the memory-side port or either read-return path."""
    dut._log.info("=== test_idle_bus_no_spurious_activity ===")
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    await _reset(dut)

    for _ in range(20):
        await RisingEdge(dut.clk)
        assert not dut.axi_arvalid_o.value
        assert not dut.axi_awvalid_o.value
        assert not dut.axi_wvalid_o.value
        assert not dut.ic_rvalid_o.value
        assert not dut.dc_rvalid_o.value
        assert not dut.dc_bvalid_o.value

    dut._log.info("Idle bus: no spurious activity: PASS")
