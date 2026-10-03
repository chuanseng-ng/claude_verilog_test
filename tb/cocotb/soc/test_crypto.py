"""test_crypto.py -- Phase 6b cocotb L1 verification for crypto_accel (rtl/periph/crypto_accel.sv
+ rtl/periph/aes128_core.sv + rtl/periph/sha256_core.sv, bead claude_verilog_test-f7vs.10,
docs/PHASE6_IP_EXPANSION_PLAN.md Sec.6b "CRYPTO", whose "Register-map corrections" and "Acceptance
criteria" blocks this suite is written to prove).

STRICT TDD: the RTL DID NOT EXIST when this suite was written.  This is step 2 of the mandated
workflow ("the verification orchestrator runs before the RTL orchestrator"): `make crypto` /
`make crypto_lint` are EXPECTED to fail until the three RTL files match the contract below.  The
assertions are therefore derived from the frozen microarchitecture contract, the plan's acceptance
criteria and the standards (FIPS-197, FIPS-180-4, NIST SP 800-38A) -- never from reading an FSM.
The golden models are tb/models/aes128_model.py (AES-128 encrypt + CTR, standard library only) and
`hashlib.sha256`; requirements.txt gains nothing.

THIS IS NOT PRODUCTION CRYPTO.  The DUT has no side-channel (timing / power / DPA) resistance, no
fault-injection hardening, is not certified and not validated against any scheme; the key shadow
is fully exposed through scan.  Nothing here claims otherwise.

DUT: tb_crypto -- ONE wrapper, FOUR crypto_accel instances sharing clk / rst_n, each with its own
flat APB4 face selected by a signal-name prefix (APB4Master(dut, prefix, ...)):

    ""        u_dut     the build under test (ADDR_W=12, EN_AES=EN_SHA=1, SBOX_PARALLEL=16)
    "v4_"     u_dut_v4  SBOX_PARALLEL = 4   (the pre-documented Gate A area fallback)
    "noaes_"  u_dut_na  EN_AES = 0          (SHA-only)
    "nosha_"  u_dut_ns  EN_SHA = 0          (AES-only)

One simulation build therefore reaches both generate arms and both fold factors; tb_crypto's
header says why.  crypto_accel has NO asynchronous input at all (clk / rst_n / APB4 in, irq_o out),
so there is no CDC, no cdc_2ff_sync and no SDC exception to test.

Register map (crypto_accel.sv, ADDR_W=12, N_REGS=32; byte offset = word index * 4):
  0x000  CRYPTO_CTRL     [RW]  [1:0] mode (0 ECB, 1 CTR, 2 SHA-256, 3 reserved), [3] IRQ enable,
                               [4] SHA_CONT.  [2] START is W1P: a WRITE-SNOOP pulse, not a stored
                               bit -- it reads 0 forever (stored mask 0x1B).  Needs pstrb[0].
  0x004  CRYPTO_STATUS   [RO]  [0] busy, [1] done, [2] key_valid, [3] key_write_rejected
  0x008-0x014  KEY0-3    [WO]  AES-128 key into a SHADOW register; the bank words read 0 FOREVER
  0x018-0x024  IV0-3     [RW]  CTR counter block (the one RW data register; HW increments IV3)
  0x028-0x034  DIN0-3    [WO]  a 4-WORD APERTURE onto one 512-bit shift register; reads 0
  0x038-0x044  DOUT0-3   [RO]  AES output block (the bank word IS the result register)
  0x048-0x064  DIGEST0-7 [RO]  SHA-256 digest, which is ALSO the chaining value (CTRL[4] SHA_CONT)
  0x068  CRYPTO_IRQ_STAT [RO]  [0] sticky done (the SAME flop as STATUS[1])
  0x06C  CRYPTO_IRQ_CLR  [WO]  W1C by write-snoop: [0] clears done, [1] clears key_write_rejected
  0x070-0x07C  reserved (read 0, writes dropped);  word index >= 32 (0x080..0xFFC): read 0,
                               writes dropped, pslverr stays 0 (the bank's out-of-range policy)

BYTE ORDER (frozen contract Sec.0).  FIPS big-endian everywhere: for a 128-bit block B[0..15],
word 0 carries B0 in bits [31:24]; DIN0[31:24] = B0 ... DIN3[7:0] = B15; likewise KEY, IV, DOUT.
DIGEST0[31:24] is the MSB of H0.  So the FIPS-197 hex strings and `hashlib.sha256().digest()`
line up with NO byte swap in this suite.  DIN is a FIFO of words: software writes 4 words in order
for AES (first word lands at msg[127:96]) and 16 words in order for SHA (first word = M0); WHICH of
the four DIN addresses is written is irrelevant, the WRITE ORDER is the contract.

Operation: write KEY0-3 once, push the block through DIN, write CTRL (mode), write CTRL again with
START, poll STATUS.done (or take irq_o), read DOUT / DIGEST.  SHA multi-block: first block with
SHA_CONT = 0 (starts from the FIPS-180-4 H0 constants), later blocks with SHA_CONT = 1 (continue
from the current DIGEST).  PADDING AND LENGTH ARE SOFTWARE'S JOB, so `_sha_pad` below is the
testbench doing the driver's work.

Timing conventions this suite pins (frozen contract Sec.3).  "E" is the clock edge at which the
START write's ACCESS phase is sampled; N counts edges INCLUDING E, so "N = 11" means STATUS.done
first reads 1 after the 11th edge counting E as the 1st.
  - AES ECB / CTR: N = 11 at SBOX_PARALLEL = 16 (1 whitening + 10 rounds), N = 41 at 4.
  - SHA-256: N = 66 (1 load + 64 rounds + 1 final add).     - illegal op: N = 2.
  - While running, STATUS reads busy = 1, done = 0 after every edge 1 .. N-1; after edge N it reads
    busy = 0, done = 1.  STATUS and IRQ_STAT carry NEXT-STATE values (hw_wen every cycle), so a
    read one transfer after the start always sees busy = 1 and a read after the completion edge
    always sees done = 1 -- never a stale 0.
  - DOUT / DIGEST / IV3 are written with the cores' COMBINATIONAL next-state result on that same
    completion edge, so done and the data become visible together.
  - irq_o = done & CTRL[3], combinational off flops: LEVEL-HELD, never a pulse (every IRQ crosses
    into cpu_core_clk through a plain 2-FF sync in soc_top, which can miss a pulse).

CYCLE-SAMPLING HAZARD (learned on PWM / WDT / TRNG / I2C): a value read straight after
`await RisingEdge` is the PRE-edge value.  Every internal-state sample below therefore goes
RisingEdge FIRST and then settles through Timer(1, "step") (inside `_Dev.peek`, which also drives
an idle bus's paddr so it is side-effect free), so each sample is the settled post-edge state of a
KNOWN edge and none is duplicated or skipped.  Crypto has no read-snoop registers, so plain APB
reads are safe too; peek is simply the right tool for sampling STATUS mid-operation.  Tests that
align an APB ACCESS phase with a specific internal edge (set-beats-clear, busy-boundary) drive the
raw SETUP / ACCESS phases from `_Dev.timed_write`, counted from the edge E that `_Dev.start`
returns on.

DECISIONS the spec left open (or resolved inside the contract).  Writing the tests first is what
pins them, so they are asserted HERE and the RTL implements what this file asserts:

  D1. MODE AND START ARE NEVER WRITTEN IN ONE TRANSFER BY THIS SUITE.  The contract derives
      mode_w from the bank register (regs_o[CTRL]), whose value during the START write's own
      ACCESS cycle is the PRE-write one, so a single write that both changes the mode and sets
      START would run the OLD mode.  The suite always writes CTRL (no start) first and CTRL|START
      second (`_Dev.start`), and does NOT pin the single-write behaviour.  Reported to the
      reviewer as a contract under-specification.
  D2. DONE IS STICKY ACROSS A NEW START: a START does not clear it, so software must W1C
      IRQ_CLR[0] before polling (every helper here does).  test_crypto_done_sticky_across_start.
  D3. START WHILE BUSY IS SILENTLY IGNORED, INCLUDING ON THE COMPLETION EDGE ITSELF (the FSM is
      still busy during that cycle); one edge later it is accepted.  No status bit, no pslverr.
      test_crypto_start_while_busy_ignored, test_crypto_start_at_busy_boundary.
  D4. ILLEGAL OPS ARE HANG-FREE: mode 3, an AES start with key_valid = 0, and a mode whose core is
      compiled out all take the 2-edge zero-length path -- busy pulses for one edge, done and
      IRQ_STAT set (so an enabled irq_o fires), and NO DOUT / DIGEST / IV writeback.  A start that
      is silently dropped would satisfy "do not hang the FSM" but hang a `while (!done);` driver.
      DONE DOES NOT IMPLY VALID DATA.  test_crypto_illegal_mode3_is_hang_free,
      test_crypto_start_without_key_is_hang_free, test_crypto_compiled_out_core_is_hang_free.
  D5. SHA does NOT need a key (key_valid gates only ECB/CTR).
      test_crypto_start_without_key_is_hang_free.
  D6. DOUT / DIGEST VALIDITY WINDOW: valid from one completion edge until the next, so a read
      taken while a new operation is in flight returns the PREVIOUS result, never a partial round
      state.  test_crypto_dout_digest_hold_previous_result_while_busy.
  D7. A KEY WRITE WHILE BUSY IS REJECTED (any operation, SHA included): the shadow is unchanged,
      STATUS[3] latches.  STATUS[3] clears on reset, on IRQ_CLR[1] and on an accepted key write;
      IRQ_CLR[0] does not touch it and IRQ_CLR[1] does not touch done.
      test_crypto_key_write_while_busy_is_rejected, test_crypto_key_rejected_clear_paths.
  D8. DIN PUSHES WHILE BUSY AND PARTIAL-STROBE DIN WRITES ARE SILENTLY DROPPED, with NO status bit
      (a documented asymmetry with key_write_rejected).  CTR is what forces the busy rule: the
      plaintext is consumed at the COMPLETION edge.  test_crypto_din_push_while_busy_is_dropped,
      test_crypto_din_partial_strobe_is_dropped.
  D9. KEY HAS NO READBACK PATH, so key loading is provable ONLY through known-answer vectors:
      the FIPS-197 tests are the key-load tests.  test_crypto_key_regs_read_zero_forever.
  D10. key_valid = all four words written, in any order, cleared ONLY by reset: a partial rewrite
      leaves it 1 over a mixed key (software's problem).  A zero-strobe key write is NOT pinned.
      test_crypto_key_valid_semantics.
  D11. IV same-cycle collision: a software write to IV3 on the completion edge BEATS the hardware
      increment (IV is a real RW register; software is re-seeding), whereas software cannot beat
      the hardware on the WMASK = 0 words (DOUT).  Writing IV3 mid-operation otherwise corrupts
      the counter and is software's responsibility -- not asserted.
      test_crypto_iv_sw_write_beats_hw_increment, test_crypto_ro_regs_ignore_writes.
  D12. SBOX_PARALLEL = 4 is BIT-IDENTICAL to 16 and differs only in latency (41 vs 11).
      test_crypto_sbox4_is_bit_identical_and_41_cycles.
  D13. The elaboration-guard tests shell out to `verilator --lint-only -G<PARAM>=<bad>` and
      require BOTH a non-zero exit AND the offending PARAMETER NAME in the output (the generate
      block labels themselves are not printed by Verilator).  The RTL source list is NOT
      hardcoded here: it is read from this directory's Makefile CRYPTO_SOURCES through
      tools/verif/check_source_closure.py's own parser, so it cannot drift from `make crypto`;
      tb_crypto.sv is swapped for a throwaway single-instance top generated at test time (a -G
      override of tb_crypto's four-instance wrapper would put two identical instances in one
      elaboration and draw a spurious VARHIDDEN -- see tb_crypto.sv).

VECTORS PINNED HERE (hardcoded as literals, independently of tb/models/aes128_model.py, whose
selftest() pins the same ones -- the double-pin tb/models/trng_lfsr_model.py / test_trng.py
established, so a silent model edit cannot move the target this suite chases):
  FIPS-197 Appendix B (key 2b7e1516..., pt 3243f6a8... -> 3925841d...), FIPS-197 Appendix C.1
  (key 000102..0f, pt 00112233..ff -> 69c4e0d8...), NIST SP 800-38A F.5.1 CTR-AES128 (four
  blocks), FIPS-180-4 "abc", "" and the 56-byte two-block message.  Every other expectation is
  computed by the model or by hashlib.

Tests (grouped; the name states the behaviour):
  register file   reset_defaults, ctrl_stored_bits_and_start_reads_zero, out_of_range_and_reserved,
                  ro_regs_ignore_writes, strobe_gating_of_start
  AES ECB         fips197_appendix_b, fips197_appendix_c1, ecb_random_vs_model,
                  sbox4_is_bit_identical_and_41_cycles
  AES CTR         ctr_sp800_38a_roundtrip, ctr_inc32_rightmost_word_only,
                  ctr_zero_din_is_raw_keystream, iv_rw_and_hw_increment_rules,
                  iv_sw_write_beats_hw_increment
  key handling    key_regs_read_zero_forever, key_valid_semantics, key_any_order_and_partial_strobe,
                  key_write_while_busy_is_rejected, key_rejected_clear_paths
  DIN             din_aperture_and_order, din_partial_strobe_is_dropped,
                  din_push_while_busy_is_dropped, din_is_a_shift_register
  SHA-256         sha256_fips_vectors, sha256_multiblock_vs_hashlib, sha256_cont_semantics
  handshake       cycle_counts, done_sticky_across_start, done_irq_stat_mirror_and_w1c,
                  set_beats_same_cycle_clear, irq_level_held_and_masked,
                  start_while_busy_ignored, start_at_busy_boundary,
                  dout_digest_hold_previous_result_while_busy, writeback_isolation,
                  reset_mid_operation
  illegal ops     illegal_mode3_is_hang_free, start_without_key_is_hang_free,
                  compiled_out_core_is_hang_free
  elaboration     elaboration_guards_reject_illegal_config, elaboration_legal_configs_pass
"""

import hashlib
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

from tb.models import aes128_model as aes  # noqa: E402

CLK_PERIOD_NS = 10  # 100 MHz -- matches SoC reference clock (same convention as test_trng.py)

# -- register byte offsets ----------------------------------------------------
CRYPTO_CTRL = 0x000
CRYPTO_STATUS = 0x004
KEY = (0x008, 0x00C, 0x010, 0x014)
IV = (0x018, 0x01C, 0x020, 0x024)
DIN = (0x028, 0x02C, 0x030, 0x034)
DOUT = (0x038, 0x03C, 0x040, 0x044)
DIGEST = tuple(0x048 + 4 * i for i in range(8))
CRYPTO_IRQ_STAT = 0x068
CRYPTO_IRQ_CLR = 0x06C
RESERVED = (0x070, 0x074, 0x078, 0x07C)
OUT_OF_RANGE = 0x080  # word index 32 -- first address past the 32-register map
N_REGS = 32

# -- CTRL fields -------------------------------------------------------------
MODE_ECB, MODE_CTR, MODE_SHA, MODE_RSVD = 0, 1, 2, 3
CTRL_START = 0x04
CTRL_IE = 0x08
CTRL_CONT = 0x10
CTRL_STORED_MASK = 0x1B  # bit 2 (START) is NOT stored

# -- STATUS bits -------------------------------------------------------------
ST_BUSY, ST_DONE, ST_KEYV, ST_REJ = 0x1, 0x2, 0x4, 0x8
CLR_DONE, CLR_REJ = 0x1, 0x2

# -- cycle counts (frozen contract Sec.1-3) --------------------------------------
N_AES_16 = 11
N_AES_4 = 41
N_SHA = 66
N_ILLEGAL = 2

# -- vectors, hardcoded INDEPENDENTLY of the model (double-pin, see docstring) -----
FIPS_B_KEY = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
FIPS_B_PT = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
FIPS_B_CT = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")
FIPS_C1_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
FIPS_C1_PT = bytes.fromhex("00112233445566778899aabbccddeeff")
FIPS_C1_CT = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
CTR_KEY = FIPS_B_KEY
CTR_IV = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
CTR_PT = tuple(
    bytes.fromhex(h)
    for h in (
        "6bc1bee22e409f96e93d7e117393172a",
        "ae2d8a571e03ac9c9eb76fac45f61b41",
        "30c81c46a35ce411e5fbc1191a0a52ef",
        "f69f2445df4f9b17ad2b417be66c3710",
    )
)
CTR_CT = tuple(
    bytes.fromhex(h)
    for h in (
        "874d6191b620e3261bef6864990db6ce",
        "9806f66b7970fdff8617187bb9a668ef",
        "5ae4df3edbd5d35e5b4f09020db03eab",
        "1e031dda2fbe03d1792170a0f3009cee",
    )
)
SHA_ABC = bytes.fromhex("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
SHA_EMPTY = bytes.fromhex("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
SHA_56 = b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"
SHA_56_DIGEST = bytes.fromhex("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1")

# -- module-level task handle list (guard against cross-test coroutine leakage) -------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _ctrl(mode: int = 0, ie: int = 0, cont: int = 0, start: int = 0) -> int:
    """Compose a CRYPTO_CTRL value."""
    return (mode & 3) | (start << 2) | (ie << 3) | (cont << 4)


def _sha_pad(msg: bytes) -> bytes:
    """FIPS-180-4 Sec.5.1.1 padding -- the TESTBENCH does software's job: 0x80, zeros, then the
    64-bit big-endian message length in bits, to a multiple of 64 bytes."""
    return msg + b"\x80" + bytes((55 - len(msg)) % 64) + (8 * len(msg)).to_bytes(8, "big")


def _words(data: bytes) -> list[int]:
    """Big-endian 32-bit words of `data` (FIPS order: word 0 carries byte 0 in [31:24])."""
    return [int.from_bytes(data[i : i + 4], "big") for i in range(0, len(data), 4)]


def _rand_bytes(rng: random.Random, n: int) -> bytes:
    return bytes(rng.randrange(256) for _ in range(n))


def _now_cycle() -> int:
    """Absolute clock-cycle index (sim time / period); only differences are meaningful."""
    return int(get_sim_time(units="ns")) // CLK_PERIOD_NS


async def _settle() -> None:
    """Let the post-edge state settle (see the CYCLE-SAMPLING HAZARD note)."""
    await Timer(1, units="step")


# ---------------------------------------------------------------------------
# One DUT instance's APB4 face + driver helpers
# ---------------------------------------------------------------------------
class _Dev:
    """Driver for one crypto_accel instance of tb_crypto (prefix "" = the primary build)."""

    def __init__(self, dut, prefix: str, name: str):
        self.dut = dut
        self.name = name
        self.apb = APB4Master(dut, prefix, dut.clk)
        for sig in ("psel", "penable", "pwrite", "paddr", "pwdata", "pstrb", "prdata", "irq_o"):
            setattr(self, sig, getattr(dut, prefix + sig))

    def __repr__(self) -> str:
        return f"<crypto {self.name}>"

    # -- raw access --------------------------------------------------------
    async def w(self, addr: int, data: int, strb: int = 0xF) -> None:
        ok = await self.apb.write(addr, data, strb)
        assert ok, f"[{self.name}] write 0x{addr:03x} returned SLVERR (this bus never SLVERRs)"

    async def r(self, addr: int) -> int:
        data, ok = await self.apb.read(addr)
        assert ok, f"[{self.name}] read 0x{addr:03x} returned SLVERR (this bus never SLVERRs)"
        return data

    async def peek(self, addr: int) -> int:
        """Side-effect-free live register sample: point the idle bus's combinational prdata at
        `addr`, settle one simulator step, read (see the CYCLE-SAMPLING HAZARD note)."""
        self.pwrite.value = 0
        self.paddr.value = addr
        await _settle()
        return int(self.prdata.value)

    async def peek_words(self, addrs) -> list[int]:
        return [await self.peek(a) for a in addrs]

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
        return await self.peek(CRYPTO_STATUS)

    async def clear_done(self) -> None:
        await self.w(CRYPTO_IRQ_CLR, CLR_DONE)

    async def load_key(self, key: bytes, order=(0, 1, 2, 3)) -> None:
        words = _words(key)
        for i in order:
            await self.w(KEY[i], words[i])

    async def set_iv(self, iv: bytes) -> None:
        for i, wd in enumerate(_words(iv)):
            await self.w(IV[i], wd)

    async def get_iv(self) -> bytes:
        return b"".join(w.to_bytes(4, "big") for w in await self.peek_words(IV))

    async def push(self, data: bytes) -> None:
        """Push `data` through the DIN aperture in order (4 words per AES block, 16 per SHA
        block), rotating through the four DIN addresses."""
        for i, wd in enumerate(_words(data)):
            await self.w(DIN[i % 4], wd)

    async def dout(self) -> bytes:
        return b"".join(w.to_bytes(4, "big") for w in await self.peek_words(DOUT))

    async def digest(self) -> bytes:
        return b"".join(w.to_bytes(4, "big") for w in await self.peek_words(DIGEST))

    async def start(self, mode: int, ie: int = 0, cont: int = 0) -> None:
        """Select the mode (no start), then write it again with START (D1).  Returns right after
        edge E, the START write's ACCESS edge."""
        await self.w(CRYPTO_CTRL, _ctrl(mode, ie, cont))
        await self.w(CRYPTO_CTRL, _ctrl(mode, ie, cont, start=1))

    async def trace(self, budget: int = 400) -> list[tuple[int, int, int]]:
        """Per-edge samples (STATUS, IRQ_STAT, irq_o) starting right after edge E (sample 1) and
        ending with the first sample whose STATUS.done is set; len() == N.  Requires done == 0
        beforehand (use clear_done) and no intervening await since `start`."""
        out: list[tuple[int, int, int]] = []
        for k in range(budget):
            if k:
                await RisingEdge(self.dut.clk)
            st = await self.peek(CRYPTO_STATUS)
            ist = await self.peek(CRYPTO_IRQ_STAT)
            out.append((st, ist, int(self.irq_o.value)))
            if st & ST_DONE:
                return out
        raise AssertionError(f"[{self.name}] STATUS.done never set within {budget} edges")

    async def run(self, mode: int, ie: int = 0, cont: int = 0) -> list[tuple[int, int, int]]:
        """clear done, start, trace to completion."""
        await self.clear_done()
        await self.start(mode, ie, cont)
        return await self.trace()

    async def ecb(self, pt: bytes) -> bytes:
        """One ECB block with the key already loaded; returns the DOUT bytes."""
        await self.clear_done()
        await self.push(pt)
        await self.start(MODE_ECB)
        await self.trace()
        return await self.dout()

    async def ctr(self, block: bytes) -> bytes:
        """One CTR block (IV and key already loaded); returns the DOUT bytes."""
        await self.clear_done()
        await self.push(block)
        await self.start(MODE_CTR)
        await self.trace()
        return await self.dout()

    async def sha(self, msg: bytes) -> bytes:
        """Hash `msg` (multi-block, TB-side padding, SHA_CONT chaining); returns the digest."""
        padded = _sha_pad(msg)
        for i in range(0, len(padded), 64):
            await self.clear_done()
            await self.push(padded[i : i + 64])
            await self.start(MODE_SHA, cont=int(i > 0))
            await self.trace()
        return await self.digest()


class _Rig:
    """The four instances of tb_crypto."""

    def __init__(self, dut):
        self.main = _Dev(dut, "", "main")
        self.v4 = _Dev(dut, "v4_", "sbox4")
        self.noaes = _Dev(dut, "noaes_", "noaes")
        self.nosha = _Dev(dut, "nosha_", "nosha")
        self.all = (self.main, self.v4, self.noaes, self.nosha)


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
    """Start the 100 MHz clock, build the four drivers and reset the DUTs."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)
    dut.rst_n.value = 0
    rig = _Rig(dut)
    await _reset(dut, rig)
    return rig


def _check_pattern(dev: _Dev, tr, n_expected: int, what: str, key_valid: int | None = None) -> None:
    """Assert the busy/done pattern of a trace: busy=1/done=0 for edges 1..N-1, busy=0/done=1 on
    edge N, IRQ_STAT[0] mirroring STATUS[1] throughout, N == n_expected."""
    n = len(tr)
    assert n == n_expected, f"[{dev.name}] {what}: done after {n} edges, contract says {n_expected}"
    for k, (st, ist, _irq) in enumerate(tr, start=1):
        last = k == n
        want = ST_DONE if last else ST_BUSY
        assert st & 0x3 == want, (
            f"[{dev.name}] {what}: STATUS=0x{st:x} after edge {k}/{n}, "
            f"expected (busy,done) bits 0x{want:x}"
        )
        assert ist == (st >> 1) & 1, (
            f"[{dev.name}] {what}: IRQ_STAT=0x{ist:x} != STATUS.done after edge {k}/{n} "
            f"(one flop, two words)"
        )
        if key_valid is not None:
            assert bool(st & ST_KEYV) == bool(key_valid), (
                f"[{dev.name}] {what}: STATUS=0x{st:x} key_valid != {key_valid} after edge {k}"
            )


# ===========================================================================
# Register file
# ===========================================================================
@cocotb.test()
async def test_crypto_reset_defaults(dut):
    """Every one of the 32 words reads 0 after reset on every build (STATUS == 0: not busy, not
    done, no key, no rejection), irq_o is low, and the block stays quiescent for 200 idle cycles
    -- nothing starts, nothing sets by itself.  KEY / DIN / IRQ_CLR / reserved words read 0 by
    construction, DOUT / DIGEST / IV by reset value."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    for d in rig.all:
        for i in range(N_REGS):
            v = await d.r(4 * i)
            assert v == 0, f"[{d.name}] word {i} (0x{4 * i:03x}) reset value 0x{v:08x}, expected 0"
        assert int(d.irq_o.value) == 0, f"[{d.name}] irq_o high out of reset"
    await ClockCycles(dut.clk, 200)
    for d in rig.all:
        st = await d.status()
        assert st == 0, f"[{d.name}] STATUS 0x{st:x} after 200 idle cycles, expected 0"
        assert int(d.irq_o.value) == 0, f"[{d.name}] irq_o rose with no operation"


@cocotb.test()
async def test_crypto_ctrl_stored_bits_and_start_reads_zero(dut):
    """CTRL stores exactly bits [4:3] and [1:0] (mask 0x1B); START (bit 2) is a write-snoop pulse
    that is NEVER stored, so it reads 0 even when written alongside every other bit.  Reserved
    bits [31:5] read 0.  The only legal reading of "W1P, reads 0".
    MUTATION TARGET: START included in the CTRL WMASK (a stored, self-clearing-by-hw start)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    for v in range(32):
        if v & CTRL_START:
            continue
        await d.w(CRYPTO_CTRL, v)
        got = await d.r(CRYPTO_CTRL)
        assert got == v, f"CTRL wrote 0x{v:02x} read 0x{got:08x}"
    await d.w(CRYPTO_CTRL, 0xFFFF_FFFB)  # everything but START
    got = await d.r(CRYPTO_CTRL)
    assert got == CTRL_STORED_MASK, (
        f"CTRL 0xFFFFFFFB read 0x{got:08x}, expected 0x1b (bit 2 / reserved masked)"
    )
    await d.w(CRYPTO_CTRL, 0xFFFF_FFE0)  # reserved bits only
    got = await d.r(CRYPTO_CTRL)
    assert got == 0, f"reserved CTRL bits stored: 0x{got:08x}"
    # START written alone (no key -> the 2-edge illegal path), then with every other bit set
    await d.w(CRYPTO_CTRL, CTRL_START)
    assert await d.r(CRYPTO_CTRL) == 0, "START bit read back non-zero"
    await d.trace()
    await d.w(CRYPTO_CTRL, 0xFFFF_FFFF)  # mode 3 + IE + CONT + START: illegal op, no hang
    got = await d.r(CRYPTO_CTRL)
    assert got == CTRL_STORED_MASK, f"CTRL 0xFFFFFFFF read 0x{got:08x}, expected 0x1b"
    await d.trace()


@cocotb.test()
async def test_crypto_out_of_range_and_reserved(dut):
    """Reserved words 28..31 and every word index >= 32 (0x080..0xFFC): a write is dropped (no
    aliasing onto CTRL / IV / DIN / KEY ...), a read returns 0, pslverr stays 0 (the bank's
    policy).  An aliasing bug would, among other things, start an operation (word 32 truncating
    onto CTRL with bit 2 set), which STATUS == 0 afterwards rules out."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    addrs = list(RESERVED) + [OUT_OF_RANGE, 0x084, 0x0FC, 0x100, 0x400, 0x7FC, 0xFFC]
    for a in addrs:
        await d.w(a, 0xFFFF_FFFF)
        got = await d.r(a)
        assert got == 0, f"address 0x{a:03x} read 0x{got:08x} after a write, expected 0"
    await ClockCycles(dut.clk, 20)
    for i in range(N_REGS):
        v = await d.peek(4 * i)
        assert v == 0, f"word {i} (0x{4 * i:03x}) became 0x{v:08x}: an out-of-range write aliased"
    assert int(d.irq_o.value) == 0


@cocotb.test()
async def test_crypto_ro_regs_ignore_writes(dut):
    """STATUS, DOUT, DIGEST and IRQ_STAT are read-only: a write is ignored with no error.  Proven
    where it matters: junk written to DIGEST / DOUT / STATUS / IRQ_STAT BETWEEN the blocks of a
    SHA chain does not corrupt the chain (the rejected 'DIGEST is RW' alternative would), and a
    software write to DOUT / DIGEST landing on the very edge hardware writes them LOSES to
    hardware (WMASK = 0 words are HW-owned; compare IV, D11).
    MUTATION TARGET: a non-zero WMASK on DIGEST / DOUT."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    padded = _sha_pad(SHA_56)  # two blocks
    assert len(padded) == 128
    await d.clear_done()
    await d.push(padded[:64])
    await d.start(MODE_SHA)
    await d.trace()
    mid_digest = await d.digest()
    mid_status = await d.status()
    for a in [CRYPTO_STATUS, CRYPTO_IRQ_STAT, *DOUT, *DIGEST]:
        await d.w(a, 0xFFFF_FFFF)
    assert await d.digest() == mid_digest, "a write to DIGEST changed the chaining value"
    assert await d.dout() == bytes(16), "a write to DOUT changed it"
    assert await d.status() == mid_status, "a write to STATUS / IRQ_STAT changed STATUS"
    await d.clear_done()
    await d.push(padded[64:])
    await d.start(MODE_SHA, cont=1)
    await d.trace()
    got = await d.digest()
    assert got == SHA_56_DIGEST == hashlib.sha256(SHA_56).digest(), (
        f"chained digest 0x{got.hex()} after junk RO writes, expected 0x{SHA_56_DIGEST.hex()}"
    )

    # SW write to DOUT0 / DIGEST0 on the exact completion edge: hardware wins.
    await d.load_key(FIPS_C1_KEY)
    await d.clear_done()
    await d.push(FIPS_C1_PT)
    await d.start(MODE_ECB)
    await d.timed_write(N_AES_16 - 1, DOUT[0], 0xDEAD_BEEF)
    await ClockCycles(dut.clk, 2)
    assert await d.dout() == FIPS_C1_CT, "SW write on the completion edge beat the hardware DOUT"
    await d.clear_done()
    await d.push(_sha_pad(b"abc"))
    await d.start(MODE_SHA)
    await d.timed_write(N_SHA - 1, DIGEST[0], 0xDEAD_BEEF)
    await ClockCycles(dut.clk, 2)
    assert await d.digest() == SHA_ABC, "SW write on the completion edge beat the hardware DIGEST"


@cocotb.test()
async def test_crypto_strobe_gating_of_start(dut):
    """START needs pstrb[0] (the byte lane holding CTRL[2]): a write of 0x4 with strobes 0b1110 or
    0b0000 starts NOTHING (and an operation that never starts never sets done), while 0b0001
    starts one.  Strobes on the stored bits are honoured: a write confined to byte lane 1 does not
    touch mode / IE / CONT.
    MUTATION TARGET: start_pulse_w not gated by strb_mask_w[2]."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_B_KEY)
    await d.push(FIPS_B_PT)
    await d.w(CRYPTO_CTRL, _ctrl(MODE_ECB))
    for strb in (0b1110, 0b0000, 0b0010, 0b0100, 0b1000):
        await d.w(CRYPTO_CTRL, CTRL_START, strb=strb)
    await ClockCycles(dut.clk, 40)
    st = await d.status()
    assert st & (ST_BUSY | ST_DONE) == 0, f"a START without strobe 0 started an op: STATUS=0x{st:x}"
    await d.w(CRYPTO_CTRL, CTRL_START, strb=0b0001)
    tr = await d.trace()
    assert len(tr) == N_AES_16
    assert await d.dout() == FIPS_B_CT
    await d.w(CRYPTO_CTRL, 0xFF, strb=0b0010)  # lane 1 only: nothing stored
    got = await d.r(CRYPTO_CTRL)
    assert got == 0, f"a lane-1 write changed CTRL to 0x{got:x}"
    await d.w(CRYPTO_CTRL, 0xFFFF_FF1B, strb=0b0001)  # lane 0 only: stored mask applies
    got = await d.r(CRYPTO_CTRL)
    assert got == CTRL_STORED_MASK, f"CTRL 0x{got:x}, expected 0x1b"


# ===========================================================================
# AES ECB
# ===========================================================================
@cocotb.test()
async def test_crypto_fips197_appendix_b(dut):
    """ECB bit-exact against the FIPS-197 Appendix B worked example (key 2b7e1516...), on every
    AES-capable build.  This IS the key-load test: KEY reads 0, so the vector is the only proof the
    shadow register got the right key in the right byte order (D9).  The literal here is asserted
    against tb/models/aes128_model.py too (double-pin).
    MUTATION TARGET: a swapped byte lane / word order on DIN, KEY or DOUT; ShiftRows in the wrong
    direction; MixColumns not skipped in round 10; a wrong key-schedule rcon."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    assert aes.encrypt_block(FIPS_B_KEY, FIPS_B_PT) == FIPS_B_CT, "model drifted from FIPS-197 B"
    for d in (rig.main, rig.v4, rig.nosha):
        await d.load_key(FIPS_B_KEY)
        st = await d.status()
        assert st & ST_KEYV, f"[{d.name}] key_valid clear after four key writes"
        got = await d.ecb(FIPS_B_PT)
        assert got == FIPS_B_CT, f"[{d.name}] ECB 0x{got.hex()} != FIPS-197 B 0x{FIPS_B_CT.hex()}"
        got = await d.ecb(FIPS_B_PT)  # same key, second block: the key persists
        assert got == FIPS_B_CT, f"[{d.name}] second ECB with the same key: 0x{got.hex()}"


@cocotb.test()
async def test_crypto_fips197_appendix_c1(dut):
    """ECB bit-exact against FIPS-197 Appendix C.1 (key 00 01 02 ... 0f, plaintext 00 11 22 ... ff),
    on every AES-capable build; DOUT0..3 also match the model's big-endian word view
    (word 0 = bytes 0..3).  The sequential key and nibble-repeating plaintext make a lane swap
    obvious.  MUTATION TARGET: as the Appendix B test."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    assert aes.encrypt_block(FIPS_C1_KEY, FIPS_C1_PT) == FIPS_C1_CT, "model drifted from FIPS C.1"
    for d in (rig.main, rig.v4, rig.nosha):
        await d.load_key(FIPS_C1_KEY)
        got = await d.ecb(FIPS_C1_PT)
        assert got == FIPS_C1_CT, (
            f"[{d.name}] ECB 0x{got.hex()} != FIPS-197 C.1 0x{FIPS_C1_CT.hex()}"
        )
        words = await d.peek_words(DOUT)
        assert tuple(words) == aes.block_to_words(FIPS_C1_CT), (
            f"[{d.name}] DOUT words {[hex(w) for w in words]}"
        )
        assert words[0] == 0x69C4E0D8, (
            f"[{d.name}] DOUT0 0x{words[0]:08x}: byte 0 must be bits [31:24]"
        )


@cocotb.test()
async def test_crypto_ecb_random_vs_model(dut):
    """16 random (key, block) pairs against tb/models/aes128_model.py: four keys, three blocks per
    key with NO key rewrite in between (the key persists and the FSM restarts cleanly back to
    back), then the next key.  ECB must leave IV and DIGEST untouched (see writeback_isolation)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0xAE5_0001)
    for _ in range(4):
        key = _rand_bytes(rng, 16)
        await d.load_key(key)
        for _ in range(3):
            pt = _rand_bytes(rng, 16)
            got = await d.ecb(pt)
            want = aes.encrypt_block(key, pt)
            assert got == want, f"key {key.hex()} pt {pt.hex()}: RTL {got.hex()} model {want.hex()}"
    assert await d.get_iv() == bytes(16), "ECB changed IV"
    assert await d.digest() == bytes(32), "ECB changed DIGEST"


@cocotb.test()
async def test_crypto_sbox4_is_bit_identical_and_41_cycles(dut):
    """The Gate A area fallback (SBOX_PARALLEL = 4) must give BIT-IDENTICAL results to 16 -- the
    FIPS vectors plus random blocks, in ECB and CTR -- and differ only in latency: 41 edges per
    block against 11 (D12).  SHA-256 is unaffected by SBOX_PARALLEL (still 66).
    MUTATION TARGET: the 4-S-box carousel losing a word (phase counter, rotate direction, or the
    round tail applied on the wrong phase)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    rng = random.Random(0x5B04)
    vectors = [(FIPS_B_KEY, FIPS_B_PT), (FIPS_C1_KEY, FIPS_C1_PT)]
    vectors += [(_rand_bytes(rng, 16), _rand_bytes(rng, 16)) for _ in range(6)]
    for key, pt in vectors:
        results = []
        for d, n in ((rig.main, N_AES_16), (rig.v4, N_AES_4)):
            await d.load_key(key)
            await d.clear_done()
            await d.push(pt)
            await d.start(MODE_ECB)
            tr = await d.trace()
            _check_pattern(d, tr, n, "ECB", key_valid=1)
            results.append(await d.dout())
        want = aes.encrypt_block(key, pt)
        assert results[0] == results[1] == want, (
            f"key {key.hex()} pt {pt.hex()}: sbox16 {results[0].hex()} sbox4 {results[1].hex()} "
            f"model {want.hex()}"
        )
    # CTR on the folded build, two blocks, against the model
    d = rig.v4
    key, iv = _rand_bytes(rng, 16), _rand_bytes(rng, 16)
    await d.load_key(key)
    await d.set_iv(iv)
    ctr = iv
    for _ in range(2):
        pt = _rand_bytes(rng, 16)
        got = await d.ctr(pt)
        assert got == aes.ctr_crypt(key, ctr, pt), f"v4 CTR block: {got.hex()}"
        ctr = aes.inc32(ctr)
    assert await d.get_iv() == ctr
    # SHA: same 66 edges on the folded build
    await d.push(_sha_pad(b"abc"))
    tr = await d.run(MODE_SHA)
    _check_pattern(d, tr, N_SHA, "SHA on the sbox4 build")
    assert await d.digest() == SHA_ABC


# ===========================================================================
# AES CTR
# ===========================================================================
@cocotb.test()
async def test_crypto_ctr_sp800_38a_roundtrip(dut):
    """CTR round-trip bit-exact: the four NIST SP 800-38A F.5.1 blocks encrypt to the published
    ciphertexts (also == the model), the IV register shows the incremented counter after EVERY
    block, and re-running the ciphertext through the same keystream (IV reset to the initial
    counter) returns the plaintext -- the property that makes an encrypt-only datapath a complete
    cipher.  Both fold factors.
    MUTATION TARGET: the XOR taken against IV or the key instead of DIN; INC32 skipped or applied
    before the encrypt; CTR decrypt routed through a different path."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    counters = [CTR_IV]
    for _ in range(4):
        counters.append(aes.inc32(counters[-1]))
    assert counters[1].hex() == "f0f1f2f3f4f5f6f7f8f9fafbfcfdff00", "INC32 model carry"
    assert counters[4].hex() == "f0f1f2f3f4f5f6f7f8f9fafbfcfdff03"
    for d in (rig.main, rig.v4):
        await d.load_key(CTR_KEY)
        await d.set_iv(CTR_IV)
        for i in range(4):
            assert await d.get_iv() == counters[i], f"[{d.name}] IV before block {i}"
            got = await d.ctr(CTR_PT[i])
            assert got == CTR_CT[i], f"[{d.name}] block {i}: 0x{got.hex()} != 0x{CTR_CT[i].hex()}"
            assert got == aes.ctr_crypt(CTR_KEY, counters[i], CTR_PT[i]), f"[{d.name}] model {i}"
            assert await d.get_iv() == counters[i + 1], f"[{d.name}] IV after block {i}"
        await d.set_iv(CTR_IV)  # decrypt: same keystream
        for i in range(4):
            got = await d.ctr(CTR_CT[i])
            assert got == CTR_PT[i], f"[{d.name}] decrypt block {i}: 0x{got.hex()}"
        assert await d.get_iv() == counters[4]


@cocotb.test()
async def test_crypto_ctr_inc32_rightmost_word_only(dut):
    """INC32 increments ONLY the rightmost word (IV3) and DISCARDS the carry: starting from
    IV3 = 0xFFFFFFFE the counters are ...FFFFFFFE, ...FFFFFFFF, ...00000000, ...00000001 with
    IV0..IV2 (00112233 44556677 8899aabb) unchanged throughout, and every keystream block (DIN =
    0, so DOUT is the raw keystream) matches the model, including the wrapped counter.
    MUTATION TARGET: carry propagating into IV2; IV0..2 being hardware-written."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    prefix = bytes.fromhex("00112233445566778899aabb")
    iv = prefix + bytes.fromhex("fffffffe")
    await d.load_key(FIPS_C1_KEY)
    await d.set_iv(iv)
    ctr = iv
    expect_iv3 = [0xFFFF_FFFF, 0x0000_0000, 0x0000_0001, 0x0000_0002]
    for i in range(4):
        got = await d.ctr(bytes(16))
        assert got == aes.encrypt_block(FIPS_C1_KEY, ctr), f"block {i}: keystream 0x{got.hex()}"
        ctr = aes.inc32(ctr)
        words = await d.peek_words(IV)
        assert words[:3] == _words(prefix), f"IV0..2 moved: {[hex(w) for w in words]}"
        assert words[3] == expect_iv3[i], f"IV3 0x{words[3]:08x}, expected 0x{expect_iv3[i]:08x}"
        assert await d.get_iv() == ctr
    assert aes.inc32(prefix + bytes.fromhex("ffffffff")) == prefix + bytes(4), "model carry"


@cocotb.test()
async def test_crypto_ctr_zero_din_is_raw_keystream(dut):
    """With DIN = 0 a CTR block is the raw keystream E(K, IV): it equals the ECB encryption of the
    IV block, which proves ECB and CTR share one datapath and the CTR XOR happens at the writeback
    against DIN (not IV, not the key).  A non-zero DIN gives keystream ^ DIN."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_C1_KEY)
    ecb = await d.ecb(FIPS_C1_PT)
    assert ecb == FIPS_C1_CT
    await d.set_iv(FIPS_C1_PT)
    got = await d.ctr(bytes(16))
    assert got == FIPS_C1_CT, f"CTR keystream 0x{got.hex()} != ECB(IV) 0x{FIPS_C1_CT.hex()}"
    await d.set_iv(FIPS_C1_PT)
    pt = bytes.fromhex("0f1e2d3c4b5a69788796a5b4c3d2e1f0")
    got = await d.ctr(pt)
    want = bytes(a ^ b for a, b in zip(FIPS_C1_CT, pt, strict=True))
    assert got == want, f"CTR 0x{got.hex()} != keystream ^ DIN 0x{want.hex()}"


@cocotb.test()
async def test_crypto_iv_rw_and_hw_increment_rules(dut):
    """IV is the one RW data register: all 32 bits of each word round-trip, byte strobes merge.
    Hardware increments IV3 by exactly one per COMPLETED CTR block and by nothing else: not by
    ECB, not by SHA, not by an illegal op (a CTR start with no key must not advance the counter,
    nor write DOUT).
    MUTATION TARGET: ctr_inc_w = done_set instead of done_set & ctr_mode; increment on the
    illegal path."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    pattern = [0xA5A5_A5A5, 0x5A5A_5A5A, 0xFFFF_FFFF, 0x0123_4567]
    for i, v in enumerate(pattern):
        await d.w(IV[i], v)
    for i, v in enumerate(pattern):
        got = await d.r(IV[i])
        assert got == v, f"IV{i} wrote 0x{v:08x} read 0x{got:08x}"
    await d.w(IV[1], 0x1122_3344, strb=0b0101)
    got = await d.r(IV[1])
    assert got == (0x5A5A_5A5A & 0xFF00_FF00) | (0x1122_3344 & 0x00FF_00FF), (
        f"IV1 merge 0x{got:08x}"
    )
    iv0 = await d.get_iv()
    # no key yet: CTR is illegal -> 2 edges, IV and DOUT untouched
    await d.push(FIPS_B_PT)
    tr = await d.run(MODE_CTR)
    _check_pattern(d, tr, N_ILLEGAL, "CTR without a key")
    assert await d.get_iv() == iv0, "an illegal CTR start advanced IV"
    assert await d.dout() == bytes(16), "an illegal CTR start wrote DOUT"
    await d.load_key(FIPS_B_KEY)
    # ECB and SHA leave IV alone
    assert await d.ecb(FIPS_B_PT) == FIPS_B_CT
    assert await d.get_iv() == iv0, "ECB changed IV"
    assert await d.sha(b"abc") == SHA_ABC
    assert await d.get_iv() == iv0, "SHA changed IV"
    # three CTR blocks -> exactly three increments
    ctr = iv0
    for _ in range(3):
        await d.ctr(FIPS_B_PT)
        ctr = aes.inc32(ctr)
        assert await d.get_iv() == ctr, "IV3 not incremented exactly once per CTR block"


@cocotb.test()
async def test_crypto_iv_sw_write_beats_hw_increment(dut):
    """D11: a software write to IV3 landing on the CTR completion edge BEATS the hardware increment
    (IV has a real WMASK, the bank's collision rule gives software the WMASK bits -- software is
    explicitly re-seeding), and the DOUT of that block is still the keystream of the PRE-write
    counter.  Documented contract, not an accident.
    MUTATION TARGET: hardware winning the IV3 collision."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    iv = bytes.fromhex("00112233445566778899aabb00000010")
    await d.load_key(FIPS_C1_KEY)
    await d.set_iv(iv)
    await d.clear_done()
    await d.push(FIPS_C1_PT)
    await d.start(MODE_CTR)
    await d.timed_write(N_AES_16 - 1, IV[3], 0x1234_5678)
    await ClockCycles(dut.clk, 2)
    st = await d.status()
    assert st & ST_DONE, f"operation did not complete, STATUS=0x{st:x}"
    words = await d.peek_words(IV)
    assert words[3] == 0x1234_5678, f"IV3 0x{words[3]:08x}: the hardware increment beat software"
    assert words[:3] == _words(iv[:12])
    assert await d.dout() == aes.ctr_crypt(FIPS_C1_KEY, iv, FIPS_C1_PT), (
        "DOUT of the colliding block"
    )


# ===========================================================================
# Key handling
# ===========================================================================
@cocotb.test()
async def test_crypto_key_regs_read_zero_forever(dut):
    """KEY0-3 read 0 ALWAYS: before any write, right after a write of all-ones, at every edge of
    an operation (the key shadow is exercised by the datapath and must not leak into the bank),
    after the operation, after a SHA run (hardware-written neighbours) and after reset.  The key
    has no readback path at all (D9), so the FIPS tests are the only proof of key loading.
    MUTATION TARGET: a non-zero WMASK or a hardware writeback on a KEY word."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.v4
    assert await d.peek_words(KEY) == [0, 0, 0, 0]
    for i, a in enumerate(KEY):
        await d.w(a, 0xFFFF_FFFF)
        assert await d.r(a) == 0, f"KEY{i} read non-zero straight after a write"
    assert await d.peek_words(KEY) == [0, 0, 0, 0]
    await d.load_key(FIPS_B_KEY)
    assert [await d.r(a) for a in KEY] == [0, 0, 0, 0], "KEY readback exposed the key"
    await d.clear_done()
    await d.push(FIPS_B_PT)
    await d.start(MODE_ECB)
    for k in range(1, N_AES_4 + 1):
        if k > 1:
            await RisingEdge(dut.clk)
        words = await d.peek_words(KEY)
        assert words == [0, 0, 0, 0], f"KEY words {[hex(w) for w in words]} visible at edge {k}"
    assert await d.dout() == FIPS_B_CT
    await d.sha(b"abc")
    assert await d.peek_words(KEY) == [0, 0, 0, 0]
    await _reset(dut, rig)
    assert await d.peek_words(KEY) == [0, 0, 0, 0]


@cocotb.test()
async def test_crypto_key_valid_semantics(dut):
    """STATUS.key_valid (D10): clear out of reset; set only once ALL FOUR distinct key words have
    been written, in any order (writing one word four times does not do it); it then stays set
    through a partial rewrite (which leaves a mixed key -- software's problem), through operations
    and through rejected writes; and is cleared ONLY by reset.  A partially rewritten key really
    is the mixed key.
    MUTATION TARGET: a write counter instead of per-word seen flags; key_valid cleared by a
    partial rewrite or by IRQ_CLR."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    assert (await d.status()) & ST_KEYV == 0
    for _ in range(4):
        await d.w(KEY[0], 0x1111_1111)
    assert (await d.status()) & ST_KEYV == 0, "key_valid set by four writes to ONE word"
    words = _words(FIPS_B_KEY)
    for n, i in enumerate((3, 1, 0, 2)):
        assert (await d.status()) & ST_KEYV == 0, (
            f"key_valid set before the 4th distinct word ({n})"
        )
        await d.w(KEY[i], words[i])
    assert (await d.status()) & ST_KEYV, "key_valid clear after all four words"
    assert await d.ecb(FIPS_B_PT) == FIPS_B_CT, "key written out of order gave the wrong result"
    # partial rewrite of one byte lane of KEY2: key_valid stays, the key is the merged key
    await d.w(KEY[2], 0xFFFF_FFFF, strb=0b0001)
    assert (await d.status()) & ST_KEYV, "a partial rewrite cleared key_valid"
    mixed = bytearray(FIPS_B_KEY)
    mixed[11] = 0xFF  # KEY2 = bytes 8..11; strobe lane 0 = bits [7:0] = byte 11
    got = await d.ecb(FIPS_B_PT)
    assert got == aes.encrypt_block(bytes(mixed), FIPS_B_PT), f"merged key result 0x{got.hex()}"
    await d.w(CRYPTO_IRQ_CLR, 0xFFFF_FFFF)
    assert (await d.status()) & ST_KEYV, "IRQ_CLR cleared key_valid"
    await _reset(dut, rig)
    assert (await d.status()) & ST_KEYV == 0, "reset did not clear key_valid"


@cocotb.test()
async def test_crypto_key_any_order_and_partial_strobe(dut):
    """KEY loads are ADDRESS-DECODED (not a shift register): any order gives the same key, and a
    key write neither pushes into nor disturbs the DIN shadow (block pushed FIRST, key loaded
    after, vector still right).  Byte-strobed key writes merge lane by lane exactly like every
    other register in the SoC: the result equals the model run on the lane-merged key.
    MUTATION TARGET: key words loaded by a shift; the byte-lane merge ignoring pstrb."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    # block first, key after, odd order
    await d.push(FIPS_C1_PT)
    await d.load_key(FIPS_C1_KEY, order=(2, 0, 3, 1))
    await d.clear_done()
    await d.start(MODE_ECB)
    await d.trace()
    assert await d.dout() == FIPS_C1_CT, "key written out of order / after the block was wrong"
    # lane-merged rewrite
    rng = random.Random(0x4B45)
    key = _rand_bytes(rng, 16)
    await d.load_key(key)
    expect = list(_words(key))
    for i, (data, strb) in enumerate(
        ((0xAABB_CCDD, 0b0101), (0x1122_3344, 0b1000), (0x5566_7788, 0b0110), (0x99AA_BBCC, 0b0001))
    ):
        await d.w(KEY[i], data, strb=strb)
        mask = sum(0xFF << (8 * b) for b in range(4) if strb >> b & 1)
        expect[i] = (expect[i] & ~mask & 0xFFFF_FFFF) | (data & mask)
    merged = b"".join(w.to_bytes(4, "big") for w in expect)
    assert merged != key
    pt = _rand_bytes(rng, 16)
    got = await d.ecb(pt)
    assert got == aes.encrypt_block(merged, pt), (
        f"merged key {merged.hex()}: RTL {got.hex()} model {aes.encrypt_block(merged, pt).hex()}"
    )


@cocotb.test()
async def test_crypto_key_write_while_busy_is_rejected(dut):
    """A key write while STATUS.busy is REJECTED and latches STATUS[3]: for each of the four KEY
    words, a write landing mid-operation leaves the shadow unchanged (this block AND the next one
    still use the original key) and key_valid stays set.  The on-the-fly key schedule would not
    need the rejection -- it is a spec/determinism requirement, so it is tested, not assumed (D7).
    Run on the 41-edge build for a wide window and once on the 11-edge build.
    MUTATION TARGET: key_accept not gated by ~busy_q; the rejected write still updating key_q."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.v4
    await d.load_key(FIPS_B_KEY)
    assert (await d.status()) & ST_REJ == 0
    for i in range(4):
        await d.clear_done()
        await d.push(FIPS_B_PT)
        await d.start(MODE_ECB)
        await d.w(KEY[i], 0xDEAD_BEEF ^ (i * 0x0101_0101))  # ACCESS at E+2, op ends at E+40
        st = await d.status()
        assert st & ST_BUSY and st & ST_REJ, f"KEY{i} write mid-op: STATUS=0x{st:x}, want busy+rej"
        assert st & ST_KEYV
        await d.trace()
        assert await d.dout() == FIPS_B_CT, f"KEY{i} write while busy changed THIS block's result"
        assert await d.ecb(FIPS_B_PT) == FIPS_B_CT, f"KEY{i} write while busy changed the key"
        await d.w(CRYPTO_IRQ_CLR, CLR_REJ)
    m = rig.main
    await m.load_key(FIPS_C1_KEY)
    await m.clear_done()
    await m.push(FIPS_C1_PT)
    await m.start(MODE_ECB)
    await m.w(KEY[0], 0x0BAD_F00D)  # ACCESS at E+2, op ends at E+10
    assert (await m.status()) & ST_REJ
    await m.trace()
    assert await m.dout() == FIPS_C1_CT
    assert await m.ecb(FIPS_C1_PT) == FIPS_C1_CT


@cocotb.test()
async def test_crypto_key_rejected_clear_paths(dut):
    """STATUS[3] key_write_rejected (D7): latches on a busy-time key write for ANY operation
    (SHA included), is sticky through completion, and clears ONLY on IRQ_CLR[1], on an accepted
    key write (so 'see rejected -> wait idle -> rewrite the key' self-clears), or reset.
    IRQ_CLR[1] does not touch done; IRQ_CLR[0] does not touch the rejection.
    MUTATION TARGET: IRQ_CLR bits crossed; the accepted-write clear missing."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_B_KEY)
    await d.clear_done()
    await d.push(_sha_pad(b"abc"))
    await d.start(MODE_SHA)
    await d.w(KEY[0], 0x1111_1111)  # lands at E+2, busy for 66 edges
    st = await d.status()
    assert st & ST_BUSY and st & ST_REJ, f"STATUS=0x{st:x} after a busy-time key write during SHA"
    await d.trace()
    assert await d.digest() == SHA_ABC
    st = await d.status()
    assert st & ST_DONE and st & ST_REJ, f"rejection not sticky through completion: 0x{st:x}"
    await d.w(CRYPTO_IRQ_CLR, CLR_REJ)  # IRQ_CLR[1]: rejection only
    st = await d.status()
    assert st & ST_REJ == 0 and st & ST_DONE, f"IRQ_CLR[1] left STATUS=0x{st:x}"
    # reject again; IRQ_CLR[0] must not clear it
    await d.clear_done()
    await d.push(_sha_pad(b"abc"))
    await d.start(MODE_SHA)
    await d.w(KEY[1], 0x2222_2222)
    await d.trace()
    await d.w(CRYPTO_IRQ_CLR, CLR_DONE)  # IRQ_CLR[0]: done only
    st = await d.status()
    assert st & ST_DONE == 0 and st & ST_REJ, f"IRQ_CLR[0] left STATUS=0x{st:x}"
    # accepted key write while idle clears the rejection (and does not touch done)
    await d.w(KEY[1], _words(FIPS_B_KEY)[1])
    st = await d.status()
    assert st & ST_REJ == 0 and st & ST_KEYV, f"an accepted key write left STATUS=0x{st:x}"
    assert await d.ecb(FIPS_B_PT) == FIPS_B_CT, "the recovery sequence must leave a working key"


# ===========================================================================
# DIN shadow
# ===========================================================================
@cocotb.test()
async def test_crypto_din_aperture_and_order(dut):
    """DIN0-3 are a 4-word aperture onto ONE shift register: the four addresses read 0 forever,
    WHICH address is written is irrelevant (the same block through addresses 2,0,3,1 or through
    DIN0 four times gives the same ciphertext) and the WRITE ORDER is the contract (the words
    pushed in reverse order encrypt as the word-reversed block).  The same holds for the 16-word
    SHA block.
    MUTATION TARGET: DIN decoded as four separate words; the shift in the wrong direction."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    for a in DIN:
        await d.w(a, 0xFFFF_FFFF)
        assert await d.r(a) == 0, f"DIN 0x{a:03x} readback non-zero"
    await d.load_key(FIPS_C1_KEY)
    words = _words(FIPS_C1_PT)
    for addr_order in ((2, 0, 3, 1), (0, 0, 0, 0), (3, 3, 1, 1)):
        await d.clear_done()
        for wd, ai in zip(words, addr_order, strict=True):
            await d.w(DIN[ai], wd)
        await d.start(MODE_ECB)
        await d.trace()
        got = await d.dout()
        assert got == FIPS_C1_CT, f"addresses {addr_order}: 0x{got.hex()} != 0x{FIPS_C1_CT.hex()}"
    rev = aes.words_to_block(list(reversed(words)))
    await d.clear_done()
    for wd in reversed(words):
        await d.w(DIN[0], wd)
    await d.start(MODE_ECB)
    await d.trace()
    got = await d.dout()
    assert got == aes.encrypt_block(FIPS_C1_KEY, rev) != FIPS_C1_CT, (
        "write order is not the contract"
    )
    # SHA block through permuted addresses
    block = _sha_pad(b"abc")
    await d.clear_done()
    for i, wd in enumerate(_words(block)):
        await d.w(DIN[(i * 3 + 1) % 4], wd)
    await d.start(MODE_SHA)
    await d.trace()
    assert await d.digest() == SHA_ABC


@cocotb.test()
async def test_crypto_din_partial_strobe_is_dropped(dut):
    """D8: a partial-strobe write to DIN is DROPPED (a byte-granular push into a shift register
    has no defined meaning): pushing a block with junk writes of strobes 0b0111, 0b1110, 0b0001,
    0b0000 interleaved still encrypts the clean block, and the write reports no error.
    MUTATION TARGET: din_push_w not requiring pstrb == 4'hF."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_B_KEY)
    await d.clear_done()
    junk = (0b0111, 0b1110, 0b0001, 0b0000, 0b1000)
    for i, wd in enumerate(_words(FIPS_B_PT)):
        await d.w(DIN[(i + 1) % 4], 0xBAD0_BAD0 + i, strb=junk[i])
        await d.w(DIN[i % 4], wd)
    await d.w(DIN[0], 0xFFFF_FFFF, strb=junk[4])
    await d.start(MODE_ECB)
    await d.trace()
    got = await d.dout()
    assert got == FIPS_B_CT, f"junk partial-strobe DIN writes leaked in: 0x{got.hex()}"


@cocotb.test()
async def test_crypto_din_push_while_busy_is_dropped(dut):
    """D8: DIN pushes while busy are REJECTED, with no status bit.  The reason is CTR: the
    plaintext is XORed at the COMPLETION edge, so a push accepted mid-operation would corrupt the
    block.  Junk pushed during an in-flight CTR block (4 on the 41-edge build, 1 on the 11-edge
    one) leaves the result equal to the model, STATUS shows no new bit, and a following clean
    push/run is unaffected.
    MUTATION TARGET: din_push_w not gated by ~busy_q."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    rng = random.Random(0xD1D1)
    for d, n_junk in ((rig.v4, 4), (rig.main, 1)):
        key, iv, pt = _rand_bytes(rng, 16), _rand_bytes(rng, 16), _rand_bytes(rng, 16)
        await d.load_key(key)
        await d.set_iv(iv)
        await d.clear_done()
        await d.push(pt)
        await d.start(MODE_CTR)
        for j in range(n_junk):
            await d.w(DIN[j % 4], 0xBAD0_0000 + j)
        st = await d.status()
        assert st & (ST_REJ | ST_KEYV) == ST_KEYV, f"[{d.name}] DIN push set a status bit: 0x{st:x}"
        await d.trace()
        got = await d.dout()
        want = aes.ctr_crypt(key, iv, pt)
        assert got == want, f"[{d.name}] junk DIN during CTR: RTL {got.hex()} model {want.hex()}"
        pt2 = _rand_bytes(rng, 16)
        got = await d.ctr(pt2)
        assert got == aes.ctr_crypt(key, aes.inc32(iv), pt2), f"[{d.name}] next block after junk"


@cocotb.test()
async def test_crypto_din_is_a_shift_register(dut):
    """DIN is a shift register with no push pointer: only the LAST 4 words (AES) / 16 words (SHA)
    pushed before START matter, so stale words ahead of the block are ignored.  AES: 8 words
    pushed (junk first) on the full build and on the 128-bit-shadow EN_SHA=0 build; SHA: 20 words
    pushed on the SHA-capable builds (including the EN_AES=0 one).
    MUTATION TARGET: a load counter / push pointer that stops accepting after N words."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    for d in (rig.main, rig.nosha):
        await d.load_key(FIPS_B_KEY)
        await d.clear_done()
        await d.push(bytes(range(16)))  # four junk words ...
        await d.push(FIPS_B_PT)  # ... then the real block
        await d.start(MODE_ECB)
        await d.trace()
        got = await d.dout()
        assert got == FIPS_B_CT, f"[{d.name}] stale DIN words leaked into the block: 0x{got.hex()}"
    for d in (rig.main, rig.noaes):
        await d.clear_done()
        await d.push(bytes(range(16)))  # four junk words ...
        await d.push(_sha_pad(b"abc"))  # ... then the real 16-word block
        await d.start(MODE_SHA)
        await d.trace()
        got = await d.digest()
        assert got == SHA_ABC, (
            f"[{d.name}] stale DIN words leaked into the SHA block: 0x{got.hex()}"
        )


# ===========================================================================
# SHA-256
# ===========================================================================
@cocotb.test()
async def test_crypto_sha256_fips_vectors(dut):
    """SHA-256 against the FIPS-180-4 vectors "abc" (one block), "" (one padded block) and the
    56-byte message (TWO blocks, chained through SHA_CONT), on every SHA-capable build -- each also
    equal to hashlib.  DIGEST0[31:24] is the first byte of the digest, so no byte swap is needed.
    MUTATION TARGET: a swapped word / byte order on DIN or DIGEST; a wrong H0 constant or K entry;
    the rolling W schedule off by a tap."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    assert hashlib.sha256(b"abc").digest() == SHA_ABC, "hashlib / hardcoded vector disagree"
    assert hashlib.sha256(b"").digest() == SHA_EMPTY
    assert hashlib.sha256(SHA_56).digest() == SHA_56_DIGEST
    for d in (rig.main, rig.v4, rig.noaes):
        for msg, want in ((b"abc", SHA_ABC), (b"", SHA_EMPTY), (SHA_56, SHA_56_DIGEST)):
            got = await d.sha(msg)
            assert got == want, f"[{d.name}] SHA-256({msg!r}) = {got.hex()}, expected {want.hex()}"
        words = await d.peek_words(DIGEST)
        assert words[0] == 0x248D_6A61, (
            f"[{d.name}] DIGEST0 0x{words[0]:08x}: MSB of H0 must be [31:24]"
        )


@cocotb.test()
async def test_crypto_sha256_multiblock_vs_hashlib(dut):
    """Bit-exact against hashlib.sha256 over multi-block chains: message lengths straddling every
    padding boundary (0, 1, 3, 55, 56, 63, 64, 65, 111, 112, 119, 120, 127, 128, 200, 263) and a
    1000-byte (16-block) message, random content.  The testbench supplies padding and length;
    block 1 runs with SHA_CONT = 0, every later block with SHA_CONT = 1.  Consecutive messages
    run back to back with no reset, so the SHA_CONT = 0 restart is proven too."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0x5A256)
    lengths = [0, 1, 3, 55, 56, 63, 64, 65, 111, 112, 119, 120, 127, 128, 200, 263, 1000]
    for n in lengths:
        msg = _rand_bytes(rng, n)
        got = await d.sha(msg)
        want = hashlib.sha256(msg).digest()
        assert got == want, f"len {n}: RTL {got.hex()} hashlib {want.hex()}"


@cocotb.test()
async def test_crypto_sha256_cont_semantics(dut):
    """CTRL[4] SHA_CONT: 0 = start from the FIPS-180-4 H0 constants EVEN THOUGH DIGEST holds an
    old chain, 1 = continue from the current DIGEST.  Proven with a block that is itself a valid
    one-block message ("abc"): after an unrelated block, X with CONT = 0 is exactly SHA-256("abc"),
    while the same X with CONT = 1 is something else (and reproducible).  The chain also survives
    an AES operation in the middle of a hash (DIGEST is the chain; AES must not touch it).
    MUTATION TARGET: SHA_CONT ignored (always H0 or always DIGEST); the chain clobbered by AES."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    rng = random.Random(0xC0A7)
    block_x = _sha_pad(b"abc")
    block_a = _rand_bytes(rng, 64)

    async def one_block(block: bytes, cont: int) -> bytes:
        await d.clear_done()
        await d.push(block)
        await d.start(MODE_SHA, cont=cont)
        await d.trace()
        return await d.digest()

    d_a = await one_block(block_a, 0)
    assert d_a != bytes(32)
    assert await one_block(block_x, 0) == SHA_ABC, "CONT=0 did not restart from H0"
    await one_block(block_a, 0)
    chained = await one_block(block_x, 1)
    assert chained not in (SHA_ABC, d_a), "CONT=1 did not continue from DIGEST"
    await one_block(block_a, 0)
    assert await one_block(block_x, 1) == chained, (
        "a chained block is not a pure function of DIGEST"
    )
    # AES in the middle of a two-block hash
    await d.load_key(FIPS_B_KEY)
    padded = _sha_pad(SHA_56)
    await one_block(padded[:64], 0)
    assert await d.ecb(FIPS_B_PT) == FIPS_B_CT
    assert await one_block(padded[64:], 1) == SHA_56_DIGEST, "an AES op disturbed the SHA chain"


# ===========================================================================
# Handshake, status, interrupt
# ===========================================================================
@cocotb.test()
async def test_crypto_cycle_counts(dut):
    """Measured cycle counts match the contract, from the START write's ACCESS edge E, with the
    exact busy/done pattern on every edge and IRQ_STAT mirroring STATUS.done on every edge:
    ECB and CTR 11 edges (SBOX_PARALLEL = 16) / 41 (= 4), SHA-256 66, any illegal op 2.  The
    illegal ops here are an AES start with no key (key_valid pinned 0) and mode 3.
    MUTATION TARGET: an extra or missing whitening / final-add cycle; busy not covering the whole
    operation; done set a cycle early or late."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    for d, n_aes in ((rig.main, N_AES_16), (rig.v4, N_AES_4)):
        await d.push(FIPS_B_PT)
        tr = await d.run(MODE_ECB)
        _check_pattern(d, tr, N_ILLEGAL, "ECB without a key", key_valid=0)
        await d.load_key(FIPS_B_KEY)
        tr = await d.run(MODE_ECB)
        _check_pattern(d, tr, n_aes, "ECB", key_valid=1)
        assert await d.dout() == FIPS_B_CT
        tr = await d.run(MODE_CTR)
        _check_pattern(d, tr, n_aes, "CTR", key_valid=1)
        await d.clear_done()
        await d.push(_sha_pad(b"abc"))
        await d.start(MODE_SHA)
        tr = await d.trace()
        _check_pattern(d, tr, N_SHA, "SHA-256", key_valid=1)
        assert await d.digest() == SHA_ABC
        tr = await d.run(MODE_RSVD)
        _check_pattern(d, tr, N_ILLEGAL, "mode 3", key_valid=1)


@cocotb.test()
async def test_crypto_done_sticky_across_start(dut):
    """D2: done is sticky and a new START does NOT clear it: with done already set, a second
    operation runs with done still reading 1 on every edge, and busy (not done) is what tells the
    driver it finished -- 11 edges.  Software must W1C before polling; only IRQ_CLR[0] clears it.
    MUTATION TARGET: START clearing done."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_B_KEY)
    assert await d.ecb(FIPS_B_PT) == FIPS_B_CT
    assert (await d.status()) & ST_DONE
    await d.push(FIPS_B_PT)
    await d.start(MODE_ECB)  # done still set
    n = 0
    for k in range(1, 40):
        if k > 1:
            await RisingEdge(dut.clk)
        st = await d.peek(CRYPTO_STATUS)
        assert st & ST_DONE, f"done cleared by a new START (edge {k}, STATUS=0x{st:x})"
        if not st & ST_BUSY:
            n = k
            break
    assert n == N_AES_16, f"busy fell after {n} edges, expected {N_AES_16}"
    await ClockCycles(dut.clk, 20)
    assert (await d.status()) & ST_DONE, "done not sticky while idle"
    await d.clear_done()
    assert (await d.status()) & ST_DONE == 0


@cocotb.test()
async def test_crypto_done_irq_stat_mirror_and_w1c(dut):
    """STATUS[1] done and IRQ_STAT[0] are the SAME flop mirrored into two words (D-plan: not two
    pieces of state): they agree on every sampled edge across reset, an operation, the sticky idle
    period and every clear, and IRQ_STAT's other bits read 0.  W1C is by write-snoop on IRQ_CLR[0]
    honouring pstrb: strobes without lane 0, or data with bit 0 clear, clear nothing; IRQ_CLR
    reads 0; writes to STATUS / IRQ_STAT do nothing.
    MUTATION TARGET: two separate done flops; IRQ_CLR ignoring pstrb."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main

    async def mirror(what: str) -> int:
        st = await d.peek(CRYPTO_STATUS)
        ist = await d.peek(CRYPTO_IRQ_STAT)
        assert ist == (st >> 1) & 1, f"{what}: IRQ_STAT=0x{ist:x} vs STATUS=0x{st:x}"
        return ist

    assert await mirror("reset") == 0
    await d.load_key(FIPS_B_KEY)
    await d.clear_done()
    await d.push(FIPS_B_PT)
    await d.start(MODE_ECB)
    _check_pattern(d, await d.trace(), N_AES_16, "ECB")
    for _ in range(10):
        assert await mirror("idle after done") == 1
        await d.next_cycle()
    await d.w(CRYPTO_IRQ_CLR, 0x1, strb=0b1110)  # no lane 0
    assert await mirror("clear without lane 0") == 1
    await d.w(CRYPTO_IRQ_CLR, 0xFFFF_FFFE)  # bit 0 clear
    assert await mirror("clear with bit 0 low") == 1
    await d.w(CRYPTO_STATUS, 0)
    await d.w(CRYPTO_IRQ_STAT, 0)
    assert await mirror("write to RO words") == 1
    await d.w(CRYPTO_IRQ_CLR, 0x1)
    assert await mirror("W1C") == 0
    await d.w(CRYPTO_IRQ_CLR, 0xFFFF_FFFF)
    assert await mirror("clear when already clear") == 0
    assert await d.r(CRYPTO_IRQ_CLR) == 0, "IRQ_CLR is not zero on read"


@cocotb.test()
async def test_crypto_set_beats_same_cycle_clear(dut):
    """The sticky done is SET-WINS: an IRQ_CLR[0] write whose ACCESS edge is exactly the completion
    edge loses to the hardware set, so a completion is never lost to a racing clear -- whether
    done was clear beforehand (case A) or already set (case B, the case a clear-wins flop gets
    wrong).  One edge EARLIER the clear takes (done set before, cleared, then set again by the
    completion -> 1); one edge LATER it clears the freshly set done -> 0.  Alignment is driven
    from the START edge E with raw SETUP/ACCESS phases (completion edge = E + 10).
    MUTATION TARGET: done_d = (done_q | set) & ~clr (clear beats set)."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_B_KEY)
    rng = random.Random(0x5E7C)
    comp = N_AES_16 - 1  # completion edge, relative to E
    cases = (
        ("A: clear on the completion edge, done was 0", False, comp, 1),
        ("B: clear on the completion edge, done was 1", True, comp, 1),
        ("C: clear one edge before completion, done was 1", True, comp - 1, 1),
        ("D: clear one edge after completion", False, comp + 1, 0),
    )
    for what, pre_done, rel, want_done in cases:
        await d.clear_done()
        if pre_done:
            await d.ecb(_rand_bytes(rng, 16))
            assert (await d.status()) & ST_DONE
        pt = _rand_bytes(rng, 16)
        await d.push(pt)
        await d.start(MODE_ECB)
        await d.timed_write(rel, CRYPTO_IRQ_CLR, CLR_DONE)
        await ClockCycles(dut.clk, 4)
        st = await d.status()
        assert st & ST_BUSY == 0, f"{what}: still busy, STATUS=0x{st:x}"
        assert bool(st & ST_DONE) == bool(want_done), (
            f"{what}: STATUS=0x{st:x}, done should be {want_done}"
        )
        assert await d.dout() == aes.encrypt_block(FIPS_B_KEY, pt), f"{what}: wrong DOUT"


@cocotb.test()
async def test_crypto_irq_level_held_and_masked(dut):
    """irq_o == done & CTRL[3], on EVERY sampled edge of an operation (so it rises with done, not
    before), and is LEVEL-HELD: with no clear it stays high on 100 consecutive cycles (a pulse
    would be missed by the plain 2-FF sync in soc_top).  CTRL[3] masks irq_o ONLY: with IE = 0
    STATUS / IRQ_STAT still show done, and re-enabling it raises the interrupt again (a level, not
    an edge latched at done time).  W1C drops it and it stays low.  An illegal op (mode 3) raises
    it too.  With IE = 0 the whole operation never raises irq_o.
    MUTATION TARGET: irq_o as a one-cycle pulse; IE masking STATUS; irq_o not following IE."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_B_KEY)
    await d.push(FIPS_B_PT)
    for ie in (0, 1):
        tr = await d.run(MODE_ECB, ie=ie)
        _check_pattern(d, tr, N_AES_16, f"ECB ie={ie}")
        for k, (st, _ist, irq) in enumerate(tr, start=1):
            assert irq == (1 if (st & ST_DONE) and ie else 0), (
                f"ie={ie}: irq_o={irq} with STATUS=0x{st:x} after edge {k}/{len(tr)}"
            )
    for i in range(100):  # still ie=1, done never cleared
        assert int(d.irq_o.value) == 1, f"irq_o dropped after {i} cycles with no clear"
        await d.next_cycle()
    await d.w(CRYPTO_CTRL, _ctrl(MODE_ECB, ie=0))  # mask
    await d.next_cycle()
    assert int(d.irq_o.value) == 0, "irq_o not masked by CTRL[3]"
    st = await d.status()
    assert st & ST_DONE and await d.peek(CRYPTO_IRQ_STAT) == 1, "IE=0 masked STATUS / IRQ_STAT"
    await d.w(CRYPTO_CTRL, _ctrl(MODE_ECB, ie=1))  # unmask
    await d.next_cycle()
    assert int(d.irq_o.value) == 1, "re-enabling IE did not raise the pending interrupt"
    await d.w(CRYPTO_IRQ_CLR, CLR_DONE)
    await d.next_cycle()
    for _ in range(50):
        assert int(d.irq_o.value) == 0, "irq_o high after W1C"
        await d.next_cycle()
    tr = await d.run(MODE_RSVD, ie=1)  # the zero-length path still interrupts
    _check_pattern(d, tr, N_ILLEGAL, "mode 3 ie=1")
    assert [irq for _st, _ist, irq in tr] == [0, 1], f"illegal-op irq pattern {[t[2] for t in tr]}"


@cocotb.test()
async def test_crypto_start_while_busy_ignored(dut):
    """D3: a START while busy is SILENTLY ignored -- no status bit, no error, no queued second
    operation.  Three extra STARTs during a CTR block (41-edge build) and one during a SHA block:
    the operation still takes exactly 41 / 66 edges, IV3 advances ONCE, the result is the
    single-block result, and after a W1C nothing re-asserts done for 150 cycles.
    MUTATION TARGET: a START in C_BUSY restarting or queueing the core."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    rng = random.Random(0x57A7)
    d = rig.v4
    key, pt = _rand_bytes(rng, 16), _rand_bytes(rng, 16)
    iv = _rand_bytes(rng, 12) + (0x10).to_bytes(4, "big")
    await d.load_key(key)
    await d.set_iv(iv)
    await d.clear_done()
    await d.push(pt)
    await d.start(MODE_CTR)
    t_e = _now_cycle()
    for _ in range(3):
        await d.w(CRYPTO_CTRL, _ctrl(MODE_CTR, start=1))
    n = 0
    while True:
        st = await d.peek(CRYPTO_STATUS)
        if st & ST_DONE:
            n = _now_cycle() - t_e + 1
            break
        assert _now_cycle() - t_e < 100, "operation never completed"
        await RisingEdge(dut.clk)
    assert n == N_AES_4, f"re-STARTs moved completion to edge {n}, expected {N_AES_4}"
    assert await d.dout() == aes.ctr_crypt(key, iv, pt)
    assert await d.get_iv() == aes.inc32(iv), "IV3 advanced more than once"
    await d.clear_done()
    await ClockCycles(dut.clk, 150)
    st = await d.status()
    assert st & (ST_BUSY | ST_DONE) == 0, f"a queued second operation ran: STATUS=0x{st:x}"
    assert await d.get_iv() == aes.inc32(iv)
    # SHA: one extra START mid-block
    m = rig.main
    await m.clear_done()
    await m.push(_sha_pad(b"abc"))
    await m.start(MODE_SHA)
    t_e = _now_cycle()
    await m.w(CRYPTO_CTRL, _ctrl(MODE_SHA, start=1))
    while True:
        st = await m.peek(CRYPTO_STATUS)
        if st & ST_DONE:
            break
        assert _now_cycle() - t_e < 200, "SHA never completed"
        await RisingEdge(dut.clk)
    assert _now_cycle() - t_e + 1 == N_SHA
    assert await m.digest() == SHA_ABC
    await m.clear_done()
    await ClockCycles(dut.clk, 150)
    assert (await m.status()) & (ST_BUSY | ST_DONE) == 0, "a queued SHA block ran"


@cocotb.test()
async def test_crypto_start_at_busy_boundary(dut):
    """D3 at the boundary: a START whose ACCESS edge is the COMPLETION edge itself (the FSM is
    still busy that cycle) is ignored -- IV3 advances once and no second block ever starts; a
    START one edge LATER is accepted and runs a full second block (IV3 advances twice, DOUT is
    the keystream of the SECOND counter XOR the unchanged DIN, again 11 edges).  Driven with raw
    phases from the START edge E.
    MUTATION TARGET: START accepted on done_set (busy_d instead of busy_q); START lost one edge
    after completion."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    iv = bytes.fromhex("00112233445566778899aabb00000010")
    pt = FIPS_C1_PT
    start_word = _ctrl(MODE_CTR, start=1)
    await d.load_key(FIPS_C1_KEY)
    comp = N_AES_16 - 1  # completion edge relative to E

    # (1) START on the completion edge: ignored
    await d.set_iv(iv)
    await d.clear_done()
    await d.push(pt)
    await d.start(MODE_CTR)
    await d.timed_write(comp, CRYPTO_CTRL, start_word)
    await ClockCycles(dut.clk, 3)
    st = await d.status()
    assert st & ST_BUSY == 0 and st & ST_DONE, f"STATUS=0x{st:x} after the boundary START"
    await ClockCycles(dut.clk, 40)
    assert (await d.status()) & ST_BUSY == 0, "the boundary START started a second block"
    assert await d.get_iv() == aes.inc32(iv), "IV3 advanced twice for a boundary START"
    assert await d.dout() == aes.ctr_crypt(FIPS_C1_KEY, iv, pt)

    # (2) START one edge after completion: accepted
    await d.set_iv(iv)
    await d.clear_done()
    await d.start(MODE_CTR)
    t_e = _now_cycle()
    await d.timed_write(comp + 1, CRYPTO_CTRL, start_word)
    t_e2 = _now_cycle()  # edge E2 of the second operation
    assert t_e2 - t_e == comp + 1
    n = 0
    for k in range(1, 40):
        if k > 1:
            await RisingEdge(dut.clk)
        st = await d.peek(CRYPTO_STATUS)
        assert k > 1 or st & ST_BUSY, f"second block not running right after its START (0x{st:x})"
        if not st & ST_BUSY:
            n = k
            break
    assert n == N_AES_16, f"second block took {n} edges, expected {N_AES_16}"
    assert await d.get_iv() == aes.inc32(aes.inc32(iv)), "IV3 not advanced twice"
    want = aes.ctr_crypt(FIPS_C1_KEY, aes.inc32(iv), pt)
    assert await d.dout() == want, "second block is not keystream(IV+1) ^ DIN"


@cocotb.test()
async def test_crypto_dout_digest_hold_previous_result_while_busy(dut):
    """D6, the validity window: a read taken while a new operation is in flight returns the
    PREVIOUS result, never a partial round state -- DOUT / DIGEST equal the old value on EVERY
    edge 1 .. N-1 and the new value appears exactly with done on edge N ("DOUT/DIGEST are never
    garbage; they are either current or one operation stale").  AES on both fold factors (the
    41-edge one also through real APB reads taken inside the window), SHA-256 on the full build.
    MUTATION TARGET: round state written straight into the bank result registers; the result
    visible a cycle before done."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    rng = random.Random(0x7A11D)
    for d, n_aes in ((rig.main, N_AES_16), (rig.v4, N_AES_4)):
        key = _rand_bytes(rng, 16)
        await d.load_key(key)
        pt1, pt2 = _rand_bytes(rng, 16), _rand_bytes(rng, 16)
        res1 = await d.ecb(pt1)
        assert res1 == aes.encrypt_block(key, pt1)
        res2 = aes.encrypt_block(key, pt2)
        assert res1 != res2
        await d.clear_done()
        await d.push(pt2)
        await d.start(MODE_ECB)
        t_e = _now_cycle()
        if d is rig.v4:  # real APB reads inside the window (8 edges of a 41-edge operation)
            prev_words = _words(res1)
            for a, pw in zip(DOUT, prev_words, strict=True):
                got = await d.r(a)
                assert got == pw, (
                    f"[{d.name}] in-flight APB read of 0x{a:03x}: 0x{got:08x} != 0x{pw:08x}"
                )
        while True:
            st = await d.peek(CRYPTO_STATUS)
            cur = await d.dout()
            k = _now_cycle() - t_e + 1
            if st & ST_DONE:
                assert k == n_aes, f"[{d.name}] done after {k} edges, expected {n_aes}"
                assert cur == res2, (
                    f"[{d.name}] DOUT 0x{cur.hex()} at done, expected 0x{res2.hex()}"
                )
                break
            assert cur == res1, f"[{d.name}] DOUT changed to 0x{cur.hex()} at edge {k} before done"
            assert k < n_aes, f"[{d.name}] never completed"
            await RisingEdge(dut.clk)
    # SHA-256
    d = rig.main
    first = await d.sha(b"abc")
    assert first == SHA_ABC
    msg2 = b"abd"
    want2 = hashlib.sha256(msg2).digest()
    await d.clear_done()
    await d.push(_sha_pad(msg2))
    await d.start(MODE_SHA)
    t_e = _now_cycle()
    while True:
        st = await d.peek(CRYPTO_STATUS)
        cur = await d.digest()
        k = _now_cycle() - t_e + 1
        if st & ST_DONE:
            assert k == N_SHA, f"SHA done after {k} edges"
            assert cur == want2, f"DIGEST 0x{cur.hex()} at done, expected 0x{want2.hex()}"
            break
        assert cur == first, f"DIGEST changed to 0x{cur.hex()} at edge {k} before done"
        assert k < N_SHA
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_crypto_writeback_isolation(dut):
    """Each operation writes ONLY its own result registers: ECB leaves IV and DIGEST alone; SHA
    leaves DOUT and IV alone; CTR changes DOUT and IV3 but never DIGEST; an illegal op writes
    nothing at all.  (The bank words ARE the result registers, so a stray hw_wen would show
    immediately.)
    MUTATION TARGET: aes_wb_w not gated by the mode (DOUT written on a SHA completion); sha_wb_w
    firing on AES completion."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    await d.load_key(FIPS_C1_KEY)
    dout1 = await d.ecb(FIPS_C1_PT)
    assert dout1 == FIPS_C1_CT
    assert await d.digest() == bytes(32), "ECB wrote DIGEST"
    assert await d.get_iv() == bytes(16), "ECB wrote IV"
    dig1 = await d.sha(b"abc")
    assert dig1 == SHA_ABC
    assert await d.dout() == dout1, "SHA wrote DOUT"
    assert await d.get_iv() == bytes(16), "SHA wrote IV"
    iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    await d.set_iv(iv)
    ctr_out = await d.ctr(FIPS_B_PT)
    assert ctr_out == aes.ctr_crypt(FIPS_C1_KEY, iv, FIPS_B_PT)
    assert await d.digest() == dig1, "CTR wrote DIGEST"
    assert await d.get_iv() == aes.inc32(iv)
    await d.push(FIPS_B_PT)
    tr = await d.run(MODE_RSVD)
    _check_pattern(d, tr, N_ILLEGAL, "mode 3")
    assert await d.dout() == ctr_out and await d.digest() == dig1, "an illegal op wrote a result"
    assert await d.get_iv() == aes.inc32(iv), "an illegal op wrote IV"


@cocotb.test()
async def test_crypto_reset_mid_operation(dut):
    """A reset during an operation aborts it cleanly and returns the WHOLE block to its reset
    state: STATUS == 0 (so key_valid and key_write_rejected are cleared too), CTRL == 0 (IE
    included), irq_o low, DOUT / DIGEST / IV zero.  The shadow state is gone with it: an ECB start
    afterwards takes the 2-edge no-key path and writes nothing (it must not encrypt with a stale
    key), and a fresh key + block then works normally.
    MUTATION TARGET: key_seen / FSM state / done not reset."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.v4
    await d.load_key(FIPS_C1_KEY)
    await d.set_iv(bytes.fromhex("00112233445566778899aabbccddeeff"))
    assert await d.ecb(FIPS_C1_PT) == FIPS_C1_CT
    await d.clear_done()
    await d.push(FIPS_C1_PT)
    await d.start(MODE_ECB)
    await ClockCycles(dut.clk, 8)
    assert (await d.status()) & ST_BUSY
    await _reset(dut, rig)
    assert await d.status() == 0, "STATUS not zero after a mid-operation reset"
    assert await d.peek(CRYPTO_CTRL) == 0
    assert await d.peek_words(DOUT) == [0] * 4
    assert await d.get_iv() == bytes(16)
    assert int(d.irq_o.value) == 0
    await d.push(FIPS_C1_PT)
    tr = await d.run(MODE_ECB)
    _check_pattern(d, tr, N_ILLEGAL, "ECB after reset (no key)", key_valid=0)
    assert await d.dout() == bytes(16), "encrypted with a key that reset should have forgotten"
    await d.load_key(FIPS_C1_KEY)
    assert await d.ecb(FIPS_C1_PT) == FIPS_C1_CT

    # SHA mid-block on the full build, with done / rejected / IE all set beforehand
    m = rig.main
    await m.load_key(FIPS_B_KEY)
    await m.clear_done()
    await m.push(_sha_pad(b"abc"))
    await m.start(MODE_SHA, ie=1)
    await m.w(KEY[0], 0x1234_5678)  # rejected: busy
    await ClockCycles(dut.clk, 20)
    await _reset(dut, rig)
    assert await m.status() == 0 and await m.peek(CRYPTO_CTRL) == 0
    assert await m.digest() == bytes(32)
    assert int(m.irq_o.value) == 0
    assert await m.sha(b"abc") == SHA_ABC, "SHA broken after a mid-block reset"


# ===========================================================================
# Illegal / disabled operations: hang-free (D4, D5)
# ===========================================================================
@cocotb.test()
async def test_crypto_illegal_mode3_is_hang_free(dut):
    """D4: mode 3 (reserved) takes the 2-edge zero-length path on EVERY build: busy for one edge,
    done and IRQ_STAT set (an enabled irq_o fires on edge 2), and NO writeback -- DOUT, DIGEST and
    IV are exactly what the previous legal operations left (`done` does not imply valid data).  On
    a fresh block the data registers are still zero when done is already set.  A legal operation
    afterwards works (the FSM returned to idle).
    MUTATION TARGET: mode 3 dropped (hangs a `while(!done)` driver) or aliased onto ECB/SHA."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    for d in rig.all:
        await d.load_key(FIPS_C1_KEY)  # a valid key, so the ONLY reason for 'illegal' is the mode
        await d.push(FIPS_C1_PT)
        tr = await d.run(MODE_RSVD, ie=1)
        _check_pattern(d, tr, N_ILLEGAL, "mode 3")
        assert [t[2] for t in tr] == [0, 1], f"[{d.name}] irq pattern {[t[2] for t in tr]}"
        assert await d.dout() == bytes(16) and await d.digest() == bytes(32), (
            f"[{d.name}] done set but data written: done must not imply valid data"
        )
    d = rig.main
    dout1 = await d.ecb(FIPS_C1_PT)
    assert dout1 == FIPS_C1_CT
    dig1 = await d.sha(b"abc")
    await d.set_iv(bytes.fromhex("000102030405060708090a0b0c0d0e0f"))
    iv1 = await d.get_iv()
    await d.push(FIPS_B_PT)
    tr = await d.run(MODE_RSVD)
    _check_pattern(d, tr, N_ILLEGAL, "mode 3 after legal ops")
    assert await d.dout() == dout1, "mode 3 overwrote DOUT"
    assert await d.digest() == dig1, "mode 3 overwrote DIGEST"
    assert await d.get_iv() == iv1, "mode 3 advanced IV"
    assert await d.ecb(FIPS_B_PT) == aes.encrypt_block(FIPS_C1_KEY, FIPS_B_PT), (
        "FSM did not return to idle after an illegal op"
    )


@cocotb.test()
async def test_crypto_start_without_key_is_hang_free(dut):
    """D4 / D5: an ECB or CTR start with key_valid = 0 takes the 2-edge path instead of encrypting
    with a zero (or stale) key: done sets, DOUT stays 0, IV3 does not advance.  Three of four key
    words are still 'no key'; the fourth distinct word makes the same operation legal.  SHA-256
    needs NO key (key_valid gates only ECB / CTR) and runs its full 66 edges on a fresh block.
    MUTATION TARGET: key_valid not folded into op_legal_w (encrypts with zeros); SHA gated by
    key_valid."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)
    d = rig.main
    zero_key_ct = aes.encrypt_block(bytes(16), FIPS_C1_PT)
    assert zero_key_ct != bytes(16)
    await d.push(FIPS_C1_PT)
    iv = bytes.fromhex("0f0e0d0c0b0a09080706050403020100")
    await d.set_iv(iv)
    for mode, name in ((MODE_ECB, "ECB"), (MODE_CTR, "CTR")):
        tr = await d.run(mode)
        _check_pattern(d, tr, N_ILLEGAL, f"{name} without a key", key_valid=0)
        assert await d.dout() == bytes(16), f"{name} without a key wrote DOUT (zero-key result?)"
        assert await d.get_iv() == iv, f"{name} without a key advanced IV"
    words = _words(FIPS_C1_KEY)
    for i in (0, 2, 3):
        await d.w(KEY[i], words[i])
        tr = await d.run(MODE_ECB)
        _check_pattern(d, tr, N_ILLEGAL, f"ECB with {i} partial key words", key_valid=0)
    assert await d.dout() == bytes(16)
    await d.w(KEY[1], words[1])
    tr = await d.run(MODE_ECB)
    _check_pattern(d, tr, N_AES_16, "ECB with all four words", key_valid=1)
    assert await d.dout() == FIPS_C1_CT
    # SHA on a fresh block: no key needed
    await _reset(dut, rig)
    assert (await d.status()) & ST_KEYV == 0
    await d.clear_done()
    await d.push(_sha_pad(b"abc"))
    await d.start(MODE_SHA)
    tr = await d.trace()
    _check_pattern(d, tr, N_SHA, "SHA without a key", key_valid=0)
    assert await d.digest() == SHA_ABC


@cocotb.test()
async def test_crypto_compiled_out_core_is_hang_free(dut):
    """D4: a mode whose core is compiled out (EN_AES = 0 or EN_SHA = 0) takes the 2-edge path with
    done set (irq_o fires if enabled) and no writeback, even with a fully loaded key -- the build
    reports cleanly instead of hanging.  The surviving core is unaffected: on the SHA-only build
    SHA-256("abc") takes 66 edges and is exact, on the AES-only build FIPS-197 C.1 takes 11 and is
    exact, CTR advances IV3 once, and the dead mode still reports 2 edges afterwards.
    MUTATION TARGET: a start for an absent core hanging the FSM or reporting stale data."""
    _kill_active_tasks()
    rig = await _start_clock_and_reset(dut)

    d = rig.noaes  # SHA-only
    await d.load_key(FIPS_C1_KEY)
    await d.push(FIPS_C1_PT)
    iv = bytes.fromhex("00112233445566778899aabbccddeeff")
    await d.set_iv(iv)
    for mode, name in ((MODE_ECB, "ECB"), (MODE_CTR, "CTR")):
        tr = await d.run(mode, ie=1)
        _check_pattern(d, tr, N_ILLEGAL, f"{name} on the EN_AES=0 build")
        assert [t[2] for t in tr] == [0, 1], f"EN_AES=0 {name}: irq pattern"
        assert await d.dout() == bytes(16), f"EN_AES=0 {name} wrote DOUT"
        assert await d.get_iv() == iv, f"EN_AES=0 {name} advanced IV"
    await d.clear_done()
    await d.push(_sha_pad(b"abc"))
    await d.start(MODE_SHA)
    _check_pattern(d, await d.trace(), N_SHA, "SHA on the EN_AES=0 build")
    assert await d.digest() == SHA_ABC
    await d.push(FIPS_C1_PT)
    tr = await d.run(MODE_ECB)
    _check_pattern(d, tr, N_ILLEGAL, "ECB again after SHA")
    assert await d.digest() == SHA_ABC and await d.dout() == bytes(16)

    d = rig.nosha  # AES-only
    await d.load_key(FIPS_C1_KEY)
    await d.set_iv(iv)
    await d.clear_done()
    await d.push(FIPS_C1_PT)
    await d.start(MODE_ECB)
    _check_pattern(d, await d.trace(), N_AES_16, "ECB on the EN_SHA=0 build", key_valid=1)
    assert await d.dout() == FIPS_C1_CT
    await d.push(_sha_pad(b"abc"))
    tr = await d.run(MODE_SHA, ie=1)
    _check_pattern(d, tr, N_ILLEGAL, "SHA on the EN_SHA=0 build")
    assert [t[2] for t in tr] == [0, 1], "EN_SHA=0 SHA: irq pattern"
    assert await d.digest() == bytes(32), "EN_SHA=0 SHA wrote DIGEST"
    assert await d.dout() == FIPS_C1_CT, "EN_SHA=0 SHA disturbed DOUT"
    await d.push(FIPS_C1_PT)
    got = await d.ctr(FIPS_C1_PT)
    assert got == aes.ctr_crypt(FIPS_C1_KEY, iv, FIPS_C1_PT)
    assert await d.get_iv() == aes.inc32(iv)


# ===========================================================================
# Elaboration guards (lint-only; no simulation)
# ===========================================================================
def _crypto_sources() -> list[str]:
    """CRYPTO_SOURCES as `make crypto` sees it, resolved with the repo's own Makefile parser
    (tools/verif/check_source_closure.py), NOT a hand-copied list that could drift (D13)."""
    verif = str(_PROJ_ROOT / "tools" / "verif")
    if verif not in sys.path:
        sys.path.insert(0, verif)
    from check_source_closure import extract_makefile_lists

    lists = extract_makefile_lists(Path(__file__).resolve().parent / "Makefile")
    assert "CRYPTO_SOURCES" in lists, "CRYPTO_SOURCES missing from tb/cocotb/soc/Makefile"
    return lists["CRYPTO_SOURCES"]


# A throwaway SINGLE-instance top for the lint-only checks.  tb_crypto itself holds four
# configurations, and a -G override that made its primary instance identical to one of the
# variants would give Verilator two identically-parameterised crypto_accel instances and a
# spurious VARHIDDEN on the local strb_expand function (a wrapper artefact: a lone instance lints
# clean in every configuration).  So the guards are exercised through this one instead.
_SINGLE_TOP = """`default_nettype none
module tb_crypto_single #(
    parameter int unsigned ADDR_W        = 12,
    parameter bit          EN_AES        = 1,
    parameter bit          EN_SHA        = 1,
    parameter int unsigned SBOX_PARALLEL = 16
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
    crypto_accel #(
        .ADDR_W(ADDR_W), .EN_AES(EN_AES), .EN_SHA(EN_SHA), .SBOX_PARALLEL(SBOX_PARALLEL)
    ) u_dut (
        .clk(clk), .rst_n(rst_n), .psel(psel), .penable(penable), .pwrite(pwrite),
        .paddr(paddr), .pwdata(pwdata), .pstrb(pstrb), .prdata(prdata), .pready(pready),
        .pslverr(pslverr), .irq_o(irq_o)
    );
endmodule
`default_nettype wire
"""


def _lint(*overrides: str) -> subprocess.CompletedProcess:
    """`verilator --lint-only -Wall` of the CRYPTO_SOURCES RTL under a single-instance top, with
    optional -G<PARAM>=<value> overrides."""
    rtl = [p for p in _crypto_sources() if Path(p).name != "tb_crypto.sv"]
    assert len(rtl) == len(_crypto_sources()) - 1, "tb_crypto.sv not found in CRYPTO_SOURCES"
    with tempfile.TemporaryDirectory() as tmp:
        top = Path(tmp) / "tb_crypto_single.sv"
        top.write_text(_SINGLE_TOP, encoding="utf-8")
        cmd = [
            "verilator",
            "--lint-only",
            "-Wall",
            "-Wno-IMPORTSTAR",
            "-Wno-SYNCASYNCNET",
            "--top-module",
            "tb_crypto_single",
            *overrides,
            *rtl,
            str(top),
        ]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)


@cocotb.test()
async def test_crypto_elaboration_guards_reject_illegal_config(dut):
    """The elaboration guards refuse an illegal configuration: SBOX_PARALLEL other than 16 / 4
    (3, 8, 0), ADDR_W outside [7, 32] (6, 33), and EN_AES = EN_SHA = 0 (a peripheral that can do
    nothing is a build error).  Each override must give a NON-ZERO exit AND name the offending
    parameter in the output, without being a mere missing-file error; the same command line at the
    defaults is the negative control that proves it is sound (D13).  Lint-only: no simulation."""
    ok = _lint()
    assert ok.returncode == 0, f"default elaboration must pass:\n{ok.stdout}{ok.stderr}"
    cases = [
        (("-GSBOX_PARALLEL=3",), "SBOX_PARALLEL"),
        (("-GSBOX_PARALLEL=8",), "SBOX_PARALLEL"),
        (("-GSBOX_PARALLEL=0",), "SBOX_PARALLEL"),
        (("-GADDR_W=6",), "ADDR_W"),
        (("-GADDR_W=33",), "ADDR_W"),
        (("-GEN_AES=0", "-GEN_SHA=0"), "EN_AES"),
    ]
    for args, name in cases:
        r = _lint(*args)
        out = r.stdout + r.stderr
        assert r.returncode != 0, f"{args} elaborated; the guard is not firing"
        assert name in out, f"{args} failed, but not via the {name} guard:\n{out}"
        assert "Cannot find file" not in out, (
            f"{args} failed on a missing file, not a guard:\n{out}"
        )


@cocotb.test()
async def test_crypto_elaboration_legal_configs_pass(dut):
    """Both generate arms elaborate and lint clean on their own: EN_AES = 0 alone and EN_SHA = 0
    alone (the other core stays), SBOX_PARALLEL = 4, and the lowest legal ADDR_W (7: five word
    bits for 32 registers).  -Wall, so any warning is a failure too."""
    for args in (
        ("-GEN_AES=0",),
        ("-GEN_SHA=0",),
        ("-GSBOX_PARALLEL=4",),
        ("-GADDR_W=7",),
    ):
        r = _lint(*args)
        assert r.returncode == 0, f"{args} must elaborate cleanly:\n{r.stdout}{r.stderr}"
