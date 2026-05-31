"""
Phase 5 (M3) — AXI4-Lite register-bank unit tests.

Verifies rtl/soc/axi_lite_register_bank.sv (via tb_axi_lite_register_bank):
read/write round-trip, per-register WMASK (read-only + partial), wstrb byte
lanes, the hardware status-injection path (bypasses WMASK), and out-of-range
addressing (completes OKAY, write dropped / read 0).

Register layout (N_REGS = 8, byte addr = idx*4):
    reg0..reg5 : fully SW-writable
    reg6 @0x18 : SW read-only, HW-writable (status)
    reg7 @0x1C : low-byte writable only (WMASK 0x000000FF)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from bfm.axi4lite_master import AXI4LiteMaster

CLK_PERIOD_NS = 2

REG0 = 0x00
REG6 = 0x18    # read-only / status
REG7 = 0x1C    # low-byte writable
OOR  = 0x100   # word 64 >= N_REGS -> out of range

RESP_OKAY = 0


async def _setup(dut):
    """Start clock, reset, build AXI4-Lite master. Returns the master."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.hw_status_wen.value = 0
    dut.hw_status_wdata.value = 0
    dut.rst_n.value = 0
    m = AXI4LiteMaster(dut, "s_axil_", dut.clk)
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    return m


@cocotb.test()
async def test_rw_roundtrip(dut):
    m = await _setup(dut)
    resp = await m.write(REG0, 0xDEADBEEF)
    assert resp == RESP_OKAY, f"write resp {resp}"
    data, rresp = await m.read(REG0)
    assert rresp == RESP_OKAY
    assert data == 0xDEADBEEF, f"reg0 read {data:#x}"
    dut._log.info("rw round-trip OK")


@cocotb.test()
async def test_readonly_register(dut):
    """reg6 has WMASK=0: SW writes are dropped, read stays at reset (0)."""
    m = await _setup(dut)
    resp = await m.write(REG6, 0x12345678)
    assert resp == RESP_OKAY, "RO write must still ack OKAY"
    data, _ = await m.read(REG6)
    assert data == 0x00000000, f"RO reg changed to {data:#x}"
    dut._log.info("read-only WMASK OK")


@cocotb.test()
async def test_hw_status_injection(dut):
    """Hardware write bypasses WMASK and is visible to a SW read of reg6."""
    m = await _setup(dut)
    dut.hw_status_wdata.value = 0x00C0FFEE
    dut.hw_status_wen.value = 1
    await RisingEdge(dut.clk)
    dut.hw_status_wen.value = 0
    await RisingEdge(dut.clk)
    data, _ = await m.read(REG6)
    assert data == 0x00C0FFEE, f"HW status read {data:#x}"
    dut._log.info("HW status injection OK")


@cocotb.test()
async def test_wstrb_byte_lanes(dut):
    """Only strobed byte lanes update; reg starts at 0 after reset."""
    m = await _setup(dut)
    # Write all four bytes but strobe only the low lane.
    resp = await m.write(REG0, 0xAABBCCDD, strb=0x1)
    assert resp == RESP_OKAY
    data, _ = await m.read(REG0)
    assert data == 0x000000DD, f"wstrb low-lane got {data:#x}"

    # Now strobe the high lane only; low lane must persist.
    resp = await m.write(REG0, 0x11223344, strb=0x8)
    assert resp == RESP_OKAY
    data, _ = await m.read(REG0)
    assert data == 0x110000DD, f"wstrb high-lane got {data:#x}"
    dut._log.info("wstrb byte lanes OK")


@cocotb.test()
async def test_partial_wmask(dut):
    """reg7 WMASK=0x000000FF: only the low byte is SW-writable."""
    m = await _setup(dut)
    resp = await m.write(REG7, 0xFFFFFFFF)
    assert resp == RESP_OKAY
    data, _ = await m.read(REG7)
    assert data == 0x000000FF, f"partial WMASK got {data:#x}"
    dut._log.info("partial WMASK OK")


@cocotb.test()
async def test_out_of_range(dut):
    """Address beyond N_REGS completes OKAY: write dropped, read returns 0."""
    m = await _setup(dut)
    resp = await m.write(OOR, 0xDEADC0DE)
    assert resp == RESP_OKAY, f"OOR write resp {resp}"
    data, rresp = await m.read(OOR)
    assert rresp == RESP_OKAY, f"OOR read resp {rresp}"
    assert data == 0x00000000, f"OOR read {data:#x}"
    # In-range register untouched by the OOR write.
    data0, _ = await m.read(REG0)
    assert data0 == 0x00000000, f"reg0 disturbed: {data0:#x}"
    dut._log.info("out-of-range OK")
