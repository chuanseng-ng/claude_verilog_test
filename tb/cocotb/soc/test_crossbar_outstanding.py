"""axi4_crossbar: one master with a second request in flight.

The crossbar keeps one transaction per slave engine and the master face has no ids. A master that
issues a new AW or AR before the previous one has completed is legal AXI4. These tests drive that
case from m0 with a cycle-accurate pipelined driver and check the rule every master relies on:
every request the master saw accepted gets exactly one response, with the right data, in order.

Defect tests (expect_fail, each needs a different master behaviour):
  * a second AW/AR while the first waits for its slave is acknowledged and lost
  * two reads to two slaves in flight: the R channel of one slave hides the other
  * two writes to two slaves in flight: the W beats are shown to both slave engines

Each defect test has a control that does the same work but waits for the response before the next
request. The control passes, so the expect_fail cannot come from the driver or the checks.

Same wrapper/topology as test_crossbar.py: 3 masters x 2 slaves (s0 = ROM, s1 = SRAM).
Run together with it: ``make crossbar``.
"""

import cocotb
from axi4_fabric_bfm import OKAY, AxiMaster, AxiSlave
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

CLK_PERIOD_NS = 2
ROM_BASE = 0x0000_1000
SRAM_BASE = 0x0000_2000
BUDGET = 400            # cycles a scenario may take before the driver gives up
TAIL = 16               # quiet cycles watched after the last response for an extra one
WAIT_RESP = None        # gap value: the next request waits for the response of the previous one

# Signals shown in a cycle trace: (label, prefix, valid, ready) per channel.
_CH = (("AW", "awvalid", "awready"), ("W", "wvalid", "wready"), ("B", "bvalid", "bready"),
       ("AR", "arvalid", "arready"), ("R", "rvalid", "rready"))


async def _setup(dut, s0_kw=None, s1_kw=None):
    """Clock + reset, three idle masters, two scripted slaves. Returns (s0, s1)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
    for i in range(3):
        AxiMaster(dut, f"m{i}_", dut.clk)      # drives every master input to idle
    s0 = AxiSlave(dut, "s0_", dut.clk, **(s0_kw or {}))
    s1 = AxiSlave(dut, "s1_", dut.clk, **(s1_kw or {}))
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    s0.start()
    s1.start()
    return s0, s1


class _Tap:
    """Passive cycle trace of the m0 face and both slave faces. Row k is the state at edge k."""

    def __init__(self, dut):
        self.dut = dut
        self.rows = []
        self._task = cocotb.start_soon(self._run())

    def _sig(self, pre, name):
        return int(getattr(self.dut, f"{pre}_{name}").value)

    async def _run(self):
        while True:
            await RisingEdge(self.dut.clk)
            self.rows.append({p: {n: self._sig(p, n) for _, v, r in _CH for n in (v, r)}
                              for p in ("m0", "s0", "s1")})

    def stop(self):
        self._task.kill()

    def dump(self, lo=0, hi=None):
        out = []
        for k, row in enumerate(self.rows[lo:hi], lo):
            cols = []
            for p in ("m0", "s0", "s1"):
                cols.append(p + "[" + " ".join(f"{lab}={row[p][v]}{row[p][r]}" for lab, v, r in _CH
                                                if row[p][v] or row[p][r]) + "]")
            out.append(f"  edge {k:3d}: " + "  ".join(cols))
        return "\n".join(out)


class _Run:
    """What the master saw: one list per channel of (edge, ...) handshakes."""

    def __init__(self):
        self.aw, self.w, self.b, self.ar, self.r = [], [], [], [], []
        self.cycles = 0


async def _drive_writes(dut, reqs, *, gap, w_gap=0):
    """m0 issues the write ``reqs`` ([{addr, data}]) back to back.

    ``gap``: idle cycles between the accepted AW of one request and the AW of the next, or WAIT_RESP
    to wait for the B of the previous request. A request's W beats start the cycle after its AW is
    accepted. ``w_gap``: idle cycles between W beats. bready stays high. The driver does not assert
    anything: a request that never completes ends the run at BUDGET and the test reports it."""
    g = lambda n: getattr(dut, f"m0_{n}")   # noqa: E731
    run = _Run()
    beats = [(d, k == len(r["data"]) - 1, i)
             for i, r in enumerate(reqs) for k, d in enumerate(r["data"])]
    aw_i = w_i = w_wait = 0
    aw_at = 0
    quiet = 0
    cyc = 0
    while cyc < BUDGET and quiet < TAIL:
        may = (cyc >= aw_at) if gap is not WAIT_RESP else (len(run.b) >= aw_i)
        awv = aw_i < len(reqs) and may
        g("awvalid").value = 1 if awv else 0
        if awv:
            g("awaddr").value, g("awlen").value = reqs[aw_i]["addr"], len(reqs[aw_i]["data"]) - 1
        wv = w_i < len(beats) and beats[w_i][2] < len(run.aw) and w_wait == 0
        g("wvalid").value = 1 if wv else 0
        if wv:
            g("wdata").value, g("wlast").value = beats[w_i][0], int(beats[w_i][1])
        elif w_wait:
            w_wait -= 1
        g("bready").value = 1
        await RisingEdge(dut.clk)
        cyc += 1
        if awv and int(g("awready").value):
            run.aw.append((cyc, reqs[aw_i]["addr"]))
            aw_i += 1
            aw_at = cyc + (gap if gap is not WAIT_RESP else 0)
        if wv and int(g("wready").value):
            run.w.append((cyc, beats[w_i][0]))
            w_i += 1
            w_wait = w_gap
        if int(g("bvalid").value):
            run.b.append((cyc, int(g("bresp").value)))
        if aw_i == len(reqs) and len(run.b) >= len(reqs):
            quiet += 1
    g("awvalid").value = g("wvalid").value = 0
    run.cycles = cyc
    return run


async def _drive_reads(dut, reqs, *, gap):
    """m0 issues the reads ``reqs`` ([{addr, n}]) back to back. ``gap`` as in _drive_writes
    (WAIT_RESP waits for RLAST of the previous read). rready stays high."""
    g = lambda n: getattr(dut, f"m0_{n}")   # noqa: E731
    run = _Run()
    ar_i = 0
    ar_at = 0
    quiet = 0
    cyc = 0
    while cyc < BUDGET and quiet < TAIL:
        lasts = sum(b[3] for b in run.r)
        may = (cyc >= ar_at) if gap is not WAIT_RESP else (lasts >= ar_i)
        arv = ar_i < len(reqs) and may
        g("arvalid").value = 1 if arv else 0
        if arv:
            g("araddr").value, g("arlen").value = reqs[ar_i]["addr"], reqs[ar_i]["n"] - 1
        g("rready").value = 1
        await RisingEdge(dut.clk)
        cyc += 1
        if arv and int(g("arready").value):
            run.ar.append((cyc, reqs[ar_i]["addr"]))
            ar_i += 1
            ar_at = cyc + (gap if gap is not WAIT_RESP else 0)
        if int(g("rvalid").value):
            run.r.append((cyc, int(g("rdata").value), int(g("rresp").value), int(g("rlast").value)))
        if ar_i == len(reqs) and sum(b[3] for b in run.r) >= len(reqs):
            quiet += 1
    g("arvalid").value = 0
    run.cycles = cyc
    return run


def _write_problems(run, reqs):
    """Every accepted AW has one B, and each slave got exactly its own AW and W beats."""
    bad = []
    if len(run.aw) != len(reqs):
        bad.append(f"master saw {len(run.aw)} of {len(reqs)} AW accepted")
    if len(run.b) != len(run.aw):
        bad.append(f"{len(run.aw)} AW accepted at edges {[c for c, _ in run.aw]} but "
                   f"{len(run.b)} B seen at edges {[c for c, _ in run.b]}")
    if any(resp != OKAY for _, resp in run.b):
        bad.append(f"B responses {[r for _, r in run.b]}")
    for slave, label in ((reqs[0]["slave"], "first"), (reqs[1]["slave"], "second")):
        mine = [r for r in reqs if r["slave"] is slave]
        want_aw = [r["addr"] for r in mine]
        want_w = [d for r in mine for d in r["data"]]
        got_aw = [a["addr"] for a in slave.aw_log]
        got_w = [w["data"] for w in slave.w_log]
        if got_aw != want_aw:
            bad.append(f"{label} request's slave got AW {[hex(a) for a in got_aw]}, "
                       f"wanted {[hex(a) for a in want_aw]}")
        if got_w != want_w:
            bad.append(f"{label} request's slave got W {[hex(d) for d in got_w]}, "
                       f"wanted {[hex(d) for d in want_w]}")
        if slave.viol:
            bad.append(f"slave protocol violations {slave.viol}")
    return bad


def _read_problems(run, reqs):
    """Every accepted AR gets its own beats once, in request order, RLAST on each last beat."""
    bad = []
    want = []
    for r in reqs:
        want += [(r["slave"].mem[r["addr"] + 4 * k], int(k == r["n"] - 1)) for k in range(r["n"])]
    got = [(d, last) for _, d, _, last in run.r]
    if len(run.ar) != len(reqs):
        bad.append(f"master saw {len(run.ar)} of {len(reqs)} AR accepted")
    if got != want:
        bad.append(f"AR accepted at edges {[c for c, _ in run.ar]}; R beats "
                   f"{[(hex(d), last) for d, last in got]} at edges {[c for c, *_ in run.r]}, "
                   f"wanted {[(hex(d), last) for d, last in want]}")
    if any(r[2] != OKAY for r in run.r):
        bad.append(f"R responses {[r[2] for r in run.r]}")
    for slave in {id(r["slave"]): r["slave"] for r in reqs}.values():
        want_ar = [r["addr"] for r in reqs if r["slave"] is slave]
        got_ar = [a["addr"] for a in slave.ar_log]
        if got_ar != want_ar:
            bad.append(f"slave got AR {[hex(a) for a in got_ar]}, "
                       f"wanted {[hex(a) for a in want_ar]}")
        if slave.viol:
            bad.append(f"slave protocol violations {slave.viol}")
    return bad


def _verdict(dut, tap, problems, run):
    tap.stop()
    if problems:
        dut._log.info("cycle trace (edge: m0 face, s0 face, s1 face; xy = valid,ready):\n"
                      + tap.dump(0, run.cycles))
    assert not problems, "; ".join(problems)


# ───────────────────────── scenario setup shared by defect test and control ───────────────────
def _fill(slave, base, tag, n=8):
    for k in range(n):
        slave.mem[base + 4 * k] = (tag << 16) + k


async def _same_slave_writes(dut, gap):
    s0, s1 = await _setup(dut, s1_kw=dict(aw_delay=4))
    reqs = [dict(addr=SRAM_BASE + 0x10, data=[0x1111_0001, 0x1111_0002], slave=s1),
            dict(addr=SRAM_BASE + 0x50, data=[0x2222_0001, 0x2222_0002], slave=s1)]
    tap = _Tap(dut)
    run = await _drive_writes(dut, reqs, gap=gap)
    _verdict(dut, tap, _write_problems(run, reqs), run)


async def _same_slave_reads(dut, gap):
    s0, s1 = await _setup(dut, s1_kw=dict(ar_delay=4))
    _fill(s1, SRAM_BASE + 0x40, 0xAA01)
    _fill(s1, SRAM_BASE + 0x80, 0xAA02)
    reqs = [dict(addr=SRAM_BASE + 0x40, n=2, slave=s1), dict(addr=SRAM_BASE + 0x80, n=2, slave=s1)]
    tap = _Tap(dut)
    run = await _drive_reads(dut, reqs, gap=gap)
    _verdict(dut, tap, _read_problems(run, reqs), run)


async def _cross_slave_reads(dut, gap):
    s0, s1 = await _setup(dut, s0_kw=dict(r_delay=0), s1_kw=dict(r_delay=2))
    _fill(s0, ROM_BASE + 0x20, 0xB001, 4)
    _fill(s1, SRAM_BASE + 0x40, 0xB002, 4)
    reqs = [dict(addr=ROM_BASE + 0x20, n=4, slave=s0), dict(addr=SRAM_BASE + 0x40, n=4, slave=s1)]
    tap = _Tap(dut)
    run = await _drive_reads(dut, reqs, gap=gap)
    _verdict(dut, tap, _read_problems(run, reqs), run)


async def _cross_slave_writes(dut, gap):
    s0, s1 = await _setup(dut)
    reqs = [dict(addr=ROM_BASE + 0x20, data=[0xC001_0000 + k for k in range(4)], slave=s0),
            dict(addr=SRAM_BASE + 0x40, data=[0xC002_0000 + k for k in range(4)], slave=s1)]
    tap = _Tap(dut)
    run = await _drive_writes(dut, reqs, gap=gap, w_gap=2)
    _verdict(dut, tap, _write_problems(run, reqs), run)


# ───────────────────────────────── defect tests and controls ──────────────────────────────────
@cocotb.test(expect_fail=True)
async def test_defect_second_aw_while_first_waits(dut):
    """Defect: while a granted write waits for its slave, the crossbar shows the slave's AWREADY to
    the granted master (W_AW arm of slv_awready). A second AW issued in that window is acknowledged
    and never forwarded, so it gets no response. Asserts: every accepted AW gets one B, and the
    slave gets both AWs and W bursts. expect_fail until the crossbar holds AWREADY low in that
    window."""
    await _same_slave_writes(dut, gap=0)


@cocotb.test()
async def test_control_second_aw_after_first_completes(dut):
    """Control of the test above: the same two writes to the same slow slave, the second AW only
    after the first B. Both complete with their own data."""
    await _same_slave_writes(dut, gap=WAIT_RESP)


@cocotb.test(expect_fail=True)
async def test_defect_second_ar_while_first_waits(dut):
    """Defect: while a granted read waits for its slave, the crossbar shows the slave's ARREADY to
    the granted master (R_AR arm of slv_arready). A second AR issued in that window is acknowledged
    and never forwarded, so it gets no R beats. Asserts: every accepted AR gets its own R beats.
    expect_fail until the crossbar holds ARREADY low in that window."""
    await _same_slave_reads(dut, gap=0)


@cocotb.test()
async def test_control_second_ar_after_first_completes(dut):
    """Control of the test above: the same two reads to the same slow slave, the second AR only
    after RLAST of the first. Both return their own data."""
    await _same_slave_reads(dut, gap=WAIT_RESP)


@cocotb.test(expect_fail=True)
async def test_defect_two_reads_two_slaves_in_flight(dut):
    """Defect: one master with a read in flight to s0 and a second to s1 gets the R channel of s1
    only. The master-side mux assigns slv_rvalid/rdata per slave in turn, so the last slave in
    R_DATA overrides the other while both rready are high. Asserts: the R beats are the burst of
    s0 and then the burst of s1, once each. expect_fail until the R mux is steered by an in-order
    queue."""
    await _cross_slave_reads(dut, gap=2)


@cocotb.test()
async def test_control_two_reads_two_slaves_in_order(dut):
    """Control of the test above: the same two reads to two slaves, the second AR only after RLAST
    of the first. The beats arrive in order and intact."""
    await _cross_slave_reads(dut, gap=WAIT_RESP)


@cocotb.test(expect_fail=True)
async def test_defect_two_writes_two_slaves_in_flight(dut):
    """Defect: one master with a write in flight to s0 and a second to s1. Both slave write engines
    are in W_DATA and both take their W data from the one master (m_wdata[wsel]), so each slave gets
    the beats of the other burst too. Asserts: s0 gets exactly the W beats of burst 1 and s1 exactly
    those of burst 2, and both B arrive. expect_fail until W beats are steered per AW."""
    await _cross_slave_writes(dut, gap=2)


@cocotb.test()
async def test_control_two_writes_two_slaves_in_order(dut):
    """Control of the test above: the same two writes to two slaves, the second AW only after the
    first B. Each slave gets exactly its own W beats."""
    await _cross_slave_writes(dut, gap=WAIT_RESP)
