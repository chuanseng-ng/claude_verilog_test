#!/usr/bin/env python3
"""
gen_pll2_decode_hex.py — generate pll2_decode.hex for GH #92 SoC-level PLL2
APB slot decode test (test_pll2_decode.py, DUT tb_soc_pll).

Why CPU-firmware based (not a live cocotb APB/AXI-Lite BFM against soc_top):
  test_pll_regs.py's header documents that driving the SoC-internal AXI-Lite
  ring signals from a cocotb BFM hangs under Verilator — those nets are
  continuously driven by RTL (axi4_to_axilite's combinational assigns), so a
  cocotb value-write is overridden by the next RTL eval in the same time
  step.  The same applies to the downstream APB nets driven by axil_to_apb.
  The only crash-proof way to exercise a real SoC-level MMIO access (through
  the actual CPU -> D-cache-bypass -> AXI4 crossbar -> axi4_to_axilite ->
  axi_lite_interconnect -> axil_to_apb -> apb_interconnect path) is to have
  the CPU itself issue the loads/stores, exactly as test_periph_loopback.py
  does for DMA/UART/SPI.

Firmware runs from ROM @ 0x0000_1000 (RESET_PC), self-checking:

  1. PLL   (existing instance, APB_PLL=4, 0x2000_7000) CONTROL[0] == 1
     (pll_enable, reset default / non-clearable per GH #89).
  2. PLL   STATUS[0] == 1 (locked — system PLL locks the SoC out of reset,
     so by the time firmware runs this must already be 1).
  3. PMU   (APB_PMU=5, 0x2000_8000) STATUS == 0x3 (cpu_domain_on=1,
     gpu_domain_on=1, busy=0 — steady-state reset default, no CTRL writes
     issued by this firmware) — spot-check that PMU's slot did not move
     when APB_PLL2 was inserted after it in the map... actually PLL2 sits
     AFTER PMU (index 6 > index 5) so PMU's own decode is unaffected by
     construction, but this is a cheap regression tripwire in case a future
     edit reorders the map.
  4. PLL2  (APB_PLL2=6, 0x2000_9000) CONTROL == 0x0000_0001 exactly — the
     new slot decodes and returns the pll_apb_regs RESET_VAL, not garbage /
     DECERR / another slave's data (the AXI4 crossbar returns DECERR data
     with no CPU trap — see docs; a wrong slave or open bus would show up
     here as a data mismatch, not a hang).
  5. PLL2  STATUS[0] == 1 (locked — cpu_pll_locked_o mirrors pll_locked_o
     in the tied-clock tb_soc_pll config; the second stub lock counter
     starts on the same reset de-assert edge as the first).
  6. Anti-brick (GH #89 fix applies to instance 2 too, same pll_apb_regs
     module): write CONTROL = 0x0000_0000 (attempt to clear pll_enable AND
     the div_n/post_div_sel fields). Read back: must be exactly 0x1 — WMASK
     bit[0]=0 keeps pll_enable pinned at its RESET_VAL, and the write DID
     land on bits [9:4] (now 0, same value they already were) so the
     readback matches CONTROL's true architectural state, not a stuck bus.
  7. PLL2 STATUS[0] still == 1 after the CONTROL write (lock does not
     glitch when the same-module register bank takes a write).

Self-checking: branches to PASS_PC on full success, FAIL_PC on any failure.
Testbench scoreboards commit_pc_o for PASS_PC/FAIL_PC (same pattern as
test_periph_loopback.py / test_boot.py).

Register allocation:
  x2  = PLL  base  0x2000_7000
  x3  = PMU  base  0x2000_8000
  x4  = PLL2 base  0x2000_9000
  x8  = scratch (register value read back)
  x9  = scratch (expected value)
  x31 = result marker (1=pass, -1=fail)
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

    # ── 1. PLL CONTROL[0] == 1 (existing instance untouched by GH #92) ──────
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
