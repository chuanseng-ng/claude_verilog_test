"""npu_model.py -- pure-Python golden model of the INT8 NPU's arithmetic (rtl/npu/npu_top.sv +
rtl/npu/npu_mac_array.sv + rtl/npu/npu_weight_mem.sv; bead claude_verilog_test-f7vs.11, Phase 6c,
docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6c -- NPU").

STANDARD LIBRARY ONLY. requirements.txt is deliberately untouched (same promise as
tb/models/aes128_model.py): this is a test oracle, not a fast implementation.

This module is the authoritative specification of what the RTL must compute; the RTL implements
what this file computes. It models ONLY THE ARITHMETIC -- not cycle timing, not the register bank,
not the APB handshake, not the AIN / AOUT FIFO depths or the weight-SRAM read latency
(tb/cocotb/soc/test_npu.py pins all of that).

WHAT IS COMPUTED
----------------
For one inference of KLEN chunks (c = 0 .. KLEN-1) and four output lanes (j = 0 .. 3):

    acc[j] = SUM_c SUM_(i=0..3)  W[c][i][j] * a[c][i]                  (signed INT32)
    y[j]   = relu?( sat_int8( (acc[j] * SCALE_MULT) >> SCALE_SHIFT ) )

One chunk is one 32-bit AIN word carrying a[c][0..3] and four CONSECUTIVE weight-SRAM words
carrying W[c][i][0..3], one word per row i, at SRAM[TILEBASE + 4*c + i]. The four accumulators are
zeroed at START and accumulate across all KLEN chunks; the requantiser then drains the four lanes
and the four INT8 results are packed into ONE 32-bit AOUT word.

BYTE-LANE CONTRACT (one rule, used for WDATA, AIN and AOUT alike)
-----------------------------------------------------------------
LITTLE-ENDIAN: element / lane index 0 is bits [7:0], index 1 is [15:8], index 2 is [23:16] and
index 3 is [31:24] of the 32-bit register word.

    word = (e3 & 0xFF) << 24 | (e2 & 0xFF) << 16 | (e1 & 0xFF) << 8 | (e0 & 0xFF)

So a weight word is row i of the tile with W[c][i][j] in byte j; an AIN word is a[c][0..3] with
a[c][i] in byte i; an AOUT word is y[0..3] with y[j] in byte j. Each byte is a two's-complement
INT8. Rationale: RV32 is little-endian, so firmware can `memcpy` an `int8_t[4]` straight into a
register with no byte swap (the opposite choice to the AES model, whose FIPS hex notation forced
big-endian). `pack_word` / `unpack_word` are the only place the conversion lives.

WEIGHT / ACTIVATION / PRODUCT RANGES
------------------------------------
W and a are signed INT8 (-128 .. 127). A product is INT8 x INT8 -> INT16 (-16256 .. 16384). Four
products per chunk, KLEN chunks per inference.

ACCUMULATOR: SIGNED INT32, SATURATING -- and the saturation can never fire
--------------------------------------------------------------------------
The accumulator policy is SATURATE (`sat_int32`), not wrap. But the reachable range is tiny: the
worst case is every operand -128 (product +16384), 4 products per chunk and 64 chunks, i.e.
256 * 16384 = 2**22 = 4_194_304, which is 2**9 times smaller than INT32_MAX. So for every legal
(KLEN <= 64) inference the INT32 accumulator CANNOT overflow, and `sat_int32` is the DEFINED
behaviour for a width the architecture never reaches. Consequences:
  * the RTL is free to use a narrower accumulator (>= 24 bits signed holds every reachable value)
    or the full 32 bits; the two are observably identical;
  * what the RTL must NOT do is truncate or saturate the accumulator x scale PRODUCT to 32 bits
    (see below) -- that product needs at least 40 bits and is a real, reachable overflow site.
`accumulate` applies `sat_int32` after every addition so the policy is executable and tested at the
INT32 limits (tb/tests/test_npu_model.py), even though no legal input reaches them.

REQUANTISE (the shared stage)
-----------------------------
SCALE register: SCALE[15:0] = SCALE_MULT (UNSIGNED 16-bit multiplier), SCALE[20:16] = SCALE_SHIFT
(unsigned right shift, 0 .. 31).

    p  = acc * SCALE_MULT            exact signed product; NEVER truncated
    s  = p >> SCALE_SHIFT            ARITHMETIC right shift = FLOOR division by 2**SCALE_SHIFT
    y  = sat_int8(s)                 clamp to [-128, 127], applied to the FULL-WIDTH shifted value
    y  = max(0, y)   if CTRL[0] RELU_EN

ROUNDING IS TRUNCATION TO MINUS INFINITY (floor), NOT round-half-up and NOT toward zero:
    ( 3 * 1) >> 1 =  1      (round-half-up would give 2)
    (-1 * 1) >> 1 = -1      (toward-zero would give 0)
    (-3 * 1) >> 1 = -2      (toward-zero and half-up would both give -1)
In RTL this is `$signed(prod) >>> shift`, with the product held wide enough for every reachable
value (|acc| <= 2**22 needs 24 signed bits, so 24 + 16 = 40 bits; a full-INT32 accumulator would
need 48) and the saturation compare done on the shifted full-width value. A 32-bit product
would wrap for e.g. acc = 2**22, mult = 65535, shift = 0: the true result saturates to 127,
a 32-bit wrap gives -128.
SCALE_MULT = 0 gives y = 0 for every lane. ReLU is applied AFTER saturation; since saturation is
monotone and ReLU is max(0, .), the order does not change the result, but this is the order the
RTL's requantiser implements.

ILLEGAL STARTS
--------------
`legal_start` is the legality predicate the RTL's 2-cycle zero-length path uses:
KLEN in 1 .. 63 and TILEBASE + 4*KLEN <= WEIGHT_WORDS (1024). `infer` refuses an illegal start
(ValueError) because the RTL computes nothing for one.

KLEN RANGE: 63 AT THE REGISTER, 64 IN THE MODEL (a plan defect, flagged)
-------------------------------------------------------------------------
The plan documents KLEN[5:0] as "1..64" with KLEN == 0 illegal. A 6-bit field cannot hold 64:
writing 64 stores 0 (WMASK 0x3F), which is then an illegal start. The register-reachable maximum
is therefore 63. The ARITHMETIC is defined here for 1 .. KLEN_MAX = 64 because the accumulator
bound above is stated for the plan's 64; `legal_start` enforces the register's real limit
(KLEN_REG_MAX = 63). Resolving the discrepancy (KLEN-1 encoding, or "max 63") belongs to the
plan's owner; the model needs no change either way for 1 .. 63.

Run `python3 tb/models/npu_model.py` to execute the self-check.
"""

from __future__ import annotations

from collections.abc import Sequence

GRID = 4  # 4x4 weight-stationary grid: 4 rows (i) x 4 output lanes (j)
WEIGHT_WORDS = 1024  # 4 KB weight SRAM, one 32-bit word = one row of INT8 weights
WORDS_PER_CHUNK = 4  # one weight word per row i
KLEN_MAX = 64  # arithmetic range (the plan's "1..64")
KLEN_REG_MAX = 63  # what KLEN[5:0] can actually hold
SCALE_MULT_BITS = 16
SCALE_SHIFT_BITS = 5

INT8_MIN, INT8_MAX = -(1 << 7), (1 << 7) - 1
INT32_MIN, INT32_MAX = -(1 << 31), (1 << 31) - 1


# ---------------------------------------------------------------------------
# Byte-lane view (the ONLY place the 32-bit word <-> 4 x INT8 conversion lives)
# ---------------------------------------------------------------------------
def sat_int8(x: int) -> int:
    """Clamp to the signed INT8 range [-128, 127]."""
    return max(INT8_MIN, min(INT8_MAX, x))


def sat_int32(x: int) -> int:
    """Clamp to the signed INT32 range (the accumulator's SATURATE policy)."""
    return max(INT32_MIN, min(INT32_MAX, x))


def pack_word(elems: Sequence[int]) -> int:
    """Pack 4 signed INT8 values into one 32-bit word, element 0 in bits [7:0] (little-endian)."""
    if len(elems) != GRID:
        raise ValueError(f"pack_word needs {GRID} elements, got {len(elems)}")
    word = 0
    for k, e in enumerate(elems):
        if not INT8_MIN <= e <= INT8_MAX:
            raise ValueError(f"element {k} = {e} is outside INT8")
        word |= (e & 0xFF) << (8 * k)
    return word


def unpack_word(word: int) -> tuple[int, int, int, int]:
    """Inverse of `pack_word`: 4 signed INT8 values, element 0 from bits [7:0]."""
    if not 0 <= word <= 0xFFFF_FFFF:
        raise ValueError(f"word 0x{word:x} is not a 32-bit value")
    out = []
    for k in range(GRID):
        b = (word >> (8 * k)) & 0xFF
        out.append(b - 256 if b & 0x80 else b)
    return (out[0], out[1], out[2], out[3])


def make_scale(mult: int, shift: int) -> int:
    """Compose the SCALE register value: SCALE[15:0] = mult, SCALE[20:16] = shift."""
    if not 0 <= mult < (1 << SCALE_MULT_BITS):
        raise ValueError(f"scale multiplier {mult} outside 0..{(1 << SCALE_MULT_BITS) - 1}")
    if not 0 <= shift < (1 << SCALE_SHIFT_BITS):
        raise ValueError(f"scale shift {shift} outside 0..{(1 << SCALE_SHIFT_BITS) - 1}")
    return (shift << SCALE_MULT_BITS) | mult


def split_scale(scale: int) -> tuple[int, int]:
    """Decode a SCALE register value into (mult, shift); bits above [20:0] are ignored (the bank
    never stores them)."""
    return scale & 0xFFFF, (scale >> SCALE_MULT_BITS) & 0x1F


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------
def accumulate(acc: int, products: Sequence[int]) -> int:
    """Add `products` into a signed-INT32 accumulator, SATURATING after every addition."""
    for p in products:
        acc = sat_int32(acc + p)
    return acc


def mac_chunk(acc: Sequence[int], weights: Sequence[int], a_word: int) -> list[int]:
    """One chunk: acc[j] += SUM_i W[i][j] * a[i].

    `weights` is the four SRAM words of the tile (row i = weights[i], lane j in byte j); `a_word`
    is the AIN word (a[i] in byte i). Returns the four updated accumulators.
    """
    if len(weights) != WORDS_PER_CHUNK:
        raise ValueError(f"a chunk is {WORDS_PER_CHUNK} weight words, got {len(weights)}")
    a = unpack_word(a_word)
    rows = [unpack_word(w) for w in weights]
    return [accumulate(acc[j], [rows[i][j] * a[i] for i in range(GRID)]) for j in range(GRID)]


def requant(acc: int, mult: int, shift: int, relu: bool) -> int:
    """Requantise one INT32 accumulator to INT8: floor((acc*mult) >> shift), saturate, ReLU."""
    if not 0 <= mult < (1 << SCALE_MULT_BITS):
        raise ValueError(f"scale multiplier {mult} outside the unsigned 16-bit range")
    if not 0 <= shift < (1 << SCALE_SHIFT_BITS):
        raise ValueError(f"scale shift {shift} outside 0..31")
    y = sat_int8((acc * mult) >> shift)  # Python's >> on a negative int is the arithmetic shift
    return max(0, y) if relu else y


def legal_start(tilebase: int, klen: int, weight_words: int = WEIGHT_WORDS) -> bool:
    """True iff START is accepted: 1 <= KLEN <= 63 (the register's range) and the tile run
    TILEBASE + 4*KLEN fits inside the weight SRAM."""
    return 1 <= klen <= KLEN_REG_MAX and 0 <= tilebase and tilebase + 4 * klen <= weight_words


def infer_lanes(
    weight_mem: Sequence[int],
    tilebase: int,
    ain_words: Sequence[int],
    scale: int,
    relu: bool,
) -> tuple[int, int, int, int]:
    """One whole inference; returns the four signed INT8 results y[0..3].

    `weight_mem` is the weight-SRAM image (one 32-bit word per entry), `ain_words` the KLEN AIN
    words in push order (KLEN = len(ain_words)). Arithmetic range 1 <= KLEN <= KLEN_MAX; the tile
    run must lie inside the memory image.
    """
    klen = len(ain_words)
    if not 1 <= klen <= KLEN_MAX:
        raise ValueError(f"KLEN {klen} outside 1..{KLEN_MAX}")
    if tilebase < 0 or tilebase + 4 * klen > len(weight_mem):
        raise ValueError(f"tile run {tilebase}+4*{klen} exceeds the {len(weight_mem)}-word memory")
    mult, shift = split_scale(scale)
    acc = [0] * GRID
    for c in range(klen):
        base = tilebase + 4 * c
        acc = mac_chunk(acc, weight_mem[base : base + 4], ain_words[c])
    return tuple(requant(a, mult, shift, relu) for a in acc)  # type: ignore[return-value]


def infer(
    weight_mem: Sequence[int],
    tilebase: int,
    ain_words: Sequence[int],
    scale: int,
    relu: bool,
) -> int:
    """`infer_lanes` packed into the AOUT word (y[0] in bits [7:0]).

    Unlike `infer_lanes` this refuses an ILLEGAL start (the RTL writes no AOUT word for one):
    KLEN in 1..63 and TILEBASE + 4*KLEN <= 1024 (the memory image's own size is not consulted).
    """
    if not legal_start(tilebase, len(ain_words), WEIGHT_WORDS):
        raise ValueError(f"illegal start: TILEBASE={tilebase} KLEN={len(ain_words)}")
    return pack_word(infer_lanes(weight_mem, tilebase, ain_words, scale, relu))


def blank_weight_mem(words: int = WEIGHT_WORDS) -> list[int]:
    """An all-zero weight-SRAM image (the model's stand-in for the 1024 x 32 macro)."""
    return [0] * words


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
def selftest() -> None:
    """Hand-computed vectors; the pytest suite (tb/tests/test_npu_model.py) re-pins them as
    independent literals."""
    # 1. byte-lane packing: element 0 in bits [7:0]
    assert pack_word([1, -2, 3, -4]) == 0xFC03FE01
    assert unpack_word(0xFC03FE01) == (1, -2, 3, -4)
    assert unpack_word(pack_word([-128, 127, 0, -1])) == (-128, 127, 0, -1)

    # 2. identity tile, KLEN = 1: y == a (rows are unit vectors)
    mem = blank_weight_mem()
    mem[0:4] = [0x00000001, 0x00000100, 0x00010000, 0x01000000]
    a = pack_word([1, -2, 3, -4])
    assert unpack_word(infer(mem, 0, [a], make_scale(1, 0), False)) == (1, -2, 3, -4)
    assert unpack_word(infer(mem, 0, [a], make_scale(1, 0), True)) == (1, 0, 3, 0)

    # 3. dense tile, KLEN = 1: y = [48, 8, -32, 28]
    mem[4:8] = [
        pack_word([1, 2, 3, 4]),
        pack_word([5, 6, 7, 8]),
        pack_word([-1, -2, -3, -4]),
        pack_word([10, 0, -10, 5]),
    ]
    a = pack_word([1, 2, 3, 4])
    assert unpack_word(infer(mem, 4, [a], make_scale(1, 0), False)) == (48, 8, -32, 28)
    assert unpack_word(infer(mem, 4, [a], make_scale(1, 1), False)) == (24, 4, -16, 14)
    assert unpack_word(infer(mem, 4, [a], make_scale(3, 2), False)) == (36, 6, -24, 21)
    assert unpack_word(infer(mem, 4, [a], make_scale(5, 0), False)) == (127, 40, -128, 127)
    assert unpack_word(infer(mem, 4, [a], make_scale(1, 0), True)) == (48, 8, 0, 28)

    # 4. floor rounding and the 40-bit product
    assert requant(3, 1, 1, False) == 1
    assert requant(-1, 1, 1, False) == -1
    assert requant(-3, 1, 1, False) == -2
    assert requant(1 << 22, 65535, 0, False) == 127  # a 32-bit product would wrap to -128
    assert requant(-(1 << 22), 65535, 0, False) == -128
    assert requant(12345, 0, 7, False) == 0

    # 5. accumulator saturation policy
    assert sat_int32(INT32_MAX + 1) == INT32_MAX
    assert sat_int32(INT32_MIN - 1) == INT32_MIN
    assert accumulate(INT32_MAX, [1]) == INT32_MAX
    assert accumulate(INT32_MIN, [-1]) == INT32_MIN

    # 6. the worst reachable accumulator is 2**22 at KLEN = 64
    mem = [pack_word([-128] * 4)] * WEIGHT_WORDS
    worst = infer_lanes(mem, 0, [pack_word([-128] * 4)] * 64, make_scale(1, 15), False)
    assert worst == (127,) * 4  # 4194304 >> 15 = 128 -> saturates
    assert infer_lanes(mem, 0, [pack_word([-128] * 4)] * 64, make_scale(1, 16), False) == (64,) * 4

    # 7. legality
    assert legal_start(1020, 1) and not legal_start(1021, 1)
    assert legal_start(768, 63) and not legal_start(773, 63) and not legal_start(0, 0)
    assert not legal_start(0, 64)  # KLEN[5:0] cannot hold 64

    print("npu_model selftest: PASS")
    print("  dense tile y =", (48, 8, -32, 28), "(KLEN=1, scale 1>>0)")


if __name__ == "__main__":
    selftest()
