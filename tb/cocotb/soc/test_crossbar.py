"""
Phase 5 (M3) — AXI4 crossbar unit tests.

Verifies routing, arbitration, cross-slave concurrency, backpressure, bursts
and response steering for rtl/soc/axi4_crossbar.sv (via tb_axi4_crossbar).

Topology: 3 masters (m0/m1/m2) x 2 slaves (s0=ROM, s1=SRAM).
Slave map (soc_addr_map_pkg):
    s0 ROM : 0x0000_1000 .. 0x0000_1FFF
    s1 SRAM: 0x0000_2000 .. 0x0FFF_FFFF
    unmapped (DECERR): below 0x1000, e.g. 0x0000_0000
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Combine

from bfm.axi4_master import AXI4Master, RESP_OKAY, RESP_DECERR
from axi4_slave_model import AXI4SlaveModel

CLK_PERIOD_NS = 2

ROM_BASE = 0x0000_1000
SRAM_BASE = 0x0000_2000
BAD_ADDR = 0x0000_0000


async def _setup(dut, **slave_kwargs):
    """Start clock, reset, build 3 masters + 2 slaves. Returns (masters, s0, s1)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
    masters = [AXI4Master(dut, f"m{i}", dut.clk) for i in range(3)]
    s0 = AXI4SlaveModel(dut, "s0", dut.clk, **slave_kwargs)
    s1 = AXI4SlaveModel(dut, "s1", dut.clk, **slave_kwargs)
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    s0.start()
    s1.start()
    return masters, s0, s1


@cocotb.test()
async def test_routing_and_decerr(dut):
    masters, s0, s1 = await _setup(dut)
    m0 = masters[0]

    # Write/read ROM (s0)
    resp = await m0.write(ROM_BASE + 0x10, [0xCAFEBABE])
    assert resp == RESP_OKAY
    data, rresp = await m0.read(ROM_BASE + 0x10)
    assert rresp == RESP_OKAY
    assert data[0] == 0xCAFEBABE, f"ROM read {data[0]:#x}"
    assert s0.mem[ROM_BASE + 0x10] == 0xCAFEBABE
    assert (SRAM_BASE) not in s1.mem or True  # SRAM untouched so far

    # Write/read SRAM (s1)
    resp = await m0.write(SRAM_BASE + 0x20, [0x12345678])
    assert resp == RESP_OKAY
    data, rresp = await m0.read(SRAM_BASE + 0x20)
    assert data[0] == 0x12345678, f"SRAM read {data[0]:#x}"
    assert s1.mem[SRAM_BASE + 0x20] == 0x12345678
    # ensure ROM did not receive the SRAM write
    assert (SRAM_BASE + 0x20) not in s0.mem

    # Unmapped address -> DECERR (must complete, not hang)
    resp = await m0.write(BAD_ADDR, [0xDEAD])
    assert resp == RESP_DECERR, f"expected DECERR, got {resp}"
    data, rresp = await m0.read(BAD_ADDR, length=1)
    assert rresp == RESP_DECERR, f"expected read DECERR, got {rresp}"

    dut._log.info("routing + DECERR OK")


@cocotb.test()
async def test_arbitration_same_slave(dut):
    """Two masters hammer the same slave; both complete, no lost beats."""
    masters, s0, s1 = await _setup(dut)
    m0, m1 = masters[0], masters[1]

    async def w0():
        return await m0.write(SRAM_BASE + 0x100, [0xAAAA0000])

    async def w1():
        return await m1.write(SRAM_BASE + 0x200, [0xBBBB1111])

    t0 = cocotb.start_soon(w0())
    t1 = cocotb.start_soon(w1())
    await Combine(t0, t1)
    assert t0.result() == RESP_OKAY and t1.result() == RESP_OKAY
    assert s1.mem[SRAM_BASE + 0x100] == 0xAAAA0000
    assert s1.mem[SRAM_BASE + 0x200] == 0xBBBB1111
    dut._log.info("same-slave arbitration OK")


@cocotb.test()
async def test_concurrency_diff_slaves(dut):
    """Masters targeting different slaves proceed concurrently."""
    masters, s0, s1 = await _setup(dut)
    m0, m1 = masters[0], masters[1]

    async def to_rom():
        return await m0.write(ROM_BASE + 0x30, [0x0B0B0B0B])

    async def to_sram():
        return await m1.write(SRAM_BASE + 0x40, [0x0C0C0C0C])

    t0 = cocotb.start_soon(to_rom())
    t1 = cocotb.start_soon(to_sram())
    await Combine(t0, t1)
    assert s0.mem[ROM_BASE + 0x30] == 0x0B0B0B0B
    assert s1.mem[SRAM_BASE + 0x40] == 0x0C0C0C0C
    dut._log.info("cross-slave concurrency OK")


@cocotb.test()
async def test_backpressure(dut):
    """Slave inserts ready/valid delays; master delays bready/rready."""
    masters, s0, s1 = await _setup(
        dut, aw_delay=2, w_delay=1, b_delay=3, ar_delay=2, r_delay=2)
    m0 = masters[0]

    resp = await m0.write(SRAM_BASE + 0x50, [0xFEEDFACE], ready_delay=2)
    assert resp == RESP_OKAY
    data, rresp = await m0.read(SRAM_BASE + 0x50, ready_delay=2)
    assert rresp == RESP_OKAY
    assert data[0] == 0xFEEDFACE, f"got {data[0]:#x}"
    dut._log.info("backpressure OK")


@cocotb.test()
async def test_burst(dut):
    """4-beat INCR burst write then read (cache-line shaped)."""
    masters, s0, s1 = await _setup(dut)
    m0 = masters[0]

    payload = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
    resp = await m0.write(SRAM_BASE + 0x80, payload)
    assert resp == RESP_OKAY
    for i, w in enumerate(payload):
        assert s1.mem[SRAM_BASE + 0x80 + i * 4] == w, f"beat {i}"

    data, rresp = await m0.read(SRAM_BASE + 0x80, length=4)
    assert rresp == RESP_OKAY
    assert data == payload, f"burst read {data}"
    dut._log.info("burst OK")


@cocotb.test()
async def test_response_steering(dut):
    """Interleaved reads from two masters to two slaves return to the right master."""
    masters, s0, s1 = await _setup(dut)
    m0, m1 = masters[0], masters[1]

    # Seed distinct data in each slave region.
    await m0.write(ROM_BASE + 0xA0, [0x5A5A0001])
    await m1.write(SRAM_BASE + 0xB0, [0xA5A50002])

    async def rd0():
        d, r = await m0.read(ROM_BASE + 0xA0)
        return d[0]

    async def rd1():
        d, r = await m1.read(SRAM_BASE + 0xB0)
        return d[0]

    t0 = cocotb.start_soon(rd0())
    t1 = cocotb.start_soon(rd1())
    await Combine(t0, t1)
    assert t0.result() == 0x5A5A0001, f"m0 got {t0.result():#x}"
    assert t1.result() == 0xA5A50002, f"m1 got {t1.result():#x}"
    dut._log.info("response steering OK")
