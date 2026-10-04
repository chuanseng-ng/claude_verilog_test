#!/usr/bin/env python3
"""
gen_npu_hex.py — generate npu_fw.hex and npu_fw_addrs.py for the Phase 6c SoC-level NPU FABRIC test
(bead claude_verilog_test-f7vs.11, docs/PHASE6_IP_EXPANSION_PLAN.md §7 "6c -- NPU", L2 testability).

Scope, deliberately small. The L1 suite (test_npu.py, `make npu`) owns every behaviour of the
peripheral itself: arithmetic, requantiser corner cases, FIFO depths, weight-write rejection, the
sticky-IRQ and hang-free paths. This image only proves that npu_top is REACHABLE AND CORRECT THROUGH
THE REAL SoC FABRIC — which nothing else drives — and that its interrupt reaches the CPU.

Path exercised (soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_NPU slave 13 (npu_top, base 0x2001_0000)
  npu_top.irq_o --> interrupt_controller.irq_src_i[11] --> ext_irq --> CPU MEIP

Reuses the pure-Python hand-assembler of trng_fw/gen_trng_hex.py (same Assembler / lui_addi /
CSRRW / MRET machinery) and the structure of crypto_fw/gen_crypto_hex.py — no riscv32 cross
toolchain, so the suite is CI-safe. Synchronisation and scoring are by commit_pc_o marker PCs.

Register map (rtl/npu/npu_top.sv header — authoritative; word indices x 4):
  +0x00 CTRL     [0] RELU_EN, [3] IRQ_EN, [2] START (W1P, not stored, reads 0)
  +0x04 STATUS   RO live: [0] busy [1] done [2] ain_full [3] ain_empty [4] aout_valid
                 [5] aout_full [6] cfg_rejected (sticky). Reset value 0x08.
  +0x08 WADDR    RW [9:0], auto-increments on every accepted WDATA
  +0x0C WDATA    WO (4 packed INT8 -> weight SRAM[WADDR]); reads 0
  +0x10 TILEBASE RW [9:0]      +0x14 KLEN RW [5:0]      +0x18 SCALE RW [20:0]
  +0x1C AIN      WO (4 packed INT8 activations -> AIN FIFO); reads 0
  +0x20 AOUT     RO head of the AOUT FIFO (4 packed INT8); A READ POPS IT; empty reads 0
  +0x24 IRQ_STAT RO [0] sticky done    +0x28 IRQ_CLR W1C [0] done, [1] cfg_rejected
  +0x2C..        reserved (read 0)
START is written in a SEPARATE transfer after the mode bits (the header's software contract).

Weight tile (12 words written through WADDR=0 / WDATA, auto-increment), little-endian lanes:
  words 0-3   DENSE    rows [1,2,3,4] [5,6,7,8] [-1,-2,-3,-4] [10,0,-10,5]
  words 4-7   IDENTITY rows are the four unit vectors
  words 8-11  DENSE    (a second copy, so run 1 exercises a non-zero TILEBASE)
These are the hand-computed vectors pinned in tb/models/npu_model.py's selftest.

PHASE 1 — polled, KLEN = 1, TILEBASE = 8 (DENSE), SCALE = (5 >> 0), no ReLU, IRQ_EN = 0
  a = [1,2,3,4] -> acc = [48, 8, -32, 28] -> y = [127, 40, -128, 127]   (saturates both ways)
  Scored: reset STATUS (0x08), reserved word, WADDR auto-increment read-back (12), WDATA reads 0,
  STATUS after the AIN push, STATUS / IRQ_STAT at done, AOUT, STATUS after the popping read and
  after IRQ_CLR. The interrupt lines must stay LOW while `done` is pending (the IE gate).

PHASE 2 — interrupt driven, KLEN = 2, TILEBASE = 0 (DENSE then IDENTITY), SCALE = (3 >> 1), ReLU
  a0 = [1,2,3,4], a1 = [1,-2,3,-4] -> acc = [49, 6, -29, 24] -> y = [73, 9, 0, 36] (ReLU: lane 2)
  CTRL = RELU|IRQ_EN; done -> npu_irq -> irq_ctrl[11] -> CPU. The ISR reads STATUS / IRQ_STAT / the
  interrupt controller's PENDING_MASKED, writes ONE IRQ_CLR[0], reads back, MRET. A bounded wait on
  the ISR counter turns a missing interrupt into FAIL_PC rather than a hang. AOUT is read AFTER the
  trap (the ISR must not pop it); a second AOUT read of the now-empty FIFO must return 0.

PHASE 3 — ILLEGAL START (KLEN = 0), polled, IRQ_EN = 0
  The 2-cycle zero-length path: done sets, STATUS[6] cfg_rejected latches, no AOUT word is pushed,
  nothing hangs. STATUS must read done|ain_empty|cfg_rejected (0x4A); IRQ_CLR = 0b11 clears both.

Result area (SRAM word indices from RES_BASE_WI) — see RES_NAMES below.

Register allocation (MAIN): x2 = NPU_BASE  x3 = IRQ_CTRL_BASE  x4 = RES_BASE_ADDR  x5 = staging
  x13 = scratch  x14/x15 = poll counter/limit  x16-x18 = scratch.  x1 is clobbered by the ISR.
Register allocation (ISR, at ISR_PC = ROM_BASE + 4): x26 x27 x28 x29 x30 x31 and x1.
"""

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
from tb.models import npu_model  # noqa: E402

ISR_OFFSET_WORDS = 1
MAIN_START_WORDS = 24

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------
NPU_BASE = 0x2001_0000
NP_OFF_CTRL = 0x00
NP_OFF_STATUS = 0x04
NP_OFF_WADDR = 0x08
NP_OFF_WDATA = 0x0C
NP_OFF_TILEBASE = 0x10
NP_OFF_KLEN = 0x14
NP_OFF_SCALE = 0x18
NP_OFF_AIN = 0x1C
NP_OFF_AOUT = 0x20
NP_OFF_IRQ_STAT = 0x24
NP_OFF_IRQ_CLR = 0x28
NP_OFF_RESERVED = 0x2C

IRQ_CTRL_BASE = 0x2000_6000
IRQ_OFF_MASK = 0x004
IRQ_OFF_PENDING = 0x008
NPU_IRQ_MASK_BIT = 0x800  # interrupt_controller.irq_src_i[11] = NPU slot

SRAM_BASE = 0x0000_2000
RES_BASE_WI = 300  # SRAM word 300 = byte 0x0000_24B0
RES_BASE_ADDR = SRAM_BASE + RES_BASE_WI * 4

RES_ISR_COUNT = 0
RES_ISR_STATUS = 1
RES_ISR_IRQC_PEND = 2
RES_ISR_IRQ_STAT = 3
RES_STATUS_RESET = 4
RES_RESERVED_READ = 5
RES_WADDR_RB = 6
RES_WDATA_READ = 7
RES_P1_TILEBASE_RB = 8
RES_P1_STATUS_ARMED = 9
RES_P1_STATUS_DONE = 10
RES_P1_IRQ_STAT = 11
RES_P1_AOUT = 12
RES_P1_STATUS_POP = 13
RES_P1_STATUS_CLR = 14
RES_P2_SCALE_RB = 15
RES_P2_CTRL_RB = 16
RES_P2_STATUS_ARMED = 17
RES_P2_STATUS_PRE = 18
RES_P2_AOUT = 19
RES_P2_STATUS_POP = 20
RES_P2_AOUT_EMPTY = 21
RES_P3_STATUS_DONE = 22
RES_P3_IRQ_STAT = 23
RES_P3_AOUT_EMPTY = 24
RES_P3_STATUS_CLR = 25
RES_NAMES = (
    "RES_ISR_COUNT",
    "RES_ISR_STATUS",
    "RES_ISR_IRQC_PEND",
    "RES_ISR_IRQ_STAT",
    "RES_STATUS_RESET",
    "RES_RESERVED_READ",
    "RES_WADDR_RB",
    "RES_WDATA_READ",
    "RES_P1_TILEBASE_RB",
    "RES_P1_STATUS_ARMED",
    "RES_P1_STATUS_DONE",
    "RES_P1_IRQ_STAT",
    "RES_P1_AOUT",
    "RES_P1_STATUS_POP",
    "RES_P1_STATUS_CLR",
    "RES_P2_SCALE_RB",
    "RES_P2_CTRL_RB",
    "RES_P2_STATUS_ARMED",
    "RES_P2_STATUS_PRE",
    "RES_P2_AOUT",
    "RES_P2_STATUS_POP",
    "RES_P2_AOUT_EMPTY",
    "RES_P3_STATUS_DONE",
    "RES_P3_IRQ_STAT",
    "RES_P3_AOUT_EMPTY",
    "RES_P3_STATUS_CLR",
)
RES_WORDS = len(RES_NAMES)

# ---------------------------------------------------------------------------
# Register field values
# ---------------------------------------------------------------------------
CTRL_RELU_IE = 0x09  # RELU_EN | IRQ_EN
CTRL_START = 0x04
ST_DONE = 0x2
ST_RESET = 0x08  # ain_empty
ST_AIN_PUSHED_1 = 0x00  # one AIN word queued: not empty, not full
ST_DONE_AOUT = 0x1A  # done | ain_empty | aout_valid
ST_DONE_POPPED = 0x0A  # done | ain_empty
ST_AOUT_ONLY = 0x18  # ain_empty | aout_valid
ST_ILLEGAL = 0x4A  # cfg_rejected | ain_empty | done
CLR_DONE = 0x1
CLR_BOTH = 0x3
POLL_LIMIT = 4000
# NPU latency from START is a few tens of clk; one wait iteration costs >= 13 clk, so 1000
# iterations is a wide margin and keeps a missing interrupt a clean FAIL_PC inside the test budget.
TRAP_LIMIT = 1000

# ---------------------------------------------------------------------------
# Vectors. Hand-computed literals (pinned in npu_model.selftest), cross-checked against the model.
# ---------------------------------------------------------------------------
DENSE_ROWS = [
    npu_model.pack_word([1, 2, 3, 4]),
    npu_model.pack_word([5, 6, 7, 8]),
    npu_model.pack_word([-1, -2, -3, -4]),
    npu_model.pack_word([10, 0, -10, 5]),
]
IDENT_ROWS = [0x00000001, 0x00000100, 0x00010000, 0x01000000]
WEIGHTS = DENSE_ROWS + IDENT_ROWS + DENSE_ROWS
assert DENSE_ROWS == [0x04030201, 0x08070605, 0xFCFDFEFF, 0x05F6000A], "dense tile literal"

P1_TILEBASE = 8
P1_SCALE = npu_model.make_scale(5, 0)
P1_AIN = [npu_model.pack_word([1, 2, 3, 4])]
P1_EXPECT = npu_model.pack_word([127, 40, -128, 127])

P2_TILEBASE = 0
P2_SCALE = npu_model.make_scale(3, 1)
P2_AIN = [npu_model.pack_word([1, 2, 3, 4]), npu_model.pack_word([1, -2, 3, -4])]
P2_EXPECT = npu_model.pack_word([73, 9, 0, 36])

# Cross-check the literals against the model so a typo here cannot silently become the contract.
_mem = npu_model.blank_weight_mem()
_mem[: len(WEIGHTS)] = WEIGHTS
assert npu_model.infer(_mem, P1_TILEBASE, P1_AIN, P1_SCALE, False) == P1_EXPECT
assert npu_model.infer(_mem, P2_TILEBASE, P2_AIN, P2_SCALE, True) == P2_EXPECT
assert npu_model.unpack_word(P1_EXPECT) == (127, 40, -128, 127)
assert npu_model.unpack_word(P2_EXPECT) == (73, 9, 0, 36)


def _emit_li(asm: Assembler, rd: int, value32: int) -> None:
    lo, hi = lui_addi(rd, value32)
    asm.emit(lo)
    asm.emit(hi)


def _fail_if_ne(asm: Assembler, ra: int, rb: int) -> None:
    asm.thunk(lambda lbl, pc: BNE(ra, rb, lbl["FAIL"] - pc))


def _rd_check(
    asm: Assembler, off: int, res_name: str, expect: int, mask: int = 0xFFFF_FFFF
) -> None:
    """x16 = NPU[off]; store to result slot; (x16 & mask) must equal `expect`."""
    asm.emit(LW(16, 2, off))
    asm.emit(SW(16, 4, globals()[res_name] * 4))
    if mask != 0xFFFF_FFFF:
        _emit_li(asm, 18, mask)
        asm.emit(AND(16, 16, 18))
    _emit_li(asm, 17, expect)
    _fail_if_ne(asm, 16, 17)


def _wr(asm: Assembler, off: int, value: int) -> None:
    _emit_li(asm, 5, value)
    asm.emit(SW(5, 2, off))


def _poll_done(asm: Assembler, tag: str) -> None:
    """Poll NPU_STATUS.done, bounded; FAIL if it never sets."""
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.label(f"{tag}_POLL")
    asm.emit(LW(16, 2, NP_OFF_STATUS))
    asm.emit(ANDI(16, 16, ST_DONE))
    asm.thunk(lambda lbl, pc: BNE(16, 0, lbl[f"{tag}_OK"] - pc))
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl[f"{tag}_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))  # never completed
    asm.label(f"{tag}_OK")


def build_firmware(asm: Assembler) -> None:
    # WORD 0 (0x1000): reset-vector trampoline
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    asm.label("ISR")
    _emit_li(asm, 28, NPU_BASE)
    _emit_li(asm, 27, IRQ_CTRL_BASE)
    asm.emit(LW(29, 28, NP_OFF_STATUS))  # what the trap can see
    asm.emit(LW(31, 28, NP_OFF_IRQ_STAT))
    asm.emit(LW(26, 27, IRQ_OFF_PENDING))  # interrupt controller PENDING_MASKED
    asm.emit(ADDI(1, 0, CLR_DONE))
    asm.emit(SW(1, 28, NP_OFF_IRQ_CLR))  # ONE write: W1C done, source drops (AOUT is NOT read here)
    _emit_li(asm, 30, RES_BASE_ADDR)
    asm.emit(LW(1, 30, RES_ISR_COUNT * 4))
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, RES_ISR_COUNT * 4))  # ISR_COUNT += 1
    asm.emit(SW(29, 30, RES_ISR_STATUS * 4))
    asm.emit(SW(26, 30, RES_ISR_IRQC_PEND * 4))
    asm.emit(SW(31, 30, RES_ISR_IRQ_STAT * 4))
    # Read-back: a fabric round trip that proves the clear landed and lets the level-held IRQ drain
    # through the ext_irq synchroniser before MRET re-enables MIE.
    asm.emit(LW(29, 28, NP_OFF_STATUS))
    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # MAIN
    asm.label("MAIN")
    _emit_li(asm, 2, NPU_BASE)
    _emit_li(asm, 3, IRQ_CTRL_BASE)
    _emit_li(asm, 4, RES_BASE_ADDR)

    _emit_li(asm, 1, ROM_BASE + ISR_OFFSET_WORDS * 4)
    asm.emit(CSRRW(0, 0x305, 1))  # csrw mtvec, x1

    for w in range(RES_WORDS):  # zero the result area
        asm.emit(SW(0, 4, w * 4))

    # Arm the interrupt path. CTRL[3] stays 0 until phase 2, so no trap may occur before then.
    _emit_li(asm, 13, NPU_IRQ_MASK_BIT)
    asm.emit(SW(13, 3, IRQ_OFF_MASK))  # IRQ_MASK bit 11 (NPU)
    _emit_li(asm, 1, 0x800)
    asm.emit(CSRRW(0, 0x304, 1))  # csrw mie, x1   (MEIE)
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))  # csrw mstatus, x1 (MIE)

    asm.label("IRQ_READY")
    asm.nop()

    # ---- reset values, then the 12-word weight tile through WADDR / WDATA -------------------
    _rd_check(asm, NP_OFF_STATUS, "RES_STATUS_RESET", ST_RESET)
    _rd_check(asm, NP_OFF_RESERVED, "RES_RESERVED_READ", 0x0)
    _wr(asm, NP_OFF_WADDR, 0)
    for w in WEIGHTS:
        _wr(asm, NP_OFF_WDATA, w)
    _rd_check(asm, NP_OFF_WADDR, "RES_WADDR_RB", len(WEIGHTS))  # auto-increment landed 12 times
    _rd_check(asm, NP_OFF_WDATA, "RES_WDATA_READ", 0x0)  # weight port is write-only

    # ---- PHASE 1: polled, KLEN = 1, saturating, IRQ_EN = 0 ----------------------------------
    _wr(asm, NP_OFF_TILEBASE, P1_TILEBASE)
    _rd_check(asm, NP_OFF_TILEBASE, "RES_P1_TILEBASE_RB", P1_TILEBASE)
    _wr(asm, NP_OFF_KLEN, 1)
    _wr(asm, NP_OFF_SCALE, P1_SCALE)
    _wr(asm, NP_OFF_CTRL, 0)
    for a in P1_AIN:
        _wr(asm, NP_OFF_AIN, a)
    _rd_check(asm, NP_OFF_STATUS, "RES_P1_STATUS_ARMED", ST_AIN_PUSHED_1)
    _wr(asm, NP_OFF_CTRL, CTRL_START)  # mode bits were written in an earlier transfer
    asm.label("P1_START")
    asm.nop()
    _poll_done(asm, "P1")
    _rd_check(asm, NP_OFF_STATUS, "RES_P1_STATUS_DONE", ST_DONE_AOUT)
    _rd_check(asm, NP_OFF_IRQ_STAT, "RES_P1_IRQ_STAT", 0x1)
    _rd_check(asm, NP_OFF_AOUT, "RES_P1_AOUT", P1_EXPECT)  # this read pops
    _rd_check(asm, NP_OFF_STATUS, "RES_P1_STATUS_POP", ST_DONE_POPPED)
    _wr(asm, NP_OFF_IRQ_CLR, CLR_DONE)
    _rd_check(asm, NP_OFF_STATUS, "RES_P1_STATUS_CLR", ST_RESET)
    asm.label("P1_DONE")
    asm.nop()

    # ---- PHASE 2: interrupt driven, KLEN = 2, ReLU ------------------------------------------
    _wr(asm, NP_OFF_TILEBASE, P2_TILEBASE)
    _wr(asm, NP_OFF_KLEN, 2)
    _wr(asm, NP_OFF_SCALE, P2_SCALE)
    _rd_check(
        asm, NP_OFF_SCALE, "RES_P2_SCALE_RB", P2_SCALE
    )  # shift bit set: a [20:16] decode check
    _wr(asm, NP_OFF_CTRL, CTRL_RELU_IE)  # IRQ enable + ReLU, done = 0: line must stay low
    _rd_check(asm, NP_OFF_CTRL, "RES_P2_CTRL_RB", CTRL_RELU_IE)
    for a in P2_AIN:
        _wr(asm, NP_OFF_AIN, a)
    _rd_check(asm, NP_OFF_STATUS, "RES_P2_STATUS_ARMED", ST_AIN_PUSHED_1)
    # P2_ARMED sits BEFORE the START write on purpose. A store commits only once its write response
    # has come back through the CPU -> fabric CDC path, and that round trip is longer than the NPU's
    # start-to-done latency, so a marker placed after START commits with `done` and the IRQ already
    # up. Here IE is set (its write has completed) and `done` is provably 0: phase 2 starts armed.
    asm.label("P2_ARMED")
    asm.nop()
    _wr(asm, NP_OFF_CTRL, CTRL_RELU_IE | CTRL_START)

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

    # Teeth: exactly one trap; the ISR saw done (STATUS and IRQ_STAT); the controller saw bit 11.
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
    _emit_li(asm, 18, NPU_IRQ_MASK_BIT)
    asm.emit(AND(17, 17, 18))
    _fail_if_ne(asm, 17, 18)

    _rd_check(asm, NP_OFF_STATUS, "RES_P2_STATUS_PRE", ST_AOUT_ONLY)  # ISR's IRQ_CLR dropped done
    _rd_check(asm, NP_OFF_AOUT, "RES_P2_AOUT", P2_EXPECT)  # this read pops
    _rd_check(asm, NP_OFF_STATUS, "RES_P2_STATUS_POP", ST_RESET)
    _rd_check(asm, NP_OFF_AOUT, "RES_P2_AOUT_EMPTY", 0x0)  # empty FIFO reads 0
    asm.label("P2_DONE")
    asm.nop()

    # ---- PHASE 3: illegal START (KLEN = 0), polled, IRQ_EN = 0 ------------------------------
    _wr(asm, NP_OFF_CTRL, 0)  # IRQ enable and ReLU cleared
    asm.label("P3_GATE")
    asm.nop()
    _wr(asm, NP_OFF_KLEN, 0)
    _wr(asm, NP_OFF_CTRL, CTRL_START)
    _poll_done(asm, "P3")
    _rd_check(asm, NP_OFF_STATUS, "RES_P3_STATUS_DONE", ST_ILLEGAL)
    _rd_check(asm, NP_OFF_IRQ_STAT, "RES_P3_IRQ_STAT", 0x1)
    _rd_check(asm, NP_OFF_AOUT, "RES_P3_AOUT_EMPTY", 0x0)  # an illegal start pushes no result
    _wr(asm, NP_OFF_IRQ_CLR, CLR_BOTH)
    _rd_check(asm, NP_OFF_STATUS, "RES_P3_STATUS_CLR", ST_RESET)
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


ADDR_CONSTS = ("RES_BASE_WI", *RES_NAMES)

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
    hex_path = os.path.join(out_dir, "npu_fw.hex")
    with open(hex_path, "w") as f:
        for w in padded:
            f.write(f"{w:08x}\n")
    print(f"Wrote {len(padded)} words to {hex_path} ({len(words)} used)")

    addrs_path = os.path.join(out_dir, "npu_fw_addrs.py")
    with open(addrs_path, "w") as f:
        f.write("# Auto-generated by gen_npu_hex.py — do not edit.\n")
        for name, label in MARKERS:
            f.write(f"{name:<22} = 0x{labels[label]:08x}\n")
        for name in ADDR_CONSTS:
            f.write(f"{name:<22} = {globals()[name]}\n")
    print(f"Wrote {addrs_path}")


if __name__ == "__main__":
    main()
