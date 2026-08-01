"""
Phase 5 (M3) — AXI4-Lite control-interconnect unit tests.

APB migration PR-7 update: the AXI-Lite ring now has 3 slaves, not 6.
  s0 GPU         0x2000_1000 (register bank slot 0)
  s1 APB bridge  0x2000_2000 .. 0x2000_9FFF (register bank slot 1, proxy)
  s2 DMA         0x2000_5000 (register bank slot 2, last-match over bridge)

GH #92 update: the APB bridge window was extended
from 0x2000_8FFF to 0x2000_9FFF (soc_periph_map_pkg.sv AXIL_APB_LIMIT /
soc_addr_map_pkg.sv PERIPH_LIMIT) to add the PLL2 slot at 0x2000_9000-9FFF,
following the exact same pattern as the earlier PMU- and PLL-slot
extensions. The next person who extends this window again should update
BAD_HIGH below (and the docstrings that reference the current limit) the
same way.

Verifies rtl/soc/axi_lite_interconnect.sv + rtl/soc/axi_lite_register_bank.sv
together: per-slave routing, cross-slave isolation, DECERR on unmapped
addresses, and master-side backpressure.

Unmapped addresses (DECERR):
    0x2000_0000 — below GPU base (CPU-debug APB gap)
    0x2000_A000 — above the APB bridge limit (0x2000_9FFF, PLL2 slot included)
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
# GH #92: bridge window now extends through the PLL2 slot
# (soc_periph_map_pkg.AXIL_APB_LIMIT = 0x2000_9FFF), so 0x2000_9000 --
# the old BAD_HIGH -- is now legitimately mapped (OKAY) rather than
# DECERR. (Same thing happened at GH #100/#101 for the PMU slot, and
# before that for the PLL slot.) BAD_HIGH must stay one slot above
# whatever AXIL_APB_LIMIT currently is; kept hardcoded rather than
# derived from the SV package (see test_decerr_unmapped docstring for
# why) so bump this by hand, matching this same edit, the next time the
# APB window grows.
BAD_HIGH = 0x2000_A000   # above APB bridge limit 0x2000_9FFF (PLL2 slot included)


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
      BAD_HIGH = 0x2000_A000 — above APB bridge limit 0x2000_9FFF
    Note: 0x2000_9000 is now INSIDE the APB bridge window (PLL2 slot,
    GH #92) and returns OKAY -- same pattern as 0x2000_8000 becoming
    mapped when the PMU slot was added (GH #100/#101), and 0x2000_7000
    before that when the PLL slot was added.

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
