"""Bead ej6j -- directed tests for rtl/soc/axilite_to_axi4.sv (GPU ifetch AXI4-Lite -> AXI4 adapter).

The adapter's AR skid buffer is the Phase 5 M9 handshake fix: the GPU compute unit raises
m_axil_if_arvalid for exactly ONE cycle (a scheduler pulse), but AXI4 rule A3-38 requires the AR
request on the crossbar side to stay valid, with a stable payload, until arready.  If the crossbar is
not ready in the pulse cycle the buffer must remember the address and keep driving it.  That hold path
(ar_hold_q / ar_addr_q) had never executed in any suite.

Intent checked:
  * one-cycle pulse + crossbar arready low for N cycles -> exactly ONE AR handshake later, with the
    pulsed address, even though the slave-side address bus is garbage by then; arvalid/payload stay
    stable until accepted; arvalid drops right after (no duplicate AR)
  * a protocol-legal master that holds arvalid is handled identically and sees arready exactly once
  * the buffer is empty again afterwards (the next request is not polluted by the held address)
  * fixed AR attributes (id = MASTER_ID, len 0, size 4 B, INCR) and the tied-off write channels
  * R channel is a pass-through: data, response (OKAY/SLVERR/DECERR) and rready backpressure
"""

import cocotb
from axi4_fabric_bfm import (BURST_INCR, DECERR, GARBAGE, OKAY, SLVERR, AxiSlave)
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

ADDR_A = 0x0000_1040
ADDR_B = 0x0000_2080
WIN = 14


async def _setup(dut, clock=True, **slave_kw):
    if clock:
        cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.s_axil_arvalid.value = 0
    dut.s_axil_araddr.value = 0
    dut.s_axil_rready.value = 1     # drain R beats by default so the slave returns to AR
    dut.m_axi_awready.value = 0
    dut.m_axi_wready.value = 0
    dut.m_axi_bvalid.value = 0
    dut.m_axi_bid.value = 0
    dut.m_axi_bresp.value = 0
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    slave = AxiSlave(dut, "m_axi_", dut.clk, **slave_kw)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    slave.start()
    return slave


async def _pulse_ar(dut, addr):
    """arvalid high for exactly one cycle, araddr garbage afterwards.  Returns whether the adapter
    accepted it in the pulse cycle (s_axil_arready sampled at that edge)."""
    dut.s_axil_araddr.value = addr
    dut.s_axil_arvalid.value = 1
    await RisingEdge(dut.clk)
    accepted = int(dut.s_axil_arready.value)
    dut.s_axil_arvalid.value = 0
    dut.s_axil_araddr.value = GARBAGE
    return accepted


async def _observe(dut, cycles):
    """Sample the crossbar-side AR channel and the slave-side arready for ``cycles`` edges."""
    rows = []
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        rows.append(dict(av=int(dut.m_axi_arvalid.value), ar=int(dut.m_axi_arready.value),
                         addr=int(dut.m_axi_araddr.value), sar=int(dut.s_axil_arready.value),
                         id=int(dut.m_axi_arid.value), ln=int(dut.m_axi_arlen.value),
                         sz=int(dut.m_axi_arsize.value), bu=int(dut.m_axi_arburst.value),
                         awv=int(dut.m_axi_awvalid.value), wv=int(dut.m_axi_wvalid.value),
                         br=int(dut.m_axi_bready.value)))
    return rows


@cocotb.test()
async def test_pulse_is_held_until_accepted(dut):
    """One-cycle ARVALID pulse, crossbar arready delayed: the skid buffer holds the request."""
    first = True
    for delay in (1, 2, 5, 9):
        slave = await _setup(dut, clock=first, ar_delay=delay)
        first = False
        acc = await _pulse_ar(dut, ADDR_A)
        rows = await _observe(dut, WIN)
        hs = [r for r in rows if r["av"] and r["ar"]]
        assert not acc, f"delay={delay}: arready was already high in the pulse cycle"
        assert len(slave.ar_log) == 1, f"delay={delay}: {len(slave.ar_log)} AR handshakes (expected exactly 1)"
        assert slave.ar_log[0]["addr"] == ADDR_A, f"delay={delay}: AR addr {slave.ar_log[0]['addr']:#x}"
        assert len(hs) == 1
        assert not slave.viol, f"delay={delay}: {slave.viol}"
        # held from the cycle after the pulse until accepted
        n_hold = 0
        for r in rows:
            if r["av"]:
                assert r["addr"] == ADDR_A, f"held AR address drifted to {r['addr']:#x}"
                n_hold += 1
                if r["ar"]:
                    break
        assert n_hold >= delay, f"held only {n_hold} cycles with arready delayed {delay}"
        after = rows[rows.index(hs[0]) + 1:]
        assert all(not r["av"] for r in after), "arvalid stayed high after the AR was accepted (duplicate AR)"
        # slave-side arready returned once, on the accepting cycle
        assert sum(r["sar"] for r in rows) == 1 and [r for r in rows if r["sar"]][0] is hs[0]
        for r in rows:
            assert (r["id"], r["ln"], r["sz"], r["bu"]) == (0, 0, 2, BURST_INCR), r
        slave.stop()


@cocotb.test()
async def test_no_stall_passes_straight_through(dut):
    """Crossbar ready in the pulse cycle: accepted immediately, nothing is buffered."""
    slave = await _setup(dut, ar_delay=0)
    acc = await _pulse_ar(dut, ADDR_A)
    assert acc, "adapter must return arready in the cycle the crossbar accepts"
    rows = await _observe(dut, 6)
    assert all(not r["av"] for r in rows), "no residual AR after a same-cycle accept"
    assert len(slave.ar_log) == 1 and slave.ar_log[0]["addr"] == ADDR_A


@cocotb.test()
async def test_buffer_is_empty_after_drain(dut):
    """After a held request drains, the next request is independent of the held address."""
    slave = await _setup(dut, ar_delay=4)
    await _pulse_ar(dut, ADDR_A)
    await _observe(dut, 12)                       # A accepted somewhere in here
    assert [a["addr"] for a in slave.ar_log] == [ADDR_A]
    # idle bus with a changing address must not produce a request
    for v in (ADDR_B, 0x1234, ADDR_A):
        dut.s_axil_araddr.value = v
        rows = await _observe(dut, 2)
        assert all(not r["av"] for r in rows), "buffer re-armed itself (stale ar_hold_q)"
    await _pulse_ar(dut, ADDR_B)
    await _observe(dut, 12)
    assert [a["addr"] for a in slave.ar_log] == [ADDR_A, ADDR_B], [hex(a["addr"]) for a in slave.ar_log]
    assert not slave.viol


@cocotb.test()
async def test_protocol_legal_master_that_holds_arvalid(dut):
    """A master that keeps arvalid until arready (AXI-Lite rule) must see arready exactly once."""
    first = True
    for delay in (0, 3, 7):
        slave = await _setup(dut, clock=first, ar_delay=delay)
        first = False
        dut.s_axil_araddr.value = ADDR_B
        dut.s_axil_arvalid.value = 1
        got = 0
        for i in range(30):
            await RisingEdge(dut.clk)
            if int(dut.s_axil_arready.value):
                got += 1
                dut.s_axil_arvalid.value = 0
                dut.s_axil_araddr.value = GARBAGE
                break
        assert got == 1, f"delay={delay}: never saw arready"
        await _observe(dut, 6)
        assert [a["addr"] for a in slave.ar_log] == [ADDR_B], f"delay={delay}"
        assert not slave.viol
        slave.stop()


@cocotb.test()
async def test_read_channel_passthrough(dut):
    """R is combinational pass-through: data, SLVERR/DECERR and rready backpressure reach the master."""
    def resp(kind, addr):
        return {ADDR_A: OKAY, ADDR_B: SLVERR, 0x3000: DECERR}.get(addr, OKAY)

    slave = await _setup(dut, resp_fn=resp, r_delay=2)
    slave.mem.update({ADDR_A: 0x1111_AAAA, ADDR_B: 0x2222_BBBB, 0x3000: 0x3333_CCCC})
    for addr, exp_resp in ((ADDR_A, OKAY), (ADDR_B, SLVERR), (0x3000, DECERR)):
        await _pulse_ar(dut, addr)
        stalled = 0
        snap = None
        for _ in range(40):
            dut.s_axil_rready.value = 1 if stalled >= 4 else 0
            await RisingEdge(dut.clk)
            if int(dut.s_axil_rvalid.value):
                cur = (int(dut.s_axil_rdata.value), int(dut.s_axil_rresp.value))
                assert snap is None or cur == snap, "R payload moved while rready was low"
                snap = cur
                assert int(dut.m_axi_rready.value) == (1 if stalled >= 4 else 0), "rready must pass through"
                if stalled >= 4:
                    break
                stalled += 1
        dut.s_axil_rready.value = 0
        assert snap == (slave.mem[addr], exp_resp), f"{addr:#x}: {snap}"
        await _observe(dut, 3)


@cocotb.test()
async def test_write_channels_tied_off(dut):
    """Write channels never request; spurious B beats are absorbed (bready=1) without side effects."""
    slave = await _setup(dut, ar_delay=2)
    await _pulse_ar(dut, ADDR_A)
    dut.m_axi_bvalid.value = 1
    dut.m_axi_bresp.value = SLVERR
    dut.m_axi_bid.value = 5
    rows = await _observe(dut, 10)
    dut.m_axi_bvalid.value = 0
    assert all(r["awv"] == 0 and r["wv"] == 0 and r["br"] == 1 for r in rows), "write channel not tied off"
    assert len(slave.ar_log) == 1


@cocotb.test()
async def test_reset_clears_held_request(dut):
    """A reset while a request is held drops it: no AR after reset."""
    slave = await _setup(dut, ar_delay=50)
    await _pulse_ar(dut, ADDR_A)
    rows = await _observe(dut, 4)
    assert all(r["av"] for r in rows), "request should still be held"
    slave.stop()
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    rows = await _observe(dut, 3)
    assert all(not r["av"] for r in rows), "held AR survived reset"
    dut.rst_n.value = 1
    rows = await _observe(dut, 6)
    assert all(not r["av"] for r in rows), "held AR reappeared after reset release"
