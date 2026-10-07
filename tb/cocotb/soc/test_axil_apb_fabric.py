"""
Bead claude_verilog_test-8riq (GH #216 coverage gap) -- AXI-Lite / APB control-fabric tests.

DUT: tb_axil_apb_fabric -- the real chain axi_lite_interconnect -> axil_to_apb -> apb_interconnect
(see the wrapper header for the address map), with a cocotb-scripted AXI-Lite slave on ring slot 0
and a cocotb-scripted APB slave on APB slot 2.  The other APB slots are real apb4_register_bank
instances.

What this closes (none of it was reachable with the existing register-bank stub slaves, which are
always ready and always OKAY):

  * ready/valid backpressure on every channel of axi_lite_interconnect (AW / W / AR held low by
    the slave, B / R held low by the master), including payload and valid stability while stalled;
  * SLVERR and DECERR actually leaving the slave side, crossing the ring response mux and being
    seen by the master, for writes and reads, with and without master stalls;
  * the ring's own DECERR (unmapped address) under the same stalls, and proof that no slave sees
    a beat of an unmapped access;
  * APB SLVERR end to end: a scripted APB slave's pslverr, and apb_interconnect's own pslverr for
    an in-window address no APB slave claims, both arriving as SLVERR at the AXI-Lite master;
  * pwdata / pstrb / pwrite / paddr routing through axil_to_apb + apb_interconnect to the right
    slave only, with APB wait states.

Spec / intent references: rtl/soc/axi_lite_interconnect.sv header ("Unmapped address -> DECERR ...
a bad config access never stalls the CPU", depth-1 outstanding, slave latched for the life of the
transaction), rtl/soc/axil_to_apb.sv header ("pslverr -> bresp/rresp = SLVERR"),
rtl/soc/apb_interconnect.sv header ("psel_i=1 but no slave addressed -> pslverr_o=1, pready_o=1,
prdata_o=0"), AMBA AXI valid-stability rule and APB4 SETUP/ACCESS phase rules.
"""

import cocotb
from axil_stall_bfm import ScriptedApbSlave, ScriptedSlave, StallMaster
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

CLK_PERIOD_NS = 2

OKAY, EXOKAY, SLVERR, DECERR = 0, 1, 2, 3

EXT_AXIL = 0x2000_1000     # ring slot 0 (scripted AXI-Lite slave)
BANK0 = 0x2000_2000        # APB slot 0 (real register bank)
BANK1 = 0x2000_3000        # APB slot 1 (real register bank)
EXT_APB = 0x2000_4000      # APB slot 2 (scripted APB slave)
UNCLAIMED = 0x2000_5000    # inside the bridge window, claimed by no APB slave
UNCLAIMED_END = 0x2000_7FFC
UNMAPPED_LOW = 0x2000_0000
UNMAPPED_HIGH = 0x2000_8000

_live = []   # helper objects of the previous test: their coroutines must not leak into the next


async def _setup(dut):
    for obj in _live:
        obj.stop()
    _live.clear()
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.rst_n.value = 0
    m = StallMaster(dut, "m_axil_", dut.clk)
    ext = ScriptedSlave(dut, "x_axil_", dut.clk)
    apb = ScriptedApbSlave(dut, "xp_", dut.clk)
    ext.start()
    apb.start()
    _live.extend([ext, apb])
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    return m, ext, apb


def _no_violations(*objs):
    for o in objs:
        assert not o.violations, f"{type(o).__name__} protocol violations: {o.violations}"


# ---------------------------------------------------------------------------
# axi_lite_interconnect: slave-side ready stalls (W_AW / W_DATA / R_AR with the handshake low)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ring_aw_stall(dut):
    """The slave holds awready low: the master must see awready low for the same time, the
    interconnect must keep awvalid + address stable at the slave, and the transfer must then
    complete once, with the right payload."""
    m, ext, _ = await _setup(dut)
    ext.aw_stall = 4
    t = await m.write(EXT_AXIL + 0x14, 0xA5A5_1234, strb=0x9)
    assert t.aw_wait >= 4, f"master saw only {t.aw_wait} awready-low edges (4-cycle slave stall)"
    assert ext.aw_beats == [EXT_AXIL + 0x14], f"AW beats at slave: {ext.aw_beats}"
    assert ext.w_beats == [(0xA5A5_1234, 0x9)], f"W beats at slave: {ext.w_beats}"
    assert t.resp == OKAY
    assert not t.resp_unstable
    _no_violations(ext)


@cocotb.test()
async def test_ring_w_stall(dut):
    """The slave holds wready low: same contract on the W channel (W_DATA with w_hs low)."""
    m, ext, _ = await _setup(dut)
    ext.w_stall = 5
    t = await m.write(EXT_AXIL + 0x08, 0xDEAD_BEEF, strb=0x6)
    assert t.w_wait >= 5, f"master saw only {t.w_wait} wready-low edges for a 5-cycle slave stall"
    assert ext.aw_beats == [EXT_AXIL + 0x08]
    assert ext.w_beats == [(0xDEAD_BEEF, 0x6)]
    assert t.resp == OKAY
    _no_violations(ext)


@cocotb.test()
async def test_ring_aw_and_w_stall_together(dut):
    m, ext, _ = await _setup(dut)
    ext.aw_stall, ext.w_stall = 3, 3
    t = await m.write(EXT_AXIL, 0x0123_4567)
    assert t.aw_wait >= 3 and t.w_wait >= 3
    assert ext.aw_beats == [EXT_AXIL] and ext.w_beats == [(0x0123_4567, 0xF)]
    _no_violations(ext)


@cocotb.test()
async def test_ring_ar_stall(dut):
    """The slave holds arready low (R_AR with ar_hs low); the read must still return the slave's
    data and OKAY exactly once."""
    m, ext, _ = await _setup(dut)
    ext.ar_stall = 4
    ext.rdata_value = 0xCAFE_F00D
    t = await m.read(EXT_AXIL + 0x20)
    assert t.ar_wait >= 4, f"master saw only {t.ar_wait} arready-low edges (4-cycle slave stall)"
    assert ext.ar_beats == [EXT_AXIL + 0x20]
    assert (t.resp, t.data) == (OKAY, 0xCAFE_F00D)
    _no_violations(ext)


@cocotb.test()
async def test_ring_slow_slave_responses(dut):
    """Slave answers late (b_delay / r_delay): the ring must wait, not time out or invent a
    response, and the late data must arrive intact."""
    m, ext, _ = await _setup(dut)
    ext.b_delay, ext.r_delay = 9, 9
    ext.rdata_value = 0x1357_9BDF
    t = await m.write(EXT_AXIL, 0x1)
    assert t.resp == OKAY
    t = await m.read(EXT_AXIL)
    assert (t.resp, t.data) == (OKAY, 0x1357_9BDF)
    _no_violations(ext)


@cocotb.test()
async def test_ring_aw_w_ordering(dut):
    """W before AW and AW before W from the master: each channel completes exactly once with its own
    payload, the response comes only after both."""
    m, ext, _ = await _setup(dut)
    t = await m.write(EXT_AXIL + 4, 0x1111_1111, w_delay=0, aw_delay=6)
    assert t.resp == OKAY
    t = await m.write(EXT_AXIL + 8, 0x2222_2222, w_delay=6, aw_delay=0)
    assert t.resp == OKAY
    assert ext.aw_beats == [EXT_AXIL + 4, EXT_AXIL + 8]
    assert ext.w_beats == [(0x1111_1111, 0xF), (0x2222_2222, 0xF)]
    _no_violations(ext)


# ---------------------------------------------------------------------------
# Error responses leaving a slave and reaching the master
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ring_slave_error_responses_reach_master(dut):
    """bresp/rresp from the slave pass through the ring's response mux verbatim (EXOKAY, SLVERR,
    DECERR), with the master stalling its ready: valid and payload stay stable, and the next
    OKAY transaction is not polluted by the previous error."""
    m, ext, _ = await _setup(dut)
    ext.rdata_value = 0x600D_DA7A
    for code in (EXOKAY, SLVERR, DECERR):
        ext.bresp_code = code
        t = await m.write(EXT_AXIL, 0xBAD0_0000 | code, b_stall=3)
        assert t.resp == code, f"slave bresp {code} reached the master as {t.resp}"
        assert t.resp_wait >= 3 and not t.resp_unstable, t.resp_unstable
        ext.rresp_code = code
        t = await m.read(EXT_AXIL, r_stall=3)
        assert t.resp == code, f"slave rresp {code} reached the master as {t.resp}"
        assert t.data == 0x600D_DA7A, f"read data lost on an error response: {t.data:#x}"
        assert t.resp_wait >= 3 and not t.resp_unstable, t.resp_unstable
    ext.bresp_code = ext.rresp_code = OKAY
    t = await m.write(EXT_AXIL, 0x1)
    assert t.resp == OKAY, "an earlier error response leaked into the next write"
    t = await m.read(EXT_AXIL)
    assert t.resp == OKAY, "an earlier error response leaked into the next read"
    _no_violations(ext)


# ---------------------------------------------------------------------------
# The ring's own DECERR (unmapped address)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ring_decerr_with_master_stalls(dut):
    """Unmapped write and read complete with DECERR (the master never hangs), the DECERR response is
    held stable while the master withholds bready/rready, read data is 0, and not one beat of the
    access reaches any slave."""
    m, ext, apb = await _setup(dut)
    for bad in (UNMAPPED_LOW, UNMAPPED_LOW + 0x10, UNMAPPED_HIGH, 0xFFFF_FFFC):
        t = await m.write(bad, 0xDEAD_0000, b_stall=4)
        assert t.resp == DECERR, f"write {bad:#x}: resp {t.resp}"
        assert t.resp_wait >= 4 and not t.resp_unstable, t.resp_unstable
        t = await m.read(bad, r_stall=4)
        assert (t.resp, t.data) == (DECERR, 0), f"read {bad:#x}: resp {t.resp} data {t.data:#x}"
        assert t.resp_wait >= 4 and not t.resp_unstable, t.resp_unstable
    # AW and W arriving far apart at an unmapped address: engine absorbs both, then answers.
    t = await m.write(UNMAPPED_HIGH, 0x1, aw_delay=0, w_delay=7)
    assert t.resp == DECERR
    t = await m.write(UNMAPPED_HIGH, 0x1, aw_delay=7, w_delay=0)
    assert t.resp == DECERR
    assert not ext.aw_beats and not ext.w_beats and not ext.ar_beats, (
        f"an unmapped access leaked to ring slot 0: {ext.aw_beats} {ext.w_beats} {ext.ar_beats}")
    assert not apb.accesses, f"an unmapped access leaked to the APB subtree: {apb.accesses}"
    # The engines are back in IDLE: a legal access still works.
    ext.rdata_value = 0x42
    t = await m.read(EXT_AXIL)
    assert (t.resp, t.data) == (OKAY, 0x42)


# ---------------------------------------------------------------------------
# axil_to_apb + apb_interconnect + apb4_register_bank, end to end
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_apb_write_data_routing_and_isolation(dut):
    """pwdata / pstrb / pwrite / paddr reach the addressed APB slave and only that slave."""
    m, _, _ = await _setup(dut)
    seen_psel = set()

    async def watch():
        while True:
            await RisingEdge(dut.clk)
            seen_psel.add(int(dut.apb_psel_o.value))

    w = cocotb.start_soon(watch())
    for reg in range(8):
        for base, tag in ((BANK0, 0xA0), (BANK1, 0xB0)):
            t = await m.write(base + 4 * reg, (tag << 24) | (reg << 8) | tag, strb=0xF)
            assert t.resp == OKAY
    for reg in range(8):
        for base, tag in ((BANK0, 0xA0), (BANK1, 0xB0)):
            t = await m.read(base + 4 * reg)
            assert (t.resp, t.data) == (OKAY, (tag << 24) | (reg << 8) | tag), (
                f"bank@{base:#x} reg{reg}: {t.data:#x}")
    # Byte strobes survive both bridges: clear only byte 1 / bytes 0 and 3.
    await m.write(BANK0 + 4, 0xFFFF_FFFF)
    await m.write(BANK0 + 4, 0x0000_0000, strb=0b0010)
    t = await m.read(BANK0 + 4)
    assert t.data == 0xFFFF_00FF, f"strobe 0b0010 wrote {t.data:#010x}"
    await m.write(BANK0 + 4, 0x0000_0000, strb=0b1001)
    t = await m.read(BANK0 + 4)
    assert t.data == 0x00FF_0000, f"strobe 0b1001 left {t.data:#010x}"
    w.kill()
    assert seen_psel <= {0b000, 0b001, 0b010}, f"unexpected psel pattern(s) {sorted(seen_psel)}"
    assert 0b001 in seen_psel and 0b010 in seen_psel
    # Neither bank saw an access meant for the other: bank1 still holds its own data.
    t = await m.read(BANK1 + 4)
    assert t.data == (0xB0 << 24) | (1 << 8) | 0xB0


@cocotb.test()
async def test_apb_ext_slave_wait_states_and_payload(dut):
    """The scripted APB slave sees the exact write payload, after SETUP+ACCESS with wait states;
    the bridge holds the transfer until pready; read data comes back from the slave."""
    m, _, apb = await _setup(dut)
    apb.wait_states = 3
    t = await m.write(EXT_APB + 0x10, 0xDEAD_BEEF, strb=0xA)
    assert t.resp == OKAY
    assert apb.accesses == [(1, EXT_APB + 0x10, 0xDEAD_BEEF, 0xA)], apb.accesses
    apb.rdata_value = 0x1234_5678
    apb.wait_states = 5
    t = await m.read(EXT_APB + 0x24)
    assert (t.resp, t.data) == (OKAY, 0x1234_5678)
    assert apb.accesses[-1][:2] == (0, EXT_APB + 0x24)
    _no_violations(apb)


@cocotb.test()
async def test_apb_slverr_end_to_end(dut):
    """An APB slave's pslverr arrives at the AXI-Lite master as SLVERR for writes and reads
    (with and without wait states, with the master stalling bready/rready so S_WRESP/S_RRESP are
    held), and is not sticky."""
    m, _, apb = await _setup(dut)
    apb.slverr = 1
    for waits in (0, 3):
        apb.wait_states = waits
        t = await m.write(EXT_APB, 0x5, b_stall=3)
        assert t.resp == SLVERR, f"write, pslverr, waits={waits}: bresp {t.resp}"
        assert t.resp_wait >= 3 and not t.resp_unstable, t.resp_unstable
        t = await m.read(EXT_APB, r_stall=3)
        assert t.resp == SLVERR, f"read, pslverr, waits={waits}: rresp {t.resp}"
        assert not t.resp_unstable, t.resp_unstable
    apb.slverr = 0
    apb.wait_states = 0
    apb.rdata_value = 0x77
    t = await m.write(EXT_APB, 0x6)
    assert t.resp == OKAY, "SLVERR from the previous transfer stuck in the bridge"
    t = await m.read(EXT_APB)
    assert (t.resp, t.data) == (OKAY, 0x77)
    _no_violations(apb)


@cocotb.test()
async def test_apb_unclaimed_slot_slverr(dut):
    """An address inside the bridge window that no APB slave claims (a reserved slot) is answered
    by apb_interconnect with pslverr, which must come out as SLVERR (not DECERR, not a hang) with
    read data 0, and no APB slave is selected."""
    m, _, apb = await _setup(dut)
    seen_psel = set()

    async def watch():
        while True:
            await RisingEdge(dut.clk)
            seen_psel.add(int(dut.apb_psel_o.value))

    # Pre-load a bank so a mis-routed read would be visible as non-zero data.
    await m.write(BANK0, 0xFFFF_FFFF)
    w = cocotb.start_soon(watch())
    for addr in (UNCLAIMED, UNCLAIMED + 0x800, UNCLAIMED_END):
        t = await m.write(addr, 0xBAD0_BAD0, b_stall=2)
        assert t.resp == SLVERR, f"write {addr:#x}: bresp {t.resp}"
        assert not t.resp_unstable, t.resp_unstable
        t = await m.read(addr, r_stall=2)
        assert (t.resp, t.data) == (SLVERR, 0), f"read {addr:#x}: rresp {t.resp} data {t.data:#x}"
    w.kill()
    assert seen_psel == {0b000}, f"unclaimed access selected an APB slave: {sorted(seen_psel)}"
    assert not apb.accesses
    t = await m.read(BANK0)
    assert (t.resp, t.data) == (OKAY, 0xFFFF_FFFF), "bank corrupted by an unclaimed-slot write"


@cocotb.test()
async def test_ring_engines_independent(dut):
    """The write and read engines are independent: a read to the APB side completes while a write to
    a slow slave on the other ring slot is still waiting for its B response."""
    m, ext, _ = await _setup(dut)
    ext.b_delay = 25
    await m.write(BANK0 + 0x0C, 0x0C0C_0C0C)       # preload via the bridge
    wr_done = []

    async def slow_write():
        t = await m.write(EXT_AXIL, 0x1)
        wr_done.append(t)

    w = cocotb.start_soon(slow_write())
    for _ in range(4):
        await RisingEdge(dut.clk)
    t = await m.read(BANK0 + 0x0C)
    assert (t.resp, t.data) == (OKAY, 0x0C0C_0C0C)
    assert not wr_done, "the read had to wait for an unrelated slow write"
    await w
    assert wr_done[0].resp == OKAY
    _no_violations(ext)


@cocotb.test()
async def test_ring_unmapped_read_single_beat(dut):
    """REGRESSION GUARD for fixed RTL bug claude_verilog_test-3xtv.

    One AR to an unmapped address with rready tied high must produce exactly ONE R beat (DECERR,
    data 0), and the next legal read must return its own data.  Before the 3xtv fix
    axi_lite_interconnect returned the DECERR beat twice (rvalid high on two consecutive cycles
    with no second request), and the phantom beat answered the next read.  The assertions below
    are the spec; do NOT weaken them.
    """
    m, ext, _ = await _setup(dut)
    ext.rdata_value = 0x5AFE_C0DE
    dut.m_axil_rready.value = 1
    dut.m_axil_araddr.value = UNMAPPED_LOW
    dut.m_axil_arvalid.value = 1
    beats = []
    ar_done = False
    for _ in range(14):
        await RisingEdge(dut.clk)
        if not ar_done and int(dut.m_axil_arready.value):
            ar_done = True
            dut.m_axil_arvalid.value = 0
        if int(dut.m_axil_rvalid.value) and int(dut.m_axil_rready.value):
            beats.append((int(dut.m_axil_rresp.value), int(dut.m_axil_rdata.value)))
    dut._log.info(f"unmapped AR with rready=1 produced R beats (resp, data): {beats}")
    assert ar_done, "AR was never accepted"
    assert beats and beats[0] == (DECERR, 0), f"first R beat wrong: {beats}"
    assert len(beats) == 1, f"one unmapped AR produced {len(beats)} R beats: {beats}"
    dut.m_axil_rready.value = 0
    t = await m.read(EXT_AXIL)
    assert (t.resp, t.data) == (OKAY, 0x5AFE_C0DE), (
        f"next legal read got resp {t.resp} data {t.data:#x} (a phantom DECERR beat answered it)")
