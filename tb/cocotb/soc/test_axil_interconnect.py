"""
Phase 5 (M3) — AXI4-Lite control-interconnect unit tests.

Verifies rtl/soc/axi_lite_interconnect.sv + rtl/soc/axi_lite_register_bank.sv
together (via tb_axi_lite_interconnect): per-slave routing, cross-slave
isolation, response steering, DECERR on unmapped addresses, and master-side
backpressure (response held while the master stalls bready/rready).

Topology: one CPU master ("m_axil_") x 7 register-bank slaves (Phase 7 M-c +1 PLL).
Slave map (soc_periph_map_pkg):
    GPU 0x2000_1000  UART 0x2000_2000  SPI 0x2000_3000
    Timer 0x2000_4000  DMA 0x2000_5000  IRQ 0x2000_6000  PLL 0x2000_7000
    unmapped (DECERR): 0x2000_0000 (gap below GPU), 0x2000_8000 (above PLL)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from bfm.axi4lite_master import AXI4LiteMaster

CLK_PERIOD_NS = 2

RESP_OKAY = 0
RESP_DECERR = 3

# Slave base addresses (reg0 of each bank lives at base + 0x0).
SLAVES = {
    "gpu":   0x2000_1000,
    "uart":  0x2000_2000,
    "spi":   0x2000_3000,
    "timer": 0x2000_4000,
    "dma":   0x2000_5000,
    "irq":   0x2000_6000,
}
BAD_LOW  = 0x2000_0000   # below the ring (CPU-debug gap, below GPU at 0x2000_1000)
BAD_HIGH = 0x2000_8000   # above the ring (PLL limit is 0x2000_7FFF; Phase 7 M-c added slot 6)


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
    """Write a distinct value to reg0 of every slave, then read all back.

    Correct read-back of each slave's own value proves both routing (the write
    reached the addressed slave) and isolation (no slave saw another's write).
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
    """Routing holds across multiple registers within one slave."""
    m = await _setup(dut)
    base = SLAVES["uart"]
    vals = {0x0: 0x11111111, 0x4: 0x22222222, 0x8: 0x33333333}
    for off, v in vals.items():
        assert await m.write(base + off, v) == RESP_OKAY
    for off, v in vals.items():
        data, _ = await m.read(base + off)
        assert data == v, f"uart+{off:#x} = {data:#x}"
    dut._log.info("multi-register routing OK")


@cocotb.test()
async def test_decerr_unmapped(dut):
    """Unmapped addresses return DECERR and complete (never hang)."""
    m = await _setup(dut)
    for bad in (BAD_LOW, BAD_HIGH):
        resp = await m.write(bad, 0xDEAD)
        assert resp == RESP_DECERR, f"write {bad:#x} resp {resp}"
        data, rresp = await m.read(bad)
        assert rresp == RESP_DECERR, f"read {bad:#x} resp {rresp}"
        assert data == 0, f"DECERR read data {data:#x}"
    # A good transaction still works after DECERR (engine returned to idle).
    assert await m.write(SLAVES["spi"], 0xBEEF) == RESP_OKAY
    data, _ = await m.read(SLAVES["spi"])
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

    addr = SLAVES["timer"] + 0x0
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
