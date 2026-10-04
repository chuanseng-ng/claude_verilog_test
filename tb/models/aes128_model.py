"""aes128_model.py -- pure-Python golden model of the CRYPTO peripheral's AES-128 datapath
(rtl/periph/aes128_core.sv + the CTR wrapper logic in rtl/periph/crypto_accel.sv; bead
claude_verilog_test-f7vs.10, Phase 6b, docs/PHASE6_IP_EXPANSION_PLAN.md Sec.6b "CRYPTO").

STANDARD LIBRARY ONLY. requirements.txt is deliberately untouched: the SHA-256 half of the
peripheral is checked against `hashlib.sha256`, and this module is the AES half's counterpart. It
is a clear, table-free-where-possible FIPS-197 implementation, NOT a fast or constant-time one --
it is a test oracle, never production crypto, and it has no side-channel resistance whatsoever.

This module is the authoritative specification of what the RTL must compute; the RTL implements
what this file computes. It does NOT model the peripheral's cycle timing, its register bank or its
handshake -- only the arithmetic (tb/cocotb/soc/test_crypto.py pins the rest).

BYTE ORDER (the contract the whole peripheral and its suite hang on)
--------------------------------------------------------------------
FIPS-197 / FIPS-180-4 big-endian, consistently. A 128-bit block is the 16-byte string B[0..15] as
it appears in the standard's hex notation; the 32-bit register words carry it with word 0 holding
B0 in bits [31:24]:

    word 0 = B0<<24 | B1<<16 | B2<<8 | B3      (DIN0 / KEY0 / IV0 / DOUT0)
    word 3 = B12<<24 | B13<<16 | B14<<8 | B15  (DIN3 / KEY3 / IV3 / DOUT3)

so the FIPS-197 hex strings, `bytes.fromhex`, `hashlib.sha256().digest()` and the register words
line up with NO byte swap anywhere. `block_to_words` / `words_to_block` are the only place the
conversion lives. The AES state is column-major: state byte index 4*c + r is row r of column c,
so bytes 0..3 are column 0 and ShiftRows is a fixed re-wiring of the 16-byte vector.

CTR MODE (NIST SP 800-38A Sec.6.5, Appendix B.1 "INC32")
--------------------------------------------------------
The peripheral exposes ECB and CTR over one ENCRYPT-ONLY datapath; CTR is what makes it a complete
cipher in both directions.

    keystream[i] = AES-128-Encrypt(K, counter[i])         counter[0] = the IV register block
    output[i]    = input[i] XOR keystream[i]              (the XOR happens at the writeback)
    counter[i+1] = INC32(counter[i])

INC32 increments ONLY the rightmost 32-bit word (IV3), modulo 2**32. The carry out of that word is
DISCARDED: IV0..IV2 never change, so a counter that crosses 2**32 blocks wraps to the same
counter-block prefix. Software must not run one counter past a 2**32-block wrap. CTR decryption
is bit-identical to CTR encryption (S ^ (S ^ P) = P) -- there is no decrypt mode and no inverse
S-box anywhere.

KEY SCHEDULE
------------
`expand_key` is the FIPS-197 Sec.5.2 expansion. The RTL instead computes it ON THE FLY with one
128-bit round-key register, advancing once per round; `next_round_key` is that exact step
(w0' = w0 ^ SubWord(RotWord(w3)) ^ {rcon,24'h0}, w1' = w0'^w1, w2' = w1'^w2, w3' = w2'^w3, with
rcon advanced by `xtime` per round, starting at 0x01). selftest() proves the two formulations
agree, so a divergence between the RTL's on-the-fly schedule and the standard is attributable.

MIXCOLUMNS FORMULATION
----------------------
`mix_column` uses the same identity the RTL does,
    b_i = a_i ^ t ^ xtime(a_i ^ a_(i+1 mod 4)),   t = a0^a1^a2^a3
which equals the textbook 2*a_i ^ 3*a_(i+1) ^ a_(i+2) ^ a_(i+3) (selftest() checks the two against
each other and against FIPS-197-style column vectors).

VECTORS PINNED HERE AND AGAIN IN THE SUITE
------------------------------------------
Each constant below is asserted by selftest() AND re-asserted, hardcoded independently, by
tb/cocotb/soc/test_crypto.py (the double-pin tb/models/trng_lfsr_model.py / test_trng.py
established), so a silent edit of this model cannot move the target the suite chases:
  * FIPS-197 Appendix B   -- the worked example (key 2b7e1516..., plaintext 3243f6a8...).
  * FIPS-197 Appendix C.1 -- the AES-128 known-answer vector (key 000102...0f).
  * NIST SP 800-38A F.5.1 -- CTR-AES128 over four blocks (counter f0f1...feff).

Run `python3 tb/models/aes128_model.py` to execute the self-check.
"""

from __future__ import annotations

BLOCK_BYTES = 16
KEY_BYTES = 16
NUM_ROUNDS = 10
WORD_BYTES = 4

# ---------------------------------------------------------------------------
# Known-answer vectors (FIPS-197 Appendix B / C.1, NIST SP 800-38A F.5.1)
# ---------------------------------------------------------------------------
# Appendix B: the worked example. Chosen because it is the one every AES reference prints, and its
# full intermediate-state table is in the standard -- the first thing to open when an RTL round is
# wrong.
FIPS197_B_KEY = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
FIPS197_B_PLAINTEXT = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
FIPS197_B_CIPHERTEXT = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")
# Appendix B's final-round key (Appendix A.1 key expansion, w40..w43).
FIPS197_B_LAST_ROUND_KEY = bytes.fromhex("d014f9a8c9ee2589e13f0cc8b6630ca6")

# Appendix C.1: key = 00 01 02 ... 0f, plaintext = 00 11 22 ... ff. A sequential key and a
# byte-repeating-nibble plaintext make a byte-lane or word-order swap obvious by eye.
FIPS197_C1_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
FIPS197_C1_PLAINTEXT = bytes.fromhex("00112233445566778899aabbccddeeff")
FIPS197_C1_CIPHERTEXT = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")

# SP 800-38A F.5.1 CTR-AES128.Encrypt: initial counter block, and four (plaintext, ciphertext)
# pairs. The counter's rightmost word is 0xfcfdfeff, so block 2's counter is ...fcfdff00 -- the
# increment ripples through a byte boundary of IV3 (but never past IV3). Every ciphertext here was
# cross-checked against `openssl enc -aes-128-ctr` when the model was written.
SP800_38A_CTR_KEY = FIPS197_B_KEY
SP800_38A_CTR_IV = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
SP800_38A_CTR_PLAINTEXT: tuple[bytes, ...] = (
    bytes.fromhex("6bc1bee22e409f96e93d7e117393172a"),
    bytes.fromhex("ae2d8a571e03ac9c9eb76fac45f61b41"),
    bytes.fromhex("30c81c46a35ce411e5fbc1191a0a52ef"),
    bytes.fromhex("f69f2445df4f9b17ad2b417be66c3710"),
)
SP800_38A_CTR_CIPHERTEXT: tuple[bytes, ...] = (
    bytes.fromhex("874d6191b620e3261bef6864990db6ce"),
    bytes.fromhex("9806f66b7970fdff8617187bb9a668ef"),
    bytes.fromhex("5ae4df3edbd5d35e5b4f09020db03eab"),
    bytes.fromhex("1e031dda2fbe03d1792170a0f3009cee"),
)


# ---------------------------------------------------------------------------
# GF(2^8) and the S-box
# ---------------------------------------------------------------------------
def xtime(b: int) -> int:
    """Multiply by x (i.e. by 2) in GF(2^8) modulo x^8 + x^4 + x^3 + x + 1.

    Args:
        b: A byte, 0..255.

    Returns:
        ``{b[6:0], 1'b0} ^ (b[7] ? 8'h1B : 8'h00)`` -- the RTL's xtime, bit for bit.
    """
    return ((b << 1) & 0xFF) ^ (0x1B if b & 0x80 else 0x00)


def gmul(a: int, b: int) -> int:
    """Multiply two bytes in GF(2^8) (shift-and-add over `xtime`).

    Args:
        a: First byte.
        b: Second byte.

    Returns:
        The GF(2^8) product, 0..255.
    """
    product = 0
    while b:
        if b & 1:
            product ^= a
        a = xtime(a)
        b >>= 1
    return product


def _gf_inverse(a: int) -> int:
    """Multiplicative inverse in GF(2^8) as a**254 (0 maps to 0, per FIPS-197 Sec.5.1.1)."""
    result, base, exp = 1, a, 254
    while exp:
        if exp & 1:
            result = gmul(result, base)
        base = gmul(base, base)
        exp >>= 1
    return result if a else 0


def _rotl8(x: int, n: int) -> int:
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _build_sbox() -> tuple[int, ...]:
    """FIPS-197 Sec.5.1.1: multiplicative inverse followed by the affine transformation.

    Derived rather than typed in, so the model's S-box is independent of the 256 literals in the
    RTL's `case` (the two can then be compared by the vectors, not by copy).
    """
    table = []
    for a in range(256):
        b = _gf_inverse(a)
        table.append(b ^ _rotl8(b, 1) ^ _rotl8(b, 2) ^ _rotl8(b, 3) ^ _rotl8(b, 4) ^ 0x63)
    return tuple(table)


SBOX: tuple[int, ...] = _build_sbox()


# ---------------------------------------------------------------------------
# Round transformations (state = 16 bytes, column-major: index 4*c + r)
# ---------------------------------------------------------------------------
def sub_bytes(state: bytes) -> bytes:
    """Apply the S-box to every byte."""
    return bytes(SBOX[b] for b in state)


def shift_rows(state: bytes) -> bytes:
    """Cyclically shift row r left by r positions (a fixed re-wiring in hardware)."""
    return bytes(state[4 * ((c + r) % 4) + r] for c in range(4) for r in range(4))


def mix_column(col: bytes) -> bytes:
    """MixColumns on one 4-byte column via ``b_i = a_i ^ t ^ xtime(a_i ^ a_(i+1))``."""
    t = col[0] ^ col[1] ^ col[2] ^ col[3]
    return bytes(col[i] ^ t ^ xtime(col[i] ^ col[(i + 1) % 4]) for i in range(4))


def mix_columns(state: bytes) -> bytes:
    """MixColumns on all four columns."""
    return b"".join(mix_column(state[4 * c : 4 * c + 4]) for c in range(4))


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------------------
# Key schedule
# ---------------------------------------------------------------------------
def next_round_key(round_key: bytes, rcon: int) -> bytes:
    """One on-the-fly key-schedule step -- exactly what aes128_core's rk_q update computes.

    Args:
        round_key: The current 16-byte round key {w0,w1,w2,w3} (w0 = bytes 0..3).
        rcon: The round constant for the NEW key (0x01 for round 1, then `xtime` per round).

    Returns:
        The next round key.
    """
    w = [round_key[4 * i : 4 * i + 4] for i in range(4)]
    rot = w[3][1:] + w[3][:1]  # RotWord
    sub = bytes(SBOX[b] for b in rot)  # SubWord
    w0 = _xor(w[0], bytes([sub[0] ^ rcon, sub[1], sub[2], sub[3]]))
    w1 = _xor(w0, w[1])
    w2 = _xor(w1, w[2])
    w3 = _xor(w2, w[3])
    return w0 + w1 + w2 + w3


def expand_key(key: bytes) -> list[bytes]:
    """FIPS-197 Sec.5.2 key expansion.

    Args:
        key: The 16-byte cipher key.

    Returns:
        The eleven 16-byte round keys, index 0 = the cipher key itself (whitening key).
    """
    _check_len("key", key, KEY_BYTES)
    keys = [key]
    rcon = 0x01
    for _ in range(NUM_ROUNDS):
        keys.append(next_round_key(keys[-1], rcon))
        rcon = xtime(rcon)
    return keys


# ---------------------------------------------------------------------------
# Block cipher
# ---------------------------------------------------------------------------
def _check_len(name: str, value: bytes, expected: int) -> None:
    if len(value) != expected:
        raise ValueError(f"{name} must be {expected} bytes, got {len(value)}")


def encrypt_block(key: bytes, block: bytes) -> bytes:
    """AES-128 encryption of one block (the ECB primitive).

    Args:
        key: The 16-byte cipher key, FIPS byte order.
        block: The 16-byte plaintext block, FIPS byte order.

    Returns:
        The 16-byte ciphertext block.

    Raises:
        ValueError: If `key` or `block` is not exactly 16 bytes.
    """
    _check_len("key", key, KEY_BYTES)
    _check_len("block", block, BLOCK_BYTES)
    round_keys = expand_key(key)
    state = _xor(block, round_keys[0])  # initial AddRoundKey ("whitening")
    for rnd in range(1, NUM_ROUNDS + 1):
        state = shift_rows(sub_bytes(state))
        if rnd != NUM_ROUNDS:  # the final round has no MixColumns
            state = mix_columns(state)
        state = _xor(state, round_keys[rnd])
    return state


# ---------------------------------------------------------------------------
# CTR mode
# ---------------------------------------------------------------------------
def inc32(counter: bytes) -> bytes:
    """NIST SP 800-38A B.1 INC32: add 1 to the rightmost 32 bits, discarding the carry.

    Args:
        counter: A 16-byte counter block.

    Returns:
        The counter with only its last four bytes incremented (mod 2**32); bytes 0..11 unchanged.
    """
    _check_len("counter", counter, BLOCK_BYTES)
    low = (int.from_bytes(counter[12:], "big") + 1) & 0xFFFF_FFFF
    return counter[:12] + low.to_bytes(4, "big")


def ctr_keystream(key: bytes, iv: bytes, n_blocks: int) -> list[bytes]:
    """The first `n_blocks` keystream blocks E(K, counter_i) for counter_0 = `iv`.

    Args:
        key: The 16-byte cipher key.
        iv: The initial 16-byte counter block (the IV0..IV3 registers).
        n_blocks: How many keystream blocks to produce.

    Returns:
        A list of 16-byte keystream blocks.
    """
    stream = []
    counter = iv
    for _ in range(n_blocks):
        stream.append(encrypt_block(key, counter))
        counter = inc32(counter)
    return stream


def ctr_crypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    """CTR encrypt OR decrypt (they are the same operation) of whole 16-byte blocks.

    Args:
        key: The 16-byte cipher key.
        iv: The initial 16-byte counter block.
        data: Plaintext or ciphertext; a multiple of 16 bytes (the peripheral is block-granular).

    Returns:
        `data` XOR the keystream, same length.

    Raises:
        ValueError: If `data` is not a whole number of blocks.
    """
    if len(data) % BLOCK_BYTES:
        raise ValueError(f"data length {len(data)} is not a multiple of {BLOCK_BYTES}")
    stream = ctr_keystream(key, iv, len(data) // BLOCK_BYTES)
    return b"".join(
        _xor(data[i * BLOCK_BYTES : (i + 1) * BLOCK_BYTES], ks) for i, ks in enumerate(stream)
    )


# ---------------------------------------------------------------------------
# Register-word view (big-endian, see the module docstring)
# ---------------------------------------------------------------------------
def block_to_words(block: bytes) -> tuple[int, int, int, int]:
    """Split a 16-byte block into the four 32-bit register words, word 0 = bytes 0..3 MSB-first.

    Args:
        block: A 16-byte block.

    Returns:
        (word0, word1, word2, word3).
    """
    _check_len("block", block, BLOCK_BYTES)
    w = [int.from_bytes(block[4 * i : 4 * i + 4], "big") for i in range(4)]
    return (w[0], w[1], w[2], w[3])


def words_to_block(words: tuple[int, int, int, int] | list[int]) -> bytes:
    """Inverse of `block_to_words`.

    Args:
        words: Four 32-bit register words, word 0 first.

    Returns:
        The 16-byte block.

    Raises:
        ValueError: If there are not exactly four words.
    """
    if len(words) != 4:
        raise ValueError(f"need 4 words, got {len(words)}")
    return b"".join((w & 0xFFFF_FFFF).to_bytes(4, "big") for w in words)


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
def _mix_column_textbook(col: bytes) -> bytes:
    """The FIPS-197 Sec.5.1.3 matrix form 2*a_i ^ 3*a_(i+1) ^ a_(i+2) ^ a_(i+3), via `gmul`."""
    return bytes(
        gmul(2, col[i]) ^ gmul(3, col[(i + 1) % 4]) ^ col[(i + 2) % 4] ^ col[(i + 3) % 4]
        for i in range(4)
    )


def selftest() -> None:
    """Self-check the model against independent derivations and the pinned vectors.

    Covers the GF(2^8) worked examples of FIPS-197 Sec.4.2, S-box properties and spot values,
    MixColumns (matrix form versus the RTL's xtime form, plus published column vectors), the key
    schedule (full expansion versus the on-the-fly step, plus Appendix A.1's last round key), the
    FIPS-197 Appendix B and C.1 block vectors, INC32 and the SP 800-38A F.5.1 CTR vectors.
    """
    # 1. GF(2^8): FIPS-197 Sec.4.2 -- {57}.{83} = {c1}; xtime chain {57} -> {ae} -> {47} -> {8e}
    assert gmul(0x57, 0x83) == 0xC1
    assert gmul(0x57, 0x13) == 0xFE
    assert [xtime(0x57), xtime(0xAE), xtime(0x47), xtime(0x8E)] == [0xAE, 0x47, 0x8E, 0x07]

    # 2. S-box: a bijection with no fixed point and no "opposite" fixed point, plus spot values
    #    (FIPS-197 Fig.7: S(00)=63, S(01)=7c, S(53)=ed, S(ff)=16)
    assert sorted(SBOX) == list(range(256))
    assert all(SBOX[a] != a and SBOX[a] != a ^ 0xFF for a in range(256))
    assert (SBOX[0x00], SBOX[0x01], SBOX[0x53], SBOX[0xFF]) == (0x63, 0x7C, 0xED, 0x16)

    # 3. MixColumns: the RTL's xtime form equals the textbook matrix form on every column of a
    #    sweep, and matches the widely published column vectors
    for a in range(0, 256, 7):
        col = bytes([a, (a * 3) & 0xFF, (a * 5 + 1) & 0xFF, 255 - a])
        assert mix_column(col) == _mix_column_textbook(col), col.hex()
    for column, mixed in (
        ("db135345", "8e4da1bc"),
        ("f20a225c", "9fdc589d"),
        ("01010101", "01010101"),
        ("c6c6c6c6", "c6c6c6c6"),
        ("d4d4d4d5", "d5d5d7d6"),
        ("2d26314c", "4d7ebdf8"),
    ):
        assert mix_column(bytes.fromhex(column)) == bytes.fromhex(mixed), column

    # 4. ShiftRows is a pure permutation, and row 0 is not moved (bytes 0, 4, 8, 12)
    probe = bytes(range(16))
    assert sorted(shift_rows(probe)) == list(range(16))
    assert [shift_rows(probe)[4 * c] for c in range(4)] == [0, 4, 8, 12]
    assert shift_rows(probe) == bytes.fromhex("00050a0f04090e03080d02070c01060b")

    # 5. Key schedule: FIPS-197 Appendix A.1 round 1 key and last round key; the on-the-fly step
    #    (what the RTL does) reproduces the full expansion
    rks = expand_key(FIPS197_B_KEY)
    assert rks[1] == bytes.fromhex("a0fafe1788542cb123a339392a6c7605")
    assert rks[10] == FIPS197_B_LAST_ROUND_KEY
    rk, rcon = FIPS197_B_KEY, 0x01
    for r in range(1, NUM_ROUNDS + 1):
        rk = next_round_key(rk, rcon)
        rcon = xtime(rcon)
        assert rk == rks[r], f"on-the-fly round key {r} != expansion"
    assert rcon == 0x6C  # the 11th value the xtime chain would produce after 0x36

    # 6. FIPS-197 Appendix B and C.1 block vectors (ECB)
    assert encrypt_block(FIPS197_B_KEY, FIPS197_B_PLAINTEXT) == FIPS197_B_CIPHERTEXT
    assert encrypt_block(FIPS197_C1_KEY, FIPS197_C1_PLAINTEXT) == FIPS197_C1_CIPHERTEXT

    # 7. INC32: only the rightmost word moves, the carry is discarded
    assert inc32(bytes.fromhex("000102030405060708090a0b0c0d0e0f")).hex() == (
        "000102030405060708090a0b0c0d0e10"
    )
    assert inc32(bytes.fromhex("00112233445566778899aabbffffffff")).hex() == (
        "00112233445566778899aabb00000000"
    )
    assert inc32(bytes.fromhex("ffffffffffffffffffffffffffffffff")).hex() == (
        "ffffffffffffffffffffffff00000000"
    )

    # 8. SP 800-38A F.5.1: four-block CTR keystream, both directions
    for i, (pt, ct) in enumerate(
        zip(SP800_38A_CTR_PLAINTEXT, SP800_38A_CTR_CIPHERTEXT, strict=True)
    ):
        iv_i = SP800_38A_CTR_IV
        for _ in range(i):
            iv_i = inc32(iv_i)
        assert ctr_crypt(SP800_38A_CTR_KEY, iv_i, pt) == ct, f"CTR block {i} encrypt"
        assert ctr_crypt(SP800_38A_CTR_KEY, iv_i, ct) == pt, f"CTR block {i} decrypt"
    whole = ctr_crypt(SP800_38A_CTR_KEY, SP800_38A_CTR_IV, b"".join(SP800_38A_CTR_PLAINTEXT))
    assert whole == b"".join(SP800_38A_CTR_CIPHERTEXT)

    # 9. CTR with an all-zero input is the raw keystream, and the IV register view round-trips
    zero = bytes(BLOCK_BYTES)
    assert ctr_crypt(FIPS197_B_KEY, FIPS197_B_PLAINTEXT, zero) == FIPS197_B_CIPHERTEXT
    assert words_to_block(block_to_words(FIPS197_B_PLAINTEXT)) == FIPS197_B_PLAINTEXT
    assert block_to_words(FIPS197_B_PLAINTEXT) == (0x3243F6A8, 0x885A308D, 0x313198A2, 0xE0370734)

    print("aes128_model selftest: PASS")
    print("  FIPS-197 App.B ct  =", FIPS197_B_CIPHERTEXT.hex())
    print("  FIPS-197 App.C.1 ct=", FIPS197_C1_CIPHERTEXT.hex())
    print("  SP800-38A F.5.1 ct0=", SP800_38A_CTR_CIPHERTEXT[0].hex())


if __name__ == "__main__":
    selftest()
