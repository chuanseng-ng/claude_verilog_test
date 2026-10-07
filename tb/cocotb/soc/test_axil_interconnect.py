"""
Phase 5 (M3) — AXI4-Lite control-interconnect unit tests.

APB migration PR-7 update: the AXI-Lite ring now has 3 slaves, not 6.
  s0 GPU         0x2000_1000 (register bank slot 0)
  s1 APB bridge  0x2000_2000 .. 0x2000_AFFF (register bank slot 1, proxy)
  s2 DMA         0x2000_5000 (register bank slot 2, last-match over bridge)

Phase 6a update (bead claude_verilog_test-ckc): the APB bridge window was
extended from 0x2000_9FFF to 0x2000_AFFF (soc_periph_map_pkg.sv
AXIL_APB_LIMIT / soc_addr_map_pkg.sv PERIPH_LIMIT) to add the GPIO slot at
0x2000_A000-AFFF, following the exact same pattern as the earlier PLL2-, PMU-
and PLL-slot extensions.

Phase 6 update (bead claude_verilog_test-f7vs.2): the APB bridge window was
extended again, from 0x2000_AFFF to 0x2001_0FFF (soc_periph_map_pkg.sv
AXIL_APB_LIMIT / soc_addr_map_pkg.sv PERIPH_LIMIT), pre-allocating the full
14-slot APB sub-map in one commit (docs/PHASE6_IP_EXPANSION_PLAN.md §4):
PWM/WDT/TRNG/I2C/CRYPTO/NPU at 0x2000_B000-0x2001_0FFF. Only the first 8 APB
slots (through GPIO) are wired to real slaves — APB_N_SLAVES stays 8 — so an
address in the new reserved range (e.g. 0x2000_B000, PWM's slot) is now
in-window at the AXI-Lite ring level and routes to the APB-bridge proxy slave
without DECERR-ing. The next person who extends this window again should
update BAD_HIGH below (and the docstrings that reference the current limit)
the same way.

Verifies rtl/soc/axi_lite_interconnect.sv + rtl/soc/axi_lite_register_bank.sv
together: per-slave routing, cross-slave isolation, DECERR on unmapped
addresses, and master-side backpressure.

Unmapped addresses (DECERR):
    0x2000_0000 — below GPU base (CPU-debug APB gap)
    0x2001_1000 — above the APB bridge limit (0x2001_0FFF, full 14-slot
                  reserved window included)

In-window-but-reserved addresses (OKAY at this ring level, NOT SLVERR):
    0x2000_B000 — PWM's reserved APB slot. Note: apb_interconnect.sv's own
                  default-SLVERR-for-unclaimed-slot behaviour (the real APB
                  sub-decode) is NOT exercised by this testbench — this DUT
                  (tb_axi_lite_interconnect) never instantiates
                  apb_interconnect.sv or axil_to_apb.sv; the "apb_bridge"
                  slot here is a generic axi_lite_register_bank stub that
                  always returns OKAY for any in-window address (see that
                  module's own header comment: "Out-of-range word addresses
                  complete with OKAY"). See test_reserved_slot_in_window
                  below.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from bfm.axi4lite_master import AXI4LiteMaster

CLK_PERIOD_NS = 2

RESP_OKAY = 0
RESP_DECERR = 3

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
# Phase 6 / bead claude_verilog_test-f7vs.2: bridge window now extends
# through the full 14-slot reserved APB sub-map (soc_periph_map_pkg.
# AXIL_APB_LIMIT = 0x2001_0FFF), so 0x2000_B000 -- the old BAD_HIGH -- is
# now legitimately in-window (OKAY at this ring level) rather than DECERR.
# (Same thing happened at Phase 6a / bead ckc for the GPIO slot, at GH #92
# for the PLL2 slot, at GH #100/#101 for the PMU slot, and before that for
# the PLL slot.) BAD_HIGH must stay one slot above whatever AXIL_APB_LIMIT
# currently is; kept hardcoded rather than derived from the SV package
# (see test_decerr_unmapped docstring for why) so bump this by hand,
# matching this same edit, the next time the APB window grows.
BAD_HIGH = 0x2001_1000   # above APB bridge limit 0x2001_0FFF (full 14-slot window included)

# In-window-but-reserved: PWM's slot (index 8 of the 14-slot APB sub-map) has
# no APB slave built yet, but is inside AXIL_APB_LIMIT, so it must NOT DECERR
# at this ring level. See test_reserved_slot_in_window.
RESERVED_UNBUILT = 0x2000_B000   # PWM slot — reserved, not yet a real APB slave


async def _setup(dut):
    """Start clock, reset, build the CPU-side AXI4-Lite master."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
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
    14-slot reserved sub-map, Phase 6 / bead f7vs.2) and returns OKAY at
    this ring level -- see test_reserved_slot_in_window -- same pattern as
    0x2000_A000 becoming mapped when the GPIO slot was added (Phase 6a /
    bead ckc), 0x2000_9000 when the PLL2 slot was added (GH #92),
    0x2000_8000 when the PMU slot was added (GH #100/#101), and
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

    apb_interconnect.sv:104-110 defines the real APB sub-decode: psel_i=1 but
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
# GH #222 W5 (bead kp61): AxPROT routing.
#
# axi_lite_interconnect forwards AWPROT/ARPROT to the selected slave only
# (axi_lite_interconnect.sv:159 `_s_awprot[wsel] = m_axil_awprot`, :287 `_s_arprot[rsel] =
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
