"""
Phase 5 (APB migration PR-1) — axil_to_apb bridge unit tests.

Verifies rtl/soc/axil_to_apb.sv (via tb_axil_to_apb) against the 6 directed
tests specified for bead claude_verilog_test-o4p.

The DUT is the AXI4-Lite → APB4 bridge wired to an apb4_register_bank slave.
Tests drive the AXI4-Lite port via AXI4LiteMaster BFM and observe:
  - AXI write response (bresp) and read response (rresp / rdata)
  - APB SETUP and ACCESS phase ordering (sampled from internal bridge signals
    via cocotb .value accessors on the bridge instance)
  - SLVERR propagation using the force_slverr TB port

Tests:
    T1  test_write_roundtrip            — AXI write → APB SETUP/ACCESS → bresp OKAY
    T2  test_read_roundtrip             — AXI read → APB SETUP/ACCESS → rdata/rresp OKAY
    T3  test_pslverr_propagation        — force_slverr=1 → bresp/rresp = SLVERR (2'b10)
    T4  test_aw_before_w               — AW arrives one cycle before W; bridge buffers AW
    T5  test_w_before_aw               — W arrives one cycle before AW; bridge buffers W
    T6  test_back_to_back_write_read   — back-to-back write then read; read waits for write
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from bfm.axi4lite_master import AXI4LiteMaster

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2

REG0 = 0x00
REG1 = 0x04

RESP_OKAY   = 0   # AXI_RESP_OKAY
RESP_SLVERR = 2   # AXI_RESP_SLVERR


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------
async def _setup(dut):
    """Start clock, reset, init force_slverr and HW ports. Return AXI4LiteMaster."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.force_slverr.value    = 0
    dut.hw_status_wen.value   = 0
    dut.hw_status_wdata.value = 0
    dut.rst_n.value = 0
    m = AXI4LiteMaster(dut, "s_axil_", dut.clk)
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    return m


# ---------------------------------------------------------------------------
# T1 — AXI-Lite write round-trip: bresp OKAY, APB SETUP then ACCESS
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_write_roundtrip(dut):
    """
    Issue one AXI4-Lite write.  Verify:
      - bresp = OKAY (0)
      - APB SETUP phase observed (psel=1, penable=0) before ACCESS
      - APB ACCESS phase observed (psel=1, penable=1) with pready=1
      - Data visible in the register bank via a subsequent AXI read
    """
    m = await _setup(dut)

    # Start the write and observe APB signalling while it completes
    write_task = cocotb.start_soon(m.write(REG0, 0xA5A5A5A5))

    # Allow the write to begin — wait for psel to go high
    for _ in range(20):
        await RisingEdge(dut.clk)
        psel    = int(dut.u_bridge.psel.value)
        penable = int(dut.u_bridge.penable.value)
        if psel and not penable:
            dut._log.info("APB SETUP observed: psel=1 penable=0")
            # Next cycle should be ACCESS
            await RisingEdge(dut.clk)
            assert int(dut.u_bridge.psel.value)    == 1, "psel dropped before ACCESS"
            assert int(dut.u_bridge.penable.value) == 1, "penable not 1 in ACCESS"
            break
    else:
        raise AssertionError("APB SETUP phase not observed within 20 cycles")

    bresp = await write_task
    assert bresp == RESP_OKAY, f"write bresp {bresp} expected OKAY(0)"

    # Read back
    data, rresp = await m.read(REG0)
    assert rresp == RESP_OKAY,    f"read rresp {rresp} expected OKAY"
    assert data  == 0xA5A5A5A5,  f"read {data:#010x} expected 0xA5A5A5A5"
    dut._log.info("write round-trip: SETUP/ACCESS observed, bresp OKAY OK")


# ---------------------------------------------------------------------------
# T2 — AXI-Lite read round-trip: rdata and rresp OKAY
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_read_roundtrip(dut):
    """
    Write a value then read it back through the bridge.
    rdata must match; rresp must be OKAY (0).
    """
    m = await _setup(dut)
    bresp = await m.write(REG1, 0x12345678)
    assert bresp == RESP_OKAY, f"write bresp {bresp}"
    data, rresp = await m.read(REG1)
    assert rresp == RESP_OKAY,   f"rresp {rresp} expected OKAY"
    assert data  == 0x12345678, f"rdata {data:#010x} expected 0x12345678"
    dut._log.info("read round-trip: rdata/rresp OKAY OK")


# ---------------------------------------------------------------------------
# T3 — pslverr=1 propagates to AXI bresp/rresp = SLVERR
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pslverr_propagation(dut):
    """
    Assert force_slverr=1 to override the APB slave pslverr output.
    The bridge must translate pslverr=1 → bresp=SLVERR (2'b10) for writes
    and rresp=SLVERR (2'b10) for reads.
    """
    m = await _setup(dut)

    # Write with pslverr forced
    dut.force_slverr.value = 1
    bresp = await m.write(REG0, 0xDEADBEEF)
    dut.force_slverr.value = 0
    assert bresp == RESP_SLVERR, \
        f"write bresp {bresp} expected SLVERR(2) when pslverr=1"

    # Read with pslverr forced
    dut.force_slverr.value = 1
    data, rresp = await m.read(REG0)
    dut.force_slverr.value = 0
    assert rresp == RESP_SLVERR, \
        f"read rresp {rresp} expected SLVERR(2) when pslverr=1"

    dut._log.info("pslverr→SLVERR propagation (write+read) OK")


# ---------------------------------------------------------------------------
# T4 — AW arrives before W: bridge buffers AW and waits for W
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_aw_before_w(dut):
    """
    Drive AW channel one cycle before W channel.  The bridge must:
      - Accept AW (awready) when AW is presented (state=IDLE, aw_cap clear)
      - Hold off APB SETUP until W also arrives
      - Complete write with bresp OKAY
    """
    await _setup(dut)

    # Drive AW, withhold W
    dut.s_axil_awaddr.value  = REG0
    dut.s_axil_awprot.value  = 0
    dut.s_axil_awvalid.value = 1
    dut.s_axil_wvalid.value  = 0
    dut.s_axil_bready.value  = 1

    # Wait for AW handshake
    for _ in range(10):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_awvalid.value) and int(dut.s_axil_awready.value):
            dut._log.info("AW handshake observed")
            dut.s_axil_awvalid.value = 0
            break
    else:
        raise AssertionError("AW handshake not seen within 10 cycles")

    # APB must still be idle (no W yet)
    assert int(dut.u_bridge.psel.value) == 0, \
        "bridge started APB transfer before W arrived"

    # Now present W
    await RisingEdge(dut.clk)
    dut.s_axil_wdata.value  = 0xFEEDFACE
    dut.s_axil_wstrb.value  = 0xF
    dut.s_axil_wvalid.value = 1

    # Wait for B response
    for _ in range(20):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_bvalid.value) and int(dut.s_axil_bready.value):
            bresp = int(dut.s_axil_bresp.value)
            dut.s_axil_wvalid.value = 0
            assert bresp == RESP_OKAY, f"bresp {bresp} after AW-before-W"
            dut._log.info("AW-before-W ordering: bridge buffers AW, completes OK")
            break
    else:
        raise AssertionError("B response not received after AW-before-W sequence")


# ---------------------------------------------------------------------------
# T5 — W arrives before AW: bridge buffers W and waits for AW
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_w_before_aw(dut):
    """
    Drive W channel one cycle before AW channel.  The bridge must:
      - Accept W (wready) when W is presented (state=IDLE, w_cap clear)
      - Hold off APB SETUP until AW also arrives
      - Complete write with bresp OKAY
    """
    await _setup(dut)

    # Drive W, withhold AW
    dut.s_axil_wdata.value  = 0xC0DECAFE
    dut.s_axil_wstrb.value  = 0xF
    dut.s_axil_wvalid.value = 1
    dut.s_axil_awvalid.value = 0
    dut.s_axil_bready.value  = 1

    # Wait for W handshake
    for _ in range(10):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_wvalid.value) and int(dut.s_axil_wready.value):
            dut._log.info("W handshake observed")
            dut.s_axil_wvalid.value = 0
            break
    else:
        raise AssertionError("W handshake not seen within 10 cycles")

    # APB must still be idle (no AW yet)
    assert int(dut.u_bridge.psel.value) == 0, \
        "bridge started APB transfer before AW arrived"

    # Now present AW
    await RisingEdge(dut.clk)
    dut.s_axil_awaddr.value  = REG1
    dut.s_axil_awprot.value  = 0
    dut.s_axil_awvalid.value = 1

    # Wait for B response
    for _ in range(20):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_bvalid.value) and int(dut.s_axil_bready.value):
            bresp = int(dut.s_axil_bresp.value)
            dut.s_axil_awvalid.value = 0
            assert bresp == RESP_OKAY, f"bresp {bresp} after W-before-AW"
            dut._log.info("W-before-AW ordering: bridge buffers W, completes OK")
            break
    else:
        raise AssertionError("B response not received after W-before-AW sequence")


# ---------------------------------------------------------------------------
# T6 — Back-to-back write then read: read waits for write to complete
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_back_to_back_write_read(dut):
    """
    Issue a write immediately followed by a read.  The bridge is depth-1 so
    the read must wait for the write to fully complete (B handshake) before
    the AR channel is accepted.

    Verify:
      - Write completes with bresp OKAY
      - Read completes with rresp OKAY and correct rdata
    """
    m = await _setup(dut)

    WRITE_VAL = 0xBEEFCAFE

    # Issue write and read concurrently from separate coroutines
    async def do_write():
        return await m.write(REG0, WRITE_VAL)

    async def do_read():
        # Wait a few cycles then issue read — bridge must block AR until idle
        for _ in range(2):
            await RisingEdge(dut.clk)
        return await m.read(REG0)

    write_task = cocotb.start_soon(do_write())
    read_task  = cocotb.start_soon(do_read())

    bresp        = await write_task
    data, rresp  = await read_task

    assert bresp == RESP_OKAY,  f"write bresp {bresp}"
    assert rresp == RESP_OKAY,  f"read rresp {rresp}"
    assert data  == WRITE_VAL, f"read {data:#010x} expected {WRITE_VAL:#010x}"
    dut._log.info("back-to-back write→read: both complete in order OK")


# ---------------------------------------------------------------------------
# T7 — GH #85 regression guard: concurrent AR + AW + W in S_IDLE
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_concurrent_ar_aw_w_write_priority(dut):
    """
    GH #85 regression: simultaneous AR + AW + W presented while the bridge is
    in S_IDLE.

    Pre-fix RTL (s_axil_arready had no !s_axil_awvalid/!s_axil_wvalid gate):
      arready=1 fires in the same clock edge as the AW+W handshake.  Both the
      write-address capture block and the read-address capture block evaluate
      in the same always_ff body.  Non-blocking assignments execute in program
      order, so the AR block's  "addr_q <= araddr; is_write_q <= 0"  takes
      effect last and overwrites the write address and direction flag.  The
      subsequent APB transfer is therefore issued as a READ — the write data
      never lands in the register bank.  The bridge then goes to S_RRESP
      (not S_WRESP), so bvalid never fires.

    Post-fix RTL:
      arready is gated by (!s_axil_awvalid && !s_axil_wvalid).  While awvalid
      or wvalid is asserted, arready=0; the AR-capture block never fires in the
      same cycle.  The write completes correctly (bresp=OKAY, data lands), then
      the bridge returns to S_IDLE with awvalid=wvalid=0 and accepts AR.

    This test FAILS against pre-fix RTL (timeout on bvalid) and PASSES after
    the GH #85 fix.
    """
    await _setup(dut)

    WRITE_VAL = 0xDEAD_BEEF

    # ── Drive AW + W + AR simultaneously to REG0 ─────────────────────────────
    dut.s_axil_awaddr.value  = REG0
    dut.s_axil_awprot.value  = 0
    dut.s_axil_awvalid.value = 1
    dut.s_axil_wdata.value   = WRITE_VAL
    dut.s_axil_wstrb.value   = 0xF
    dut.s_axil_wvalid.value  = 1
    dut.s_axil_araddr.value  = REG0
    dut.s_axil_arprot.value  = 0
    dut.s_axil_arvalid.value = 1
    dut.s_axil_bready.value  = 1
    dut.s_axil_rready.value  = 1

    # ── One clock edge: AW+W handshake fires; AR must be deferred ────────────
    # After this edge the bridge is in S_SETUP with is_write_q=1 (post-fix) or
    # is_write_q=0/addr=araddr (pre-fix).  Deassert write channels — they were
    # captured (awready=wready=1 in IDLE).
    await RisingEdge(dut.clk)
    dut.s_axil_awvalid.value = 0
    dut.s_axil_wvalid.value  = 0
    # s_axil_arvalid stays 1 — AR is waiting for arready to come back high.

    # ── Wait for B response: the write must complete correctly ────────────────
    # Pre-fix: bridge goes to S_RRESP (not S_WRESP), bvalid never fires →
    #          timeout, AssertionError — test correctly fails.
    # Post-fix: S_SETUP→S_ACCESS→S_WRESP, bvalid=1.
    bresp = None
    for _ in range(20):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_bvalid.value) and int(dut.s_axil_bready.value):
            bresp = int(dut.s_axil_bresp.value)
            break
    assert bresp is not None, (
        "write B response not received within 20 cycles — "
        "pre-fix RTL issued a read instead of a write (is_write_q overwritten "
        "by concurrent AR capture), so bvalid never fires"
    )
    assert bresp == RESP_OKAY, f"write bresp {bresp} expected OKAY(0)"
    dut._log.info("write completed with bresp=OKAY (GH #85)")

    # ── AR must now be accepted — bridge is IDLE, write channels deasserted ───
    ar_accepted = False
    for _ in range(10):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_arvalid.value) and int(dut.s_axil_arready.value):
            ar_accepted = True
            dut.s_axil_arvalid.value = 0
            dut._log.info("AR accepted after write completed (GH #85)")
            break
    assert ar_accepted, "AR not accepted within 10 cycles after write completion"

    # ── R response must carry the written value ───────────────────────────────
    # Pre-fix: if somehow bvalid fired (it won't), the read would return the
    # APB prdata from the spurious read — register value is 0 (never written).
    rdata = rresp = None
    for _ in range(20):
        await RisingEdge(dut.clk)
        if int(dut.s_axil_rvalid.value) and int(dut.s_axil_rready.value):
            rdata = int(dut.s_axil_rdata.value)
            rresp = int(dut.s_axil_rresp.value)
            break
    assert rdata is not None, "R response not received within 20 cycles"
    assert rresp == RESP_OKAY, f"read rresp {rresp} expected OKAY(0)"
    assert rdata == WRITE_VAL, (
        f"rdata {rdata:#010x} != {WRITE_VAL:#010x} — "
        "pre-fix: concurrent AR corrupted addr_q/is_write_q, APB did a read "
        "instead of a write, register was never updated"
    )
    dut._log.info(
        f"GH #85 concurrent AR+AW+W: write priority correct, "
        f"AR deferred, rdata={rdata:#010x}  PASS"
    )
