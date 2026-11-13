#!/usr/bin/env python3
"""
gen_pll2_decode_hex.py -- generate pll2_decode.hex for the SoC-level PLL2 APB slot decode test
(test_pll_lock.py test_pll2_apb_slot_decode and test_soc_multiclock_pll2.py, DUT tb_soc_pll).
Why CPU firmware and not a cocotb APB/AXI-Lite BFM against soc_top: driving the
SoC-internal AXI-Lite ring from a cocotb BFM hangs under Verilator (test_pll_regs.py documents it).
RTL drives those nets continuously, so a cocotb write is overridden by the next RTL eval. The same
holds for the APB nets from axil_to_apb. A real MMIO access needs the CPU to issue it, as
test_periph_loopback.py does.
Firmware runs from ROM at 0x0000_1000 and is self-checking (PASS_PC / FAIL_PC, scored
  by commit_pc_o):
  1. PLL (APB_PLL=4, 0x2000_7000) CONTROL[0] == 1 (pll_enable, non-clearable).
  2. PLL STATUS[0] == 1 (locked: the system PLL locks out of reset).
  3. PMU (APB_PMU=5, 0x2000_8000) STATUS == 0x3 (cpu_domain_on, gpu_domain_on, not busy). This is a
     tripwire in case a later edit reorders the map. PLL2 sits after the PMU, so its decode is safe.
  4. PLL2 (APB_PLL2=6, 0x2000_9000) CONTROL == 0x0000_0001: the slot returns the
     pll_apb_regs RESET_VAL.
     The crossbar returns DECERR data with no CPU trap, so a wrong slave shows as a data mismatch.
  5. PLL2 STATUS[0] == 1 (cpu_pll_locked_o mirrors pll_locked_o in the tied-clock
     tb_soc_pll config).
  6. Anti-brick: write CONTROL = 0 to PLL2. It must read back 0x1: WMASK bit 0 pins pll_enable, and
     the write does land on bits [9:4].
  7. PLL2 STATUS[0] is still 1 after that write.
Doc: tm:suite:soc-pll2-fw-gen-pll2-decode-hex
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import LUI, ADDI, SW, LW, ANDI, BNE, JAL, EBREAK

ROM_BASE  = 0x0000_1000
ROM_WORDS = 1024
NOP       = 0x00000013   # ADDI x0, x0, 0


def lui_addi(rd: int, value32: int):
    """rd = value32 via LUI+ADDI, bit-11 sign-extension compensated.

    All three base addresses used by this firmware (0x2000_7000,
    0x2000_8000, 0x2000_9000) have lower12 == 0, so this always degenerates
    to a plain LUI with an ADDI x0,x0,0 NOP placeholder — kept general for
    consistency with gen_periph_hex.py's proven helper.
    """
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}) mismatch: 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


class Assembler:
    """Minimal two-pass label resolver (same pattern as gen_periph_hex.py)."""
    def __init__(self):
        self._items = []
        self.labels = {}

    def emit(self, word: int):
        self._items.append(('word', word & 0xFFFF_FFFF))

    def label(self, name: str):
        self._items.append(('label', name))

    def thunk(self, fn):
        self._items.append(('thunk', fn))

    def resolve(self):
        self.labels = {}
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                self.labels[val] = ROM_BASE + idx * 4
            else:
                idx += 1

        words = []
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                continue
            cur_pc = ROM_BASE + idx * 4
            if typ == 'thunk':
                w = val(self.labels, cur_pc) & 0xFFFF_FFFF
            else:
                w = val
            words.append(w)
            idx += 1
        return words


def _check_bit0_eq(asm, base_reg, offset, expect, fail_label="FAIL"):
    """LW scratch = mem[base_reg+offset]; scratch &= 1; branch FAIL if != expect."""
    asm.emit(LW(8, base_reg, offset))
    asm.emit(ANDI(8, 8, 1))
    asm.emit(ADDI(9, 0, expect))
    asm.thunk(lambda lbl, pc, fl=fail_label: BNE(8, 9, lbl[fl] - pc))


def _check_word_eq(asm, base_reg, offset, expect, fail_label="FAIL"):
    """LW scratch = mem[base_reg+offset]; branch FAIL if scratch != expect."""
    asm.emit(LW(8, base_reg, offset))
    asm.emit(ADDI(9, 0, expect))
    asm.thunk(lambda lbl, pc, fl=fail_label: BNE(8, 9, lbl[fl] - pc))


def build_firmware(asm: Assembler):
    # ── Base register materialisation ────────────────────────────────────────
    l2, a2 = lui_addi(2, 0x2000_7000)   # PLL  base
    asm.emit(l2); asm.emit(a2)
    l3, a3 = lui_addi(3, 0x2000_8000)   # PMU  base
    asm.emit(l3); asm.emit(a3)
    l4, a4 = lui_addi(4, 0x2000_9000)   # PLL2 base
    asm.emit(l4); asm.emit(a4)

    # ── 1. PLL CONTROL[0] == 1 (existing instance untouched) ──────
    _check_bit0_eq(asm, 2, 0x000, 1)

    # ── 2. PLL STATUS[0] == 1 (system PLL locked — SoC already booted) ──────
    _check_bit0_eq(asm, 2, 0x004, 1)

    # ── 3. PMU STATUS == 0x3 (slot did not move) ─────────────────────────────
    _check_word_eq(asm, 3, 0x004, 0x3)

    # ── 4. PLL2 CONTROL == 0x0000_0001 exactly (new slot decodes, RESET_VAL) ─
    _check_word_eq(asm, 4, 0x000, 0x1)

    # ── 5. PLL2 STATUS[0] == 1 (second stub PLL locked) ──────────────────────
    _check_bit0_eq(asm, 4, 0x004, 1)

    # ── 6. Anti-brick: write 0 to PLL2 CONTROL; readback must stay 0x1 ───────
    asm.emit(SW(0, 4, 0x000))            # CONTROL = 0 (x0)
    _check_word_eq(asm, 4, 0x000, 0x1)

    # ── 7. PLL2 STATUS[0] still == 1 after the CONTROL write ────────────────
    _check_bit0_eq(asm, 4, 0x004, 1)

    # ── Success path ──────────────────────────────────────────────────────────
    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    # ── FAIL ──────────────────────────────────────────────────────────────────
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


def print_listing(words, labels):
    pc_to_label = {v: k for k, v in labels.items()}
    print("\n=== PLL2 Decode Firmware Listing ===")
    print(f"{'PC':>10}  {'Word':>10}  Annotation")
    print("-" * 60)
    for i, w in enumerate(words):
        if w == NOP and i >= 60:
            break
        pc = ROM_BASE + i * 4
        lbl = f"<{pc_to_label[pc]}>" if pc in pc_to_label else ""
        print(f"0x{pc:08x}  0x{w:08x}  {lbl}")
    print()


if __name__ == '__main__':
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm = Assembler()
    build_firmware(asm)
    words = asm.resolve()
    labels = asm.labels

    print_listing(words, labels)

    for req in ('FAIL', 'PASS'):
        assert req in labels, f"Label {req!r} not found; got {list(labels)}"

    pass_pc = labels['PASS']
    fail_pc = labels['FAIL']
    print(f"PASS_PC = 0x{pass_pc:08x}  (word {(pass_pc - ROM_BASE)//4})")
    print(f"FAIL_PC = 0x{fail_pc:08x}  (word {(fail_pc - ROM_BASE)//4})")

    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} > ROM_WORDS={ROM_WORDS}"
    )

    padded = list(words)
    padded.extend([NOP] * (ROM_WORDS - len(padded)))

    hex_path = os.path.join(out_dir, 'pll2_decode.hex')
    os.makedirs(out_dir, exist_ok=True)
    with open(hex_path, 'w') as f:
        for w in padded:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded)} words to {hex_path}")

    addrs_path = os.path.join(out_dir, 'pll2_decode_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_pll2_decode_hex.py — do not edit.\n")
        f.write(f"PASS_PC = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC = 0x{fail_pc:08x}\n")
    print(f"Wrote {addrs_path}")
    print(f"  PASS_PC = 0x{pass_pc:08x}")
    print(f"  FAIL_PC = 0x{fail_pc:08x}")
