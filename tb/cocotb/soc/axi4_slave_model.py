"""
Behavioral AXI4 slave model for cocotb (Phase 5 crossbar testbench).

A burst-capable AXI4 slave with a sparse word memory.  Echoes the id from
AW/AR onto B/R so response steering can be checked.  Supports configurable
ready/valid delays to exercise crossbar backpressure handling.

Signal naming: <prefix>_<channelfield>, e.g. prefix "s0" -> s0_awaddr.
INCR bursts of 32-bit beats only (this SoC's geometry).

Handshake conventions
---------------------
cocotb enforces that signal writes happen only in the ACTIVE phase (triggered
by RisingEdge), never in the ReadOnly phase.  The pattern used throughout:

  READY channels (AW / W / AR)
    1. Assert ready (active phase — always the first statement after either
       a RisingEdge trigger or a break from a previous ReadOnly-based loop).
    2. Poll: `await ReadOnly(); if valid: break; await RisingEdge`.
    3. After the while loop (still in ReadOnly context), `await RisingEdge`
       so the deassert and any next-state writes are in the active phase.

  VALID channels (B / R)
    1. Assert valid + data (active phase).
    2. Poll: `await ReadOnly(); if ready: break; await RisingEdge`.
       (Matches the BFM, which also samples starting at the current ReadOnly.)
    3. After the while loop, `await RisingEdge` before deasserting valid.

  Multi-beat R loop
    Between beats, we are in ReadOnly context (the previous beat's rready
    handshake broke from a ReadOnly).  Therefore the FIRST thing each new
    beat does is `await RisingEdge` to re-enter the active phase before
    driving rdata / rvalid / rlast.  For the first beat (i=0) this is
    harmless (just one extra idle cycle).
"""

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

RESP_OKAY = 0b00


class AXI4SlaveModel:
    def __init__(self, dut, prefix, clock, mem=None,
                 aw_delay=0, w_delay=0, b_delay=0,
                 ar_delay=0, r_delay=0):
        self.dut = dut
        self.clock = clock
        self.p = prefix
        self.mem = mem if mem is not None else {}
        self.aw_delay = aw_delay
        self.w_delay = w_delay
        self.b_delay = b_delay
        self.ar_delay = ar_delay
        self.r_delay = r_delay

        s = self._sig
        s("awready").value = 0
        s("wready").value = 0
        s("bid").value = 0
        s("bresp").value = RESP_OKAY
        s("bvalid").value = 0
        s("arready").value = 0
        s("rid").value = 0
        s("rdata").value = 0
        s("rresp").value = RESP_OKAY
        s("rlast").value = 0
        s("rvalid").value = 0

    def _sig(self, field):
        return getattr(self.dut, f"{self.p}_{field}")

    def start(self):
        cocotb.start_soon(self._write_loop())
        cocotb.start_soon(self._read_loop())

    async def _write_loop(self):
        s = self._sig
        while True:
            # ── AW: assert awready, poll for awvalid ──────────────────────────
            for _ in range(self.aw_delay):
                await RisingEdge(self.clock)
            s("awready").value = 1
            awid = addr = awlen = 0
            while True:
                await ReadOnly()
                if s("awvalid").value:
                    awid  = int(s("awid").value)
                    addr  = int(s("awaddr").value)
                    awlen = int(s("awlen").value)
                    break
                await RisingEdge(self.clock)
            # Re-enter active phase before any signal writes.
            await RisingEdge(self.clock)
            s("awready").value = 0

            # ── W: per beat, assert wready, poll for wvalid ───────────────────
            for i in range(awlen + 1):
                for _ in range(self.w_delay):
                    await RisingEdge(self.clock)
                s("wready").value = 1
                wdata = wstrb = 0
                while True:
                    await ReadOnly()
                    if s("wvalid").value:
                        wdata = int(s("wdata").value)
                        wstrb = int(s("wstrb").value)
                        break
                    await RisingEdge(self.clock)
                # Re-enter active phase; deassert wready, write beat to memory.
                await RisingEdge(self.clock)
                s("wready").value = 0
                cur = self.mem.get(addr + i * 4, 0)
                val = 0
                for b in range(4):
                    src = wdata if (wstrb >> b) & 1 else cur
                    val |= ((src >> (b * 8)) & 0xFF) << (b * 8)
                self.mem[addr + i * 4] = val
                # Next beat or B phase: we are now in the active phase — OK
                # to fall straight into the next for-loop iteration and
                # call wready=1 (active write is safe here).

            # ── B: assert bvalid, poll for bready ─────────────────────────────
            # We arrive here in the active phase (from the last W beat's
            # `await RisingEdge` that deasserted wready).
            for _ in range(self.b_delay):
                await RisingEdge(self.clock)
            s("bid").value   = awid
            s("bresp").value = RESP_OKAY
            s("bvalid").value = 1
            while True:
                await ReadOnly()
                if s("bready").value:
                    break
                await RisingEdge(self.clock)
            await RisingEdge(self.clock)
            s("bvalid").value = 0
            # Back to active phase for the next AW phase iteration.

    async def _read_loop(self):
        s = self._sig
        while True:
            # ── AR: assert arready, poll for arvalid ──────────────────────────
            for _ in range(self.ar_delay):
                await RisingEdge(self.clock)
            s("arready").value = 1
            arid = addr = arlen = 0
            while True:
                await ReadOnly()
                if s("arvalid").value:
                    arid  = int(s("arid").value)
                    addr  = int(s("araddr").value)
                    arlen = int(s("arlen").value)
                    break
                await RisingEdge(self.clock)
            await RisingEdge(self.clock)
            s("arready").value = 0

            # ── R: drive each beat ────────────────────────────────────────────
            # At the top of every beat iteration we do `await RisingEdge` to
            # ensure we are always in the active phase when driving signals,
            # regardless of which phase the previous iteration ended in.
            for i in range(arlen + 1):
                # Guarantee active phase at the start of each beat.
                for _ in range(self.r_delay):
                    await RisingEdge(self.clock)
                await RisingEdge(self.clock)
                s("rid").value   = arid
                s("rdata").value = self.mem.get(addr + i * 4, 0)
                s("rresp").value = RESP_OKAY
                s("rlast").value = 1 if i == arlen else 0
                s("rvalid").value = 1
                # Poll rready; break when seen in ReadOnly.
                while True:
                    await ReadOnly()
                    if s("rready").value:
                        break
                    await RisingEdge(self.clock)
                # Loop to next beat: starts with `await RisingEdge` above.
            # All beats done; deassert in active phase (need one more edge).
            await RisingEdge(self.clock)
            s("rvalid").value = 0
            s("rlast").value  = 0
