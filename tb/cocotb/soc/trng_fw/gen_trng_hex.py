#!/usr/bin/env python3
"""
gen_trng_hex.py — generate trng_fw.hex and trng_fw_addrs.py for the Phase 6a-4 SoC-level TRNG
test (bead claude_verilog_test-f7vs.8 steps 4-5, docs/PHASE6_IP_EXPANSION_PLAN.md §10).

Modelled directly on wdt_fw/gen_wdt_hex.py — same Assembler/lui_addi/CSRRW/MRET machinery, same
commit_pc_o marker-PC synchronisation idiom. A committed pure-Python hand-assembler, so the suite
needs no riscv32 cross toolchain and is CI-safe (a toolchain-dependent suite in soc_all_ci is what
broke PR #195).

Path exercised (confirmed from soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_TRNG slave 10 (trng, base 0x2000_D000)

TRNG register map (rtl/periph/trng.sv, word indices):
  +0x00 TRNG_CTRL    RW  [0] enable, [1] IRQ enable, [5:2] FIFO threshold
  +0x04 TRNG_STATUS  RO  [0] data ready, [1] FIFO full, [2] health_fail, [3] INSECURE
  +0x08 TRNG_DATA    RO  read POPS one word (0 when empty)
  +0x0C TRNG_SEED    RW  reset 0xACE1_2345; sampled at the CTRL.EN 0->1 edge
  +0x10 TRNG_IRQ_CLR WO  W1C against STATUS[2]

One image, two phases. Every word the peripheral produces is a pure function of TRNG_SEED
(tb/models/trng_lfsr_model.py), so the cocotb test can check the words firmware popped are
VALUE-EXACT against the model — not merely "some data arrived".

PHASE 1 — polled, IE = 0
  * read STATUS before enabling: must be exactly 0x8 (INSECURE only). That is the marker that the
    default build is a deterministic LFSR, and firmware can see it through the fabric.
  * read DATA on the empty FIFO: must be 0 (and must not underflow).
  * read SEED: must be the reset value 0xACE1_2345; write SEED1, read it back.
  * enable (CTRL = EN); poll STATUS until FIFO full; STATUS must read 0xB (ready|full|insecure).
  * pop PHASE1_WORDS words, polling STATUS[0] before each, storing each to SRAM.
  The IRQ path is armed BEFORE this phase (interrupt_controller bit 8, MEIE, MIE) while CTRL.IE
  stays 0: data is ready for the whole phase, so a single spurious trap here proves the IE gate is
  not working. The test scores trng_irq low throughout phase 1 from the SoC boundary.

PHASE 2 — interrupt driven
  * disable (CTRL = 0), write SEED2, then ONE write CTRL = EN | IE | (THRESHOLD << 2): the enable
    edge starts a fresh session from SEED2 and the IRQ level asserts when the FIFO reaches
    THRESHOLD words.
  * trng_irq -> interrupt_controller[8] -> CPU MEIP -> ISR.

  ISR design — ONE write, no window. trng's irq_o is a LEVEL (IE & fifo_level >= threshold), so
  "clear the status, then disable" would be two writes with a window in between (the PWM L2
  lesson: every MMIO access crosses the full fabric, so the condition can re-fire between them).
  Here the ISR reads STATUS (logged), then makes a SINGLE write, CTRL = EN | THRESHOLD<<2 with IE
  cleared, which drops the source in one access; there is nothing to clear. Its last action is a
  CTRL read-back: a fabric round trip that proves the write landed and lets the level-held IRQ
  drain through the 2-FF ext_irq synchroniser before MRET re-enables MIE (otherwise a stale
  ext_irq would re-vector). Exactly ONE trap is expected; firmware settles and checks that.
  * main then pops PHASE2_WORDS words (polling data-ready) and stores them.

Result area (SRAM word indices from RES_BASE_WI):
   0 ISR_COUNT          1 ISR_STATUS (TRNG_STATUS the ISR saw)
   2 STATUS_PRE         3 EMPTY_READ         4 SEED_RESET_READ    5 SEED_READBACK
   6 STATUS_FULL        8.. phase-1 words    16.. phase-2 words

Register allocation (MAIN):
  x2 = TRNG_BASE  x3 = IRQ_CTRL_BASE  x4 = RES_BASE_ADDR  x5 = write staging
  x14/x15 = poll counter/limit  x16-x24 = scratch  x31 = result marker (set only at the end)
Register allocation (ISR, at ISR_PC = ROM_BASE + 4):
  x28 = TRNG_BASE  x29 = STATUS seen  x30 = RES_BASE_ADDR  x31 = scratch  x1 = count
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, ANDI, SW, LW, BNE, BLT, JAL, EBREAK,
)


def CSRRW(rd: int, csr: int, rs1: int) -> int:
    """CSRRW rd, csr, rs1"""
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73


def MRET() -> int:
    """MRET — return from machine-mode trap (restores PC from mepc, MIE from MPIE)"""
    return 0x30200073


# ---------------------------------------------------------------------------
# ROM layout
# ---------------------------------------------------------------------------
ROM_BASE   = 0x0000_1000
ROM_WORDS  = 1024
NOP        = 0x00000013   # ADDI x0, x0, 0

# Word 0 = reset-vector trampoline (JAL x0, MAIN); word 1 = ISR start.
ISR_OFFSET_WORDS = 1
MAIN_START_WORDS = 20

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------
TRNG_BASE           = 0x2000_D000
TRNG_OFF_CTRL       = 0x00
TRNG_OFF_STATUS     = 0x04
TRNG_OFF_DATA       = 0x08
TRNG_OFF_SEED       = 0x0C

IRQ_CTRL_BASE       = 0x2000_6000
IRQ_OFF_MASK        = 0x004
TRNG_IRQ_MASK_BIT   = 0x100   # interrupt_controller.irq_src_i[8] = TRNG slot

SRAM_BASE           = 0x0000_2000
RES_BASE_WI         = 300     # SRAM word 300 = byte 0x0000_24B0
RES_BASE_ADDR       = SRAM_BASE + RES_BASE_WI * 4
RES_ISR_COUNT       = 0
RES_ISR_STATUS      = 1
RES_STATUS_PRE      = 2
RES_EMPTY_READ      = 3
RES_SEED_RESET      = 4
RES_SEED_READBACK   = 5
RES_STATUS_FULL     = 6
RES_P1_WORDS        = 8
RES_P2_WORDS        = 16

# ---------------------------------------------------------------------------
# Test parameters
# ---------------------------------------------------------------------------
SEED_RESET_VAL = 0xACE1_2345
SEED1          = 0x1234_5678   # phase 1 (healthy: see trng_lfsr_model.GOLDEN_SEEDS)
SEED2          = 0xDEAD_BEEF   # phase 2 (healthy: see trng_lfsr_model.GOLDEN_SEEDS)
PHASE1_WORDS   = 8
PHASE2_WORDS   = 4
THRESHOLD      = 2

CTRL_EN        = 0x1
CTRL_IE        = 0x2

STATUS_PRE_EXPECT  = 0x8   # INSECURE only
STATUS_FULL_EXPECT = 0xB   # INSECURE | full | ready

POLL_LIMIT     = 4000


def lui_addi(rd: int, value32: int):
    """Return (lui_word, addi_word) to load a 32-bit constant into rd."""
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}): upper=0x{upper20:05x} "
        f"lower_signed={lower_signed} -> 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


class Assembler:
    """Two-pass label assembler.  Labels resolve to byte PCs; ROM_BASE is the origin."""
    def __init__(self, origin: int = ROM_BASE):
        self._origin = origin
        self._items  = []
        self.labels  = {}

    def emit(self, word: int):
        self._items.append(('word', word & 0xFFFF_FFFF))

    def nop(self):
        self._items.append(('word', NOP))

    def label(self, name: str):
        self._items.append(('label', name))

    def thunk(self, fn):
        """Emit a word whose encoding depends on resolved label addresses."""
        self._items.append(('thunk', fn))

    def pad_to_word(self, word_idx: int):
        """Pad with NOPs until we are at word_idx."""
        cur = sum(1 for t, _ in self._items if t != 'label')
        assert cur <= word_idx, (
            f"pad_to_word({word_idx}): already at word {cur}"
        )
        while cur < word_idx:
            self.nop()
            cur += 1

    def resolve(self):
        self.labels = {}
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                self.labels[val] = self._origin + idx * 4
            else:
                idx += 1
        words = []
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                continue
            cur_pc = self._origin + idx * 4
            w = val(self.labels, cur_pc) & 0xFFFF_FFFF if typ == 'thunk' else val
            words.append(w)
            idx += 1
        return words


def _emit_li(asm: Assembler, rd: int, value32: int) -> None:
    lo, hi = lui_addi(rd, value32)
    asm.emit(lo)
    asm.emit(hi)


def _fail_if_ne(asm: Assembler, ra: int, rb: int) -> None:
    asm.thunk(lambda lbl, pc: BNE(ra, rb, lbl["FAIL"] - pc))


def _emit_pop_loop(asm: Assembler, tag: str, first_result_wi: int, n_words: int) -> None:
    """Pop n_words from TRNG_DATA into result[first_result_wi..], polling STATUS[0] before each.

    x22 = &result slot, x23 = words left. Each pop is a bounded poll (x14/x15).
    """
    asm.emit(ADDI(22, 4, first_result_wi * 4))
    asm.emit(ADDI(23, 0, n_words))
    asm.label(f"{tag}_WORD")
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.label(f"{tag}_POLL")
    asm.emit(LW(16, 2, TRNG_OFF_STATUS))
    asm.emit(ANDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 0, lbl[f"{tag}_POP"] - pc))     # data ready
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl[f"{tag}_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))               # never became ready
    asm.label(f"{tag}_POP")
    asm.emit(LW(17, 2, TRNG_OFF_DATA))                                 # read POPS the FIFO
    asm.emit(SW(17, 22, 0))
    asm.emit(ADDI(22, 22, 4))
    asm.emit(ADDI(23, 23, -1))
    asm.thunk(lambda lbl, pc: BNE(23, 0, lbl[f"{tag}_WORD"] - pc))


def build_firmware(asm: Assembler) -> None:
    # WORD 0 (0x1000): reset-vector trampoline
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    asm.label("ISR")
    _emit_li(asm, 28, TRNG_BASE)
    asm.emit(LW(29, 28, TRNG_OFF_STATUS))          # x29 = what this trap can see
    asm.emit(ADDI(31, 0, CTRL_EN | (THRESHOLD << 2)))
    asm.emit(SW(31, 28, TRNG_OFF_CTRL))            # ONE write: IE cleared, source drops
    _emit_li(asm, 30, RES_BASE_ADDR)
    asm.emit(LW(1, 30, RES_ISR_COUNT * 4))
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, RES_ISR_COUNT * 4))         # ISR_COUNT += 1
    asm.emit(SW(29, 30, RES_ISR_STATUS * 4))       # STATUS seen
    # Read-back: a fabric round trip that proves the CTRL write landed and lets the level-held
    # IRQ drain through the ext_irq 2-FF synchroniser before MRET re-enables MIE.
    asm.emit(LW(29, 28, TRNG_OFF_CTRL))
    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # MAIN
    asm.label("MAIN")
    _emit_li(asm, 2, TRNG_BASE)
    _emit_li(asm, 3, IRQ_CTRL_BASE)
    _emit_li(asm, 4, RES_BASE_ADDR)

    # MTVEC -> ISR
    _emit_li(asm, 1, ROM_BASE + ISR_OFFSET_WORDS * 4)
    asm.emit(CSRRW(0, 0x305, 1))   # csrw mtvec, x1

    # Zero the whole result area so the teeth checks in the test are reliable.
    for w in range(RES_P2_WORDS + PHASE2_WORDS):
        asm.emit(SW(0, 4, w * 4))

    # Arm the interrupt path. CTRL.IE stays 0 until phase 2, so no trap may occur before then.
    _emit_li(asm, 13, TRNG_IRQ_MASK_BIT)
    asm.emit(SW(13, 3, IRQ_OFF_MASK))              # IRQ_MASK bit 8 (TRNG)
    _emit_li(asm, 1, 0x800)
    asm.emit(CSRRW(0, 0x304, 1))                   # csrw mie, x1   (MEIE)
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))                   # csrw mstatus, x1 (MIE)

    asm.label("IRQ_READY")
    asm.nop()

    # ---- PHASE 1: polled -------------------------------------------------------------------
    # STATUS before enable == 0x8 (INSECURE only; not ready, not full, not failed).
    asm.emit(LW(16, 2, TRNG_OFF_STATUS))
    asm.emit(SW(16, 4, RES_STATUS_PRE * 4))
    asm.emit(ADDI(17, 0, STATUS_PRE_EXPECT))
    _fail_if_ne(asm, 16, 17)

    # DATA read on an empty FIFO returns 0.
    asm.emit(LW(16, 2, TRNG_OFF_DATA))
    asm.emit(SW(16, 4, RES_EMPTY_READ * 4))
    _fail_if_ne(asm, 16, 0)

    # SEED reset value, then write SEED1 and read it back.
    asm.emit(LW(16, 2, TRNG_OFF_SEED))
    asm.emit(SW(16, 4, RES_SEED_RESET * 4))
    _emit_li(asm, 17, SEED_RESET_VAL)
    _fail_if_ne(asm, 16, 17)
    _emit_li(asm, 5, SEED1)
    asm.emit(SW(5, 2, TRNG_OFF_SEED))
    asm.emit(LW(16, 2, TRNG_OFF_SEED))
    asm.emit(SW(16, 4, RES_SEED_READBACK * 4))
    _fail_if_ne(asm, 16, 5)

    # Enable (IE = 0). CTRL is written after SEED: the enable edge samples it.
    asm.emit(ADDI(5, 0, CTRL_EN))
    asm.emit(SW(5, 2, TRNG_OFF_CTRL))
    asm.label("P1_ENABLED")
    asm.nop()

    # Poll STATUS until FIFO full (bit 1), bounded.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.label("FULL_POLL")
    asm.emit(LW(16, 2, TRNG_OFF_STATUS))
    asm.emit(ANDI(18, 16, 2))
    asm.thunk(lambda lbl, pc: BNE(18, 0, lbl["FULL_SEEN"] - pc))
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["FULL_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))          # FIFO never filled
    asm.label("FULL_SEEN")
    # Full stalls the entropy arm, so STATUS is now stable: ready | full | INSECURE, no failure.
    asm.emit(LW(16, 2, TRNG_OFF_STATUS))
    asm.emit(SW(16, 4, RES_STATUS_FULL * 4))
    asm.emit(ADDI(17, 0, STATUS_FULL_EXPECT))
    _fail_if_ne(asm, 16, 17)

    _emit_pop_loop(asm, "P1", RES_P1_WORDS, PHASE1_WORDS)
    asm.label("P1_DONE")
    asm.nop()

    # ---- PHASE 2: interrupt driven ---------------------------------------------------------
    asm.emit(SW(0, 2, TRNG_OFF_CTRL))                              # disable
    _emit_li(asm, 5, SEED2)
    asm.emit(SW(5, 2, TRNG_OFF_SEED))
    asm.emit(ADDI(5, 0, CTRL_EN | CTRL_IE | (THRESHOLD << 2)))
    asm.emit(SW(5, 2, TRNG_OFF_CTRL))                              # enable edge + IE, one write
    asm.label("P2_ENABLED")
    asm.nop()

    # Wait (bounded) for the one trap.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.emit(ADDI(18, 0, 1))
    asm.label("TRAP_WAIT")
    asm.emit(LW(16, 4, RES_ISR_COUNT * 4))
    asm.thunk(lambda lbl, pc: BLT(16, 18, lbl["TRAP_WAIT_NEXT"] - pc))   # count < 1: keep waiting
    asm.thunk(lambda lbl, pc: JAL(0, lbl["TRAP_DONE"] - pc))
    asm.label("TRAP_WAIT_NEXT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["TRAP_WAIT"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))          # IRQ never arrived

    asm.label("TRAP_DONE")
    _emit_pop_loop(asm, "P2", RES_P2_WORDS, PHASE2_WORDS)

    # Settle: a spurious second trap (stale level-held IRQ, or IE not really cleared) lands here.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 600))
    asm.label("SETTLE")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["SETTLE"] - pc))

    # Teeth: exactly one trap, and the ISR saw data ready + INSECURE.
    asm.emit(LW(17, 4, RES_ISR_COUNT * 4))
    asm.emit(ADDI(18, 0, 1))
    _fail_if_ne(asm, 17, 18)
    asm.emit(LW(17, 4, RES_ISR_STATUS * 4))
    asm.emit(ANDI(17, 17, 0x9))
    asm.emit(ADDI(18, 0, 0x9))
    _fail_if_ne(asm, 17, 18)

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


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm = Assembler(origin=ROM_BASE)
    build_firmware(asm)
    words = asm.resolve()
    labels = asm.labels
    assert len(words) <= ROM_WORDS, f"firmware too large: {len(words)} words > {ROM_WORDS}"
    for req in ('ISR', 'MAIN', 'FAIL', 'PASS', 'IRQ_READY', 'P1_ENABLED', 'P1_DONE',
                'P2_ENABLED'):
        assert req in labels, f"label {req!r} not found in {list(labels)}"
    padded = list(words) + [NOP] * (ROM_WORDS - len(words))
    hex_path = os.path.join(out_dir, 'trng_fw.hex')
    with open(hex_path, 'w') as f:
        for w in padded:
            f.write(f'{w:08x}\n')
    print(f"Wrote {len(padded)} words to {hex_path} ({len(words)} used)")

    addrs_path = os.path.join(out_dir, 'trng_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_trng_hex.py — do not edit.\n")
        f.write(f"PASS_PC        = 0x{labels['PASS']:08x}\n")
        f.write(f"FAIL_PC        = 0x{labels['FAIL']:08x}\n")
        f.write(f"ISR_PC         = 0x{labels['ISR']:08x}\n")
        f.write(f"IRQ_READY_PC   = 0x{labels['IRQ_READY']:08x}\n")
        f.write(f"P1_ENABLED_PC  = 0x{labels['P1_ENABLED']:08x}\n")
        f.write(f"P1_DONE_PC     = 0x{labels['P1_DONE']:08x}\n")
        f.write(f"P2_ENABLED_PC  = 0x{labels['P2_ENABLED']:08x}\n")
        f.write(f"SEED_RESET_VAL = 0x{SEED_RESET_VAL:08x}\n")
        f.write(f"SEED1          = 0x{SEED1:08x}\n")
        f.write(f"SEED2          = 0x{SEED2:08x}\n")
        f.write(f"PHASE1_WORDS   = {PHASE1_WORDS}\n")
        f.write(f"PHASE2_WORDS   = {PHASE2_WORDS}\n")
        f.write(f"THRESHOLD      = {THRESHOLD}\n")
        f.write(f"RES_BASE_WI    = {RES_BASE_WI}\n")
        f.write(f"RES_ISR_COUNT  = {RES_ISR_COUNT}\n")
        f.write(f"RES_ISR_STATUS = {RES_ISR_STATUS}\n")
        f.write(f"RES_STATUS_PRE = {RES_STATUS_PRE}\n")
        f.write(f"RES_EMPTY_READ = {RES_EMPTY_READ}\n")
        f.write(f"RES_SEED_RESET = {RES_SEED_RESET}\n")
        f.write(f"RES_SEED_READBACK = {RES_SEED_READBACK}\n")
        f.write(f"RES_STATUS_FULL = {RES_STATUS_FULL}\n")
        f.write(f"RES_P1_WORDS   = {RES_P1_WORDS}\n")
        f.write(f"RES_P2_WORDS   = {RES_P2_WORDS}\n")
    print(f"Wrote {addrs_path}")


if __name__ == '__main__':
    main()
