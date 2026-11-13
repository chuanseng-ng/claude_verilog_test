"""
test_wdt.py -- Phase 6a-3 cocotb verification for watchdog_timer (rtl/periph/watchdog_timer.sv; plan
"6a-3 -- WDT"). DUT: tb_wdt (ADDR_W=12); beyond the APB4 face irq_o and wdt_rst_req_o (both
level-held). Register map: watchdog_timer.sv header (N_REGS=8; FEED magic 0x5A5A_C0DE).
Timing (P = PRESCALE, R = RELOAD, E = the edge where the CTRL[0] write commits): enabling loads the
counter from RELOAD; it counts down once per tick (one tick = PRESCALE+1 cycles); timeout = 0. BARK
(sticky STATUS[0]) is visible k edges after E, (P+1)*(R-1) <= k <= (P+1)*R + 6.
The suite does NOT pin one latency constant, but pins what must not depend on it: the latency is
IDENTICAL on every run from reset, so run-to-run differences (R=40 vs R=16 is exactly 24 cycles at
P=0) and set-beats-clear alignment are exact. A FEED takes effect within 2 edges of its commit edge
(feed checks wait ClockCycles(dut.clk, 2)); W1C clears act ON the commit edge.
BITE: after the bark the counter reloads and runs a second period; a second timeout with no valid
feed sets sticky STATUS[1] AND wdt_rst_req_o on the SAME edge, d edges after the bark,
max((P+1)*R,1) <= d <= (P+1)*(R+1)+3. wdt_rst_req_o is LEVEL-HELD UNTIL RESET (a separate latch):
W1C, feeding or disabling do NOT drop it. RST_EN gates only the SoC cpu_domain_rst_n AND-in
(invisible at L1): a bite sets STATUS[1] and wdt_rst_req_o with RST_EN = 0 too. A hardware set beats
a same-cycle clear.
WINDOW MODE (CTRL[2]=1, WINDOW != 0): a feed while COUNT > WINDOW is a violation (STATUS[2], no
reload); COUNT == WINDOW is accepted.
DECISIONS the spec left open (asserted here, the RTL follows): D1 RELOAD == 0 while enabled FAILS
TOWARD FIRING (bark within a few cycles, then bite; no hang, no underflow): a misconfigured watchdog
must be noisy. D2 A RELOAD write while running does not touch the live counter. D3 Reading COUNT,
FEED, STATUS or IRQ_CLR perturbs NOTHING (a FEED read must not pet the dog). D4 A feed needs pstrb
== 0xF. D5 irq_o = |STATUS[2:0] (masking is the interrupt_controller's job). D6 A valid feed clears
the bark->bite escalation. D7 Bite is TERMINAL (only rst_n revives it). D8 A disabled feed is a
no-op; a window violation never escalates.
Sampling: RisingEdge(dut.clk) FIRST, then read.
Run: make -C tb/cocotb/soc wdt
Doc: tm:suite:soc-test-wdt
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.apb4_master import APB4Master
import reg_maps  # noqa: E402
from reg_walk import M32, check_w1c, walk_bank  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10  # matches the SoC reference clock (same convention as test_pwm.py)

WDT_CTRL = 0x000
WDT_RELOAD = 0x004
WDT_COUNT = 0x008
WDT_WINDOW = 0x00C
WDT_FEED = 0x010
WDT_PRESCALE = 0x014
WDT_STATUS = 0x018
WDT_IRQ_CLR = 0x01C
WDT_OUT_OF_RANGE = 0x020  # word index 8 -- first address past the 8-register map

MAGIC = 0x5A5A_C0DE

CTRL_EN = 0x1
CTRL_RST_EN = 0x2
CTRL_WIN_EN = 0x4

ST_BARK = 0x1
ST_BITE = 0x2
ST_VIOL = 0x4
ST_ALL = 0x7

# ---------------------------------------------------------------------------
# Module-level task handle list (guard against cross-test coroutine leakage)
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _idle_bus(dut) -> None:
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = 0
    dut.pwdata.value = 0
    dut.pstrb.value = 0xF


async def _start_clock_and_reset(dut) -> None:
    """Start the clock and apply synchronous reset with the APB4 bus idled. The WDT has no
    top-level inputs beyond clk/rst_n/APB4 (no async pins, no CDC)."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n.value = 0
    _idle_bus(dut)

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def _pulse_reset(dut) -> None:
    """Re-apply reset on an already-running clock (used to get a clean, identical starting state
    between the measurement runs inside one test)."""
    dut.rst_n.value = 0
    _idle_bus(dut)
    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def _make_apb_bfm(dut) -> APB4Master:
    """Construct APB4Master BFM targeting the DUT's flat APB4 ports."""
    return APB4Master(dut, "", dut.clk)


async def _peek(dut, addr: int) -> int:
    """Point the idle APB4 bus's read-data path at `addr` and return the value it shows right
    now, with NO APB transaction and NO side effects (apb4_register_bank drives prdata purely
    combinationally off paddr/pwrite, independent of psel/penable). Ported verbatim from
    test_pwm.py / test_gpio.py -- see test_gpio.py's docstring for the Verilator/cocotb settle-
    timing bug this `Timer(1, units="step")` works around."""
    dut.pwrite.value = 0
    dut.paddr.value = addr
    await Timer(1, units="step")
    return int(dut.prdata.value)


async def _next_cycle(dut) -> None:
    """Advance to the next rising edge and let the post-edge state settle, so raw output pins
    (irq_o / wdt_rst_req_o) can be read as that edge's settled value. RisingEdge FIRST, then the
    settle -- see the SAMPLING HAZARD note in the module docstring."""
    await RisingEdge(dut.clk)
    await Timer(1, units="step")


def _raw_write_setup(dut, addr: int, data: int) -> None:
    """Drive the SETUP phase of a raw APB4 write (bypasses APB4Master so the caller can align
    the write's own ACCESS-phase commit edge with a specific internal DUT event, cycle-exact)."""
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 1
    dut.paddr.value = addr
    dut.pwdata.value = data
    dut.pstrb.value = 0xF


def _raw_write_access(dut) -> None:
    """Drive the ACCESS phase (pready is hardwired 1 -- commits this edge)."""
    dut.penable.value = 1


def _raw_write_idle(dut) -> None:
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0


async def _configure(bfm: APB4Master, reload: int, prescale: int = 0, window: int = 0) -> None:
    """Program RELOAD/PRESCALE/WINDOW (always in this order, always all three, so every run has
    the same bus history). The caller writes WDT_CTRL LAST: that write's commit edge is the "E"
    anchor of the timing contract."""
    for addr, val in ((WDT_RELOAD, reload), (WDT_PRESCALE, prescale), (WDT_WINDOW, window)):
        ok = await bfm.write(addr, val)
        assert ok, f"configuration write to 0x{addr:03x} returned SLVERR"


async def _cycles_until_status(dut, mask: int, max_cycles: int) -> int:
    """Advance one edge at a time, peeking WDT_STATUS after each edge, until every bit in `mask`
    reads set; return k, the number of edges consumed (the state is visible after edge k).
    Raises AssertionError on budget exhaustion -- an absent bark/bite is itself a bug this suite
    must catch, never a silent hang. Bus activity: none (peek only)."""
    for k in range(1, max_cycles + 1):
        await RisingEdge(dut.clk)  # edge first, then sample (see SAMPLING HAZARD)
        stat = await _peek(dut, WDT_STATUS)
        if (stat & mask) == mask:
            return k
    raise AssertionError(f"WDT_STATUS bit(s) 0x{mask:x} not observed within {max_cycles} cycles")


def _bark_bounds(reload: int, prescale: int) -> tuple[int, int]:
    """Allowed edge count from E to a visible bark (see the module docstring's timing contract)."""
    return (prescale + 1) * (reload - 1), (prescale + 1) * reload + 6


def _bite_gap_bounds(reload: int, prescale: int) -> tuple[int, int]:
    """Allowed edge count from a visible bark to a visible bite."""
    return max((prescale + 1) * reload, 1), (prescale + 1) * (reload + 1) + 3


async def _measure_bark_bite(
    dut, bfm: APB4Master, reload: int, prescale: int = 0, ctrl: int = CTRL_EN, window: int = 0
) -> tuple[int, int]:
    """Reset, configure, enable, then sample EVERY edge until the bite is visible. Returns
    (k_bark, k_bite) measured in edges after E (the enable write's commit edge). On every sample
    it also asserts the invariants that must hold at every single cycle of a run with no feeds
    and no clears:
      - COUNT never exceeds RELOAD (no underflow wrap of the 32-bit down counter, D1)
      - irq_o == |STATUS[2:0]  (level off the sticky bits, D5)
      - wdt_rst_req_o == STATUS[1]  (rises on the bite edge, lock-step)
      - no window violation (nothing was fed)
    and finally that bark/bite land inside their latency windows."""
    await _pulse_reset(dut)
    await _configure(bfm, reload, prescale, window)
    ok = await bfm.write(WDT_CTRL, ctrl)
    assert ok, "WDT_CTRL enable write returned SLVERR"

    k_bark = k_bite = None
    budget = 3 * (prescale + 1) * (reload + 2) + 40
    for k in range(1, budget + 1):
        await RisingEdge(dut.clk)  # edge first, then sample (see SAMPLING HAZARD)
        stat = await _peek(dut, WDT_STATUS)
        cnt = await _peek(dut, WDT_COUNT)
        irq = int(dut.irq_o.value)
        rst = int(dut.wdt_rst_req_o.value)
        assert cnt <= reload, f"COUNT 0x{cnt:x} exceeds RELOAD {reload} at edge {k} (underflow?)"
        assert stat & ST_VIOL == 0, f"spurious window violation with no feeds, STATUS=0x{stat:x}"
        assert irq == int((stat & ST_ALL) != 0), (
            f"irq_o ({irq}) must equal |STATUS[2:0] (STATUS=0x{stat:x}) at edge {k}"
        )
        assert rst == ((stat >> 1) & 1), (
            f"wdt_rst_req_o ({rst}) must rise on the same edge as STATUS[1] (STATUS=0x{stat:x}) "
            f"at edge {k}"
        )
        if k_bark is None and (stat & ST_BARK):
            k_bark = k
        if k_bite is None and (stat & ST_BITE):
            k_bite = k
            break
    assert k_bark is not None, f"no bark within {budget} cycles (R={reload}, P={prescale})"
    assert k_bite is not None, f"no bite within {budget} cycles (R={reload}, P={prescale})"

    lo, hi = _bark_bounds(reload, prescale)
    assert lo <= k_bark <= hi, (
        f"bark at edge {k_bark}, expected within [{lo}, {hi}] (R={reload}, P={prescale})"
    )
    gap = k_bite - k_bark
    glo, ghi = _bite_gap_bounds(reload, prescale)
    assert glo <= gap <= ghi, (
        f"bite {gap} cycles after the bark, expected within [{glo}, {ghi}] (R={reload}, P={prescale}) "
        f"-- a second FULL period must elapse"
    )
    return k_bark, k_bite


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_wdt_reset_defaults(dut):
    """After reset every RW register reads 0 (CTRL -- including RST_EN -- RELOAD, WINDOW,
    PRESCALE), COUNT reads 0, STATUS reads 0, FEED and IRQ_CLR read 0, irq_o == 0 and
    wdt_rst_req_o == 0."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    expected = {
        "WDT_CTRL": WDT_CTRL,
        "WDT_RELOAD": WDT_RELOAD,
        "WDT_COUNT": WDT_COUNT,
        "WDT_WINDOW": WDT_WINDOW,
        "WDT_FEED": WDT_FEED,
        "WDT_PRESCALE": WDT_PRESCALE,
        "WDT_STATUS": WDT_STATUS,
        "WDT_IRQ_CLR": WDT_IRQ_CLR,
    }
    for name, addr in expected.items():
        data, ok = await bfm.read(addr)
        assert ok, f"{name} reset-default read returned SLVERR"
        assert data == 0, f"{name} expected 0 at reset, got 0x{data:08x}"

    ctrl, _ = await bfm.read(WDT_CTRL)
    assert ctrl & CTRL_RST_EN == 0, "WDT_CTRL.RST_EN (bit 1) must reset to 0"
    assert ctrl & CTRL_EN == 0, "the watchdog must reset DISABLED"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0, f"irq_o expected 0 at reset, got {int(dut.irq_o.value)}"
    assert int(dut.wdt_rst_req_o.value) == 0, "wdt_rst_req_o expected 0 at reset"
    dut._log.info("WDT reset defaults confirmed")


@cocotb.test()
async def test_wdt_rw_roundtrip_all_registers(dut):
    """Round trip on every RW register. RELOAD/WINDOW are full 32-bit; PRESCALE is [15:0] and
    CTRL is [2:0] (D9), so a write of all-ones reads back masked. The watchdog is left disabled
    while the data registers are exercised; CTRL goes last and is restored to 0."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    # (name, addr, written pattern, expected readback)
    cases = [
        ("WDT_RELOAD", WDT_RELOAD, 0x89AB_CDEF, 0x89AB_CDEF),
        ("WDT_RELOAD", WDT_RELOAD, 0xFFFF_FFFF, 0xFFFF_FFFF),
        ("WDT_WINDOW", WDT_WINDOW, 0x1234_5678, 0x1234_5678),
        ("WDT_WINDOW", WDT_WINDOW, 0xFFFF_FFFF, 0xFFFF_FFFF),
        ("WDT_PRESCALE", WDT_PRESCALE, 0x0000_CAFE, 0x0000_CAFE),
        ("WDT_PRESCALE", WDT_PRESCALE, 0xFFFF_CAFE, 0x0000_CAFE),  # [31:16] reserved
        ("WDT_CTRL", WDT_CTRL, 0x0000_0005, 0x0000_0005),  # window mode + enable
        ("WDT_CTRL", WDT_CTRL, 0xFFFF_FFFF, 0x0000_0007),  # only [2:0] are defined
    ]
    for name, addr, pattern, expect in cases:
        ok_w = await bfm.write(addr, pattern)
        assert ok_w, f"{name} write returned SLVERR"
        data, ok_r = await bfm.read(addr)
        assert ok_r, f"{name} readback returned SLVERR"
        assert data == expect, (
            f"{name} wrote 0x{pattern:08x}: got 0x{data:08x}, expected 0x{expect:08x}"
        )
        ok_c = await bfm.write(addr, 0)
        assert ok_c, f"{name} clear-back-to-0 write returned SLVERR"
        data, _ = await bfm.read(addr)
        assert data == 0, f"{name} must clear back to 0, got 0x{data:08x}"
    dut._log.info(
        "RW round trip confirmed on CTRL/RELOAD/WINDOW/PRESCALE incl. reserved-bit masking"
    )


@cocotb.test()
async def test_wdt_ro_ignores_writes_wo_reads_zero(dut):
    """WDT_COUNT and WDT_STATUS are read-only: writes (all-ones) are ignored. WDT_FEED and
    WDT_IRQ_CLR are write-only: they read 0 no matter what was last written. The watchdog is
    disabled throughout, so no feed can have side effects and COUNT/STATUS have nothing to show."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for name, addr in (("WDT_COUNT", WDT_COUNT), ("WDT_STATUS", WDT_STATUS)):
        ok_w = await bfm.write(addr, 0xFFFF_FFFF)
        assert ok_w, f"{name} write returned SLVERR (RO writes must be silently ignored)"
        data, ok_r = await bfm.read(addr)
        assert ok_r
        assert data == 0, f"{name} is read-only, must ignore a write; got 0x{data:08x}"

    for name, addr in (("WDT_FEED", WDT_FEED), ("WDT_IRQ_CLR", WDT_IRQ_CLR)):
        for pattern in (MAGIC, 0xFFFF_FFFF, 0x1234_5678, 0x0000_0001):
            ok_w = await bfm.write(addr, pattern)
            assert ok_w, f"{name} write(0x{pattern:08x}) returned SLVERR"
            data, ok_r = await bfm.read(addr)
            assert ok_r
            assert data == 0, (
                f"{name} must always read 0, got 0x{data:08x} after writing 0x{pattern:08x}"
            )
    dut._log.info("RO-ignore-writes and WO-reads-zero confirmed")


@cocotb.test()
async def test_wdt_out_of_range_access(dut):
    """Word index >= 8 (byte offset >= 0x020, inside the 12-bit ADDR_W slot) is out of range:
    writes are silently dropped and reads return 0, both with pslverr == 0. Made sharper than the
    plain policy check: the watchdog is RUNNING while a magic value is stored to 0x030 (which
    would be WDT_FEED if the decode aliased modulo 8) and 0 is stored to 0x020 (which would
    disable the watchdog if it aliased onto WDT_CTRL) -- neither may have any effect."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _configure(bfm, 500)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await ClockCycles(dut.clk, 10)

    prev = await _peek(dut, WDT_COUNT)
    for addr, data in ((WDT_OUT_OF_RANGE, 0x0), (0x030, MAGIC), (0x0FC, 0xFFFF_FFFF)):
        ok_w = await bfm.write(addr, data)
        assert ok_w, f"out-of-range write to 0x{addr:03x} must return OKAY (pslverr=0), got SLVERR"
        rd, ok_r = await bfm.read(addr)
        assert ok_r, f"out-of-range read from 0x{addr:03x} must return OKAY (pslverr=0), got SLVERR"
        assert rd == 0, f"out-of-range read from 0x{addr:03x} must return 0, got 0x{rd:08x}"
        cur = await _peek(dut, WDT_COUNT)
        assert cur < prev, (
            f"an out-of-range write to 0x{addr:03x} must not touch the counter "
            f"(COUNT {prev} -> {cur}); aliased decode?"
        )
        prev = cur

    ctrl, _ = await bfm.read(WDT_CTRL)
    reload, _ = await bfm.read(WDT_RELOAD)
    assert ctrl == CTRL_EN, f"an out-of-range write must not alias onto WDT_CTRL, got 0x{ctrl:08x}"
    assert reload == 500, f"out-of-range writes must not alias onto WDT_RELOAD, got {reload}"
    dut._log.info(
        "out-of-range access policy (drop write, read 0, pslverr=0, no aliasing) confirmed"
    )


@cocotb.test()
async def test_wdt_pstrb_partial_word(dut):
    """Byte-strobed writes update only the strobed bytes; strb == 0 is a no-op; bytes outside a
    register's implemented bits stay 0. Exercised on RELOAD (32 bits) and PRESCALE ([15:0])."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    assert await bfm.write(WDT_RELOAD, 0xAABB_CCDD)
    steps = [
        (0x0000_0011, 0x1, 0xAABB_CC11),  # byte 0 only
        (0x9900_0000, 0x8, 0x99BB_CC11),  # byte 3 only
        (0x00EE_FF00, 0x6, 0x99EE_FF11),  # bytes 1-2
        (0x0000_0000, 0x0, 0x99EE_FF11),  # no strobe: no-op
    ]
    for data, strb, expect in steps:
        assert await bfm.write(WDT_RELOAD, data, strb=strb)
        got, _ = await bfm.read(WDT_RELOAD)
        assert got == expect, (
            f"RELOAD strb=0x{strb:x} write 0x{data:08x}: got 0x{got:08x}, expected 0x{expect:08x}"
        )

    assert await bfm.write(WDT_PRESCALE, 0x0000_1234)
    assert await bfm.write(WDT_PRESCALE, 0x0000_5600, strb=0x2)  # byte 1 only
    got, _ = await bfm.read(WDT_PRESCALE)
    assert got == 0x5634, f"PRESCALE byte-1 strobed write: got 0x{got:08x}, expected 0x00005634"
    assert await bfm.write(WDT_PRESCALE, 0xFFFF_0000, strb=0xC)  # bytes 2-3: outside [15:0]
    got, _ = await bfm.read(WDT_PRESCALE)
    assert got == 0x5634, f"PRESCALE [31:16] is reserved, got 0x{got:08x}"
    dut._log.info("pstrb partial-word writes confirmed")


@cocotb.test()
async def test_wdt_feed_magic_accepted(dut):
    """The magic value 0x5A5A_C0DE written to WDT_FEED reloads the counter. Three angles: (a) a
    feed mid-period makes COUNT jump back up to ~RELOAD, (b) feeding every half period for six
    full periods never lets the dog bark, (c) once feeding stops, the bark arrives on schedule
    (measured from the last feed's commit edge)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 60
    await _configure(bfm, reload)
    assert await bfm.write(WDT_CTRL, CTRL_EN)

    # (a) reload observable
    await ClockCycles(dut.clk, 30)
    c0 = await _peek(dut, WDT_COUNT)
    assert c0 < reload - 20, f"precondition: counter should have run down, got {c0}"
    assert await bfm.write(WDT_FEED, MAGIC), "magic feed returned SLVERR"
    await ClockCycles(dut.clk, 2)
    c1 = await _peek(dut, WDT_COUNT)
    assert c1 > c0 and reload - 6 <= c1 <= reload, (
        f"a valid feed must reload the counter: COUNT {c0} -> {c1}, expected ~{reload}"
    )

    # (b) keep-alive over 6 full periods
    for i in range(12):
        await ClockCycles(dut.clk, 28)
        assert await bfm.write(WDT_FEED, MAGIC)
        stat = await _peek(dut, WDT_STATUS)
        assert stat == 0, f"STATUS=0x{stat:x} after feed #{i}: the dog must stay quiet while fed"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0 and int(dut.wdt_rst_req_o.value) == 0

    # (c) feeding stops -> bark on schedule from the LAST feed's commit edge
    k = await _cycles_until_status(dut, ST_BARK, reload + 30)
    assert reload - 2 <= k <= reload + 10, (
        f"bark {k} edges after the last valid feed, expected ~{reload} (feed reloads a FULL period)"
    )
    dut._log.info(
        f"magic feed accepted; keep-alive quiet; bark {k} edges after last feed (R={reload})"
    )


@cocotb.test()
async def test_wdt_feed_wrong_value_rejected(dut):
    """Any value other than the magic word is rejected: the counter keeps counting, so a wild-
    pointer store cannot accidentally pet the dog. Also rejected: the magic word with a partial
    pstrb (D4). Proven two ways -- COUNT keeps strictly falling across every rejected write, AND
    the bark still lands on its original schedule from enable. Finally a real feed is accepted
    (so the rejections above are not simply a dead bus)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 60
    await _configure(bfm, reload)
    assert await bfm.write(WDT_CTRL, CTRL_EN)  # edge E
    elapsed = 0

    await ClockCycles(dut.clk, 20)
    elapsed += 20
    prev = await _peek(dut, WDT_COUNT)

    attempts = [
        (0x5A5A_C0DF, 0xF),
        (0xA5A5_C0DE, 0xF),
        (0x0000_C0DE, 0xF),
        (0x5A5A_0000, 0xF),
        (0xFFFF_FFFF, 0xF),
        (0x0000_0000, 0xF),
        (MAGIC, 0x7),  # partial strobes: byte 3 missing
        (MAGIC, 0xE),  # byte 0 missing
        (MAGIC, 0x3),
        (MAGIC, 0x1),
    ]
    for data, strb in attempts:
        assert await bfm.write(WDT_FEED, data, strb=strb), (
            "FEED write must return OKAY even when rejected"
        )
        elapsed += 2
        cur = await _peek(dut, WDT_COUNT)
        assert cur < prev, (
            f"rejected feed (data=0x{data:08x}, strb=0x{strb:x}) must not reload: COUNT {prev} -> {cur}"
        )
        stat = await _peek(dut, WDT_STATUS)
        assert stat == 0, f"a rejected feed must not set any status bit, got 0x{stat:x}"
        prev = cur

    k = await _cycles_until_status(dut, ST_BARK, reload + 30)
    total = elapsed + k
    lo, hi = _bark_bounds(reload, 0)
    assert lo <= total <= hi, (
        f"bark at edge {total} after enable; rejected feeds must not move it (expected [{lo}, {hi}])"
    )

    # A real feed still works on the same bus (reset first so it is a fresh, unbarked run).
    await _pulse_reset(dut)
    await _configure(bfm, reload)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await ClockCycles(dut.clk, 30)
    before = await _peek(dut, WDT_COUNT)
    assert await bfm.write(WDT_FEED, MAGIC, strb=0xF)
    await ClockCycles(dut.clk, 2)
    after = await _peek(dut, WDT_COUNT)
    assert after > before, f"full-strobe magic feed must be accepted: COUNT {before} -> {after}"
    dut._log.info("wrong values and partial-strobe magic rejected; full magic accepted")


@cocotb.test()
async def test_wdt_bark_timing(dut):
    """Bark is visible within the documented latency window after enable, and the latency is a
    constant: raising RELOAD from 16 to 40 (P=0) moves the bark EXACTLY 24 cycles later. At the
    bark the bite bit and wdt_rst_req_o are still clear, and irq_o has risen. (Every-cycle
    invariants -- COUNT <= RELOAD, irq_o == |STATUS, rst_req lock-step -- are asserted inside
    _measure_bark_bite for the whole run.)"""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ks = {}
    for reload in (16, 40):
        k_bark, k_bite = await _measure_bark_bite(dut, bfm, reload)
        ks[reload] = k_bark
        assert k_bite > k_bark
    assert ks[40] - ks[16] == 24, (
        f"bark time must scale exactly with RELOAD at P=0: k(16)={ks[16]}, k(40)={ks[40]}, "
        f"difference {ks[40] - ks[16]} != 24"
    )

    # State at the bark edge itself: bark set, bite NOT yet, irq_o up, no reset request.
    await _pulse_reset(dut)
    await _configure(bfm, 40)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await _cycles_until_status(dut, ST_BARK, 40 + 20)
    stat = await _peek(dut, WDT_STATUS)
    assert stat == ST_BARK, f"at the bark edge STATUS must be exactly bark, got 0x{stat:x}"
    assert int(dut.irq_o.value) == 1, "irq_o must rise with the bark"
    assert int(dut.wdt_rst_req_o.value) == 0, (
        "wdt_rst_req_o must NOT assert on a bark, only on the bite"
    )
    dut._log.info(f"bark timing confirmed: k(16)={ks[16]} k(40)={ks[40]}")


@cocotb.test()
async def test_wdt_bite_timing_and_rst_req_level_hold(dut):
    """A second FULL period after the bark, with no valid feed, is the bite: sticky STATUS[1] and
    wdt_rst_req_o rise together. The gap scales exactly with RELOAD (16 -> 40 adds exactly 24).
    wdt_rst_req_o is level-held until reset -- unaffected by W1C-clearing the bite bit and by a
    valid feed -- and bite is TERMINAL (D7): the counter is frozen at 0 and no further events
    accumulate. Only rst_n drops the request."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    gaps = {}
    for reload in (40, 16):  # ends on 16, leaving the DUT at the bite for the post-bite checks
        k_bark, k_bite = await _measure_bark_bite(dut, bfm, reload)
        gaps[reload] = k_bite - k_bark
    assert gaps[40] - gaps[16] == 24, (
        f"bark->bite gap must scale exactly with RELOAD at P=0: gap(16)={gaps[16]}, gap(40)={gaps[40]}"
    )

    # Level-held: 60 consecutive settled cycles after the bite, request still up, counter frozen.
    for cycle in range(60):
        await _next_cycle(dut)
        assert int(dut.wdt_rst_req_o.value) == 1, (
            f"wdt_rst_req_o dropped {cycle} cycles after the bite (must be level-held)"
        )
        assert await _peek(dut, WDT_COUNT) == 0, "bite is terminal: COUNT must stay frozen at 0"

    # W1C-clear every status bit: the sticky bits go, the reset request does NOT.
    assert await bfm.write(WDT_IRQ_CLR, ST_ALL)
    stat = await _peek(dut, WDT_STATUS)
    assert stat == 0, f"W1C of all bits must clear STATUS, got 0x{stat:x}"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0, "irq_o must drop once every sticky bit is cleared"
    assert int(dut.wdt_rst_req_o.value) == 1, (
        "wdt_rst_req_o must survive a W1C clear (held until RESET)"
    )

    # A valid feed after the bite does not revive the dog or drop the request (terminal).
    assert await bfm.write(WDT_FEED, MAGIC)
    await ClockCycles(dut.clk, 3 * 16 + 10)
    stat = await _peek(dut, WDT_STATUS)
    assert stat == 0, (
        f"bite is terminal: no further events after a post-bite feed, got STATUS=0x{stat:x}"
    )
    assert await _peek(dut, WDT_COUNT) == 0
    await Timer(1, units="step")
    assert int(dut.wdt_rst_req_o.value) == 1, "a feed must not drop wdt_rst_req_o"

    # Only reset clears it.
    await _pulse_reset(dut)
    await Timer(1, units="step")
    assert int(dut.wdt_rst_req_o.value) == 0, "rst_n must clear wdt_rst_req_o"
    assert await _peek(dut, WDT_STATUS) == 0
    dut._log.info(
        f"bite timing + level-hold + terminal confirmed: gap(16)={gaps[16]} gap(40)={gaps[40]}"
    )


@cocotb.test()
async def test_wdt_rst_en_does_not_gate_wdt_rst_req(dut):
    """WDT_CTRL.RST_EN resets to 0 and governs ONLY the SoC-level CPU-domain reset path (a soc_top
    integration concern, invisible at this L1 boundary). So at the default RST_EN == 0 a bite must
    STILL set STATUS[1] and STILL assert wdt_rst_req_o, and the bark/bite timing must be
    IDENTICAL with RST_EN == 1. _measure_bark_bite already asserts wdt_rst_req_o == STATUS[1] on
    every cycle, so a design that gated the request with RST_EN fails inside it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ctrl0, _ = await bfm.read(WDT_CTRL)
    assert ctrl0 & CTRL_RST_EN == 0, "RST_EN must reset to 0"

    timing_off = await _measure_bark_bite(dut, bfm, 16, ctrl=CTRL_EN)  # RST_EN = 0
    await Timer(1, units="step")
    assert int(dut.wdt_rst_req_o.value) == 1, "RST_EN=0: a bite must still assert wdt_rst_req_o"
    assert await _peek(dut, WDT_STATUS) & ST_BITE, "RST_EN=0: a bite must still set STATUS[1]"

    timing_on = await _measure_bark_bite(dut, bfm, 16, ctrl=CTRL_EN | CTRL_RST_EN)  # RST_EN = 1
    await Timer(1, units="step")
    assert int(dut.wdt_rst_req_o.value) == 1, "RST_EN=1: a bite asserts wdt_rst_req_o"
    ctrl1, _ = await bfm.read(WDT_CTRL)
    assert ctrl1 == CTRL_EN | CTRL_RST_EN, f"CTRL readback with RST_EN=1: 0x{ctrl1:x}"

    assert timing_off == timing_on, (
        f"RST_EN must not change bark/bite timing at the L1 boundary: RST_EN=0 {timing_off}, "
        f"RST_EN=1 {timing_on}"
    )
    dut._log.info(f"RST_EN independence confirmed: bark/bite = {timing_off} both ways")


@cocotb.test()
async def test_wdt_feed_after_bark_defers_bite(dut):
    """After a bark the watchdog is in its second period. Valid feeds during it must prevent the
    bite (D6: a feed clears the escalation as well as reloading): feed every ~22 cycles for
    ~130 cycles (more than three full R=40 periods) and neither STATUS[1] nor wdt_rst_req_o may
    appear. Then stop feeding: the bite must arrive ~two periods after the last feed -- NOT one
    (which would mean the feed only reloaded the counter without clearing the escalation)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 40
    await _configure(bfm, reload)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await _cycles_until_status(dut, ST_BARK, reload + 20)

    for i in range(6):
        await ClockCycles(dut.clk, 20)
        assert await bfm.write(WDT_FEED, MAGIC)
        stat = await _peek(dut, WDT_STATUS)
        assert stat & ST_BITE == 0, f"bite after bark despite valid feed #{i}: STATUS=0x{stat:x}"
        await Timer(1, units="step")
        assert int(dut.wdt_rst_req_o.value) == 0, f"wdt_rst_req_o asserted despite valid feed #{i}"

    k = await _cycles_until_status(dut, ST_BITE, 4 * reload)
    assert 2 * reload - 2 <= k <= 2 * reload + 12, (
        f"bite {k} edges after the last valid feed; a feed must restart the FULL two-period "
        f"escalation, expected ~{2 * reload}"
    )
    await Timer(1, units="step")
    assert int(dut.wdt_rst_req_o.value) == 1
    dut._log.info(f"feed-after-bark defers bite: bite {k} edges after last feed (2R={2 * reload})")


@cocotb.test()
async def test_wdt_window_violation_no_reload(dut):
    """Window mode on (CTRL[2]) with WINDOW=50, RELOAD=200: a feed at COUNT ~180 (> WINDOW, the
    window is closed) is a violation. It sets STATUS[2], raises irq_o (D5), and must NOT reload
    the counter (COUNT keeps falling from where it was) nor assert wdt_rst_req_o or set bark/bite
    (D8). Later, once COUNT has fallen to <= WINDOW, a feed is accepted: COUNT jumps back to
    ~RELOAD and no new violation is recorded."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload, window = 200, 50
    await _configure(bfm, reload, window=window)
    assert await bfm.write(WDT_CTRL, CTRL_EN | CTRL_WIN_EN)
    await ClockCycles(dut.clk, 20)

    c0 = await _peek(dut, WDT_COUNT)
    assert c0 > window, f"precondition: window must still be closed, COUNT={c0}"
    assert await bfm.write(WDT_FEED, MAGIC)
    await ClockCycles(dut.clk, 2)
    stat = await _peek(dut, WDT_STATUS)
    assert stat == ST_VIOL, f"an early feed must set exactly STATUS[2], got 0x{stat:x}"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 1, "a window violation must raise irq_o (D5)"
    assert int(dut.wdt_rst_req_o.value) == 0, (
        "a window violation alone must not request a reset (D8)"
    )
    c1 = await _peek(dut, WDT_COUNT)
    assert c1 < c0, f"an early (violating) feed must NOT reload: COUNT {c0} -> {c1}"

    # Clear the violation, run down into the open window, feed legitimately.
    assert await bfm.write(WDT_IRQ_CLR, ST_VIOL)
    assert await _peek(dut, WDT_STATUS) == 0
    for _ in range(reload):
        await RisingEdge(dut.clk)
        if await _peek(dut, WDT_COUNT) <= 30:
            break
    else:
        raise AssertionError("COUNT never fell into the open window")
    assert await bfm.write(WDT_FEED, MAGIC)
    await ClockCycles(dut.clk, 2)
    c2 = await _peek(dut, WDT_COUNT)
    stat = await _peek(dut, WDT_STATUS)
    assert reload - 8 <= c2 <= reload, f"an in-window feed must reload the counter, got COUNT={c2}"
    assert stat == 0, f"an in-window feed must not record a violation, got STATUS=0x{stat:x}"
    dut._log.info("window violation sets STATUS[2] without reloading; in-window feed accepted")


@cocotb.test()
async def test_wdt_window_boundary(dut):
    """The closed window is strictly 'COUNT above WINDOW'. With PRESCALE=15 every COUNT value
    persists for 16 cycles, so the boundary can be hit deterministically: a feed while COUNT ==
    WINDOW+1 is a violation (no reload); a feed while COUNT == WINDOW is ACCEPTED (reload, no
    violation)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload, window, prescale = 40, 20, 15
    await _configure(bfm, reload, prescale, window)
    assert await bfm.write(WDT_CTRL, CTRL_EN | CTRL_WIN_EN)

    async def wait_count(target: int) -> None:
        for _ in range(reload * (prescale + 1) + 64):
            await RisingEdge(dut.clk)  # edge first, then sample
            if await _peek(dut, WDT_COUNT) == target:
                return
        raise AssertionError(f"COUNT never reached {target}")

    await wait_count(window + 1)
    assert await bfm.write(WDT_FEED, MAGIC)
    await ClockCycles(dut.clk, 2)
    stat = await _peek(dut, WDT_STATUS)
    cnt = await _peek(dut, WDT_COUNT)
    assert stat == ST_VIOL, (
        f"COUNT == WINDOW+1 is still closed: expected a violation, got STATUS=0x{stat:x}"
    )
    assert cnt <= window + 1, f"a violating feed must not reload, COUNT={cnt}"

    assert await bfm.write(WDT_IRQ_CLR, ST_VIOL)
    assert await _peek(dut, WDT_STATUS) == 0

    await wait_count(window)
    assert await bfm.write(WDT_FEED, MAGIC)
    await ClockCycles(dut.clk, 2)
    stat = await _peek(dut, WDT_STATUS)
    cnt = await _peek(dut, WDT_COUNT)
    assert stat == 0, (
        f"COUNT == WINDOW is inside the open window: no violation expected, got 0x{stat:x}"
    )
    assert cnt >= reload - 1, f"COUNT == WINDOW feed must be accepted (reload), got COUNT={cnt}"
    dut._log.info("window boundary confirmed: WINDOW+1 violates, WINDOW accepted")


@cocotb.test()
async def test_wdt_window_disabled_accepts_any_feed(dut):
    """Window mode is default-disabled and needs BOTH CTRL[2]==1 and WINDOW != 0. A feed at COUNT
    ~170 (way above any plausible threshold) must be accepted -- COUNT jumps back up, STATUS[2]
    stays 0 -- (a) with CTRL[2]=1 but WINDOW == 0, and (b) with WINDOW=50 but CTRL[2]==0."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 200
    for label, window, ctrl in (
        ("WINDOW==0, window mode on", 0, CTRL_EN | CTRL_WIN_EN),
        ("window mode off, WINDOW=50", 50, CTRL_EN),
    ):
        await _pulse_reset(dut)
        await _configure(bfm, reload, window=window)
        assert await bfm.write(WDT_CTRL, ctrl)
        await ClockCycles(dut.clk, 30)
        before = await _peek(dut, WDT_COUNT)
        assert before < reload - 20
        assert await bfm.write(WDT_FEED, MAGIC)
        await ClockCycles(dut.clk, 2)
        after = await _peek(dut, WDT_COUNT)
        stat = await _peek(dut, WDT_STATUS)
        assert stat == 0, (
            f"[{label}] feed must be accepted with no violation, got STATUS=0x{stat:x}"
        )
        assert reload - 8 <= after <= reload, (
            f"[{label}] feed must reload the counter: {before} -> {after}"
        )
    dut._log.info("window disabled (WINDOW==0 and CTRL[2]==0) accepts a feed at any time")


@cocotb.test()
async def test_wdt_prescaler_scaling(dut):
    """One counter tick = (PRESCALE+1) core_clk cycles. In steady state COUNT falls by EXACTLY 10
    over 10*(P+1) cycles, for P = 0, 3 and 7. (Two peeks a whole number of ticks apart, so the
    prescaler phase cancels.) Coarse end-to-end check as well: at P=3 the bark->bite gap is
    ~(P+1)*RELOAD cycles."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for prescale in (0, 3, 7):
        await _pulse_reset(dut)
        await _configure(bfm, 100_000, prescale)
        assert await bfm.write(WDT_CTRL, CTRL_EN)
        await ClockCycles(dut.clk, 24)  # settle into steady state
        await RisingEdge(dut.clk)  # sample on a known edge
        c0 = await _peek(dut, WDT_COUNT)
        await ClockCycles(dut.clk, 10 * (prescale + 1))
        c1 = await _peek(dut, WDT_COUNT)
        assert c0 - c1 == 10, (
            f"P={prescale}: COUNT must fall by exactly 10 in {10 * (prescale + 1)} cycles, got {c0} -> {c1}"
        )

    k_bark, k_bite = await _measure_bark_bite(dut, bfm, 6, prescale=3)
    dut._log.info(f"prescaler scaling confirmed; P=3 R=6 bark={k_bark} bite={k_bite}")


@cocotb.test()
async def test_wdt_disabled_is_inert(dut):
    """CTRL[0] == 0: no bark, bite or violation accumulates and the counter does not run -- not
    with a tiny RELOAD, not with window mode armed, not with feeds (valid or not) hammering the
    FEED register. It is not vacuous: enabling afterwards makes the very same configuration bark.
    Also: disabling a RUNNING watchdog freezes it (COUNT stable, nothing fires even after several
    periods) and re-enabling reloads the counter (D8)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _configure(bfm, 4, window=3)
    assert await bfm.write(WDT_CTRL, CTRL_WIN_EN)  # window armed, enable OFF
    c_start = await _peek(dut, WDT_COUNT)
    for data in (MAGIC, 0x1234_5678):
        assert await bfm.write(WDT_FEED, data)
    await ClockCycles(dut.clk, 200)
    stat = await _peek(dut, WDT_STATUS)
    assert stat == 0, (
        f"disabled: no status may accumulate (no bark/bite, no violation from a feed), got 0x{stat:x}"
    )
    assert await _peek(dut, WDT_COUNT) == c_start, "disabled: the counter must not run"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0 and int(dut.wdt_rst_req_o.value) == 0

    # Non-vacuous: the same configuration, enabled, barks.
    assert await bfm.write(WDT_CTRL, CTRL_EN | CTRL_WIN_EN)
    k = await _cycles_until_status(dut, ST_BARK, 40)
    lo, hi = _bark_bounds(4, 0)
    assert lo <= k <= hi, f"control run: bark at {k}, expected [{lo}, {hi}]"

    # Disable a running watchdog: frozen, silent, and re-enable reloads.
    await _pulse_reset(dut)
    await _configure(bfm, 100)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await ClockCycles(dut.clk, 30)
    assert await bfm.write(WDT_CTRL, 0)
    frozen = await _peek(dut, WDT_COUNT)
    await ClockCycles(dut.clk, 250)  # > 2 full periods
    assert await _peek(dut, WDT_COUNT) == frozen, "disabling must stop the counter"
    stat = await _peek(dut, WDT_STATUS)
    assert stat == 0, f"nothing may fire while disabled, got STATUS=0x{stat:x}"
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await ClockCycles(dut.clk, 3)
    cnt = await _peek(dut, WDT_COUNT)
    assert 100 - 8 <= cnt <= 100, (
        f"re-enabling must reload the counter from RELOAD, got COUNT={cnt}"
    )
    dut._log.info("disabled watchdog confirmed inert; disable freezes; enable reloads")


@cocotb.test()
async def test_wdt_reload_zero_fails_toward_firing(dut):
    """D1: enabled with RELOAD == 0 (also the state after 'enable without programming RELOAD',
    since RELOAD resets to 0) the watchdog FAILS TOWARD FIRING: bark within a few cycles, bite
    right after, COUNT reading 0 throughout (never underflowing to 0xFFFF_FFFF, never hanging for
    ~2^32 ticks). Every-cycle invariants come from _measure_bark_bite (COUNT <= RELOAD == 0 on
    every sample). A silent watchdog is the dangerous failure; a misconfigured one must be noisy."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    k_bark, k_bite = await _measure_bark_bite(dut, bfm, 0)
    assert k_bark <= 6, f"RELOAD==0 must bark promptly, took {k_bark} cycles"
    assert 1 <= k_bite - k_bark <= 4, (
        f"RELOAD==0 second period is zero-length: gap {k_bite - k_bark}"
    )
    await Timer(1, units="step")
    assert int(dut.wdt_rst_req_o.value) == 1
    dut._log.info(
        f"RELOAD==0 fails toward firing: bark at {k_bark}, bite at {k_bite}, COUNT stayed 0"
    )


@cocotb.test()
async def test_wdt_reload_write_deferred_to_next_reload(dut):
    """D2: a write to WDT_RELOAD while RUNNING does not touch the live counter; it is picked up at
    the next reload event. RELOAD=200 running -> write 1000 -> COUNT keeps falling (no jump to
    1000). Then write 6, far below the live COUNT (~150): the dog must NOT time out immediately
    and COUNT must not clamp to 6. A feed then loads the NEW value (COUNT <= 6) and the bark
    follows within a few cycles."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _configure(bfm, 200)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await ClockCycles(dut.clk, 20)

    c0 = await _peek(dut, WDT_COUNT)
    assert await bfm.write(WDT_RELOAD, 1000)
    c1 = await _peek(dut, WDT_COUNT)
    assert c1 < c0 <= 200, f"raising RELOAD mid-run must not reload the counter: COUNT {c0} -> {c1}"

    assert await bfm.write(WDT_RELOAD, 6)
    await ClockCycles(dut.clk, 12)
    stat = await _peek(dut, WDT_STATUS)
    c2 = await _peek(dut, WDT_COUNT)
    assert stat == 0, (
        f"lowering RELOAD mid-run must not cause an immediate timeout, got STATUS=0x{stat:x}"
    )
    assert c2 > 100, f"lowering RELOAD mid-run must not clamp the live counter, got COUNT={c2}"

    assert await bfm.write(WDT_FEED, MAGIC)
    await ClockCycles(dut.clk, 2)
    c3 = await _peek(dut, WDT_COUNT)
    assert c3 <= 6, f"the next reload must pick up the NEW RELOAD (6), got COUNT={c3}"
    k = await _cycles_until_status(dut, ST_BARK, 30)
    assert k <= 6 + 6, f"bark after a reload from RELOAD=6 must be prompt, took {k}"
    dut._log.info("RELOAD writes take effect at the next reload, not immediately")


@cocotb.test()
async def test_wdt_count_readable_without_side_effects(dut):
    """D3: WDT_COUNT is readable through real APB reads while the counter runs. Six rounds of
    {read COUNT, read FEED, read STATUS, read IRQ_CLR} (8 clock edges per round): every COUNT
    sample falls by EXACTLY 8 from the last -- so reading COUNT costs nothing, and above all
    reading the WO FEED register does NOT feed (a feed would raise COUNT), reading IRQ_CLR does
    not clear anything and no read sets a status bit."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 5000
    await _configure(bfm, reload)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    await ClockCycles(dut.clk, 10)

    samples = []
    for _ in range(6):
        cnt, ok = await bfm.read(WDT_COUNT)
        assert ok
        for addr in (WDT_FEED, WDT_STATUS, WDT_IRQ_CLR):
            data, ok = await bfm.read(addr)
            assert ok
            assert data == 0, f"read of 0x{addr:03x} must return 0 here, got 0x{data:x}"
        samples.append(cnt)

    assert all(s <= reload for s in samples), f"COUNT must never exceed RELOAD: {samples}"
    diffs = [a - b for a, b in zip(samples, samples[1:])]
    assert diffs == [8] * 5, (
        f"COUNT must fall by exactly 8 per 8-edge round, unperturbed by reads: samples={samples} diffs={diffs}"
    )
    assert await _peek(dut, WDT_STATUS) == 0
    dut._log.info(f"COUNT readable, reads side-effect free: {samples}")


@cocotb.test()
async def test_wdt_status_sticky_and_w1c(dut):
    """Drive STATUS to 0b111 (violation from an early feed, then bark, then bite). Every bit is
    sticky: STATUS is unchanged 50 cycles later. W1C: writing 0 bits is a no-op; writing 1 to a
    bit clears exactly that bit (0x4 -> 0x3, 0x1 -> 0x2, 0x2 -> 0x0); irq_o follows |STATUS[2:0]
    (still high while any bit is left, low at 0); wdt_rst_req_o stays up through every clear."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 40
    await _configure(bfm, reload, window=10)
    assert await bfm.write(WDT_CTRL, CTRL_EN | CTRL_WIN_EN)
    await ClockCycles(dut.clk, 5)
    assert await bfm.write(WDT_FEED, MAGIC)  # early -> violation
    await _cycles_until_status(dut, ST_BITE, 6 * reload)
    stat = await _peek(dut, WDT_STATUS)
    assert stat == ST_ALL, f"expected violation+bark+bite = 0x7, got 0x{stat:x}"

    await ClockCycles(dut.clk, 50)
    assert await _peek(dut, WDT_STATUS) == ST_ALL, "every STATUS bit must be sticky"

    async def check(expect_stat: int, expect_irq: int, what: str) -> None:
        stat = await _peek(dut, WDT_STATUS)
        assert stat == expect_stat, f"{what}: STATUS expected 0x{expect_stat:x}, got 0x{stat:x}"
        await Timer(1, units="step")
        assert int(dut.irq_o.value) == expect_irq, f"{what}: irq_o expected {expect_irq}"
        assert int(dut.wdt_rst_req_o.value) == 1, f"{what}: wdt_rst_req_o must survive W1C clears"

    assert await bfm.write(WDT_IRQ_CLR, 0x0)
    await check(0x7, 1, "W1C of 0 is a no-op")
    assert await bfm.write(WDT_IRQ_CLR, 0xFFFF_FFF8)  # only reserved bits set
    await check(0x7, 1, "W1C of reserved bits is a no-op")
    assert await bfm.write(WDT_IRQ_CLR, ST_VIOL)
    await check(0x3, 1, "clear violation")
    assert await bfm.write(WDT_IRQ_CLR, ST_BARK)
    await check(0x2, 1, "clear bark")
    assert await bfm.write(WDT_IRQ_CLR, ST_BITE)
    await check(0x0, 0, "clear bite")
    dut._log.info("STATUS sticky + per-bit W1C confirmed; irq_o tracks; wdt_rst_req_o survives")


@cocotb.test()
async def test_wdt_set_beats_same_cycle_clear(dut):
    """A WDT_IRQ_CLR write whose ACCESS-phase commit edge coincides EXACTLY with the edge that
    latches a bark (or a bite) must leave the bit SET -- a bark/bite is never lost to a racing
    clear (W1C is an APB write-snoop, and the hardware set wins, as in gpio/pwm).

    Method (same as test_pwm_irq_set_beats_same_cycle_clear, without assuming a latency constant):
    the enable-to-event latency is identical on every run from reset (see the module docstring),
    so (1) CALIBRATE it as k_bark / k_bite edges after E with _measure_bark_bite, (2) rerun the
    identical bus sequence from a fresh reset and land a raw APB write's commit edge on E+k,
    cycle-exact. Edge arithmetic: after the enable write returns we are AT edge E; a raw write's
    SETUP is sampled 1 edge after arming and its ACCESS commits 1 edge after that, so arming SETUP
    at E+(k-2) commits at E+k. CONTROL: the same clear one edge later (E+k+1) must CLEAR the bit,
    which proves the alignment is not accidentally a whole edge early."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 24
    k_bark, k_bite = await _measure_bark_bite(dut, bfm, reload)

    async def run(mask: int, k: int, offset: int) -> int:
        await _pulse_reset(dut)
        await _configure(bfm, reload)
        assert await bfm.write(WDT_CTRL, CTRL_EN)  # now AT edge E
        await ClockCycles(dut.clk, k + offset - 2)
        _raw_write_setup(dut, WDT_IRQ_CLR, mask)
        await RisingEdge(dut.clk)  # SETUP sampled
        _raw_write_access(dut)
        await RisingEdge(dut.clk)  # ACCESS commits on edge E + k + offset
        _raw_write_idle(dut)
        return await _peek(dut, WDT_STATUS)

    for name, mask, k in (("bark", ST_BARK, k_bark), ("bite", ST_BITE, k_bite)):
        stat = await run(mask, k, 0)
        assert stat & mask == mask, (
            f"a WDT_IRQ_CLR write landing on the SAME edge as the {name} set must leave the bit SET "
            f"(set beats clear), got STATUS=0x{stat:x}"
        )
        await Timer(1, units="step")
        assert int(dut.irq_o.value) == 1, f"irq_o must be high with the {name} bit set"

        stat = await run(mask, k, 1)
        assert stat & mask == 0, (
            f"control: a clear committing one edge AFTER the {name} set must clear it, got "
            f"STATUS=0x{stat:x} -- the race alignment above would not have been on the set edge"
        )
    dut._log.info(
        f"set-beats-same-cycle-clear confirmed for bark (k={k_bark}) and bite (k={k_bite})"
    )


@cocotb.test()
async def test_wdt_irq_level_held_across_cycles(dut):
    """irq_o is low before the bark, rises with it, and then stays high on EVERY one of 100
    consecutive settled cycles (which span the bite too) -- level-held, never a single-cycle
    pulse (required so the SoC's plain 2-FF IRQ synchroniser can observe it)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    reload = 20
    await _configure(bfm, reload)
    assert await bfm.write(WDT_CTRL, CTRL_EN)
    for _ in range(5):
        await _next_cycle(dut)
        assert int(dut.irq_o.value) == 0, "irq_o must stay low before the first timeout"

    await _cycles_until_status(dut, ST_BARK, reload + 20)
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 1, "irq_o must be asserted at the bark"

    for cycle in range(100):
        await _next_cycle(dut)
        assert int(dut.irq_o.value) == 1, (
            f"irq_o dropped at cycle {cycle} of the 100-cycle hold window -- must be level-held, not a pulse"
        )
    dut._log.info("irq_o level-held across 100 consecutive cycles -- confirmed")


# -- Register walk: reset/idle values, RO/RW masks, byte lanes, unmapped words ------

@cocotb.test()
async def test_register_walk(dut):
    """Walk every watchdog register against the documented map (reg_maps.WDT); the enable bit is never driven, FEED is skipped."""
    await _start_clock_and_reset(dut)
    m = _make_apb_bfm(dut)
    regs, first = reg_maps.BANKS["wdt"]
    await walk_bank(m, regs, first, log=dut._log)


@cocotb.test()
async def test_register_w1c_semantics(dut):
    """WDT_IRQ_CLR is W1C against WDT_STATUS: let the dog bark then bite (both sticky; bite is
    terminal so nothing re-sets), then clear bark and bite one at a time."""
    await _start_clock_and_reset(dut)
    m = _make_apb_bfm(dut)
    R = reg_maps.WDT
    o = lambda n: reg_maps.off(R, n)  # noqa: E731
    await m.write(o("WDT_RELOAD"), 2)
    await m.write(o("WDT_PRESCALE"), 0)
    await m.write(o("WDT_CTRL"), 0x1)               # enable, RST_EN off
    await ClockCycles(dut.clk, 40)
    st, _ = await m.read(o("WDT_STATUS"))
    assert st & 0x3 == 0x3, f"un-fed dog must have barked and bitten, STATUS=0x{st:x}"
    rep = await check_w1c(m, o("WDT_STATUS"), o("WDT_IRQ_CLR"), [(0, 0), (1, 1)], name="WDT_STATUS")
    rep.assert_clean()


# -- Full-width counter and prescaler -------------------------------------------------

@cocotb.test()
async def test_wdt_counter_full_width_and_wide_prescaler(dut):
    """Every bit of the 32-bit COUNT and of the 16-bit prescaler phase moves in both directions.

    COUNT: RELOAD = 2**k is fed in (a valid feed reloads), one tick later the live count is
    2**k - 1 (bit k falls, every lower bit rises), the next feed with RELOAD = 2**(k+1) makes bit k
    rise again.  Walking k = 8..31 therefore toggles each of COUNT[31:8] both ways without running
    2**31 ticks, and the value read back is checked against the reload each time.
    Prescaler: PRESCALE = 0x8000 makes the phase counter run 0 .. 0x8000 (every bit 4..15 rises)
    and fall back to 0 on the tick; the count has fallen by exactly one after one period.
    """
    await _start_clock_and_reset(dut)
    m = _make_apb_bfm(dut)
    await m.write(WDT_PRESCALE, 0)
    await m.write(WDT_RELOAD, 1 << 8)
    await m.write(WDT_CTRL, CTRL_EN)
    for k in range(8, 32):
        await m.write(WDT_RELOAD, 1 << k)
        await m.write(WDT_FEED, MAGIC)
        count, _ = await m.read(WDT_COUNT)
        assert (1 << k) - 40 <= count <= (1 << k), f"k={k}: COUNT {count:#x} after a feed of {1 << k:#x}"
    st, _ = await m.read(WDT_STATUS)
    assert st == 0, f"STATUS {st:#x}: a counter this large must not have timed out"

    await _pulse_reset(dut)
    await m.write(WDT_PRESCALE, 0x8000)
    await m.write(WDT_RELOAD, 1000)
    await m.write(WDT_CTRL, CTRL_EN)
    period = 0x8000 + 1
    await ClockCycles(dut.clk, period + 200)
    count, _ = await m.read(WDT_COUNT)
    assert count == 999, f"COUNT {count} after one prescaler period of {period} cycles"
