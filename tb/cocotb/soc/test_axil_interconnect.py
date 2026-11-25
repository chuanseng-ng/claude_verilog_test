"""
Phase 5 (M3) -- AXI4-Lite control-interconnect unit tests.
The AXI-Lite ring has 3 slaves: the GPU, an APB-bridge proxy slot and the DMA (last match over the
bridge). The bridge window end is soc_periph_map_pkg.sv AXIL_APB_LIMIT (soc_addr_map_pkg.sv
PERIPH_LIMIT). It covers the full 14-slot APB sub-map:
Doc: ds:ch:phase6-ip-expansion-plan:4-address-map-pre-allocated-in-full
Only the first 8 APB slots (through GPIO) have real slaves (APB_N_SLAVES stays 8), so an address in
the reserved range (e.g. 0x2000_B000, the PWM slot) is in-window at the ring level and routes to the
APB-bridge proxy slave without DECERR. When the window grows again, update BAD_HIGH below and the
docstrings that cite the limit.
Unmapped (DECERR): 0x2000_0000 (below the GPU base, the CPU-debug APB gap) and 0x2001_1000 (above
the APB bridge limit). In-window but reserved (OKAY at this ring level, NOT SLVERR): 0x2000_B000.
apb_interconnect.sv's default-SLVERR-for-unclaimed-slot behaviour is NOT exercised here: this DUT
(tb_axi_lite_interconnect) has neither apb_interconnect.sv nor axil_to_apb.sv. Its "apb_bridge" slot
is a generic axi_lite_register_bank stub that completes OKAY for any in-window address. See
test_reserved_slot_in_window.
Off slots (slv_off_i): a slot that the test marks off is answered by the interconnect with SLVERR
and OFF_RDATA, and the request never reaches the slave. The tests that use it drive the master port
cycle by cycle (`_txn`) and sample the interface at the falling edge of the clock, so each cycle is
one entry of the trace.

Run: make -C tb/cocotb/soc axil_interconnect
Doc: tm:suite:soc-test-axil-interconnect
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event, FallingEdge, RisingEdge

from bfm.axi4lite_master import AXI4LiteMaster
from reset_ready_probe import assert_ready_low, hold_reset_sample_ready, release_reset_sample_ready

CLK_PERIOD_NS = 2

RESP_OKAY = 0
RESP_SLVERR = 2
RESP_DECERR = 3
OFF_RDATA = 0xDEAD_BEEF

# 3-slave AXI-Lite ring (PR-7 topology).
# Each entry maps to one register-bank stub in tb_axi_lite_interconnect.
# APB_BRIDGE covers the address range shared by UART/SPI/Timer/IRQ/PLL;
# DMA has its own slot (last-match wins at 0x2000_5000).
SLAVES = {
    "gpu":        0x2000_1000,   # slot 0
    "apb_bridge": 0x2000_2000,   # slot 1 (APB subtree proxy)
    "dma":        0x2000_5000,   # slot 2 (last-match over bridge window)
}
BAD_LOW  = 0x2000_0000   # below GPU base — gap before ring
# The bridge window extends through the full 14-slot reserved APB sub-map (soc_periph_map_pkg.
# AXIL_APB_LIMIT = 0x2001_0FFF), so 0x2000_B000 -- the old BAD_HIGH -- is in-window (OKAY at
# this ring level) and not DECERR. The same happened earlier for the GPIO, PLL2, PMU and PLL slots.
# BAD_HIGH must stay one slot above whatever AXIL_APB_LIMIT currently is. It is hardcoded and
# not derived from the SV package (see test_decerr_unmapped docstring for why), so bump it by hand
# the next time the APB window grows.
BAD_HIGH = 0x2001_1000   # above APB bridge limit 0x2001_0FFF (full 14-slot window included)

# In-window-but-reserved: PWM's slot (index 8 of the 14-slot APB sub-map) has
# no APB slave built yet, but is inside AXIL_APB_LIMIT, so it must NOT DECERR
# at this ring level. See test_reserved_slot_in_window.
RESERVED_UNBUILT = 0x2000_B000   # PWM slot — reserved, not yet a real APB slave


def _set_hang(dut, addr=0, w=0, resp=0):
    """Drive the per-slot stall levels of the wrapper (bit k = slot k). All zero: no stall."""
    dut.hang_addr.value = addr
    dut.hang_w.value = w
    dut.hang_resp.value = resp


async def _setup(dut):
    """Start clock, reset, build the CPU-side AXI4-Lite master."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
    dut.slv_off.value = 0
    _set_hang(dut)
    m = AXI4LiteMaster(dut, "m_axil_", dut.clk)
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    return m


@cocotb.test()
async def test_route_and_isolation(dut):
    """Write a distinct value to reg0 of every ring slave, then read all back.

    PR-7 topology: 3 slaves (GPU, APB-bridge proxy, DMA).
    Correct read-back proves routing and cross-slave isolation.
    Note: DMA (slot 2) wins last-match over the APB-bridge window at 0x2000_5000.
    A write to the APB-bridge base (0x2000_2000) must NOT alias to the DMA slot.
    """
    m = await _setup(dut)
    # Distinct payload per slave.
    payload = {name: 0xA5A50000 | (i << 8)
               for i, name in enumerate(SLAVES)}

    for name, base in SLAVES.items():
        resp = await m.write(base + 0x0, payload[name])
        assert resp == RESP_OKAY, f"{name} write resp {resp}"

    for name, base in SLAVES.items():
        data, rresp = await m.read(base + 0x0)
        assert rresp == RESP_OKAY, f"{name} read resp {rresp}"
        assert data == payload[name], \
            f"{name} reg0 = {data:#x}, expected {payload[name]:#x}"

    dut._log.info("routing + isolation OK")


@cocotb.test()
async def test_multi_register_routing(dut):
    """Routing holds across multiple registers within one slave.

    Uses the APB-bridge proxy slot (slot 1 at 0x2000_2000).  Multiple register
    offsets within the same 4 KB bank window should read back their written values.
    """
    m = await _setup(dut)
    base = SLAVES["apb_bridge"]
    vals = {0x0: 0x11111111, 0x4: 0x22222222, 0x8: 0x33333333}
    for off, v in vals.items():
        assert await m.write(base + off, v) == RESP_OKAY
    for off, v in vals.items():
        data, _ = await m.read(base + off)
        assert data == v, f"apb_bridge+{off:#x} = {data:#x}"
    dut._log.info("multi-register routing OK")


@cocotb.test()
async def test_decerr_unmapped(dut):
    """Unmapped addresses return DECERR and complete (never hang).

    PR-7 unmapped regions:
      BAD_LOW  = 0x2000_0000 — below GPU base (CPU-debug APB gap)
      BAD_HIGH = 0x2001_1000 — above APB bridge limit 0x2001_0FFF
    Note: 0x2000_B000 (PWM slot) is now INSIDE the APB bridge window (full
    14-slot reserved sub-map) and returns OKAY at
    this ring level -- see test_reserved_slot_in_window -- same pattern as
    0x2000_A000 becoming mapped when the GPIO slot was added, 0x2000_9000 when the PLL2 slot
    was added, 0x2000_8000 when the PMU slot was added, and
    0x2000_7000 before that when the PLL slot was added.

    On deriving BAD_HIGH from soc_periph_map_pkg.AXIL_APB_LIMIT instead of
    hardcoding it: tb_axi_lite_interconnect.sv already `import
    soc_periph_map_pkg::*;` internally but does not expose AXIL_APB_LIMIT
    as a DUT port/parameter, and cocotb/Verilator cannot read an SV
    package-scoped localparam directly without one. Doing this properly
    would mean adding a dedicated debug output port to the shared TB
    wrapper purely to serve this one assertion -- more invasive than the
    fix warrants, and inconsistent with how the prior PLL-slot extension
    was handled (a manual constant + docstring update, same as here). Left
    hardcoded; a `dbg_axil_apb_limit_o` port would be the clean way to
    remove this manual step if a future window change makes it worth it.
    """
    m = await _setup(dut)
    for bad in (BAD_LOW, BAD_HIGH):
        resp = await m.write(bad, 0xDEAD)
        assert resp == RESP_DECERR, f"write {bad:#x} resp {resp}"
        data, rresp = await m.read(bad)
        assert rresp == RESP_DECERR, f"read {bad:#x} resp {rresp}"
        assert data == 0, f"DECERR read data {data:#x}"
    # A good transaction still works after DECERR (engine returned to idle).
    assert await m.write(SLAVES["dma"], 0xBEEF) == RESP_OKAY
    data, _ = await m.read(SLAVES["dma"])
    assert data == 0xBEEF
    dut._log.info("DECERR unmapped OK")


@cocotb.test()
async def test_reserved_slot_in_window(dut):
    """PWM's reserved-but-unbuilt APB slot (0x2000_B000) must not DECERR or hang.

    apb_interconnect.sv defines the real APB sub-decode: psel_i=1 but
    no slave claims the address returns pslverr_o=1 (SLVERR-equivalent), not
    DECERR. That module is NOT part of this testbench's build, though
    (tb_axi_lite_interconnect / AXIL_SOURCES in Makefile instantiate only
    axi_lite_interconnect + axi_lite_register_bank stubs -- apb_interconnect.sv
    and axil_to_apb.sv are pulled in only by the full-SoC source lists). At
    this ring level, RESERVED_UNBUILT is simply an in-window address for the
    "apb_bridge" proxy slot (slot 1, base 0x2000_2000, limit now
    AXIL_APB_LIMIT=0x2001_0FFF): the interconnect routes it straight to the
    stub axi_lite_register_bank, which always completes with OKAY for any
    in-window address (see that module's header: "Out-of-range word addresses
    complete with OKAY: writes are dropped, reads return 0."). So the
    assertion this test can honestly make at this level is response==OKAY and
    completion without a hang -- confirming the address is correctly inside
    AXIL_APB_LIMIT and does not spuriously DECERR. The real apb_interconnect
    SLVERR-for-unclaimed-slot behaviour needs a DUT that actually instantiates
    apb_interconnect.sv (e.g. an SoC-level or axil_to_apb+apb_interconnect
    test), which this file's DUT does not.
    """
    m = await _setup(dut)
    resp = await m.write(RESERVED_UNBUILT, 0xCAFE)
    assert resp == RESP_OKAY, (
        f"write {RESERVED_UNBUILT:#x} resp {resp}; expected OKAY at the "
        f"AXI-Lite ring level (in-window, routed to the apb_bridge proxy stub)"
    )
    data, rresp = await m.read(RESERVED_UNBUILT)
    assert rresp == RESP_OKAY, f"read {RESERVED_UNBUILT:#x} resp {rresp}"
    # A good transaction on another slave still works afterwards (no stuck state).
    assert await m.write(SLAVES["dma"], 0xF00D) == RESP_OKAY
    data, _ = await m.read(SLAVES["dma"])
    assert data == 0xF00D
    dut._log.info("reserved-slot in-window (no DECERR, no hang) OK")


@cocotb.test()
async def test_backpressure(dut):
    """Master stalls bready/rready; the interconnect must hold the response."""
    # Drive the master port directly (the BFM keeps bready/rready high, which
    # would defeat the stall we want to test).
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
    dut.slv_off.value = 0
    # Idle all master inputs.
    for sig in ("awvalid", "wvalid", "bready", "arvalid", "rready"):
        getattr(dut, f"m_axil_{sig}").value = 0
    dut.m_axil_awprot.value = 0
    dut.m_axil_arprot.value = 0
    dut.m_axil_wstrb.value = 0xF
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)

    addr = SLAVES["gpu"] + 0x0
    # ── Write with delayed bready ────────────────────────────────────────────
    dut.m_axil_awaddr.value = addr
    dut.m_axil_awvalid.value = 1
    dut.m_axil_wdata.value = 0xFEEDFACE
    dut.m_axil_wvalid.value = 1
    dut.m_axil_bready.value = 0
    aw_done = w_done = False
    while not (aw_done and w_done):
        await RisingEdge(dut.clk)
        if dut.m_axil_awvalid.value and dut.m_axil_awready.value:
            aw_done = True
            dut.m_axil_awvalid.value = 0
        if dut.m_axil_wvalid.value and dut.m_axil_wready.value:
            w_done = True
            dut.m_axil_wvalid.value = 0
    # Wait for the response, then hold bready low and confirm bvalid sticks.
    while not dut.m_axil_bvalid.value:
        await RisingEdge(dut.clk)
    for _ in range(3):
        assert dut.m_axil_bvalid.value == 1, "bvalid dropped during bready stall"
        assert int(dut.m_axil_bresp.value) == RESP_OKAY
        await RisingEdge(dut.clk)
    dut.m_axil_bready.value = 1
    await RisingEdge(dut.clk)
    dut.m_axil_bready.value = 0

    # ── Read with delayed rready ─────────────────────────────────────────────
    dut.m_axil_araddr.value = addr
    dut.m_axil_arvalid.value = 1
    dut.m_axil_rready.value = 0
    while not (dut.m_axil_arvalid.value and dut.m_axil_arready.value):
        await RisingEdge(dut.clk)
    dut.m_axil_arvalid.value = 0
    while not dut.m_axil_rvalid.value:
        await RisingEdge(dut.clk)
    for _ in range(3):
        assert dut.m_axil_rvalid.value == 1, "rvalid dropped during rready stall"
        assert int(dut.m_axil_rdata.value) == 0xFEEDFACE
        await RisingEdge(dut.clk)
    dut.m_axil_rready.value = 1
    await RisingEdge(dut.clk)
    dut.m_axil_rready.value = 0
    dut._log.info("backpressure OK")


# ──────────────────────────────────────────────────────────────────────────────
# AxPROT routing.
#
# axi_lite_interconnect forwards AWPROT/ARPROT to the selected slave only
# (axi_lite_interconnect.sv: `_s_awprot[wsel] = m_axil_awprot` and `_s_arprot[rsel] =
# m_axil_arprot`).  Nothing in the SoC decodes AxPROT, so before this test a mis-routed or
# dropped AxPROT could not be seen by any suite -- and the toggle coverage of the field was
# waived as "never driven".  The tb wrapper exposes the per-slave buses (s_awprot/s_arprot,
# packed [slave][2:0]) and --public-flat-rw makes them visible to cocotb.
# ──────────────────────────────────────────────────────────────────────────────

PROT_VALUES = (0b001, 0b010, 0b100, 0b111, 0b101)  # privileged, non-secure, instruction, all, mix


def _lane(bus_value, slave_idx, width=3):
    """Slice slave ``slave_idx`` out of a packed [N][width-1:0] bus."""
    return (int(bus_value) >> (width * slave_idx)) & ((1 << width) - 1)


async def _prot_monitor(dut, samples):
    """Every cycle, record (aw_valid_mask, aw_lanes, ar_valid_mask, ar_lanes) of the slave side."""
    n = len(SLAVES)
    while True:
        await RisingEdge(dut.clk)
        samples.append(
            (
                int(dut.s_awvalid.value),
                [_lane(dut.s_awprot.value, k) for k in range(n)],
                int(dut.s_arvalid.value),
                [_lane(dut.s_arprot.value, k) for k in range(n)],
            )
        )


@cocotb.test()
async def test_axprot_routed_to_selected_slave_only(dut):
    """Non-zero AWPROT/ARPROT reaches the addressed slave unchanged and no other slave.

    For every slave and every PROT value: write + read through the BFM with that PROT.
    While the slave-side valid of slave k is up, lane k must carry exactly the master's value;
    every other lane must stay 0 on every cycle (a mis-routed prot would show up there).  An
    unmapped address (DECERR, request dropped) must leak PROT to no slave at all.
    """
    m = await _setup(dut)
    samples = []
    cocotb.start_soon(_prot_monitor(dut, samples))
    await RisingEdge(dut.clk)

    n = len(SLAVES)
    for k, (name, base) in enumerate(SLAVES.items()):
        for prot in PROT_VALUES:
            samples.clear()
            resp = await m.write(base + 0x0, 0xC0DE0000 | (k << 8) | prot, prot=prot)
            assert resp == RESP_OKAY, f"{name} write prot={prot:#05b} resp {resp}"
            _, rresp = await m.read(base + 0x0, prot=prot)
            assert rresp == RESP_OKAY, f"{name} read prot={prot:#05b} resp {rresp}"
            await RisingEdge(dut.clk)

            aw_seen = ar_seen = 0
            for awv, awp, arv, arp in samples:
                for j in range(n):
                    if (awv >> j) & 1:
                        assert j == k, f"{name}: awvalid raised on slave {j}"
                        assert awp[j] == prot, f"{name}: awprot {awp[j]:#05b} != {prot:#05b}"
                        aw_seen += 1
                    elif j != k:
                        assert awp[j] == 0, f"{name}: awprot leaked {awp[j]:#05b} to slave {j}"
                    if (arv >> j) & 1:
                        assert j == k, f"{name}: arvalid raised on slave {j}"
                        assert arp[j] == prot, f"{name}: arprot {arp[j]:#05b} != {prot:#05b}"
                        ar_seen += 1
                    elif j != k:
                        assert arp[j] == 0, f"{name}: arprot leaked {arp[j]:#05b} to slave {j}"
            # not vacuous: the selected slave really saw both requests
            assert aw_seen > 0, f"{name}: slave never saw awvalid (prot={prot:#05b})"
            assert ar_seen > 0, f"{name}: slave never saw arvalid (prot={prot:#05b})"

    # Unmapped address: the interconnect accepts and drops the request -- DECERR, and PROT
    # must not appear on any slave lane.
    samples.clear()
    resp = await m.write(BAD_LOW, 0xDEAD_BEEF, prot=0b111)
    assert resp == RESP_DECERR, f"unmapped write resp {resp}"
    _, rresp = await m.read(BAD_LOW, prot=0b111)
    assert rresp == RESP_DECERR, f"unmapped read resp {rresp}"
    await RisingEdge(dut.clk)
    for awv, awp, arv, arp in samples:
        assert awv == 0 and arv == 0, "unmapped access reached a slave"
        assert awp == [0] * n and arp == [0] * n, "PROT leaked to a slave on an unmapped access"

    dut._log.info("AxPROT routing OK")


# ──────────────────────────────────────────────────────────────────────────────
# Off slots (slv_off_i).
#
# The master port is driven cycle by cycle. Cycle 0 is the first cycle with the request valid high.
# `off` and `ready` map a cycle number to a new value of slv_off or of bready/rready. A change
# takes effect at the start of that cycle. With the register-bank stub slaves, a write passes the
# states W_IDLE (cycle 0), W_AW (1), W_DATA (2) and W_RESP (3: the slave response is valid), and a
# read passes R_IDLE (0), R_AR (1) and R_DATA (2: the slave response is valid, the output register
# holds it from cycle 3). The trace keeps the engine state of every cycle, so a test can prove that
# its flag change fell into the state it names.
# ──────────────────────────────────────────────────────────────────────────────

GPU = SLAVES["gpu"]
APB = SLAVES["apb_bridge"]
DMA = SLAVES["dma"]
SLOT_GPU, SLOT_APB, SLOT_DMA = 0, 1, 2
W_IDLE, W_AW, W_DATA, W_RESP = range(4)
R_IDLE, R_AR, R_DATA = range(3)
MAX_TXN_CYCLES = 60
TAIL_CYCLES = 8


class _Txn:
    """Result of one `_txn`: the responses and the per-cycle trace."""

    def __init__(self):
        self.rec = []  # one dict per cycle
        self.n_resp = 0  # response handshakes (B or R)
        self.resp = None
        self.rdata = None
        self.resp_cycle = None
        self.hang = False
        self.unstable = []  # a valid response that changed while not accepted
        self.fwd = {"aw": 0, "w": 0, "ar": 0}  # cycles in which any slave saw the valid
        self.master_hs = {"aw": False, "w": False, "ar": False}  # channel accepted from the master
        self.max_cycles = MAX_TXN_CYCLES

    def state_at(self, cycle):
        return self.rec[cycle]["state"]

    def fmt(self):
        return " ".join(
            f"[{r['c']} off={r['off']:03b} st={r['state']} rv={r['rv']} resp={r['resp']}"
            f" fwd={r['fwd']}]"
            for r in self.rec[:14]
        )


async def _txn(dut, kind, addr, data=0, off=None, ready=None, act=None, max_cycles=MAX_TXN_CYCLES):
    """One write (kind "w") or read (kind "r"). Returns a `_Txn`. `act` maps a cycle to a callable
    that runs at the start of that cycle (a stall release). `max_cycles` is the hang limit."""
    off = off or {}
    ready = ready or {}
    act = act or {}
    is_w = kind == "w"
    ready_sig = dut.m_axil_bready if is_w else dut.m_axil_rready
    state_sig = dut.u_axil_ic.wstate if is_w else dut.u_axil_ic.rstate
    t = _Txn()
    t.max_cycles = max_cycles
    ready_sig.value = 1
    await RisingEdge(dut.clk)
    aw = is_w
    w = is_w
    ar = not is_w
    if is_w:
        dut.m_axil_awaddr.value = addr
        dut.m_axil_awprot.value = 0
        dut.m_axil_awvalid.value = 1
        dut.m_axil_wdata.value = data
        dut.m_axil_wstrb.value = 0xF
        dut.m_axil_wvalid.value = 1
    else:
        dut.m_axil_araddr.value = addr
        dut.m_axil_arprot.value = 0
        dut.m_axil_arvalid.value = 1
    cycle = 0
    done_at = None
    prev = None
    while True:
        if cycle in off:
            dut.slv_off.value = off[cycle]
        if cycle in ready:
            ready_sig.value = ready[cycle]
        if cycle in act:
            act[cycle]()
        await FallingEdge(dut.clk)
        fwd = {
            "aw": int(dut.s_awvalid.value),
            "w": int(dut.s_wvalid.value),
            "ar": int(dut.s_arvalid.value),
        }
        for k, v in fwd.items():
            if v:
                t.fwd[k] += 1
        rdy = int(ready_sig.value)
        if is_w:
            rv, resp, rdata = (
                int(dut.m_axil_bvalid.value),
                int(dut.m_axil_bresp.value),
                None,
            )
            aw_hs = aw and int(dut.m_axil_awready.value)
            w_hs = w and int(dut.m_axil_wready.value)
        else:
            rv, resp, rdata = (
                int(dut.m_axil_rvalid.value),
                int(dut.m_axil_rresp.value),
                int(dut.m_axil_rdata.value),
            )
            aw_hs = w_hs = False
        ar_hs = ar and int(dut.m_axil_arready.value)
        if prev is not None and prev[0] and not prev[1]:
            if not rv or (resp, rdata) != (prev[2], prev[3]):
                t.unstable.append(
                    f"cycle {cycle}: valid response changed before it was accepted"
                )
        prev = (rv, rdy, resp, rdata)
        t.rec.append(
            {
                "c": cycle,
                "off": int(dut.slv_off.value),
                "state": int(state_sig.value),
                "rv": rv,
                "resp": resp,
                "fwd": (fwd["aw"], fwd["w"], fwd["ar"]),
            }
        )
        if rv and rdy:
            t.n_resp += 1
            if t.resp is None:
                t.resp, t.rdata, t.resp_cycle = resp, rdata, cycle
                done_at = cycle
        await RisingEdge(dut.clk)
        if aw_hs:
            aw = False
            t.master_hs["aw"] = True
            dut.m_axil_awvalid.value = 0
        if w_hs:
            w = False
            t.master_hs["w"] = True
            dut.m_axil_wvalid.value = 0
        if ar_hs:
            ar = False
            t.master_hs["ar"] = True
            dut.m_axil_arvalid.value = 0
        cycle += 1
        if done_at is None and cycle >= max_cycles:
            t.hang = True
            break
        if done_at is not None and cycle > done_at + TAIL_CYCLES:
            break
    if is_w:
        dut.m_axil_awvalid.value = 0
        dut.m_axil_wvalid.value = 0
    else:
        dut.m_axil_arvalid.value = 0
    ready_sig.value = 1
    return t


def _check_once(t, resp, label, rdata=None):
    """The transaction ended once, with the given response (and read data) and a stable response."""
    assert not t.hang, f"{label}: no response in {t.max_cycles} cycles. {t.fmt()}"
    assert t.n_resp == 1, (
        f"{label}: {t.n_resp} responses, expected exactly 1. {t.fmt()}"
    )
    assert t.resp == resp, f"{label}: resp {t.resp}, expected {resp}. {t.fmt()}"
    if rdata is not None:
        assert t.rdata == rdata, (
            f"{label}: rdata {t.rdata:#x}, expected {rdata:#x}. {t.fmt()}"
        )
    assert not t.unstable, f"{label}: {t.unstable}. {t.fmt()}"


async def _setup_off(dut):
    """Start the clock and reset, then write a known value to reg0 of the three slaves. Returns the
    master BFM."""
    m = await _setup(dut)
    for k, base in enumerate(SLAVES.values()):
        assert await m.write(base, 0x5A00_0000 | k) == RESP_OKAY
    return m


def _known(k):
    return 0x5A00_0000 | k


async def _rereset(dut, m):
    """Reset the DUT and the stub slaves again without a second clock, then restore the known
    values. A transaction that the flag cut short leaves a stub slave with an unanswered request,
    as a powered-off slave would be reset before it returns."""
    dut.slv_off.value = 0
    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    for k, base in enumerate(SLAVES.values()):
        assert await m.write(base, _known(k)) == RESP_OKAY


async def _expect_slot_unchanged(dut, m, k, base, label):
    data, rresp = await m.read(base)
    assert rresp == RESP_OKAY and data == _known(k), (
        f"{label}: slot {k} reg0 {data:#x} resp {rresp}"
    )


@cocotb.test()
async def test_off_flag_default_value(dut):
    """The wrapper mirrors the OFF_RDATA parameter of the DUT: it is 0xDEAD_BEEF."""
    await _setup(dut)
    assert int(dut.off_rdata_o.value) == OFF_RDATA, f"{int(dut.off_rdata_o.value):#x}"


@cocotb.test()
async def test_off_write_slverr_not_forwarded(dut):
    """A write to an off slot ends once with SLVERR. No slave sees an AW or W valid, the slot keeps
    its old value, and the slot answers normally once the flag is clear."""
    m = await _setup_off(dut)
    for k, base in enumerate(SLAVES.values()):
        dut.slv_off.value = 1 << k
        t = await _txn(dut, "w", base, 0xBAD0_0000 | k)
        _check_once(t, RESP_SLVERR, f"write slot {k}")
        assert t.fwd == {"aw": 0, "w": 0, "ar": 0}, (
            f"slot {k}: forwarded {t.fwd}. {t.fmt()}"
        )
        dut.slv_off.value = 0
        await _expect_slot_unchanged(dut, m, k, base, f"after off write slot {k}")


@cocotb.test()
async def test_off_read_slverr_and_data(dut):
    """A read from an off slot ends once with SLVERR and the data 0xDEAD_BEEF. No slave sees an AR
    valid."""
    m = await _setup_off(dut)
    for k, base in enumerate(SLAVES.values()):
        dut.slv_off.value = 1 << k
        t = await _txn(dut, "r", base)
        _check_once(t, RESP_SLVERR, f"read slot {k}", OFF_RDATA)
        assert t.fwd == {"aw": 0, "w": 0, "ar": 0}, (
            f"slot {k}: forwarded {t.fwd}. {t.fmt()}"
        )
        dut.slv_off.value = 0
        await _expect_slot_unchanged(dut, m, k, base, f"after off read slot {k}")


@cocotb.test()
async def test_off_rises_during_write_aw(dut):
    """The flag rises in the cycle in which the write engine is in W_AW (the AW is not yet taken).
    The AW and W are accepted and dropped, nothing is forwarded, and the write ends once with
    SLVERR."""
    m = await _setup_off(dut)
    t = await _txn(dut, "w", GPU, 0xBAD0_0001, off={1: 0b001})
    assert t.state_at(1) == W_AW, f"stimulus missed W_AW. {t.fmt()}"
    assert t.state_at(0) == W_IDLE
    _check_once(t, RESP_SLVERR, "off rises in W_AW")
    assert t.fwd == {"aw": 0, "w": 0, "ar": 0}, f"forwarded {t.fwd}. {t.fmt()}"
    dut.slv_off.value = 0
    await _expect_slot_unchanged(dut, m, SLOT_GPU, GPU, "after")


@cocotb.test()
async def test_off_rises_during_write_w(dut):
    """The flag rises in the cycle of W_DATA. The AW went to the slave before the flag rose. The W
    is sunk and not forwarded, and the write ends once with SLVERR."""
    await _setup_off(dut)
    t = await _txn(dut, "w", GPU, 0xBAD0_0002, off={2: 0b001})
    assert t.state_at(2) == W_DATA, f"stimulus missed W_DATA. {t.fmt()}"
    _check_once(t, RESP_SLVERR, "off rises in W_DATA")
    assert t.fwd["aw"] == 1, (
        f"the AW before the flag should be forwarded once. {t.fmt()}"
    )
    assert t.fwd["w"] == 0, f"the W was forwarded after the flag rose. {t.fmt()}"


@cocotb.test()
async def test_off_rises_during_write_response(dut):
    """The flag rises in W_RESP, in the cycle in which the slave response is valid. The local
    SLVERR replaces it, once. With bready low the local response is held until accepted."""
    m = await _setup_off(dut)
    t = await _txn(dut, "w", GPU, 0xBAD0_0003, off={3: 0b001})
    assert t.state_at(3) == W_RESP, f"stimulus missed W_RESP. {t.fmt()}"
    _check_once(t, RESP_SLVERR, "off rises in W_RESP")
    await _rereset(dut, m)
    t = await _txn(dut, "w", GPU, 0xBAD0_0004, off={3: 0b001}, ready={0: 1, 3: 0, 6: 1})
    assert t.state_at(3) == W_RESP
    _check_once(t, RESP_SLVERR, "off rises in W_RESP, bready low for 3 cycles")
    assert t.resp_cycle == 6, (
        f"the response was accepted in cycle {t.resp_cycle}. {t.fmt()}"
    )


@cocotb.test()
async def test_off_rises_during_read_ar(dut):
    """The flag rises in R_AR. The AR is accepted and dropped, nothing is forwarded, and the read
    ends once with SLVERR and 0xDEAD_BEEF."""
    await _setup_off(dut)
    t = await _txn(dut, "r", GPU, off={1: 0b001})
    assert t.state_at(1) == R_AR and t.state_at(0) == R_IDLE, (
        f"stimulus missed R_AR. {t.fmt()}"
    )
    _check_once(t, RESP_SLVERR, "off rises in R_AR", OFF_RDATA)
    assert t.fwd == {"aw": 0, "w": 0, "ar": 0}, f"forwarded {t.fwd}. {t.fmt()}"


@cocotb.test()
async def test_off_rises_while_read_in_flight(dut):
    """The AR went to the slave and the flag rises in R_DATA, in the cycle in which the slave read
    response is valid but not yet registered. The local SLVERR is delivered once and the read does
    not hang."""
    await _setup_off(dut)
    t = await _txn(dut, "r", GPU, off={2: 0b001})
    assert t.state_at(2) == R_DATA, f"stimulus missed R_DATA. {t.fmt()}"
    _check_once(t, RESP_SLVERR, "off rises with the read in flight", OFF_RDATA)
    assert t.fwd["ar"] == 1, (
        f"the AR before the flag should be forwarded once. {t.fmt()}"
    )


@cocotb.test()
async def test_off_rises_after_read_response_registered(dut):
    """The slave response is already in the output register when the flag rises. It is delivered
    once with its own data and OKAY, and the local response does not replace it. Checked with rready
    high and with rready low while the flag rises."""
    m = await _setup_off(dut)
    t = await _txn(dut, "r", GPU, off={3: 0b001})
    assert t.state_at(3) == R_DATA, f"stimulus missed the registered cycle. {t.fmt()}"
    _check_once(
        t, RESP_OKAY, "flag rises with the response registered", _known(SLOT_GPU)
    )
    assert t.resp_cycle == 3, t.fmt()
    # The flag is still high: the next read of the slot is answered locally.
    t = await _txn(dut, "r", GPU)
    _check_once(t, RESP_SLVERR, "next read while the flag stays high", OFF_RDATA)
    await _rereset(dut, m)
    t = await _txn(dut, "r", GPU, off={3: 0b001}, ready={0: 1, 3: 0, 7: 1})
    assert t.state_at(3) == R_DATA
    _check_once(
        t,
        RESP_OKAY,
        "flag rises with the response registered, rready low",
        _known(SLOT_GPU),
    )
    assert t.resp_cycle == 7, t.fmt()
    t = await _txn(dut, "r", GPU)
    _check_once(t, RESP_SLVERR, "next read while the flag stays high", OFF_RDATA)


@cocotb.test()
async def test_off_falls_mid_transaction_stays_local(dut):
    """The flag falls during a transaction that it started. The transaction still ends locally with
    SLVERR and nothing is forwarded afterwards. Cases: flag high from cycle 0 and low from cycle 2,
    a one-cycle pulse in W_AW / R_AR, and a pulse in R_DATA."""
    m = await _setup_off(dut)
    for label, kind, off in (
        ("write fall at 2", "w", {0: 0b001, 2: 0}),
        ("write pulse in W_AW", "w", {1: 0b001, 2: 0}),
        ("write pulse in W_DATA", "w", {2: 0b001, 3: 0}),
        ("read fall at 2", "r", {0: 0b001, 2: 0}),
        ("read pulse in R_AR", "r", {1: 0b001, 2: 0}),
        ("read pulse in R_DATA", "r", {2: 0b001, 3: 0}),
    ):
        await _rereset(dut, m)
        t = await _txn(dut, kind, GPU, 0xBAD0_0005, off=off)
        _check_once(t, RESP_SLVERR, label, OFF_RDATA if kind == "r" else None)
        late = [r for r in t.rec if r["c"] >= 3 and any(r["fwd"])]
        assert not late, f"{label}: forwarding resumed after the flag fell. {t.fmt()}"


@cocotb.test()
async def test_off_pulse_in_write_response_keeps_error(dut):
    """The flag is high for one cycle in W_RESP while bready is low, then falls. The master has seen
    a valid SLVERR that it did not accept, so the response must stay SLVERR until it is accepted:
    it does not change back to the slave response and it does not drop (AXI4 stability, and the
    rule that a flag edge does not split a transaction). The write engine latches the flag in
    W_RESP as it does in W_AW and W_DATA; without that latch bresp goes SLVERR in cycle 3 and OKAY
    from cycle 4 with bvalid held."""
    await _setup_off(dut)
    t = await _txn(
        dut, "w", GPU, 0xBAD0_0006, off={3: 0b001, 4: 0}, ready={0: 1, 3: 0, 6: 1}
    )
    assert t.state_at(3) == W_RESP, f"stimulus missed W_RESP. {t.fmt()}"
    _check_once(t, RESP_SLVERR, "one-cycle off pulse in W_RESP, bready low")


@cocotb.test()
async def test_other_slots_unaffected_while_one_is_off(dut):
    """With one slot off, the other two slots route, answer OKAY and return their own data. The
    off slot answers SLVERR in the same sequence."""
    m = await _setup_off(dut)
    for off_slot in range(3):
        dut.slv_off.value = 1 << off_slot
        for k, base in enumerate(SLAVES.values()):
            payload = 0xC0DE_0000 | (off_slot << 8) | k
            tw = await _txn(dut, "w", base + 4, payload)
            tr = await _txn(dut, "r", base + 4)
            if k == off_slot:
                _check_once(tw, RESP_SLVERR, f"off {off_slot}: write slot {k}")
                _check_once(
                    tr, RESP_SLVERR, f"off {off_slot}: read slot {k}", OFF_RDATA
                )
                assert tw.fwd == {"aw": 0, "w": 0, "ar": 0} and tr.fwd == tw.fwd
            else:
                _check_once(tw, RESP_OKAY, f"off {off_slot}: write slot {k}")
                _check_once(tr, RESP_OKAY, f"off {off_slot}: read slot {k}", payload)
                assert tw.fwd["aw"] == 1 and tw.fwd["w"] == 1 and tr.fwd["ar"] == 1, (
                    f"off {off_slot}: slot {k} did not see the request. {tw.fmt()}"
                )
    dut.slv_off.value = 0
    for k, base in enumerate(SLAVES.values()):
        await _expect_slot_unchanged(dut, m, k, base, "reg0 after all off runs")


@cocotb.test()
async def test_unmapped_address_decerr_has_priority_over_off(dut):
    """An unmapped address returns DECERR (and 0 read data) when every slot is off."""
    await _setup_off(dut)
    dut.slv_off.value = 0b111
    for bad in (BAD_LOW, BAD_HIGH):
        tw = await _txn(dut, "w", bad, 0x1234)
        _check_once(tw, RESP_DECERR, f"write {bad:#x}")
        tr = await _txn(dut, "r", bad)
        _check_once(tr, RESP_DECERR, f"read {bad:#x}", 0)
        assert tw.fwd == {"aw": 0, "w": 0, "ar": 0} and tr.fwd == tw.fwd


@cocotb.test()
async def test_forwarding_resumes_after_flag_clears(dut):
    """Back to back: an off write and an off read, the flag clears in the cycle after the response,
    and the next write and read are forwarded and answered normally."""
    await _setup_off(dut)
    tw = await _txn(dut, "w", GPU, 0xBAD0_0007, off={0: 0b001})
    _check_once(tw, RESP_SLVERR, "off write")
    dut.slv_off.value = 0
    tw2 = await _txn(dut, "w", GPU, 0x0123_4567)
    _check_once(tw2, RESP_OKAY, "write after the flag cleared")
    assert tw2.fwd["aw"] == 1 and tw2.fwd["w"] == 1, tw2.fmt()
    dut.slv_off.value = 0b001
    tr = await _txn(dut, "r", GPU)
    _check_once(tr, RESP_SLVERR, "off read", OFF_RDATA)
    dut.slv_off.value = 0
    tr2 = await _txn(dut, "r", GPU)
    _check_once(tr2, RESP_OKAY, "read after the flag cleared", 0x0123_4567)
    assert tr2.fwd["ar"] == 1, tr2.fmt()


@cocotb.test()
async def test_off_rises_after_write_response_shown_keeps_okay(dut):
    """The slave response (OKAY) is shown to the master with bready low, then the flag rises, then
    bready goes high. The master receives the OKAY once, and bvalid and bresp do not change in any
    cycle while it waits. The write itself reached the slave, so the next write to the slot while
    the flag is still high gets SLVERR and is not forwarded. Variants: the flag rises one cycle
    after the response is first shown, and later; and it rises and falls before bready."""
    m = await _setup_off(dut)
    for label, off in (
        ("rise 1 cycle after the response", {4: 0b001}),
        ("rise 2 cycles after the response", {5: 0b001}),
        ("pulse after the response", {4: 0b001, 5: 0}),
    ):
        await _rereset(dut, m)
        t = await _txn(dut, "w", GPU, 0x0A11_0000, off=off, ready={0: 0, 8: 1})
        assert t.state_at(3) == W_RESP and t.rec[3]["rv"] == 1, f"{label}: {t.fmt()}"
        assert t.rec[3]["off"] == 0, f"{label}: the flag was already high when B was shown"
        _check_once(t, RESP_OKAY, label)
        assert t.resp_cycle == 8, f"{label}: accepted in cycle {t.resp_cycle}. {t.fmt()}"
        assert all(r["rv"] == 1 and r["resp"] == RESP_OKAY for r in t.rec[3:9]), (
            f"{label}: bvalid or bresp changed while waiting. {t.fmt()}"
        )
        # The write is not undone: with the flag cleared the slot holds the data.
        dut.slv_off.value = 0
        data, rresp = await m.read(GPU)
        assert rresp == RESP_OKAY and data == 0x0A11_0000, f"{label}: slot holds {data:#x}"
        # The next write while the flag is high gets SLVERR and nothing is forwarded.
        dut.slv_off.value = 0b001
        t2 = await _txn(dut, "w", GPU, 0x0A11_0001)
        _check_once(t2, RESP_SLVERR, f"{label}: next write while off")
        assert t2.fwd == {"aw": 0, "w": 0, "ar": 0}, f"{label}: forwarded {t2.fwd}. {t2.fmt()}"
        dut.slv_off.value = 0
        data, rresp = await m.read(GPU)
        assert data == 0x0A11_0000, f"{label}: the off write changed the slot: {data:#x}"


@cocotb.test()
async def test_off_rises_after_read_response_shown_keeps_data(dut):
    """The read response is shown with rready low (so it sits in the output register), then the
    flag rises later, then rready goes high. The master receives the original data and OKAY once,
    and rvalid, rresp and rdata do not change in any cycle while it waits. The next read of the slot
    while the flag is still high gets SLVERR and 0xDEAD_BEEF."""
    m = await _setup_off(dut)
    for label, off in (
        ("rise 1 cycle after the response", {4: 0b001}),
        ("rise 3 cycles after the response", {6: 0b001}),
        ("pulse after the response", {4: 0b001, 5: 0}),
    ):
        await _rereset(dut, m)
        t = await _txn(dut, "r", GPU, off=off, ready={0: 0, 9: 1})
        assert t.state_at(3) == R_DATA and t.rec[3]["rv"] == 1, f"{label}: {t.fmt()}"
        assert t.rec[3]["off"] == 0, f"{label}: the flag was already high when R was shown"
        _check_once(t, RESP_OKAY, label, _known(SLOT_GPU))
        assert t.resp_cycle == 9, f"{label}: accepted in cycle {t.resp_cycle}. {t.fmt()}"
        assert all(r["rv"] == 1 and r["resp"] == RESP_OKAY for r in t.rec[3:10]), (
            f"{label}: rvalid or rresp changed while waiting. {t.fmt()}"
        )
        dut.slv_off.value = 0b001
        t2 = await _txn(dut, "r", GPU)
        _check_once(t2, RESP_SLVERR, f"{label}: next read while off", OFF_RDATA)
        assert t2.fwd == {"aw": 0, "w": 0, "ar": 0}, f"{label}: forwarded {t2.fwd}. {t2.fmt()}"
        dut.slv_off.value = 0


# ---------------------------------------------------------------------------
# Master-face ready outputs while rst_n is asserted (single clock, 1:1 by construction)
# ---------------------------------------------------------------------------
# The interconnect already drives these low in reset, so the first test is a regression guard and
# passes. The target is an unmapped address: the interconnect accepts and drops it, which makes
# AWREADY and ARREADY rise as soon as the request is captured, so the control can see them.
def _reset_probe_ports(dut):
    valids = [dut.m_axil_awvalid, dut.m_axil_wvalid, dut.m_axil_arvalid]
    extra = {dut.m_axil_awaddr: BAD_LOW, dut.m_axil_araddr: BAD_LOW,
             dut.m_axil_bready: 1, dut.m_axil_rready: 1}
    readies = {"m_axil_awready": dut.m_axil_awready, "m_axil_wready": dut.m_axil_wready,
               "m_axil_arready": dut.m_axil_arready}
    return valids, extra, readies


@cocotb.test()
async def test_reset_ready_low_in_reset(dut):
    """Guard: AWREADY, WREADY and ARREADY are low while rst_n is low, with all VALIDs high."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    valids, extra, readies = _reset_probe_ports(dut)
    seen = await hold_reset_sample_ready(dut.clk, dut.rst_n, valids, readies, extra)
    assert_ready_low(dut, seen, "master-face ready while rst_n is low")


@cocotb.test()
async def test_reset_ready_control_after_release(dut):
    """Control: the same stimulus after rst_n releases shows AWREADY and ARREADY high."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    valids, extra, readies = _reset_probe_ports(dut)
    await hold_reset_sample_ready(dut.clk, dut.rst_n, valids, readies, extra)
    high = await release_reset_sample_ready(dut.clk, dut.rst_n, readies)
    assert {"m_axil_awready", "m_axil_arready"} <= high, (
        f"probe is blind: after release only {sorted(high)} went high"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bounded wait (TIMEOUT_CYCLES).
#
# A slave that never answers must not hang the master. Each engine counts clk cycles from the
# moment it presents the request to the slot. At TIMEOUT_CYCLES the interconnect answers the
# master with SLVERR (read data OFF_RDATA) and marks the slot stale. While a slot is stale, a new
# access of the same engine to it is answered locally at once and is not forwarded. The late
# response of the slot is absorbed, then the slot is forwarded again. Other slots are not
# affected. Unmapped addresses (DECERR) and off slots keep their answers.
#
# The tests use the default bound. The wrapper does not pass TIMEOUT_CYCLES to the DUT, so the
# build keeps elaborating on an RTL that has no such parameter. A later change that adds the
# parameter can pass a small value through the wrapper and shrink TIMEOUT_CYCLES below.
#
# The wrapper stalls a slot with hang_addr (address handshake never completes), hang_w (W never
# accepted) and hang_resp (B or R held back, released by the test for a slave that answers late).
#
# Each test that needs the bounded wait is expect_fail until the RTL has it. The tests without
# expect_fail are controls: they pass on the present RTL and must keep passing.
# ──────────────────────────────────────────────────────────────────────────────

TIMEOUT_CYCLES = 4096  # default of the TIMEOUT_CYCLES parameter
TIMEOUT_MARGIN = 32  # cycles for the request handshake, the engine states and the output register
AT_ONCE = 12  # a local answer ends within this many cycles
BOUND_RUN = TIMEOUT_CYCLES + TIMEOUT_MARGIN + 8


def _check_bounded(t, resp, label, rdata=None):
    """The master got one `resp` (and `rdata` for a read) no later than the bound plus margin."""
    _check_once(t, resp, label, rdata)
    assert t.resp_cycle <= TIMEOUT_CYCLES + TIMEOUT_MARGIN, (
        f"{label}: response in cycle {t.resp_cycle}, bound {TIMEOUT_CYCLES}+{TIMEOUT_MARGIN}"
    )


def _check_local(t, resp, label, rdata=None):
    """A local answer: one response within AT_ONCE cycles, nothing forwarded to a slave."""
    _check_once(t, resp, label, rdata)
    assert t.resp_cycle <= AT_ONCE, f"{label}: response in cycle {t.resp_cycle}. {t.fmt()}"
    assert t.fwd == {"aw": 0, "w": 0, "ar": 0}, f"{label}: forwarded {t.fwd}. {t.fmt()}"


async def _quiet_master(dut, signal, cycles, label):
    """The master response channel `signal` (bvalid or rvalid) stays low for `cycles` cycles."""
    sig = getattr(dut, signal)
    for c in range(cycles):
        await FallingEdge(dut.clk)
        assert int(sig.value) == 0, f"{label}: {signal} high in cycle {c} of the quiet window"
    await RisingEdge(dut.clk)


async def _run_in_background(coro):
    """Start `coro`, return (event, box). The event is set when it ends, box[0] holds its result."""
    ev = Event()
    box = []

    async def _wrap():
        box.append(await coro)
        ev.set()

    cocotb.start_soon(_wrap())
    return ev, box


@cocotb.test(expect_fail=True)
async def test_timeout_write_no_response_slverr(dut):
    """The slot takes AW and W and never gives B. The master gets one BRESP SLVERR within the bound.

    expect_fail: the write engine waits for B forever (no bounded wait yet)."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    t = await _txn(dut, "w", GPU, 0xBAD0_1001, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "write, slot never answers B")


@cocotb.test(expect_fail=True)
async def test_timeout_read_no_response_slverr_and_data(dut):
    """The slot takes AR and never gives R. The master gets one RRESP SLVERR and RDATA 0xDEAD_BEEF
    within the bound.

    expect_fail: the read engine waits for R forever."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_APB)
    t = await _txn(dut, "r", APB, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "read, slot never answers R", OFF_RDATA)


@cocotb.test(expect_fail=True)
async def test_timeout_write_address_never_accepted(dut):
    """The slot never accepts the AW. The bound also covers this wait: the master gets one SLVERR
    within the bound and its AW and W are both taken.

    expect_fail: the write engine waits for AWREADY forever."""
    await _setup_off(dut)
    _set_hang(dut, addr=1 << SLOT_DMA)
    t = await _txn(dut, "w", DMA, 0xBAD0_1002, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "write, slot never accepts AW")
    assert t.master_hs["aw"] and t.master_hs["w"], f"master channels not taken: {t.master_hs}"


@cocotb.test(expect_fail=True)
async def test_timeout_write_data_never_accepted(dut):
    """The slot takes the AW and never accepts the W. The master gets one SLVERR within the bound
    and its W is taken.

    expect_fail: the write engine waits for WREADY forever."""
    await _setup_off(dut)
    _set_hang(dut, w=1 << SLOT_APB)
    t = await _txn(dut, "w", APB, 0xBAD0_1003, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "write, slot never accepts W")
    assert t.master_hs["w"], f"master W not taken: {t.master_hs}"


@cocotb.test(expect_fail=True)
async def test_timeout_read_address_never_accepted(dut):
    """The slot never accepts the AR. The master gets one SLVERR and 0xDEAD_BEEF within the bound
    and its AR is taken.

    expect_fail: the read engine waits for ARREADY forever."""
    await _setup_off(dut)
    _set_hang(dut, addr=1 << SLOT_GPU)
    t = await _txn(dut, "r", GPU, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "read, slot never accepts AR", OFF_RDATA)
    assert t.master_hs["ar"], f"master AR not taken: {t.master_hs}"


@cocotb.test(expect_fail=True)
async def test_stale_write_slot_answers_at_once(dut):
    """After a write timeout the slot is stale: the next write to it ends at once with SLVERR and
    no AW or W is forwarded. A write to another slot still works.

    expect_fail: the first write never times out."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    t = await _txn(dut, "w", GPU, 0xBAD0_2001, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "write that times out")
    for n in range(2):
        t = await _txn(dut, "w", GPU, 0xBAD0_2002 + n)
        _check_local(t, RESP_SLVERR, f"write {n} to the stale slot")
    t = await _txn(dut, "w", DMA, 0x600D_0001)
    _check_once(t, RESP_OKAY, "write to another slot")


@cocotb.test(expect_fail=True)
async def test_stale_read_slot_answers_at_once(dut):
    """After a read timeout the slot is stale: the next read of it ends at once with SLVERR and
    0xDEAD_BEEF and no AR is forwarded. A read of another slot still works.

    expect_fail: the first read never times out."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    t = await _txn(dut, "r", GPU, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "read that times out", OFF_RDATA)
    for n in range(2):
        t = await _txn(dut, "r", GPU)
        _check_local(t, RESP_SLVERR, f"read {n} of the stale slot", OFF_RDATA)
    t = await _txn(dut, "r", DMA)
    _check_once(t, RESP_OKAY, "read of another slot", _known(SLOT_DMA))


@cocotb.test(expect_fail=True)
async def test_late_write_response_absorbed_slot_reopens(dut):
    """The late B of a timed-out write is not shown to the master. Once the slot has answered, the
    next write is forwarded and ends with OKAY, and the data reads back.

    expect_fail: the first write never times out."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    t = await _txn(dut, "w", GPU, 0xBAD0_3001, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "write that times out")
    t = await _txn(dut, "w", GPU, 0xBAD0_3002)
    _check_local(t, RESP_SLVERR, "write to the stale slot")
    _set_hang(dut)
    await _quiet_master(dut, "m_axil_bvalid", 40, "late B")
    t = await _txn(dut, "w", GPU, 0x600D_3003)
    _check_once(t, RESP_OKAY, "write after the slot reopened")
    assert t.fwd["aw"] >= 1 and t.fwd["w"] >= 1, f"not forwarded: {t.fwd}"
    data, rresp = await dut_read(dut, GPU)
    assert rresp == RESP_OKAY and data == 0x600D_3003, f"read back {data:#x} resp {rresp}"


@cocotb.test(expect_fail=True)
async def test_late_read_response_absorbed_slot_reopens(dut):
    """The late R of a timed-out read is not shown to the master. Once the slot has answered, the
    next read is forwarded and returns the real data with OKAY.

    expect_fail: the first read never times out."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    t = await _txn(dut, "r", GPU, max_cycles=BOUND_RUN)
    _check_bounded(t, RESP_SLVERR, "read that times out", OFF_RDATA)
    t = await _txn(dut, "r", GPU)
    _check_local(t, RESP_SLVERR, "read of the stale slot", OFF_RDATA)
    _set_hang(dut)
    await _quiet_master(dut, "m_axil_rvalid", 40, "late R")
    t = await _txn(dut, "r", GPU)
    _check_once(t, RESP_OKAY, "read after the slot reopened", _known(SLOT_GPU))
    assert t.fwd["ar"] >= 1, f"not forwarded: {t.fwd}"


async def dut_read(dut, addr):
    """One read through `_txn`. Returns (data, resp)."""
    t = await _txn(dut, "r", addr)
    return t.rdata, t.resp


@cocotb.test(expect_fail=True)
async def test_write_timeout_leaves_read_engine_and_other_slots_alone(dut):
    """While the write engine waits for a slot that never answers, reads of the other slots work
    at once. The write then times out with SLVERR, and writes to the other slots work afterwards.

    expect_fail: the write never times out."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    ev, box = await _run_in_background(_txn(dut, "w", GPU, 0xBAD0_4001, max_cycles=BOUND_RUN))
    for k in (SLOT_APB, SLOT_DMA):
        t = await _txn(dut, "r", list(SLAVES.values())[k])
        _check_once(t, RESP_OKAY, f"read of slot {k} during the write wait", _known(k))
        assert t.resp_cycle <= AT_ONCE, f"slot {k}: read took {t.resp_cycle} cycles"
    await ev.wait()
    _check_bounded(box[0], RESP_SLVERR, "write that times out")
    for k in (SLOT_APB, SLOT_DMA):
        t = await _txn(dut, "w", list(SLAVES.values())[k], 0x600D_4000 | k)
        _check_once(t, RESP_OKAY, f"write to slot {k} after the timeout")


@cocotb.test(expect_fail=True)
async def test_read_timeout_leaves_write_engine_and_other_slots_alone(dut):
    """While the read engine waits for a slot that never answers, writes to the other slots work
    at once. The read then times out with SLVERR and 0xDEAD_BEEF, and reads of the other slots work
    afterwards.

    expect_fail: the read never times out."""
    await _setup_off(dut)
    _set_hang(dut, resp=1 << SLOT_GPU)
    ev, box = await _run_in_background(_txn(dut, "r", GPU, max_cycles=BOUND_RUN))
    for k in (SLOT_APB, SLOT_DMA):
        t = await _txn(dut, "w", list(SLAVES.values())[k], 0x600D_5000 | k)
        _check_once(t, RESP_OKAY, f"write to slot {k} during the read wait")
        assert t.resp_cycle <= AT_ONCE, f"slot {k}: write took {t.resp_cycle} cycles"
    await ev.wait()
    _check_bounded(box[0], RESP_SLVERR, "read that times out", OFF_RDATA)
    for k in (SLOT_APB, SLOT_DMA):
        t = await _txn(dut, "r", list(SLAVES.values())[k])
        _check_once(t, RESP_OKAY, f"read of slot {k} after the timeout", 0x600D_5000 | k)


@cocotb.test()
async def test_slow_legal_slave_is_not_cut(dut):
    """Control: a slave that answers late, but before the bound, gets its real response. The
    response is held back for 150 cycles and for the bound minus 200 cycles. No SLVERR, the read
    data is the real data, and the response does not come before the slave gives it."""
    m = await _setup_off(dut)
    for latency in (150, TIMEOUT_CYCLES - 200):
        for kind in ("w", "r"):
            _set_hang(dut, resp=1 << SLOT_GPU)
            act = {latency: lambda: _set_hang(dut)}
            t = await _txn(dut, kind, GPU, 0x600D_6000 | latency, act=act, max_cycles=latency + 60)
            label = f"{'write' if kind == 'w' else 'read'}, slave answers after {latency} cycles"
            _check_once(t, RESP_OKAY, label, None if kind == "w" else 0x600D_6000 | latency)
            assert t.resp_cycle >= latency, f"{label}: response early, cycle {t.resp_cycle}"
            assert t.resp_cycle <= latency + AT_ONCE, (
                f"{label}: response late, cycle {t.resp_cycle}"
            )
        _set_hang(dut)
        data, rresp = await m.read(GPU)
        assert rresp == RESP_OKAY and data == 0x600D_6000 | latency, (
            f"latency {latency}: write did not land, read back {data:#x} resp {rresp}"
        )


@cocotb.test()
async def test_decerr_and_off_keep_priority_with_all_slots_stalled(dut):
    """Control: with every channel group of every slot stalled, an unmapped address still ends at
    once with DECERR (read data 0) and an off slot still ends at once with SLVERR and 0xDEAD_BEEF.
    Neither reaches a slave."""
    await _setup_off(dut)
    _set_hang(dut, addr=0b111, w=0b111, resp=0b111)
    for bad in (BAD_LOW, BAD_HIGH):
        t = await _txn(dut, "w", bad, 0xBAD0_7001)
        _check_local(t, RESP_DECERR, f"write {bad:#x}")
        t = await _txn(dut, "r", bad)
        _check_local(t, RESP_DECERR, f"read {bad:#x}", 0)
    for k, base in enumerate(SLAVES.values()):
        dut.slv_off.value = 1 << k
        t = await _txn(dut, "w", base, 0xBAD0_7002)
        _check_local(t, RESP_SLVERR, f"write off slot {k}")
        t = await _txn(dut, "r", base)
        _check_local(t, RESP_SLVERR, f"read off slot {k}", OFF_RDATA)
    dut.slv_off.value = 0
