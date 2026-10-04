"""test_npu.py -- Phase 6c cocotb L1 verification for npu_top (rtl/npu/npu_top.sv +
rtl/npu/npu_mac_array.sv + rtl/npu/npu_weight_mem.sv, bead claude_verilog_test-f7vs.11,
docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6c -- NPU", whose register map, software contract and
eight acceptance criteria this suite is written to prove).

STRICT TDD: the RTL DID NOT EXIST when this suite was written.  This is step 2 of the mandated
workflow ("the verification orchestrator runs before the RTL orchestrator"): `make npu` /
`make npu_lint` are EXPECTED to fail to elaborate (npu_top not found) until the three RTL files
match the contract below.  The assertions are derived from the plan's register map, its software
contract, its acceptance criteria and the golden model tb/models/npu_model.py (standard library
only; requirements.txt gains nothing) -- never from reading an FSM.  Every arithmetic expectation
is either (a) a HAND-COMPUTED literal written into this file, independent of the model, or (b) the
model's output; the model is itself pinned by tb/tests/test_npu_model.py.

DUT: tb_npu -- ONE wrapper, TWO npu_top instances sharing clk / rst_n, each with its own flat APB4
face selected by a signal-name prefix (APB4Master(dut, prefix, ...)):

    ""      u_dut      the build under test (ADDR_W=12, WEIGHT_WORDS=1024, GRID=4, EN_NPU=1)
    "off_"  u_dut_off  EN_NPU = 0   (the SoC tie-off arm: APB must still terminate cleanly)

npu_top has NO asynchronous input (clk / rst_n / APB4 in, irq_o out), so there is no CDC, no
cdc_2ff_sync and no SDC exception to test.

Register map (npu_top.sv, ADDR_W=12, N_REGS=16; byte offset = word index * 4):
  0x00 CTRL      [RW]  [0] RELU_EN, [3] IRQ_EN.  [2] START is W1P: a WRITE-SNOOP pulse, not a stored
                       bit -- it reads 0 forever (stored mask 0x09).
  0x04 STATUS    [RO]  [0] busy [1] done [2] ain_full [3] ain_empty [4] aout_valid [5] aout_full
                       [6] cfg_rejected (sticky).  Reset value 0x08 (the AIN FIFO is empty).
  0x08 WADDR     [RW]  [9:0] weight-SRAM word address; auto-increments on every WDATA write
  0x0C WDATA     [WO]  4 packed INT8 weights -> SRAM[WADDR]; reads 0 forever
  0x10 TILEBASE  [RW]  [9:0] SRAM word address of the first weight word of the next inference
  0x14 KLEN      [RW]  [5:0] number of 4-element chunks (each = 4 SRAM words + 1 AIN word)
  0x18 SCALE     [RW]  [15:0] requantise multiplier, [20:16] right shift
  0x1C AIN       [WO]  4 packed INT8 activations -> AIN FIFO (depth 4); reads 0 forever
  0x20 AOUT      [RO]  head of the AOUT FIFO (depth 4); a READ POPS it
  0x24 IRQ_STAT  [RO]  [0] sticky done (the SAME flop as STATUS[1])
  0x28 IRQ_CLR   [WO]  W1C by write-snoop: [0] clears done, [1] clears cfg_rejected
  0x2C-0x3C reserved (read 0, writes dropped);  word index >= 16 (0x40..0xFFC): read 0, writes
                       dropped, pslverr stays 0 (the register bank's out-of-range policy)

BYTE ORDER / ARITHMETIC (the model's contract, restated because the RTL implements it).
  * LITTLE-ENDIAN lanes for WDATA, AIN and AOUT alike: element / lane 0 is bits [7:0], lane 3 is
    bits [31:24]; each byte a two's-complement INT8.
  * y[j] = requant( SUM_c SUM_i W[c][i][j] * a[c][i] ); one chunk = one AIN word (a[c][0..3]) plus
    the four SRAM words SRAM[TILEBASE + 4c + i] (row i, lane j in byte j).
  * requant(acc) = sat_int8( (acc * SCALE[15:0]) >> SCALE[20:16] ), the multiplier UNSIGNED, the
    shift an ARITHMETIC shift = FLOOR (not round-half-up, not toward zero), the product NOT
    truncated to 32 bits; then max(0, .) if CTRL[0].
  * The INT32 accumulator saturates, but |acc| <= 2**22 for every legal run, so it never fires.
  * Accumulators are zeroed at START.

DECISIONS the spec left open (or resolved inside the contract).  Writing the tests first is what
pins them, so they are asserted HERE and the RTL implements what this file asserts:

  D1. RELU_EN / IRQ_EN ARE NEVER CHANGED IN THE SAME TRANSFER AS START.  The contract derives
      relu from the bank register, whose value during the START write's own ACCESS cycle is the
      PRE-write one (see crypto_accel's identical D1).  The suite writes CTRL (no start) first and
      CTRL|START second (`_Dev.start`), and does NOT pin the single-write behaviour.
  D2. THE WEIGHT SRAM HAS NO READBACK, so weights are proven ONLY by inference results.  Every
      test loads every weight word it consumes (SRAM content is not reset, and the suite never
      relies on an unloaded word).  `_Dev.mem` mirrors what the suite loaded.
  D3. AIN PROTOCOL.  The AIN FIFO is depth 4.  A START with fewer than KLEN AIN words queued is
      STARVED, not illegal: the engine stays busy (done 0) until KLEN words have been consumed, so
      software may START first and stream AIN afterwards (KLEN > 4 REQUIRES it).  An AIN write
      while the FIFO is FULL is DROPPED silently (FIFO unchanged, no cfg_rejected).
      test_npu_ain_backpressure, test_npu_starved_start_waits_for_ain.
  D4. AOUT.  Depth 4.  An empty AOUT reads 0 and a read of it pops nothing (no underflow, no
      stale duplicate).  The result is visible no later than done: whenever STATUS.done reads 1
      after a legal run STATUS.aout_valid is already 1, so `while (!done); read AOUT` is safe.
      test_npu_aout_pops_on_read, test_npu_aout_empty_reads_zero_no_stale_duplicate.
  D5. LEGAL-RUN LATENCY IS NOT PINNED, but it must be DETERMINISTIC: identical runs with the AIN
      FIFO pre-filled take the same number of edges N (counted from the START write's ACCESS edge E,
      inclusive), and busy is high on every edge 1..N-1.  The set-beats-clear alignment calibrates
      itself on N.  The ILLEGAL path IS pinned: N = 2 exactly.
  D6. ILLEGAL START (KLEN == 0, KLEN > 63 as stored, or TILEBASE + 4*KLEN > 1024): busy for one
      edge, done on the second, cfg_rejected latched, NO AOUT push, the bus never stalls (pready is
      sampled high on every edge).  The AIN FIFO content around an illegal start is not specified;
      the suite never queues AIN words before one.
  D7. cfg_rejected CLEARS on reset, on IRQ_CLR[1] and on an accepted WDATA write.  IRQ_CLR[0] does
      not touch it and IRQ_CLR[1] does not touch done.  (Whether an accepted WADDR write clears it
      is NOT pinned.)
  D8. A WADDR or WDATA WRITE WHILE BUSY IS REJECTED: WADDR is unchanged, nothing reaches the SRAM,
      cfg_rejected latches.
  D9. WADDR IS A 10-BIT COUNTER: the auto-increment past 1023 wraps to 0 and WADDR never reads
      outside [9:0] (the bank's HW write bypasses WMASK, so the RTL must mask the increment).
  D10. KLEN[5:0] CANNOT HOLD 64.  The plan says "1..64"; the register holds 0..63, writing 64
      stores 0, and START with KLEN == 0 is illegal.  The register-reachable maximum is 63 and the
      suite tests 63.  FLAGGED to the plan's owner -- the model supports 1..64 arithmetic.
  D11. SAME-CYCLE WADDR COLLISION.  The auto-increment fires on the WDATA write's own cycle and one
      APB master cannot complete two transfers in one cycle (the earliest next ACCESS is E + 2), so
      a literal same-cycle SW-vs-HW WADDR collision is UNREACHABLE at L1.  What is provable, and
      pinned: a WADDR write issued BACK-TO-BACK after a WDATA write lands exactly (never old + 1,
      never SW + 1), and the next WDATA goes to that address.  test_npu_waddr_sw_write_wins.
  D12. THE WEIGHT_WORDS ELABORATION GUARD: any value other than 1024 is a $fatal naming
      WEIGHT_WORDS (plan Sec.7, "a parameter sweep cannot silently fall back to flops").  Lint-only.
  D13. Partial-strobe WDATA / AIN / START writes, START while busy (legal and illegal), a
      zero-strobe weight write while busy, done being sticky across a new START, and AOUT-FIFO
      overflow (a fifth unpopped result) ARE pinned, each by its own test (start_partial_strobe_
      ignored, partial_strobe_wdata_ain_dropped, start_while_busy_ignored, zero_strobe_weight_
      write_while_busy_not_rejected, done_sticky_across_start, aout_overflow_drops_fifth).  The
      shared helpers still clear done before a START and pop every result they do not
      deliberately queue, so these tests deliberately bypass that convention.  They were added
      after a 65-mutant campaign on rtl/npu left exactly these behaviours unkilled.

CYCLE-SAMPLING HAZARD (learned on PWM / WDT / TRNG / I2C / CRYPTO): a value read straight after
`await RisingEdge` is the PRE-edge value.  Every internal-state sample therefore goes RisingEdge
FIRST and then settles through Timer(1, "step") (inside `_Dev.peek`, which also points an idle
bus's paddr at the word so the sample is SIDE-EFFECT FREE -- a psel = 0 bus never pops AOUT).
Plain APB reads are used only where the side effect (the AOUT pop) is the point.

Tests (grouped; the name states the behaviour):
  register file   reset_defaults_and_reserved, wmask_enforcement, ctrl_start_reads_zero,
                  wdata_ain_irqclr_read_zero_forever, scale_strobe_merging
  weights         waddr_autoincrement, waddr_wraps_at_1023, waddr_sw_write_wins
  inference       klen1_hand_vectors, multichunk_hand_vector, multichunk_random_vs_model,
                  klen_register_max_63, tilebase_selects_tile_and_accumulators_clear
  requantise      relu_on_off, scale_hand_table, scale_floor_rounding, scale_random_sweep,
                  scale_product_not_32_bit
  FIFOs           aout_pops_on_read, aout_empty_reads_zero_no_stale_duplicate, ain_backpressure,
                  starved_start_waits_for_ain
  handshake       irq_level_held_and_masked, set_beats_same_cycle_clear, status_not_stale,
                  reset_mid_operation
  illegal / reject illegal_start_is_hang_free, legal_boundaries_accepted, cfg_rejected_clear_paths,
                  weight_write_while_busy_is_rejected
  strobes / START start_partial_strobe_ignored, partial_strobe_wdata_ain_dropped,
                  start_while_busy_ignored, zero_strobe_weight_write_while_busy_not_rejected,
                  done_sticky_across_start, aout_overflow_drops_fifth
  EN_NPU = 0      en_npu_off_terminates_cleanly
  elaboration     elaboration_guard_rejects_bad_weight_words, elaboration_legal_configs_pass
39 tests in all.
"""

import random
import subprocess
import sys
import tempfile
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb.utils import get_sim_time

_TB_DIR = Path(__file__).resolve().parent.parent
if str(_TB_DIR) not in sys.path:
    sys.path.insert(0, str(_TB_DIR))
_PROJ_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

from bfm.apb4_master import APB4Master  # noqa: E402

from tb.models import npu_model as npu  # noqa: E402

CLK_PERIOD_NS = 10  # 100 MHz -- matches SoC reference clock (same convention as test_crypto.py)

# -- register byte offsets ----------------------------------------------------
CTRL = 0x00
STATUS = 0x04
WADDR = 0x08
WDATA = 0x0C
TILEBASE = 0x10
KLEN = 0x14
SCALE = 0x18
AIN = 0x1C
AOUT = 0x20
IRQ_STAT = 0x24
IRQ_CLR = 0x28
RESERVED = (0x2C, 0x30, 0x34, 0x38, 0x3C)
OUT_OF_RANGE = (0x40, 0x44, 0x80, 0x400, 0xFFC)  # word index >= 16
N_REGS = 16

# -- CTRL fields -------------------------------------------------------------
CTRL_RELU = 0x1
CTRL_START = 0x4
CTRL_IE = 0x8

# -- STATUS bits -------------------------------------------------------------
ST_BUSY = 0x01
ST_DONE = 0x02
ST_AIN_FULL = 0x04
ST_AIN_EMPTY = 0x08
ST_AOUT_VALID = 0x10
ST_AOUT_FULL = 0x20
ST_REJ = 0x40
STATUS_RESET = ST_AIN_EMPTY

CLR_DONE, CLR_REJ = 0x1, 0x2

AIN_DEPTH = 4
AOUT_DEPTH = 4
N_ILLEGAL = 2  # frozen contract: the zero-length path

# Writable-bit masks (plan Sec.7 WMASK line)
WMASKS = {
    CTRL: 0x0000_0009,
    WADDR: 0x0000_03FF,
    TILEBASE: 0x0000_03FF,
    KLEN: 0x0000_003F,
    SCALE: 0x001F_FFFF,
}

# -- HAND-COMPUTED vectors, written INDEPENDENTLY of the model (double-pin) -----------------------
# Identity tile (row i is the unit vector e_i): y == a.
IDENT_ROWS = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
IDENT_A = [1, -2, 3, -4]  # bytes 01 FE 03 FC
IDENT_Y_WORD = 0xFC03FE01  # y = (1, -2, 3, -4)
IDENT_Y_RELU_WORD = 0x00030001  # y = (1, 0, 3, 0)
# Dense tile: y0 = 1*1+5*2+(-1)*3+10*4 = 48   y1 = 2*1+6*2+(-2)*3+0*4 = 8
#             y2 = 3*1+7*2+(-3)*3+(-10)*4 = -32   y3 = 4*1+8*2+(-4)*3+5*4 = 28
DENSE_ROWS = [[1, 2, 3, 4], [5, 6, 7, 8], [-1, -2, -3, -4], [10, 0, -10, 5]]
DENSE_A = [1, 2, 3, 4]
DENSE_TABLE = {  # (mult, shift, relu) -> AOUT word, lanes (y0, y1, y2, y3) low byte first
    (1, 0, 0): 0x1CE00830,  # ( 48,  8, -32, 28)
    (1, 0, 1): 0x1C000830,  # ( 48,  8,   0, 28)  ReLU zeroes only the negative lane
    (1, 1, 0): 0x0EF00418,  # ( 24,  4, -16, 14)  >> 1
    (3, 2, 0): 0x15E80624,  # ( 36,  6, -24, 21)  144>>2, 24>>2, -96>>2, 84>>2
    (5, 0, 0): 0x7F80287F,  # (127, 40,-128,127)  240->127, -160->-128, 140->127  (both rails)
    (0, 0, 0): 0x00000000,  # zero multiplier
    (1, 31, 0): 0x00FF0000,  # (  0,  0,  -1,  0)  floor: -32 >> 31 == -1
    (1, 31, 1): 0x00000000,
}
# Two chunks (the dense tile twice, a1 = e0 so chunk 1 adds row 0 verbatim): (49, 10, -29, 32)
TWO_CHUNK_Y_WORD = 0x20E30A31
# Rounding discriminators through the identity tile with a = (3, -1, -3, 5), scale 1 >> 1:
# floor -> (1, -1, -2, 2) = 01 FF FE 02.   (half-up would be (2, 0, -1, 3); toward-zero (1,0,-1,2))
FLOOR_A = [3, -1, -3, 5]
FLOOR_Y_WORD = 0x02FEFF01
# KLEN = 63, every weight and activation -128: acc = 63 * 4 * 16384 = 4_128_768 on every lane.
# KLEN = 63, weights -128, activations +127: acc = 63 * 4 * (-16256) = -4_096_512.
WIDE_NEG_TABLE = {  # (mult, shift) -> AOUT word, weights -128, a = -128
    (65535, 0): 0x7F7F7F7F,  # a 32-bit product would wrap to -4_128_768 -> -128
    (65535, 31): 0x7D7D7D7D,  # 4_128_768 * 65535 >> 31 = 125.998 -> 125
    (1, 16): 0x3F3F3F3F,  # exactly 63
    (1, 15): 0x7E7E7E7E,  # exactly 126
    (1, 22): 0x00000000,  # 0.98 -> 0
}
WIDE_POS_TABLE = {  # weights -128, a = +127
    (65535, 0): 0x80808080,  # -128 rail
    (1, 15): 0x82828282,  # -125.016 -> floor -126
    (1, 16): 0xC1C1C1C1,  # -62.5 -> floor -63
}

# -- module-level task handle list (guard against cross-test coroutine leakage) -------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def npu_test(fn):
    """cocotb.test with a 10 ms simulated-time ceiling: a bus hang fails instead of spinning."""
    return cocotb.test(timeout_time=10, timeout_unit="ms")(fn)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _ctrl(relu: int = 0, ie: int = 0, start: int = 0) -> int:
    """Compose a CTRL value."""
    return relu | (start << 2) | (ie << 3)


def _pack(vals) -> int:
    return npu.pack_word(vals)


def _scale(mult: int, shift: int) -> int:
    return npu.make_scale(mult, shift)


def _now_cycle() -> int:
    """Absolute clock-cycle index (sim time / period); only differences are meaningful."""
    return int(get_sim_time(units="ns")) // CLK_PERIOD_NS


async def _settle() -> None:
    """Let the post-edge state settle (see the CYCLE-SAMPLING HAZARD note)."""
    await Timer(1, units="step")


def _rand_row(rng: random.Random) -> list[int]:
    return [rng.randint(-128, 127) for _ in range(4)]


# ---------------------------------------------------------------------------
# One DUT instance's APB4 face + driver helpers
# ---------------------------------------------------------------------------
class _Dev:
    """Driver for one npu_top instance of tb_npu (prefix "" = the primary build)."""

    def __init__(self, dut, prefix: str, name: str):
        self.dut = dut
        self.name = name
        self.apb = APB4Master(dut, prefix, dut.clk)
        for sig in (
            "psel",
            "penable",
            "pwrite",
            "paddr",
            "pwdata",
            "pstrb",
            "prdata",
            "pready",
            "pslverr",
            "irq_o",
        ):
            setattr(self, sig, getattr(dut, prefix + sig))
        self.mem = npu.blank_weight_mem()  # D2: mirror of the weight words the suite has loaded

    def __repr__(self) -> str:
        return f"<npu {self.name}>"

    # -- raw access --------------------------------------------------------
    async def w(self, addr: int, data: int, strb: int = 0xF) -> None:
        ok = await self.apb.write(addr, data, strb)
        assert ok, f"[{self.name}] write 0x{addr:03x} returned SLVERR (this bus never SLVERRs)"

    async def r(self, addr: int) -> int:
        """A real APB read.  NB: a read of AOUT POPS the AOUT FIFO."""
        data, ok = await self.apb.read(addr)
        assert ok, f"[{self.name}] read 0x{addr:03x} returned SLVERR (this bus never SLVERRs)"
        return data

    async def peek(self, addr: int) -> int:
        """Side-effect-free live register sample: point the idle bus's combinational prdata at
        `addr`, settle one simulator step, read (see the CYCLE-SAMPLING HAZARD note).  psel stays
        0, so peeking AOUT never pops it."""
        self.pwrite.value = 0
        self.paddr.value = addr
        await _settle()
        return int(self.prdata.value)

    async def next_cycle(self) -> None:
        """Advance one edge and return in its settled post-edge state."""
        await RisingEdge(self.dut.clk)
        await _settle()

    async def timed_write(self, rel: int, addr: int, data: int, strb: int = 0xF) -> None:
        """APB write whose ACCESS phase is sampled at edge E + `rel`, where E is the edge the
        immediately preceding `_Dev.start` returned on (call this with NO intervening await).
        Drives the raw SETUP / ACCESS phases so the write can be aligned with an internal edge."""
        assert rel >= 2, "a write needs a SETUP edge before its ACCESS edge"
        if rel > 2:
            await ClockCycles(self.dut.clk, rel - 2)
        self.psel.value = 1
        self.penable.value = 0
        self.pwrite.value = 1
        self.paddr.value = addr
        self.pwdata.value = data
        self.pstrb.value = strb
        await RisingEdge(self.dut.clk)  # SETUP sampled at E + rel - 1
        self.penable.value = 1
        await RisingEdge(self.dut.clk)  # ACCESS sampled at E + rel
        self.psel.value = 0
        self.penable.value = 0
        self.pwrite.value = 0
        self.pstrb.value = 0xF

    # -- register-level helpers ----------------------------------------------
    async def status(self) -> int:
        return await self.peek(STATUS)

    async def clear_done(self) -> None:
        await self.w(IRQ_CLR, CLR_DONE)

    async def clear_rej(self) -> None:
        await self.w(IRQ_CLR, CLR_REJ)

    async def load_words(self, base: int, words) -> None:
        """Load raw 32-bit weight words from SRAM address `base` (device must be idle)."""
        await self.w(WADDR, base)
        for k, wd in enumerate(words):
            await self.w(WDATA, wd)
            self.mem[(base + k) % npu.WEIGHT_WORDS] = wd

    async def load_tile(self, base: int, rows) -> None:
        """Load one 4 x 4 INT8 tile (row i -> word base + i)."""
        await self.load_words(base, [_pack(r) for r in rows])

    async def configure(self, tilebase: int, klen: int, scale: int, relu: int = 0, ie: int = 0):
        await self.w(TILEBASE, tilebase)
        await self.w(KLEN, klen)
        await self.w(SCALE, scale)
        await self.w(CTRL, _ctrl(relu, ie))  # D1: mode bits first, START in a separate transfer

    async def start(self, relu: int = 0, ie: int = 0) -> None:
        """Write CTRL with START (same RELU / IE bits as already stored).  Returns right after
        edge E, the START write's ACCESS edge."""
        await self.w(CTRL, _ctrl(relu, ie, start=1))

    async def push_ain(self, words) -> None:
        for wd in words:
            await self.w(AIN, wd)

    def expect(self, tilebase: int, ains, scale: int, relu: int) -> int:
        """The model's AOUT word for the weights the suite has loaded."""
        return npu.infer(self.mem, tilebase, list(ains), scale, bool(relu))

    # -- observation ---------------------------------------------------------
    async def wait_done(self, pending, budget: int = 20000) -> tuple[int, int]:
        """Sample STATUS each settled edge from the one right after the START edge E, feeding
        `pending` AIN words whenever the FIFO has room, until done.  Returns (N, STATUS at done)
        where N counts edges from E INCLUSIVE."""
        pending = list(pending)
        e_cycle = _now_cycle()
        for _ in range(budget):
            st = await self.peek(STATUS)
            if st & ST_DONE:
                assert not pending, f"[{self.name}] done with {len(pending)} AIN words unconsumed"
                return _now_cycle() - e_cycle + 1, st
            if pending and not st & ST_AIN_FULL:
                await self.w(AIN, pending.pop(0))
            else:
                await self.next_cycle()
        raise AssertionError(f"[{self.name}] STATUS.done never set within {budget} samples")

    async def trace(self, budget: int = 4000) -> list[tuple[int, int, int, int]]:
        """Per-edge samples (STATUS, IRQ_STAT, irq_o, pready) starting right after edge E (sample
        1) and ending with the first sample whose STATUS.done is set; len() == N.  Requires done
        == 0 beforehand and no intervening await since `start`."""
        out: list[tuple[int, int, int, int]] = []
        for k in range(budget):
            if k:
                await RisingEdge(self.dut.clk)
            st = await self.peek(STATUS)
            ist = await self.peek(IRQ_STAT)
            out.append((st, ist, int(self.irq_o.value), int(self.pready.value)))
            if st & ST_DONE:
                return out
        raise AssertionError(f"[{self.name}] STATUS.done never set within {budget} edges")

    async def infer(
        self, tilebase: int, ains, scale: int, relu: int = 0, ie: int = 0, pop: bool = True
    ) -> int:
        """One whole inference with the AIN words streamed as the FIFO drains; returns the AOUT
        word (popped by a real read when `pop`, else peeked).  Asserts D4's done-implies-result
        and that AOUT's peek matches the pop."""
        await self.configure(tilebase, len(ains), scale, relu, ie)
        await self.clear_done()
        pre = list(ains[:AIN_DEPTH])
        await self.push_ain(pre)
        await self.start(relu, ie)
        _n, st = await self.wait_done(ains[AIN_DEPTH:])
        assert st & ST_AOUT_VALID, f"[{self.name}] done with no AOUT result (STATUS=0x{st:02x})"
        assert not st & ST_BUSY, f"[{self.name}] busy and done together (STATUS=0x{st:02x})"
        head = await self.peek(AOUT)
        if not pop:
            return head
        got = await self.r(AOUT)
        assert got == head, f"[{self.name}] AOUT read 0x{got:08x} != live head 0x{head:08x}"
        return got

    async def run_traced(self, tilebase, ains, scale, relu=0, ie=0):
        """configure, clear done, pre-fill (<= 4 words), start, trace to completion."""
        assert len(ains) <= AIN_DEPTH
        await self.configure(tilebase, len(ains), scale, relu, ie)
        await self.clear_done()
        await self.push_ain(ains)
        await self.start(relu, ie)
        return await self.trace()


class _Rig:
    """The two instances of tb_npu."""

    def __init__(self, dut):
        self.main = _Dev(dut, "", "main")
        self.off = _Dev(dut, "off_", "off")
        self.all = (self.main, self.off)


async def _reset(dut, rig: _Rig, cycles: int = 4) -> None:
    """Synchronous reset with every bus idle (also usable mid-test to get a clean state)."""
    dut.rst_n.value = 0
    for d in rig.all:
        d.psel.value = 0
        d.penable.value = 0
        d.pwrite.value = 0
        d.paddr.value = 0
        d.pwdata.value = 0
        d.pstrb.value = 0xF
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def _start_clock_and_reset(dut) -> _Rig:
    """Start the 100 MHz clock, build the two drivers and reset the DUTs."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)
    dut.rst_n.value = 0
    rig = _Rig(dut)
    await _reset(dut, rig)
    return rig


def _check_pattern(dev: _Dev, tr, n_expected: int | None, what: str) -> int:
    """Assert the busy/done pattern of a trace: busy=1/done=0 for edges 1..N-1, busy=0/done=1 on
    edge N, IRQ_STAT[0] mirroring STATUS[1] throughout, pready high on every edge, and
    N == n_expected when given.  Returns N."""
    n = len(tr)
    if n_expected is not None:
        assert n == n_expected, (
            f"[{dev.name}] {what}: done after {n} edges, contract says {n_expected}"
        )
    for k, (st, ist, _irq, rdy) in enumerate(tr, start=1):
        last = k == n
        want = ST_DONE if last else ST_BUSY
        assert st & (ST_BUSY | ST_DONE) == want, (
            f"[{dev.name}] {what}: STATUS=0x{st:02x} after edge {k}/{n}, "
            f"expected (busy,done) bits 0x{want:x}"
        )
        assert ist == (st >> 1) & 1, (
            f"[{dev.name}] {what}: IRQ_STAT=0x{ist:x} != STATUS.done after edge {k}/{n} "
            f"(one flop, two words)"
        )
        assert rdy == 1, f"[{dev.name}] {what}: pready low after edge {k}/{n} (bus stalled)"
    return n


# ===========================================================================
# Register file
# ===========================================================================
@npu_test
async def test_npu_reset_defaults_and_reserved(dut):
    """Every one of the 16 words reads 0 after reset on both builds EXCEPT STATUS, which reads
    0x08 on the real build (ain_empty is the only bit set: not busy, not done, nothing queued,
    nothing rejected); irq_o is low and the block stays quiescent for 200 idle cycles.  The
    reserved words 0x2C-0x3C read 0 and are UNWRITABLE, and so is every word index >= 16 (read 0,
    write dropped, pslverr stays 0) -- none of those writes disturbs STATUS or any register."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    for i in range(N_REGS):
        v = await d.r(4 * i)
        want = STATUS_RESET if 4 * i == STATUS else 0
        assert v == want, f"word {i} (0x{4 * i:03x}) reset value 0x{v:08x}, expected 0x{want:x}"
    assert int(d.irq_o.value) == 0, "irq_o high out of reset"
    for _ in range(200):
        await d.next_cycle()
        assert await d.peek(STATUS) == STATUS_RESET, "STATUS moved with the block idle"
        assert int(d.irq_o.value) == 0
    for addr in RESERVED + OUT_OF_RANGE:
        await d.w(addr, 0xFFFFFFFF)
        v = await d.r(addr)
        assert v == 0, f"0x{addr:03x} read 0x{v:08x} after a write; reserved / OOR must read 0"
    for i in range(N_REGS):
        v = await d.peek(4 * i)
        want = STATUS_RESET if 4 * i == STATUS else 0
        assert v == want, f"reserved/OOR write disturbed word {i}: 0x{v:08x}"


@npu_test
async def test_npu_wmask_enforcement(dut):
    """Each RW word keeps exactly its WMASK bits and no others: CTRL 0x09 (bit 2 NEVER sticks),
    WADDR / TILEBASE [9:0], KLEN [5:0], SCALE [20:0], with 1s, alternating and zero patterns.
    KLEN = 64 stores 0 (D10: the register cannot hold 64).  (CTRL patterns have bit 2 cleared so
    the write cannot fire START; that bit's own test is test_npu_ctrl_start_reads_zero.)"""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    for addr, mask in WMASKS.items():
        for pat in (0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0xFFFF0000, 0x0000FFFF, 0x12345678, 0):
            val = pat & ~CTRL_START if addr == CTRL else pat
            await d.w(addr, val)
            got = await d.r(addr)
            assert got == val & mask, (
                f"word 0x{addr:02x}: wrote 0x{val:08x}, read 0x{got:08x}, "
                f"expected 0x{val & mask:08x}"
            )
    await d.w(KLEN, 64)
    assert await d.r(KLEN) == 0, "KLEN = 64 must store 0 (6-bit field)"
    await d.w(KLEN, 63)
    assert await d.r(KLEN) == 63
    # the writes above never raised done, rejection or an interrupt
    assert await d.peek(STATUS) & (ST_DONE | ST_REJ | ST_BUSY) == 0
    # every RO / WO word is unaffected by writing to its neighbours
    assert await d.peek(STATUS) == STATUS_RESET
    for addr in (WDATA, AIN, AOUT, IRQ_STAT, IRQ_CLR):
        assert await d.r(addr) == 0, f"0x{addr:02x} disturbed by writes to its neighbours"


@npu_test
async def test_npu_ctrl_start_reads_zero(dut):
    """CTRL[2] START is a write-snoop PULSE, not a stored bit: it reads 0 immediately and on every
    later cycle, while the stored bits next to it stick.  START with the reset KLEN == 0 is an
    illegal start (the cleanest side-effect-free way to fire the pulse): it takes the 2-cycle path,
    proving the pulse was decoded, and CTRL still reads 0x09 on every sampled edge."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.w(CTRL, CTRL_RELU | CTRL_IE)
    assert await d.peek(CTRL) == 0x9
    await d.clear_done()
    await d.start(relu=1, ie=1)  # CTRL <- 0xD, KLEN == 0
    seen = []
    for _ in range(8):
        seen.append(await d.peek(CTRL))
        await d.next_cycle()
    assert seen == [0x9] * 8, f"CTRL read {[hex(v) for v in seen]}; START must never be stored"
    st = await d.peek(STATUS)
    assert st & ST_DONE and st & ST_REJ, f"START pulse not decoded: STATUS=0x{st:02x}"


@npu_test
async def test_npu_wdata_ain_irqclr_read_zero_forever(dut):
    """WDATA, AIN and IRQ_CLR are write-snoop only: they read 0 before, between and after any
    number of writes (live peek AND real read), so a stored copy can never leak out.  Each write
    is also shown to have TAKEN EFFECT (WDATA advances WADDR, AIN fills the FIFO, IRQ_CLR[0] clears
    a set done), so the zeros cannot come from a dead register."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0x7E50)
    await d.configure(0, 0, _scale(1, 0))  # KLEN == 0: a START raises done (illegal path)
    for k in range(6):
        await d.w(WDATA, rng.getrandbits(32) | 1)
        assert await d.peek(WADDR) == k + 1, "WDATA write had no effect"
        if k < AIN_DEPTH:  # a fifth push would hit the full FIFO (D3), keep the test about reads
            await d.w(AIN, rng.getrandbits(32) | 1)
            assert not await d.peek(STATUS) & ST_AIN_EMPTY, "AIN write had no effect"
        await d.start()
        await d.trace()
        assert await d.peek(STATUS) & ST_DONE
        await d.w(IRQ_CLR, rng.getrandbits(32) | CLR_DONE)
        assert not await d.peek(STATUS) & ST_DONE, "IRQ_CLR write had no effect"
        for addr in (WDATA, AIN, IRQ_CLR):
            assert await d.peek(addr) == 0, f"0x{addr:02x} peeked non-zero after write {k}"
            assert await d.r(addr) == 0, f"0x{addr:02x} read non-zero after write {k}"
    for _ in range(20):
        await d.next_cycle()
        for addr in (WDATA, AIN, IRQ_CLR):
            assert await d.peek(addr) == 0


@npu_test
async def test_npu_scale_strobe_merging(dut):
    """Byte strobes merge into the masked register exactly as the bank does: SCALE written one byte
    lane at a time assembles 0x001F_xxxx and the bits above [20:0] never appear."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.w(SCALE, 0)
    await d.w(SCALE, 0xFFFFFFFF, strb=0b0100)  # byte 2 only: [23:16] -> [20:16]
    assert await d.r(SCALE) == 0x001F0000
    await d.w(SCALE, 0xFFFFFFFF, strb=0b0011)  # bytes 0-1
    assert await d.r(SCALE) == 0x001FFFFF
    await d.w(SCALE, 0x00000000, strb=0b0001)  # clear byte 0 only
    assert await d.r(SCALE) == 0x001FFF00
    await d.w(SCALE, 0xFFFFFFFF, strb=0b1000)  # byte 3: entirely above the mask
    assert await d.r(SCALE) == 0x001FFF00
    await d.w(SCALE, 0xFFFFFFFF, strb=0b0000)  # no lane selected: no change
    assert await d.r(SCALE) == 0x001FFF00


# ===========================================================================
# Weight loading
# ===========================================================================
@npu_test
async def test_npu_waddr_autoincrement(dut):
    """WADDR advances by EXACTLY 1 per WDATA write (checked after every write, from a non-zero
    start), a write to WADDR repositions it, and the words land where WADDR pointed: a tile
    loaded at 200 and another at 300 both infer correctly (weights are observable only that way,
    D2)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.w(WADDR, 200)
    assert await d.peek(WADDR) == 200
    for k, row in enumerate(DENSE_ROWS):
        await d.w(WDATA, _pack(row))
        d.mem[200 + k] = _pack(row)
        assert await d.peek(WADDR) == 201 + k, f"WADDR after WDATA write {k + 1}"
    await d.load_tile(300, IDENT_ROWS)
    assert await d.peek(WADDR) == 304
    got = await d.infer(200, [_pack(DENSE_A)], _scale(1, 0))
    assert got == DENSE_TABLE[(1, 0, 0)], f"tile at 200: 0x{got:08x}"
    got = await d.infer(300, [_pack(IDENT_A)], _scale(1, 0))
    assert got == IDENT_Y_WORD, f"tile at 300: 0x{got:08x}"
    # a WDATA write does not disturb the other RW registers
    assert await d.peek(TILEBASE) == 300 and await d.peek(KLEN) == 1


@npu_test
async def test_npu_waddr_wraps_at_1023(dut):
    """D9: the auto-increment past 1023 wraps to 0 and WADDR never reads above 0x3FF; the word
    written at 1023 is a real word (a tile at 1020 uses it) and the wrap lands the next word at
    0."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.w(WADDR, 1020)
    rows = DENSE_ROWS
    for k, row in enumerate(rows):
        await d.w(WDATA, _pack(row))
        d.mem[1020 + k] = _pack(row)
        v = await d.peek(WADDR)
        assert v & ~0x3FF == 0, f"WADDR read 0x{v:x}: bits above [9:0] must never appear"
        assert v == (1021 + k) % 1024, f"WADDR = {v} after writing word {1020 + k}"
    assert await d.peek(WADDR) == 0, "WADDR must wrap 1023 -> 0"
    await d.w(WDATA, _pack(IDENT_ROWS[0]))  # this one lands at word 0
    d.mem[0] = _pack(IDENT_ROWS[0])
    assert await d.peek(WADDR) == 1
    got = await d.infer(1020, [_pack(DENSE_A)], _scale(1, 0))
    assert got == DENSE_TABLE[(1, 0, 0)], "the tile ending at word 1023 did not infer correctly"
    assert await d.peek(WADDR) == 1, "WADDR is unrelated to inference"


@npu_test
async def test_npu_waddr_sw_write_wins(dut):
    """D11: a WADDR write issued BACK-TO-BACK after a WDATA write lands exactly -- WADDR reads the
    software value, never old + 1 and never software + 1 -- and the next WDATA goes there.  A
    literal same-cycle collision is unreachable from one APB master (the earliest next ACCESS is
    E + 2); this is the strongest L1 evidence, and it covers a delayed increment too.  The tile is
    scattered out of order (rows 0, 2, 1, 3) so any misplaced word breaks the inference."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    base = 500
    words = [_pack(r) for r in DENSE_ROWS]
    order = [0, 2, 1, 3]
    await d.w(WADDR, base + order[0])
    for k, row_idx in enumerate(order):
        if k:
            await d.w(WADDR, base + row_idx)  # back-to-back after the previous WDATA
            got = await d.peek(WADDR)
            assert got == base + row_idx, (
                f"WADDR = {got} right after a back-to-back write of {base + row_idx}: the "
                f"software write lost to the auto-increment"
            )
        await d.w(WDATA, words[row_idx])
        d.mem[base + row_idx] = words[row_idx]
        assert await d.peek(WADDR) == base + row_idx + 1
    got = await d.infer(base, [_pack(DENSE_A)], _scale(1, 0))
    assert got == DENSE_TABLE[(1, 0, 0)], f"scattered tile mis-loaded: 0x{got:08x}"


# ===========================================================================
# Inference
# ===========================================================================
@npu_test
async def test_npu_klen1_hand_vectors(dut):
    """KLEN = 1 against HAND-COMPUTED words (not model output): the identity tile returns its
    activations (0xFC03FE01, ReLU 0x00030001) and the dense tile returns (48, 8, -32, 28) =
    0x1CE00830 -- which also pins the little-endian lane order and that row i multiplies a[i].
    Each is also scoreboarded against the model, at TILEBASE 0, 4 and the last legal tile 1020."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    await d.load_tile(4, DENSE_ROWS)
    await d.load_tile(1020, DENSE_ROWS)
    a_id, a_dn = _pack(IDENT_A), _pack(DENSE_A)
    got = await d.infer(0, [a_id], _scale(1, 0))
    assert got == IDENT_Y_WORD, f"identity: 0x{got:08x}"
    assert got == d.expect(0, [a_id], _scale(1, 0), 0)
    got = await d.infer(0, [a_id], _scale(1, 0), relu=1)
    assert got == IDENT_Y_RELU_WORD, f"identity + ReLU: 0x{got:08x}"
    for base in (4, 1020):
        got = await d.infer(base, [a_dn], _scale(1, 0))
        assert got == DENSE_TABLE[(1, 0, 0)], f"dense tile at {base}: 0x{got:08x}"
        assert got == d.expect(base, [a_dn], _scale(1, 0), 0)
    # row selection: a = e0 returns row 0 verbatim, a = e3 returns row 3 (no transpose)
    got = await d.infer(4, [_pack([1, 0, 0, 0])], _scale(1, 0))
    assert got == _pack([1, 2, 3, 4])
    got = await d.infer(4, [_pack([0, 0, 0, 1])], _scale(1, 0))
    assert got == _pack([10, 0, -10, 5])


@npu_test
async def test_npu_multichunk_hand_vector(dut):
    """KLEN = 2 (the dense tile at words 4..7 then again at 8..11, activations dense then e0):
    chunk 1 adds row 0 verbatim -> (49, 10, -29, 32) = 0x20E30A31.  Proves the weight address
    advances by exactly 4 words per chunk and the accumulators carry across chunks."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(4, DENSE_ROWS)
    await d.load_tile(8, DENSE_ROWS)
    ains = [_pack(DENSE_A), _pack([1, 0, 0, 0])]
    got = await d.infer(4, ains, _scale(1, 0))
    assert got == TWO_CHUNK_Y_WORD, f"two chunks: 0x{got:08x}"
    assert got == d.expect(4, ains, _scale(1, 0), 0)
    # distinct tiles per chunk: tile 0 row 0 = all ones, tile 1 row 0 = all twos
    await d.load_words(16, [_pack([1] * 4), 0, 0, 0, _pack([2] * 4), 0, 0, 0])
    one = _pack([1, 0, 0, 0])
    assert await d.infer(16, [one], _scale(1, 0)) == _pack([1] * 4)
    assert await d.infer(16, [one, one], _scale(1, 0)) == _pack([3] * 4)


@npu_test
async def test_npu_multichunk_random_vs_model(dut):
    """Random weights / activations / scale / ReLU at KLEN in {2, 3, 4, 5, 8, 17} -- four of them
    beyond the depth-4 AIN FIFO, so streaming AIN words while the engine runs is exercised --
    scoreboarded against the model.  Back-to-back inferences share the weight SRAM."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0x4E50_0001)
    for klen in (2, 3, 4, 5, 8, 17):
        base = rng.randrange(0, 1024 - 4 * klen + 1)
        await d.load_tile(base, [_rand_row(rng) for _ in range(4 * klen)])
        ains = [_pack(_rand_row(rng)) for _ in range(klen)]
        scale = _scale(rng.randrange(1, 1 << 16), rng.randrange(8, 24))
        relu = rng.getrandbits(1)
        got = await d.infer(base, ains, scale, relu)
        assert got == d.expect(base, ains, scale, relu), (
            f"KLEN={klen} base={base} scale=0x{scale:x} relu={relu}: got 0x{got:08x}, "
            f"model 0x{d.expect(base, ains, scale, relu):08x}"
        )


@npu_test
async def test_npu_klen_register_max_63(dut):
    """D10: KLEN = 63 (the register maximum) over the whole weight window 0..251, random data,
    against the model; the last chunk reads words 248..251."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0x4E50_003F)
    await d.load_tile(0, [_rand_row(rng) for _ in range(4 * 63)])
    ains = [_pack(_rand_row(rng)) for _ in range(63)]
    for relu, scale in ((0, _scale(3, 14)), (1, _scale(1, 12))):
        got = await d.infer(0, ains, scale, relu)
        assert got == d.expect(0, ains, scale, relu), f"KLEN=63 relu={relu}: 0x{got:08x}"


@npu_test
async def test_npu_tilebase_selects_tile_and_accumulators_clear(dut):
    """The same inference run three times returns the same word (the accumulators are zeroed at
    START -- a leak would double it) and weights persist; a different TILEBASE selects a
    different tile and returning to the first reproduces the first result; changing KLEN between
    runs works."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    await d.load_tile(4, DENSE_ROWS)  # chunk 1 of a KLEN = 2 run from TILEBASE 0 reads words 4..7
    await d.load_tile(64, [[-v for v in r] for r in DENSE_ROWS])  # the negated tile
    a = _pack(DENSE_A)
    first = await d.infer(0, [a], _scale(1, 0))
    assert first == DENSE_TABLE[(1, 0, 0)]
    for k in range(2):
        again = await d.infer(0, [a], _scale(1, 0))
        assert again == first, (
            f"run {k + 2} returned 0x{again:08x} != 0x{first:08x} (acc not cleared)"
        )
    neg = await d.infer(64, [a], _scale(1, 0))
    assert neg == _pack([-48, -8, 32, -28]), f"negated tile: 0x{neg:08x}"
    assert await d.infer(0, [a], _scale(1, 0)) == first
    # KLEN 1 -> 2 -> 1 with the same TILEBASE
    two = await d.infer(0, [a, a], _scale(1, 0))
    assert two == _pack([96, 16, -64, 56]), f"two identical chunks: 0x{two:08x}"
    assert await d.infer(0, [a], _scale(1, 0)) == first


# ===========================================================================
# Requantise
# ===========================================================================
@npu_test
async def test_npu_relu_on_off(dut):
    """RELU_EN on and off over the SAME input with a negative accumulator: off keeps y2 = -32
    (0x1CE00830), on zeroes ONLY that lane (0x1C000830); an all-negative result becomes the zero
    word under ReLU; ReLU never clamps a positive lane and the CTRL bit reads back."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    await d.load_tile(8, [[-v for v in r] for r in DENSE_ROWS])
    a = _pack(DENSE_A)
    off = await d.infer(0, [a], _scale(1, 0), relu=0)
    assert await d.peek(CTRL) & CTRL_RELU == 0
    on = await d.infer(0, [a], _scale(1, 0), relu=1)
    assert await d.peek(CTRL) & CTRL_RELU == CTRL_RELU
    assert off == DENSE_TABLE[(1, 0, 0)] and on == DENSE_TABLE[(1, 0, 1)]
    assert await d.infer(0, [a], _scale(1, 0), relu=0) == off, "RELU_EN off again must restore"
    # negated tile: lanes (-48, -8, 32, -28) -> ReLU (0, 0, 32, 0)
    assert await d.infer(8, [a], _scale(1, 0), relu=0) == _pack([-48, -8, 32, -28])
    assert await d.infer(8, [a], _scale(1, 0), relu=1) == _pack([0, 0, 32, 0])
    # all lanes negative -> zero word
    e0 = _pack([1, 0, 0, 0])
    assert await d.infer(8, [e0], _scale(1, 0), relu=0) == _pack([-1, -2, -3, -4])
    assert await d.infer(8, [e0], _scale(1, 0), relu=1) == 0, "all-negative result must ReLU to 0"


@npu_test
async def test_npu_scale_hand_table(dut):
    """SCALE multiplier / shift sweep over the dense tile against HAND-COMPUTED words: >>1, 3 >> 2,
    a multiplier that saturates INT8 in BOTH directions at once ((5, 0): 240 -> 127 and -160 ->
    -128), a zero multiplier, shift 31 (floor drives the negative lane to -1, not 0) and the ReLU
    variants.  Each is also checked against the model."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    a = _pack(DENSE_A)
    for (mult, shift, relu), want in DENSE_TABLE.items():
        got = await d.infer(0, [a], _scale(mult, shift), relu)
        assert got == want, f"mult={mult} shift={shift} relu={relu}: 0x{got:08x} != 0x{want:08x}"
        assert got == d.expect(0, [a], _scale(mult, shift), relu)


@npu_test
async def test_npu_scale_floor_rounding(dut):
    """The right shift is FLOOR: through the identity tile a = (3, -1, -3, 5) >> 1 gives
    (1, -1, -2, 2) = 0x02FEFF01.  Round-half-up would give (2, 0, -1, 3) and truncate-toward-zero
    (1, 0, -1, 2); both are rejected by lanes 0-2 (a literal, not the model).
    MUTATION TARGET: `>>>` replaced by round-to-nearest or by sign-magnitude shifting."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    got = await d.infer(0, [_pack(FLOOR_A)], _scale(1, 1))
    assert got == FLOOR_Y_WORD, f"floor shift: 0x{got:08x} != 0x{FLOOR_Y_WORD:08x}"


@npu_test
async def test_npu_scale_random_sweep(dut):
    """Multiplier x shift grid (1 / 255 / 256 / 32767 / 32768 / 65535 by 0 / 1 / 7 / 8 / 15 / 16 /
    24 / 31) on a random tile with random activations and a random RELU_EN, every point scoreboarded
    against the model: catches multiplier-bit and shift-bit stuck-ats a hand table would miss."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0x5CA1E)
    for _ in range(2):
        await d.load_tile(0, [_rand_row(rng) for _ in range(4)])
        for mult in (1, 255, 256, 32767, 32768, 65535):
            for shift in (0, 1, 7, 8, 15, 16, 24, 31):
                a = _pack(_rand_row(rng))
                relu = rng.getrandbits(1)
                got = await d.infer(0, [a], _scale(mult, shift), relu)
                want = d.expect(0, [a], _scale(mult, shift), relu)
                assert got == want, (
                    f"mult={mult} shift={shift} relu={relu} a=0x{a:08x}: "
                    f"got 0x{got:08x}, model 0x{want:08x}"
                )


@npu_test
async def test_npu_scale_product_not_32_bit(dut):
    """The accumulator x SCALE product is NOT truncated to 32 bits: KLEN = 63, every weight and
    activation -128 gives acc = 4_128_768 on each lane, and 4_128_768 * 65535 overflows 32 bits
    (a wrapped product would read -4_128_768 and saturate to -128 instead of 127).  Hand-computed
    words for both rails, the exact-power-of-two cases (63, 126) and the floor case (125).
    MUTATION TARGET: a 32-bit product register."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_words(0, [0x80808080] * (4 * 63))
    neg = [0x80808080] * 63
    pos = [0x7F7F7F7F] * 63
    for (mult, shift), want in WIDE_NEG_TABLE.items():
        got = await d.infer(0, neg, _scale(mult, shift))
        assert got == want, f"(-128 x -128) mult={mult} shift={shift}: 0x{got:08x} != 0x{want:08x}"
    for (mult, shift), want in WIDE_POS_TABLE.items():
        got = await d.infer(0, pos, _scale(mult, shift))
        assert got == want, f"(-128 x +127) mult={mult} shift={shift}: 0x{got:08x} != 0x{want:08x}"
    assert await d.infer(0, pos, _scale(65535, 0), relu=1) == 0, "ReLU of a saturated -128 is 0"


# ===========================================================================
# FIFOs
# ===========================================================================
@npu_test
async def test_npu_aout_pops_on_read(dut):
    """D4: AOUT is a live mirror of the FIFO head and a READ POPS it.  Two results queued: STATUS
    shows aout_valid (not full), repeated side-effect-free peeks keep returning the FIRST result,
    then two real reads return them IN ORDER and aout_valid drops after the second.  Then four
    results fill the depth-4 FIFO (aout_full only after the fourth) and four reads drain it in
    order, aout_valid / aout_full tracking each pop."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    words = [_pack([k + 1, -(k + 1), 2 * k, 3]) for k in range(4)]  # identity: y == a
    for k in range(2):
        await d.infer(0, [words[k]], _scale(1, 0), pop=False)
    st = await d.peek(STATUS)
    assert st & ST_AOUT_VALID and not st & ST_AOUT_FULL, f"two queued: STATUS=0x{st:02x}"
    for _ in range(5):  # live mirror: peeking never pops
        assert await d.peek(AOUT) == words[0]
        await d.next_cycle()
    assert await d.r(AOUT) == words[0]
    st = await d.peek(STATUS)
    assert st & ST_AOUT_VALID, "one result must still be queued after the first pop"
    assert await d.peek(AOUT) == words[1], "head did not advance after the pop"
    assert await d.r(AOUT) == words[1]
    st = await d.peek(STATUS)
    assert not st & (ST_AOUT_VALID | ST_AOUT_FULL), f"drained: STATUS=0x{st:02x}"
    for k in range(AOUT_DEPTH):
        await d.infer(0, [words[k]], _scale(1, 0), pop=False)
        st = await d.peek(STATUS)
        assert st & ST_AOUT_VALID
        assert bool(st & ST_AOUT_FULL) == (k == AOUT_DEPTH - 1), (
            f"after {k + 1} queued results STATUS=0x{st:02x}"
        )
    for k in range(AOUT_DEPTH):
        assert await d.r(AOUT) == words[k], f"pop {k} out of order"
        st = await d.peek(STATUS)
        assert not st & ST_AOUT_FULL, f"aout_full still set after pop {k}"
        assert bool(st & ST_AOUT_VALID) == (k < AOUT_DEPTH - 1)


@npu_test
async def test_npu_aout_empty_reads_zero_no_stale_duplicate(dut):
    """D4: an empty AOUT reads 0 and a read of it pops nothing.  After the LAST result is popped,
    further reads return 0 -- never a stale copy of the previous result -- and a result produced
    afterwards is still delivered exactly once."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    for _ in range(3):
        assert await d.r(AOUT) == 0, "empty AOUT must read 0"
    assert await d.peek(STATUS) == STATUS_RESET, "reads of an empty AOUT disturbed STATUS"
    await d.load_tile(0, IDENT_ROWS)
    w1, w2 = _pack([5, 6, 7, 8]), _pack([-5, -6, -7, -8])
    await d.infer(0, [w1], _scale(1, 0), pop=False)
    await d.infer(0, [w2], _scale(1, 0), pop=False)
    assert await d.r(AOUT) == w1
    assert await d.r(AOUT) == w2
    for k in range(3):
        assert await d.r(AOUT) == 0, f"read {k + 3} returned a stale duplicate"
        assert await d.peek(AOUT) == 0
    assert not await d.peek(STATUS) & ST_AOUT_VALID
    assert await d.infer(0, [w1], _scale(1, 0)) == w1  # still works, delivered once
    assert await d.r(AOUT) == 0


@npu_test
async def test_npu_ain_backpressure(dut):
    """D3: the depth-4 AIN FIFO.  Four pushes: ain_empty drops on the first, ain_full rises ONLY on
    the fourth.  A fifth push into the full FIFO is DROPPED (no overwrite, no extra entry, no
    cfg_rejected): a KLEN = 4 inference over per-chunk weights (1, 2, 3, 4) and activations
    (1, 2, 3, 4) returns sum(k^2) = 30 in every lane -- an overwritten last word (100) would give
    saturated 127, a reordering something else -- and afterwards the FIFO is EMPTY (ain_empty,
    not ain_full), so no phantom fifth word was queued."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    tiles = []
    for c in range(4):
        tiles += [_pack([c + 1] * 4), 0, 0, 0]  # chunk c: row 0 = (c+1) in every lane
    await d.load_words(0, tiles)
    ains = [_pack([c + 1, 0, 0, 0]) for c in range(4)]
    await d.configure(0, 4, _scale(1, 0))
    await d.clear_done()
    assert await d.peek(STATUS) & ST_AIN_EMPTY
    for k, wd in enumerate(ains):
        assert not await d.peek(STATUS) & ST_AIN_FULL, f"ain_full before push {k + 1}"
        await d.w(AIN, wd)
        st = await d.peek(STATUS)
        assert not st & ST_AIN_EMPTY, f"ain_empty after push {k + 1}"
        assert bool(st & ST_AIN_FULL) == (k == AIN_DEPTH - 1), f"STATUS=0x{st:02x} after {k + 1}"
    await d.w(AIN, _pack([100, 0, 0, 0]))  # full: dropped
    st = await d.peek(STATUS)
    assert st & ST_AIN_FULL and not st & ST_REJ, f"fifth push: STATUS=0x{st:02x}"
    await d.start()
    _n, st = await d.wait_done([])
    assert st & ST_AIN_EMPTY and not st & ST_AIN_FULL, f"after drain STATUS=0x{st:02x}"
    assert not st & ST_REJ
    got = await d.r(AOUT)
    assert got == _pack([30] * 4), f"0x{got:08x}: AIN contents/order/drop wrong (want 30 per lane)"


@npu_test
async def test_npu_starved_start_waits_for_ain(dut):
    """D3: START with an EMPTY AIN FIFO is not an error -- the engine stays busy (done 0, nothing
    in AOUT) for as long as it is starved, consumes AIN words as they arrive, and completes only
    after the KLEN-th.  Here KLEN = 2: 40 idle cycles, one word, 40 more cycles still busy, the
    second word, done -- and the result is the two-chunk result (0x20E30A31)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(4, DENSE_ROWS)
    await d.load_tile(8, DENSE_ROWS)
    a0, a1 = _pack(DENSE_A), _pack([1, 0, 0, 0])
    await d.configure(4, 2, _scale(1, 0))
    await d.clear_done()
    await d.start()
    for phase, feed in enumerate((None, a0, a1)):
        if feed is not None:
            await d.w(AIN, feed)
        if phase == 2:
            break
        for _ in range(40):
            await d.next_cycle()
            st = await d.peek(STATUS)
            assert st & ST_BUSY and not st & (ST_DONE | ST_AOUT_VALID), (
                f"phase {phase}: starved engine STATUS=0x{st:02x}"
            )
    _n, st = await d.wait_done([])
    assert st & ST_AOUT_VALID
    assert await d.r(AOUT) == TWO_CHUNK_Y_WORD


# ===========================================================================
# Handshake
# ===========================================================================
@npu_test
async def test_npu_irq_level_held_and_masked(dut):
    """irq_o == done & CTRL[3] on EVERY sampled edge of an operation (it rises with done, not
    before), and is LEVEL-HELD: with no clear it stays high on 100 consecutive cycles (a pulse
    would be missed by the plain 2-FF sync in soc_top).  CTRL[3] masks irq_o ONLY: with IRQ_EN = 0
    STATUS / IRQ_STAT still show done, and re-enabling it raises the interrupt again (a level, not
    an edge latched at done time).  IRQ_CLR[0] drops it and it stays low.  An illegal start
    interrupts too ([0, 1] over its two edges).  With IRQ_EN = 0 a whole run never raises irq_o.
    MUTATION TARGET: irq_o as a one-cycle pulse; IRQ_EN masking STATUS; irq_o ignoring IRQ_EN."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    a = [_pack(DENSE_A)]
    for ie in (0, 1):
        tr = await d.run_traced(0, a, _scale(1, 0), ie=ie)
        _check_pattern(d, tr, None, f"inference ie={ie}")
        for k, (st, _ist, irq, _rdy) in enumerate(tr, start=1):
            assert irq == (1 if (st & ST_DONE) and ie else 0), (
                f"ie={ie}: irq_o={irq} with STATUS=0x{st:02x} after edge {k}/{len(tr)}"
            )
        assert tr[-1][0] & ST_AOUT_VALID
        assert await d.r(AOUT) == DENSE_TABLE[(1, 0, 0)]
    for i in range(100):  # still ie=1, done never cleared
        assert int(d.irq_o.value) == 1, f"irq_o dropped after {i} cycles with no clear"
        await d.next_cycle()
    await d.w(CTRL, _ctrl(ie=0))  # mask
    await d.next_cycle()
    assert int(d.irq_o.value) == 0, "irq_o not masked by CTRL[3]"
    st = await d.peek(STATUS)
    assert st & ST_DONE and await d.peek(IRQ_STAT) == 1, "IRQ_EN = 0 masked STATUS / IRQ_STAT"
    await d.w(CTRL, _ctrl(ie=1))  # unmask
    await d.next_cycle()
    assert int(d.irq_o.value) == 1, "re-enabling IRQ_EN did not raise the pending interrupt"
    await d.w(IRQ_CLR, CLR_DONE)
    await d.next_cycle()
    for _ in range(50):
        assert int(d.irq_o.value) == 0, "irq_o high after IRQ_CLR[0]"
        await d.next_cycle()
    assert await d.peek(IRQ_STAT) == 0
    tr = await d.run_traced(0, [], _scale(1, 0), ie=1)  # KLEN == 0: the zero-length path
    _check_pattern(d, tr, N_ILLEGAL, "illegal start ie=1")
    assert [t[2] for t in tr] == [0, 1], f"illegal-start irq pattern {[t[2] for t in tr]}"


@npu_test
async def test_npu_set_beats_same_cycle_clear(dut):
    """The sticky done is SET-WINS (done_d = (done_q & ~clr) | set): an IRQ_CLR[0] write whose
    ACCESS edge is exactly the completion edge loses to the hardware set, whether done was clear
    beforehand (case A) or already set (case B, the case a clear-wins flop gets wrong).  One edge
    EARLIER the clear takes (case C: done was 1, cleared, then set again by the completion -> 1);
    one edge LATER it clears the freshly set done (case D -> 0).  The legal-run latency N is not in
    the spec, so the test CALIBRATES it on two identical dry runs (D5: they must agree, and N >= 4
    so a write can be aligned), then aligns raw SETUP / ACCESS phases to the completion edge
    E + N - 1.
    MUTATION TARGET: done_d = (done_q | set) & ~clr (clear beats set)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    a = [_pack(DENSE_A)]
    n_runs = []
    for _ in range(2):
        tr = await d.run_traced(0, a, _scale(1, 0))
        n_runs.append(_check_pattern(d, tr, None, "calibration run"))
        assert await d.r(AOUT) == DENSE_TABLE[(1, 0, 0)]
    assert n_runs[0] == n_runs[1], f"latency not deterministic: {n_runs} edges (D5)"
    n = n_runs[0]
    assert n >= 4, f"latency N={n} is too short to align a clear to the completion edge"
    comp = n - 1  # completion edge, relative to E
    cases = (
        ("A: clear on the completion edge, done was 0", False, comp, 1),
        ("B: clear on the completion edge, done was 1", True, comp, 1),
        ("C: clear one edge before completion, done was 1", True, comp - 1, 1),
        ("D: clear one edge after completion", False, comp + 1, 0),
    )
    for what, pre_done, rel, want_done in cases:
        await d.clear_done()
        if pre_done:
            await d.infer(0, a, _scale(1, 0))
            assert await d.peek(STATUS) & ST_DONE, f"{what}: pre-set done missing"
        await d.configure(0, 1, _scale(1, 0))
        await d.push_ain(a)
        await d.start()
        await d.timed_write(rel, IRQ_CLR, CLR_DONE)
        await ClockCycles(dut.clk, n + 4)
        st = await d.peek(STATUS)
        assert st & ST_BUSY == 0, f"{what}: still busy, STATUS=0x{st:02x}"
        assert bool(st & ST_DONE) == bool(want_done), (
            f"{what}: STATUS=0x{st:02x}, done should be {want_done}"
        )
        assert await d.peek(IRQ_STAT) == want_done, f"{what}: IRQ_STAT != STATUS.done"
        assert await d.r(AOUT) == DENSE_TABLE[(1, 0, 0)], f"{what}: wrong or missing result"


@npu_test
async def test_npu_status_not_stale(dut):
    """STATUS is written with the NEXT-STATE value every cycle (live mirror, no lag): the APB read
    that follows the START write by one transfer already shows the completion of an illegal start
    (done = 1, busy = 0, cfg_rejected = 1; IRQ_STAT = 1 likewise), and after a LEGAL start every
    real APB read of STATUS is either busy alone or done WITH aout_valid -- never the stale idle
    value 0x08 (or 0x00) the pre-start state would give, and never busy and done together."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.configure(0, 0, _scale(1, 0))  # KLEN == 0: illegal
    await d.clear_done()
    await d.start()
    st = await d.r(STATUS)
    assert st & ST_DONE and not st & ST_BUSY and st & ST_REJ, (
        f"stale STATUS 0x{st:02x} after illegal"
    )
    await d.clear_done()
    await d.start()
    assert await d.r(IRQ_STAT) == 1, "IRQ_STAT stale one transfer after the completion edge"
    # legal run polled with REAL back-to-back APB reads
    await d.load_tile(0, DENSE_ROWS)
    await d.configure(0, 1, _scale(1, 0))
    await d.clear_done()
    await d.clear_rej()
    await d.push_ain([_pack(DENSE_A)])
    await d.start()
    reads = []
    for _ in range(2000):
        st = await d.r(STATUS)
        reads.append(st)
        if st & ST_DONE:
            break
    else:
        raise AssertionError("done never observed through APB reads")
    for k, st in enumerate(reads):
        busy, done = bool(st & ST_BUSY), bool(st & ST_DONE)
        assert busy != done, f"read {k}: STATUS=0x{st:02x} is stale-idle or busy+done"
    assert reads[-1] & ST_AOUT_VALID, f"done read without a result: 0x{reads[-1]:02x}"
    assert await d.r(AOUT) == DENSE_TABLE[(1, 0, 0)]


@npu_test
async def test_npu_reset_mid_operation(dut):
    """A reset during a starved operation returns the block to its reset state: STATUS 0x08 (busy,
    done and any queued AIN word gone), every RW register 0, quiescent for 100 cycles with no
    phantom operation, and a fresh KLEN = 1 inference afterwards returns ITS result and leaves the
    AIN FIFO empty (a surviving stale AIN word would be consumed first and corrupt it)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    await d.configure(0, 2, _scale(3, 2), relu=1, ie=1)
    await d.clear_done()
    await d.push_ain([_pack([100, 100, 100, 100])])  # a stale word that must not survive
    await d.start(relu=1, ie=1)
    for _ in range(10):
        await d.next_cycle()
    assert await d.peek(STATUS) & ST_BUSY, "operation not in flight before the reset"
    await _reset(dut, rig)
    for addr in (CTRL, WADDR, TILEBASE, KLEN, SCALE, AIN, AOUT, IRQ_STAT, IRQ_CLR):
        assert await d.peek(addr) == 0, f"0x{addr:02x} not reset"
    assert await d.peek(STATUS) == STATUS_RESET
    assert int(d.irq_o.value) == 0
    for _ in range(100):
        await d.next_cycle()
        assert await d.peek(STATUS) == STATUS_RESET, "phantom activity after reset"
    got = await d.infer(0, [_pack(DENSE_A)], _scale(1, 0))
    assert got == DENSE_TABLE[(1, 0, 0)], f"post-reset inference: 0x{got:08x}"
    assert await d.peek(STATUS) & ST_AIN_EMPTY, "stale AIN word survived the reset"


# ===========================================================================
# Illegal START and cfg_rejected
# ===========================================================================
@npu_test
async def test_npu_illegal_start_is_hang_free(dut):
    """D6: every illegal START takes the 2-edge zero-length path -- busy for edge 1, done on edge 2,
    cfg_rejected latched, NO AOUT push (aout_valid stays 0, AOUT reads 0), pready high on every
    edge and the bus still answers afterwards.  Cases: KLEN == 0; KLEN written 64 (stores 0);
    TILEBASE + 4*KLEN just over 1024 for KLEN 1, 1 and 63 (1021, 1023, 773) and well over (1020 with
    KLEN 2, 1000 with KLEN 63).  `done` does NOT imply valid data.
    MUTATION TARGET: a dropped START (hang) or an off-by-one in the bounds compare."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    cases = (
        ("KLEN=0", 0, 0),
        ("KLEN=64 stores 0", 0, 64),
        ("1021+4*1=1025", 1021, 1),
        ("1023+4*1=1027", 1023, 1),
        ("773+4*63=1025", 773, 63),
        ("1020+4*2=1028", 1020, 2),
        ("1000+4*63=1252", 1000, 63),
    )
    for what, tilebase, klen in cases:
        await d.clear_done()
        await d.clear_rej()
        await d.configure(tilebase, klen, _scale(1, 0), ie=1)
        await d.clear_done()
        await d.start(ie=1)
        tr = await d.trace()
        _check_pattern(d, tr, N_ILLEGAL, what)
        st = tr[-1][0]
        assert st & ST_REJ, f"{what}: cfg_rejected not latched (STATUS=0x{st:02x})"
        assert not st & ST_AOUT_VALID, f"{what}: an illegal start pushed a result"
        assert await d.peek(AOUT) == 0 and await d.r(AOUT) == 0, f"{what}: AOUT not empty"
        assert [t[2] for t in tr] == [0, 1], f"{what}: irq pattern {[t[2] for t in tr]}"
        assert await d.r(STATUS) & ST_REJ, f"{what}: bus did not answer / rejection lost"


@npu_test
async def test_npu_legal_boundaries_accepted(dut):
    """The legality compare is exact: the LAST legal tile (TILEBASE 1020, KLEN 1) and the largest
    legal run (TILEBASE 772, KLEN 63: 772 + 252 == 1024) are ACCEPTED -- cfg_rejected stays 0, a
    result appears -- and match the model on random data.  (The matching illegal neighbours are
    in test_npu_illegal_start_is_hang_free.)"""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0xB0DD)
    for tilebase, klen in ((1020, 1), (772, 63)):
        await d.load_tile(tilebase, [_rand_row(rng) for _ in range(4 * klen)])
        ains = [_pack(_rand_row(rng)) for _ in range(klen)]
        scale = _scale(rng.randrange(1, 1 << 16), rng.randrange(8, 24))
        await d.clear_rej()
        got = await d.infer(tilebase, ains, scale)
        assert got == d.expect(tilebase, ains, scale, 0), f"{tilebase}/{klen}: 0x{got:08x}"
        assert not await d.peek(STATUS) & ST_REJ, f"{tilebase}/{klen} wrongly rejected"


@npu_test
async def test_npu_cfg_rejected_clear_paths(dut):
    """D7: STATUS[6] cfg_rejected is sticky and clears on exactly three events -- IRQ_CLR[1],
    an accepted WDATA write, and reset -- while IRQ_CLR[0] leaves it alone and IRQ_CLR[1] leaves
    done alone.  (It is latched here by an illegal start: KLEN == 0.)"""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.configure(0, 0, _scale(1, 0))

    async def latch() -> int:
        await d.clear_done()
        await d.clear_rej()
        await d.start()
        await d.trace()
        st = await d.peek(STATUS)
        assert st & ST_REJ and st & ST_DONE, f"latch failed: STATUS=0x{st:02x}"
        return st

    await latch()
    await d.w(IRQ_CLR, CLR_DONE)  # IRQ_CLR[0] does not touch cfg_rejected
    st = await d.peek(STATUS)
    assert st & ST_REJ and not st & ST_DONE, f"IRQ_CLR[0]: STATUS=0x{st:02x}"
    await d.next_cycle()
    assert await d.peek(STATUS) & ST_REJ, "cfg_rejected is not sticky"
    await d.w(IRQ_CLR, CLR_REJ)
    assert not await d.peek(STATUS) & ST_REJ, "IRQ_CLR[1] did not clear cfg_rejected"
    await latch()
    await d.w(IRQ_CLR, CLR_REJ)  # IRQ_CLR[1] does not touch done
    st = await d.peek(STATUS)
    assert st & ST_DONE and not st & ST_REJ, f"IRQ_CLR[1]: STATUS=0x{st:02x}"
    await latch()
    await d.w(WADDR, 0)
    await d.w(WDATA, 0x01020304)  # accepted (idle) weight write
    d.mem[0] = 0x01020304
    st = await d.peek(STATUS)
    assert not st & ST_REJ, "an accepted WDATA write did not clear cfg_rejected"
    assert st & ST_DONE, "an accepted WDATA write must not clear done"
    await d.w(IRQ_CLR, 0x3)
    assert await d.peek(STATUS) & (ST_REJ | ST_DONE) == 0, "IRQ_CLR = 0x3 clears both"
    await latch()
    await _reset(dut, rig)
    assert await d.peek(STATUS) == STATUS_RESET, "reset did not clear cfg_rejected / done"


@npu_test
async def test_npu_weight_write_while_busy_is_rejected(dut):
    """D8: a WADDR or WDATA write while STATUS.busy is REJECTED -- WADDR unchanged, the junk
    never reaches the SRAM, cfg_rejected latches (and IRQ_CLR[1] clears it again, even while
    busy).  The busy window is made deterministic by a STARVED start (D3).  WADDR is parked INSIDE
    the tile (word 1), so an accepted junk WDATA would overwrite row 1 and the inference result
    would change; it must not.  Once idle, the same write IS accepted: WADDR advances and
    cfg_rejected clears (D7)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    await d.w(WADDR, 1)
    await d.configure(0, 1, _scale(1, 0))
    await d.clear_done()
    await d.clear_rej()
    await d.start()
    for _ in range(10):
        await d.next_cycle()
    st = await d.peek(STATUS)
    assert st & ST_BUSY and not st & ST_DONE, f"not in the starved busy window: 0x{st:02x}"
    await d.w(WADDR, 3)  # rejected
    assert await d.peek(WADDR) == 1, "WADDR write accepted while busy"
    assert await d.peek(STATUS) & ST_REJ, "rejected WADDR write did not latch cfg_rejected"
    await d.clear_rej()
    assert not await d.peek(STATUS) & ST_REJ
    for _ in range(3):
        await d.w(WDATA, 0xFFFFFFFF)  # rejected, none may land or advance WADDR
        assert await d.peek(WADDR) == 1, "WDATA while busy advanced WADDR"
        assert await d.peek(STATUS) & ST_REJ, "rejected WDATA write did not latch cfg_rejected"
    await d.push_ain([_pack(DENSE_A)])
    _n, st = await d.wait_done([])
    got = await d.r(AOUT)
    assert got == DENSE_TABLE[(1, 0, 0)], f"a rejected write reached the SRAM: 0x{got:08x}"
    assert await d.peek(STATUS) & ST_REJ, "cfg_rejected lost across the end of the operation"
    await d.w(WDATA, _pack(DENSE_ROWS[1]))  # idle again: accepted (rewrites row 1 verbatim)
    assert await d.peek(WADDR) == 2, "idle WDATA write was not accepted"
    assert not await d.peek(STATUS) & ST_REJ, "accepted WDATA write did not clear cfg_rejected"


# ===========================================================================
# Strobes, START-while-busy, sticky done, AOUT overflow (closes the former D13 gaps)
# ===========================================================================
async def _starved_busy_window(d: _Dev, tilebase: int, klen: int) -> None:
    """START with an EMPTY AIN FIFO and wait it out: a deterministic busy window (the engine
    fetches its first chunk's rows, then sits starved on the AIN FIFO; done stays 0)."""
    await d.configure(tilebase, klen, _scale(1, 0))
    await d.clear_done()
    await d.clear_rej()
    await d.start()
    for _ in range(15):
        await d.next_cycle()
    st = await d.peek(STATUS)
    assert st & ST_BUSY and not st & ST_DONE, f"not in the starved busy window: 0x{st:02x}"


@npu_test
async def test_npu_start_partial_strobe_ignored(dut):
    """D13a: START is decoded from byte lane 0 only.  A CTRL write of 0x4 with pstrb 1110 (lane 0
    not selected) or 0000 starts nothing: no busy, no done, no AOUT result, and the queued AIN word
    is NOT consumed.  A normal START afterwards runs the inference.
    MUTATION TARGET: `& pstrb[0]` dropped from the START snoop."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    a = _pack(IDENT_A)
    await d.configure(0, 1, _scale(1, 0))
    await d.clear_done()
    await d.push_ain([a])
    for strb in (0b1110, 0b0000):
        await d.w(CTRL, CTRL_START, strb=strb)
        for _ in range(30):
            await d.next_cycle()
        st = await d.peek(STATUS)
        assert not st & (ST_BUSY | ST_DONE | ST_AOUT_VALID), f"strb={strb:04b}: STATUS=0x{st:02x}"
        assert not st & ST_AIN_EMPTY, f"strb={strb:04b}: the AIN word was consumed"
    await d.start()
    await d.wait_done([])
    assert await d.r(AOUT) == IDENT_Y_WORD


@npu_test
async def test_npu_partial_strobe_wdata_ain_dropped(dut):
    """D13b: a WDATA or AIN write needs a FULL strobe.  Partial strobes (0001, 0011, 0111, 1110,
    1000) on WDATA leave WADDR where it was, latch no cfg_rejected and never reach the SRAM; on AIN
    they queue nothing (ain_empty stays set).  The identity-tile inference afterwards is exact.
    MUTATION TARGETS: `pstrb == 4'hF` relaxed to `|pstrb` on the WDATA accept or the AIN push."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    await d.w(WADDR, 0)
    strobes = (0b0001, 0b0011, 0b0111, 0b1110, 0b1000)
    for strb in strobes:
        await d.w(WDATA, 0xFFFFFFFF, strb=strb)
        assert await d.peek(WADDR) == 0, f"WDATA strb={strb:04b} advanced WADDR"
        assert not await d.peek(STATUS) & ST_REJ, f"WDATA strb={strb:04b} latched cfg_rejected"
    for strb in strobes:
        await d.w(AIN, 0x7F7F7F7F, strb=strb)
        st = await d.peek(STATUS)
        assert st & ST_AIN_EMPTY, f"AIN strb={strb:04b} queued a word: STATUS=0x{st:02x}"
    got = await d.infer(0, [_pack(IDENT_A)], _scale(1, 0))
    assert got == IDENT_Y_WORD, f"a partial-strobe write reached the SRAM or AIN: 0x{got:08x}"


@npu_test
async def test_npu_start_while_busy_ignored(dut):
    """D13c: START while busy is ignored, legal or not.  Inside a starved busy window TILEBASE and
    KLEN are rewritten (both are writable while busy) and START is written again, first legal and
    then with KLEN = 0.  Neither may restart the run (a restart would reload KLEN / TILEBASE and
    consume a different tile), complete it early (done) or latch cfg_rejected (the illegal-START
    path).  The original two-chunk run then finishes with the original result, consumes both AIN
    words, and queues exactly one result.
    MUTATION TARGETS: `~busy_q` dropped from start_accept_w (C20) or from start_ill_w (C28)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, DENSE_ROWS)
    await d.load_tile(4, DENSE_ROWS)
    await d.load_tile(16, IDENT_ROWS)
    a0, a1 = _pack(DENSE_A), _pack([1, 0, 0, 0])
    want = d.expect(0, [a0, a1], _scale(1, 0), 0)
    assert want == TWO_CHUNK_Y_WORD
    await _starved_busy_window(d, 0, 2)
    await d.w(TILEBASE, 16)
    await d.w(KLEN, 1)
    await d.start()  # legal START while busy
    for _ in range(5):
        await d.next_cycle()
    st = await d.peek(STATUS)
    assert st & ST_BUSY and not st & (ST_DONE | ST_REJ), f"legal START while busy: 0x{st:02x}"
    await d.w(KLEN, 0)
    await d.start()  # illegal START while busy
    for _ in range(5):
        await d.next_cycle()
    st = await d.peek(STATUS)
    assert st & ST_BUSY and not st & (ST_DONE | ST_REJ), f"illegal START while busy: 0x{st:02x}"
    await d.push_ain([a0, a1])
    _n, st = await d.wait_done([])
    assert st & ST_AIN_EMPTY, "the original run did not consume both AIN words"
    got = await d.r(AOUT)
    assert got == want, f"result 0x{got:08x} != the original run's 0x{want:08x}"
    assert not await d.peek(STATUS) & ST_AOUT_VALID, "a second result was queued"


@npu_test
async def test_npu_zero_strobe_weight_write_while_busy_not_rejected(dut):
    """D13d: a zero-strobe WDATA / WADDR write selects no byte lane, so it is not a write attempt:
    while busy it latches no cfg_rejected.  (A partial-strobe attempt while busy IS an attempt and
    does latch it -- checked last, so the zero-strobe result cannot be a stuck-low flag.)
    MUTATION TARGET: `& (|pstrb)` dropped from wt_attempt_w."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    await _starved_busy_window(d, 0, 1)
    await d.w(WDATA, 0xFFFFFFFF, strb=0)
    await d.w(WADDR, 5, strb=0)
    st = await d.peek(STATUS)
    assert not st & ST_REJ, f"a zero-strobe write latched cfg_rejected: STATUS=0x{st:02x}"
    await d.w(WDATA, 0xFFFFFFFF, strb=0b0001)
    assert await d.peek(STATUS) & ST_REJ, "a partial-strobe write while busy was not rejected"
    await d.push_ain([_pack(IDENT_A)])
    await d.wait_done([])
    assert await d.r(AOUT) == IDENT_Y_WORD


@npu_test
async def test_npu_done_sticky_across_start(dut):
    """D13e: done is sticky until IRQ_CLR[0]; an accepted START does not clear it.  After one
    finished run, START the next WITHOUT clearing done: STATUS shows busy AND done together right
    after the START, and done is still set when the run ends.
    MUTATION TARGET: `& ~start_accept_w` added to the done hold term."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    a = _pack(IDENT_A)
    await d.infer(0, [a], _scale(1, 0))  # leaves done set
    assert await d.peek(STATUS) & ST_DONE
    await d.push_ain([a])
    await d.start()  # no clear_done first
    await d.next_cycle()
    st = await d.peek(STATUS)
    assert st & ST_BUSY and st & ST_DONE, f"done not sticky across START: STATUS=0x{st:02x}"
    for _ in range(60):
        await d.next_cycle()
    st = await d.peek(STATUS)
    assert not st & ST_BUSY and st & ST_DONE, f"STATUS=0x{st:02x} after the second run"


@npu_test
async def test_npu_aout_overflow_drops_fifth(dut):
    """D13f: a result that finishes into a FULL AOUT FIFO is dropped and the older, unpopped
    results are preserved.  Five inferences with no pop in between: aout_full is set, four reads
    return results 0..3 in order, and the FIFO is then empty (no fifth entry, no overwrite).
    MUTATION TARGET: the `~aout_vp_w[3]` full guard on the AOUT push position."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_tile(0, IDENT_ROWS)
    words = [_pack([k + 1, -(k + 1), 2 * k, 3]) for k in range(AOUT_DEPTH + 1)]
    for k in range(AOUT_DEPTH + 1):
        await d.infer(0, [words[k]], _scale(1, 0), pop=False)
    assert await d.peek(STATUS) & ST_AOUT_FULL
    for k in range(AOUT_DEPTH):
        assert await d.r(AOUT) == words[k], f"pop {k}: the older results must be preserved"
    st = await d.peek(STATUS)
    assert not st & (ST_AOUT_VALID | ST_AOUT_FULL), f"a fifth result leaked: STATUS=0x{st:02x}"


# ===========================================================================
# EN_NPU = 0
# ===========================================================================
@npu_test
async def test_npu_en_npu_off_terminates_cleanly(dut):
    """EN_NPU = 0 constant-folds the block away but its APB face still terminates: pready = 1
    (sampled in the SETUP phase, the ACCESS phase and idle), pslverr = 0, prdata = 0 for every
    word including STATUS (it reads 0x00, not the live build's 0x08), irq_o tied 0 even after
    CTRL <- 0xFFFFFFFF (IRQ_EN and START both set), writes accepted and dropped, and the live build
    next to it is unaffected.  The face is checked BEFORE any BFM call so a stuck pready fails here
    instead of hanging the BFM."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.off
    d.psel.value = 1
    d.penable.value = 0
    d.pwrite.value = 0
    d.paddr.value = STATUS
    await d.next_cycle()
    assert int(d.pready.value) == 1 and int(d.pslverr.value) == 0, "SETUP phase: pready / pslverr"
    d.penable.value = 1
    await d.next_cycle()
    assert int(d.pready.value) == 1 and int(d.pslverr.value) == 0, "ACCESS phase: pready / pslverr"
    assert int(d.prdata.value) == 0, "STATUS must read 0 on the disabled build"
    d.psel.value = 0
    d.penable.value = 0
    for _ in range(5):
        await d.next_cycle()
        assert int(d.pready.value) == 1 and int(d.pslverr.value) == 0 and int(d.irq_o.value) == 0
    for i in range(N_REGS):
        assert await d.r(4 * i) == 0, f"off build: word {i} read non-zero"
    for addr in OUT_OF_RANGE:
        assert await d.r(addr) == 0
    for addr in [4 * i for i in range(N_REGS)] + list(OUT_OF_RANGE):
        await d.w(addr, 0xFFFFFFFF)  # CTRL gets IRQ_EN | START; AIN / WDATA get data
        assert int(d.irq_o.value) == 0, f"irq_o rose after a write to 0x{addr:03x}"
    for i in range(N_REGS):
        assert await d.r(4 * i) == 0, f"off build: word {i} stored a write"
    for _ in range(100):
        await d.next_cycle()
        assert int(d.irq_o.value) == 0 and int(d.pready.value) == 1 and int(d.pslverr.value) == 0
        assert await d.peek(STATUS) == 0
    assert await rig.main.peek(STATUS) == STATUS_RESET, "the live build was disturbed"


# ===========================================================================
# Elaboration guards (lint-only; no simulation)
# ===========================================================================
def _npu_sources() -> list[str]:
    """NPU_SOURCES as `make npu` sees it, resolved with the repo's own Makefile parser
    (tools/verif/check_source_closure.py), NOT a hand-copied list that could drift."""
    verif = str(_PROJ_ROOT / "tools" / "verif")
    if verif not in sys.path:
        sys.path.insert(0, verif)
    from check_source_closure import extract_makefile_lists

    lists = extract_makefile_lists(Path(__file__).resolve().parent / "Makefile")
    assert "NPU_SOURCES" in lists, "NPU_SOURCES missing from tb/cocotb/soc/Makefile"
    return lists["NPU_SOURCES"]


# A throwaway SINGLE-instance top for the lint-only checks (see tb_npu.sv: a -G override of the
# two-instance wrapper could put two identically-parameterised npu_top instances in one build).
_SINGLE_TOP = """`default_nettype none
module tb_npu_single #(
    parameter int unsigned ADDR_W       = 12,
    parameter int unsigned WEIGHT_WORDS = 1024,
    parameter int unsigned GRID         = 4,
    parameter bit          EN_NPU       = 1
) (
    input  logic              clk,
    input  logic              rst_n,
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,
    output logic              irq_o
);
    npu_top #(
        .ADDR_W(ADDR_W), .WEIGHT_WORDS(WEIGHT_WORDS), .GRID(GRID), .EN_NPU(EN_NPU)
    ) u_dut (
        .clk(clk), .rst_n(rst_n), .psel(psel), .penable(penable), .pwrite(pwrite),
        .paddr(paddr), .pwdata(pwdata), .pstrb(pstrb), .prdata(prdata), .pready(pready),
        .pslverr(pslverr), .irq_o(irq_o)
    );
endmodule
`default_nettype wire
"""


def _lint(*overrides: str) -> subprocess.CompletedProcess:
    """`verilator --lint-only -Wall` of the NPU_SOURCES RTL under a single-instance top, with
    optional -G<PARAM>=<value> overrides."""
    rtl = [p for p in _npu_sources() if Path(p).name != "tb_npu.sv"]
    assert len(rtl) == len(_npu_sources()) - 1, "tb_npu.sv not found in NPU_SOURCES"
    with tempfile.TemporaryDirectory() as tmp:
        top = Path(tmp) / "tb_npu_single.sv"
        top.write_text(_SINGLE_TOP, encoding="utf-8")
        cmd = [
            "verilator",
            "--lint-only",
            "-Wall",
            "-Wno-IMPORTSTAR",
            "-Wno-SYNCASYNCNET",
            "-Wno-DECLFILENAME",  # sim/sram_1rw_256x32_verilator.v: file != module name (Makefile)
            "--top-module",
            "tb_npu_single",
            *overrides,
            *rtl,
            str(top),
        ]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)


@cocotb.test()
async def test_npu_elaboration_guard_rejects_bad_weight_words(dut):
    """D12: WEIGHT_WORDS other than 1024 is an elaboration $fatal naming WEIGHT_WORDS (the 4 KB
    macro is the only memory the block is built around; a sweep must not silently infer flops).
    Each override must give a NON-ZERO exit AND name the parameter in the output without being a
    mere missing-file error; the same command line at the defaults is the negative control that
    proves it is sound.  Lint-only: no simulation."""
    ok = _lint()
    assert ok.returncode == 0, f"default elaboration must pass:\n{ok.stdout}{ok.stderr}"
    for args in (("-GWEIGHT_WORDS=512",), ("-GWEIGHT_WORDS=4096",), ("-GWEIGHT_WORDS=0",)):
        r = _lint(*args)
        out = r.stdout + r.stderr
        assert r.returncode != 0, f"{args} elaborated; the guard is not firing"
        assert "WEIGHT_WORDS" in out, f"{args} failed, but not via the WEIGHT_WORDS guard:\n{out}"
        assert "Cannot find file" not in out, (
            f"{args} failed on a missing file, not a guard:\n{out}"
        )


@cocotb.test()
async def test_npu_elaboration_legal_configs_pass(dut):
    """Both generate arms elaborate and lint clean on their own (-Wall, so any warning fails):
    EN_NPU = 1 at the defaults and EN_NPU = 0 (the block constant-folds away).  The EN_NPU = 0
    arm is also always built inside tb_npu, so this is a second, single-instance proof."""
    for args in ((), ("-GEN_NPU=0",), ("-GEN_NPU=1",)):
        r = _lint(*args)
        assert r.returncode == 0, f"{args} must elaborate cleanly:\n{r.stdout}{r.stderr}"
