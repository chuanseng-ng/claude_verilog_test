"""test_pwm.py -- Phase 6a-2 cocotb verification for pwm_controller (rtl/periph/pwm_controller.sv,
bead claude_verilog_test-f7vs.6, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-2 -- PWM" + Sec.9).

STRICT TDD: pwm_controller DOES NOT EXIST YET as of this suite's authorship. This is step 2 of
the mandated workflow ("the verification orchestrator runs before the RTL orchestrator" --
Sec.9) -- `make pwm`/`make pwm_lint` are EXPECTED to fail to elaborate until a separate RTL
agent writes rtl/periph/pwm_controller.sv to match the contract documented here.

DUT: tb_pwm (standalone wrapper, directly instantiates pwm_controller, N_CH=4 default, ADDR_W=12)

Register map (pwm_controller.sv, ADDR_W=12 local byte offset, N_REGS=8):
  0x000  PWM_CTRL       [RW]   [3:0] per-channel enable, [7:4] per-channel output polarity
                                (polarity: 0 = active-high, 1 = inverted)
  0x004  PWM_PERIOD     [RW]   [15:0] shared period, in prescaled ticks
  0x008  PWM_PRESCALE   [RW]   [15:0] core_clk divider; one tick = (PRESCALE+1) clocks
  0x00C  PWM_DUTY01     [RW]   [15:0] ch0 duty, [31:16] ch1 duty
  0x010  PWM_DUTY23     [RW]   [15:0] ch2 duty, [31:16] ch3 duty
  0x014  PWM_IRQ_EN     [RW]   [3:0] per-channel period-wrap IRQ enable (masks irq_o ONLY)
  0x018  PWM_IRQ_STAT   [RO]   [3:0] sticky per-channel period-wrap (HW-written)
  0x01C  PWM_IRQ_CLR    [WO]   W1C against PWM_IRQ_STAT; always reads 0
  >=0x020 (word index >= 8)    out-of-range: writes dropped, reads return 0, pslverr=0

N_CH defaults to 4 in tb_pwm, matching the register map's fixed [3:0]/[7:4] nibble split above
(the elaboration-time N_CH guard, 1 <= N_CH <= 8, is a `generate`-scope $fatal per
docs/PHASE6_IP_EXPANSION_PLAN.md Sec.10 item 1 / gpio_controller.sv precedent -- not exercised
here, matching test_gpio.py's own precedent of not driving an elaboration-time $fatal via cocotb).

Timing contract, one shared period counter for ALL channels (docs/PHASE6_IP_EXPANSION_PLAN.md
Sec.7: "Shared period, per-channel duty"), left/edge-aligned only (no centre-alignment, no
dead-time -- both explicit non-goals):
  - A tick occurs every (PRESCALE+1) core_clk cycles.
  - The shared tick counter counts 0 .. PERIOD-1 and wraps back to 0 (period-wrap event).
  - Channel ch's "active condition" is (tick_count < DUTY[ch]) while ch is enabled
    (PWM_CTRL[ch] == 1); pwm_o[ch] = active_condition XOR PWM_CTRL[4+ch] (polarity), i.e.
    polarity=0 (active-high) drives pwm_o[ch]=1 during the active condition and 0 otherwise;
    polarity=1 (inverted) drives pwm_o[ch]=0 during the active condition and 1 otherwise.
  - A DISABLED channel (PWM_CTRL[ch] == 0) drives its inactive level continuously and its
    PWM_IRQ_STAT bit never accumulates a period-wrap event, regardless of its DUTY value (see
    test_pwm_disabled_channel_no_output_no_irq) -- this is a real datapath gate, not merely an
    irq_o mask (contrast with PWM_IRQ_EN, which masks irq_o only and does not affect
    accumulation -- see test_pwm_irq_en_masks_output_only).

This suite SPECIFIES (not empirically measures, since no RTL exists yet) three corner cases the
golden spec calls out by name and leaves to the implementer without a chosen answer -- documented
here so the RTL agent implements what this suite asserts, not the reverse:
  DUTY == 0            : a TRUE 0% duty cycle -- pwm_o[ch] must NEVER read the active level, not
                          even for a single clock cycle (the classic one-cycle PWM glitch bug).
                          See test_pwm_duty_zero_is_true_zero_percent.
  DUTY >= PERIOD        : a TRUE 100% duty cycle -- pwm_o[ch] must be continuously active across
                          every sampled cycle, INCLUDING the exact tick-wrap-to-0 instant (no
                          one-tick low glitch at wraparound). See
                          test_pwm_duty_ge_period_is_true_100_percent.
  PERIOD == 0           : no valid period exists. This suite specifies that the active condition
                          must be forced FALSE unconditionally (pwm_o[ch] holds at its inactive
                          level) and that no period-wrap IRQ event may ever fire -- the design
                          decision that avoids both an output glitch and a spurious/runaway
                          interrupt storm from an ill-defined free-running compare. See
                          test_pwm_period_zero_defined_behavior.

Periodicity-based synchronisation (used by several tests below instead of any assumed
wrap-to-STAT-visible latency constant, since no RTL exists yet to measure one empirically the way
test_gpio.py's test_gpio_data_in_sync_latency did): with PRESCALE=0, one tick equals exactly one
core_clk cycle, so consecutive period-wrap-visible events recur exactly PERIOD clock cycles apart
-- this holds regardless of whatever fixed internal pipeline latency separates the true wrap
instant from its visibility in PWM_IRQ_STAT, because that constant is identical every period and
cancels out of the *difference* between two consecutive visible events. `_wait_for_irq_stat()`
locates one such event by direct polling (never assumed/hardcoded), and tests that need a
phase-aligned sampling window (test_pwm_per_channel_independence, test_pwm_polarity_inversion)
rely on a further invariant: any period-clock-cycle-long contiguous sampling window taken from a
steady-state periodic 0/1 signal with a fixed on-time per period contains exactly that same
on-time count of active samples, regardless of the window's phase offset within the period (it is
a cyclic rotation of one period's worth of samples). This lets those two tests assert an exact
active-cycle COUNT without needing to know or assume the wrap's exact internal latency.
test_pwm_irq_set_beats_same_cycle_clear additionally uses the periodicity invariant to predict a
SPECIFIC future edge (the next period-wrap's visible edge, exactly PERIOD cycles after an
observed one) and lands a raw APB write's ACCESS/commit edge on it cycle-exact, mirroring
gpio_controller's proven test_gpio_edge_set_beats_same_cycle_clear methodology.

irq_o = |(PWM_IRQ_STAT & PWM_IRQ_EN), purely combinational and level-held (never a pulse) -- same
contract and same underlying reason as gpio_controller.sv (every IRQ source feeding
interrupt_controller crosses core_clk -> cpu_core_clk through a plain 2-FF cdc_2ff_sync at
rtl/soc/soc_top.sv:637-644, which can only safely observe a level held for multiple destination-
clock cycles).

Tests:
  test_pwm_reset_defaults
      All RW regs 0 (CTRL/PERIOD/PRESCALE/DUTY01/DUTY23/IRQ_EN), IRQ_STAT == 0 (PERIOD==0 and
      every channel disabled at reset -- no wrap can occur), IRQ_CLR reads 0, pwm_o == 0 (all
      channels disabled -> inactive level at default polarity), irq_o == 0.
  test_pwm_rw_roundtrip_all_registers
      Write/read-back round trip on CTRL, PERIOD, PRESCALE, DUTY01, DUTY23, IRQ_EN.
  test_pwm_irq_clr_reads_as_zero
      PWM_IRQ_CLR always reads back 0, regardless of what was last written to it.
  test_pwm_out_of_range_access
      Word index >= 8 (byte offset >= 0x020): write silently dropped, read returns 0, pslverr=0.
  test_pwm_duty01_pstrb_partial_word
      A strobed PWM_DUTY01 write (byte0+1 only) updates ch0's duty and leaves ch1's duty (upper
      16 bits, non-strobed bytes) untouched.
  test_pwm_duty_zero_is_true_zero_percent
      DUTY==0: pwm_o never shows the active level, sampled every cycle across 3 full periods.
  test_pwm_duty_ge_period_is_true_100_percent
      DUTY==PERIOD and DUTY>PERIOD: pwm_o is continuously active every sampled cycle, including
      across the tick-wrap boundary (no dropout glitch).
  test_pwm_period_zero_defined_behavior
      PERIOD==0: pwm_o holds inactive and PWM_IRQ_STAT never sets, for an enabled+IRQ_EN channel
      with a nonzero DUTY that would normally be active.
  test_pwm_prescaler_change_mid_period
      Changing PWM_PRESCALE partway through an in-progress period does not lock up or run away --
      a period-wrap IRQ is still observed within a generous bounded cycle budget afterwards.
  test_pwm_polarity_inversion
      PWM_CTRL[7:4]: an inverted-polarity channel's active-cycle count over one phase-aligned
      period window equals (PERIOD - DUTY), the exact complement of the non-inverted case.
  test_pwm_per_channel_independence
      4 distinct duties across all 4 channels simultaneously: each channel's active-cycle count
      over one phase-aligned period window equals exactly its own configured DUTY.
  test_pwm_disabled_channel_no_output_no_irq
      A disabled channel (PWM_CTRL[ch]==0) holds its inactive level and never accumulates
      PWM_IRQ_STAT, across 3 confirmed period wraps on a separate enabled reference channel --
      even with its own DUTY configured to a value that would normally be active and its own
      PWM_IRQ_EN bit set.
  test_pwm_irq_period_wrap_sticky_and_clear
      PWM_IRQ_STAT stays set (sticky) across further period wraps with no CLR write, then clears
      on a PWM_IRQ_CLR write.
  test_pwm_irq_set_beats_same_cycle_clear
      A PWM_IRQ_CLR write whose ACCESS-phase commit edge coincides EXACTLY with a fresh
      period-wrap event leaves the bit SET, not cleared.
  test_pwm_irq_en_masks_output_only
      PWM_IRQ_EN gates irq_o only; PWM_IRQ_STAT accumulation is unaffected by it.
  test_pwm_irq_level_held_across_cycles
      irq_o stays asserted across many consecutive cycles once its condition is enabled (no pulse).
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
CLK_PERIOD_NS = 10  # 100 MHz -- matches SoC reference clock (same convention as test_gpio.py)

PWM_CTRL = 0x000
PWM_PERIOD = 0x004
PWM_PRESCALE = 0x008
PWM_DUTY01 = 0x00C
PWM_DUTY23 = 0x010
PWM_IRQ_EN = 0x014
PWM_IRQ_STAT = 0x018
PWM_IRQ_CLR = 0x01C
PWM_OUT_OF_RANGE = 0x020  # word index 8 -- first address past the 8-register map

N_CH = 4
ALL_CH_MASK = 0xF  # (1 << N_CH) - 1

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


async def _start_clock_and_reset(dut) -> None:
    """Start 100 MHz clock and apply synchronous reset with the APB4 bus idled. PWM has no
    additional top-level inputs beyond clk/rst_n/APB4 (no async pins, unlike tb_gpio's
    gpio_in_i)."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n.value = 0
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = 0
    dut.pwdata.value = 0
    dut.pstrb.value = 0xF

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
    test_gpio.py's _peek() -- see that file's docstring for the underlying Verilator/cocotb
    settle-timing bug this `Timer(1, units="step")` works around (a bare synchronous read can
    return stale prdata left over from a previous address)."""
    dut.pwrite.value = 0
    dut.paddr.value = addr
    await Timer(1, units="step")
    return int(dut.prdata.value)


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


def _duty_addr_and_shift(ch: int) -> tuple[int, int]:
    """Return (register byte address, bit shift) for channel `ch`'s 16-bit duty field: channels
    0/1 live in PWM_DUTY01 low/high half-words, channels 2/3 live in PWM_DUTY23."""
    addr = PWM_DUTY01 if ch < 2 else PWM_DUTY23
    shift = 16 if (ch % 2) else 0
    return addr, shift


async def _wait_for_irq_stat(dut, mask: int, max_cycles: int = 4096) -> None:
    """Advance the clock one edge at a time, peeking PWM_IRQ_STAT after each edge, until any bit
    in `mask` reads set. Raises AssertionError (never silently hangs or times out via the cocotb
    harness's own generic mechanism) if the budget is exhausted -- an absent period-wrap event is
    itself a bug this suite must catch. Callers own PWM_IRQ_EN / PWM_IRQ_CLR configuration; this
    helper only observes PWM_IRQ_STAT."""
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        stat = await _peek(dut, PWM_IRQ_STAT)
        if stat & mask:
            return
    raise AssertionError(f"PWM_IRQ_STAT bit(s) 0x{mask:x} not observed within {max_cycles} cycles")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_pwm_reset_defaults(dut):
    """After reset: CTRL/PERIOD/PRESCALE/DUTY01/DUTY23/IRQ_EN == 0, IRQ_CLR reads 0, IRQ_STAT ==
    0 (PERIOD==0 and every channel disabled at reset means no period-wrap event can ever have
    occurred), pwm_o == 0 (all channels disabled -> inactive level at default polarity=0), and
    irq_o == 0."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ctrl, ok1 = await bfm.read(PWM_CTRL)
    period, ok2 = await bfm.read(PWM_PERIOD)
    prescale, ok3 = await bfm.read(PWM_PRESCALE)
    duty01, ok4 = await bfm.read(PWM_DUTY01)
    duty23, ok5 = await bfm.read(PWM_DUTY23)
    irq_en, ok6 = await bfm.read(PWM_IRQ_EN)
    irq_stat, ok7 = await bfm.read(PWM_IRQ_STAT)
    irq_clr, ok8 = await bfm.read(PWM_IRQ_CLR)

    assert all([ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8]), "reset-default reads returned SLVERR"
    assert ctrl == 0, f"PWM_CTRL expected 0 at reset, got 0x{ctrl:08x}"
    assert period == 0, f"PWM_PERIOD expected 0 at reset, got 0x{period:08x}"
    assert prescale == 0, f"PWM_PRESCALE expected 0 at reset, got 0x{prescale:08x}"
    assert duty01 == 0, f"PWM_DUTY01 expected 0 at reset, got 0x{duty01:08x}"
    assert duty23 == 0, f"PWM_DUTY23 expected 0 at reset, got 0x{duty23:08x}"
    assert irq_en == 0, f"PWM_IRQ_EN expected 0 at reset, got 0x{irq_en:08x}"
    assert irq_stat == 0, f"PWM_IRQ_STAT expected 0 at reset (no channel enabled), got 0x{irq_stat:08x}"
    assert irq_clr == 0, f"PWM_IRQ_CLR expected to read 0 at reset, got 0x{irq_clr:08x}"
    assert int(dut.pwm_o.value) == 0, f"pwm_o expected 0 at reset, got 0x{int(dut.pwm_o.value):x}"
    assert int(dut.irq_o.value) == 0, f"irq_o expected 0 at reset, got {int(dut.irq_o.value)}"
    dut._log.info("PWM reset defaults confirmed")


@cocotb.test()
async def test_pwm_rw_roundtrip_all_registers(dut):
    """Write/read-back round trip on every RW register: CTRL, PERIOD, PRESCALE, DUTY01, DUTY23,
    IRQ_EN. Each pattern below is sized to that register's own WMASK so the readback is expected
    byte-identical."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    rw_regs = {
        "PWM_CTRL": (PWM_CTRL, 0x0000_00A5),  # [7:0] meaningful: enable+polarity mix
        "PWM_PERIOD": (PWM_PERIOD, 0x0000_BEEF),
        "PWM_PRESCALE": (PWM_PRESCALE, 0x0000_CAFE),
        "PWM_DUTY01": (PWM_DUTY01, 0x1234_5678),
        "PWM_DUTY23": (PWM_DUTY23, 0x89AB_CDEF),
        "PWM_IRQ_EN": (PWM_IRQ_EN, 0x0000_000F),
    }

    for name, (addr, pattern) in rw_regs.items():
        ok_w = await bfm.write(addr, pattern)
        assert ok_w, f"{name} write returned SLVERR"
        data, ok_r = await bfm.read(addr)
        assert ok_r, f"{name} readback returned SLVERR"
        assert data == pattern, f"{name} readback: got 0x{data:08x}, expected 0x{pattern:08x}"
        # Restore to 0 so later registers in this loop aren't affected by an earlier write.
        ok_clear = await bfm.write(addr, 0x0000_0000)
        assert ok_clear, f"{name} clear-back-to-0 write returned SLVERR"
    dut._log.info("RW round trip confirmed on CTRL/PERIOD/PRESCALE/DUTY01/DUTY23/IRQ_EN")


@cocotb.test()
async def test_pwm_irq_clr_reads_as_zero(dut):
    """PWM_IRQ_CLR always reads back 0, regardless of what pattern was last written to it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for pattern in (0xFFFF_FFFF, 0x1234_5678, 0x0000_0001):
        ok_w = await bfm.write(PWM_IRQ_CLR, pattern)
        assert ok_w, f"PWM_IRQ_CLR write(0x{pattern:08x}) returned SLVERR"
        data, ok_r = await bfm.read(PWM_IRQ_CLR)
        assert ok_r, "PWM_IRQ_CLR read returned SLVERR"
        assert data == 0, f"PWM_IRQ_CLR must always read 0, got 0x{data:08x} after writing 0x{pattern:08x}"
    dut._log.info("PWM_IRQ_CLR reads-as-zero confirmed across multiple written patterns")


@cocotb.test()
async def test_pwm_out_of_range_access(dut):
    """Word index >= 8 (byte offset >= 0x020, within the 12-bit ADDR_W slot) is out of range:
    writes are silently dropped and reads return 0, both with pslverr==0 (OKAY) per the register
    bank's out-of-range policy."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for addr in (PWM_OUT_OF_RANGE, 0x0FC):
        ok_w = await bfm.write(addr, 0xFFFF_FFFF)
        assert ok_w, f"out-of-range write to 0x{addr:03x} must return OKAY (pslverr=0), got SLVERR"
        data, ok_r = await bfm.read(addr)
        assert ok_r, f"out-of-range read from 0x{addr:03x} must return OKAY (pslverr=0), got SLVERR"
        assert data == 0, f"out-of-range read from 0x{addr:03x} must return 0, got 0x{data:08x}"
    dut._log.info("out-of-range access policy (drop write, read 0, pslverr=0) confirmed")


@cocotb.test()
async def test_pwm_duty01_pstrb_partial_word(dut):
    """A partial-word PWM_DUTY01 write (pstrb selecting only bytes 0-1, ch0's half-word) must
    update only ch0's duty -- ch1's duty (upper 16 bits, non-strobed bytes) must survive
    unchanged."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok1 = await bfm.write(PWM_DUTY01, 0xBBBB_AAAA)  # ch0=0xAAAA, ch1=0xBBBB
    assert ok1, "initial full-word PWM_DUTY01 write returned SLVERR"
    duty01_before, ok_r0 = await bfm.read(PWM_DUTY01)
    assert ok_r0
    assert duty01_before == 0xBBBB_AAAA, f"precondition failed: got 0x{duty01_before:08x}"

    # strb=0x3 selects bytes 0-1 only (ch0's half-word) -- ch1's half-word must be preserved.
    ok2 = await bfm.write(PWM_DUTY01, 0x0000_1111, strb=0x3)
    assert ok2, "partial-word PWM_DUTY01 write returned SLVERR"

    duty01_after, ok_r1 = await bfm.read(PWM_DUTY01)
    assert ok_r1
    assert duty01_after & 0xFFFF == 0x1111, (
        f"ch0 (strobed half-word) must be updated by the partial-word write, got 0x{duty01_after:08x}"
    )
    assert (duty01_after >> 16) & 0xFFFF == 0xBBBB, (
        f"ch1 (non-strobed half-word) must remain unchanged by the partial-word write, "
        f"got 0x{duty01_after:08x}"
    )
    dut._log.info(f"PWM_DUTY01 pstrb partial-word write confirmed: 0x{duty01_after:08x}")


@cocotb.test()
async def test_pwm_duty_zero_is_true_zero_percent(dut):
    """DUTY==0 for an enabled channel must produce a TRUE 0% duty cycle: pwm_o for that channel
    must never read the active level, not even for a single clock cycle -- not at the tick==0
    instant and not across a full multi-period sampling window (the classic one-cycle PWM glitch
    bug). Sampled every clock cycle across 3 full periods plus margin."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 0
    mask = 1 << ch
    period = 8
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, 0 << shift)
    assert ok3
    ok4 = await bfm.write(PWM_CTRL, mask)  # enable ch0, default polarity (active-high)
    assert ok4

    for cycle in range(3 * period + 8):
        await RisingEdge(dut.clk)
        pwm_val = int(dut.pwm_o.value)
        assert (pwm_val & mask) == 0, (
            f"duty==0 must be a true 0% duty cycle: pwm_o[{ch}] went active at cycle {cycle}, "
            f"got pwm_o=0x{pwm_val:x}"
        )
    dut._log.info("duty==0 true 0% (no glitch) confirmed over 3 full periods")


@cocotb.test()
async def test_pwm_duty_ge_period_is_true_100_percent(dut):
    """DUTY >= PERIOD for an enabled channel must produce a TRUE 100% duty cycle: pwm_o for that
    channel must be continuously active across every sampled clock cycle, INCLUDING the exact
    tick-count wrap-to-0 boundary -- no one-tick low glitch at wraparound. Tested with DUTY ==
    PERIOD and again with DUTY > PERIOD."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 1
    mask = 1 << ch
    period = 8
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(PWM_CTRL, mask)
    assert ok3

    for duty in (period, period + 5):  # duty == period, then duty > period
        ok4 = await bfm.write(duty_addr, duty << shift)
        assert ok4
        for cycle in range(3 * period + 8):
            await RisingEdge(dut.clk)
            pwm_val = int(dut.pwm_o.value)
            assert (pwm_val & mask) == mask, (
                f"duty ({duty}) >= period ({period}) must be a true 100% duty cycle -- "
                f"pwm_o[{ch}] went inactive at cycle {cycle} (possible wrap-boundary glitch), "
                f"got pwm_o=0x{pwm_val:x}"
            )
    dut._log.info("duty>=period true 100% (no wrap-boundary glitch) confirmed")


@cocotb.test()
async def test_pwm_period_zero_defined_behavior(dut):
    """PERIOD==0 is an explicit, defined corner case (see this file's module docstring for the
    full rationale): this suite specifies that the channel's active condition must be forced
    FALSE, so pwm_o holds its inactive level continuously, and no period-wrap IRQ event may ever
    fire -- both together ruling out the alternative reading (a free-running counter with an
    undefined compare) that could otherwise produce an output glitch or a spurious/runaway
    interrupt storm. This is a specification decision made by this suite, not an empirical RTL
    measurement: the RTL implementation must match it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 2
    mask = 1 << ch
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, 0)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, 5 << shift)  # a duty that would normally be active
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok4
    ok5 = await bfm.write(PWM_CTRL, mask)
    assert ok5

    for cycle in range(64):
        await RisingEdge(dut.clk)
        pwm_val = int(dut.pwm_o.value)
        assert (pwm_val & mask) == 0, (
            f"PERIOD==0 must hold pwm_o[{ch}] inactive, got pwm_o=0x{pwm_val:x} at cycle {cycle}"
        )

    stat = await _peek(dut, PWM_IRQ_STAT)
    assert stat & mask == 0, f"PERIOD==0 must never generate a period-wrap IRQ event, got IRQ_STAT=0x{stat:08x}"
    dut._log.info("PERIOD==0 defined behaviour (held inactive, no spurious IRQ) confirmed")


@cocotb.test()
async def test_pwm_prescaler_change_mid_period(dut):
    """Changing PWM_PRESCALE partway through an in-progress period must be well-behaved: no
    lock-up, no runaway counter. Verified behaviourally (black-box, no dependence on any internal
    tick_count signal): a channel is configured for a repeating period-wrap IRQ, the prescaler is
    changed midway through the first period, and this test asserts the IRQ eventually fires again
    within a generous bounded cycle budget -- proving forward progress resumed rather than the
    counter freezing or reaching a pathological state that never again satisfies its compare."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 3
    mask = 1 << ch
    period = 8
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 1)  # tick = 2 clocks
    assert ok2
    ok3 = await bfm.write(duty_addr, 4 << shift)
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok4
    ok5 = await bfm.write(PWM_CTRL, mask)
    assert ok5

    # Run partway into the first period (roughly half of it, at the ORIGINAL prescale), then
    # change the prescaler mid-flight.
    await ClockCycles(dut.clk, period)
    ok6 = await bfm.write(PWM_PRESCALE, 3)  # tick = 4 clocks -- changed mid-period
    assert ok6

    # Bounded budget: comfortably more than one full period even at the slower post-change tick
    # rate (period ticks * 4 clocks/tick worst case * safety margin).
    await _wait_for_irq_stat(dut, mask, max_cycles=period * 4 * 4)
    dut._log.info("period-wrap IRQ observed after a mid-period prescale change -- no lock-up")


@cocotb.test()
async def test_pwm_polarity_inversion(dut):
    """PWM_CTRL[7:4] polarity, per channel: 0 = active-high, 1 = inverted (pwm_o[ch] == 0 during
    the duty "on" window, == 1 otherwise -- the exact complement of polarity=0). Verified via the
    periodicity invariant described in this file's module docstring: a phase-aligned window of
    exactly PERIOD clock cycles (PRESCALE=0, so 1 tick = 1 clock) must contain exactly
    (PERIOD - DUTY) active-level samples for an inverted-polarity channel, regardless of where
    within the period the window starts."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 0
    mask = 1 << ch
    pol_bit = 1 << (4 + ch)
    period = 16
    duty = 6
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, duty << shift)
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok4
    ok5 = await bfm.write(PWM_IRQ_CLR, mask)
    assert ok5
    ok6 = await bfm.write(PWM_CTRL, mask | pol_bit)  # enabled, inverted polarity
    assert ok6

    await _wait_for_irq_stat(dut, mask)  # phase-align: steady-state periodic behaviour confirmed
    # Settle before sampling. _wait_for_irq_stat ends in _peek()'s Timer(1, "step"),
    # and pwm_o is COMBINATIONAL off tick_count_q, so a bare int(dut.pwm_o.value)
    # read here returns the pre-edge value -- the first two samples come back
    # identical and the window loses one real sample at the far end. One real clock
    # edge puts sampling on a settled, known boundary. Same class as the settle
    # _peek() itself documents; the expected counts below are UNCHANGED.
    await RisingEdge(dut.clk)

    on_count = 0
    for _ in range(period):
        pwm_val = int(dut.pwm_o.value)
        if pwm_val & mask:
            on_count += 1
        await RisingEdge(dut.clk)

    expected_on = period - duty
    assert on_count == expected_on, (
        f"inverted-polarity channel {ch}: expected exactly {expected_on} active cycles "
        f"(period-duty = {period}-{duty}) out of one full {period}-cycle window, got {on_count}"
    )
    dut._log.info(f"polarity inversion confirmed: on_count={on_count} expected={expected_on}")


@cocotb.test()
async def test_pwm_per_channel_independence(dut):
    """4 distinct duties across all 4 channels simultaneously (shared period, per-channel duty):
    each channel's active-cycle count over one phase-aligned PERIOD-cycle window (see this file's
    module docstring for the periodicity invariant) must equal exactly its own configured DUTY,
    with all other channels' differing duties having no effect on it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    period = 16
    duties = {0: 2, 1: 6, 2: 10, 3: 15}  # distinct duty per channel, all < period

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(PWM_DUTY01, duties[0] | (duties[1] << 16))
    assert ok3
    ok4 = await bfm.write(PWM_DUTY23, duties[2] | (duties[3] << 16))
    assert ok4
    ok5 = await bfm.write(PWM_IRQ_EN, ALL_CH_MASK)
    assert ok5
    ok6 = await bfm.write(PWM_IRQ_CLR, ALL_CH_MASK)
    assert ok6
    ok7 = await bfm.write(PWM_CTRL, ALL_CH_MASK)  # all 4 enabled, default polarity active-high
    assert ok7

    await _wait_for_irq_stat(dut, ALL_CH_MASK)  # any enabled channel wraps together (shared period)
    # Settle before sampling -- see the note in test_pwm_polarity_inversion.
    # pwm_o is combinational off tick_count_q, so a bare read straight after
    # _wait_for_irq_stat returns the pre-edge value. Expected counts UNCHANGED.
    await RisingEdge(dut.clk)

    on_counts = {ch: 0 for ch in duties}
    for _ in range(period):
        pwm_val = int(dut.pwm_o.value)
        for ch in duties:
            if pwm_val & (1 << ch):
                on_counts[ch] += 1
        await RisingEdge(dut.clk)

    for ch, duty in duties.items():
        assert on_counts[ch] == duty, (
            f"channel {ch}: expected exactly {duty} active cycles out of one full {period}-cycle "
            f"period, got {on_counts[ch]} -- per-channel duty independence violated"
        )
    dut._log.info(f"per-channel independence confirmed: on_counts={on_counts} duties={duties}")


@cocotb.test()
async def test_pwm_disabled_channel_no_output_no_irq(dut):
    """PWM_CTRL[3:0] enable: a DISABLED channel must drive its inactive level continuously and
    must NOT accumulate PWM_IRQ_STAT, even though the shared period counter keeps wrapping (proven
    live via a separate enabled reference channel) and even though its own DUTY and PWM_IRQ_EN
    are both configured as if it were live -- proving this is a real datapath/status gate, not
    merely an irq_o mask (contrast test_pwm_irq_en_masks_output_only, where PWM_IRQ_EN gates
    irq_o only and IRQ_STAT keeps accumulating regardless)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    live_ch = 0   # kept enabled -- reference channel proving the shared counter is running
    dead_ch = 1   # left disabled -- the channel under test
    live_mask = 1 << live_ch
    dead_mask = 1 << dead_ch
    period = 8

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(PWM_DUTY01, 4 | (4 << 16))  # both channels: duty=4 (would be active half the period)
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, live_mask | dead_mask)
    assert ok4
    ok5 = await bfm.write(PWM_CTRL, live_mask)  # only live_ch enabled; dead_ch stays disabled
    assert ok5

    for wrap in range(3):
        await _wait_for_irq_stat(dut, live_mask)

        stat = await _peek(dut, PWM_IRQ_STAT)
        assert stat & live_mask == live_mask, (
            f"precondition failed at wrap {wrap}: reference channel {live_ch}'s wrap bit must be "
            f"set, got IRQ_STAT=0x{stat:08x}"
        )
        assert stat & dead_mask == 0, (
            f"disabled channel {dead_ch} must never accumulate IRQ_STAT despite a period wrap "
            f"(wrap {wrap}), got IRQ_STAT=0x{stat:08x}"
        )
        pwm_val = int(dut.pwm_o.value)
        assert pwm_val & dead_mask == 0, (
            f"disabled channel {dead_ch} must hold its inactive level (wrap {wrap}), "
            f"got pwm_o=0x{pwm_val:x}"
        )

        ok_clr = await bfm.write(PWM_IRQ_CLR, live_mask | dead_mask)
        assert ok_clr, "PWM_IRQ_CLR write returned SLVERR"
    dut._log.info("disabled-channel no-output/no-IRQ-accumulation confirmed across 3 period wraps")


@cocotb.test()
async def test_pwm_irq_period_wrap_sticky_and_clear(dut):
    """PWM_IRQ_STAT is sticky per channel: once a period-wrap event sets a channel's bit, it stays
    set across many subsequent clock cycles -- including across further period wraps while
    unacknowledged -- until a PWM_IRQ_CLR write targeting it lands with no coincident fresh wrap
    (see test_pwm_irq_set_beats_same_cycle_clear for that race)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 1
    mask = 1 << ch
    period = 8
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, 3 << shift)
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok4
    ok5 = await bfm.write(PWM_CTRL, mask)
    assert ok5

    await _wait_for_irq_stat(dut, mask)
    stat_set = await _peek(dut, PWM_IRQ_STAT)
    assert stat_set & mask == mask, f"IRQ_STAT bit must be set after the period wrap, got 0x{stat_set:08x}"

    # Sticky across MULTIPLE further period wraps with no CLR write -- comfortably more than 2
    # full periods of continued activity.
    await ClockCycles(dut.clk, 2 * period + 3)
    stat_still_set = await _peek(dut, PWM_IRQ_STAT)
    assert stat_still_set & mask == mask, (
        f"IRQ_STAT bit must remain sticky-set across further period wraps with no CLR write, "
        f"got 0x{stat_still_set:08x}"
    )

    ok6 = await bfm.write(PWM_IRQ_CLR, mask)
    assert ok6, "PWM_IRQ_CLR write returned SLVERR"
    stat_cleared = await _peek(dut, PWM_IRQ_STAT)
    assert stat_cleared & mask == 0, f"IRQ_STAT bit must clear after the CLR write, got 0x{stat_cleared:08x}"
    dut._log.info("PWM period-wrap sticky + clear-by-CLR confirmed")


@cocotb.test()
async def test_pwm_irq_set_beats_same_cycle_clear(dut):
    """A PWM_IRQ_CLR write whose ACCESS-phase commit edge coincides EXACTLY with the edge that
    latches a fresh period-wrap event into PWM_IRQ_STAT must leave the bit SET, not cleared --
    mirroring gpio_controller's proven set-beats-clear formula (see gpio_controller.sv header and
    test_gpio_edge_set_beats_same_cycle_clear). PRESCALE=0 makes one tick equal exactly one clock
    cycle, so once a first wrap's visible edge is located via _wait_for_irq_stat, periodicity
    alone (no dependence on any particular internal wrap-to-STAT latency constant, only that it is
    the SAME constant every period -- see this file's module docstring) predicts the NEXT wrap's
    visible edge lands exactly PERIOD clock cycles later. A raw APB write (not APB4Master, so its
    own SETUP/ACCESS edges can be placed cycle-exact) is timed so its ACCESS (commit) edge lands
    on that predicted edge.

    Edge arithmetic, relative to W1 = the edge _wait_for_irq_stat(...) returns after (wrap #1's
    visible edge):
      - The ordinary CLR write issued right after W1 consumes exactly 2 edges (APB4Master's
        SETUP-phase RisingEdge, then its ACCESS/commit RisingEdge -- pready is hardwired 1, zero
        wait states), landing at W1+2.
      - Wrap #2's predicted visible edge is W1+PERIOD.
      - A raw write's SETUP phase, once armed, is sampled 1 edge later; its ACCESS phase, once
        armed, commits 1 edge after THAT (same two-edges-per-write shape as APB4Master, just
        driven by hand so the two arming points can be placed exactly).
      - So: from W1+2, advance (PERIOD-4) more edges to W1+(PERIOD-2), arm SETUP (sampled at
        W1+(PERIOD-1)), then arm ACCESS (commits at W1+PERIOD) -- landing exactly on wrap #2."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 2
    mask = 1 << ch
    period = 12  # comfortable margin for the (period - 4) advance below to stay positive
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, 4 << shift)
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok4
    ok5 = await bfm.write(PWM_CTRL, mask)
    assert ok5

    await _wait_for_irq_stat(dut, mask)  # locate wrap #1's visible edge (== W1)

    ok_clr = await bfm.write(PWM_IRQ_CLR, mask)  # consumes exactly 2 edges: now at W1+2
    assert ok_clr
    stat_cleared = await _peek(dut, PWM_IRQ_STAT)
    assert stat_cleared & mask == 0, (
        f"precondition failed: IRQ_STAT must read clear immediately after CLR, got 0x{stat_cleared:08x}"
    )

    await ClockCycles(dut.clk, period - 4)  # now at W1+(period-2)
    _raw_write_setup(dut, PWM_IRQ_CLR, mask)
    await RisingEdge(dut.clk)  # SETUP edge, now at W1+(period-1)
    _raw_write_access(dut)
    await RisingEdge(dut.clk)  # ACCESS/commit edge, now at W1+period == wrap #2's predicted edge
    _raw_write_idle(dut)

    stat_race = await _peek(dut, PWM_IRQ_STAT)
    assert stat_race & mask == mask, (
        f"a PWM_IRQ_CLR write landing on the SAME edge as a fresh period-wrap event must leave "
        f"the bit SET (set beats clear), got 0x{stat_race:08x}"
    )
    dut._log.info(f"PWM set-beats-same-cycle-clear confirmed: stat=0x{stat_race:08x}")


@cocotb.test()
async def test_pwm_irq_en_masks_output_only(dut):
    """PWM_IRQ_EN gates irq_o only -- PWM_IRQ_STAT accumulates a period-wrap event regardless of
    it. Enabling the channel's IRQ_EN bit afterwards asserts irq_o immediately (purely
    combinational off regs_o, no extra latency), mirroring gpio_controller's identical contract
    (test_gpio_irq_en_masks_output_only)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 3
    mask = 1 << ch
    period = 8
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, 3 << shift)
    assert ok3
    ok4 = await bfm.write(PWM_CTRL, mask)  # channel enabled; IRQ_EN left at reset default 0
    assert ok4

    await _wait_for_irq_stat(dut, mask)  # STAT must accumulate even with IRQ_EN==0
    stat = await _peek(dut, PWM_IRQ_STAT)
    assert stat & mask == mask, f"IRQ_STAT must capture the wrap even with IRQ_EN==0, got 0x{stat:08x}"
    # As with _peek(), cocotb's VPI write/read alone does not make Verilator re-evaluate
    # combinational logic -- a simulator time step must elapse first.
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0, (
        f"irq_o must stay 0 while IRQ_EN==0 for this channel, got {int(dut.irq_o.value)}"
    )

    ok5 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok5, "PWM_IRQ_EN write returned SLVERR"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 1, (
        f"irq_o must assert immediately once IRQ_EN is set for a pending channel, got {int(dut.irq_o.value)}"
    )
    dut._log.info("PWM_IRQ_EN masks irq_o only, independent of IRQ_STAT accumulation -- confirmed")


@cocotb.test()
async def test_pwm_irq_level_held_across_cycles(dut):
    """irq_o stays asserted across many consecutive clock cycles once its condition holds --
    level-held, never a single-cycle pulse (required so the SoC's plain 2-FF IRQ synchroniser at
    rtl/soc/soc_top.sv:637-644 can observe it), mirroring test_gpio_irq_level_held_across_cycles."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ch = 0
    mask = 1 << ch
    period = 8
    duty_addr, shift = _duty_addr_and_shift(ch)

    ok1 = await bfm.write(PWM_PERIOD, period)
    assert ok1
    ok2 = await bfm.write(PWM_PRESCALE, 0)
    assert ok2
    ok3 = await bfm.write(duty_addr, 3 << shift)
    assert ok3
    ok4 = await bfm.write(PWM_IRQ_EN, mask)
    assert ok4
    ok5 = await bfm.write(PWM_CTRL, mask)
    assert ok5

    await _wait_for_irq_stat(dut, mask)
    assert int(dut.irq_o.value) == 1, f"irq_o must be asserted before the hold-check window, got {int(dut.irq_o.value)}"

    for cycle in range(50):
        await RisingEdge(dut.clk)
        assert int(dut.irq_o.value) == 1, (
            f"irq_o dropped at cycle {cycle} of the 50-cycle hold window -- must be level-held, not a pulse"
        )
    dut._log.info("irq_o level-held across 50 consecutive cycles -- confirmed")


# -- Register walk (bead 7ovx): reset/idle values, RO/RW masks, byte lanes, unmapped words ------

@cocotb.test()
async def test_register_walk(dut):
    """Walk every PWM register against the documented map (reg_maps.PWM)."""
    await _start_clock_and_reset(dut)
    m = _make_apb_bfm(dut)
    regs, first = reg_maps.BANKS["pwm"]
    await walk_bank(m, regs, first, log=dut._log)


@cocotb.test()
async def test_register_w1c_semantics(dut):
    """PWM_IRQ_CLR is W1C against the sticky period-wrap bits: four channels wrap, then each bit
    is cleared alone (a 0, a low strobe or a non-pending bit clears nothing)."""
    await _start_clock_and_reset(dut)
    m = _make_apb_bfm(dut)
    R = reg_maps.PWM
    o = lambda n: reg_maps.off(R, n)  # noqa: E731
    await m.write(o("PWM_PERIOD"), 3)
    await m.write(o("PWM_PRESCALE"), 0)
    await m.write(o("PWM_CTRL"), 0xF)               # enable all four channels
    await ClockCycles(dut.clk, 24)
    await m.write(o("PWM_CTRL"), 0)                 # disabled channels cannot wrap: bits hold
    await ClockCycles(dut.clk, 4)
    st, _ = await m.read(o("PWM_IRQ_STAT"))
    assert st == 0xF, f"four enabled channels must each have wrapped, STAT=0x{st:x}"
    rep = await check_w1c(m, o("PWM_IRQ_STAT"), o("PWM_IRQ_CLR"),
                          [(b, b) for b in range(4)], name="PWM_IRQ_STAT")
    rep.assert_clean()
