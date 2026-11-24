"""axi4_crossbar: round-robin arbitration between masters, checked against a reference model.

Per slave and direction one engine has one rotating pointer.  While the engine is idle, the first
requester at or above the pointer wins, else the search wraps.  A grant moves the pointer to the
granted master plus one.  Reset leaves it at master 0.  The same cycle carries the handshake.

`RrModel` is a Python copy of this rule.  `Bench.replay` runs it over the recorded trace: at each
master-side address handshake the model, given the masters whose xVALID was high for that slave,
must name the master the DUT granted.  `Bench.finish` runs that check and these at test end:

* Early-accept and engine agree: per slave, the master-side handshake order equals the slave-side
  grant order, and no cycle has two master-side handshakes for one slave.
* Grant bound: while a master X keeps xVALID high, each other master is granted at most once, so at
  most N-1 grants fall between X's request and its grant.  Proof: only a master in the circular span
  from the pointer up to X can win before X.  A grant moves the pointer one above the winner, so the
  span shrinks and its winners are distinct.  The span holds at most N-1 masters.
* Time bound: the period T of grant to next grant is measured with one master alone and back to
  back.  Each grant to another master holds the engine for one T, so X is granted within (N-1)*T
  cycles of its request.  Under full contention the period must not exceed T: no arbiter bubble.

Masters and slaves are cycle-stepped drivers.  A per-cycle trace is dumped on failure.
Run with test_crossbar.py: ``make crossbar``.
"""
# Doc: ds:ch:mod-data-fabric

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Combine, ReadOnly, RisingEdge, with_timeout

CLK_PERIOD_NS = 2
BASE = (0x0000_1000, 0x0000_2000)  # s0 = ROM window, s1 = SRAM window
DATA_MASK = 0x5A5A_5A5A
TIMEOUT_US = 40
N_MASTERS = 3
N_SLAVES = 2
TRACE_TAIL = 70
SUBSETS = [(0, 1, 2), (1, 2), (0, 2), (0, 1)]


def slave_of(addr):
    return 0 if addr < BASE[1] else 1


class RrModel:
    """Reference arbiter of one slave and one direction.

    `ptr` is the master where the next search starts.  Reset value is master 0.
    """

    def __init__(self, n=N_MASTERS, ptr=0):
        self.n = n
        self.ptr = ptr

    def pick(self, req):
        """First requester at or above the pointer, else the first one after the wrap."""
        for k in range(self.n):
            m = (self.ptr + k) % self.n
            if m in req:
                return m
        return None

    def grant(self, req):
        """Pick a master and move the pointer to one above it."""
        m = self.pick(req)
        if m is not None:
            self.ptr = (m + 1) % self.n
        return m

    def predict(self, masters):
        """Grant order for masters that all request now and do not request again."""
        left, order = set(masters), []
        trial = RrModel(self.n, self.ptr)
        while left:
            m = trial.grant(left)
            order.append(m)
            left.discard(m)
        return order


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
        # (cycle, master, slave) master-side address handshake
        self.mgrant = {"r": [], "w": []}
        # per cycle, per master: target slave while xVALID is high, else None
        self.req = {"r": [], "w": []}
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
            targets = []
            for m in range(N_MASTERS):
                valid, ready = v(f"m{m}_{ax}valid"), v(f"m{m}_{ax}ready")
                slave = slave_of(v(f"m{m}_{ax}addr")) if valid else None
                targets.append(slave)
                if valid and (kind, m) not in self.start:
                    self.start[(kind, m)] = c
                    self.starts[kind][m].append(c)
                if valid and ready:
                    self.waits[kind][m].append(c - self.start.pop((kind, m)))
                    self.mgrant[kind].append((c, m, slave))
                cell.append(f"{valid}{ready}")
                if kind == "r":
                    fin = v(f"m{m}_rvalid") and v(f"m{m}_rlast") and v(f"m{m}_rready")
                else:
                    fin = v(f"m{m}_bvalid") and v(f"m{m}_bready")
                if fin:
                    self.done[kind][m].append(c)
            self.req[kind].append(targets)
            for s in range(N_SLAVES):
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

    def grant_cycles(self, kind, slave):
        """Cycles of the master-side address handshakes for `slave`."""
        return [c for c, _, s in self.mgrant[kind] if s == slave]


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

    # ── reference model and trace checks ──
    def replay(self, kind):
        """Run the reference arbiter over the trace; return one model per slave.

        Fails at the first handshake where the DUT's master differs from the model's.
        """
        models = [RrModel() for _ in range(N_SLAVES)]
        for c, m, s in self.mon.mgrant[kind]:
            req = {k for k, tgt in enumerate(self.mon.req[kind][c]) if tgt == s}
            want = models[s].grant(req)
            self.check(
                want == m,
                f"{kind} slave {s} cycle {c}: requesters {sorted(req)}, "
                f"reference grants m{want}, DUT granted m{m}",
            )
        return models

    def expected_order(self, kind, slave, masters):
        """Grant order the model predicts for `masters` requesting together on `slave` now."""
        return self.replay(kind)[slave].predict(masters)

    def check_arbitration(self, kind):
        mon = self.mon
        self.replay(kind)
        seen = {}
        for c, m, s in mon.mgrant[kind]:
            self.check(
                (c, s) not in seen,
                f"{kind} cycle {c}: m{seen.get((c, s))} and m{m} both saw the handshake for s{s}",
            )
            seen[(c, s)] = m
        for s in range(N_SLAVES):
            master_side = [m for _, m, sl in mon.mgrant[kind] if sl == s]
            slave_side = [mid for _, mid in mon.sgrant[kind][s]]
            self.check(
                master_side == slave_side,
                f"{kind} s{s}: master-side order {master_side} != slave-side order {slave_side}",
            )
        for x in range(N_MASTERS):
            mine = [(c, s) for c, m, s in mon.mgrant[kind] if m == x]
            for start, (grant, s) in zip(mon.starts[kind][x], mine):
                others = [
                    m for c, m, sl in mon.mgrant[kind] if sl == s and start <= c < grant and m != x
                ]
                self.check(
                    len(others) <= N_MASTERS - 1 and len(set(others)) == len(others),
                    f"{kind} m{x} waited from cycle {start} to {grant} on s{s} "
                    f"while others were granted {others}",
                )

    async def finish(self):
        """Let the last transfers settle, then run the trace checks for both directions."""
        await self.cycles(4)
        for kind in ("r", "w"):
            self.check_arbitration(kind)

    async def solo_period(self, kind, slave, n=10):
        """Longest grant-to-grant period of master 0 alone and back to back."""
        first = len(self.mon.grant_cycles(kind, slave))
        stop = [False]
        hog = cocotb.start_soon(self.hog(kind, 0, slave, stop))
        while len(self.mon.grant_cycles(kind, slave)) < first + n:
            await self.cycles(1)
        stop[0] = True
        await self.join(hog)
        grants = self.mon.grant_cycles(kind, slave)[first:]
        await self.cycles(4)
        return max(b - a for a, b in zip(grants, grants[1:]))


async def _same_cycle_round(b, kind, masters, slave):
    """All `masters` raise their request in the same cycle; return grant order at the slave."""
    since = b.mon.cyc
    tasks = [cocotb.start_soon(b.xfer(kind, m, slave)) for m in masters]
    await b.join(*tasks)
    starts = {b.mon.starts[kind][m][-1] for m in masters}
    b.check(len(starts) == 1, f"requests were not simultaneous: {sorted(starts)}")
    order = b.mon.order(kind, slave, since)
    master_side = [m for c, m, _ in b.mon.mgrant[kind] if c >= since]
    b.check(order == master_side, f"slave order {order} != master order {master_side}")
    await b.cycles(3)
    return order


async def _order_test(dut, kind):
    b = await Bench.create(dut)
    # After reset every pointer is at master 0, and the two slaves do not share a pointer.
    for slave in (0, 1):
        got = await _same_cycle_round(b, kind, (0, 1, 2), slave)
        b.check(got == [0, 1, 2], f"slave {slave} after reset: got {got}, want [0, 1, 2]")
    for slave in (0, 1):
        for lat in (0, 2):
            b.r_lat = b.b_lat = lat
            for prime in (0, 1, 2):
                for masters in SUBSETS:
                    # A lone grant to `prime` puts this slave's pointer at prime+1.  A lone grant
                    # on the other slave must not move it.
                    await b.xfer(kind, prime, slave)
                    await b.cycles(3)
                    await b.xfer(kind, (prime + 1) % N_MASTERS, 1 - slave)
                    await b.cycles(3)
                    want = b.expected_order(kind, slave, masters)
                    got = await _same_cycle_round(b, kind, masters, slave)
                    b.check(
                        got == want,
                        f"slave {slave} lat {lat} after m{prime} {masters}: got {got}, want {want}",
                    )
                    dut._log.info(
                        "grant order slave=%d lat=%d prime=m%d requesters=%s -> %s",
                        slave,
                        lat,
                        prime,
                        masters,
                        got,
                    )
    await b.finish()


@cocotb.test(timeout_time=40, timeout_unit="us")
async def test_grant_order_reads_same_cycle(dut):
    """Same-cycle AR requests follow the rotating pointer, for every pointer position."""
    await _order_test(dut, "r")


@cocotb.test(timeout_time=40, timeout_unit="us")
async def test_grant_order_writes_same_cycle(dut):
    """Same-cycle AW requests follow the rotating pointer, for every pointer position."""
    await _order_test(dut, "w")


async def _lower_masters_bounded(dut, kind):
    b = await Bench.create(dut, r_lat=1, b_lat=1)
    period = await b.solo_period(kind, 1)
    bound = (N_MASTERS - 1) * period
    first = len(b.mon.done[kind][0])
    stop = [False]
    hog = cocotb.start_soon(b.hog(kind, 0, 1, stop))
    await b.cycles(6)
    t0 = b.mon.cyc
    low = [cocotb.start_soon(b.xfer(kind, m, 1)) for m in (1, 2)]
    await b.join(*low)
    stop[0] = True
    await b.join(hog)
    n0 = hog.result()
    gaps = b.idle_gaps(kind, 0, first)
    b.check(set(gaps) == {0}, f"m0 was not back-to-back, idle gaps {sorted(set(gaps))}")
    w1, w2 = b.mon.waits[kind][1][0], b.mon.waits[kind][2][0]
    b.check(max(w1, w2) <= bound, f"m1 waited {w1}, m2 waited {w2} cycles, bound {bound}")
    await b.finish()
    dut._log.info(
        "%s m0 hogs: %d back-to-back transfers; m1 waited %d, m2 waited %d cycles "
        "(period %d, bound %d, requested at cycle %d)",
        kind,
        n0,
        w1,
        w2,
        period,
        bound,
        t0,
    )


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_m0_back_to_back_reads_lower_masters_served_within_bound(dut):
    """m0 re-requests with no idle cycle; m1 and m2 get an AR grant within (N-1)*T cycles."""
    await _lower_masters_bounded(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_m0_back_to_back_writes_lower_masters_served_within_bound(dut):
    """m0 re-requests with no idle cycle; m1 and m2 get an AW grant within (N-1)*T cycles."""
    await _lower_masters_bounded(dut, "w")


async def _three_hogs(dut, kind, grants_each=12):
    b = await Bench.create(dut, r_lat=1, b_lat=1)
    period = await b.solo_period(kind, 1)
    bound = (N_MASTERS - 1) * period
    first = len(b.mon.grant_cycles(kind, 1))
    seen = [len(b.mon.waits[kind][m]) for m in range(N_MASTERS)]
    stop = [False]
    hogs = [cocotb.start_soon(b.hog(kind, m, 1, stop)) for m in range(N_MASTERS)]
    while len(b.mon.grant_cycles(kind, 1)) < first + N_MASTERS * grants_each:
        await b.cycles(1)
    stop[0] = True
    await b.join(*hogs)
    counts = [h.result() for h in hogs]
    await b.finish()
    order = [m for _, m, s in b.mon.mgrant[kind][-sum(counts) :] if s == 1]
    b.check(sorted(order[:3]) == [0, 1, 2], f"first round {order[:3]} is not every master once")
    b.check(
        all(order[i] == order[i - N_MASTERS] for i in range(N_MASTERS, len(order))),
        f"grant order is not a repeating rotation: {order}",
    )
    b.check(max(counts) - min(counts) <= 1, f"unequal shares {counts}")
    cycles = b.mon.grant_cycles(kind, 1)[first:]
    held = max(y - x for x, y in zip(cycles, cycles[1:]))
    b.check(held <= period, f"contended period {held} exceeds the lone period {period}")
    worst = max(w for m in range(N_MASTERS) for w in b.mon.waits[kind][m][seen[m] :])
    b.check(worst <= bound, f"worst wait {worst} cycles exceeds (N-1)*T = {bound}")
    dut._log.info(
        "%s three hogs: shares %s, worst wait %d cycles, bound %d, period %d (contended %d)",
        kind,
        counts,
        worst,
        bound,
        period,
        held,
    )


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_three_hogs_share_reads_evenly_within_bound(dut):
    """All three masters read back to back: equal shares, a repeating rotation, wait <= (N-1)*T."""
    await _three_hogs(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_three_hogs_share_writes_evenly_within_bound(dut):
    """All three masters write back to back: equal shares, a repeating rotation, wait <= (N-1)*T."""
    await _three_hogs(dut, "w")


async def _gap_test(dut, kind):
    b = await Bench.create(dut, r_lat=1, b_lat=1)
    orders = {}
    for gap in (0, 1, 2, 20):
        stop = [False]
        first = len(b.mon.starts[kind][0])
        hog = cocotb.start_soon(b.hog(kind, 0, 1, stop, gap=gap))
        seen = len(b.mon.sgrant[kind][1])
        while len(b.mon.sgrant[kind][1]) == seen:  # wait until m0 is mid-transfer
            await b.cycles(1)
        seen = len(b.mon.sgrant[kind][1])
        want = b.expected_order(kind, 1, (1, 2))  # pointer is one above m0
        low = [cocotb.start_soon(b.xfer(kind, m, 1)) for m in (1, 2)]
        await b.join(*low)
        while len(b.mon.sgrant[kind][1]) < seen + 3:  # m0 must come back once
            await b.cycles(1)
        stop[0] = True
        await b.join(hog)
        order = [mid for _, mid in b.mon.sgrant[kind][1][seen:]]
        got_gap = set(b.idle_gaps(kind, 0, first))
        b.check(got_gap == {gap}, f"m0 idle gap {sorted(got_gap)}, wanted {gap}")
        b.check(order[:2] == want, f"gap {gap}: grant order {order}, model says {want}")
        b.check(order[2] == 0, f"gap {gap}: m0 was not served after m1 and m2: {order}")
        orders[gap] = order[:3]
        waits = (b.mon.waits[kind][1][-1], b.mon.waits[kind][2][-1])
        dut._log.info(
            "%s m0 gap=%d: grants after m1/m2 arrive %s; m1/m2 waited %s cycles",
            kind,
            gap,
            order[:3],
            waits,
        )
        await b.cycles(4)
    b.check(len({tuple(o) for o in orders.values()}) == 1, f"idle gap changed the order: {orders}")
    await b.finish()


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_m0_idle_gap_does_not_reorder_grants_reads(dut):
    """The pointer moves on a grant, not with time: m0's idle gap before its next AR does not
    change the order in which m1, m2 and m0 are served."""
    await _gap_test(dut, "r")


@cocotb.test(timeout_time=20, timeout_unit="us")
async def test_m0_idle_gap_does_not_reorder_grants_writes(dut):
    """The pointer moves on a grant, not with time: m0's idle gap before its next AW does not
    change the order in which m1, m2 and m0 are served."""
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
    # m0 idle: m1 and m2 contend, the model picks the order, the second follows with no bubble.
    want = b.expected_order(kind, 1, (1, 2))
    s = b.mon.cyc
    tasks = [cocotb.start_soon(b.xfer(kind, m, 1)) for m in (1, 2)]
    await b.join(*tasks)
    b.check(b.mon.order(kind, 1, s) == want, f"order {b.mon.order(kind, 1, s)}, model {want}")
    bubble = b.mon.mgrant[kind][-1][0] - b.mon.done[kind][want[0]][-1]
    b.check(bubble == 1, f"second master granted {bubble} cycles after the first one's completion")
    await b.finish()
    dut._log.info(
        "%s lone-master latency per master %s; second granted %d cycle after first done",
        kind,
        lat,
        bubble,
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
    await b.finish()
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
