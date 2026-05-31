"""
AXI4 (burst-capable) Master BFM for cocotb testbenches.

Extends the AXI4-Lite master pattern with AxLEN / AxSIZE / AxBURST and
W/R LAST so it can drive the Phase 5 AXI4 crossbar.

Master-facing crossbar ports carry NO id (the crossbar tags slave-facing
requests with the master index internally), so this BFM drives no id field.

Signal naming: <prefix>_<channelfield>, e.g. prefix "m0" -> m0_awaddr.

Handshake protocol
------------------
All ready signals are sampled at ReadOnly AFTER a RisingEdge.  The AW and
AR loops also sample at the SAME RisingEdge as the first drive, so
combinational-awready responders (e.g. the crossbar's DECERR engine) are
seen.  Signals are only written in the active phase (never at ReadOnly).
"""

from cocotb.triggers import RisingEdge, ReadOnly

# AXI encodings (mirror rtl/soc/axi_pkg.sv)
BURST_INCR = 0b01
SIZE_4B = 0b010
RESP_OKAY = 0b00
RESP_DECERR = 0b11


class AXI4Master:
    """Burst-capable AXI4 master driver (single outstanding transaction)."""

    def __init__(self, dut, prefix, clock):
        self.dut = dut
        self.clock = clock
        self.p = prefix
        s = self._sig
        # Initialize all master-driven outputs to idle.
        s("awaddr").value = 0
        s("awlen").value = 0
        s("awsize").value = SIZE_4B
        s("awburst").value = BURST_INCR
        s("awvalid").value = 0
        s("wdata").value = 0
        s("wstrb").value = 0
        s("wlast").value = 0
        s("wvalid").value = 0
        s("bready").value = 0
        s("araddr").value = 0
        s("arlen").value = 0
        s("arsize").value = SIZE_4B
        s("arburst").value = BURST_INCR
        s("arvalid").value = 0
        s("rready").value = 0

    def _sig(self, field):
        return getattr(self.dut, f"{self.p}_{field}")

    async def _edge(self):
        await RisingEdge(self.clock)

    async def write(self, addr, data, strb=0xF, ready_delay=0):
        """Burst write. `data` is a list of 32-bit words. Returns bresp."""
        s = self._sig
        n = len(data)

        # ── AW phase ──────────────────────────────────────────────────────────
        # Drive awvalid at the next rising edge, then poll awready starting
        # at that SAME rising edge (to catch combinational/DECERR responders)
        # and continuing at subsequent rising edges.
        await self._edge()
        s("awaddr").value = addr
        s("awlen").value = n - 1
        s("awsize").value = SIZE_4B
        s("awburst").value = BURST_INCR
        s("awvalid").value = 1
        # Poll awready: first check at the ReadOnly of the CURRENT edge (same
        # cycle as drive), then advance each cycle until seen.
        while True:
            await ReadOnly()
            if s("awready").value:
                break
            await self._edge()
        # Handshake complete; deassert awvalid at the next active phase.
        await self._edge()
        s("awvalid").value = 0

        # ── W phase ───────────────────────────────────────────────────────────
        for i, word in enumerate(data):
            s("wdata").value = word
            s("wstrb").value = strb
            s("wlast").value = 1 if i == n - 1 else 0
            s("wvalid").value = 1
            # Poll wready: check at current ReadOnly first, then advance.
            while True:
                await ReadOnly()
                if s("wready").value:
                    break
                await self._edge()
            # Handshake complete; advance one edge before next beat or cleanup.
            await self._edge()
        s("wvalid").value = 0
        s("wlast").value = 0

        # ── B phase ───────────────────────────────────────────────────────────
        for _ in range(ready_delay):
            await self._edge()
        s("bready").value = 1
        while True:
            await ReadOnly()
            if s("bvalid").value:
                bresp = int(s("bresp").value)
                break
            await self._edge()
        await self._edge()
        s("bready").value = 0
        return bresp

    async def read(self, addr, length=1, ready_delay=0):
        """Burst read of `length` beats. Returns (data_list, last_rresp)."""
        s = self._sig

        # ── AR phase ──────────────────────────────────────────────────────────
        await self._edge()
        s("araddr").value = addr
        s("arlen").value = length - 1
        s("arsize").value = SIZE_4B
        s("arburst").value = BURST_INCR
        s("arvalid").value = 1
        # Poll arready at the current ReadOnly first (same cycle as drive).
        while True:
            await ReadOnly()
            if s("arready").value:
                break
            await self._edge()
        await self._edge()
        s("arvalid").value = 0

        # ── R phase ───────────────────────────────────────────────────────────
        for _ in range(ready_delay):
            await self._edge()
        s("rready").value = 1
        data = []
        resp = RESP_OKAY
        while True:
            await ReadOnly()
            if s("rvalid").value:
                data.append(int(s("rdata").value))
                resp = int(s("rresp").value)
                last = bool(s("rlast").value)
                await self._edge()
                if last:
                    break
            else:
                await self._edge()
        s("rready").value = 0
        return data, resp
