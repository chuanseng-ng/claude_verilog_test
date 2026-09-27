#!/usr/bin/env python3
"""
gen_gpio_hex.py — generate gpio_fw.hex for the Phase 6a SoC-level GPIO test
(bead claude_verilog_test-8qn4 item 1).

Unlike periph_fw / cpu_gpu_irq_fw, this firmware is NOT fully self-checking in
isolation: two of its three phases require the cocotb testbench to observe or
drive the tb_soc_top boundary ports (gpio_out_o/gpio_oe_o, gpio_in_i) at the
right moment. Synchronisation between firmware progress and the cocotb driver
is done the same way test_periph_loopback / test_cpu_gpu_irq already do it —
via commit_pc_o scoreboarding — except here cocotb watches three additional
marker PCs (OUTPUT_DONE, INPUT_READY, IRQ_READY), not just PASS_PC/FAIL_PC.

Path exercised (confirmed from soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_GPIO slave 7 (gpio_controller, base 0x2000_A000)

GPIO register map (rtl/periph/gpio_controller.sv, word indices):
  +0x00 GPIO_DATA_IN   RO
  +0x04 GPIO_DATA_OUT  RW
  +0x08 GPIO_DIR       RW   (1 = output)
  +0x0C GPIO_IRQ_EN    RW
  +0x10 GPIO_IRQ_TYPE  RW   (0 = level, 1 = edge)
  +0x14 GPIO_IRQ_POL   RW   (0 = low/falling, 1 = high/rising)
  +0x18 GPIO_IRQ_STAT  RO   (sticky in edge mode, live in level mode)
  +0x1C GPIO_IRQ_CLR   WO   (always reads 0)
  +0x20 first out-of-range word (N_REGS=8) — read must return 0

Three test phases, each gated by a distinct marker PC the cocotb test
watches via commit_pc_o:

  Phase 1 (OUTPUT): firmware writes GPIO_DIR=TEST_DIR_VAL and
    GPIO_DATA_OUT=TEST_DATA_VAL, then commits OUTPUT_DONE_PC. cocotb samples
    gpio_oe_o/gpio_out_o at that point and asserts they equal the written
    values — proving the write reached slave 7 through the whole fabric.

  Phase 2 (INPUT): firmware commits INPUT_READY_PC just before entering a
    bounded poll loop reading GPIO_DATA_IN. cocotb, on seeing that PC, drives
    gpio_in_i = INPUT_MASK (bits INPUT_PIN_A/INPUT_PIN_B). The poll loop
    naturally tolerates the pin's 3-clock-edge synchroniser latency (2-stage
    cdc_2ff_sync + 1 register-bank cycle) because each iteration costs several
    cycles and the loop simply retries until it observes the new value or
    times out (a real synchronisation bug would show as a poll-limit FAIL).

  Phase 3 (INTERRUPT, end to end): firmware configures pin IRQ_PIN_IDX for a
    rising-edge interrupt, clears any stale sticky status, unmasks it in
    GPIO_IRQ_EN, unmasks bit 5 (GPIO) in interrupt_controller's IRQ_MASK
    (base 0x2000_6000), enables MEIE/MIE, then commits IRQ_READY_PC and enters
    a bounded WFI-style poll loop on an ISR_FLAG word in SRAM. cocotb, on
    seeing IRQ_READY_PC, raises gpio_in_i bit IRQ_PIN_IDX (0->1). The ISR
    (installed at mtvec = ISR_PC) clears GPIO_IRQ_CLR for that pin, increments
    an ISR_COUNT word, sets ISR_FLAG, and MRETs. Firmware then teeth-checks:
    ISR_COUNT == 1 exactly (no spurious re-trigger after MRET re-enables MIE —
    this is the firmware-side proof that the interrupt actually deasserted,
    since a stuck-asserted level would immediately re-vector) and
    GPIO_IRQ_STAT bit IRQ_PIN_IDX == 0 (edge-sticky bit cleared). The cocotb
    test independently watches commit_pc_o for ISR_PC (proof the CPU actually
    took the trap, not merely that a status bit got set) and directly samples
    the internal gpio_irq / ext_irq nets before and after the ISR runs (proof
    of deassertion at the RTL level, not just firmware self-report).

  Phase 4 (register-bank policy, cheap teeth checks): GPIO_IRQ_CLR always
  reads 0; a read at word index 8 (first out-of-range offset, +0x20) returns
  0 (apb4_register_bank's documented drop/return-0 OOR policy).

All peripheral base addresses used here (GPIO_BASE, IRQ_CTRL_BASE) have
bits[11:0]=0, so no LUI sign-extension compensation is needed for them (see
periph_fw/gen_periph_hex.py's header) — lui_addi() handles the general case
regardless.

Register allocation (MAIN):
  x1  = scratch (LUI/ADDI temporaries, CSR value staging)
  x2  = GPIO_BASE       0x2000_A000
  x3  = IRQ_CTRL_BASE   0x2000_6000
  x4  = ISR_FLAG_ADDR   (SRAM, word ISR_FLAG_WI)
  x5  = scratch (write patterns)
  x6  = INPUT_MASK      (bits INPUT_PIN_A | INPUT_PIN_B)
  x7  = poll counter (input phase)
  x8  = poll limit (input phase)
  x9  = scratch (GPIO_DATA_IN readback)
  x10 = scratch (masked readback)
  x11 = IRQ_PIN bit mask (1 << IRQ_PIN_IDX) — held live across phase 3
  x12 = scratch (register read-modify-write staging)
  x13 = scratch (IRQ_MASK bit-5 value / small constants)
  x14 = poll counter (WFI loop)
  x15 = poll limit (WFI loop)
  x16 = scratch (ISR_FLAG readback)
  x17 = scratch (ISR_COUNT readback / expected constant)
  x18 = scratch (expected constant for ISR_COUNT compare)
  x19 = scratch (GPIO_IRQ_STAT readback / masked)
  x20 = scratch (GPIO_IRQ_CLR readback)
  x21 = scratch (out-of-range readback)
  x31 = result marker (1 = pass, -1 = fail)

Register allocation (ISR, at ISR_PC = ROM_BASE + 4):
  x28 = GPIO_BASE (reconstructed independently of MAIN's x2 — ISR runs with
        MIE cleared, but MAIN's registers are still architecturally live;
        rebuilding is defensive, matching cpu_gpu_irq_fw's convention)
  x29 = IRQ_PIN bit mask (rebuilt in the ISR — see below)
  x30 = SRAM ISR_FLAG_ADDR (rebuilt in the ISR)
  x31 = scratch (constant 1 / ISR_COUNT staging)
  x1  = scratch (ISR_COUNT readback)
  Only x1, x28-x31 are touched by the ISR; MAIN uses x1-x21 before entering
  the WFI loop and does not rely on any of those values surviving a trap, so
  this is safe scratch (same reasoning as cpu_gpu_irq_fw's ISR register note).
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, SW, LW, BNE, BEQ, JAL, EBREAK, SLLI, AND, OR,
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
# See cpu_gpu_irq_fw/gen_cpu_gpu_irq_hex.py's header for why the trampoline
# is required (RESET_PC = ROM_BASE would otherwise execute the ISR as
# ordinary startup code).
ISR_OFFSET_WORDS = 1
MAIN_START_WORDS = 20   # ISR measures ~13 words; padded generously.

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------
GPIO_BASE          = 0x2000_A000
GPIO_OFF_DATA_IN   = 0x00
GPIO_OFF_DATA_OUT  = 0x04
GPIO_OFF_DIR       = 0x08
GPIO_OFF_IRQ_EN    = 0x0C
GPIO_OFF_IRQ_TYPE  = 0x10
GPIO_OFF_IRQ_POL   = 0x14
GPIO_OFF_IRQ_STAT  = 0x18
GPIO_OFF_IRQ_CLR   = 0x1C
GPIO_OFF_OOR       = 0x20   # word index 8 — first out-of-range offset (N_REGS=8)

IRQ_CTRL_BASE      = 0x2000_6000
IRQ_OFF_STATUS     = 0x000
IRQ_OFF_MASK       = 0x004
IRQ_OFF_PENDING    = 0x008
GPIO_IRQ_MASK_BIT  = 0x20   # interrupt_controller.irq_src_i[5] = GPIO slot

SRAM_BASE          = 0x0000_2000
ISR_FLAG_WI        = 300   # SRAM word 300 = byte 0x0000_24B0
ISR_COUNT_WI       = 301   # SRAM word 301 = byte 0x0000_24B4
ISR_FLAG_ADDR      = SRAM_BASE + ISR_FLAG_WI * 4

# ---------------------------------------------------------------------------
# Test-pattern constants (all fit as small positive 12-bit ADDI immediates,
# so no lui_addi() is needed for any of them)
# ---------------------------------------------------------------------------
TEST_DIR_VAL   = 0x00FF   # pins 0-7 = outputs; all others remain inputs
TEST_DATA_VAL  = 0x00A5   # drive pattern 1010_0101 on pins 0-7

INPUT_PIN_A    = 8
INPUT_PIN_B    = 12
INPUT_MASK     = (1 << INPUT_PIN_A) | (1 << INPUT_PIN_B)   # 0x1100

IRQ_PIN_IDX    = 20   # distinct from the output pins (0-7) and input pins (8, 12)

INPUT_POLL_LIMIT = 64     # generous vs. the 3-clock-edge sync latency
WFI_POLL_LIMIT    = 2000  # mirrors cpu_gpu_irq_fw's POLL_LIMIT


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


# ---------------------------------------------------------------------------
# Firmware
# ---------------------------------------------------------------------------
def build_firmware(asm: Assembler) -> None:
    # =========================================================================
    # WORD 0 (0x1000): reset-vector trampoline
    # =========================================================================
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # =========================================================================
    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    # =========================================================================
    asm.label("ISR")

    l28, a28 = lui_addi(28, GPIO_BASE)
    asm.emit(l28); asm.emit(a28)

    # x29 = 1 << IRQ_PIN_IDX
    asm.emit(ADDI(29, 0, 1))
    asm.emit(SLLI(29, 29, IRQ_PIN_IDX))

    # Clear the edge-sticky status bit for IRQ_PIN_IDX
    asm.emit(SW(29, 28, GPIO_OFF_IRQ_CLR))

    l30, a30 = lui_addi(30, ISR_FLAG_ADDR)
    asm.emit(l30); asm.emit(a30)

    # ISR_FLAG = 1
    asm.emit(ADDI(31, 0, 1))
    asm.emit(SW(31, 30, 0))

    # ISR_COUNT += 1  (word at ISR_FLAG_ADDR + 4)
    asm.emit(LW(1, 30, 4))
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, 4))

    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # =========================================================================
    # MAIN FIRMWARE
    # =========================================================================
    asm.label("MAIN")

    l2, a2 = lui_addi(2, GPIO_BASE)
    asm.emit(l2); asm.emit(a2)

    l3, a3 = lui_addi(3, IRQ_CTRL_BASE)
    asm.emit(l3); asm.emit(a3)

    l4, a4 = lui_addi(4, ISR_FLAG_ADDR)
    asm.emit(l4); asm.emit(a4)

    # ── MTVEC: point at the ISR (word 1 = ROM_BASE+4, MODE=0 Direct) ─────────
    ISR_PC_VAL = ROM_BASE + ISR_OFFSET_WORDS * 4
    l1, a1 = lui_addi(1, ISR_PC_VAL)
    asm.emit(l1); asm.emit(a1)
    asm.emit(CSRRW(0, 0x305, 1))   # csrw mtvec, x1

    # Zero ISR_FLAG / ISR_COUNT so the teeth checks below are reliable.
    asm.emit(SW(0, 4, 0))
    asm.emit(SW(0, 4, 4))

    # =========================================================================
    # PHASE 1 — OUTPUT PATH
    # =========================================================================
    asm.emit(ADDI(5, 0, TEST_DIR_VAL))
    asm.emit(SW(5, 2, GPIO_OFF_DIR))
    asm.emit(ADDI(5, 0, TEST_DATA_VAL))
    asm.emit(SW(5, 2, GPIO_OFF_DATA_OUT))

    asm.label("OUTPUT_DONE")
    asm.nop()

    # =========================================================================
    # PHASE 2 — INPUT PATH (respects the 3-clock-edge sync latency by
    # retrying in a bounded loop rather than asserting on the first read)
    # =========================================================================
    l6, a6 = lui_addi(6, INPUT_MASK)
    asm.emit(l6); asm.emit(a6)
    asm.emit(ADDI(7, 0, 0))                 # poll counter = 0
    asm.emit(ADDI(8, 0, INPUT_POLL_LIMIT))  # poll limit

    asm.label("INPUT_READY")
    asm.nop()

    asm.label("INPUT_POLL")
    asm.emit(LW(9, 2, GPIO_OFF_DATA_IN))
    asm.emit(AND(10, 9, 6))
    asm.thunk(lambda lbl, pc: BEQ(10, 6, lbl["INPUT_MATCHED"] - pc))
    asm.emit(ADDI(7, 7, 1))
    asm.thunk(lambda lbl, pc: BNE(7, 8, lbl["INPUT_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))   # poll-limit timeout

    asm.label("INPUT_MATCHED")

    # =========================================================================
    # PHASE 3 — INTERRUPT PATH, end to end
    # =========================================================================
    # x11 = 1 << IRQ_PIN_IDX (held live through the rest of MAIN)
    asm.emit(ADDI(11, 0, 1))
    asm.emit(SLLI(11, 11, IRQ_PIN_IDX))

    # Configure edge-sensitive, rising-edge (active-high) trigger for IRQ_PIN_IDX
    asm.emit(LW(12, 2, GPIO_OFF_IRQ_TYPE))
    asm.emit(OR(12, 12, 11))
    asm.emit(SW(12, 2, GPIO_OFF_IRQ_TYPE))

    asm.emit(LW(12, 2, GPIO_OFF_IRQ_POL))
    asm.emit(OR(12, 12, 11))
    asm.emit(SW(12, 2, GPIO_OFF_IRQ_POL))

    # Clear any stale status bit carried over from level mode before enabling.
    asm.emit(SW(11, 2, GPIO_OFF_IRQ_CLR))

    # Unmask IRQ_PIN_IDX in GPIO_IRQ_EN
    asm.emit(LW(12, 2, GPIO_OFF_IRQ_EN))
    asm.emit(OR(12, 12, 11))
    asm.emit(SW(12, 2, GPIO_OFF_IRQ_EN))

    # Unmask bit 5 (GPIO) in interrupt_controller's IRQ_MASK
    asm.emit(ADDI(13, 0, GPIO_IRQ_MASK_BIT))
    asm.emit(SW(13, 3, IRQ_OFF_MASK))

    # Enable MEIE (mie bit 11) and MIE (mstatus bit 3)
    l1b, a1b = lui_addi(1, 0x800)
    asm.emit(l1b); asm.emit(a1b)
    asm.emit(CSRRW(0, 0x304, 1))   # csrw mie, x1
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))   # csrw mstatus, x1

    asm.label("IRQ_READY")
    asm.nop()

    # WFI-style bounded poll on ISR_FLAG (x4 = ISR_FLAG_ADDR)
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, WFI_POLL_LIMIT))

    asm.label("WFI_LOOP")
    asm.emit(LW(16, 4, 0))
    asm.thunk(lambda lbl, pc: BNE(16, 0, lbl["ISR_DONE"] - pc))
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["WFI_LOOP"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))   # ISR never fired

    asm.label("ISR_DONE")

    # Teeth check 1: ISR_COUNT must be exactly 1 — a stuck-asserted interrupt
    # (deassertion bug) would immediately re-vector after MRET re-enables MIE,
    # incrementing ISR_COUNT again before firmware gets here.
    asm.emit(LW(17, 4, 4))
    asm.emit(ADDI(18, 0, 1))
    asm.thunk(lambda lbl, pc: BNE(17, 18, lbl["FAIL"] - pc))

    # Teeth check 2: GPIO_IRQ_STAT bit IRQ_PIN_IDX must read 0 (edge-sticky
    # bit cleared by the ISR's GPIO_IRQ_CLR write, no new edge since).
    asm.emit(LW(19, 2, GPIO_OFF_IRQ_STAT))
    asm.emit(AND(19, 19, 11))
    asm.thunk(lambda lbl, pc: BNE(19, 0, lbl["FAIL"] - pc))

    # =========================================================================
    # PHASE 4 — register-bank policy checks
    # =========================================================================
    # GPIO_IRQ_CLR always reads 0 (WMASK=0, no hw_wen path — see gpio_controller.sv)
    asm.emit(LW(20, 2, GPIO_OFF_IRQ_CLR))
    asm.thunk(lambda lbl, pc: BNE(20, 0, lbl["FAIL"] - pc))

    # First out-of-range word (index 8, N_REGS=8) reads 0 per
    # apb4_register_bank.sv's documented OOR policy.
    asm.emit(LW(21, 2, GPIO_OFF_OOR))
    asm.thunk(lambda lbl, pc: BNE(21, 0, lbl["FAIL"] - pc))

    # Flush D-cache: the ISR's SW to ISR_COUNT (SRAM, a cached region) may
    # still be dirty in the D-cache, invisible to cocotb's backdoor SRAM-array
    # read at the end of the test. Same rationale as cpu_gpu_irq_fw's
    # FLUSH1/FLUSH2 — CSRW 0x7C0 (dcache_flush) + bounded spin.
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 2000))
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["FLUSH_WAIT"] - pc))

    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    # ── FAIL ──────────────────────────────────────────────────────────────────
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm = Assembler(origin=ROM_BASE)
    build_firmware(asm)
    words = asm.resolve()
    labels = asm.labels

    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} words > {ROM_WORDS}"
    )

    for req in ('ISR', 'MAIN', 'FAIL', 'PASS', 'OUTPUT_DONE', 'INPUT_READY',
                'INPUT_POLL', 'INPUT_MATCHED', 'IRQ_READY', 'WFI_LOOP', 'ISR_DONE'):
        assert req in labels, f"Label {req!r} not found in: {list(labels)}"

    pass_pc         = labels['PASS']
    fail_pc         = labels['FAIL']
    isr_pc          = labels['ISR']
    main_pc         = labels['MAIN']
    output_done_pc  = labels['OUTPUT_DONE']
    input_ready_pc  = labels['INPUT_READY']
    irq_ready_pc    = labels['IRQ_READY']

    print(f"ISR_PC          = 0x{isr_pc:08x}")
    print(f"MAIN_PC         = 0x{main_pc:08x}")
    print(f"OUTPUT_DONE_PC  = 0x{output_done_pc:08x}")
    print(f"INPUT_READY_PC  = 0x{input_ready_pc:08x}")
    print(f"IRQ_READY_PC    = 0x{irq_ready_pc:08x}")
    print(f"FAIL_PC         = 0x{fail_pc:08x}")
    print(f"PASS_PC         = 0x{pass_pc:08x}")

    padded_fw = list(words) + [NOP] * (ROM_WORDS - len(words))
    fw_path = os.path.join(out_dir, 'gpio_fw.hex')
    with open(fw_path, 'w') as f:
        for w in padded_fw:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded_fw)} words to {fw_path}")

    addrs_path = os.path.join(out_dir, 'gpio_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_gpio_hex.py — do not edit.\n")
        f.write(f"PASS_PC         = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC         = 0x{fail_pc:08x}\n")
        f.write(f"ISR_PC          = 0x{isr_pc:08x}\n")
        f.write(f"OUTPUT_DONE_PC  = 0x{output_done_pc:08x}\n")
        f.write(f"INPUT_READY_PC  = 0x{input_ready_pc:08x}\n")
        f.write(f"IRQ_READY_PC    = 0x{irq_ready_pc:08x}\n")
        f.write(f"TEST_DIR_VAL    = 0x{TEST_DIR_VAL:08x}\n")
        f.write(f"TEST_DATA_VAL   = 0x{TEST_DATA_VAL:08x}\n")
        f.write(f"INPUT_PIN_A     = {INPUT_PIN_A}\n")
        f.write(f"INPUT_PIN_B     = {INPUT_PIN_B}\n")
        f.write(f"INPUT_MASK      = 0x{INPUT_MASK:08x}\n")
        f.write(f"IRQ_PIN_IDX     = {IRQ_PIN_IDX}\n")
        f.write(f"ISR_FLAG_WI     = {ISR_FLAG_WI}\n")
        f.write(f"ISR_COUNT_WI    = {ISR_COUNT_WI}\n")
        f.write(f"WFI_POLL_LIMIT  = {WFI_POLL_LIMIT}\n")
    print(f"Wrote {addrs_path}")


if __name__ == '__main__':
    main()
