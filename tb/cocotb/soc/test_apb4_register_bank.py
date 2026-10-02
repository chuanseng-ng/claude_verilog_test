"""
Phase 5 (APB migration PR-1) — apb4_register_bank unit tests.

Verifies rtl/soc/apb4_register_bank.sv (via tb_apb4_register_bank) against the
7 directed tests specified for bead claude_verilog_test-o4p.

The register layout is IDENTICAL to tb_axi_lite_register_bank so that the
pass/fail results here prove behavioral equivalence with the AXI-Lite bank —
a prerequisite before PR-2..5 peripheral register-bank swaps are safe.

Register layout (N_REGS = 8, byte addr = word_idx * 4):
    reg0..reg5  @0x00..0x14 : fully SW-writable (WMASK = 0xFFFFFFFF)
    reg6        @0x18       : SW read-only/status (WMASK = 0x00000000), HW-writable
    reg7        @0x1C       : low-byte writable only (WMASK = 0x000000FF)

Tests:
    T1  test_apb_setup_access_protocol  — APB SETUP→ACCESS handshake; pready high only in ACCESS
    T2  test_partial_pstrb_write        — pstrb=0b0101 leaves bytes 1,3 unchanged
    T3  test_rw_roundtrip               — write→read round-trip; pslverr always 0
    T4  test_out_of_range               — OOR write dropped, OOR read returns 0, pslverr=0
    T5  test_hw_wen_bypasses_wmask      — HW injection to RO reg6 bypasses WMASK
    T6  test_wmask_zero_ro_register     — SW write to WMASK=0 reg is silently dropped
    T7  test_sw_hw_collision_sw_wins    — same-cycle SW+HW write: SW wins on the WMASK bits
    T8  test_ro_write_does_not_drop_hw_update
                                        — APB write to a WMASK=0 reg must not cancel a
                                          same-cycle HW update (bead 6o8w)
    T9  test_partial_wmask_hw_keeps_unmasked_bits
                                        — same-cycle SW write + HW write on a partial-WMASK
                                          reg: SW owns the WMASK bits, HW owns the rest
    T10 test_nregs_equals_wordw_boundary
                                        — ADDR_W=5 build only (bead r5hu): N_REGS == 2**WORDW
                                          must not make the range gate wrap to "nothing in range"

Ownership rule under test: SW owns the WMASK bits, HW owns everything else.

Two build points (bead r5hu), selected by the `apb4_register_bank` Makefile target through the
REGBANK_ADDR_W environment variable that mirrors the Verilator `-GADDR_W=` override:
  ADDR_W = 12 (default) -- 4 KB slot; N_REGS = 8 << 2**WORDW.
  ADDR_W =  5           -- WORDW = 3, N_REGS == 2**WORDW.  This module carries the GH #87 fix
                           (zero-extend the ADDRESS rather than truncating N_REGS), so it is the
                           positive control for the sibling axi_lite_register_bank defect.
                           Tests that probe byte address 0x100 run in the default build only.
"""

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

from bfm.apb4_master import APB4Master

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2

# Elaboration width of THIS build (set by the Makefile; see module docstring).
DEFAULT_ADDR_W = 12
N_REGS = 8                                   # fixed by tb_apb4_register_bank.sv
ADDR_W = int(os.environ.get("REGBANK_ADDR_W", str(DEFAULT_ADDR_W)))
# True when N_REGS == 2**(ADDR_W-2): the case where a truncating WORDW'(N_REGS) cast wraps to 0.
AT_BOUNDARY = (1 << (ADDR_W - 2)) == N_REGS
WIDE_ONLY = ADDR_W != DEFAULT_ADDR_W         # skip flag for tests that need the 4 KB window


def _check_build(dut) -> None:
    """Stale-Vtop guard: the env var must describe the binary actually being simulated."""
    assert len(dut.paddr) == ADDR_W, (
        f"REGBANK_ADDR_W={ADDR_W} but the elaborated DUT has a "
        f"{len(dut.paddr)}-bit address bus (stale SIM_BUILD?)")


# Register byte addresses
REG0 = 0x00
REG1 = 0x04
REG5 = 0x14
REG6 = 0x18   # SW read-only / HW-writable
REG7 = 0x1C   # low-byte writable only (WMASK 0x000000FF), HW-writable via hw_aux_*
OOR  = 0x100  # word 64 >= N_REGS=8  → out of range


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------
async def _setup(dut):
    """Start clock, reset DUT, init HW-injection inputs, return APB4Master."""
    _check_build(dut)
    cocotb.start_soon(Clock(dut.pclk, CLK_PERIOD_NS, units="ns").start())
    dut.hw_status_wen.value   = 0
    dut.hw_status_wdata.value = 0
    dut.hw_aux_wen.value   = 0
    dut.hw_aux_wdata.value = 0
    dut.presetn.value = 0
    m = APB4Master(dut, "", dut.pclk)
    for _ in range(5):
        await RisingEdge(dut.pclk)
    dut.presetn.value = 1
    for _ in range(2):
        await RisingEdge(dut.pclk)
    return m


# ---------------------------------------------------------------------------
# Cycle-exact helpers (bead 6o8w)
#
# All stimulus below is applied on the FALLING edge, so it is sampled by the DUT
# on the very next RISING edge.  A coroutine that acts on RisingEdge (the HW ramp)
# has therefore always finished updating by the time the test body runs at the
# following FallingEdge -- there is no same-edge resume-order race, and "the HW
# value presented on the commit edge" is simply the ramp value read at the
# falling edge that precedes it.
# ---------------------------------------------------------------------------
class _HwRamp:
    """Hold hw_status_wen=1 and present a fresh, strictly increasing value every cycle.

    Because the value changes on every clock, a one-cycle stall of the HW update path
    (a dropped HW write) is observable as a register that lags the ramp by one step.
    """

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
            await RisingEdge(self._dut.pclk)
            if not self._running:
                return
            self.value += 1
            self._dut.hw_status_wdata.value = self.value

    def stop(self) -> None:
        """Drop wen immediately (call at a falling edge: takes effect at the next rising edge)."""
        self._running = False
        self._dut.hw_status_wen.value = 0


def _raw_write_setup(dut, addr: int, data: int, strb: int = 0xF) -> None:
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 1
    dut.paddr.value = addr
    dut.pwdata.value = data
    dut.pstrb.value = strb


def _raw_write_access(dut) -> None:
    dut.penable.value = 1          # pready hardwired 1 -> commits on the next rising edge


def _raw_write_idle(dut) -> None:
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0


# ---------------------------------------------------------------------------
# T1 — APB SETUP→ACCESS protocol; pready visible only in ACCESS
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_apb_setup_access_protocol(dut):
    """
    Manually step through SETUP and ACCESS phases to verify APB4 signalling.

    In SETUP  (psel=1, penable=0): pready is driven 1 by the DUT (zero-wait
    implementation), but the master must NOT sample prdata/pslverr here.
    In ACCESS (psel=1, penable=1): pready=1, transfer completes.
    """
    _check_build(dut)
    cocotb.start_soon(Clock(dut.pclk, CLK_PERIOD_NS, units="ns").start())
    dut.hw_status_wen.value   = 0
    dut.hw_status_wdata.value = 0
    dut.hw_aux_wen.value   = 0
    dut.hw_aux_wdata.value = 0
    dut.presetn.value = 0
    # Drive APB idle manually before reset release
    dut.psel.value    = 0
    dut.penable.value = 0
    dut.pwrite.value  = 0
    dut.paddr.value   = 0
    dut.pwdata.value  = 0
    dut.pstrb.value   = 0xF
    for _ in range(5):
        await RisingEdge(dut.pclk)
    dut.presetn.value = 1
    await RisingEdge(dut.pclk)

    # ── Write: SETUP phase ───────────────────────────────────────────────────
    dut.psel.value    = 1
    dut.penable.value = 0
    dut.pwrite.value  = 1
    dut.paddr.value   = REG0
    dut.pwdata.value  = 0xCAFEBABE
    dut.pstrb.value   = 0xF
    await RisingEdge(dut.pclk)

    # psel=1, penable=0 → SETUP phase.  pslverr must be 0.
    assert int(dut.pslverr.value) == 0, "pslverr asserted in SETUP phase"

    # ── Write: ACCESS phase ──────────────────────────────────────────────────
    dut.penable.value = 1
    await RisingEdge(dut.pclk)
    # pready=1 (zero wait state), pslverr=0
    assert int(dut.pready.value)  == 1, "pready not 1 in ACCESS phase"
    assert int(dut.pslverr.value) == 0, "pslverr asserted in ACCESS phase"

    # Return to idle
    dut.psel.value    = 0
    dut.penable.value = 0
    await RisingEdge(dut.pclk)

    # ── Read back to confirm write committed ─────────────────────────────────
    m = APB4Master(dut, "", dut.pclk)
    data, ok = await m.read(REG0)
    assert ok,  "read returned pslverr"
    assert data == 0xCAFEBABE, f"read {data:#010x} expected 0xCAFEBABE"
    dut._log.info("APB SETUP/ACCESS protocol + pready/pslverr signalling OK")


# ---------------------------------------------------------------------------
# T2 — Partial pstrb write: bytes 1 and 3 unchanged when strb=0b0101
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_partial_pstrb_write(dut):
    """
    pstrb=0b0101 (bytes 0 and 2 active) — bytes 1 and 3 of reg0 must not change.

    Sequence:
      1. Write 0xFF00FF00 with pstrb=0xF  → reg0 = 0xFF00FF00
      2. Write 0x11223344 with pstrb=0x5  → only bytes 0 (0x44) and 2 (0x22) update
         Expected reg0 = 0xFF22FF44
    """
    m = await _setup(dut)

    ok = await m.write(REG0, 0xFF00FF00, strb=0xF)
    assert ok, "initial write pslverr"

    ok = await m.write(REG0, 0x11223344, strb=0x5)  # 0b0101
    assert ok, "partial-strb write pslverr"

    data, ok = await m.read(REG0)
    assert ok, "read pslverr"
    assert data == 0xFF22FF44, \
        f"partial pstrb result {data:#010x}, expected 0xFF22FF44"
    dut._log.info("partial pstrb=0x5 byte masking OK")


# ---------------------------------------------------------------------------
# T3 — Read-write round-trip; pslverr always 0
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_rw_roundtrip(dut):
    """Write a value then read it back; pslverr must be 0 on both."""
    m = await _setup(dut)
    ok = await m.write(REG1, 0xDEADBEEF)
    assert ok, "write pslverr on round-trip"
    data, ok = await m.read(REG1)
    assert ok, "read pslverr on round-trip"
    assert data == 0xDEADBEEF, f"read {data:#010x} expected 0xDEADBEEF"
    dut._log.info("read-write round-trip OK")


# ---------------------------------------------------------------------------
# T4 — Out-of-range address: write dropped, read 0, pslverr=0
# ---------------------------------------------------------------------------
@cocotb.test(skip=WIDE_ONLY)
async def test_out_of_range(dut):
    """
    Address OOR (word 64 >= N_REGS=8) must complete OKAY (pslverr=0),
    write silently dropped, read returns 0.  In-range registers untouched.

    Default build only: OOR = 0x100 does not fit in the ADDR_W=5 address bus.
    """
    m = await _setup(dut)

    # Seed reg0 so we can verify it wasn't disturbed
    await m.write(REG0, 0x12345678)

    ok = await m.write(OOR, 0xDEADC0DE)
    assert ok, "OOR write returned pslverr (spec requires OKAY+drop)"

    data, ok = await m.read(OOR)
    assert ok,   "OOR read returned pslverr"
    assert data == 0, f"OOR read {data:#010x}, expected 0"

    # reg0 must be undisturbed
    data0, _ = await m.read(REG0)
    assert data0 == 0x12345678, f"reg0 disturbed by OOR write: {data0:#010x}"
    dut._log.info("out-of-range address: OKAY+drop/0 OK")


# ---------------------------------------------------------------------------
# T5 — hw_wen_i bypasses WMASK (HW write to read-only reg6)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_hw_wen_bypasses_wmask(dut):
    """
    reg6 has WMASK=0 (SW read-only).  A hardware write via hw_status_wen
    must bypass WMASK and update the register, visible on the next SW read.
    """
    m = await _setup(dut)

    # Confirm reg6 resets to 0
    data, ok = await m.read(REG6)
    assert ok and data == 0, f"reg6 at reset: {data:#010x}"

    # HW write
    dut.hw_status_wdata.value = 0xC0FFEE00
    dut.hw_status_wen.value   = 1
    await RisingEdge(dut.pclk)
    dut.hw_status_wen.value   = 0
    await RisingEdge(dut.pclk)

    data, ok = await m.read(REG6)
    assert ok,  "read pslverr after HW injection"
    assert data == 0xC0FFEE00, f"HW injection read {data:#010x}"
    dut._log.info("hw_wen_i bypasses WMASK OK")


# ---------------------------------------------------------------------------
# T6 — WMASK=0 register: SW write is silently dropped, pslverr=0
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_wmask_zero_ro_register(dut):
    """
    reg6 WMASK=0 — SW write must complete OKAY (pslverr=0) but value stays 0.
    """
    m = await _setup(dut)

    ok = await m.write(REG6, 0xFFFFFFFF)
    assert ok, "SW write to RO reg6 returned pslverr (must be OKAY)"

    data, ok = await m.read(REG6)
    assert ok,  "read pslverr on RO register"
    assert data == 0, f"RO reg6 changed to {data:#010x}"
    dut._log.info("WMASK=0 read-only register drop OK")


# ---------------------------------------------------------------------------
# T7 — Same-cycle SW+HW collision: SW wins on the bits inside WMASK
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_sw_hw_collision_sw_wins(dut):
    """
    Same-cycle SW and HW write to reg7 (WMASK=0x000000FF): on the WMASK bits SW wins.

    Ownership rule: SW owns the WMASK bits, HW owns everything else.  When an APB
    write and a HW write land on the same edge, bits [7:0] (inside WMASK) must carry
    the SW value, never the HW value.  Bits [31:8] are outside WMASK and are
    covered by T9; this test deliberately asserts ONLY the in-WMASK byte so it states
    the part of the contract that does not depend on how the out-of-WMASK bits resolve.

    Sequence (cycle-exact, raw APB phases so the ACCESS/commit edge and the HW write
    share one rising edge):
      1. Pre-load reg7 via HW with 0xA5A5A5A5 (all 32 bits HW-writable).
      2. SETUP phase of an APB write of 0x00000055 (pstrb=0xF) to reg7.
      3. ACCESS phase, with hw_aux_wen=1 / hw_aux_wdata=0xDEADBE99 on the same edge.
      Expect reg7[7:0] == 0x55 (SW), and != 0x99 (the HW value for that byte).
    """
    m = await _setup(dut)

    # 1. HW pre-load (aux port bypasses WMASK; reg7 resets to 0)
    await FallingEdge(dut.pclk)
    dut.hw_aux_wdata.value = 0xA5A5A5A5
    dut.hw_aux_wen.value = 1
    await FallingEdge(dut.pclk)
    dut.hw_aux_wen.value = 0
    await FallingEdge(dut.pclk)
    data, _ = await m.read(REG7)
    assert data == 0xA5A5A5A5, f"pre-collision HW pre-load wrong: {data:#010x}"

    # 2. SETUP
    await FallingEdge(dut.pclk)
    _raw_write_setup(dut, REG7, 0x00000055)
    # 3. ACCESS + same-edge HW write
    await FallingEdge(dut.pclk)
    _raw_write_access(dut)
    dut.hw_aux_wdata.value = 0xDEADBE99
    dut.hw_aux_wen.value = 1
    await FallingEdge(dut.pclk)          # commit edge has happened
    dut.hw_aux_wen.value = 0
    _raw_write_idle(dut)
    await FallingEdge(dut.pclk)

    data, ok = await m.read(REG7)
    assert ok, "read pslverr after collision"
    assert (data & 0xFF) == 0x55, \
        f"SW+HW collision on WMASK byte: expected SW value 0x55, got {data & 0xFF:#04x} (reg7={data:#010x})"
    assert (data & 0xFF) != 0x99, \
        f"HW value landed in the SW-owned byte (reg7={data:#010x})"
    dut._log.info("SW+HW same-cycle collision: SW wins on WMASK bits OK (reg7=%#010x)", data)


# ---------------------------------------------------------------------------
# T8 — APB write to a WMASK=0 register must not cancel a same-cycle HW update
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ro_write_does_not_drop_hw_update(dut):
    """
    Bead 6o8w, WMASK==0 case.  reg6 is read-only to SW (WMASK=0) and HW-written.

    SW owns the WMASK bits (none), HW owns everything else, so an APB write to reg6
    is a pure no-op and must never interfere with the HW update that lands on the
    same edge.  Defect: the SW commit computes m = WMASK & strb = 0 and still emits
    regs[6] <= regs[6] (stale pre-edge value), which, as the textually later NBA,
    overrides the HW write -- the HW update for that cycle is lost.

    Observability: HW holds hw_status_wen=1 and presents a NEW value every cycle
    (0x1000, 0x1001, ...), so a one-cycle stall shows up as reg6 lagging by one.

    Sequence (falling-edge stimulus -> sampled on the next rising edge):
      SETUP edge : psel=1 penable=0  (no commit)
      COMMIT edge: psel=1 penable=1  (APB write to reg6; HW presents V)
      then stop the ramp and read reg6.
    Expect reg6 == V (HW value presented on the commit edge).  Buggy RTL gives V-1.
    """
    m = await _setup(dut)

    ramp = _HwRamp(dut, start=0x1000)
    await FallingEdge(dut.pclk)
    ramp.start()
    for _ in range(4):                       # let the ramp run with no SW traffic
        await FallingEdge(dut.pclk)

    # SETUP phase (sampled at the next rising edge; no commit)
    _raw_write_setup(dut, REG6, 0xFFFFFFFF)
    await FallingEdge(dut.pclk)

    # ACCESS phase: commits on the next rising edge, together with HW value V
    _raw_write_access(dut)
    commit_val = ramp.value                  # value the DUT samples on the commit edge
    await FallingEdge(dut.pclk)              # commit edge has now happened

    ramp.stop()                              # no further HW writes after the commit edge
    _raw_write_idle(dut)
    await FallingEdge(dut.pclk)
    await FallingEdge(dut.pclk)

    data, ok = await m.read(REG6)
    assert ok, "read pslverr on reg6"
    assert data == commit_val, (
        f"APB write to WMASK=0 reg6 dropped the same-cycle HW update: "
        f"expected {commit_val:#010x} (HW value on commit edge), got {data:#010x} "
        f"(previous-cycle value would be {commit_val - 1:#010x})")
    dut._log.info("RO write left HW update intact: reg6=%#010x", data)


# ---------------------------------------------------------------------------
# T9 — partial WMASK: HW keeps the bits SW does not own
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_partial_wmask_hw_keeps_unmasked_bits(dut):
    """
    Bead 6o8w, partial-WMASK case.  reg7 has WMASK=0x000000FF: SW owns [7:0], HW
    owns [31:8].  Same-edge APB write of 0x00000055 (pstrb=0xF) and HW write of
    0xDEADBEEF must yield 0xDEADBE55.

    Defect: the SW commit writes back (regs[7] & ~m) | (pwdata & m), where regs[7]
    is the STALE pre-edge value, so the HW-owned bits [31:8] revert to their old
    value instead of taking the HW value.

    reg7 is pre-loaded (via HW) with 0xA5A5A5A5 so the stale-[31:8] failure value
    (0xA5A5A555) is distinguishable from both the expected value (0xDEADBE55) and
    a reset-value 0.
    """
    m = await _setup(dut)

    # Pre-load reg7 with a recognisable stale value through the HW port.
    await FallingEdge(dut.pclk)
    dut.hw_aux_wdata.value = 0xA5A5A5A5
    dut.hw_aux_wen.value = 1
    await FallingEdge(dut.pclk)
    dut.hw_aux_wen.value = 0
    await FallingEdge(dut.pclk)
    data, _ = await m.read(REG7)
    assert data == 0xA5A5A5A5, f"HW pre-load of reg7 wrong: {data:#010x}"

    # SETUP
    await FallingEdge(dut.pclk)
    _raw_write_setup(dut, REG7, 0x00000055, strb=0xF)
    # ACCESS + same-edge HW write
    await FallingEdge(dut.pclk)
    _raw_write_access(dut)
    dut.hw_aux_wdata.value = 0xDEADBEEF
    dut.hw_aux_wen.value = 1
    await FallingEdge(dut.pclk)              # commit edge has happened
    dut.hw_aux_wen.value = 0
    _raw_write_idle(dut)
    await FallingEdge(dut.pclk)
    await FallingEdge(dut.pclk)

    data, ok = await m.read(REG7)
    assert ok, "read pslverr on reg7"
    assert data == 0xDEADBE55, (
        f"partial-WMASK collision: expected 0xDEADBE55 (SW owns [7:0]=0x55, "
        f"HW owns [31:8]=0xDEADBE), got {data:#010x}")
    dut._log.info("partial WMASK: SW [7:0] + HW [31:8] merged OK (reg7=%#010x)", data)


# ---------------------------------------------------------------------------
# T10 — N_REGS == 2**WORDW boundary (bead r5hu); ADDR_W=5 build only
# ---------------------------------------------------------------------------
@cocotb.test(skip=not AT_BOUNDARY)
async def test_nregs_equals_wordw_boundary(dut):
    """
    Bead r5hu positive control.  Runs only in the ADDR_W=5 build, where
    N_REGS == 2**WORDW (8 == 2**3).

    A truncating `WORDW'(N_REGS)` cast would turn 8 into 0 at WORDW=3, making every address
    "out of range": writes dropped, reads 0, transactions still OKAY (pslverr=0) -- silent.
    This module zero-extends the address instead (GH #87), so it must round-trip.  The same
    stimulus FAILS on the axi_lite_register_bank until that sibling gets the same fix; this
    passing here shows the test construction discriminates the two idioms.
    reg0 and reg5 are both checked so a reg0-only special case cannot satisfy it.
    """
    assert AT_BOUNDARY and ADDR_W == 5
    m = await _setup(dut)

    for addr, pattern in ((REG0, 0xDEADBEEF), (REG5, 0xA5C3_1E7B)):
        ok = await m.write(addr, pattern)
        assert ok, f"write @{addr:#04x} returned pslverr"
        data, ok = await m.read(addr)
        assert ok, f"read @{addr:#04x} returned pslverr"
        assert data == pattern, (
            f"N_REGS == 2**WORDW boundary: wrote {pattern:#010x} to byte addr {addr:#04x}, "
            f"read back {data:#010x} (transaction OKAY both ways -- register file is inert "
            f"if this is 0: truncating WORDW'(N_REGS) cast wrapped to 0)")
    dut._log.info("N_REGS == 2**WORDW boundary OK (reg0 + reg5 round-trip)")
