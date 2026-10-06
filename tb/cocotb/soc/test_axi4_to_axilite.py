"""Bead ej6j -- directed tests for rtl/soc/axi4_to_axilite.sv (AXI4 burst -> AXI4-Lite bridge).

The bridge serialises an AXI4 burst into N single-beat AXI4-Lite transactions on the peripheral ring.
Until now only single-beat OKAY traffic reached it (through the SoC suites), so multi-beat bursts, the
worse_resp() accumulator, every error response and every handshake-stall arm were uncovered.

Intent checked (AXI4 / the module header), not just line toggling:
  * a burst of N beats produces exactly N AXI-Lite writes/reads at base, base+4, ... (INCR)
  * W beats are accepted one at a time and only AFTER the AW; the single B is returned after the LAST
    AXI-Lite B, never earlier, and carries the awid
  * B accumulates the worst response over the burst (DECERR > SLVERR > OKAY) and a later OKAY or a
    new burst never clears or inherits it incorrectly
  * R beats are forwarded one per AXI-Lite read with the PER-BEAT response (not sticky), rid = arid
    and rlast on the final beat only, even when the final beat is an error
  * every stall (AW/W/B/AR/R valid or ready held off) preserves data, order and payload stability
  * the AXI-Lite master never changes a held payload and never has two writes/reads in flight
"""

import cocotb
from axi4_fabric_bfm import (DECERR, OKAY, SLVERR, AxiLiteSlave, AxiMaster)
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

BASE = 0x2000_4000


async def _setup(dut, clock=True, **slave_kw):
    if clock:
        cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    master = AxiMaster(dut, "s_", dut.clk)
    dut.m_axil_awready.value = 0
    dut.m_axil_wready.value = 0
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    slave = AxiLiteSlave(dut, "m_axil_", dut.clk, **slave_kw)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    slave.start()
    return master, slave


async def _quiet(dut, cycles=6):
    """Assert the AXI4 side offers no stray B / R after a transaction."""
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        assert not int(dut.s_bvalid.value), "stray B beat after the burst completed"
        assert not int(dut.s_rvalid.value), "stray R beat after the burst completed"


@cocotb.test()
async def test_write_burst_okay(dut):
    master, slave = await _setup(dut)
    data = [0x1111_0001, 0x2222_0002, 0x3333_0003, 0x4444_0004]
    t = await master.write(BASE, data, wid=5)

    assert t.bresp == OKAY and t.bid == 5, f"B resp={t.bresp} bid={t.bid}"
    assert [w["addr"] for w in slave.aw_log] == [BASE + 4 * i for i in range(4)], slave.aw_log
    assert [w["data"] for w in slave.w_log] == data
    assert all(w["strb"] == 0xF for w in slave.w_log)
    assert len(t.w_cycles) == 4
    assert t.first_bvalid > t.w_cycles[-1], "B must follow the last W beat"
    # The single B reply may only appear once the LAST AXI-Lite write has completed.
    assert t.first_bvalid > slave.w_log[-1]["cycle"], "B returned before the last AXI-Lite W"
    for i, a in enumerate(range(4)):
        assert slave.mem[BASE + 4 * a] == data[i]
    assert not slave.viol and not t.viol, (slave.viol, t.viol)
    await _quiet(dut)


@cocotb.test()
async def test_write_strobes_and_single_beat(dut):
    master, slave = await _setup(dut)
    slave.mem[BASE] = 0xAABBCCDD
    t = await master.write(BASE, [0x11223344], strb=0b0101, wid=2)
    assert t.bresp == OKAY and t.bid == 2
    assert slave.w_log[0]["strb"] == 0b0101
    assert slave.mem[BASE] == 0xAA22CC44, f"{slave.mem[BASE]:#x}"
    assert len(slave.aw_log) == 1 and not slave.viol


@cocotb.test()
async def test_write_response_accumulation(dut):
    """worse_resp(): DECERR beats SLVERR beats OKAY; position of the error in the burst is irrelevant."""
    cases = [
        ([OKAY, OKAY, OKAY, OKAY], OKAY),
        ([SLVERR, OKAY, OKAY, OKAY], SLVERR),
        ([OKAY, SLVERR, OKAY, OKAY], SLVERR),
        ([OKAY, OKAY, OKAY, SLVERR], SLVERR),
        ([DECERR, OKAY, OKAY, OKAY], DECERR),
        ([OKAY, OKAY, OKAY, DECERR], DECERR),
        ([SLVERR, DECERR, OKAY, OKAY], DECERR),   # DECERR arrives after SLVERR
        ([DECERR, SLVERR, OKAY, OKAY], DECERR),   # SLVERR arrives after DECERR: must stay DECERR
        ([DECERR, SLVERR, OKAY, DECERR], DECERR),
        ([SLVERR, SLVERR, OKAY, OKAY], SLVERR),
    ]
    master, slave = await _setup(dut)
    for n, (resps, exp) in enumerate(cases):
        slave.bresps = list(resps)
        slave.aw_log.clear()
        slave.w_log.clear()
        t = await master.write(BASE + 0x100 * n, [0xA0 + n, 0xB0 + n, 0xC0 + n, 0xD0 + n], wid=n & 0xF)
        assert t.bresp == exp, f"case {n} {resps}: bresp {t.bresp} expected {exp}"
        assert len(slave.aw_log) == 4 and len(slave.w_log) == 4, (
            f"case {n}: an error beat must not abort the burst (aw={len(slave.aw_log)})")
        assert t.bid == (n & 0xF)
        # the accumulator must not leak into the next burst
        t2 = await master.write(BASE + 0x1000, [0x55], wid=1)
        assert t2.bresp == OKAY, f"case {n}: clean burst after error returned {t2.bresp}"
    assert not slave.viol


@cocotb.test()
async def test_write_stalls(dut):
    """Every write-side handshake stalled: AW/W accepted at different times, B delayed, bready held."""
    first = True
    for kw, mkw in (
        (dict(aw_delay=3, w_delay=6, b_delay=4), dict(aw_delay=2, w_gaps=[3, 0, 4, 1], b_stall=5)),
        (dict(aw_delay=7, w_delay=1, b_delay=2), dict(aw_delay=0, w_gaps=[0, 2, 0, 5], b_stall=3)),
        (dict(aw_delay=0, w_delay=0, b_delay=0), dict(aw_delay=1, w_gaps=[1, 1, 1, 1], b_stall=9)),
    ):
        master, slave = await _setup(dut, clock=first, **kw)
        first = False
        data = [0xDEAD0001, 0xDEAD0002, 0xDEAD0003, 0xDEAD0004]
        slave.bresps = [OKAY, SLVERR, OKAY, OKAY]
        t = await master.write(BASE, data, wid=9, **mkw)
        assert t.bresp == SLVERR and t.bid == 9, (kw, mkw, t)
        assert t.b_wait == mkw["b_stall"], f"B stalled {t.b_wait} edges, expected {mkw['b_stall']}"
        assert [w["data"] for w in slave.w_log] == data, kw
        assert [w["addr"] for w in slave.aw_log] == [BASE + 4 * i for i in range(4)], kw
        assert not slave.viol and not t.viol, (kw, slave.viol, t.viol)
        await _quiet(dut)
        slave.stop()


@cocotb.test()
async def test_w_offered_before_aw_is_not_consumed(dut):
    """W valid presented 6 cycles before AW: the bridge must not accept it until the AW handshake."""
    master, slave = await _setup(dut)
    data = [0x01, 0x02]
    t = await master.write(BASE, data, aw_delay=6, w_before_aw=True)
    assert t.aw_cycle > 0 and t.w_cycles[0] > t.aw_cycle, (
        f"first W accepted at edge {t.w_cycles[0]} but AW only at {t.aw_cycle}")
    assert [w["data"] for w in slave.w_log] == data and t.bresp == OKAY
    assert not slave.viol and not t.viol


@cocotb.test()
async def test_read_burst(dut):
    master, slave = await _setup(dut)
    for n in (1, 2, 4, 8, 16):
        base = BASE + 0x200 * n
        for i in range(n):
            slave.mem[base + 4 * i] = 0xC0DE_0000 + (n << 8) + i
        slave.ar_log.clear()
        t = await master.read(base, n, rid=7)
        assert t.data == [0xC0DE_0000 + (n << 8) + i for i in range(n)], f"n={n}: {[hex(d) for d in t.data]}"
        assert [a["addr"] for a in slave.ar_log] == [base + 4 * i for i in range(n)], f"n={n}"
        assert all(b[3] == 7 for b in t.beats), "rid must reflect arid on every beat"
        assert t.resps == [OKAY] * n
        assert [b[2] for b in t.beats] == [0] * (n - 1) + [1], f"n={n}: rlast placement"
        assert not t.viol and not slave.viol, (t.viol, slave.viol)
        await _quiet(dut, 3)


@cocotb.test()
async def test_read_error_responses_are_per_beat(dut):
    """R carries the response of ITS beat; an error beat does not poison later beats and never
    truncates the burst (rlast still on the last beat)."""
    master, slave = await _setup(dut)
    slave.rresps = [OKAY, SLVERR, DECERR, OKAY]
    t = await master.read(BASE, 4, rid=3)
    assert t.resps == [OKAY, SLVERR, DECERR, OKAY], t.resps
    assert len(slave.ar_log) == 4
    assert [b[2] for b in t.beats] == [0, 0, 0, 1] and not t.viol
    slave.rresps = [OKAY, OKAY, OKAY, DECERR]      # error on the final beat
    t = await master.read(BASE + 0x40, 4, rid=4)
    assert t.resps == [OKAY, OKAY, OKAY, DECERR] and t.beats[-1][2] == 1, t.beats
    # single-beat SLVERR
    slave.rresps = [SLVERR]
    t = await master.read(BASE + 0x80, 1)
    assert t.resps == [SLVERR] and t.beats[0][2] == 1
    assert not slave.viol


@cocotb.test()
async def test_read_stalls(dut):
    """AR/R stalls on both sides: slave slow to accept AR and to answer, master slow to take R."""
    first = True
    for kw, stalls in ((dict(ar_delay=4, r_delay=3), [0, 4, 1, 2]),
                       (dict(ar_delay=0, r_delay=0), [3, 3, 3, 3]),
                       (dict(ar_delay=2, r_delay=6), [1, 0, 0, 7])):
        master, slave = await _setup(dut, clock=first, **kw)
        first = False
        for i in range(4):
            slave.mem[BASE + 4 * i] = 0xFACE_0000 + i
        t = await master.read(BASE, 4, rid=6, ar_delay=2, r_stalls=stalls)
        assert t.data == [0xFACE_0000 + i for i in range(4)], (kw, [hex(d) for d in t.data])
        assert [b[2] for b in t.beats] == [0, 0, 0, 1]
        assert not t.viol and not slave.viol, (kw, t.viol, slave.viol)
        await _quiet(dut)
        slave.stop()


@cocotb.test()
async def test_read_and_write_run_concurrently(dut):
    """The write and read FSMs are independent (module header): overlap them and check both."""
    master_w, slave = await _setup(dut, r_delay=2, b_delay=2)
    master_r = master_w     # same port; separate coroutines drive disjoint channels
    for i in range(4):
        slave.mem[BASE + 0x400 + 4 * i] = 0x7000 + i
    wr = cocotb.start_soon(master_w.write(BASE, [1, 2, 3, 4], wid=1, b_stall=4))
    rd = cocotb.start_soon(master_r.read(BASE + 0x400, 4, rid=2, r_stalls=[2, 0, 3, 0]))
    tw, tr = await wr, await rd
    assert tw.bresp == OKAY and tw.bid == 1
    assert tr.data == [0x7000 + i for i in range(4)] and all(b[3] == 2 for b in tr.beats)
    assert [w["data"] for w in slave.w_log] == [1, 2, 3, 4]
    assert not slave.viol, slave.viol


@cocotb.test()
async def test_reset_mid_burst_returns_to_idle(dut):
    """A reset in the middle of a write burst drops the burst: no stray B, and the bridge accepts a
    fresh burst afterwards with a clean response."""
    master, slave = await _setup(dut, b_delay=3)
    slave.bresps = [SLVERR, SLVERR, SLVERR, SLVERR]
    task = cocotb.start_soon(master.write(BASE, [1, 2, 3, 4], w_gaps=[0, 6, 6, 6]))
    for _ in range(14):
        await RisingEdge(dut.clk)
    task.kill()
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    master.idle()
    slave.stop()
    slave2 = AxiLiteSlave(dut, "m_axil_", dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    slave2.start()
    await _quiet(dut, 4)
    t = await master.write(BASE + 0x80, [9, 8], wid=3)
    assert t.bresp == OKAY and t.bid == 3, "response accumulator survived reset"
    assert not slave2.viol
