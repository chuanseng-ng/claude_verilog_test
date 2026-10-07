"""
Phase 5 (M3) — AXI4-Lite register-bank unit tests.

Verifies rtl/soc/axi_lite_register_bank.sv (via tb_axi_lite_register_bank):
read/write round-trip, per-register WMASK (read-only + partial), wstrb byte
lanes, the hardware status-injection path (bypasses WMASK), and out-of-range
addressing (completes OKAY, write dropped / read 0).

Register layout (N_REGS = 8, byte addr = idx*4):
    reg0..reg5 : fully SW-writable
    reg6 @0x18 : SW read-only, HW-writable (status)
    reg7 @0x1C : low-byte writable only (WMASK 0x000000FF), HW-writable via hw_aux_*

Ownership rule (bead 6o8w): SW owns the WMASK bits, HW owns everything else.  The
RO-write vs same-cycle HW update and partial-WMASK merge tests pin that rule.

Two build points (bead r5hu), selected by the `register_bank` Makefile target through the
REGBANK_ADDR_W environment variable that mirrors the Verilator `-GADDR_W=` override:
  ADDR_W = 12 (default) -- 4 KB slot; WORDW = 10, N_REGS = 8 << 2**WORDW.
  ADDR_W =  5           -- WORDW = 3, so N_REGS == 2**WORDW.  The DUT's range gate must
                           not wrap N_REGS to 0 here; test_nregs_equals_wordw_boundary
                           proves it.  Only the byte addresses 0x00..0x1C exist at this
                           width, so tests that probe 0x100 run in the default build only.
"""

import os

import cocotb
from axil_stall_bfm import StallMaster
from bfm.axi4lite_master import AXI4LiteMaster
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

CLK_PERIOD_NS = 2

# Elaboration width of THIS build (set by the Makefile; see module docstring).
DEFAULT_ADDR_W = 12
N_REGS = 8                                   # fixed by tb_axi_lite_register_bank.sv
ADDR_W = int(os.environ.get("REGBANK_ADDR_W", str(DEFAULT_ADDR_W)))
# True when N_REGS == 2**(ADDR_W-2): the case where a truncating WORDW'(N_REGS) cast wraps to 0.
AT_BOUNDARY = (1 << (ADDR_W - 2)) == N_REGS
WIDE_ONLY = ADDR_W != DEFAULT_ADDR_W         # skip flag for tests that need the 4 KB window

REG0 = 0x00
REG5 = 0x14
REG6 = 0x18    # read-only / status
REG7 = 0x1C    # low-byte writable
OOR  = 0x100   # word 64 >= N_REGS -> out of range

RESP_OKAY = 0


async def _setup(dut):
    """Start clock, reset, build AXI4-Lite master. Returns the master."""
    # Stale-Vtop guard: the env var must describe the binary actually being simulated.
    assert len(dut.s_axil_awaddr) == ADDR_W, (
        f"REGBANK_ADDR_W={ADDR_W} but the elaborated DUT has a "
        f"{len(dut.s_axil_awaddr)}-bit address bus (stale SIM_BUILD?)")
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    dut.hw_status_wen.value = 0
    dut.hw_status_wdata.value = 0
    dut.hw_aux_wen.value = 0
    dut.hw_aux_wdata.value = 0
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


@cocotb.test(skip=WIDE_ONLY)
async def test_out_of_range(dut):
    """Address beyond N_REGS completes OKAY: write dropped, read returns 0.

    Default build only: OOR = 0x100 does not fit in the ADDR_W=5 address bus.
    """
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


@cocotb.test(skip=not AT_BOUNDARY)
async def test_nregs_equals_wordw_boundary(dut):
    """
    Bead r5hu.  Runs only in the ADDR_W=5 build, where N_REGS == 2**WORDW (8 == 2**3).

    The write-commit gate and the read mux compare the word address against N_REGS.  A
    truncating `WORDW'(N_REGS)` cast turns 8 into 0 at WORDW=3, so `word < 0` is false for
    EVERY address: all SW writes are dropped and all reads return 0, yet every transaction
    still completes OKAY.  Hence the OKAY assertions below do not detect the bug -- the
    read-back data does.  reg0 and reg5 are both checked so a reg0-only special case
    cannot satisfy it.
    """
    assert AT_BOUNDARY and ADDR_W == 5
    m = await _setup(dut)

    for addr, pattern in ((REG0, 0xDEADBEEF), (REG5, 0xA5C3_1E7B)):
        resp = await m.write(addr, pattern)
        assert resp == RESP_OKAY, f"write @{addr:#04x} resp {resp}"
        data, rresp = await m.read(addr)
        assert rresp == RESP_OKAY, f"read @{addr:#04x} resp {rresp}"
        assert data == pattern, (
            f"N_REGS == 2**WORDW boundary: wrote {pattern:#010x} to byte addr {addr:#04x}, "
            f"read back {data:#010x} (transaction OKAY both ways -- register file is inert "
            f"if this is 0: truncating WORDW'(N_REGS) cast wrapped to 0)")
    dut._log.info("N_REGS == 2**WORDW boundary OK (reg0 + reg5 round-trip)")


# ---------------------------------------------------------------------------
# Bead 6o8w -- SW commit vs same-cycle HW write
#
# Stimulus is applied on the FALLING edge so the DUT samples it on the next RISING
# edge; the HW ramp acts on RisingEdge and has always finished updating by the next
# falling edge, so "the HW value presented on the commit edge" is unambiguous.
#
# Commit mechanics: the write FSM is in WR_IDLE with awready=wready=1 combinationally,
# so asserting awvalid+wvalid together makes aw_now && w_now true on the very next
# rising edge, i.e. that edge IS the commit edge (axi_lite_register_bank.sv wr_commit).
# ---------------------------------------------------------------------------
class _HwRamp:
    """Hold hw_status_wen=1 and present a fresh, strictly increasing value every cycle."""

    def __init__(self, dut, start: int):
        self._dut = dut
        self.value = start            # value presented for the NEXT rising edge
        self._running = False

    def start(self) -> None:
        self._running = True
        self._dut.hw_status_wdata.value = self.value
        self._dut.hw_status_wen.value = 1
        cocotb.start_soon(self._run())

    async def _run(self) -> None:
        while self._running:
            await RisingEdge(self._dut.clk)
            if not self._running:
                return
            self.value += 1
            self._dut.hw_status_wdata.value = self.value

    def stop(self) -> None:
        """Drop wen immediately (call at a falling edge: takes effect at the next rising edge)."""
        self._running = False
        self._dut.hw_status_wen.value = 0


def _axil_issue(dut, addr: int, data: int, strb: int = 0xF) -> None:
    """Assert AW and W together; both handshake on the next rising edge (= commit edge)."""
    dut.s_axil_awaddr.value = addr
    dut.s_axil_awvalid.value = 1
    dut.s_axil_wdata.value = data
    dut.s_axil_wstrb.value = strb
    dut.s_axil_wvalid.value = 1


def _axil_release(dut) -> None:
    dut.s_axil_awvalid.value = 0
    dut.s_axil_wvalid.value = 0


async def _axil_drain(dut) -> None:
    """Let the write FSM finish WR_RESP and return to WR_IDLE."""
    for _ in range(4):
        await FallingEdge(dut.clk)


@cocotb.test()
async def test_ro_write_does_not_drop_hw_update(dut):
    """
    Bead 6o8w, WMASK==0 case.  reg6 is SW read-only (WMASK=0) and HW-written.

    SW owns the WMASK bits (none), HW owns everything else, so a write to reg6 is a
    pure no-op and must not interfere with the HW update landing on the same edge.
    Defect: the commit computes m = WMASK & wstrb = 0 yet still emits
    regs[6] <= regs[6] (stale pre-edge value), the textually later NBA, which
    overrides the HW write and loses that cycle's HW update.

    HW holds hw_status_wen=1 and presents a new value every cycle (0x1000, 0x1001, ...)
    so a one-cycle stall is visible as reg6 lagging the ramp by one step.
    Expect reg6 == the HW value presented on the commit edge.  Buggy RTL gives that - 1.
    """
    m = await _setup(dut)

    ramp = _HwRamp(dut, start=0x1000)
    await FallingEdge(dut.clk)
    ramp.start()
    for _ in range(4):                       # ramp runs with no SW traffic
        await FallingEdge(dut.clk)

    _axil_issue(dut, REG6, 0xFFFFFFFF)       # commits on the next rising edge
    commit_val = ramp.value                  # HW value the DUT samples on that edge
    await FallingEdge(dut.clk)               # commit edge has now happened
    _axil_release(dut)
    ramp.stop()                              # no HW writes after the commit edge
    await _axil_drain(dut)

    data, rresp = await m.read(REG6)
    assert rresp == RESP_OKAY
    assert data == commit_val, (
        f"write to WMASK=0 reg6 dropped the same-cycle HW update: "
        f"expected {commit_val:#010x} (HW value on commit edge), got {data:#010x} "
        f"(previous-cycle value would be {commit_val - 1:#010x})")
    dut._log.info("RO write left HW update intact: reg6=%#010x", data)


@cocotb.test()
async def test_partial_wmask_hw_keeps_unmasked_bits(dut):
    """
    Bead 6o8w, partial-WMASK case.  reg7 has WMASK=0x000000FF: SW owns [7:0], HW owns
    [31:8].  Same-edge write of 0x00000055 (wstrb=0xF) and HW write of 0xDEADBEEF must
    yield 0xDEADBE55.

    Defect: the commit writes (regs[7] & ~m) | (wd & m) with the STALE pre-edge regs[7],
    so the HW-owned bits [31:8] revert instead of taking the HW value.  reg7 is pre-loaded
    (via HW) with 0xA5A5A5A5 so the failure value 0xA5A5A555 is distinguishable from the
    expected value and from reset.
    """
    m = await _setup(dut)

    await FallingEdge(dut.clk)
    dut.hw_aux_wdata.value = 0xA5A5A5A5
    dut.hw_aux_wen.value = 1
    await FallingEdge(dut.clk)
    dut.hw_aux_wen.value = 0
    await FallingEdge(dut.clk)
    data, _ = await m.read(REG7)
    assert data == 0xA5A5A5A5, f"HW pre-load of reg7 wrong: {data:#010x}"

    await FallingEdge(dut.clk)
    _axil_issue(dut, REG7, 0x00000055, strb=0xF)
    dut.hw_aux_wdata.value = 0xDEADBEEF
    dut.hw_aux_wen.value = 1
    await FallingEdge(dut.clk)               # commit edge has happened
    _axil_release(dut)
    dut.hw_aux_wen.value = 0
    await _axil_drain(dut)

    data, rresp = await m.read(REG7)
    assert rresp == RESP_OKAY
    assert data == 0xDEADBE55, (
        f"partial-WMASK collision: expected 0xDEADBE55 (SW owns [7:0]=0x55, "
        f"HW owns [31:8]=0xDEADBE), got {data:#010x}")
    dut._log.info("partial WMASK: SW [7:0] + HW [31:8] merged OK (reg7=%#010x)", data)


# ---------------------------------------------------------------------------
# Bead 8riq (GH #216 coverage gap): AW/W arrival order and response backpressure.
# Uses the stall-capable master in axil_stall_bfm.py -- the shared AXI4LiteMaster keeps AW and W
# together and bready/rready high, so it can never reach these paths.
# ---------------------------------------------------------------------------
async def _monitor(dut, samples):
    """Record (awready, wready, bvalid, arready, rvalid) as sampled at every rising edge."""
    while True:
        await RisingEdge(dut.clk)
        samples.append((int(dut.s_axil_awready.value), int(dut.s_axil_wready.value),
                        int(dut.s_axil_bvalid.value), int(dut.s_axil_arready.value),
                        int(dut.s_axil_rvalid.value)))


def _longest_run(samples, pred):
    best = cur = 0
    for s in samples:
        cur = cur + 1 if pred(s) else 0
        best = max(best, cur)
    return best


@cocotb.test()
async def test_w_before_aw_uses_latched_data(dut):
    """W arrives six cycles before AW.  The bank must capture W once (wready drops), keep awready
    up, raise no response before the AW lands, and then commit the LATCHED data and byte strobes
    to the address that arrives late (the master drives garbage on the W bus afterwards)."""
    await _setup(dut)
    m = StallMaster(dut, "s_axil_", dut.clk)
    t0 = await m.write(REG0 + 0x0C, 0xFFFF_FFFF)
    assert t0.resp == RESP_OKAY
    samples = []
    mon = cocotb.start_soon(_monitor(dut, samples))
    t = await m.write(REG0 + 0x0C, 0x1122_3344, strb=0b0101, aw_delay=6, w_delay=0)
    mon.kill()
    assert t.resp == RESP_OKAY
    # While W is held and AW has not arrived: wready low, awready high, no bvalid.
    window = _longest_run(samples, lambda s: s[1] == 0 and s[0] == 1 and s[2] == 0)
    assert window >= 4, f"W-captured / AW-pending window only {window} edges ({samples[:14]})"
    data = await m.read(REG0 + 0x0C)
    # strobes 0b0101 keep bytes 1 and 3 of the old 0xFFFFFFFF, take bytes 0 and 2 of the new data.
    assert data.data == 0xFF22_FF44, f"latched wdata/wstrb commit gave {data.data:#010x}"
    assert data.resp == RESP_OKAY


@cocotb.test()
async def test_aw_before_w_uses_latched_address(dut):
    """Mirror case: AW first, W six cycles later.  awready drops after the capture, no response
    before W, and the write lands at the latched address (garbage on the bus afterwards)."""
    await _setup(dut)
    m = StallMaster(dut, "s_axil_", dut.clk)
    samples = []
    mon = cocotb.start_soon(_monitor(dut, samples))
    t = await m.write(REG0 + 0x08, 0xA1B2_C3D4, aw_delay=0, w_delay=6)
    mon.kill()
    assert t.resp == RESP_OKAY
    window = _longest_run(samples, lambda s: s[0] == 0 and s[1] == 1 and s[2] == 0)
    assert window >= 4, f"AW-captured / W-pending window only {window} edges"
    rd = await m.read(REG0 + 0x08)
    assert rd.data == 0xA1B2_C3D4
    other = await m.read(REG0 + 0x0C)
    assert other.data == 0, f"write leaked into the neighbouring register: {other.data:#x}"


@cocotb.test()
async def test_response_backpressure_blocks_new_requests(dut):
    """bready / rready held low: bvalid / rvalid and their payload stay stable, and the bank accepts
    no new AW / W / AR until the response is taken (single outstanding per direction)."""
    await _setup(dut)
    m = StallMaster(dut, "s_axil_", dut.clk)
    samples = []
    mon = cocotb.start_soon(_monitor(dut, samples))
    t = await m.write(REG0 + 4, 0x600D_F00D, b_stall=5)
    assert t.resp == RESP_OKAY and t.resp_wait >= 5 and not t.resp_unstable, t.resp_unstable
    held = [s for s in samples if s[2] == 1]
    assert len(held) >= 5
    assert all(s[0] == 0 and s[1] == 0 for s in held), \
        "AW/W accepted while the B response was still pending"
    samples.clear()
    t = await m.read(REG0 + 4, r_stall=5)
    mon.kill()
    assert (t.resp, t.data) == (RESP_OKAY, 0x600D_F00D)
    assert t.resp_wait >= 5 and not t.resp_unstable, t.resp_unstable
    held = [s for s in samples if s[4] == 1]
    assert len(held) >= 5
    assert all(s[3] == 0 for s in held), "AR accepted while the R response was still pending"
