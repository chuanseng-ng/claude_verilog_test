"""trng_lfsr_model.py -- bit-exact pure-Python golden model of the LFSR entropy source of the TRNG.

Subject: rtl/periph/trng_lfsr_entropy.sv. This is NOT a randomness model. The default-build
TRNG is a deterministic generator and forces TRNG_STATUS.INSECURE = 1. The module lets the L1
suite (tb/cocotb/soc/test_trng.py) golden-vector the RTL: given TRNG_SEED, every word is a
function of the seed. The RTL implements what this file computes.

Pipeline contract (one enabled, non-stalled core clock = one raw sample):
  1. Seed: three Fibonacci LFSRs (31, 29 and 23 bits) load seed[30:0], seed[28:0], seed[22:0].
     Seed bit 31 is unused. An all-zero slice locks up and is not rescued.
  2. Step: out = state[n-1]; fb = state[n-1] ^ state[t-1]; state = ((state << 1) | fb) & mask.
     Taps (n, t): (31, 28), (29, 27), (23, 18). selftest() checks that each polynomial is primitive.
  3. Raw sample: raw[k] = out31[k] ^ out29[k] ^ out23[k]. Sample 0 is taken before any step.
  4. Von Neumann debiaser on non-overlapping raw pairs: 01 emits 0, 10 emits 1, 00/11 drop.
  5. Words pack LSB first. A full FIFO (4 deep) stalls the pipeline and never drops a sample,
     so the word sequence depends on the seed alone.
  6. Health test: repetition count (NIST SP 800-90B) on the raw samples. A run of 21 identical
     samples trips. A trip halts the pipeline and flushes the FIFO. A W1C of STATUS.health_fail
     resumes it with the run count restarted.
  7. Session: every 0 -> 1 edge of CTRL.ENABLE loads the seed and clears the FIFO, the word
     assembler and the run counter. A TRNG_SEED write at any other time changes only the register.
     A seed whose low 31 bits are 0 gives a constant 0 stream: no word, trip at raw sample 21.
Run: python3 tb/models/trng_lfsr_model.py (primitivity, first steps, known-answer words).
Doc: ds:ch:phase6-ip-expansion-plan, tm:suite:trng-lfsr-model, cr:suite:trng-lfsr-model
"""

from __future__ import annotations

from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Contract constants (mirrored by test_trng.py and, later, the RTL)
# ---------------------------------------------------------------------------
# (register width n, tap t) -- see the module docstring.
LFSR_SPECS: tuple[tuple[int, int], ...] = ((31, 28), (29, 27), (23, 18))

WORD_BITS = 32
FIFO_DEPTH = 4
RC_CUTOFF = 21  # NIST SP 800-90B repetition-count cutoff, H=1, alpha=2**-20

# TRNG_SEED reset value. Must be non-zero and must NOT start with a long run (a small seed such
# as 1, or an all-ones seed, makes every register emit a long constant run and trips the health
# test at raw sample 21 -- see selftest()). 0xACE1_2345 is healthy for at least the first 3
# million raw samples (checked by selftest()).
DEFAULT_SEED = 0xACE1_2345

# Seeds that make the repetition-count test trip at exactly raw sample RC_CUTOFF: the two lock-up
# seeds (low 31 bits zero; bit 31 is unused) and the two "all ones in the LFSR slices" seeds,
# where every register emits a long constant run before its first feedback bit arrives.
STUCK_SEEDS = (0x0000_0000, 0x8000_0000, 0x0000_0001, 0xFFFF_FFFF, 0x7FFF_FFFF)

# A seed that runs healthy for 980 raw samples (7 complete words) and then trips the
# repetition-count test at raw sample 981 (found by search, asserted in selftest()). Lets the
# suite observe a health failure that occurs AFTER the FIFO has already been filled with
# apparently good words -- the flush-and-halt behaviour.
LATE_TRIP_SEED = 0xDAE2_1BA4
LATE_TRIP_SAMPLE = 981
LATE_TRIP_WORDS_BEFORE = 7

# Healthy seeds (no trip in the first 20 000 raw samples) for the multi-seed golden vectors.
GOLDEN_SEEDS = (0x1234_5678, 0xDEAD_BEEF, 0xA5A5_A5A5, 0x1357_9BDF, 0x2468_ACE1)


def _lfsr_step(state: int, n: int, t: int) -> tuple[int, int]:
    """One Fibonacci step; returns (out_bit, next_state). out_bit is the pre-step MSB."""
    out = (state >> (n - 1)) & 1
    fb = out ^ ((state >> (t - 1)) & 1)
    return out, ((state << 1) | fb) & ((1 << n) - 1)


def seed_to_states(seed: int) -> tuple[int, int, int]:
    """Slice a 32-bit TRNG_SEED into the three LFSR initial states (bit 31 unused)."""
    seed &= 0xFFFF_FFFF
    return tuple(seed & ((1 << n) - 1) for n, _ in LFSR_SPECS)  # type: ignore[return-value]


def raw_samples(seed: int) -> Iterator[int]:
    """Infinite iterator of raw (pre-debias) samples for `seed`, sample 0 first."""
    states = list(seed_to_states(seed))
    while True:
        bit = 0
        for i, (n, t) in enumerate(LFSR_SPECS):
            out, states[i] = _lfsr_step(states[i], n, t)
            bit ^= out
        yield bit


class TrngLfsrModel:
    """Golden model for one TRNG session (one CTRL.ENABLE 0->1 edge with a given TRNG_SEED).

    Everything is computed lazily and cached, so `words(n)` for growing n is cheap.
    """

    def __init__(self, seed: int):
        self.seed = seed & 0xFFFF_FFFF
        self._raw = raw_samples(self.seed)
        self._words: list[int] = []
        # raw samples consumed at the moment word k completed (index k, 0-based)
        self._raw_at_word: list[int] = []
        self._consumed = 0
        self._cur = 0
        self._cur_bits = 0
        self._pair: list[int] = []
        # repetition-count state and first trip (raw samples consumed when it trips)
        self._run_bit = -1
        self._run_len = 0
        self.first_trip: int | None = None

    # -- internals ----------------------------------------------------------
    def _consume_one(self) -> None:
        bit = next(self._raw)
        self._consumed += 1
        # repetition count (raw samples)
        if bit == self._run_bit:
            self._run_len += 1
        else:
            self._run_bit, self._run_len = bit, 1
        if self.first_trip is None and self._run_len >= RC_CUTOFF:
            self.first_trip = self._consumed
        # von Neumann debiaser
        self._pair.append(bit)
        if len(self._pair) == 2:
            a, b = self._pair
            self._pair = []
            if a != b:
                self._cur |= a << self._cur_bits
                self._cur_bits += 1
                if self._cur_bits == WORD_BITS:
                    self._words.append(self._cur)
                    self._raw_at_word.append(self._consumed)
                    self._cur, self._cur_bits = 0, 0

    # -- public API ---------------------------------------------------------
    def words(self, n: int) -> list[int]:
        """The first `n` 32-bit words the peripheral would deliver (ignoring the health test)."""
        while len(self._words) < n:
            self._consume_one()
        return self._words[:n]

    def raw_consumed_for_words(self, n: int) -> int:
        """Raw samples consumed by the moment the n-th word (1-based) completes."""
        self.words(n)
        return self._raw_at_word[n - 1]

    def health_trip_sample(self, horizon: int) -> int | None:
        """Raw-sample count at which the repetition-count test first trips, searching the first
        `horizon` raw samples; None if it does not trip inside the horizon."""
        while self._consumed < horizon and self.first_trip is None:
            self._consume_one()
        return (
            self.first_trip
            if (self.first_trip is not None and self.first_trip <= horizon)
            else None
        )

    def words_before_trip(self) -> int:
        """Number of words fully COMPLETED strictly before the health trip (requires that a trip
        exists; call health_trip_sample first)."""
        assert self.first_trip is not None
        while self._consumed < self.first_trip:
            self._consume_one()
        return sum(1 for c in self._raw_at_word if c < self.first_trip)


def discard_fraction(seed: int, n_words: int) -> float:
    """Fraction of raw samples discarded by the von Neumann debiaser while producing n_words:
    1 - (output bits) / (raw samples). For an unbiased source this is ~0.75 (4 raw per bit)."""
    m = TrngLfsrModel(seed)
    used = m.raw_consumed_for_words(n_words)
    return 1.0 - (n_words * WORD_BITS) / used


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
def _poly_mulmod(a: int, b: int, poly: int, n: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        b >>= 1
        a <<= 1
        if (a >> n) & 1:
            a ^= poly
    return r


def _poly_powmod(e: int, poly: int, n: int) -> int:
    result, base = 1, 2  # base = x
    while e:
        if e & 1:
            result = _poly_mulmod(result, base, poly, n)
        base = _poly_mulmod(base, base, poly, n)
        e >>= 1
    return result


def _prime_factors(x: int) -> list[int]:
    fs, d = [], 2
    while d * d <= x:
        if x % d == 0:
            fs.append(d)
            while x % d == 0:
                x //= d
        d += 1
    if x > 1:
        fs.append(x)
    return fs


def is_primitive_trinomial(n: int, t: int) -> bool:
    """True if x^n + x^(n-t) + 1 is primitive over GF(2).

    That trinomial is the polynomial our (n, t) LFSR realises.
    """
    poly = (1 << n) | (1 << (n - t)) | 1
    order = (1 << n) - 1
    if _poly_powmod(order, poly, n) != 1:
        return False
    return all(_poly_powmod(order // q, poly, n) != 1 for q in _prime_factors(order))


def selftest() -> None:
    """Self-check the model against independent derivations.

    Verifies the three polynomials are primitive, cross-checks the LFSR step
    against a separate linear recurrence, and confirms the stuck, late-trip and
    healthy seeds behave as the suite's docstring claims.
    """
    # 1. all three polynomials are primitive => maximal length 2**n - 1
    for n, t in LFSR_SPECS:
        assert is_primitive_trinomial(n, t), f"x^{n}+x^{n - t}+1 is not primitive"

    # 2. LFSR step, hand-checked. 23-bit, tap 18, state 1: out = bit22 = 0, fb = 0 ^ bit17 = 0.
    assert _lfsr_step(1, 23, 18) == (0, 2)
    # state with only bit22 set: out = 1, fb = 1 ^ bit17(0) = 1 -> (state<<1)|1 masked = 1
    assert _lfsr_step(1 << 22, 23, 18) == (1, 1)

    # 3. seed slicing, bit 31 unused
    assert seed_to_states(0xFFFF_FFFF) == (0x7FFF_FFFF, 0x1FFF_FFFF, 0x7F_FFFF)
    assert seed_to_states(0x8000_0000) == (0, 0, 0)

    # 4. lock-up seed: all-zero raw stream, never a word, trips at sample RC_CUTOFF
    z = TrngLfsrModel(0)
    assert z.health_trip_sample(1000) == RC_CUTOFF
    assert all(b == 0 for b, _ in zip(raw_samples(0), range(1000), strict=False))

    # 5. a tiny seed starts with a long zero run and trips at RC_CUTOFF too (why the reset seed
    #    must not be small)
    assert TrngLfsrModel(1).health_trip_sample(1000) == RC_CUTOFF

    # 6. the reset seed is healthy for a very long time (no trip in the first 2M samples)
    d = TrngLfsrModel(DEFAULT_SEED)
    assert d.health_trip_sample(3_000_000) is None, "DEFAULT_SEED trips the health test"

    # 7. debiaser sanity: ~75 % of raw samples discarded on an unbiased-ish source
    frac = discard_fraction(DEFAULT_SEED, 128)
    assert 0.70 < frac < 0.80, frac

    # 8. words are reproducible and seed bit 31 is unused
    a = TrngLfsrModel(DEFAULT_SEED).words(16)
    assert a == TrngLfsrModel(DEFAULT_SEED ^ 0x8000_0000).words(16)
    assert a == TrngLfsrModel(DEFAULT_SEED).words(16)
    assert len(set(a)) == 16

    # 9. known-answer words for the reset seed (pinned so an accidental model edit is caught)
    assert KNOWN_ANSWER_DEFAULT_SEED == a[: len(KNOWN_ANSWER_DEFAULT_SEED)], [hex(w) for w in a[:8]]

    # 10. independent cross-check of the LFSR: the same output stream from the linear recurrence
    #     out[k] = out[k-n] ^ out[k-t] (start-up outputs are the seed slice read MSB-first).
    for idx, (n, t) in enumerate(LFSR_SPECS):
        st = seed_to_states(DEFAULT_SEED)[idx]
        via_step, s_ = [], st
        for _ in range(2000):
            o, s_ = _lfsr_step(s_, n, t)
            via_step.append(o)
        via_rec = [(st >> (n - 1 - k)) & 1 for k in range(n)]
        for k in range(n, 2000):
            via_rec.append(via_rec[k - n] ^ via_rec[k - t])
        assert via_step == via_rec, f"LFSR({n},{t}) step disagrees with its recurrence"

    # 11. the multi-seed / stuck-seed / late-trip constants are what their comments claim
    for sd in STUCK_SEEDS:
        assert TrngLfsrModel(sd).health_trip_sample(1000) == RC_CUTOFF, hex(sd)
    for sd in GOLDEN_SEEDS:
        assert TrngLfsrModel(sd).health_trip_sample(20_000) is None, hex(sd)
    late = TrngLfsrModel(LATE_TRIP_SEED)
    assert late.health_trip_sample(5000) == LATE_TRIP_SAMPLE
    assert late.words_before_trip() == LATE_TRIP_WORDS_BEFORE

    print("trng_lfsr_model selftest: PASS")
    print("  DEFAULT_SEED       =", hex(DEFAULT_SEED))
    print("  first words        =", [hex(w) for w in a[:4]])
    print("  discard fraction   =", round(frac, 4))
    print("  raw for 4/5/6 words=", [d.raw_consumed_for_words(k) for k in (4, 5, 6)])


# First words for the reset seed (produced by this model, cross-checked by selftest() step 10).
KNOWN_ANSWER_DEFAULT_SEED: list[int] = [
    0x35337491,
    0x82CE100F,
    0x2C6B394D,
    0xDEEA5F92,
    0xF8DB2FFB,
    0xB9198D17,
    0x5423CF04,
    0xF2D1A411,
]


if __name__ == "__main__":
    selftest()
