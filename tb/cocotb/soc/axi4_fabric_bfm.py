"""Cycle-accurate AXI4 / AXI4-Lite BFMs with stalls, scripted responses and protocol checks (bead ej6j).

The shared ``bfm.axi4_master.AXI4Master`` and ``AXI4SlaveModel`` always answer OKAY, keep bready/rready
high and cannot hold a ready low for a chosen number of cycles, so they can never reach the error
responses, stall arms and multi-beat bridge paths bead ej6j lists.  These helpers can.

Sampling model (same as ``axil_stall_bfm.py`` from bead 8riq): a value read right after
``await RisingEdge`` is the value the RTL sampled AT that edge, and a write made right after it takes
effect for the next edge.  A handshake happened at an edge where valid AND ready were both read as 1.

Nothing here weakens a check.  Every helper RETURNS what it observed (stall lengths, handshake
cycles, per-beat responses) and records protocol violations (valid/payload instability, early B,
rlast misplacement) in ``viol`` lists the tests assert are empty.
"""

from dataclasses import dataclass, field

from cocotb.triggers import RisingEdge

OKAY, EXOKAY, SLVERR, DECERR = 0, 1, 2, 3
BURST_FIXED, BURST_INCR, BURST_WRAP = 0, 1, 2
GARBAGE = 0xBAD0_BAD0


def _get(dut, prefix):
    return lambda name: getattr(dut, f"{prefix}{name}")


# ───────────────────────────── traces ────────────────────────────────────────
@dataclass
class WriteTrace:
    bresp: int = -1
    bid: int = -1
    aw_cycle: int = -1
    w_cycles: list = field(default_factory=list)   # edge index of every W handshake
    first_bvalid: int = -1
    b_cycle: int = -1
    aw_wait: int = 0
    b_wait: int = 0
    viol: list = field(default_factory=list)


@dataclass
class ReadTrace:
    beats: list = field(default_factory=list)      # (data, resp, last, id) per accepted R beat
    ar_cycle: int = -1
    r_cycles: list = field(default_factory=list)
    ar_wait: int = 0
    viol: list = field(default_factory=list)

    @property
    def data(self):
        return [b[0] for b in self.beats]

    @property
    def resps(self):
        return [b[1] for b in self.beats]


# ───────────────────────────── AXI4 master ───────────────────────────────────
class AxiMaster:
    """AXI4 master.  ``prefix`` is the full signal prefix, e.g. ``"m0_"`` or ``"s_"``."""

    def __init__(self, dut, prefix, clk):
        self.g = _get(dut, prefix)
        self.clk = clk
        self.has_id = hasattr(dut, f"{prefix}awid")
        self.has_rid = hasattr(dut, f"{prefix}rid")     # the crossbar wrapper's master face has no ids
        self.has_bid = hasattr(dut, f"{prefix}bid")
        self.idle()

    def idle(self):
        self._idle_w()
        self._idle_r()

    def _idle_w(self):
        g = self.g
        for n in ("awvalid", "wvalid", "bready", "wlast"):
            g(n).value = 0
        g("awaddr").value = g("wdata").value = 0
        g("awlen").value = 0
        g("awsize").value = 2
        g("awburst").value = BURST_INCR
        g("wstrb").value = 0xF
        if self.has_id:
            g("awid").value = 0

    def _idle_r(self):
        g = self.g
        for n in ("arvalid", "rready"):
            g(n).value = 0
        g("araddr").value = 0
        g("arlen").value = 0
        g("arsize").value = 2
        g("arburst").value = BURST_INCR
        if self.has_id:
            g("arid").value = 0

    async def write(self, addr, data, *, wid=0, awlen=None, burst=BURST_INCR, aw_delay=0,
                    w_before_aw=False, w_gaps=None, b_stall=0, strb=0xF, timeout=3000):
        """One write burst.  ``w_gaps[i]`` idle cycles before beat i; ``b_stall`` edges of bvalid
        seen with bready held low (bready is high from the start when 0)."""
        g, t = self.g, WriteTrace()
        n = len(data)
        awlen = n - 1 if awlen is None else awlen
        gaps = list(w_gaps) if w_gaps is not None else [0] * n
        cyc = 0
        aw_done = aw_pres = w_pres = False
        beat = 0
        gap_left = gaps[0] if n else 0
        b_seen = 0
        first_snap = None
        while True:
            # ── drive (python-side copies: a readback of a just-written cocotb signal is stale) ──
            awv = wv = 0
            if not aw_done and (aw_pres or cyc >= aw_delay):
                g("awvalid").value, g("awaddr").value, g("awlen").value = 1, addr, awlen
                g("awburst").value, g("awsize").value = burst, 2
                if self.has_id:
                    g("awid").value = wid
                aw_pres = True
                awv = 1
            else:
                g("awvalid").value = 0
                if aw_done:
                    g("awaddr").value = 0xFFFF_FFFF
            if beat < n and (aw_done or w_before_aw) and (w_pres or gap_left == 0):
                g("wvalid").value, g("wdata").value, g("wstrb").value = 1, data[beat], strb
                g("wlast").value = 1 if beat == n - 1 else 0
                w_pres = True
                wv = 1
            else:
                g("wvalid").value, g("wdata").value, g("wlast").value = 0, GARBAGE, 0
                if beat < n and (aw_done or w_before_aw) and gap_left > 0:
                    gap_left -= 1
            brdy = 1 if b_seen >= b_stall else 0
            g("bready").value = brdy
            # ── clock ──
            await RisingEdge(self.clk)
            cyc += 1
            assert cyc < timeout, f"write {addr:#x}: no B after {cyc} cycles (aw={aw_done} beat={beat})"
            if awv:
                if int(g("awready").value):
                    aw_done, aw_pres, t.aw_cycle = True, False, cyc
                else:
                    t.aw_wait += 1
            if wv and int(g("wready").value):
                t.w_cycles.append(cyc)
                beat += 1
                w_pres = False
                gap_left = gaps[beat] if beat < n else 0
            if int(g("bvalid").value):
                snap = (int(g("bresp").value), int(g("bid").value) if self.has_bid else 0)
                if t.first_bvalid < 0:
                    t.first_bvalid = cyc
                if beat < n:
                    t.viol.append(f"bvalid at edge {cyc} before all {n} W beats were accepted")
                if first_snap is not None and snap != first_snap:
                    t.viol.append(f"B payload changed while stalled {first_snap}->{snap}")
                first_snap = snap
                if brdy:
                    t.bresp, t.bid, t.b_cycle = snap[0], snap[1], cyc
                    break
                b_seen += 1
                t.b_wait += 1
            elif first_snap is not None:
                t.viol.append("bvalid dropped without a handshake")
                first_snap = None
        self._idle_w()
        return t

    async def read(self, addr, n, *, rid=0, arlen=None, burst=BURST_INCR, ar_delay=0,
                   r_stalls=0, pulse=False, timeout=3000):
        """One read burst of ``n`` beats.  ``r_stalls`` (int or per-beat list): edges of rvalid seen
        with rready held low before each beat is taken.  ``pulse``: arvalid is high for exactly one
        cycle (GPU style) -- the DUT must accept it in that cycle."""
        g, t = self.g, ReadTrace()
        arlen = n - 1 if arlen is None else arlen
        stalls = list(r_stalls) if isinstance(r_stalls, (list, tuple)) else [r_stalls] * n
        cyc = 0
        ar_done = ar_pres = False
        beat = 0
        seen = 0
        first_snap = None
        while True:
            arv = 0
            if not ar_done and (ar_pres or cyc >= ar_delay):
                g("arvalid").value, g("araddr").value, g("arlen").value = 1, addr, arlen
                g("arburst").value, g("arsize").value = burst, 2
                if self.has_id:
                    g("arid").value = rid
                ar_pres = True
                arv = 1
            else:
                g("arvalid").value = 0
                if ar_done:
                    g("araddr").value = 0xFFFF_FFFF
            cur_stall = stalls[beat] if beat < len(stalls) else 0
            rrdy = 1 if seen >= cur_stall else 0
            g("rready").value = rrdy
            await RisingEdge(self.clk)
            cyc += 1
            assert cyc < timeout, f"read {addr:#x}: only {beat}/{n} beats after {cyc} cycles"
            if arv:
                if int(g("arready").value):
                    ar_done, ar_pres, t.ar_cycle = True, False, cyc
                elif pulse:
                    raise AssertionError(f"read {addr:#x}: one-cycle ARVALID pulse was not accepted")
                else:
                    t.ar_wait += 1
            if int(g("rvalid").value):
                snap = (int(g("rdata").value), int(g("rresp").value), int(g("rlast").value),
                        int(g("rid").value) if self.has_rid else 0)
                if first_snap is not None and snap != first_snap:
                    t.viol.append(f"R payload changed while stalled {first_snap}->{snap}")
                first_snap = snap
                if rrdy:
                    t.beats.append(snap)
                    t.r_cycles.append(cyc)
                    exp_last = 1 if beat == arlen else 0
                    if snap[2] != exp_last:
                        t.viol.append(f"beat {beat}: rlast={snap[2]} expected {exp_last}")
                    beat += 1
                    seen = 0
                    first_snap = None
                    if snap[2] or beat > arlen:
                        break
                else:
                    seen += 1
            elif first_snap is not None:
                t.viol.append("rvalid dropped without a handshake")
                first_snap = None
        self._idle_r()
        return t


# ───────────────────────────── AXI4 slave ────────────────────────────────────
class AxiSlave:
    """Scripted AXI4 slave.  ``resp_fn(kind, addr)`` -> response (``kind`` is "w" for the burst base
    address, "r" for each read beat address).  Ready delays are in edges of the matching valid seen."""

    def __init__(self, dut, prefix, clk, mem=None, *, aw_delay=0, w_delay=0, b_delay=0, ar_delay=0,
                 r_delay=0, resp_fn=None):
        self.g, self.clk = _get(dut, prefix), clk
        self.mem = mem if mem is not None else {}
        self.aw_delay, self.w_delay, self.b_delay = aw_delay, w_delay, b_delay
        self.ar_delay, self.r_delay = ar_delay, r_delay
        self.resp_fn = resp_fn or (lambda kind, addr: OKAY)
        self.aw_log, self.w_log, self.ar_log, self.viol = [], [], [], []
        self.cyc = 0
        self.arvalid_edges = 0     # edges arvalid was sampled high
        self.awvalid_edges = 0
        for n in ("awready", "wready", "bvalid", "arready", "rvalid", "rlast"):
            self.g(n).value = 0
        for n in ("bid", "bresp", "rid", "rresp", "rdata"):
            self.g(n).value = 0
        self._task = None

    def start(self):
        import cocotb
        self._task = cocotb.start_soon(self._run())

    def stop(self):
        if self._task is not None:
            self._task.kill()

    async def _run(self):
        g = self.g
        wst, rst = "AW", "AR"
        aw_ready = 1 if self.aw_delay == 0 else 0
        w_ready = b_valid = ar_ready = r_valid = 0
        ar_ready = 1 if self.ar_delay == 0 else 0
        aw_seen = w_seen = ar_seen = 0
        b_wait = r_wait = 0
        wa = {}
        ra = {}
        beat = rbeat = 0
        aw_snap = ar_snap = None
        g("awready").value, g("arready").value = aw_ready, ar_ready
        while True:
            await RisingEdge(self.clk)
            self.cyc += 1
            awv, wv, brdy = int(g("awvalid").value), int(g("wvalid").value), int(g("bready").value)
            arv, rrdy = int(g("arvalid").value), int(g("rready").value)
            if arv:
                self.arvalid_edges += 1
            if awv:
                self.awvalid_edges += 1
            # ── write engine ──
            if wst == "AW":
                if awv:
                    snap = (int(g("awid").value), int(g("awaddr").value), int(g("awlen").value),
                            int(g("awburst").value))
                    if aw_snap is not None and snap != aw_snap:
                        self.viol.append(f"AW payload changed while awvalid&!awready {aw_snap}->{snap}")
                    aw_snap = snap
                    if aw_ready:
                        wa = dict(id=snap[0], addr=snap[1], len=snap[2], burst=snap[3], cycle=self.cyc)
                        self.aw_log.append(wa)
                        aw_ready, aw_seen, aw_snap = 0, 0, None
                        wst, beat = "W", 0
                        w_ready, w_seen = (1 if self.w_delay == 0 else 0), 0
                    else:
                        aw_seen += 1
                        if aw_seen >= self.aw_delay:
                            aw_ready = 1
                elif aw_snap is not None:
                    self.viol.append("awvalid dropped before awready")
                    aw_snap = None
            elif wst == "W":
                if wv:
                    if w_ready:
                        d, s, last = int(g("wdata").value), int(g("wstrb").value), int(g("wlast").value)
                        self.w_log.append(dict(data=d, strb=s, last=last, cycle=self.cyc, beat=beat))
                        ok = self.resp_fn("w", wa["addr"]) == OKAY
                        a = wa["addr"] + (0 if wa["burst"] == BURST_FIXED else 4 * beat)
                        if ok:
                            cur = self.mem.get(a, 0)
                            val = 0
                            for b in range(4):
                                src = d if (s >> b) & 1 else cur
                                val |= ((src >> (8 * b)) & 0xFF) << (8 * b)
                            self.mem[a] = val
                        beat += 1
                        w_ready, w_seen = 0, 0
                        if beat > wa["len"]:
                            if not last:
                                self.viol.append("wlast missing on the final W beat")
                            wst, b_wait = "B", self.b_delay
                        else:
                            if last:
                                self.viol.append(f"wlast early at beat {beat - 1}")
                            w_ready = 1 if self.w_delay == 0 else 0
                    else:
                        w_seen += 1
                        if w_seen >= self.w_delay:
                            w_ready = 1
            elif wst == "B":
                if b_valid:
                    if brdy:
                        b_valid, wst = 0, "AW"
                        aw_ready = 1 if self.aw_delay == 0 else 0
                elif b_wait > 0:
                    b_wait -= 1
                if wst == "B" and not b_valid and b_wait == 0:
                    b_valid = 1
                    g("bid").value = wa["id"]
                    g("bresp").value = self.resp_fn("w", wa["addr"])
            g("awready").value = aw_ready if wst == "AW" else 0
            g("wready").value = w_ready if wst == "W" else 0
            g("bvalid").value = b_valid if wst == "B" else 0
            # ── read engine ──
            if rst == "AR":
                if arv:
                    snap = (int(g("arid").value), int(g("araddr").value), int(g("arlen").value),
                            int(g("arburst").value))
                    if ar_snap is not None and snap != ar_snap:
                        self.viol.append(f"AR payload changed while arvalid&!arready {ar_snap}->{snap}")
                    ar_snap = snap
                    if ar_ready:
                        ra = dict(id=snap[0], addr=snap[1], len=snap[2], burst=snap[3], cycle=self.cyc)
                        self.ar_log.append(ra)
                        ar_ready, ar_seen, ar_snap = 0, 0, None
                        rst, rbeat, r_wait, r_valid = "R", 0, self.r_delay, 0
                    else:
                        ar_seen += 1
                        if ar_seen >= self.ar_delay:
                            ar_ready = 1
                elif ar_snap is not None:
                    self.viol.append("arvalid dropped before arready")
                    ar_snap = None
            elif rst == "R":
                if r_valid and rrdy:
                    r_valid = 0
                    rbeat += 1
                    if rbeat > ra["len"]:
                        rst = "AR"
                        ar_ready = 1 if self.ar_delay == 0 else 0
                    else:
                        r_wait = self.r_delay
                if rst == "R" and not r_valid:
                    if r_wait > 0:
                        r_wait -= 1
                    if r_wait == 0:
                        r_valid = 1
                        a = ra["addr"] + (0 if ra["burst"] == BURST_FIXED else 4 * rbeat)
                        g("rid").value = ra["id"]
                        g("rdata").value = self.mem.get(a, a ^ 0x5A5A_0000)
                        g("rresp").value = self.resp_fn("r", a)
                        g("rlast").value = 1 if rbeat == ra["len"] else 0
            g("arready").value = ar_ready if rst == "AR" else 0
            g("rvalid").value = r_valid if rst == "R" else 0


# ───────────────────────────── AXI4-Lite slave ───────────────────────────────
class AxiLiteSlave:
    """Scripted AXI4-Lite slave (AW and W are accepted independently, B after both).

    ``bresps`` / ``rresps`` are consumed one per transaction (default OKAY).  Protocol checks: AW/AR
    payload stable while valid&!ready, and no new AW/AR before the previous B/R has completed."""

    def __init__(self, dut, prefix, clk, mem=None, *, aw_delay=0, w_delay=0, b_delay=0, ar_delay=0,
                 r_delay=0, bresps=None, rresps=None):
        self.g, self.clk = _get(dut, prefix), clk
        self.mem = mem if mem is not None else {}
        self.aw_delay, self.w_delay, self.b_delay = aw_delay, w_delay, b_delay
        self.ar_delay, self.r_delay = ar_delay, r_delay
        self.bresps = list(bresps or [])
        self.rresps = list(rresps or [])
        self.aw_log, self.w_log, self.ar_log, self.viol = [], [], [], []
        self.cyc = 0
        self.max_w_outstanding = 0
        for n in ("awready", "wready", "bvalid", "arready", "rvalid"):
            self.g(n).value = 0
        for n in ("bresp", "rresp", "rdata"):
            self.g(n).value = 0
        self._task = None

    def start(self):
        import cocotb
        self._task = cocotb.start_soon(self._run())

    def stop(self):
        if self._task is not None:
            self._task.kill()

    async def _run(self):
        g = self.g
        aw_got = w_got = False
        aw_addr = 0
        aw_seen = w_seen = ar_seen = 0
        aw_snap = w_snap = ar_snap = None
        b_valid = False
        b_wait = 0
        rst = "AR"
        r_valid = False
        r_wait = 0
        ar_addr = 0
        aw_ready = 1 if self.aw_delay == 0 else 0
        w_ready = 1 if self.w_delay == 0 else 0
        ar_ready = 1 if self.ar_delay == 0 else 0
        w_data = w_strb = 0
        while True:
            g("awready").value = 1 if (aw_ready and not aw_got and not b_valid) else 0
            g("wready").value = 1 if (w_ready and not w_got and not b_valid) else 0
            g("arready").value = 1 if (ar_ready and rst == "AR") else 0
            await RisingEdge(self.clk)
            self.cyc += 1
            awv, wv, brdy = int(g("awvalid").value), int(g("wvalid").value), int(g("bready").value)
            arv, rrdy = int(g("arvalid").value), int(g("rready").value)
            # ── AW ──
            if awv:
                if aw_got or b_valid:
                    self.viol.append(f"awvalid at edge {self.cyc} while previous write still in flight")
                snap = int(g("awaddr").value)
                if aw_snap is not None and snap != aw_snap:
                    self.viol.append("AXI-Lite awaddr changed while awvalid&!awready")
                aw_snap = snap
                if aw_ready and not aw_got and not b_valid:
                    aw_got, aw_addr, aw_snap, aw_seen = True, snap, None, 0
                    self.aw_log.append(dict(addr=snap, cycle=self.cyc))
                else:
                    aw_seen += 1
                    if aw_seen >= self.aw_delay:
                        aw_ready = 1
            elif aw_snap is not None:
                self.viol.append("AXI-Lite awvalid dropped before awready")
                aw_snap = None
            # ── W ──
            if wv:
                snap = (int(g("wdata").value), int(g("wstrb").value))
                if w_snap is not None and snap != w_snap:
                    self.viol.append("AXI-Lite wdata/wstrb changed while wvalid&!wready")
                w_snap = snap
                if w_ready and not w_got and not b_valid:
                    w_got, w_data, w_strb, w_snap, w_seen = True, snap[0], snap[1], None, 0
                    self.w_log.append(dict(data=snap[0], strb=snap[1], cycle=self.cyc))
                else:
                    w_seen += 1
                    if w_seen >= self.w_delay:
                        w_ready = 1
            elif w_snap is not None:
                self.viol.append("AXI-Lite wvalid dropped before wready")
                w_snap = None
            # ── B ──
            if b_valid and brdy:
                b_valid = False
                aw_ready = 1 if self.aw_delay == 0 else 0
                w_ready = 1 if self.w_delay == 0 else 0
            if aw_got and w_got and not b_valid:
                if b_wait == 0:
                    b_wait = self.b_delay + 1
                b_wait -= 1
                if b_wait == 0:
                    resp = self.bresps.pop(0) if self.bresps else OKAY
                    if resp == OKAY:
                        cur = self.mem.get(aw_addr, 0)
                        val = 0
                        for b in range(4):
                            src = w_data if (w_strb >> b) & 1 else cur
                            val |= ((src >> (8 * b)) & 0xFF) << (8 * b)
                        self.mem[aw_addr] = val
                    g("bresp").value = resp
                    b_valid, aw_got, w_got = True, False, False
            g("bvalid").value = 1 if b_valid else 0
            # ── AR / R ──
            if rst == "AR":
                if arv:
                    snap = int(g("araddr").value)
                    if ar_snap is not None and snap != ar_snap:
                        self.viol.append("AXI-Lite araddr changed while arvalid&!arready")
                    ar_snap = snap
                    if ar_ready:
                        ar_addr, ar_snap, ar_seen = snap, None, 0
                        self.ar_log.append(dict(addr=snap, cycle=self.cyc))
                        rst, r_valid, r_wait = "R", False, self.r_delay
                    else:
                        ar_seen += 1
                        if ar_seen >= self.ar_delay:
                            ar_ready = 1
                elif ar_snap is not None:
                    self.viol.append("AXI-Lite arvalid dropped before arready")
                    ar_snap = None
            elif rst == "R":
                if arv:
                    self.viol.append(f"arvalid at edge {self.cyc} while previous read still in flight")
                if r_valid and rrdy:
                    r_valid, rst = False, "AR"
                    ar_ready = 1 if self.ar_delay == 0 else 0
                elif not r_valid:
                    if r_wait > 0:
                        r_wait -= 1
                    if r_wait == 0:
                        r_valid = True
                        g("rdata").value = self.mem.get(ar_addr, ar_addr ^ 0xA5A5_0000)
                        g("rresp").value = self.rresps.pop(0) if self.rresps else OKAY
            g("rvalid").value = 1 if r_valid else 0


# ───────────────────────────── passive watcher ───────────────────────────────
class Watch:
    """Counts edges at which any of the named signals was high (``"leak"`` checks)."""

    def __init__(self, dut, names, clk):
        import cocotb
        self.sigs = [(n, getattr(dut, n)) for n in names]
        self.clk = clk
        self.hits = []
        self._task = cocotb.start_soon(self._run())

    async def _run(self):
        while True:
            await RisingEdge(self.clk)
            for n, s in self.sigs:
                if int(s.value):
                    self.hits.append(n)

    def stop(self):
        self._task.kill()
