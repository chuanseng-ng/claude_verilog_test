"""Bead ej6j -- directed tests for rtl/soc/boot_rom.sv (behavioural AXI4 read-only boot ROM).

boot_rom is the first-fetch target after reset.  Its read path is exercised by every SoC boot suite
(which backdoor-load the array), but the WRITE path -- accept AW + W, never modify the ROM, answer
SLVERR -- and read-side backpressure (rready low mid-burst) never ran anywhere.

Intent checked (module header + AXI4):
  * a write burst of any length is fully accepted (AW, then every W beat -- never stalling the master
    forever), the ROM contents are untouched, and ONE B with SLVERR and the awid is returned only after
    the last W beat; B stays stable until bready
  * W is not accepted before AW; a second AW is not accepted while the first B is outstanding
  * read bursts return arlen+1 OKAY beats at consecutive word addresses, rid = arid, rlast on the last
    beat only, and survive rready being held low between beats (payload stable)
  * the word index is masked to the ROM depth (4 KB aliasing), and reads/writes run independently
"""

import cocotb
from axi4_fabric_bfm import OKAY, SLVERR, AxiMaster
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

ROM_BASE = 0x0000_1000
DEPTH = 1024


def _word(i):
    return 0xC0DE_0000 + (i << 4) + (i & 0xF)


async def _setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    master = AxiMaster(dut, "s_", dut.clk)
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    for i in range(64):
        dut.mem[i].value = _word(i)
    await RisingEdge(dut.clk)
    return master


def _rom(dut, n=64):
    return [int(dut.mem[i].value) for i in range(n)]


@cocotb.test()
async def test_write_burst_is_sunk_and_answered_slverr(dut):
    m = await _setup(dut)
    before = _rom(dut)
    for n, wid in ((1, 3), (2, 0xA), (4, 0x5), (8, 0xF)):
        t = await m.write(ROM_BASE + 0x10, [0xFFFF_0000 + k for k in range(n)], wid=wid)
        assert t.bresp == SLVERR, f"n={n}: ROM write must answer SLVERR, got {t.bresp}"
        assert t.bid == wid, f"n={n}: bid {t.bid} != awid {wid}"
        assert len(t.w_cycles) == n, f"n={n}: only {len(t.w_cycles)} W beats accepted (master would hang)"
        assert t.first_bvalid > t.w_cycles[-1], "B must follow the last W beat"
        assert not t.viol, t.viol
    assert _rom(dut) == before, "a write modified the read-only ROM"


@cocotb.test()
async def test_write_partial_strobes_do_not_modify_rom(dut):
    m = await _setup(dut)
    before = _rom(dut)
    for strb in (0x1, 0x6, 0x8, 0xF):
        t = await m.write(ROM_BASE, [0x1234_5678, 0x9ABC_DEF0], strb=strb)
        assert t.bresp == SLVERR
    assert _rom(dut) == before


@cocotb.test()
async def test_write_stalls_hold_b_stable(dut):
    """bready low for several cycles and W beats arriving with gaps: B stable, awready low meanwhile."""
    m = await _setup(dut)
    mon = {"awready_during_b": 0, "stop": False}

    async def watch():
        while not mon["stop"]:
            await RisingEdge(dut.clk)
            if int(dut.s_bvalid.value) and int(dut.s_awready.value):
                mon["awready_during_b"] += 1

    cocotb.start_soon(watch())
    t = await m.write(ROM_BASE + 0x20, [1, 2, 3, 4], wid=9, w_gaps=[0, 3, 0, 5], b_stall=8, aw_delay=2)
    mon["stop"] = True
    assert t.bresp == SLVERR and t.bid == 9
    assert t.b_wait == 8, f"B stalled {t.b_wait}"
    assert not t.viol, t.viol
    assert mon["awready_during_b"] == 0, "a second AW would be accepted while the first B is pending"


@cocotb.test()
async def test_w_before_aw_is_not_consumed(dut):
    m = await _setup(dut)
    t = await m.write(ROM_BASE, [7, 8], aw_delay=6, w_before_aw=True)
    assert t.w_cycles[0] > t.aw_cycle, (
        f"W accepted at edge {t.w_cycles[0]} before the AW handshake at {t.aw_cycle}")
    assert t.bresp == SLVERR and not t.viol


@cocotb.test()
async def test_read_burst_and_rready_stalls(dut):
    m = await _setup(dut)
    for n, stalls, rid in ((1, 0, 1), (4, [0, 3, 0, 2], 6), (4, 5, 0xC), (16, [1] * 16, 2)):
        base = ROM_BASE + 0x40
        t = await m.read(base, n, rid=rid, r_stalls=stalls)
        exp = [_word(((base - ROM_BASE) >> 2) + k) for k in range(n)]
        assert t.data == exp, f"n={n}: {[hex(d) for d in t.data]}"
        assert t.resps == [OKAY] * n
        assert all(b[3] == rid for b in t.beats), "rid must echo arid on every beat"
        assert [b[2] for b in t.beats] == [0] * (n - 1) + [1]
        assert not t.viol, t.viol


@cocotb.test()
async def test_read_index_is_masked_to_rom_depth(dut):
    """Documented aliasing: the word index is masked to the ROM depth, so +4 KB reads the same word."""
    m = await _setup(dut)
    a = await m.read(ROM_BASE + 0x8, 2)
    b = await m.read(ROM_BASE + 0x8 + 4 * DEPTH, 2)
    # idx = addr[11:2]: ROM_BASE (0x1000) maps to word 0, so +0x8 is word 2
    assert a.data == b.data == [_word(2), _word(3)], ([hex(d) for d in a.data], [hex(d) for d in b.data])


@cocotb.test()
async def test_read_and_write_are_independent(dut):
    m = await _setup(dut)
    wr = cocotb.start_soon(m.write(ROM_BASE + 0x80, [1, 2, 3, 4], wid=4, b_stall=6, w_gaps=[0, 2, 2, 2]))
    rd = cocotb.start_soon(m.read(ROM_BASE + 0x20, 8, rid=8, r_stalls=[1, 0, 2, 0, 3, 0, 1, 0]))
    tw, tr = await wr, await rd
    assert tw.bresp == SLVERR and tw.bid == 4
    assert tr.data == [_word(8 + k) for k in range(8)] and all(b[3] == 8 for b in tr.beats)
    assert not tw.viol and not tr.viol
