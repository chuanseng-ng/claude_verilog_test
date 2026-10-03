#!/usr/bin/env python3
"""
gen_crypto_hex.py — generate crypto_fw.hex and crypto_fw_addrs.py for the Phase 6b SoC-level
CRYPTO FABRIC test (bead claude_verilog_test-f7vs.10, docs/PHASE6_IP_EXPANSION_PLAN.md §9 step 6,
L2 testability).

Scope, deliberately small. The L1 suite (test_crypto.py, `make crypto`) owns every behaviour of the
peripheral itself: FIPS-197 / FIPS-180-4 vectors, CTR, multi-block SHA, sticky-IRQ and hang-free
paths, a fault-mutation campaign. This image only proves that crypto_accel is REACHABLE AND CORRECT
THROUGH THE REAL SoC FABRIC — which nothing else drives — and that its interrupt reaches the CPU.

Path exercised (soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_CRYPTO slave 12 (crypto_accel, base 0x2000_F000)
  crypto_accel.irq_o --> interrupt_controller.irq_src_i[10] --> ext_irq --> CPU MEIP

Reuses the pure-Python hand-assembler of trng_fw/gen_trng_hex.py (same Assembler / lui_addi /
CSRRW / MRET machinery) — no riscv32 cross toolchain, so the suite is CI-safe (a toolchain-dependent
suite in soc_all_ci is what broke PR #195). Synchronisation and scoring are by commit_pc_o marker
PCs.

Register map (rtl/periph/crypto_accel.sv header — authoritative; word indices x 4):
  +0x00 CTRL    [1:0] mode (0 ECB, 1 CTR, 2 SHA), [2] START (W1P, reads 0), [3] IRQ_EN, [4] SHA_CONT
  +0x04 STATUS  [0] busy [1] done [2] key_valid [3] key_write_rejected
  +0x08..0x14 KEY0-3 (WO, read 0)   +0x18..0x24 IV0-3 (RW)   +0x28..0x34 DIN0-3 (WO aperture)
  +0x38..0x44 DOUT0-3 (RO)          +0x48..0x64 DIGEST0-7 (RO)
  +0x68 IRQ_STAT [0] sticky done    +0x6C IRQ_CLR (W1C) [0] done, [1] key_write_rejected
  +0x70..0x7C reserved (read 0)
Mode is written in a SEPARATE transfer before START (the header's software contract).

PHASE 1 — polled, IRQ_EN = 0 (the interrupt path is ARMED in the CPU, so any trap is a gate failure)
  * read the reset values through the fabric (CTRL 0, STATUS 0, reserved word 0x070 0); write IV0
    and read it back — IV is the one RW data word, so a mis-decoded APB index cannot return it;
  * FIPS-197 App. B: KEY0-3, DIN0-3 (an aperture: the four addresses are DIN0..DIN3 in order),
    STATUS must read exactly key_valid (0x4), the key and DIN windows must read back 0;
    CTRL = ECB (0), then CTRL = START; poll STATUS.done; STATUS must be done|key_valid (0x6),
    IRQ_STAT 1, DOUT0-3 must equal the FIPS-197 App. B ciphertext 3925841d 02dc09fb dc118597
    196a0b32; IRQ_CLR = done; STATUS must drop back to key_valid (0x4).
  The test scores crypto_irq / irq_src_i / ext_irq LOW for the whole phase while `done` is pending —
  the IRQ_EN gate crossing the fabric.

PHASE 2 — interrupt driven, IRQ_EN = 1  (marker P2_ARMED: IE set, done = 0, START not yet issued)
  * FIPS-197 App. C.1 (a DIFFERENT key, rewritten over the fabric while key_valid was already 1,
    and a different block): CTRL = IRQ_EN, CTRL = IRQ_EN|START.
    done -> crypto_irq -> irq_ctrl[10] -> CPU.
  * ISR: read STATUS, IRQ_STAT and the interrupt controller's PENDING_MASKED (bit 10 must be set —
    the controller really received irq_src_i[10]), then ONE write, IRQ_CLR = done, which drops the
    level-held source in a single access (nothing to race), then a read-back round trip so the level
    drains through the ext_irq synchroniser before MRET re-enables MIE. Exactly ONE trap.
  * after the ISR: DOUT0-3 must equal the App. C.1 ciphertext 69c4e0d8 6a7b0430 d8cdb780 70b4c55a
    and STATUS must read key_valid only.

PHASE 3 — one SHA-256 block, polled, IRQ_EN = 0 again
  * CTRL = SHA (mode 2, IRQ_EN cleared), 16 words "abc"+padding via DIN0-3 round-robin (M0 first),
    CTRL = SHA|START, poll done, DIGEST0-7 must equal FIPS 180-4 ba7816bf 8f01cfea 414140de 5dae2223
    b00361a3 96177a9c b410ff61 f20015ad. The test again scores the interrupt lines LOW (done is
    pending, IRQ_EN is 0 — the gate in the SHA path too).

Result area (SRAM word indices from RES_BASE_WI):
   0 ISR_COUNT  1 ISR_STATUS  2 ISR_IRQC_PENDING  3 ISR_IRQ_STAT  4 CTRL_RESET  5 STATUS_RESET
   6 RESERVED_READ  7 IV_READBACK  8 KEY_READ  9 DIN_READ  10 P1_STATUS_ARMED  11 P1_STATUS_DONE
   12 P1_IRQ_STAT  13 P1_STATUS_CLR  14-17 P1_DOUT0-3  18-21 P2_DOUT0-3  22 P2_STATUS
   23-30 P3_DIGEST0-7  31 P3_STATUS

Register allocation (MAIN): x2 = CRYPTO_BASE  x3 = IRQ_CTRL_BASE  x4 = RES_BASE_ADDR  x5 = staging
  x13 = scratch  x14/x15 = poll counter/limit  x16-x18 = scratch.  x1 is clobbered by the ISR.
Register allocation (ISR, at ISR_PC = ROM_BASE + 4): x26 x27 x28 x29 x30 x31 and x1.
"""

import hashlib
import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import ADDI, AND, ANDI, BLT, BNE, EBREAK, JAL, LW, SW  # noqa: E402
from tb.cocotb.soc.trng_fw.gen_trng_hex import (  # noqa: E402
    CSRRW,
    MRET,
    NOP,
    ROM_BASE,
    ROM_WORDS,
    Assembler,
    lui_addi,
)

ISR_OFFSET_WORDS = 1
MAIN_START_WORDS = 24

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------
CRYPTO_BASE = 0x2000_F000
CR_OFF_CTRL = 0x00
CR_OFF_STATUS = 0x04
CR_OFF_KEY0 = 0x08
CR_OFF_IV0 = 0x18
CR_OFF_DIN0 = 0x28
CR_OFF_DOUT0 = 0x38
CR_OFF_DIGEST0 = 0x48
CR_OFF_IRQ_STAT = 0x68
CR_OFF_IRQ_CLR = 0x6C
CR_OFF_RESERVED = 0x70

IRQ_CTRL_BASE = 0x2000_6000
IRQ_OFF_MASK = 0x004
IRQ_OFF_PENDING = 0x008
CRYPTO_IRQ_MASK_BIT = 0x400  # interrupt_controller.irq_src_i[10] = CRYPTO slot

SRAM_BASE = 0x0000_2000
RES_BASE_WI = 300  # SRAM word 300 = byte 0x0000_24B0
RES_BASE_ADDR = SRAM_BASE + RES_BASE_WI * 4
RES_ISR_COUNT = 0
RES_ISR_STATUS = 1
RES_ISR_IRQC_PEND = 2
RES_ISR_IRQ_STAT = 3
RES_CTRL_RESET = 4
RES_STATUS_RESET = 5
RES_RESERVED_READ = 6
RES_IV_READBACK = 7
RES_KEY_READ = 8
RES_DIN_READ = 9
RES_P1_STATUS_ARMED = 10
RES_P1_STATUS_DONE = 11
RES_P1_IRQ_STAT = 12
RES_P1_STATUS_CLR = 13
RES_P1_DOUT0 = 14
RES_P2_DOUT0 = 18
RES_P2_STATUS = 22
RES_P3_DIGEST0 = 23
RES_P3_STATUS = 31
RES_WORDS = 32

# ---------------------------------------------------------------------------
# Register field values
# ---------------------------------------------------------------------------
CTRL_ECB = 0x00
CTRL_ECB_IE = 0x08
CTRL_START = 0x04
CTRL_SHA = 0x02
ST_DONE = 0x2
ST_KEYV = 0x4
ST_DONE_KEYV = ST_DONE | ST_KEYV
CLR_DONE = 0x1
IV_PROBE = 0xA5C3_1E78
POLL_LIMIT = 4000
# The IRQ lands ~35 clk after the start and one wait iteration costs >= 13 clk, so 1000 iterations
# is >10x margin and keeps a missing interrupt a clean FAIL_PC well inside the test's cycle budget.
TRAP_LIMIT = 1000

# ---------------------------------------------------------------------------
# Known-answer vectors, taken from the standards as literal text (not computed by the DUT's models)
# ---------------------------------------------------------------------------


def _words(hexstr: str) -> list:
    b = bytes.fromhex(hexstr)
    return [int.from_bytes(b[i : i + 4], "big") for i in range(0, len(b), 4)]


# FIPS-197 Appendix B
KEY_B = _words("2b7e151628aed2a6abf7158809cf4f3c")
PT_B = _words("3243f6a8885a308d313198a2e0370734")
CT_B = _words("3925841d02dc09fbdc118597196a0b32")
# FIPS-197 Appendix C.1
KEY_C1 = _words("000102030405060708090a0b0c0d0e0f")
PT_C1 = _words("00112233445566778899aabbccddeeff")
CT_C1 = _words("69c4e0d86a7b0430d8cdb78070b4c55a")
# FIPS 180-4 "abc": one padded block (0x80 terminator, 64-bit big-endian bit length 24)
SHA_BLOCK = [0x61626380] + [0] * 14 + [0x00000018]
SHA_DIGEST = _words("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

# Cross-check the literals so a typo here cannot silently become the contract.
assert SHA_DIGEST == _words(hashlib.sha256(b"abc").hexdigest()), "SHA-256('abc') literal mismatch"
assert b"".join(w.to_bytes(4, "big") for w in SHA_BLOCK) == (
    b"abc" + b"\x80" + bytes(52) + (24).to_bytes(8, "big")
), "SHA padding literal mismatch"


def _emit_li(asm: Assembler, rd: int, value32: int) -> None:
    lo, hi = lui_addi(rd, value32)
    asm.emit(lo)
    asm.emit(hi)


def _fail_if_ne(asm: Assembler, ra: int, rb: int) -> None:
    asm.thunk(lambda lbl, pc: BNE(ra, rb, lbl["FAIL"] - pc))


def _rd_check(asm: Assembler, off: int, res_idx: int, expect: int, mask: int = 0xFFFF_FFFF) -> None:
    """x16 = CRYPTO[off]; store to result slot; (x16 & mask) must equal `expect`."""
    asm.emit(LW(16, 2, off))
    asm.emit(SW(16, 4, res_idx * 4))
    if mask != 0xFFFF_FFFF:
        _emit_li(asm, 18, mask)
        asm.emit(AND(16, 16, 18))
    _emit_li(asm, 17, expect)
    _fail_if_ne(asm, 16, 17)


def _wr(asm: Assembler, off: int, value: int) -> None:
    _emit_li(asm, 5, value)
    asm.emit(SW(5, 2, off))


def _poll_done(asm: Assembler, tag: str) -> None:
    """Poll CRYPTO_STATUS.done, bounded; FAIL if it never sets."""
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.label(f"{tag}_POLL")
    asm.emit(LW(16, 2, CR_OFF_STATUS))
    asm.emit(ANDI(16, 16, ST_DONE))
    asm.thunk(lambda lbl, pc: BNE(16, 0, lbl[f"{tag}_OK"] - pc))
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl[f"{tag}_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))  # never completed
    asm.label(f"{tag}_OK")


def _load_key_and_block(asm: Assembler, key: list, block: list) -> None:
    for i, w in enumerate(key):
        _wr(asm, CR_OFF_KEY0 + 4 * i, w)
    for i, w in enumerate(block):
        _wr(asm, CR_OFF_DIN0 + 4 * i, w)


def _check_words(asm: Assembler, off0: int, res0: int, expect: list) -> None:
    for i, w in enumerate(expect):
        _rd_check(asm, off0 + 4 * i, res0 + i, w)


def build_firmware(asm: Assembler) -> None:
    # WORD 0 (0x1000): reset-vector trampoline
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    asm.label("ISR")
    _emit_li(asm, 28, CRYPTO_BASE)
    _emit_li(asm, 27, IRQ_CTRL_BASE)
    asm.emit(LW(29, 28, CR_OFF_STATUS))  # what the trap can see
    asm.emit(LW(31, 28, CR_OFF_IRQ_STAT))
    asm.emit(LW(26, 27, IRQ_OFF_PENDING))  # interrupt controller PENDING_MASKED
    asm.emit(ADDI(1, 0, CLR_DONE))
    asm.emit(SW(1, 28, CR_OFF_IRQ_CLR))  # ONE write: W1C done, source drops
    _emit_li(asm, 30, RES_BASE_ADDR)
    asm.emit(LW(1, 30, RES_ISR_COUNT * 4))
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, RES_ISR_COUNT * 4))  # ISR_COUNT += 1
    asm.emit(SW(29, 30, RES_ISR_STATUS * 4))
    asm.emit(SW(26, 30, RES_ISR_IRQC_PEND * 4))
    asm.emit(SW(31, 30, RES_ISR_IRQ_STAT * 4))
    # Read-back: a fabric round trip that proves the clear landed and lets the level-held IRQ drain
    # through the ext_irq synchroniser before MRET re-enables MIE.
    asm.emit(LW(29, 28, CR_OFF_STATUS))
    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # MAIN
    asm.label("MAIN")
    _emit_li(asm, 2, CRYPTO_BASE)
    _emit_li(asm, 3, IRQ_CTRL_BASE)
    _emit_li(asm, 4, RES_BASE_ADDR)

    _emit_li(asm, 1, ROM_BASE + ISR_OFFSET_WORDS * 4)
    asm.emit(CSRRW(0, 0x305, 1))  # csrw mtvec, x1

    for w in range(RES_WORDS):  # zero the result area
        asm.emit(SW(0, 4, w * 4))

    # Arm the interrupt path. CTRL[3] stays 0 until phase 2, so no trap may occur before then.
    _emit_li(asm, 13, CRYPTO_IRQ_MASK_BIT)
    asm.emit(SW(13, 3, IRQ_OFF_MASK))  # IRQ_MASK bit 10 (CRYPTO)
    _emit_li(asm, 1, 0x800)
    asm.emit(CSRRW(0, 0x304, 1))  # csrw mie, x1   (MEIE)
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))  # csrw mstatus, x1 (MIE)

    asm.label("IRQ_READY")
    asm.nop()

    # ---- PHASE 1: polled ECB, FIPS-197 App. B ----------------------------------------------
    _rd_check(asm, CR_OFF_CTRL, RES_CTRL_RESET, 0x0)
    _rd_check(asm, CR_OFF_STATUS, RES_STATUS_RESET, 0x0)
    _rd_check(asm, CR_OFF_RESERVED, RES_RESERVED_READ, 0x0)
    _wr(asm, CR_OFF_IV0, IV_PROBE)
    _rd_check(asm, CR_OFF_IV0, RES_IV_READBACK, IV_PROBE)

    _load_key_and_block(asm, KEY_B, PT_B)
    _rd_check(asm, CR_OFF_STATUS, RES_P1_STATUS_ARMED, ST_KEYV)
    _rd_check(asm, CR_OFF_KEY0, RES_KEY_READ, 0x0)  # no key readback path
    _rd_check(asm, CR_OFF_DIN0, RES_DIN_READ, 0x0)  # DIN aperture reads 0
    _wr(asm, CR_OFF_CTRL, CTRL_ECB)  # mode first ...
    _wr(asm, CR_OFF_CTRL, CTRL_ECB | CTRL_START)  # ... START in a later transfer
    asm.label("P1_START")
    asm.nop()
    _poll_done(asm, "P1")
    _rd_check(asm, CR_OFF_STATUS, RES_P1_STATUS_DONE, ST_DONE_KEYV)
    _rd_check(asm, CR_OFF_IRQ_STAT, RES_P1_IRQ_STAT, 0x1)
    _check_words(asm, CR_OFF_DOUT0, RES_P1_DOUT0, CT_B)
    _wr(asm, CR_OFF_IRQ_CLR, CLR_DONE)
    _rd_check(asm, CR_OFF_STATUS, RES_P1_STATUS_CLR, ST_KEYV)
    asm.label("P1_DONE")
    asm.nop()

    # ---- PHASE 2: interrupt-driven ECB, FIPS-197 App. C.1 ----------------------------------
    _load_key_and_block(asm, KEY_C1, PT_C1)  # key REWRITTEN with key_valid already 1
    _wr(asm, CR_OFF_CTRL, CTRL_ECB_IE)  # IRQ enable, done = 0: line must stay low
    # P2_ARMED sits BEFORE the START write on purpose. A store commits only once its write response
    # has come back through the CPU -> fabric CDC path, and that round trip is longer than the
    # 11-clk AES latency, so a marker placed after START commits with `done` and the IRQ already up.
    # Here IE is set (its write has completed) and `done` is provably 0: phase 2 starts armed.
    asm.label("P2_ARMED")
    asm.nop()
    _wr(asm, CR_OFF_CTRL, CTRL_ECB_IE | CTRL_START)

    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, TRAP_LIMIT))
    asm.emit(ADDI(18, 0, 1))
    asm.label("TRAP_WAIT")
    asm.emit(LW(16, 4, RES_ISR_COUNT * 4))
    asm.thunk(lambda lbl, pc: BLT(16, 18, lbl["TRAP_WAIT_NEXT"] - pc))  # count < 1: keep waiting
    asm.thunk(lambda lbl, pc: JAL(0, lbl["TRAP_DONE"] - pc))
    asm.label("TRAP_WAIT_NEXT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["TRAP_WAIT"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))  # IRQ never arrived

    asm.label("TRAP_DONE")
    # Settle: a spurious second trap (stale level-held IRQ) lands here.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 600))
    asm.label("SETTLE")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["SETTLE"] - pc))

    # Teeth: exactly one trap; the ISR saw done (STATUS and IRQ_STAT); the controller saw bit 10.
    asm.emit(LW(17, 4, RES_ISR_COUNT * 4))
    asm.emit(ADDI(18, 0, 1))
    _fail_if_ne(asm, 17, 18)
    asm.emit(LW(17, 4, RES_ISR_STATUS * 4))
    asm.emit(ANDI(17, 17, ST_DONE))
    asm.emit(ADDI(18, 0, ST_DONE))
    _fail_if_ne(asm, 17, 18)
    asm.emit(LW(17, 4, RES_ISR_IRQ_STAT * 4))
    asm.emit(ADDI(18, 0, 1))
    _fail_if_ne(asm, 17, 18)
    asm.emit(LW(17, 4, RES_ISR_IRQC_PEND * 4))
    _emit_li(asm, 18, CRYPTO_IRQ_MASK_BIT)
    asm.emit(AND(17, 17, 18))
    _fail_if_ne(asm, 17, 18)

    _check_words(asm, CR_OFF_DOUT0, RES_P2_DOUT0, CT_C1)
    _rd_check(asm, CR_OFF_STATUS, RES_P2_STATUS, ST_KEYV)  # the ISR's IRQ_CLR dropped done
    asm.label("P2_DONE")
    asm.nop()

    # ---- PHASE 3: one polled SHA-256 block, FIPS 180-4 "abc" --------------------------------
    _wr(asm, CR_OFF_CTRL, CTRL_SHA)  # SHA mode, IRQ enable cleared
    asm.label("P3_GATE")
    asm.nop()
    for i, w in enumerate(SHA_BLOCK):  # M0 first; the four DIN addresses are one aperture
        _wr(asm, CR_OFF_DIN0 + 4 * (i % 4), w)
    _wr(asm, CR_OFF_CTRL, CTRL_SHA | CTRL_START)
    _poll_done(asm, "P3")
    _check_words(asm, CR_OFF_DIGEST0, RES_P3_DIGEST0, SHA_DIGEST)
    _rd_check(asm, CR_OFF_STATUS, RES_P3_STATUS, ST_DONE_KEYV)
    _wr(asm, CR_OFF_IRQ_CLR, CLR_DONE)
    asm.label("P3_DONE")
    asm.nop()

    # Flush D-cache so the backdoor SRAM read at the end of the test sees the stores.
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 2000))
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["FLUSH_WAIT"] - pc))

    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


ADDR_CONSTS = (
    "IV_PROBE",
    "RES_BASE_WI",
    "RES_ISR_COUNT",
    "RES_ISR_STATUS",
    "RES_ISR_IRQC_PEND",
    "RES_ISR_IRQ_STAT",
    "RES_CTRL_RESET",
    "RES_STATUS_RESET",
    "RES_RESERVED_READ",
    "RES_IV_READBACK",
    "RES_KEY_READ",
    "RES_DIN_READ",
    "RES_P1_STATUS_ARMED",
    "RES_P1_STATUS_DONE",
    "RES_P1_IRQ_STAT",
    "RES_P1_STATUS_CLR",
    "RES_P1_DOUT0",
    "RES_P2_DOUT0",
    "RES_P2_STATUS",
    "RES_P3_DIGEST0",
    "RES_P3_STATUS",
)

MARKERS = (
    ("PASS_PC", "PASS"),
    ("FAIL_PC", "FAIL"),
    ("ISR_PC", "ISR"),
    ("IRQ_READY_PC", "IRQ_READY"),
    ("P1_START_PC", "P1_START"),
    ("P1_DONE_PC", "P1_DONE"),
    ("P2_ARMED_PC", "P2_ARMED"),
    ("P2_DONE_PC", "P2_DONE"),
    ("P3_GATE_PC", "P3_GATE"),
    ("P3_DONE_PC", "P3_DONE"),
)


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm = Assembler(origin=ROM_BASE)
    build_firmware(asm)
    words = asm.resolve()
    labels = asm.labels
    assert len(words) <= ROM_WORDS, f"firmware too large: {len(words)} words > {ROM_WORDS}"
    for _, label in MARKERS:
        assert label in labels, f"label {label!r} not found in {list(labels)}"
    padded = list(words) + [NOP] * (ROM_WORDS - len(words))
    hex_path = os.path.join(out_dir, "crypto_fw.hex")
    with open(hex_path, "w") as f:
        for w in padded:
            f.write(f"{w:08x}\n")
    print(f"Wrote {len(padded)} words to {hex_path} ({len(words)} used)")

    addrs_path = os.path.join(out_dir, "crypto_fw_addrs.py")
    with open(addrs_path, "w") as f:
        f.write("# Auto-generated by gen_crypto_hex.py — do not edit.\n")
        for name, label in MARKERS:
            f.write(f"{name:<20} = 0x{labels[label]:08x}\n")
        for name in ADDR_CONSTS:
            f.write(f"{name:<20} = {globals()[name]}\n")
    print(f"Wrote {addrs_path}")


if __name__ == "__main__":
    main()
