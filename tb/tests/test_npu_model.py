"""Unit tests for tb/models/npu_model.py (bead claude_verilog_test-f7vs.11).

The model is the golden reference the NPU's cocotb suite (tb/cocotb/soc/test_npu.py) chases, so
these tests pin it independently of that suite. Every vector below is HAND-COMPUTED and written as
a literal -- none is produced by calling the model on itself -- so a silent edit of the model's
arithmetic cannot move the target.
"""

import ast
import random
import sys
from pathlib import Path

import pytest

from tb.models import npu_model as m

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

MODEL_PATH = Path(m.__file__)


def _mem(base: int, rows: list[list[int]]) -> list[int]:
    """A blank weight image with `rows` (each a list of 4 INT8) packed from word `base`."""
    mem = m.blank_weight_mem()
    for k, row in enumerate(rows):
        mem[base + k] = m.pack_word(row)
    return mem


DENSE_TILE = [[1, 2, 3, 4], [5, 6, 7, 8], [-1, -2, -3, -4], [10, 0, -10, 5]]
DENSE_A = [1, 2, 3, 4]
# y0 = 1*1 + 5*2 + (-1)*3 + 10*4 = 48     y1 = 2*1 + 6*2 + (-2)*3 + 0*4  = 8
# y2 = 3*1 + 7*2 + (-3)*3 + (-10)*4 = -32 y3 = 4*1 + 8*2 + (-4)*3 + 5*4   = 28
DENSE_ACC = (48, 8, -32, 28)


class TestByteLanes:
    """Element 0 is bits [7:0], little-endian, two's complement."""

    def test_pack_hand_computed(self):
        """Pack hand computed."""
        # 1 -> 0x01, -2 -> 0xFE, 3 -> 0x03, -4 -> 0xFC
        assert m.pack_word([1, -2, 3, -4]) == 0xFC03FE01
        assert m.pack_word([-128, 127, 0, -1]) == 0xFF007F80
        assert m.pack_word([0, 0, 0, 0]) == 0

    def test_unpack_hand_computed(self):
        """Unpack hand computed."""
        assert m.unpack_word(0xFC03FE01) == (1, -2, 3, -4)
        assert m.unpack_word(0x80808080) == (-128, -128, -128, -128)
        assert m.unpack_word(0x7F7F7F7F) == (127, 127, 127, 127)

    def test_byte0_is_the_low_byte(self):
        """Byte0 is the low byte."""
        assert m.pack_word([1, 0, 0, 0]) == 0x00000001
        assert m.pack_word([0, 1, 0, 0]) == 0x00000100
        assert m.pack_word([0, 0, 1, 0]) == 0x00010000
        assert m.pack_word([0, 0, 0, 1]) == 0x01000000

    def test_roundtrip_random(self):
        """Roundtrip random."""
        rng = random.Random(0xA11)
        for _ in range(200):
            v = [rng.randint(-128, 127) for _ in range(4)]
            assert list(m.unpack_word(m.pack_word(v))) == v

    @pytest.mark.parametrize("bad", [[0] * 3, [0] * 5, [128, 0, 0, 0], [0, -129, 0, 0]])
    def test_pack_rejects_bad_input(self, bad):
        """Pack rejects bad input."""
        with pytest.raises(ValueError):
            m.pack_word(bad)

    @pytest.mark.parametrize("bad", [-1, 1 << 32])
    def test_unpack_rejects_non_32bit(self, bad):
        """Unpack rejects non 32bit."""
        with pytest.raises(ValueError):
            m.unpack_word(bad)

    def test_scale_fields(self):
        """Scale fields."""
        assert m.make_scale(0xFFFF, 31) == 0x001FFFFF
        assert m.make_scale(1, 0) == 0x00000001
        assert m.make_scale(3, 2) == 0x00020003
        assert m.split_scale(0x00020003) == (3, 2)
        assert m.split_scale(0xFFFFFFFF) == (0xFFFF, 31)  # bits above [20:0] are ignored
        with pytest.raises(ValueError):
            m.make_scale(0x10000, 0)
        with pytest.raises(ValueError):
            m.make_scale(0, 32)


class TestSingleChunk:
    """KLEN = 1, hand-computed."""

    def test_identity_tile_returns_the_activations(self):
        """Identity tile returns the activations."""
        mem = _mem(0, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        a = m.pack_word([1, -2, 3, -4])
        assert m.unpack_word(m.infer(mem, 0, [a], m.make_scale(1, 0), False)) == (1, -2, 3, -4)

    def test_relu_zeroes_negative_lanes_only(self):
        """Relu zeroes negative lanes only."""
        mem = _mem(0, [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        a = m.pack_word([1, -2, 3, -4])
        # 0x03 << 16 | 0x01 = 0x00030001
        assert m.infer(mem, 0, [a], m.make_scale(1, 0), True) == 0x00030001

    def test_dense_tile_raw_accumulators(self):
        """Dense tile raw accumulators."""
        mem = _mem(0, DENSE_TILE)
        a = m.pack_word(DENSE_A)
        assert m.infer_lanes(mem, 0, [a], m.make_scale(1, 0), False) == DENSE_ACC

    def test_dense_tile_is_row_times_activation_not_transposed(self):
        """Row i of the tile multiplies activation a[i]: a = e0 selects row 0 verbatim."""
        mem = _mem(0, DENSE_TILE)
        a = m.pack_word([1, 0, 0, 0])
        assert m.infer_lanes(mem, 0, [a], m.make_scale(1, 0), False) == (1, 2, 3, 4)
        a = m.pack_word([0, 0, 0, 1])
        assert m.infer_lanes(mem, 0, [a], m.make_scale(1, 0), False) == (10, 0, -10, 5)

    @pytest.mark.parametrize(
        ("mult", "shift", "relu", "want"),
        [
            (1, 1, False, (24, 4, -16, 14)),  # >>1: 48/2 8/2 -32/2 28/2
            (3, 2, False, (36, 6, -24, 21)),  # 144>>2 24>>2 -96>>2 84>>2
            (5, 0, False, (127, 40, -128, 127)),  # 240->127, -160->-128, 140->127
            (1, 0, True, (48, 8, 0, 28)),
            (0, 0, False, (0, 0, 0, 0)),  # zero multiplier
            (1, 31, False, (0, 0, -1, 0)),  # floor: -32 >> 31 == -1, positives -> 0
            (1, 31, True, (0, 0, 0, 0)),
        ],
    )
    def test_dense_tile_scaling(self, mult, shift, relu, want):
        """Dense tile scaling."""
        mem = _mem(0, DENSE_TILE)
        a = m.pack_word(DENSE_A)
        assert m.infer_lanes(mem, 0, [a], m.make_scale(mult, shift), relu) == want

    def test_tilebase_offsets_the_read(self):
        """Tilebase offsets the read."""
        mem = _mem(100, DENSE_TILE)
        a = m.pack_word(DENSE_A)
        assert m.infer_lanes(mem, 100, [a], m.make_scale(1, 0), False) == DENSE_ACC
        assert m.infer_lanes(mem, 96, [a], m.make_scale(1, 0), False) != DENSE_ACC


class TestRequantRounding:
    """Floor (truncate toward minus infinity); NOT half-up, NOT toward zero."""

    @pytest.mark.parametrize(
        ("acc", "shift", "want"),
        [
            (3, 1, 1),  # 1.5 -> 1   (round-half-up would be 2)
            (-1, 1, -1),  # -0.5 -> -1 (toward zero would be 0)
            (-3, 1, -2),  # -1.5 -> -2 (toward zero / half-up would be -1)
            (5, 2, 1),  # 1.25 -> 1
            (7, 2, 1),  # 1.75 -> 1  (round-to-nearest would be 2)
            (-7, 2, -2),  # -1.75 -> -2
            (0, 5, 0),
            (-1, 31, -1),
            (1, 31, 0),
        ],
    )
    def test_floor_semantics(self, acc, shift, want):
        """Floor semantics."""
        assert m.requant(acc, 1, shift, False) == want

    def test_product_is_not_truncated_to_32_bits(self):
        """2**22 * 65535 = 274_873_712_640 -> 127; a 32-bit wrap would give -4194304 -> -128."""
        assert (1 << 22) * 65535 == 274_873_712_640
        assert (1 << 22) * 65535 % (1 << 32) == (1 << 32) - (1 << 22)  # the wrapped low word
        assert m.requant(1 << 22, 65535, 0, False) == 127
        assert m.requant(-(1 << 22), 65535, 0, False) == -128

    def test_shift_applied_before_saturation(self):
        """A huge product shifted back into range must NOT be clamped before the shift."""
        # acc = 2**22, mult = 65535, shift = 31: 2**22 * 65535 >> 31 = 127.99.. -> 127 (floor)
        assert m.requant(1 << 22, 65535, 31, False) == 127
        # acc = 2**22, mult = 2**15, shift = 31: exactly 2**37 >> 31 = 64
        assert m.requant(1 << 22, 1 << 15, 31, False) == 64

    def test_int8_saturation_edges(self):
        """Int8 saturation edges."""
        assert m.requant(127, 1, 0, False) == 127
        assert m.requant(128, 1, 0, False) == 127
        assert m.requant(-128, 1, 0, False) == -128
        assert m.requant(-129, 1, 0, False) == -128
        assert m.requant(10**6, 1, 0, False) == 127
        assert m.requant(-(10**6), 1, 0, False) == -128

    def test_relu_after_saturation(self):
        """Relu after saturation."""
        assert m.requant(-129, 1, 0, True) == 0
        assert m.requant(-5, 1, 0, True) == 0
        assert m.requant(0, 1, 0, True) == 0
        assert m.requant(200, 1, 0, True) == 127

    def test_scale_range_checks(self):
        """Scale range checks."""
        with pytest.raises(ValueError):
            m.requant(1, -1, 0, False)  # the multiplier is UNSIGNED
        with pytest.raises(ValueError):
            m.requant(1, 1 << 16, 0, False)
        with pytest.raises(ValueError):
            m.requant(1, 1, 32, False)


class TestAccumulatorSaturation:
    """INT32 accumulator policy: SATURATE (not wrap)."""

    def test_sat_int32_limits(self):
        """Sat int32 limits."""
        assert m.sat_int32(2**31 - 1) == 2**31 - 1
        assert m.sat_int32(2**31) == 2**31 - 1
        assert m.sat_int32(-(2**31)) == -(2**31)
        assert m.sat_int32(-(2**31) - 1) == -(2**31)
        assert m.sat_int32(2**40) == 2**31 - 1

    def test_accumulate_saturates_does_not_wrap(self):
        """Accumulate saturates does not wrap."""
        assert m.accumulate(2**31 - 1, [1]) == 2**31 - 1  # a wrap would give -2**31
        assert m.accumulate(-(2**31), [-1]) == -(2**31)  # a wrap would give 2**31 - 1
        assert m.accumulate(2**31 - 10, [4, 4, 4]) == 2**31 - 1  # saturates mid-sequence
        assert m.accumulate(0, [5, -3, 2]) == 4

    def test_saturation_is_sticky_per_addition(self):
        """Saturation happens after EVERY add, so a later negative product moves off the rail."""
        assert m.accumulate(2**31 - 1, [10, -3]) == 2**31 - 4

    def test_mac_chunk_accumulates_across_calls(self):
        """Mac chunk accumulates across calls."""
        w = [m.pack_word(r) for r in DENSE_TILE]
        a = m.pack_word(DENSE_A)
        once = m.mac_chunk([0] * 4, w, a)
        twice = m.mac_chunk(once, w, a)
        assert tuple(once) == DENSE_ACC
        assert tuple(twice) == tuple(2 * v for v in DENSE_ACC)

    def test_reachable_accumulator_never_reaches_int32(self):
        """The worst case (all -128, KLEN 64) is 2**22: saturation is unreachable in a legal run."""
        w = m.pack_word([-128] * 4)
        acc = [0] * 4
        for _ in range(64):
            acc = m.mac_chunk(acc, [w] * 4, w)
        assert acc == [4_194_304] * 4
        assert 4_194_304 == 2**22 < 2**31 - 1


class TestMultiChunk:
    """KLEN > 1 and the SRAM address advance (4 words per chunk)."""

    def test_two_chunks_sum(self):
        """Two chunks sum."""
        mem = _mem(0, DENSE_TILE + DENSE_TILE)
        a0 = m.pack_word(DENSE_A)
        a1 = m.pack_word([1, 0, 0, 0])
        # chunk 1 contributes row 0 verbatim: (1,2,3,4)
        got = m.infer_lanes(mem, 0, [a0, a1], m.make_scale(1, 0), False)
        assert got == (49, 10, -29, 32)

    def test_chunks_use_distinct_weight_tiles(self):
        """Chunk c reads SRAM[tilebase + 4c ..]: tile 0 = all ones in row 0, tile 1 = all twos."""
        mem = _mem(
            8, [[1, 1, 1, 1], [0] * 4, [0] * 4, [0] * 4, [2, 2, 2, 2], [0] * 4] + [[0] * 4] * 2
        )
        a = m.pack_word([1, 0, 0, 0])
        assert m.infer_lanes(mem, 8, [a], m.make_scale(1, 0), False) == (1, 1, 1, 1)
        assert m.infer_lanes(mem, 8, [a, a], m.make_scale(1, 0), False) == (3, 3, 3, 3)

    def test_klen_64_hand_computed(self):
        """KLEN 64: W[c][0][j] = c + 1, a[c][0] = 1 -> acc = sum(1..64) = 2080 on every lane."""
        mem = m.blank_weight_mem()
        for c in range(64):
            mem[4 * c] = m.pack_word([c + 1] * 4)
        a = m.pack_word([1, 0, 0, 0])
        assert m.infer_lanes(mem, 0, [a] * 64, m.make_scale(1, 0), False) == (127,) * 4
        assert m.infer_lanes(mem, 0, [a] * 64, m.make_scale(1, 5), False) == (65,) * 4  # 2080>>5
        assert m.infer_lanes(mem, 0, [a] * 64, m.make_scale(1, 4), False) == (127,) * 4  # 130

    def test_klen_64_extreme_accumulators(self):
        """All -128 x -128 -> +2**22; all -128 x 127 -> -4_161_536."""
        w = [m.pack_word([-128] * 4)] * m.WEIGHT_WORDS
        neg = m.pack_word([-128] * 4)
        pos = m.pack_word([127] * 4)
        assert m.infer_lanes(w, 0, [neg] * 64, m.make_scale(1, 22), False) == (1,) * 4
        assert m.infer_lanes(w, 0, [neg] * 64, m.make_scale(1, 16), False) == (64,) * 4
        assert m.infer_lanes(w, 0, [neg] * 64, m.make_scale(1, 15), False) == (127,) * 4
        # -128 * 127 = -16256 per product; 256 products = -4_161_536; >> 15 floors -126.99 to -127
        assert m.infer_lanes(w, 0, [pos] * 64, m.make_scale(1, 15), False) == (-127,) * 4
        assert m.infer_lanes(w, 0, [pos] * 64, m.make_scale(1, 14), False) == (-128,) * 4
        assert m.infer_lanes(w, 0, [pos] * 64, m.make_scale(1, 14), True) == (0,) * 4

    def test_klen_63_is_the_register_maximum(self):
        """Klen 63 is the register maximum."""
        assert m.legal_start(0, 63)
        assert m.KLEN_REG_MAX == 63
        assert m.KLEN_MAX == 64

    def test_model_matches_independent_formula_random(self):
        """Random cases against a from-scratch re-statement of the formula (no model helpers)."""
        rng = random.Random(0x4E50)
        for _ in range(60):
            klen = rng.randint(1, 63)
            base = rng.randrange(0, 1024 - 4 * klen + 1)
            mem = m.blank_weight_mem()
            w = [
                [[rng.randint(-128, 127) for _ in range(4)] for _ in range(4)] for _ in range(klen)
            ]
            a = [[rng.randint(-128, 127) for _ in range(4)] for _ in range(klen)]
            for c in range(klen):
                for i in range(4):
                    mem[base + 4 * c + i] = m.pack_word(w[c][i])
            mult, shift = rng.randrange(1 << 16), rng.randrange(32)
            relu = bool(rng.getrandbits(1))
            want = []
            for j in range(4):
                acc = sum(w[c][i][j] * a[c][i] for c in range(klen) for i in range(4))
                y = max(-128, min(127, (acc * mult) >> shift))
                want.append(max(0, y) if relu else y)
            ains = [m.pack_word(x) for x in a]
            got = m.infer_lanes(mem, base, ains, m.make_scale(mult, shift), relu)
            assert list(got) == want


class TestLegality:
    """The predicate behind the 2-cycle zero-length path."""

    @pytest.mark.parametrize(
        ("tilebase", "klen", "legal"),
        [
            (0, 0, False),  # KLEN == 0
            (0, 1, True),
            (1020, 1, True),  # 1020 + 4 == 1024: last tile
            (1021, 1, False),  # 1025 > 1024
            (1023, 1, False),
            (768, 63, True),  # 768 + 252 = 1020
            (772, 63, True),  # 772 + 252 = 1024
            (773, 63, False),  # 1025
            (0, 64, False),  # the 6-bit KLEN field cannot hold 64
            (0, 63, True),
        ],
    )
    def test_legal_start(self, tilebase, klen, legal):
        """Legal start."""
        assert m.legal_start(tilebase, klen) is legal

    def test_infer_refuses_an_illegal_start(self):
        """Infer refuses an illegal start."""
        mem = m.blank_weight_mem()
        with pytest.raises(ValueError, match="illegal start"):
            m.infer(mem, 1021, [0], 1, False)
        with pytest.raises(ValueError, match="illegal start"):
            m.infer(mem, 0, [], 1, False)

    def test_infer_lanes_rejects_klen_zero_and_over_64(self):
        """Infer lanes rejects klen zero and over 64."""
        mem = m.blank_weight_mem()
        with pytest.raises(ValueError):
            m.infer_lanes(mem, 0, [], 1, False)
        with pytest.raises(ValueError):
            m.infer_lanes(mem, 0, [0] * 65, 1, False)


class TestModuleContract:
    """The model's own self-check and its no-new-dependency promise."""

    def test_selftest_passes(self, capsys):
        """Selftest passes."""
        m.selftest()
        assert "PASS" in capsys.readouterr().out

    def test_standard_library_only(self):
        """Standard library only."""
        tree = ast.parse(MODEL_PATH.read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.add(node.module.split(".")[0])
        assert mods <= set(sys.stdlib_module_names), f"non-stdlib imports: {mods}"

    def test_not_reexported_from_the_package(self):
        """Suites import `from tb.models import npu_model`, like aes128_model."""
        import tb.models as pkg

        assert "npu_model" not in getattr(pkg, "__all__", [])
