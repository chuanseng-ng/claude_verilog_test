"""axi4_crossbar: measure which master wins under contention (present fixed priority).

These tests characterise what the RTL does today.  They do not assert a fairness rule.
Per slave and per direction there is one engine.  While it is idle, the lowest-index master
whose xVALID is high in that cycle wins; the same cycle carries the handshake.  The engine
keeps no queue, so a master that arrived earlier gains nothing over a later one.

Every master issues its next request only after the B or RLAST of the previous one.  Masters
and slaves are cycle-stepped drivers in this file.  A per-cycle trace is dumped on failure.
Run with test_crossbar.py: ``make crossbar``.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Combine, ReadOnly, RisingEdge, with_timeout

CLK_PERIOD_NS = 2
BASE = (0x0000_1000, 0x0000_2000)  # s0 = ROM window, s1 = SRAM window
DATA_MASK = 0x5A5A_5A5A
TIMEOUT_US = 40
N_MASTERS = 3
TRACE_TAIL = 70


class Monitor:
    """Samples every cycle, keeps a trace and the handshake event lists."""

    def __init__(self, dut):
        self.dut = dut
        self.cyc = 0
        self.rows = []
        self.start = {}  # (kind, master) -> cycle of first valid
        self.waits = {"r": [[] for _ in range(N_MASTERS)], "w": [[] for _ in range(N_MASTERS)]}
        self.starts = {"r": [[] for _ in range(N_MASTERS)], "w": [[] for _ in range(N_MASTERS)]}
        self.done = {"r": [[] for _ in range(N_MASTERS)], "w": [[] for _ in range(N_MASTERS)]}
        self.mgrant = {"r": [], "w": []}  # (cycle, master) master-side address handshake
        self.sgrant = {"r": [[], []], "w": [[], []]}  # per slave: (cycle, master id)

    def _v(self, name):
        return int(getattr(self.dut, name).value)

    async def run(self):
        while True:
            await RisingEdge(self.dut.clk)
            await ReadOnly()
            self._sample()
            self.cyc += 1

    def _sample(self):
        v = self._v
        c = self.cyc
        cell = []
        for kind, ax, rsp in (("r", "ar", "r"), ("w", "aw", "b")):
            for m in range(N_MASTERS):
                valid, ready = v(f"m{m}_{ax}valid"), v(f"m{m}_{ax}ready")
                if valid and (kind, m) not in self.start:
                    self.start[(kind, m)] = c
                    self.starts[kind][m].append(c)
                if valid and ready:
                    self.waits[kind][m].append(c - self.start.pop((kind, m)))
                    self.mgrant[kind].append((c, m))
                cell.append(f"{valid}{ready}")
                if kind == "r":
                    fin = v(f"m{m}_rvalid") and v(f"m{m}_rlast") and v(f"m{m}_rready")
                else:
                    fin = v(f"m{m}_bvalid") and v(f"m{m}_bready")
                if fin:
                    self.done[kind][m].append(c)
            for s in range(2):
                if v(f"s{s}_{ax}valid") and v(f"s{s}_{ax}ready"):
                    self.sgrant[kind][s].append((c, v(f"s{s}_{ax}id")))
        self.rows.append((c, cell, [v(f"s{s}_{a}valid") for s in range(2) for a in ("ar", "aw")]))

    def dump(self, tail=TRACE_TAIL):
        log = self.dut._log
        log.error("cycle trace (m0..m2 AR vr | m0..m2 AW vr | s0 ar,aw valid s1 ar,aw valid)")
        for c, cell, sv in self.rows[-tail:]:
            log.error(
                "  c=%4d AR %s | AW %s | slv %s", c, " ".join(cell[:3]), " ".join(cell[3:]), sv
            )

    def order(self, kind, slave, since):
        """Master ids granted by `slave` at or after cycle `since`, in grant order."""
        return [mid for c, mid in self.sgrant[kind][slave] if c >= since]


class Bench:
    """Clock, reset, three masters, two slave responders and the monitor."""

    def __init__(self, dut, r_lat=0, b_lat=0):
        self.dut = dut
        self.r_lat = r_lat
        self.b_lat = b_lat
        self.mon = Monitor(dut)

    @classmethod
    async def create(cls, dut, **kw):
        self = cls(dut, **kw)
        cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
        dut.rst_n.value = 0
        for m in range(N_MASTERS):
            p = f"m{m}_"
            for sig in ("awvalid", "wvalid", "arvalid", "wlast"):
                getattr(dut, p + sig).value = 0
            for sig in ("awaddr", "awlen", "awsize", "araddr", "arlen", "arsize", "wdata"):
                getattr(dut, p + sig).value = 0
            dut._id(p + "awburst", False).value = 1
            dut._id(p + "arburst", False).value = 1
            dut._id(p + "wstrb", False).value = 0xF
            dut._id(p + "bready", False).value = 1
            dut._id(p + "rready", False).value = 1
        for s in range(2):
            for sig in ("awready", "wready", "arready"):
                getattr(dut, f"s{s}_{sig}").value = 1
            for sig in ("bvalid", "rvalid", "rlast", "bid", "rid", "rdata", "bresp", "rresp"):
                getattr(dut, f"s{s}_{sig}").value = 0
        for _ in range(5):
            await RisingEdge(dut.clk)
        dut.rst_n.value = 1
        for _ in range(3):
            await RisingEdge(dut.clk)
        cocotb.start_soon(self.mon.run())
        for s in range(2):
            cocotb.start_soon(self._slave_read(s))
            cocotb.start_soon(self._slave_write(s))
        await RisingEdge(dut.clk)
        return self

    # ── slave responders (one transfer at a time, always-ready address channels) ──
    async def _slave_read(self, s):
        d = self.dut
        sig = lambda n: getattr(d, f"s{s}_{n}")  # noqa: E731
        while True:
            await ReadOnly()
            hit = int(sig("arvalid").value)
            arid, addr = int(sig("arid").value), int(sig("araddr").value)
            await RisingEdge(d.clk)
            if not hit:
                continue
            for _ in range(self.r_lat):
                await RisingEdge(d.clk)
            sig("rid").value = arid
            sig("rdata").value = addr ^ DATA_MASK
            sig("rlast").value = 1
            sig("rvalid").value = 1
            while True:
                await ReadOnly()
                taken = int(sig("rready").value)
                await RisingEdge(d.clk)
                if taken:
                    break
            sig("rvalid").value = 0
            sig("rlast").value = 0

    async def _slave_write(self, s):
        d = self.dut
        sig = lambda n: getattr(d, f"s{s}_{n}")  # noqa: E731
        got_aw = got_w = False
        awid = 0
        while True:
            await ReadOnly()
            aw, w = int(sig("awvalid").value), int(sig("wvalid").value) and int(sig("wlast").value)
            cur = int(sig("awid").value)
            await RisingEdge(d.clk)
            if aw:
                got_aw, awid = True, cur
            got_w = got_w or bool(w)
            if not (got_aw and got_w):
                continue
            got_aw = got_w = False
            for _ in range(self.b_lat):
                await RisingEdge(d.clk)
            sig("bid").value = awid
            sig("bvalid").value = 1
            while True:
                await ReadOnly()
                taken = int(sig("bready").value)
                await RisingEdge(d.clk)
                if taken:
                    break
            sig("bvalid").value = 0

    # ── masters: enter and leave in the active phase after a RisingEdge ──
    async def read(self, m, addr):
        d, p = self.dut, f"m{m}_"
        getattr(d, p + "araddr").value = addr
        getattr(d, p + "arvalid").value = 1
        while True:
            await ReadOnly()
            hs = int(getattr(d, p + "arready").value)
            await RisingEdge(d.clk)
            if hs:
                break
        getattr(d, p + "arvalid").value = 0
        while True:
            await ReadOnly()
            fin = int(getattr(d, p + "rvalid").value) and int(getattr(d, p + "rlast").value)
            data = int(getattr(d, p + "rdata").value)
            await RisingEdge(d.clk)
            if fin:
                break
        self.check(data == addr ^ DATA_MASK, f"m{m} read {addr:#x} returned {data:#x}")
        return data

    async def write(self, m, addr, data=0xC0DE_0000):
        d, p = self.dut, f"m{m}_"
        getattr(d, p + "awaddr").value = addr
        getattr(d, p + "wdata").value = data | m
        getattr(d, p + "wlast").value = 1
        getattr(d, p + "awvalid").value = 1
        getattr(d, p + "wvalid").value = 1
        aw_done = w_done = False
        while not (aw_done and w_done):
            await ReadOnly()
            hs_aw = not aw_done and int(getattr(d, p + "awready").value)
            hs_w = not w_done and int(getattr(d, p + "wready").value)
            await RisingEdge(d.clk)
            if hs_aw:
                aw_done = True
                getattr(d, p + "awvalid").value = 0
            if hs_w:
                w_done = True
                getattr(d, p + "wvalid").value = 0
        getattr(d, p + "wlast").value = 0
        while True:
            await ReadOnly()
            fin = int(getattr(d, p + "bvalid").value)
            await RisingEdge(d.clk)
            if fin:
                break

    def xfer(self, kind, m, slave, off=0):
        addr = BASE[slave] + 0x40 * m + off
        return self.read(m, addr) if kind == "r" else self.write(m, addr)

    async def hog(self, kind, m, slave, stop, gap=0):
        """Back-to-back transfers of one master until `stop[0]`; `gap` idle cycles between."""
        n = 0
        while not stop[0]:
            await self.xfer(kind, m, slave, off=4 * (n % 8))
            n += 1
            for _ in range(gap):
                await RisingEdge(self.dut.clk)
        return n

    async def cycles(self, n):
        for _ in range(n):
            await RisingEdge(self.dut.clk)

    async def join(self, *tasks):
        await with_timeout(Combine(*tasks), TIMEOUT_US, "us")

    def check(self, cond, msg):
        """Assert with a cycle trace on failure."""
        if not cond:
            self.mon.dump()
            raise AssertionError(msg)

    def idle_gaps(self, kind, m, first=0):
        """Idle cycles between each completion of master m and its next valid."""
        st, dn = self.mon.starts[kind][m], self.mon.done[kind][m]
        return [st[i + 1] - (dn[i] + 1) for i in range(first, min(len(dn), len(st) - 1))]


async def _same_cycle_round(b, kind, masters, slave):
    """All `masters` raise their request in the same cycle; return grant order at the slave."""
    since = b.mon.cyc
    tasks = [cocotb.start_soon(b.xfer(kind, m, slave)) for m in masters]
    await b.join(*tasks)
    starts = {b.mon.starts[kind][m][-1] for m in masters}
    b.check(len(starts) == 1, f"requests were not simultaneous: {sorted(starts)}")
    order = b.mon.order(kind, slave, since)
    master_side = [m for c, m in b.mon.mgrant[kind] if c >= since]
    b.check(order == master_side, f"slave order {order} != master order {master_side}")
    await b.cycles(3)
    return order


async def _order_test(dut, kind):
    b = await Bench.create(dut)
    subsets = [(0, 1, 2), (1, 2), (0, 2), (0, 1)]
    for slave in (0, 1):
        for lat in (0, 2):
            b.r_lat = b.b_lat = lat
            for masters in subsets:
                for _ in range(2):
                    got = await _same_cycle_round(b, kind, masters, slave)
                    want = sorted(masters)
                    b.check(
                        got == want, f"slave {slave} lat {lat} {masters}: got {got}, want {want}"
                    )
                    dut._log.info(
                        "grant order slave=%d lat=%d requesters=%s -> %s", slave, lat, masters, got
                    )


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_grant_order_reads_same_cycle(dut):
    """Same-cycle AR requests to one slave are granted in ascending master index."""
    await _order_test(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_grant_order_writes_same_cycle(dut):
    """Same-cycle AW requests to one slave are granted in ascending master index."""
    await _order_test(dut, "w")


async def _starvation(dut, kind):
    b = await Bench.create(dut, r_lat=1, b_lat=1)
    window = 400
    stop = [False]
    hog = cocotb.start_soon(b.hog(kind, 0, 1, stop))
    await b.cycles(6)
    t0 = b.mon.cyc
    low = [cocotb.start_soon(b.xfer(kind, m, 1)) for m in (1, 2)]
    await b.cycles(window)
    stop[0] = True
    await b.join(hog, *low)
    n0 = hog.result()
    order = b.mon.order(kind, 1, 0)
    gaps = b.idle_gaps(kind, 0)
    b.check(set(gaps) == {0}, f"m0 was not back-to-back, idle gaps {sorted(set(gaps))}")
    b.check(order == [0] * n0 + [1, 2], f"grant order {order}")
    w1, w2 = b.mon.waits[kind][1][0], b.mon.waits[kind][2][0]
    b.check(w2 >= window, f"m2 granted after only {w2} cycles")
    period = (b.mon.starts[kind][0][-1] - b.mon.starts[kind][0][0]) / (n0 - 1)
    dut._log.info(
        "%s starvation: m0 %d back-to-back transfers (period %.1f cycles); "
        "m1 waited %d cycles, m2 waited %d cycles (window %d, requested at cycle %d)",
        kind,
        n0,
        period,
        w1,
        w2,
        window,
        t0,
    )


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_m0_back_to_back_reads_hold_off_lower_masters(dut):
    """m0 re-requests with no idle cycle; m1 and m2 get no AR grant until it stops."""
    await _starvation(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_m0_back_to_back_writes_hold_off_lower_masters(dut):
    """m0 re-requests with no idle cycle; m1 and m2 get no AW grant until it stops."""
    await _starvation(dut, "w")


async def _gap_test(dut, kind):
    b = await Bench.create(dut, r_lat=1, b_lat=1)
    for gap, want in ((1, [1, 0, 2]), (2, [1, 0, 2]), (20, [1, 2, 0])):
        stop = [False]
        first = len(b.mon.starts[kind][0])
        hog = cocotb.start_soon(b.hog(kind, 0, 1, stop, gap=gap))
        seen = len(b.mon.sgrant[kind][1])
        while len(b.mon.sgrant[kind][1]) == seen:  # wait until m0 is mid-transfer
            await b.cycles(1)
        seen = len(b.mon.sgrant[kind][1])
        low = [cocotb.start_soon(b.xfer(kind, m, 1)) for m in (1, 2)]
        await b.join(*low)
        while len(b.mon.sgrant[kind][1]) < seen + 3:  # m0 must come back once
            await b.cycles(1)
        stop[0] = True
        await b.join(hog)
        order = [mid for _, mid in b.mon.sgrant[kind][1][seen:]]
        got_gap = set(b.idle_gaps(kind, 0, first))
        b.check(got_gap == {gap}, f"m0 idle gap {sorted(got_gap)}, wanted {gap}")
        b.check(order[:3] == want, f"gap {gap}: grant order {order}, want {want}")
        waits = (b.mon.waits[kind][1][-1], b.mon.waits[kind][2][-1])
        dut._log.info(
            "%s m0 gap=%d: grants after m1/m2 arrive %s; m1/m2 waited %s cycles",
            kind,
            gap,
            order[:3],
            waits,
        )
        await b.cycles(4)


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_one_idle_cycle_lets_lower_master_in_reads(dut):
    """An idle ARVALID-low cycle after m0's RLAST lets the lowest waiting master win."""
    await _gap_test(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_one_idle_cycle_lets_lower_master_in_writes(dut):
    """An idle AWVALID-low cycle after m0's B lets the lowest waiting master win."""
    await _gap_test(dut, "w")


async def _lone_master(dut, kind):
    b = await Bench.create(dut)
    lat = {}
    for m in (0, 1, 2):
        s = b.mon.cyc
        await b.xfer(kind, m, 1)
        wait = b.mon.waits[kind][m][-1]
        lat[m] = b.mon.done[kind][m][-1] - b.mon.starts[kind][m][-1]
        b.check(wait == 0, f"m{m} alone waited {wait} cycles for its address handshake")
        b.check(b.mon.order(kind, 1, s) == [m], f"slave saw {b.mon.order(kind, 1, s)}")
        await b.cycles(3)
    b.check(len(set(lat.values())) == 1, f"latency depends on master index: {lat}")
    # m0 idle: m1 and m2 contend, m1 first, m2 follows with no bubble.
    s = b.mon.cyc
    tasks = [cocotb.start_soon(b.xfer(kind, m, 1)) for m in (1, 2)]
    await b.join(*tasks)
    b.check(b.mon.order(kind, 1, s) == [1, 2], f"order {b.mon.order(kind, 1, s)}")
    bubble = b.mon.mgrant[kind][-1][0] - b.mon.done[kind][1][-1]
    b.check(bubble == 1, f"m2 granted {bubble} cycles after m1's completion")
    dut._log.info(
        "%s lone-master latency per master %s; m2 granted %d cycle after m1 done", kind, lat, bubble
    )


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_lower_masters_granted_when_higher_idle_reads(dut):
    """With m0 idle, m1 or m2 is granted at once and m2 follows m1 with no bubble (reads)."""
    await _lone_master(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_lower_masters_granted_when_higher_idle_writes(dut):
    """With m0 idle, m1 or m2 is granted at once and m2 follows m1 with no bubble (writes)."""
    await _lone_master(dut, "w")


async def _cross_slave(dut, kind, hog_slave, other_master):
    other_slave = 1 - hog_slave
    b = await Bench.create(dut, r_lat=1, b_lat=1)
    count = 12

    async def burst():
        for i in range(count):
            await b.xfer(kind, other_master, other_slave, off=4 * i)

    s = b.mon.cyc
    await b.join(cocotb.start_soon(burst()))
    solo = b.mon.cyc - s
    await b.cycles(4)
    stop = [False]
    hog = cocotb.start_soon(b.hog(kind, 0, hog_slave, stop))
    await b.cycles(6)
    s, g0 = b.mon.cyc, len(b.mon.sgrant[kind][hog_slave])
    await b.join(cocotb.start_soon(burst()))
    busy = b.mon.cyc - s
    overlap = len(b.mon.sgrant[kind][hog_slave]) - g0
    stop[0] = True
    await b.join(hog)
    waits = b.mon.waits[kind][other_master][-count:]
    b.check(set(waits) == {0}, f"m{other_master} waited on its own slave: {waits}")
    b.check(busy == solo, f"m{other_master} took {busy} cycles beside the hog, {solo} alone")
    b.check(overlap > 0, "hog made no progress during the other master's run")
    dut._log.info(
        "%s m0 hogs s%d; m%d on s%d: %d transfers in %d cycles (alone %d), m0 did %d meanwhile",
        kind,
        hog_slave,
        other_master,
        other_slave,
        count,
        busy,
        solo,
        overlap,
    )


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_slaves_serve_masters_concurrently_reads(dut):
    """A master hogging one slave's read engine does not slow reads to the other slave."""
    await _cross_slave(dut, "r", 0, 2)
    await _cross_slave(dut, "r", 1, 1)


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_slaves_serve_masters_concurrently_writes(dut):
    """A master hogging one slave's write engine does not slow writes to the other slave."""
    await _cross_slave(dut, "w", 0, 2)
    await _cross_slave(dut, "w", 1, 1)
