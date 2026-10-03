"""Unit tests for tb/models/aes128_model.py (bead claude_verilog_test-f7vs.10).

The model is the golden reference the CRYPTO peripheral's cocotb suite
(tb/cocotb/soc/test_crypto.py) chases, so these tests pin it independently of that suite: the
FIPS-197 / SP 800-38A vectors are hardcoded HERE as literals (not imported from the model) so
that a silent edit of the model's own constants cannot move the target.
"""

import ast
import random
import sys
from pathlib import Path

import pytest

from tb.models import aes128_model as m

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

MODEL_PATH = Path(m.__file__)


def _h(s: str) -> bytes:
    return bytes.fromhex(s)


class TestFipsVectors:
    """FIPS-197 Appendix B / C.1 and NIST SP 800-38A F.5.1, hardcoded independently."""

    def test_appendix_b_worked_example(self):
        """Appendix b worked example."""
        key = _h("2b7e151628aed2a6abf7158809cf4f3c")
        pt = _h("3243f6a8885a308d313198a2e0370734")
        assert m.encrypt_block(key, pt) == _h("3925841d02dc09fbdc118597196a0b32")

    def test_appendix_c1_known_answer(self):
        """Appendix c1 known answer."""
        key = _h("000102030405060708090a0b0c0d0e0f")
        pt = _h("00112233445566778899aabbccddeeff")
        assert m.encrypt_block(key, pt) == _h("69c4e0d86a7b0430d8cdb78070b4c55a")

    def test_appendix_a1_round_keys(self):
        """Appendix a1 round keys."""
        rks = m.expand_key(_h("2b7e151628aed2a6abf7158809cf4f3c"))
        assert len(rks) == 11
        assert rks[0] == _h("2b7e151628aed2a6abf7158809cf4f3c")
        assert rks[1] == _h("a0fafe1788542cb123a339392a6c7605")
        assert rks[10] == _h("d014f9a8c9ee2589e13f0cc8b6630ca6")

    def test_sp800_38a_ctr(self):
        """Sp800 38a ctr."""
        key = _h("2b7e151628aed2a6abf7158809cf4f3c")
        iv = _h("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
        pt = _h(
            "6bc1bee22e409f96e93d7e117393172a"
            "ae2d8a571e03ac9c9eb76fac45f61b41"
            "30c81c46a35ce411e5fbc1191a0a52ef"
            "f69f2445df4f9b17ad2b417be66c3710"
        )
        ct = _h(
            "874d6191b620e3261bef6864990db6ce"
            "9806f66b7970fdff8617187bb9a668ef"
            "5ae4df3edbd5d35e5b4f09020db03eab"
            "1e031dda2fbe03d1792170a0f3009cee"
        )
        assert m.ctr_crypt(key, iv, pt) == ct
        assert m.ctr_crypt(key, iv, ct) == pt


class TestPrimitives:
    """GF(2^8), S-box, ShiftRows and MixColumns."""

    def test_fips_gf_examples(self):
        """Fips gf examples."""
        assert m.gmul(0x57, 0x83) == 0xC1
        assert m.gmul(0x57, 0x13) == 0xFE
        assert [m.xtime(x) for x in (0x57, 0xAE, 0x47, 0x8E)] == [0xAE, 0x47, 0x8E, 0x07]

    def test_xtime_matches_rtl_expression(self):
        """Xtime matches rtl expression."""
        for b in range(256):
            expect = ((b << 1) & 0xFF) ^ (0x1B if b >> 7 else 0)
            assert m.xtime(b) == expect

    def test_sbox_properties(self):
        """Sbox properties."""
        assert sorted(m.SBOX) == list(range(256))
        assert (m.SBOX[0x00], m.SBOX[0x01], m.SBOX[0x53], m.SBOX[0xFF]) == (0x63, 0x7C, 0xED, 0x16)

    def test_mix_column_published_vectors(self):
        """Mix column published vectors."""
        for col, out in (
            ("db135345", "8e4da1bc"),
            ("f20a225c", "9fdc589d"),
            ("2d26314c", "4d7ebdf8"),
        ):
            assert m.mix_column(_h(col)) == _h(out)

    def test_shift_rows_permutation(self):
        """Shift rows permutation."""
        assert m.shift_rows(bytes(range(16))) == _h("00050a0f04090e03080d02070c01060b")

    def test_on_the_fly_key_schedule_equals_expansion(self):
        """On the fly key schedule equals expansion."""
        rng = random.Random(0xAE5)
        for _ in range(8):
            key = bytes(rng.randrange(256) for _ in range(16))
            rks = m.expand_key(key)
            rk, rcon = key, 0x01
            for r in range(1, 11):
                rk = m.next_round_key(rk, rcon)
                rcon = m.xtime(rcon)
                assert rk == rks[r]


class TestCtr:
    """INC32 and CTR behaviour."""

    def test_inc32_only_rightmost_word(self):
        """Inc32 only rightmost word."""
        assert m.inc32(_h("000102030405060708090a0b0c0d0e0f")) == _h(
            "000102030405060708090a0b0c0d0e10"
        )

    def test_inc32_discards_carry(self):
        """Inc32 discards carry."""
        assert m.inc32(_h("00112233445566778899aabbffffffff")) == _h(
            "00112233445566778899aabb00000000"
        )
        assert m.inc32(_h("ff" * 16)) == _h("ff" * 12 + "00000000")

    def test_ctr_roundtrip_random(self):
        """Ctr roundtrip random."""
        rng = random.Random(0xC7A)
        for n in (1, 2, 5):
            key = bytes(rng.randrange(256) for _ in range(16))
            iv = bytes(rng.randrange(256) for _ in range(16))
            data = bytes(rng.randrange(256) for _ in range(16 * n))
            assert m.ctr_crypt(key, iv, m.ctr_crypt(key, iv, data)) == data

    def test_ctr_wraps_counter_word_across_blocks(self):
        """Ctr wraps counter word across blocks."""
        key = _h("2b7e151628aed2a6abf7158809cf4f3c")
        iv = _h("00112233445566778899aabbfffffffe")
        stream = m.ctr_keystream(key, iv, 3)
        counters = [iv, m.inc32(iv), m.inc32(m.inc32(iv))]
        assert counters[2] == _h("00112233445566778899aabb00000000")
        assert stream == [m.encrypt_block(key, c) for c in counters]

    def test_zero_input_is_raw_keystream(self):
        """Zero input is raw keystream."""
        key = _h("000102030405060708090a0b0c0d0e0f")
        iv = _h("00112233445566778899aabbccddeeff")
        assert m.ctr_crypt(key, iv, bytes(16)) == m.encrypt_block(key, iv)


class TestWordView:
    """Big-endian register-word view (module docstring byte-order contract)."""

    def test_word0_carries_byte0_in_msb(self):
        """Word0 carries byte0 in msb."""
        assert m.block_to_words(_h("3243f6a8885a308d313198a2e0370734")) == (
            0x3243F6A8,
            0x885A308D,
            0x313198A2,
            0xE0370734,
        )

    def test_roundtrip(self):
        """Roundtrip."""
        rng = random.Random(7)
        blk = bytes(rng.randrange(256) for _ in range(16))
        assert m.words_to_block(m.block_to_words(blk)) == blk
        assert m.words_to_block([0x00010203, 0x04050607, 0x08090A0B, 0x0C0D0E0F]) == bytes(
            range(16)
        )


class TestValidation:
    """Argument checking."""

    @pytest.mark.parametrize("n", [0, 15, 17, 32])
    def test_bad_key_length(self, n):
        """Bad key length."""
        with pytest.raises(ValueError, match="key"):
            m.encrypt_block(bytes(n), bytes(16))

    @pytest.mark.parametrize("n", [0, 15, 17])
    def test_bad_block_length(self, n):
        """Bad block length."""
        with pytest.raises(ValueError, match="block"):
            m.encrypt_block(bytes(16), bytes(n))

    def test_ctr_rejects_partial_block(self):
        """Ctr rejects partial block."""
        with pytest.raises(ValueError, match="multiple"):
            m.ctr_crypt(bytes(16), bytes(16), bytes(17))

    def test_words_to_block_needs_four_words(self):
        """Words to block needs four words."""
        with pytest.raises(ValueError, match="4 words"):
            m.words_to_block([1, 2, 3])


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
