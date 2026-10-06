"""Bead ej6j -- axi4_crossbar: decode-error bursts, stalls and slave error responses.

test_crossbar.py only ever sends single-beat DECERR and always-OKAY slaves.  These tests use the
cycle-accurate BFMs in axi4_fabric_bfm.py (stalls, scripted responses, protocol checks) and check AXI4
behaviour, not line toggling:
  * an unmapped read burst returns arlen+1 DECERR beats, rdata 0, RLAST on the last beat only, and holds
    its payload stable while RREADY is low
  * an unmapped write burst SINKS every W beat (nothing leaks to a slave), returns exactly one DECERR B
    only after WLAST, and holds B until BREADY
  * the decode-error engines are per master and do not disturb mapped traffic of other masters
  * a slave's own SLVERR/DECERR is steered back to the right master, per beat for reads
  * a one-cycle ARVALID pulse is held towards a slow slave until it accepts (AXI4 A3-38)

Same wrapper/topology as test_crossbar.py: 3 masters x 2 slaves (s0 = ROM, s1 = SRAM).
Run together with it: ``make crossbar`` (MODULE=test_crossbar,test_crossbar_errors).
"""

import cocotb
from axi4_fabric_bfm import DECERR, OKAY, SLVERR, AxiMaster, AxiSlave, Watch
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

CLK_PERIOD_NS = 2
ROM_BASE = 0x0000_1000
SRAM_BASE = 0x0000_2000
UNMAPPED = (0x0000_0000, 0x0000_0FFC, 0x1000_0000, 0x2000_1000, 0xFFFF_FFF0)
LEAK = ("s0_awvalid", "s0_wvalid", "s0_arvalid", "s1_awvalid", "s1_wvalid", "s1_arvalid")


async def _setup2(dut, clock=True, **slave_kw):
    """Clock + reset, three cycle-accurate masters and two scripted slaves."""
    if clock:
        cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
    masters = [AxiMaster(dut, f"m{i}_", dut.clk) for i in range(3)]
    s0 = AxiSlave(dut, "s0_", dut.clk, **slave_kw)
    s1 = AxiSlave(dut, "s1_", dut.clk, **slave_kw)
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    s0.start()
    s1.start()
    return masters, s0, s1


def _no_leak(watch):
    assert not watch.hits, f"unmapped traffic leaked to a slave: {sorted(set(watch.hits))}"


@cocotb.test()
async def test_decerr_read_bursts(dut):
    masters, s0, s1 = await _setup2(dut)
    leak = Watch(dut, LEAK, dut.clk)
    cases = [(1, 0), (2, 0), (4, [0, 3, 0, 2]), (4, 5), (16, [1, 0] * 8), (256, [0] * 255 + [4])]
    for mi, m in enumerate(masters):
        for n, stalls in cases:
            addr = UNMAPPED[(mi + n) % len(UNMAPPED)]
            t = await m.read(addr, n, r_stalls=stalls, ar_delay=mi, timeout=6000)
            assert len(t.beats) == n, f"m{mi} n={n}: got {len(t.beats)} beats"
            assert t.resps == [DECERR] * n, f"m{mi} n={n}: {set(t.resps)}"
            assert t.data == [0] * n, f"m{mi} n={n}: DECERR beats must carry zero data"
            assert [b[2] for b in t.beats] == [0] * (n - 1) + [1], f"m{mi} n={n}: rlast placement"
            assert not t.viol, f"m{mi} n={n}: {t.viol}"
    _no_leak(leak)


@cocotb.test()
async def test_decerr_write_bursts(dut):
    masters, s0, s1 = await _setup2(dut)
    leak = Watch(dut, LEAK, dut.clk)
    cases = [(1, None, 0), (2, [0, 2], 3), (4, [0, 3, 0, 5], 0), (4, [1, 1, 1, 1], 7),
             (16, [0, 1] * 8, 2), (64, None, 4)]
    for mi, m in enumerate(masters):
        for n, gaps, bst in cases:
            addr = UNMAPPED[(mi + n) % len(UNMAPPED)]
            t = await m.write(addr, [0xD000_0000 + k for k in range(n)], w_gaps=gaps, b_stall=bst,
                              aw_delay=mi, timeout=6000)
            assert t.bresp == DECERR, f"m{mi} n={n}: bresp {t.bresp}"
            assert len(t.w_cycles) == n, f"m{mi} n={n}: only {len(t.w_cycles)} W beats sunk"
            assert t.first_bvalid > t.w_cycles[-1], f"m{mi} n={n}: B before the last W beat"
            assert t.b_wait == bst, f"m{mi} n={n}: B stalled {t.b_wait} edges, expected {bst}"
            assert not t.viol, f"m{mi} n={n}: {t.viol}"
            # exactly one B: nothing more once the handshake is done
            for _ in range(4):
                await RisingEdge(dut.clk)
                assert not int(getattr(dut, f"m{mi}_bvalid").value), "second B for one write burst"
    _no_leak(leak)
    assert not s0.mem and not s1.mem, "an unmapped write modified a slave memory"


@cocotb.test()
async def test_decerr_then_mapped_on_same_master(dut):
    """The decode-error FSMs return to idle: a mapped burst right after an unmapped one is routed."""
    masters, s0, s1 = await _setup2(dut)
    m = masters[0]
    for _ in range(3):
        t = await m.write(UNMAPPED[0], [1, 2, 3], b_stall=2)
        assert t.bresp == DECERR
        t = await m.write(SRAM_BASE + 0x40, [0xAB, 0xCD, 0xEF, 0x01], b_stall=1)
        assert t.bresp == OKAY
        r = await m.read(UNMAPPED[2], 4, r_stalls=1)
        assert r.resps == [DECERR] * 4
        r = await m.read(SRAM_BASE + 0x40, 4)
        assert r.data == [0xAB, 0xCD, 0xEF, 0x01] and r.resps == [OKAY] * 4, [hex(d) for d in r.data]


@cocotb.test()
async def test_decerr_masters_run_concurrently_and_do_not_block_mapped(dut):
    masters, s0, s1 = await _setup2(dut, r_delay=1)
    leak = Watch(dut, ("s0_awvalid", "s0_wvalid", "s0_arvalid"), dut.clk)   # only s1 is used legitimately
    for i in range(8):
        s1.mem[SRAM_BASE + 0x100 + 4 * i] = 0x1000 + i
    t_dr = cocotb.start_soon(masters[0].read(UNMAPPED[0], 16, r_stalls=[3] * 16, timeout=6000))
    t_dw = cocotb.start_soon(masters[2].write(UNMAPPED[3], list(range(8)), w_gaps=[2] * 8, b_stall=6,
                                              timeout=6000))
    t_ok = cocotb.start_soon(masters[1].read(SRAM_BASE + 0x100, 8, timeout=6000))
    r_dr, r_dw, r_ok = await t_dr, await t_dw, await t_ok
    assert r_dr.resps == [DECERR] * 16 and [b[2] for b in r_dr.beats] == [0] * 15 + [1]
    assert r_dw.bresp == DECERR and len(r_dw.w_cycles) == 8
    assert r_ok.data == [0x1000 + i for i in range(8)] and r_ok.resps == [OKAY] * 8
    assert not (r_dr.viol or r_dw.viol or r_ok.viol), (r_dr.viol, r_dw.viol, r_ok.viol)
    assert not s1.viol
    _no_leak(leak)


@cocotb.test()
async def test_slave_responses_are_steered_per_beat(dut):
    """Slave SLVERR/DECERR reach the issuing master: B for writes, per-beat R for reads."""
    def resp1(kind, addr):
        if kind == "w":
            return {SRAM_BASE + 0x200: SLVERR, SRAM_BASE + 0x300: DECERR}.get(addr, OKAY)
        return {SRAM_BASE + 0x48: SLVERR, SRAM_BASE + 0x50: DECERR, SRAM_BASE + 0x80: SLVERR}.get(addr, OKAY)

    masters, s0, s1 = await _setup2(dut)
    s1.resp_fn = resp1
    for i in range(4):
        s1.mem[SRAM_BASE + 0x44 + 4 * i] = 0xAAA0 + i
    s0.mem[ROM_BASE + 0x10] = 0x5151
    m0, m1 = masters[0], masters[1]

    t = await m0.write(SRAM_BASE + 0x200, [1, 2, 3, 4], b_stall=2)
    assert t.bresp == SLVERR, f"slave SLVERR lost in the crossbar: {t.bresp}"
    t = await m1.write(SRAM_BASE + 0x300, [5], b_stall=0)
    assert t.bresp == DECERR, f"slave DECERR lost in the crossbar: {t.bresp}"
    t = await m0.write(SRAM_BASE + 0x400, [6, 7])
    assert t.bresp == OKAY, "OKAY slave response must not inherit the previous error"

    # error on the 2nd and 4th beat of a burst: per-beat response, data still delivered
    t = await m0.read(SRAM_BASE + 0x44, 4, r_stalls=[0, 2, 0, 1])
    assert t.resps == [OKAY, SLVERR, OKAY, DECERR], t.resps
    assert t.data == [0xAAA0 + i for i in range(4)], [hex(d) for d in t.data]
    assert [b[2] for b in t.beats] == [0, 0, 0, 1] and not t.viol
    # a different master reading a different slave concurrently is unaffected by the error traffic
    rd_err = cocotb.start_soon(m0.read(SRAM_BASE + 0x80, 1, r_stalls=3))
    rd_ok = cocotb.start_soon(m1.read(ROM_BASE + 0x10, 1))
    te, to = await rd_err, await rd_ok
    assert te.resps == [SLVERR] and to.resps == [OKAY] and to.data == [0x5151]


@cocotb.test()
async def test_one_cycle_arvalid_pulse_is_held_to_slow_slave(dut):
    """GPU-style one-cycle ARVALID: the crossbar early-accepts, captures AR and must keep driving the
    slave (stable payload) until the slave's ARREADY, however late that is."""
    first = True
    for delay in (3, 8):
        masters, s0, s1 = await _setup2(dut, clock=first, ar_delay=delay, r_delay=1)
        first = False
        for i in range(4):
            s1.mem[SRAM_BASE + 0x40 + 4 * i] = 0x7770 + i
        t = await masters[1].read(SRAM_BASE + 0x40, 4, pulse=True, r_stalls=[0, 2, 0, 0])
        assert t.data == [0x7770 + i for i in range(4)], (delay, [hex(d) for d in t.data])
        assert len(s1.ar_log) == 1 and s1.ar_log[0]["addr"] == SRAM_BASE + 0x40 and s1.ar_log[0]["len"] == 3
        assert s1.arvalid_edges >= delay, f"slave saw ARVALID only {s1.arvalid_edges} edges (delay {delay})"
        assert not s1.viol, s1.viol
        assert not t.viol
        s0.stop()
        s1.stop()


@cocotb.test()
async def test_slave_side_stalls_on_every_channel(dut):
    """Both slaves slow on AW/W/B/AR/R: bursts to different slaves complete with intact data."""
    masters, s0, s1 = await _setup2(dut, aw_delay=3, w_delay=2, b_delay=4, ar_delay=5, r_delay=2)
    data = [0xFEED0000 + k for k in range(4)]
    w0 = cocotb.start_soon(masters[0].write(ROM_BASE + 0x20, data, b_stall=3, timeout=6000))
    w1 = cocotb.start_soon(masters[1].write(SRAM_BASE + 0x60, data[::-1], w_gaps=[0, 2, 0, 1], timeout=6000))
    t0, t1 = await w0, await w1
    assert t0.bresp == OKAY and t1.bresp == OKAY and not (t0.viol or t1.viol)
    assert [s0.mem[ROM_BASE + 0x20 + 4 * k] for k in range(4)] == data
    assert [s1.mem[SRAM_BASE + 0x60 + 4 * k] for k in range(4)] == data[::-1]
    r0 = cocotb.start_soon(masters[0].read(SRAM_BASE + 0x60, 4, r_stalls=[2, 0, 0, 3], timeout=6000))
    r1 = cocotb.start_soon(masters[1].read(ROM_BASE + 0x20, 4, r_stalls=1, timeout=6000))
    a, b = await r0, await r1
    assert a.data == data[::-1] and b.data == data
    assert not (a.viol or b.viol or s0.viol or s1.viol), (a.viol, b.viol, s0.viol, s1.viol)
