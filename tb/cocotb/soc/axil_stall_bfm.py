"""Stall-capable AXI4-Lite master + scripted slaves for the bead 8riq fabric tests.

The shared ``bfm.axi4lite_master.AXI4LiteMaster`` keeps bready/rready high and asserts AW and W
together, so it can never present backpressure or ordering.  These helpers exist so a test can
hold any ready low for a chosen number of cycles and can answer with any bresp/rresp.

Sampling model (identical to the shared BFM): a value read right after ``await RisingEdge`` is the
value the RTL sampled AT that edge, and a write made right after it takes effect for the next edge.
A handshake therefore happened at an edge where valid AND ready were both read as 1.

Nothing here weakens a check: every helper RETURNS what it observed (stall lengths, stability
violations) and the tests assert on it.
"""

from dataclasses import dataclass, field

from cocotb.triggers import RisingEdge


def _sig(dut, prefix):
    """Return a function that fetches ``<prefix><name>`` from the DUT."""
    def get(name):
        return getattr(dut, f"{prefix}{name}")
    return get


@dataclass
class Trace:
    """What a master saw while one transaction ran."""
    resp: int = 0
    data: int = 0
    aw_wait: int = 0          # edges awvalid was high before the AW handshake
    w_wait: int = 0
    ar_wait: int = 0
    resp_wait: int = 0        # edges bvalid/rvalid was high before the master took it
    resp_unstable: list = field(default_factory=list)   # violations of valid/payload stability


class StallMaster:
    """AXI4-Lite master with per-channel delays.  Signals are named ``<prefix>awvalid`` etc."""

    def __init__(self, dut, prefix, clk):
        g = _sig(dut, prefix)
        self.clk = clk
        self.awvalid, self.awready, self.awaddr, self.awprot = (
            g("awvalid"), g("awready"), g("awaddr"), g("awprot"))
        self.wvalid, self.wready, self.wdata, self.wstrb = (
            g("wvalid"), g("wready"), g("wdata"), g("wstrb"))
        self.bvalid, self.bready, self.bresp = g("bvalid"), g("bready"), g("bresp")
        self.arvalid, self.arready, self.araddr, self.arprot = (
            g("arvalid"), g("arready"), g("araddr"), g("arprot"))
        self.rvalid, self.rready, self.rdata, self.rresp = (
            g("rvalid"), g("rready"), g("rdata"), g("rresp"))
        self.idle()

    def idle(self):
        for s in (self.awvalid, self.wvalid, self.arvalid, self.bready, self.rready):
            s.value = 0
        for s in (self.awaddr, self.awprot, self.wdata, self.araddr, self.arprot):
            s.value = 0
        self.wstrb.value = 0xF

    async def write(self, addr, data, strb=0xF, aw_delay=0, w_delay=0, b_stall=0,
                    b_timeout=400):
        """One write.  AW is presented after ``aw_delay`` idle cycles, W after ``w_delay``.
        bready is held low until bvalid has been seen for ``b_stall`` edges."""
        t = Trace()
        cyc = 0
        aw_done = w_done = False
        awv = wv = False
        while not (aw_done and w_done):
            if not aw_done and not awv and cyc >= aw_delay:
                self.awvalid.value, self.awaddr.value, self.awprot.value = 1, addr, 0
                awv = True
            if not w_done and not wv and cyc >= w_delay:
                self.wvalid.value, self.wdata.value, self.wstrb.value = 1, data, strb
                wv = True
            await RisingEdge(self.clk)
            cyc += 1
            if awv and not aw_done:
                if int(self.awready.value):
                    aw_done, awv = True, False
                    self.awvalid.value = 0
                    self.awaddr.value = (1 << len(self.awaddr)) - 1   # garbage once valid is low
                else:
                    t.aw_wait += 1
            if wv and not w_done:
                if int(self.wready.value):
                    w_done, wv = True, False
                    self.wvalid.value = 0
                    self.wdata.value = 0xBAD0_BAD0      # payload is garbage once valid is low
                    self.wstrb.value = 0x0
                else:
                    t.w_wait += 1
            assert cyc < b_timeout, (
                f"write {addr:#x}: AW/W never completed (aw={aw_done} w={w_done})")
        await self._take_resp(t, self.bvalid, self.bready, self.bresp, None, b_stall, b_timeout,
                              f"write {addr:#x}: no bvalid")
        return t

    async def read(self, addr, ar_delay=0, r_stall=0, r_timeout=400):
        t = Trace()
        cyc = 0
        arv = False
        done = False
        while not done:
            if not arv and cyc >= ar_delay:
                self.arvalid.value, self.araddr.value, self.arprot.value = 1, addr, 0
                arv = True
            await RisingEdge(self.clk)
            cyc += 1
            if arv:
                if int(self.arready.value):
                    done, arv = True, False
                    self.arvalid.value = 0
                    self.araddr.value = (1 << len(self.araddr)) - 1   # garbage once valid is low
                else:
                    t.ar_wait += 1
            assert cyc < r_timeout, f"read {addr:#x}: AR never accepted"
        await self._take_resp(t, self.rvalid, self.rready, self.rresp, self.rdata, r_stall,
                              r_timeout, f"read {addr:#x}: no rvalid")
        return t

    async def _take_resp(self, t, valid, ready, resp, data, stall, timeout, msg):
        """Wait for the response channel, hold ready low for ``stall`` edges of valid, then take it.
        While held, valid and the payload must not change (AXI valid-stability rule)."""
        first = None
        seen = 0
        waited = 0
        ready.value = 0
        while True:
            await RisingEdge(self.clk)
            waited += 1
            assert waited < timeout, msg
            if not int(valid.value):
                if first is not None:
                    t.resp_unstable.append(f"valid dropped after {seen} edges without a handshake")
                    first = None
                continue
            snap = (int(resp.value), int(data.value) if data is not None else 0)
            if first is None:
                first = snap
            elif snap != first:
                t.resp_unstable.append(f"payload changed while stalled: {first} -> {snap}")
            if seen >= stall:
                # valid has been seen for `stall` edges; raise ready now, the handshake lands on
                # the NEXT edge, where valid is still required to be high and the payload equal.
                ready.value = 1
                await RisingEdge(self.clk)
                if not int(valid.value):
                    t.resp_unstable.append("valid dropped before the handshake edge")
                snap2 = (int(resp.value), int(data.value) if data is not None else 0)
                if snap2 != first:
                    t.resp_unstable.append(f"payload changed at handshake: {first} -> {snap2}")
                t.resp, t.data = snap2
                t.resp_wait = seen
                ready.value = 0
                return
            seen += 1


class ScriptedSlave:
    """Cocotb-driven AXI-Lite slave on ports ``<prefix>awvalid`` ... (named from the slave's side).

    Per-channel stall (cycles the ready is held low AFTER valid has been seen), response delays
    and response codes are plain attributes the test sets before each transaction.  The slave
    records every accepted beat and the protocol violations it saw on the master side of the link.
    """

    def __init__(self, dut, prefix, clk):
        g = _sig(dut, prefix)
        self.clk = clk
        self.awvalid, self.awready, self.awaddr = g("awvalid"), g("awready"), g("awaddr")
        self.wvalid, self.wready, self.wdata, self.wstrb = (
            g("wvalid"), g("wready"), g("wdata"), g("wstrb"))
        self.bvalid, self.bready, self.bresp = g("bvalid"), g("bready"), g("bresp")
        self.arvalid, self.arready, self.araddr = g("arvalid"), g("arready"), g("araddr")
        self.rvalid, self.rready, self.rdata, self.rresp = (
            g("rvalid"), g("rready"), g("rdata"), g("rresp"))
        # knobs
        self.aw_stall = self.w_stall = self.ar_stall = 0
        self.b_delay = self.r_delay = 0
        self.bresp_code = 0
        self.rresp_code = 0
        self.rdata_value = 0
        # observations
        self.aw_beats, self.w_beats, self.ar_beats = [], [], []
        self.violations = []
        self.b_sent = self.r_sent = 0
        self._tasks = []

    def start(self):
        import cocotb
        for s in (self.awready, self.wready, self.arready, self.bvalid, self.rvalid):
            s.value = 0
        self.bresp.value = 0
        self.rresp.value = 0
        self.rdata.value = 0
        self._tasks = [cocotb.start_soon(c) for c in
                       (self._aw(), self._w(), self._ar(), self._b(), self._r())]

    def stop(self):
        for t in self._tasks:
            t.kill()
        self._tasks = []

    async def _aw(self):
        await self._chan(self.awvalid, self.awready, lambda: self.aw_stall,
                         lambda: int(self.awaddr.value), self.aw_beats, "AW")

    async def _w(self):
        await self._chan(self.wvalid, self.wready, lambda: self.w_stall,
                         lambda: (int(self.wdata.value), int(self.wstrb.value)),
                         self.w_beats, "W")

    async def _ar(self):
        await self._chan(self.arvalid, self.arready, lambda: self.ar_stall,
                         lambda: int(self.araddr.value), self.ar_beats, "AR")

    async def _chan(self, valid, ready, stall_fn, payload, sink, name):
        while True:
            await RisingEdge(self.clk)
            if not int(valid.value):
                continue
            first = payload()
            for _ in range(stall_fn()):
                await RisingEdge(self.clk)
                if not int(valid.value):
                    self.violations.append(f"{name}: valid dropped while stalled")
                elif payload() != first:
                    self.violations.append(f"{name}: payload changed while stalled")
            ready.value = 1
            await RisingEdge(self.clk)
            if not int(valid.value):
                self.violations.append(f"{name}: valid dropped before handshake")
            elif payload() != first:
                self.violations.append(f"{name}: payload changed at handshake")
            sink.append(payload())
            ready.value = 0

    async def _b(self):
        while True:
            await RisingEdge(self.clk)
            if len(self.aw_beats) > self.b_sent and len(self.w_beats) > self.b_sent:
                for _ in range(self.b_delay):
                    await RisingEdge(self.clk)
                self.bresp.value = self.bresp_code
                self.bvalid.value = 1
                while True:
                    await RisingEdge(self.clk)
                    if int(self.bready.value):
                        break
                self.bvalid.value = 0
                self.b_sent += 1

    async def _r(self):
        while True:
            await RisingEdge(self.clk)
            if len(self.ar_beats) > self.r_sent:
                for _ in range(self.r_delay):
                    await RisingEdge(self.clk)
                self.rresp.value = self.rresp_code
                self.rdata.value = self.rdata_value
                self.rvalid.value = 1
                while True:
                    await RisingEdge(self.clk)
                    if int(self.rready.value):
                        break
                self.rvalid.value = 0
                self.r_sent += 1


class ScriptedApbSlave:
    """Cocotb-driven APB4 slave on ports ``<prefix>psel`` ... (named from the slave's side).

    Zero or more wait states, optional pslverr, programmable prdata.  Records the
    pwrite/paddr/pwdata/pstrb it saw in each ACCESS phase and checks the APB phase rules (SETUP is
    exactly one cycle with penable low, control signals hold through the wait states)."""

    def __init__(self, dut, prefix, clk):
        g = _sig(dut, prefix)
        self.clk = clk
        self.psel, self.penable, self.pwrite = g("psel"), g("penable"), g("pwrite")
        self.paddr, self.pwdata, self.pstrb = g("paddr"), g("pwdata"), g("pstrb")
        self.prdata, self.pready, self.pslverr = g("prdata"), g("pready"), g("pslverr")
        self.wait_states = 0
        self.slverr = 0
        self.rdata_value = 0
        self.accesses = []       # (pwrite, paddr, pwdata, pstrb)
        self.violations = []
        self._task = None

    def start(self):
        import cocotb
        self.pready.value = 0
        self.pslverr.value = 0
        self.prdata.value = 0
        self._task = cocotb.start_soon(self._run())

    def stop(self):
        if self._task is not None:
            self._task.kill()
            self._task = None

    async def _run(self):
        while True:
            await RisingEdge(self.clk)
            if not int(self.psel.value):
                continue
            # First psel edge must be the SETUP phase.
            if int(self.penable.value):
                self.violations.append("APB: psel rose with penable already high")
            ctrl = (int(self.pwrite.value), int(self.paddr.value),
                    int(self.pwdata.value), int(self.pstrb.value))
            self.prdata.value = self.rdata_value
            # ACCESS edge(s): penable high; hold pready low for `wait_states` of them.
            n = 0
            while True:
                await RisingEdge(self.clk)
                if not (int(self.psel.value) and int(self.penable.value)):
                    self.violations.append("APB: SETUP not followed by ACCESS")
                    break
                cur = (int(self.pwrite.value), int(self.paddr.value),
                       int(self.pwdata.value), int(self.pstrb.value))
                if cur != ctrl:
                    self.violations.append(f"APB: control changed in ACCESS {ctrl} -> {cur}")
                if n >= self.wait_states:
                    self.pready.value = 1
                    self.pslverr.value = self.slverr
                    await RisingEdge(self.clk)       # the edge where pready=1 is sampled
                    self.accesses.append(ctrl)
                    self.pready.value = 0
                    self.pslverr.value = 0
                    break
                n += 1
