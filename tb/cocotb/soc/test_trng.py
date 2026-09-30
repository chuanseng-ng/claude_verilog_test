"""test_trng.py -- Phase 6a-4 cocotb verification for trng (rtl/periph/trng.sv, bead
claude_verilog_test-f7vs.8, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-4 -- TRNG" + Sec.9).

STRICT TDD: trng DOES NOT EXIST YET as of this suite's authorship. This is step 2 of the mandated
workflow ("the verification orchestrator runs before the RTL orchestrator" -- Sec.9) --
`make trng`/`make trng_lint` are EXPECTED to fail to elaborate until a separate RTL agent writes
rtl/periph/trng.sv (+ rtl/periph/trng_lfsr_entropy.sv) to match the contract documented here and in
tb/models/trng_lfsr_model.py (the authoritative, bit-exact specification of the entropy pipeline).

DUT: tb_trng (standalone wrapper, directly instantiates trng, ADDR_W=12). The only port beyond the
APB4 face is `irq_o`: the peripheral has NO top-level pins. There is no async input, hence no CDC of
its own; the single clock domain is core_clk (== clk in tb_trng).

Register map (trng.sv, ADDR_W=12 local byte offset, N_REGS=8):
  0x000  TRNG_CTRL     [RW]   [0] enable, [1] IRQ enable, [5:2] FIFO threshold; [31:6] reserved
  0x004  TRNG_STATUS   [RO]   [0] data ready (FIFO level >= 1), [1] FIFO full (level == 4),
                              [2] health_fail (sticky), [3] INSECURE; [31:4] read 0
  0x008  TRNG_DATA     [RO]   a read POPS one 32-bit word from the 4-deep FIFO (read-snoop, the
                              SPI_RX idiom). The only RO register in this SoC with a read side effect.
  0x00C  TRNG_SEED     [RW]   32-bit LFSR seed; sampled at the CTRL.ENABLE 0->1 edge
  0x010  TRNG_IRQ_CLR  [WO]   W1C against STATUS.health_fail; reads 0
  0x014, 0x018, 0x01C  reserved: write dropped, read 0
  >=0x020 (word index >= 8)   out-of-range: writes dropped, reads return 0, pslverr=0

ENTROPY SOURCE IS `ifdef-SWAPPED, NOT A PORT (Sec.7 "Key structural decision"):
    `ifdef TRNG_RO_SKY130   rtl/periph/trng_ro_sky130.sv    (ring oscillator + blackbox stub)
    `else                   rtl/periph/trng_lfsr_entropy.sv (default -- the arm this suite tests)
trng.sv itself is 100 % portable (it sits in every file list and every PD flow); only the entropy-
QUALITY claim is Sky130-exclusive. tb_trng does not define TRNG_RO_SKY130, so this suite always
exercises the LFSR arm: three LFSRs on distinct primitive polynomials (31/29/23 bit) XOR-combined
through a von Neumann debiaser. That arm is DETERMINISTIC and explicitly NOT CRYPTOGRAPHIC, and it
must advertise the fact by forcing TRNG_STATUS.INSECURE = 1. Because it is deterministic from
TRNG_SEED it can be golden-vectored: tb/models/trng_lfsr_model.py is a pure-Python model of the
whole pipeline (seed slicing, LFSR step, raw XOR, von Neumann pairing, LSB-first word packing,
stall-not-drop backpressure, repetition-count health test) and the suite requires the RTL's popped
words to match it BIT-EXACTLY. `python3 tb/models/trng_lfsr_model.py` self-checks the model
standalone (polynomial primitivity, an independent recurrence cross-check of the LFSR step, the
stuck / late-trip seeds this suite depends on).

INSECURE (STATUS[3]) MUST READ 1 IN THE DEFAULT BUILD. It is the only thing distinguishing a
deterministic LFSR from real entropy behind a register named TRNG. test_trng_insecure_reads_one
asserts it at reset, while enabled, after filling, after a health failure, after a W1C of every bit
and after writes to STATUS -- it is constant, not a status that can be cleared or masked.

DISTRIBUTION CHECKS ARE SANITY, NOT A RANDOMNESS-QUALITY CLAIM. Bit balance within +/-5 %, no
repeated 32-word window, per-bit-lane balance and the debiaser's raw-samples-per-output-bit ratio
(test_trng_distribution_sanity) are passed trivially by a von Neumann debiaser over LFSRs, and
would be passed by many broken-but-plausible generators too. They exist to catch WIRING bugs (a
stuck word-assembly bit, a FIFO that repeats a word, a debiaser that keeps both bits of a pair), not
weak entropy. Real entropy quality is a Sky130 ring-oscillator / lab question, out of this phase.

Timing/pipeline contract this suite pins (see the model's docstring for the full derivation):
  - One raw sample per enabled, non-stalled core clock; sample 0 is consumed on the first edge
    after the edge that commits CTRL.ENABLE ("E"). Fill latency is therefore a known function of
    the seed: the k-th word is visible R_k .. R_k + FILL_SLACK edges after E, where R_k is
    TrngLfsrModel(seed).raw_consumed_for_words(k). FILL_SLACK absorbs registered pipeline stages.
  - The 4-deep FIFO applies BACKPRESSURE AS A STALL, never a drop: the sequence of popped words is
    a pure function of the seed, independent of when or how fast software reads.
  - The repetition-count health test (NIST SP 800-90B) runs on the RAW samples with cutoff C = 21.
    Adaptive-proportion is a documented non-goal.
  - STATUS/DATA are register-bank mirrors of internal state and may lag it by a cycle or two; the
    suite tolerates POP_SETTLE = 2 idle cycles after a pop before trusting STATUS again, and never
    pins an exact READY/FULL edge -- only the [R_k, R_k + FILL_SLACK] window.
  - irq_o is LEVEL-HELD, never a pulse: every IRQ source crosses core_clk -> cpu_core_clk through a
    plain 2-FF cdc_2ff_sync in soc_top, which can miss a pulse.
  - The W1C clear is an APB write-snoop on TRNG_IRQ_CLR, NOT a WMASK path, honouring pstrb; a
    hardware set beats a same-cycle clear so a health failure is never lost to a racing clear.
  - Disabled (CTRL[0] == 0): no entropy accumulates and the FIFO does not fill.

DECISIONS the spec left open. Writing the tests first is what settles them, so they are asserted
here and the RTL implements what this file asserts, not the reverse:

  D1. TRNG_DATA read on an EMPTY FIFO returns 0x0000_0000, sets NO error status (no sticky bit, no
      pslverr -- consistent with the rest of this bus, where out-of-range reads also return 0
      with pslverr=0), and does not underflow the FIFO. STATUS.data_ready is the ONLY validity
      indicator. Rationale: the unsafe alternatives are (a) returning the last word again, which
      hands firmware a REPEATED "random" word -- a key or nonce reused without any signal -- and
      (b) returning whatever a stale read-data register happens to hold. A constant 0 is the value
      no consumer mistakes for fresh entropy once it has checked ready, and the FIFO state is left
      untouched (a phantom pop must not corrupt the level: the next fill must still deliver exactly
      the golden four words). See test_trng_empty_read_returns_zero_no_error.
  D2. A TRNG_SEED write while the TRNG is ENABLED updates the register ONLY. It does NOT reseed the
      running LFSRs; the seed is sampled at the CTRL.ENABLE 0->1 edge, which also starts a fresh
      session (FIFO flushed, word assembler and health run-length cleared). Rationale: an
      immediate reseed would let any bus master force a known sequence at a chosen instant and
      splices two streams in mid-word; sampling at the enable edge means forcing a known sequence
      needs a VISIBLE disable->enable cycle, and it makes the seed's effect atomic with a flush of
      the words produced under the old seed. (Deterministic replay by disable/enable is a feature
      of the LFSR arm -- it is what makes the golden vectors possible -- and is exactly why
      STATUS.INSECURE is forced to 1.) See test_trng_seed_write_while_enabled.
  D3. health_fail HALTS entropy production and FLUSHES the FIFO. It is not just a status bit.
      Rationale: SP 800-90B says the output of a source that failed its health test must not be
      used, and the words already buffered were produced by the failing source. After the trip the
      FIFO reads empty (READY=0, FULL=0, DATA reads 0 per D1) and stays that way. Writing
      TRNG_IRQ_CLR bit 2 clears the sticky bit and RESUMES production from the current LFSR state
      (no reseed) with the repetition-count run length restarted from empty; a persistently stuck
      source simply trips again 21 samples later. Disabling / re-enabling does NOT clear
      health_fail. See test_trng_health_fail_flushes_and_halts / _sticky_and_w1c.

  Further decisions, made because the tests below cannot be written deterministically without them:
  D4. FIFO threshold 0 behaves as 1. Read literally, `fifo_level >= 0` is always true and would hold
      an enabled IRQ asserted forever (an interrupt storm from a reset-default field). Thresholds
      1..4 fire at that level; thresholds 5..15 can never be reached by a 4-deep FIFO, so they mean
      "IRQ on health failure only". See test_trng_threshold_irq.
  D5. TRNG_IRQ_CLR is BIT-ALIGNED with TRNG_STATUS (the WDT/GPIO convention): health_fail is STATUS
      bit 2, so it is cleared by writing 1 to IRQ_CLR bit 2 (0x4). Writes to the other bits (incl.
      bit 0/1/3) do nothing. Spec: "W1C against STATUS.health_fail".
  D6. Disabling RETAINS the FIFO contents (they are readable and still count toward the IRQ level);
      only the next ENABLE edge flushes. irq_o depends on CTRL[1] but NOT on CTRL[0].
  D7. TRNG_SEED resets to trng_lfsr_model.DEFAULT_SEED (0xACE1_2345), a value verified healthy;
      a seed of 0 (or any seed whose low 31 bits are 0) is NOT rescued: it loads all-zero LFSRs,
      trips the health test at raw sample 21, and is therefore reported rather than hidden.

SAMPLING HAZARD (learned on PWM, test_pwm.py; repeated on WDT): outputs that are combinational off
registered state return the PRE-edge value if read straight after a helper that settles with
Timer(1, "step"). Every cycle-counting sampling loop below therefore does
`await RisingEdge(dut.clk)` FIRST and only then reads (through _peek(), or through _next_cycle()
for raw output pins), so each sample is the settled post-edge state of a known edge and no sample is
silently duplicated or skipped.

Tests:
  test_trng_reset_defaults
      CTRL 0, STATUS == 0x8 exactly (INSECURE only), DATA 0, SEED == DEFAULT_SEED, IRQ_CLR and the
      reserved words read 0, irq_o == 0; quiescent for 200 idle cycles.
  test_trng_insecure_reads_one
      STATUS[3] == 1 in every state and cannot be cleared by any write.
  test_trng_rw_roundtrip
      CTRL round-trips [5:0] with reserved bits masked; SEED round-trips all 32 bits.
  test_trng_ro_ignores_writes_wo_reads_zero
      Writes to STATUS/DATA (also while the FIFO is filling) are ignored and neither pop nor
      corrupt it; IRQ_CLR reads 0 whatever was written.
  test_trng_out_of_range_access
      Reserved + word index >= 8: write dropped (no aliasing onto IRQ_CLR/CTRL/SEED), read 0.
  test_trng_pstrb_partial_word
      Byte-strobed writes to SEED/CTRL/IRQ_CLR touch only the strobed bytes; strb=0 is a no-op.
  test_trng_fifo_fills_when_enabled
      READY then FULL rise inside the model-derived latency windows; exactly the four golden words;
      the FIFO then stalls (holds, does not drop or repeat) for 1500 cycles.
  test_trng_pop_on_read
      Each APB read of DATA pops exactly one word, in order; peeks, writes and STATUS reads do not.
  test_trng_empty_read_returns_zero_no_error
      D1: empty read -> 0, no error, no stale repeat, no underflow.
  test_trng_golden_words_default_seed
      First 16 words after reset match the model bit-exactly.
  test_trng_golden_words_custom_seeds
      First 8 words for five other seeds match; seed bit 31 is unused.
  test_trng_replay_independent_of_pop_timing
      Eager reading and heavily-stalled reading give the SAME 12 words (stall, not drop).
  test_trng_seed_write_while_enabled
      D2: a SEED write mid-run does not disturb the stream; the next enable edge flushes and reseeds;
      re-enable replays.
  test_trng_threshold_irq
      D4: irq_o == IRQ_EN & (level >= max(thr,1)) over the full level 0..4 x threshold 0..15 matrix.
  test_trng_irq_enable_masks_output_only
      CTRL[1]=0 drops irq_o (data and health paths) but leaves STATUS and production untouched.
  test_trng_health_fail_on_stuck_source
      Stuck/weak seeds trip health_fail at raw sample 21 (+ latency); nothing is produced; INSECURE.
  test_trng_health_fail_flushes_and_halts
      D3: a failure AFTER the FIFO has filled empties the FIFO and stops production.
  test_trng_health_fail_sticky_and_w1c
      Sticky across disable/enable; W1C (bit 2 only, D5) clears it and resumes production.
  test_trng_set_beats_same_cycle_clear
      A clear committing on exactly the trip edge leaves health_fail SET; one edge later clears it.
  test_trng_irq_level_held
      irq_o high on 100 consecutive cycles on both the health and the threshold path.
  test_trng_disabled_is_inert
      Disabled: nothing accumulates; a partly filled FIFO is retained and frozen (D6).
  test_trng_distribution_sanity
      128 words: bit balance, per-lane balance, no repeats, raw-per-bit ratio -- SANITY only.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb.utils import get_sim_time

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.apb4_master import APB4Master

from tb.models.trng_lfsr_model import (
    DEFAULT_SEED,
    FIFO_DEPTH,
    GOLDEN_SEEDS,
    KNOWN_ANSWER_DEFAULT_SEED,
    LATE_TRIP_SAMPLE,
    LATE_TRIP_SEED,
    LATE_TRIP_WORDS_BEFORE,
    RC_CUTOFF,
    STUCK_SEEDS,
    WORD_BITS,
    TrngLfsrModel,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10  # 100 MHz -- matches SoC reference clock (same convention as test_wdt.py)

TRNG_CTRL = 0x000
TRNG_STATUS = 0x004
TRNG_DATA = 0x008
TRNG_SEED = 0x00C
TRNG_IRQ_CLR = 0x010
TRNG_RESERVED = (0x014, 0x018, 0x01C)
TRNG_OUT_OF_RANGE = 0x020  # word index 8 -- first address past the 8-register map

CTRL_EN = 0x1
CTRL_IE = 0x2
CTRL_THR_SHIFT = 2

ST_READY = 0x1
ST_FULL = 0x2
ST_HEALTH = 0x4
ST_INSECURE = 0x8

HEALTH_CLR = 0x4  # IRQ_CLR bit 2: bit-aligned with STATUS[2] (D5)

FILL_SLACK = 24  # registered-pipeline tolerance on the model-derived fill / trip latencies
POP_SETTLE = 2  # idle cycles after a pop before STATUS is trusted again (mirror lag, see docstring)

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
    """Start 100 MHz clock and apply synchronous reset with the APB4 bus idled. The TRNG has no
    top-level inputs beyond clk/rst_n/APB4 (no async pins, no CDC)."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n.value = 0
    _idle_bus(dut)

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def _pulse_reset(dut) -> None:
    """Re-apply reset on an already-running clock (clean, identical starting state between the
    independent runs inside one test)."""
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
    combinationally off paddr/pwrite, independent of psel/penable -- and the TRNG_DATA pop is
    gated on psel & penable, so a peek of TRNG_DATA must not pop; test_trng_pop_on_read relies on
    that). Ported from test_wdt.py / test_pwm.py / test_gpio.py -- see test_gpio.py's docstring
    for the Verilator/cocotb settle-timing bug this `Timer(1, units="step")` works around."""
    dut.pwrite.value = 0
    dut.paddr.value = addr
    await Timer(1, units="step")
    return int(dut.prdata.value)


async def _next_cycle(dut) -> None:
    """Advance to the next rising edge and let the post-edge state settle, so raw output pins
    (irq_o) can be read as that edge's settled value. RisingEdge FIRST, then the settle -- see the
    SAMPLING HAZARD note in the module docstring."""
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


def _ctrl(en: int = 0, ie: int = 0, thr: int = 0) -> int:
    """Compose a TRNG_CTRL value."""
    return (en & 1) | ((ie & 1) << 1) | ((thr & 0xF) << CTRL_THR_SHIFT)


async def _write(bfm: APB4Master, addr: int, data: int, strb: int = 0xF) -> None:
    ok = await bfm.write(addr, data, strb)
    assert ok, f"write to 0x{addr:03x} returned SLVERR (this bus never SLVERRs)"


async def _read(bfm: APB4Master, addr: int) -> int:
    data, ok = await bfm.read(addr)
    assert ok, f"read of 0x{addr:03x} returned SLVERR (this bus never SLVERRs)"
    return data


async def _wait_status(dut, mask: int, value: int, max_cycles: int) -> int:
    """Advance one edge at a time, peeking TRNG_STATUS after each edge, until (STATUS & mask) ==
    value; return k, the number of edges consumed (the state is visible after edge k). Raises
    AssertionError on budget exhaustion -- an absent event is itself a bug this suite must catch,
    never a silent hang. Bus activity: none (peek only)."""
    for k in range(1, max_cycles + 1):
        await RisingEdge(dut.clk)  # edge first, then sample (see SAMPLING HAZARD)
        stat = await _peek(dut, TRNG_STATUS)
        if (stat & mask) == value:
            return k
    raise AssertionError(
        f"TRNG_STATUS & 0x{mask:x} never became 0x{value:x} within {max_cycles} cycles"
    )


async def _pop(dut, bfm: APB4Master) -> int:
    """One APB read of TRNG_DATA (pops one word), then POP_SETTLE idle cycles."""
    word = await _read(bfm, TRNG_DATA)
    await ClockCycles(dut.clk, POP_SETTLE)
    return word


async def _collect(dut, bfm: APB4Master, n: int, budget: int = 4000) -> list[int]:
    """Pop `n` words, waiting for STATUS.READY before each. `budget` is the per-word wait in
    cycles (a word costs ~128 raw samples on average; 4000 is a hard 'never came' bound)."""
    words = []
    for i in range(n):
        await _wait_status(dut, ST_READY, ST_READY, budget)
        words.append(await _pop(dut, bfm))
        assert len(words) == i + 1
    return words


async def _level(dut, bfm: APB4Master, en: int) -> int:
    """Measure the FIFO level (0..4) through irq_o: with IRQ_EN=1 and threshold k in 1..4,
    irq_o == (level >= k), so level == number of thresholds that fire. Leaves CTRL at
    (en, IE=1, thr=4). The FIFO must be STABLE while this runs -- disabled (en=0, D6: contents are
    retained) or full and stalled -- and health_fail must be clear (it would force irq_o high)."""
    fired = []
    for thr in (1, 2, 3, 4):
        await _write(bfm, TRNG_CTRL, _ctrl(en=en, ie=1, thr=thr))
        for _ in range(3):
            await _next_cycle(dut)
        fired.append(int(dut.irq_o.value))
    assert fired == sorted(fired, reverse=True), f"irq_o not monotone in threshold: {fired}"
    return sum(fired)


async def _enable_and_fill(dut, bfm: APB4Master, seed: int = DEFAULT_SEED) -> int:
    """Fresh reset, program `seed`, enable, wait until STATUS.FULL, then DISABLE so the four
    buffered words are frozen for inspection (D6: disable retains the FIFO). Returns the number of
    edges from the enable commit edge E to FULL being visible."""
    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, seed)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))  # now AT edge E
    k = await _wait_status(dut, ST_FULL, ST_FULL, 3000)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    return k


async def _run_late_trip(dut, bfm: APB4Master) -> list[int]:
    """Drive the LATE_TRIP_SEED session to its health failure with the FIFO kept topped up.
    Pops ONE word every 800 cycles (each pop lets production resume; 800 cycles is enough for the
    pipeline to run into backpressure again, so the FIFO holds words when the trip lands). CTRL is
    (en, IE, thr=15): irq_o == health_fail only. Returns the words popped before the trip; ends
    with STATUS.HEALTH observed set."""
    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, LATE_TRIP_SEED)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=1, thr=15))
    got: list[int] = []
    for _ in range(14):
        await ClockCycles(dut.clk, 800)
        stat = await _peek(dut, TRNG_STATUS)
        if stat & ST_HEALTH:
            return got
        assert stat & ST_READY, f"expected buffered words while draining, STATUS=0x{stat:x}"
        got.append(await _pop(dut, bfm))
    raise AssertionError(f"health_fail never observed for seed 0x{LATE_TRIP_SEED:08x}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_trng_reset_defaults(dut):
    """After reset: CTRL 0 (disabled, IRQ masked, threshold 0), STATUS == 0x8 EXACTLY (nothing
    ready, not full, no health failure -- only the constant INSECURE flag), DATA 0 (empty FIFO,
    D1), SEED == DEFAULT_SEED (D7), IRQ_CLR and the reserved words read 0, irq_o == 0. The block
    stays quiescent through 200 idle cycles (nothing accumulates while disabled)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    assert await _read(bfm, TRNG_CTRL) == 0
    stat = await _read(bfm, TRNG_STATUS)
    assert stat == ST_INSECURE, f"reset STATUS must be exactly INSECURE (0x8), got 0x{stat:x}"
    assert await _read(bfm, TRNG_DATA) == 0, "empty-FIFO DATA read must return 0 (D1)"
    seed = await _read(bfm, TRNG_SEED)
    assert seed == DEFAULT_SEED, f"SEED reset value 0x{seed:08x}, expected 0x{DEFAULT_SEED:08x}"
    assert await _read(bfm, TRNG_IRQ_CLR) == 0
    for addr in TRNG_RESERVED:
        assert await _read(bfm, addr) == 0, f"reserved 0x{addr:03x} must read 0"

    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0, "irq_o must be low out of reset"
    for _ in range(200):
        await _next_cycle(dut)
        assert int(dut.irq_o.value) == 0, "irq_o must stay low while idle/disabled"
    stat = await _peek(dut, TRNG_STATUS)
    assert stat == ST_INSECURE, f"STATUS drifted while disabled: 0x{stat:x}"
    assert await _read(bfm, TRNG_DATA) == 0, "nothing may accumulate while disabled"


@cocotb.test()
async def test_trng_insecure_reads_one(dut):
    """*** STATUS[3] (INSECURE) MUST READ 1 IN THE DEFAULT BUILD. *** The default entropy source is
    a deterministic LFSR: this bit is the ONLY thing distinguishing it from real entropy behind a
    register named TRNG. It must be constant -- asserted at reset, after CTRL writes, while
    enabled and producing, when full, after a health failure, after every possible W1C write, after
    writes to STATUS itself, and after disabling. Nothing may clear or mask it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    async def check(where: str) -> None:
        for how, stat in (("APB read", await _read(bfm, TRNG_STATUS)), ("peek", await _peek(dut, TRNG_STATUS))):
            assert stat & ST_INSECURE, (
                f"TRNG_STATUS.INSECURE (bit 3) MUST read 1 in the default LFSR build, but it "
                f"read 0 ({how}, {where}, STATUS=0x{stat:x}): a deterministic generator would be "
                f"indistinguishable from a real TRNG"
            )

    await check("at reset")
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=3))
    await check("after a CTRL write, disabled")

    # writes to STATUS must not clear it
    for val in (0x0000_0000, 0xFFFF_FFFF, 0x0000_0008):
        await _write(bfm, TRNG_STATUS, val)
        await check(f"after writing 0x{val:08x} to STATUS")

    # every W1C pattern incl. a direct hit on bit 3
    for val in (0x0000_0008, 0xFFFF_FFFF, 0x0000_000F):
        await _write(bfm, TRNG_IRQ_CLR, val)
        await check(f"after writing 0x{val:08x} to IRQ_CLR")

    # enabled, producing, full
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await ClockCycles(dut.clk, 20)
    await check("enabled, first cycles")
    await _wait_status(dut, ST_FULL, ST_FULL, 3000)
    await check("enabled and full")
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    await check("after disable")

    # health failure and its clear
    await _pulse_reset(dut)
    await check("after a second reset")
    await _write(bfm, TRNG_SEED, 0)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
    await check("with health_fail set")
    await _write(bfm, TRNG_IRQ_CLR, 0xFFFF_FFFF)
    await check("after W1C of health_fail")
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    await check("final")


@cocotb.test()
async def test_trng_rw_roundtrip(dut):
    """CTRL is [5:0] wide: every (IE, threshold) combination round-trips with EN=0 and reserved
    [31:6] reads 0 whatever was written. SEED round-trips all 32 bits (a write does not itself
    start anything: STATUS stays 0x8). CTRL=0xFFFF_FFFF reads back 0x3F (all defined bits set)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for ie in (0, 1):
        for thr in range(16):
            want = _ctrl(en=0, ie=ie, thr=thr)
            await _write(bfm, TRNG_CTRL, want)
            got = await _read(bfm, TRNG_CTRL)
            assert got == want, f"CTRL round trip: wrote 0x{want:x}, read 0x{got:x}"

    await _write(bfm, TRNG_CTRL, 0xFFFF_FFC0)  # only reserved bits
    assert await _read(bfm, TRNG_CTRL) == 0, "reserved CTRL bits [31:6] must not stick"
    await _write(bfm, TRNG_CTRL, 0xFFFF_FFFC)  # reserved + thr=0xF, IE=0, EN=0
    assert await _read(bfm, TRNG_CTRL) == 0x3C, "0xFFFF_FFFC (IE=EN=0) must read back 0x3C"

    for pattern in (0xFFFF_FFFF, 0x0000_0000, 0x5A5A_5A5A, 0xA5A5_A5A5, 0x0000_0001, 0x8000_0000):
        await _write(bfm, TRNG_SEED, pattern)
        got = await _read(bfm, TRNG_SEED)
        assert got == pattern, f"SEED round trip: wrote 0x{pattern:08x}, read 0x{got:08x}"

    await _write(bfm, TRNG_CTRL, 0x0)
    await ClockCycles(dut.clk, 50)
    assert await _peek(dut, TRNG_STATUS) == ST_INSECURE, "register writes alone must not start the TRNG"

    await _write(bfm, TRNG_CTRL, 0xFFFF_FFFF)
    assert await _read(bfm, TRNG_CTRL) == 0x3F, "all defined CTRL bits set must read 0x3F"
    await _write(bfm, TRNG_CTRL, 0x0)


@cocotb.test()
async def test_trng_ro_ignores_writes_wo_reads_zero(dut):
    """STATUS and DATA are read-only: APB stores to them are ignored. That has to hold while the
    hardware is WRITING those registers every cycle (the register bank lets a SW store win over a
    same-cycle HW write, so a naive RO word would swallow a FIFO-head update): 40 stores to
    STATUS/DATA are sprayed across the whole fill and the four words that come out must still be
    exactly the golden four -- nothing popped by a store, nothing lost, nothing corrupted.
    IRQ_CLR is write-only: it reads 0 whatever was written."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    golden = TrngLfsrModel(DEFAULT_SEED).words(FIFO_DEPTH)

    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    for i in range(20):
        await _write(bfm, TRNG_STATUS, 0xFFFF_FFFF if i % 2 else 0x0)
        await _write(bfm, TRNG_DATA, 0xDEAD_BEEF ^ i)
        await ClockCycles(dut.clk, 30)
    await _wait_status(dut, ST_FULL, ST_FULL, 3000)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))

    stat = await _read(bfm, TRNG_STATUS)
    assert stat == ST_READY | ST_FULL | ST_INSECURE, f"STATUS 0x{stat:x} != READY|FULL|INSECURE"
    for val in (0xFFFF_FFFF, 0x0000_0000, 0x0000_0004):
        await _write(bfm, TRNG_IRQ_CLR, val)
        assert await _read(bfm, TRNG_IRQ_CLR) == 0, f"IRQ_CLR must read 0 after writing 0x{val:x}"
    words = [await _pop(dut, bfm) for _ in range(FIFO_DEPTH)]
    assert words == golden, (
        f"stores to STATUS/DATA disturbed the FIFO: got {[hex(w) for w in words]}, "
        f"expected {[hex(w) for w in golden]}"
    )
    assert await _read(bfm, TRNG_STATUS) == ST_INSECURE


@cocotb.test()
async def test_trng_out_of_range_access(dut):
    """Reserved words (0x014/0x018/0x01C) and everything at word index >= 8 (0x020 ... 0xFFC):
    a write is dropped (pslverr=0, no aliasing onto CTRL/SEED/IRQ_CLR) and a read returns 0. The
    aliasing check is made with a REAL pending health_fail: a stray 0x4 landing on any of these
    addresses must not clear it (i.e. must not alias to TRNG_IRQ_CLR at 0x010)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    addrs = (*TRNG_RESERVED, TRNG_OUT_OF_RANGE, 0x024, 0x100, 0x7FC, 0xFFC)
    for addr in addrs:
        assert await _read(bfm, addr) == 0, f"read of unmapped 0x{addr:03x} must return 0"
        await _write(bfm, addr, 0xFFFF_FFFF)
        assert await _read(bfm, addr) == 0, f"unmapped 0x{addr:03x} must not store"
    assert await _read(bfm, TRNG_CTRL) == 0, "a stray write aliased onto TRNG_CTRL"
    assert await _read(bfm, TRNG_SEED) == DEFAULT_SEED, "a stray write aliased onto TRNG_SEED"
    assert await _read(bfm, TRNG_STATUS) == ST_INSECURE

    # aliasing onto IRQ_CLR, against a live health_fail (seed 0 = stuck source)
    await _write(bfm, TRNG_SEED, 0)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
    for addr in addrs:
        await _write(bfm, addr, HEALTH_CLR)
        assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, (
            f"a write of 0x4 to unmapped 0x{addr:03x} cleared health_fail (aliased onto IRQ_CLR)"
        )
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_pstrb_partial_word(dut):
    """Byte strobes: SEED and CTRL update only the strobed bytes and strb=0 is a no-op. The W1C
    write-snoop on IRQ_CLR honours pstrb too (health_fail is bit 2 == byte 0): a store whose
    byte-0 strobe is clear cannot clear it, even when the data carries the bit, and only a store
    strobing byte 0 does."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _write(bfm, TRNG_SEED, 0x0000_0000)
    steps = (  # (data, strb, expected SEED after)
        (0xAABB_CCDD, 0b0001, 0x0000_00DD),
        (0xAABB_CCDD, 0b0010, 0x0000_CCDD),
        (0xAABB_CCDD, 0b0100, 0x00BB_CCDD),
        (0xAABB_CCDD, 0b1000, 0xAABB_CCDD),
        (0x1111_1111, 0b0000, 0xAABB_CCDD),  # strb=0: no-op
        (0x1234_5678, 0b1010, 0x12BB_56DD),
    )
    for data, strb, want in steps:
        await _write(bfm, TRNG_SEED, data, strb)
        got = await _read(bfm, TRNG_SEED)
        assert got == want, f"SEED after 0x{data:08x} strb={strb:04b}: 0x{got:08x}, want 0x{want:08x}"

    await _write(bfm, TRNG_CTRL, 0x3C)
    await _write(bfm, TRNG_CTRL, 0x0000_0001, strb=0b0010)  # byte 1 only: EN (byte 0) untouched
    assert await _read(bfm, TRNG_CTRL) == 0x3C
    await ClockCycles(dut.clk, 100)
    assert await _peek(dut, TRNG_STATUS) == ST_INSECURE, "CTRL.EN set through a byte-1-only strobe"
    await _write(bfm, TRNG_CTRL, 0x0000_0001, strb=0b0001)  # byte 0: replaces [7:0]
    assert await _read(bfm, TRNG_CTRL) == 0x01
    await _write(bfm, TRNG_CTRL, 0x0)

    # W1C honours pstrb: stuck source (seed 0) gives a live health_fail
    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, 0)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
    for strb in (0b0010, 0b1110, 0b0000):
        await _write(bfm, TRNG_IRQ_CLR, 0xFFFF_FFFF, strb)
        assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, (
            f"IRQ_CLR store with byte-0 strobe clear (strb={strb:04b}) cleared health_fail"
        )
    await _write(bfm, TRNG_IRQ_CLR, HEALTH_CLR, 0b0001)
    assert not (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "strb=0001 W1C of bit 2 must clear"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_fifo_fills_when_enabled(dut):
    """From reset, enable with the default seed and watch STATUS every edge. The model fixes how
    many raw samples each word costs (one raw sample per enabled clock, von Neumann discarding
    ~75 % of them), so the k-th word must be visible R_k .. R_k + FILL_SLACK edges after the
    enable commit edge E. Also: STATUS is exactly INSECURE (nothing ready) before word 1; READY
    rises WITHOUT FULL; FULL comes with READY; afterwards the FIFO STALLS -- 1500 further cycles
    leave it at exactly READY|FULL -- and exactly the four golden words come out (no drop, no
    repeat under backpressure). A debiaser that kept both bits of a pair, or a source that ran
    faster/slower than one sample per clock, misses these windows."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    model = TrngLfsrModel(DEFAULT_SEED)
    r1 = model.raw_consumed_for_words(1)
    r4 = model.raw_consumed_for_words(FIFO_DEPTH)
    golden = model.words(FIFO_DEPTH)

    await _write(bfm, TRNG_CTRL, _ctrl(en=1))  # now AT edge E
    k_ready = k_full = None
    for k in range(1, r4 + FILL_SLACK + 200):
        await RisingEdge(dut.clk)  # edge first, then sample (see SAMPLING HAZARD)
        stat = await _peek(dut, TRNG_STATUS)
        assert stat & ST_INSECURE
        assert not stat & ST_HEALTH, f"spurious health_fail at edge {k}, STATUS=0x{stat:x}"
        if k_ready is None and stat & ST_READY:
            k_ready = k
            assert not stat & ST_FULL, f"FULL asserted together with the first word, STATUS=0x{stat:x}"
        if stat & ST_FULL:
            assert stat & ST_READY, "FULL without READY"
            k_full = k
            break
    assert k_ready is not None and k_full is not None, "FIFO never filled"
    assert r1 <= k_ready <= r1 + FILL_SLACK, (
        f"first word visible at edge {k_ready}, expected within [{r1}, {r1 + FILL_SLACK}] "
        f"(model: {r1} raw samples)"
    )
    assert r4 <= k_full <= r4 + FILL_SLACK, (
        f"FIFO full at edge {k_full}, expected within [{r4}, {r4 + FILL_SLACK}] "
        f"(model: {r4} raw samples for 4 words)"
    )

    for _ in range(15):  # stalled: holds at FULL, nothing dropped, nothing new
        await ClockCycles(dut.clk, 100)
        stat = await _peek(dut, TRNG_STATUS)
        assert stat == ST_READY | ST_FULL | ST_INSECURE, f"stalled FIFO STATUS 0x{stat:x}"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    words = [await _pop(dut, bfm) for _ in range(FIFO_DEPTH)]
    assert words == golden, f"got {[hex(w) for w in words]}, expected {[hex(w) for w in golden]}"
    assert await _peek(dut, TRNG_STATUS) == ST_INSECURE, "FIFO must be empty after four pops"


@cocotb.test()
async def test_trng_pop_on_read(dut):
    """TRNG_DATA is the one RO register with a read side effect: each APB READ ACCESS pops exactly
    one word, in order. Nothing else pops: not a peek of the read-data path (no psel/penable), not
    reads of the other registers, not stores to DATA. Level is measured through the threshold IRQ
    (irq_o == level >= thr) on a frozen (disabled, D6) FIFO holding the four golden words:
    4 -> 3 -> 2 -> 1 -> 0, and STATUS READY/FULL track it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    golden = TrngLfsrModel(DEFAULT_SEED).words(FIFO_DEPTH)

    await _enable_and_fill(dut, bfm)
    assert await _level(dut, bfm, en=0) == 4

    for _ in range(5):
        await _peek(dut, TRNG_DATA)
    for addr in (TRNG_CTRL, TRNG_STATUS, TRNG_SEED, TRNG_IRQ_CLR, *TRNG_RESERVED):
        await _read(bfm, addr)
    await _write(bfm, TRNG_DATA, 0x1234_5678)
    assert await _level(dut, bfm, en=0) == 4, "peeks / other reads / a DATA store popped the FIFO"

    seen = []
    for i in range(FIFO_DEPTH):
        word = await _pop(dut, bfm)
        assert word == golden[i], f"pop {i}: got 0x{word:08x}, expected 0x{golden[i]:08x}"
        seen.append(word)
        lvl = await _level(dut, bfm, en=0)
        assert lvl == FIFO_DEPTH - 1 - i, f"after pop {i} level is {lvl}, expected {FIFO_DEPTH - 1 - i}"
        stat = await _peek(dut, TRNG_STATUS)
        assert bool(stat & ST_READY) == (lvl > 0), f"READY inconsistent with level {lvl}: 0x{stat:x}"
        assert not stat & ST_FULL, f"FULL still set at level {lvl}: 0x{stat:x}"
    assert len(set(seen)) == FIFO_DEPTH, "consecutive reads returned the same word (no pop?)"


@cocotb.test()
async def test_trng_empty_read_returns_zero_no_error(dut):
    """D1: reading TRNG_DATA on an EMPTY FIFO returns 0x0000_0000 with pslverr=0, sets NO status
    (STATUS stays exactly INSECURE: no sticky underrun bit, no health_fail) and must NOT return the
    last-popped word again (a repeated 'random' word is the unsafe outcome this decision exists to
    prevent). The FIFO must not underflow either: after several empty reads a normal fill still
    delivers exactly the golden four words, then reads 0 again."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    golden = TrngLfsrModel(DEFAULT_SEED).words(FIFO_DEPTH)

    for i in range(4):  # empty from reset
        assert await _read(bfm, TRNG_DATA) == 0, f"empty read {i} returned non-zero"
    assert await _read(bfm, TRNG_STATUS) == ST_INSECURE, "an empty read must not set any status"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0

    await _enable_and_fill(dut, bfm)
    words = [await _pop(dut, bfm) for _ in range(FIFO_DEPTH)]
    assert words == golden, "phantom pops from the earlier empty reads corrupted the FIFO"

    for i in range(3):  # empty after draining: must not repeat golden[3]
        word = await _read(bfm, TRNG_DATA)
        assert word == 0, f"empty read after drain returned 0x{word:08x} (stale/repeated word?)"
    stat = await _read(bfm, TRNG_STATUS)
    assert stat == ST_INSECURE, f"STATUS 0x{stat:x} after empty reads, expected only INSECURE"
    assert await _level(dut, bfm, en=0) == 0, "empty reads changed the FIFO level"


@cocotb.test()
async def test_trng_golden_words_default_seed(dut):
    """THE determinism check. From reset (TRNG_SEED == DEFAULT_SEED) the first 16 words popped
    must match tb/models/trng_lfsr_model.py BIT-EXACTLY: seed slicing, all three LFSR
    polynomials/taps, the raw XOR, von Neumann pairing, LSB-first packing and FIFO ordering. The
    model's pinned known-answer words are asserted too, so a silent edit of the model cannot make
    the suite chase a moved target. health_fail must stay clear throughout."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    model = TrngLfsrModel(DEFAULT_SEED)
    golden = model.words(16)
    assert golden[: len(KNOWN_ANSWER_DEFAULT_SEED)] == KNOWN_ANSWER_DEFAULT_SEED, "model drifted"

    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    words = await _collect(dut, bfm, 16)
    for i, (got, want) in enumerate(zip(words, golden, strict=True)):
        assert got == want, (
            f"word {i}: RTL 0x{got:08x} != model 0x{want:08x} "
            f"(first mismatch; RTL {[hex(w) for w in words[:4]]} vs model {[hex(w) for w in golden[:4]]})"
        )
    stat = await _peek(dut, TRNG_STATUS)
    assert not stat & ST_HEALTH, f"health_fail set on a healthy seed, STATUS=0x{stat:x}"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_golden_words_custom_seeds(dut):
    """The seed really drives the stream: five further seeds (each verified healthy by the model)
    give their own first 8 golden words. Seed BIT 31 IS UNUSED (the LFSRs are seeded from
    seed[30:0] / [28:0] / [22:0]): setting it must not change a single word -- this pins the
    slicing that a wrong-width or rotated seed mapping would break."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    async def run(seed: int, n: int) -> list[int]:
        await _pulse_reset(dut)
        await _write(bfm, TRNG_SEED, seed)
        await _write(bfm, TRNG_CTRL, _ctrl(en=1))
        words = await _collect(dut, bfm, n)
        await _write(bfm, TRNG_CTRL, _ctrl(en=0))
        return words

    distinct = set()
    for seed in GOLDEN_SEEDS:
        golden = TrngLfsrModel(seed).words(8)
        words = await run(seed, 8)
        assert words == golden, (
            f"seed 0x{seed:08x}: RTL {[hex(w) for w in words]} != model {[hex(w) for w in golden]}"
        )
        distinct.add(tuple(golden))
    assert len(distinct) == len(GOLDEN_SEEDS), "different seeds must give different streams"

    base = GOLDEN_SEEDS[-1]
    words = await run(base | 0x8000_0000, 4)
    assert words == TrngLfsrModel(base).words(4), "seed bit 31 must be unused"


@cocotb.test()
async def test_trng_replay_independent_of_pop_timing(dut):
    """BACKPRESSURE IS A STALL, NOT A DROP: the sequence of popped words is a pure function of the
    seed. The same seed is read (a) eagerly, and (b) lazily -- a 3000-cycle head start that fills
    and stalls the pipeline, then pops separated by irregular idle gaps of 0..1500 cycles (each
    gap lets the FIFO fill and stall again). Both must equal the model's 12 words. A pipeline that
    kept sampling while the FIFO was full and discarded bits would desynchronise here."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    seed = GOLDEN_SEEDS[3]
    golden = TrngLfsrModel(seed).words(12)

    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, seed)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    eager = await _collect(dut, bfm, 12)
    assert eager == golden, f"eager read: {[hex(w) for w in eager]} != {[hex(w) for w in golden]}"

    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, seed)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await ClockCycles(dut.clk, 3000)
    lazy = []
    for gap in (0, 700, 0, 1500, 50, 0, 0, 900, 1200, 10, 0, 300):
        await ClockCycles(dut.clk, gap)
        await _wait_status(dut, ST_READY, ST_READY, 4000)
        lazy.append(await _pop(dut, bfm))
    assert lazy == golden, f"lazy read: {[hex(w) for w in lazy]} != {[hex(w) for w in golden]}"


@cocotb.test()
async def test_trng_seed_write_while_enabled(dut):
    """D2: a TRNG_SEED write while ENABLED only updates the register (it reads back) -- the running
    LFSRs are NOT reseeded, so ten consecutive words still follow seed A. The seed is sampled at the
    CTRL.ENABLE 0->1 edge, which starts a fresh session: (b) disable/enable takes seed B and FLUSHES
    the words A left in the FIFO (D6: disable itself retains them); (c) disable/enable again with
    no SEED write REPLAYS B's stream; (d) a SEED written while disabled is picked up at the next
    enable. An immediate reseed would let any bus master force a known sequence mid-run."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    seed_a, seed_b, seed_c = GOLDEN_SEEDS[1], GOLDEN_SEEDS[2], GOLDEN_SEEDS[4]
    ma, mb, mc = TrngLfsrModel(seed_a), TrngLfsrModel(seed_b), TrngLfsrModel(seed_c)

    await _write(bfm, TRNG_SEED, seed_a)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    got = await _collect(dut, bfm, 2)
    await _write(bfm, TRNG_SEED, seed_b)  # while enabled
    assert await _read(bfm, TRNG_SEED) == seed_b, "SEED must still be a plain RW register"
    got += await _collect(dut, bfm, 8)
    assert got == ma.words(10), (
        f"a SEED write while enabled disturbed the running stream: {[hex(w) for w in got]}"
    )

    # (b) disable retains, enable flushes + reseeds
    #
    # PRECONDITION: _collect() above drained every word it produced, so the FIFO
    # is empty right now. Asserting "disable retains buffered words" against an
    # empty FIFO tests nothing and cannot pass -- the next word does not complete
    # for ~90 more raw samples. Wait for a word to actually be BUFFERED first,
    # then disable, then assert it survived. The assertion itself is unchanged;
    # this only establishes the precondition it always needed.
    await _wait_status(dut, ST_READY, ST_READY, 4000)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    await ClockCycles(dut.clk, 20)
    assert (await _peek(dut, TRNG_STATUS)) & ST_READY, "D6: disabling must retain buffered words"
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await ClockCycles(dut.clk, 4)
    assert await _collect(dut, bfm, 4) == mb.words(4), "enable edge must flush and load the new seed"

    # (c) replay
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    await ClockCycles(dut.clk, 20)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await ClockCycles(dut.clk, 4)
    assert await _collect(dut, bfm, 4) == mb.words(4), "re-enable with the same seed must replay"

    # (d) SEED written while disabled
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    await _write(bfm, TRNG_SEED, seed_c)
    await ClockCycles(dut.clk, 20)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    await ClockCycles(dut.clk, 4)
    assert await _collect(dut, bfm, 4) == mc.words(4), "SEED written while disabled not picked up"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_threshold_irq(dut):
    """irq_o == IRQ_EN & (level >= thr), level-driven, over the FULL matrix: FIFO level 4..0
    (a frozen, disabled FIFO holding golden words, popped one at a time) x threshold 0..15.
    D4: threshold 0 behaves as 1 (level >= 0 would be a permanently asserted interrupt), and
    thresholds 5..15 can never fire on a 4-deep FIFO. IRQ_EN=0 masks every cell. Then the live
    case: enabled from reset with thr=4, irq_o stays low until the FIFO is full (never more than
    the 2-cycle mirror lag early) and is high once it is."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _enable_and_fill(dut, bfm)
    for level in range(FIFO_DEPTH, -1, -1):
        if level < FIFO_DEPTH:
            await _pop(dut, bfm)
        for thr in range(16):
            await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=thr))
            for _ in range(3):
                await _next_cycle(dut)
            want = int(level >= max(thr, 1))
            got = int(dut.irq_o.value)
            assert got == want, f"level={level} thr={thr}: irq_o={got}, expected {want}"
        await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=0, thr=1))  # masked
        for _ in range(3):
            await _next_cycle(dut)
        assert int(dut.irq_o.value) == 0, f"level={level}: IRQ_EN=0 must mask irq_o"

    # live: thr = FIFO depth -> irq_o tracks FULL
    await _pulse_reset(dut)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=1, thr=FIFO_DEPTH))
    r4 = TrngLfsrModel(DEFAULT_SEED).raw_consumed_for_words(FIFO_DEPTH)
    early = 0
    for k in range(1, r4 + FILL_SLACK + 100):
        await RisingEdge(dut.clk)
        stat = await _peek(dut, TRNG_STATUS)
        irq = int(dut.irq_o.value)
        if stat & ST_FULL:
            break
        early = early + 1 if irq else 0
        assert early <= 2, f"irq_o high for {early} cycles before the FIFO is full (edge {k})"
    else:
        raise AssertionError("FIFO never filled")
    for _ in range(4):
        await _next_cycle(dut)
    assert int(dut.irq_o.value) == 1, "irq_o must be high once level >= threshold"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_irq_enable_masks_output_only(dut):
    """CTRL[1] (IRQ enable) gates irq_o and NOTHING ELSE. (a) full FIFO, thr=1: IE=0 -> irq_o low
    while STATUS still shows READY|FULL; IE=1 -> high; IE=0 -> low again. (b) enabled with IE=0 the
    FIFO still fills (production is not masked) and irq_o stays low. (c) health path: with a stuck
    seed and IE=0, STATUS.health_fail is set but irq_o is low; IE=1 raises it (thr=15 can never
    fire, so it is the health term alone); IE=0 drops it again with health_fail still set."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    async def irq_after(ctrl: int) -> int:
        await _write(bfm, TRNG_CTRL, ctrl)
        for _ in range(3):
            await _next_cycle(dut)
        return int(dut.irq_o.value)

    await _enable_and_fill(dut, bfm)
    assert await irq_after(_ctrl(en=0, ie=0, thr=1)) == 0
    assert await _peek(dut, TRNG_STATUS) == ST_READY | ST_FULL | ST_INSECURE, "IE must not touch STATUS"
    assert await irq_after(_ctrl(en=0, ie=1, thr=1)) == 1
    assert await irq_after(_ctrl(en=0, ie=0, thr=1)) == 0

    await _pulse_reset(dut)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=0, thr=1))
    await _wait_status(dut, ST_FULL, ST_FULL, 3000)
    for _ in range(4):
        await _next_cycle(dut)
    assert int(dut.irq_o.value) == 0, "IE=0 must keep irq_o low even with the FIFO full"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))

    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, 0)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=0, thr=15))
    await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
    for _ in range(3):
        await _next_cycle(dut)
    assert int(dut.irq_o.value) == 0, "IE=0 must mask the health_fail interrupt"
    assert await irq_after(_ctrl(en=1, ie=1, thr=15)) == 1, "IE=1 must raise irq_o on health_fail"
    assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "rewriting CTRL must not clear health_fail"
    assert await irq_after(_ctrl(en=1, ie=0, thr=15)) == 0
    assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "IE must not touch health_fail"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_health_fail_on_stuck_source(dut):
    """Repetition-count health test (NIST SP 800-90B, cutoff C = 21 on the RAW samples): seeds that
    make every LFSR emit a constant run -- 0 and 0x8000_0000 (all-zero slices: lock-up, NOT
    rescued), 1, 0xFFFF_FFFF and 0x7FFF_FFFF -- trip health_fail at raw sample 21. Enabled at
    edge E it must become visible k edges later with 21 <= k <= 21 + FILL_SLACK (the 21st identical
    sample cannot be consumed any sooner than one per clock). Nothing is ever produced (no word
    fits in 21 samples), the source stays halted, irq_o rises with IRQ_EN, and INSECURE stays 1.
    A weak/dead source is REPORTED, not papered over (D7)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for seed in STUCK_SEEDS:
        trip = TrngLfsrModel(seed).health_trip_sample(1000)
        assert trip == RC_CUTOFF, f"model: seed 0x{seed:08x} trips at {trip}, expected {RC_CUTOFF}"
        await _pulse_reset(dut)
        await _write(bfm, TRNG_SEED, seed)
        await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=1, thr=15))  # now AT edge E
        k = await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
        assert RC_CUTOFF <= k <= RC_CUTOFF + FILL_SLACK, (
            f"seed 0x{seed:08x}: health_fail visible {k} edges after enable, expected within "
            f"[{RC_CUTOFF}, {RC_CUTOFF + FILL_SLACK}]"
        )
        for _ in range(2):
            await _next_cycle(dut)
        assert int(dut.irq_o.value) == 1, "health_fail must raise irq_o (IRQ_EN=1)"
        await ClockCycles(dut.clk, 500)
        stat = await _peek(dut, TRNG_STATUS)
        assert stat == ST_HEALTH | ST_INSECURE, (
            f"seed 0x{seed:08x}: STATUS 0x{stat:x} after the trip, expected HEALTH|INSECURE only "
            f"(no word may be produced, and none was possible)"
        )
        assert await _read(bfm, TRNG_DATA) == 0
        await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_health_fail_flushes_and_halts(dut):
    """D3: a health failure that lands AFTER the FIFO has filled with apparently good words. The
    model's LATE_TRIP_SEED runs healthy for 980 raw samples (7 complete words) and trips at raw
    sample 981. The FIFO is kept topped up by popping one word every 800 cycles; when the trip lands
    it must (a) not land early -- at least 2 and at most 7 words were popped first, all matching the
    golden prefix -- then (b) FLUSH the FIFO (READY=0, FULL=0, DATA reads 0: the buffered words
    came from the failing source), (c) HALT production (still empty 2000 cycles later, STATUS
    exactly HEALTH|INSECURE), and (d) hold irq_o high (thr=15 cannot fire, so it is the health
    term alone)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    model = TrngLfsrModel(LATE_TRIP_SEED)
    assert model.health_trip_sample(5000) == LATE_TRIP_SAMPLE
    assert model.words_before_trip() == LATE_TRIP_WORDS_BEFORE

    got = await _run_late_trip(dut, bfm)
    assert 2 <= len(got) <= LATE_TRIP_WORDS_BEFORE, (
        f"{len(got)} words popped before health_fail: it tripped too early/late for a raw "
        f"sample-{LATE_TRIP_SAMPLE} failure ({LATE_TRIP_WORDS_BEFORE} words precede it)"
    )
    assert got == model.words(len(got)), "words popped before the trip must match the golden prefix"

    await ClockCycles(dut.clk, 3)
    stat = await _peek(dut, TRNG_STATUS)
    assert stat & ST_HEALTH
    assert not stat & (ST_READY | ST_FULL), f"FIFO not flushed at the trip, STATUS=0x{stat:x}"
    assert await _read(bfm, TRNG_DATA) == 0, "DATA must read 0 after the flush (D1/D3)"
    await _next_cycle(dut)
    assert int(dut.irq_o.value) == 1, "health_fail must hold irq_o high"

    await ClockCycles(dut.clk, 2000)
    stat = await _peek(dut, TRNG_STATUS)
    assert stat == ST_HEALTH | ST_INSECURE, f"production did not halt: STATUS=0x{stat:x} after 2000 cycles"
    assert await _read(bfm, TRNG_DATA) == 0
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_health_fail_sticky_and_w1c(dut):
    """health_fail is STICKY: it survives idling, W1C writes that miss bit 2 (0xB, 0x0), disabling
    and re-enabling (an enable edge starts a new session but does not clear it). Only a W1C of
    bit 2 (D5) clears it, which also drops irq_o. Then the resume half of D3: after the clear on a
    still-enabled TRNG production RESUMES from the current LFSR state -- STATUS.READY comes back,
    and, the stream past the failing run being healthy (model: longest later run is 11 < 21),
    health_fail does not re-trip."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _run_late_trip(dut, bfm)  # ends enabled, IE=1, thr=15
    await ClockCycles(dut.clk, 500)
    assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "health_fail must be sticky"
    for miss in (0x0000_000B, 0x0000_0000, 0xFFFF_FFFB):
        await _write(bfm, TRNG_IRQ_CLR, miss)
        assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, (
            f"W1C of 0x{miss:x} (bit 2 clear) cleared health_fail"
        )
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=15))
    await ClockCycles(dut.clk, 20)
    assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "disabling must not clear health_fail"
    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=1, thr=15))  # new session
    assert (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "re-enabling must not clear health_fail"
    await ClockCycles(dut.clk, 5)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=15))
    await _write(bfm, TRNG_IRQ_CLR, HEALTH_CLR)
    assert not (await _peek(dut, TRNG_STATUS)) & ST_HEALTH, "W1C of bit 2 must clear health_fail"
    for _ in range(3):
        await _next_cycle(dut)
    assert int(dut.irq_o.value) == 0, "irq_o must fall with health_fail (FIFO empty, thr=15)"

    # resume half of D3
    await _run_late_trip(dut, bfm)
    await _write(bfm, TRNG_IRQ_CLR, HEALTH_CLR)
    assert not (await _peek(dut, TRNG_STATUS)) & ST_HEALTH
    await _wait_status(dut, ST_READY, ST_READY, 1500)  # production resumed
    await ClockCycles(dut.clk, 1500)
    stat = await _peek(dut, TRNG_STATUS)
    assert stat & ST_READY and not stat & ST_HEALTH, (
        f"after the clear production must resume without re-tripping, STATUS=0x{stat:x}"
    )
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))


@cocotb.test()
async def test_trng_set_beats_same_cycle_clear(dut):
    """A TRNG_IRQ_CLR write whose ACCESS-phase commit edge coincides EXACTLY with the edge that
    latches health_fail must leave it SET -- a health failure is never lost to a racing clear (W1C
    is an APB write-snoop and the hardware set wins, as in gpio/pwm/wdt).

    Method (test_wdt_set_beats_same_cycle_clear, without assuming a latency constant): the
    enable-to-trip latency of the stuck seed 0 is identical on every run from reset, so (1)
    CALIBRATE it as k edges after E, (2) rerun the identical bus sequence from a fresh reset and
    land a raw APB write's commit edge on E+k, cycle-exact. Edge arithmetic: after the enable write
    returns we are AT edge E; a raw write's SETUP is sampled 1 edge after arming and its ACCESS
    commits 1 edge after that, so arming SETUP at E+(k-2) commits at E+k. CONTROLS: the same clear
    one edge LATER (E+k+1) must clear the bit (the alignment is not accidentally a whole edge
    early), and one edge EARLIER (E+k-1) has nothing to clear so the bit must still get set."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _pulse_reset(dut)
    await _write(bfm, TRNG_SEED, 0)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1))
    k = await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
    assert RC_CUTOFF <= k <= RC_CUTOFF + FILL_SLACK, f"calibration: trip at edge {k}"

    async def run(offset: int) -> tuple[int, int]:
        await _pulse_reset(dut)
        await _write(bfm, TRNG_SEED, 0)
        await _write(bfm, TRNG_CTRL, _ctrl(en=1))  # now AT edge E
        await ClockCycles(dut.clk, k + offset - 2)
        _raw_write_setup(dut, TRNG_IRQ_CLR, HEALTH_CLR)
        await RisingEdge(dut.clk)  # SETUP sampled
        _raw_write_access(dut)
        await RisingEdge(dut.clk)  # ACCESS commits on edge E + k + offset
        _raw_write_idle(dut)
        at_commit = await _peek(dut, TRNG_STATUS)
        await RisingEdge(dut.clk)
        return at_commit, await _peek(dut, TRNG_STATUS)

    at, later = await run(0)
    assert at & ST_HEALTH, (
        f"a IRQ_CLR write landing on the SAME edge as the health_fail set must leave it SET "
        f"(set beats clear), got STATUS=0x{at:x}"
    )
    assert later & ST_HEALTH, "health_fail must stay set after the racing clear"

    at, _ = await run(1)
    assert not at & ST_HEALTH, (
        f"control: a clear committing one edge AFTER the set must clear it, got STATUS=0x{at:x} -- "
        f"the race alignment above would not have been on the set edge"
    )
    at, later = await run(-1)
    assert not at & ST_HEALTH, f"control: a clear one edge BEFORE the trip cannot set anything: 0x{at:x}"
    assert later & ST_HEALTH, "control: the trip must still land after an early, useless clear"
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    dut._log.info(f"set-beats-same-cycle-clear confirmed for health_fail (k={k})")


@cocotb.test()
async def test_trng_irq_level_held(dut):
    """irq_o is a LEVEL, never a pulse (the SoC's plain 2-FF IRQ synchroniser can miss a pulse).
    (a) health path: low for the first 15 cycles of a stuck-seed run, rises with health_fail, then
    high on EVERY one of 100 consecutive settled cycles. (b) threshold path: a frozen full FIFO with
    thr=4 holds irq_o high on 100 consecutive cycles, until a pop drops the level below."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    await _write(bfm, TRNG_SEED, 0)
    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=1, thr=15))
    for _ in range(15):
        await _next_cycle(dut)
        assert int(dut.irq_o.value) == 0, "irq_o must stay low before the health trip"
    await _wait_status(dut, ST_HEALTH, ST_HEALTH, 200)
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 1, "irq_o must be asserted at the trip"
    for cycle in range(100):
        await _next_cycle(dut)
        assert int(dut.irq_o.value) == 1, f"irq_o dropped at cycle {cycle} of the health-path hold"

    await _enable_and_fill(dut, bfm)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=FIFO_DEPTH))
    for _ in range(3):
        await _next_cycle(dut)
    for cycle in range(100):
        await _next_cycle(dut)
        assert int(dut.irq_o.value) == 1, f"irq_o dropped at cycle {cycle} of the threshold-path hold"
    await _pop(dut, bfm)
    for _ in range(3):
        await _next_cycle(dut)
    assert int(dut.irq_o.value) == 0, "irq_o must fall once level < threshold"
    dut._log.info("irq_o level-held across 100 consecutive cycles on both paths -- confirmed")


@cocotb.test()
async def test_trng_disabled_is_inert(dut):
    """Disabled (CTRL[0] == 0) is inert: from reset, with IRQ enabled and a threshold of 1, a SEED
    write and 2000 idle cycles produce nothing -- STATUS stays exactly INSECURE, DATA reads 0,
    irq_o stays low. Then, D6: enable until the first word appears and disable again -- the words
    already buffered are RETAINED and FROZEN (level identical 1500 cycles later, STATUS unchanged,
    no further word accumulates), they still drive irq_o (irq_o depends on CTRL[1], not CTRL[0]),
    and they are the golden prefix."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    golden = TrngLfsrModel(DEFAULT_SEED).words(FIFO_DEPTH)

    await _write(bfm, TRNG_SEED, DEFAULT_SEED)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=1))
    for _ in range(40):
        await ClockCycles(dut.clk, 50)
        assert await _peek(dut, TRNG_STATUS) == ST_INSECURE, "a disabled TRNG accumulated state"
        assert int(dut.irq_o.value) == 0, "a disabled, empty TRNG raised irq_o"
    assert await _read(bfm, TRNG_DATA) == 0

    await _write(bfm, TRNG_CTRL, _ctrl(en=1, ie=1, thr=1))
    await _wait_status(dut, ST_READY, ST_READY, 3000)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=1))
    await ClockCycles(dut.clk, 4)
    lvl0 = await _level(dut, bfm, en=0)
    assert 1 <= lvl0 <= 2, f"expected 1-2 buffered words at disable, measured {lvl0}"
    stat0 = await _peek(dut, TRNG_STATUS)
    await _write(bfm, TRNG_CTRL, _ctrl(en=0, ie=1, thr=1))
    for _ in range(3):
        await _next_cycle(dut)
    assert int(dut.irq_o.value) == 1, "retained data must still drive irq_o while disabled (D6)"

    await ClockCycles(dut.clk, 1500)
    assert await _level(dut, bfm, en=0) == lvl0, "a disabled TRNG kept filling its FIFO"
    assert await _peek(dut, TRNG_STATUS) == stat0, "STATUS changed while disabled"
    words = [await _pop(dut, bfm) for _ in range(lvl0)]
    assert words == golden[:lvl0], "retained words are not the golden prefix"
    assert await _level(dut, bfm, en=0) == 0


@cocotb.test()
async def test_trng_distribution_sanity(dut):
    """*** SANITY, NOT A RANDOMNESS-QUALITY CLAIM. *** A von Neumann debiaser over LFSRs passes all
    of this trivially; these checks catch WIRING bugs, not weak entropy (the source is deterministic
    and INSECURE by design). Over 128 words = 4096 bits from the default seed (which must also
    equal the model word for word): total bit balance within +/-5 % of 50 % (2048 +/- 205 ones);
    every one of the 32 bit lanes balanced across the words (32..96 ones of 128 -- a stuck
    word-assembly bit fails this); no repeated word and no repeated 32-word window (a FIFO/pop bug
    returning the same word); and the debiaser ratio: with the consumer keeping up, the elapsed
    cycles for 4096 output bits are the raw samples consumed, which the model gives exactly and
    which must be ~4 raw samples per output bit (75 % discarded) -- a debiaser that kept both bits
    of a pair, or discarded the wrong fraction, misses the model-derived window."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    n = 128
    model = TrngLfsrModel(DEFAULT_SEED)
    golden = model.words(n)
    raw_needed = model.raw_consumed_for_words(n)

    await _write(bfm, TRNG_CTRL, _ctrl(en=1))  # now AT edge E
    t0 = get_sim_time(units="ns")
    words = await _collect(dut, bfm, n)
    elapsed = (get_sim_time(units="ns") - t0) / CLK_PERIOD_NS
    await _write(bfm, TRNG_CTRL, _ctrl(en=0))
    assert words == golden, "distribution run must equal the model word for word"

    bits = n * WORD_BITS
    ones = sum(bin(w).count("1") for w in words)
    assert abs(ones - bits // 2) <= 0.05 * bits, f"bit balance: {ones} ones of {bits}"
    for lane in range(WORD_BITS):
        lane_ones = sum((w >> lane) & 1 for w in words)
        assert 32 <= lane_ones <= 96, f"bit lane {lane}: {lane_ones} ones of {n} words"
    assert len(set(words)) == n, "repeated 32-bit word in the output"
    windows = [tuple(words[i : i + 32]) for i in range(n - 32 + 1)]
    assert len(set(windows)) == len(windows), "a 32-word window repeats"

    per_bit = elapsed / bits
    assert 3.5 <= per_bit <= 4.5, f"{per_bit:.2f} raw samples per output bit, expected ~4 (von Neumann)"
    assert raw_needed <= elapsed <= raw_needed + 64, (
        f"{elapsed:.0f} cycles for {n} words, model needs {raw_needed} raw samples "
        f"(window [{raw_needed}, {raw_needed + 64}])"
    )
    stat = await _peek(dut, TRNG_STATUS)
    assert not stat & ST_HEALTH
