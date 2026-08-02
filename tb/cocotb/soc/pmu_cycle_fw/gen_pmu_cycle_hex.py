#!/usr/bin/env python3
"""
gen_pmu_cycle_hex.py — generate pmu_cycle.hex for the GH #95 (Group C)
PMU-driven live CPU-domain power-cycle test (test_soc_pmu_multiclock.py).

Firmware runs from ROM @ 0x0000_1000 (RESET_PC, same as every other _fw in
this directory).

Purpose: this firmware is the CPU-side half of a real, hardware-routed
power-down trigger. The CPU cannot power itself back up once its own clock
is gated by the PMU (rtl/soc/pmu.sv), so this firmware only ever programs
the power-DOWN transition; test_soc_pmu_multiclock.py supplies the
power-UP trigger externally (see that file's module docstring for why, and
why that is a legitimate scope split rather than a shortcut).

Mechanism: CPU cannot write PMU CTRL (0x2000_8000) directly and reliably
survive doing so from software (the write may land on the same cycle the
CPU's own clock is about to be gated, and in general "does software surve
writing its own power-off register" is not the property under test here).
Instead, the CPU programs the DMA engine (a fabric-domain, core_clk-driven
AXI4 master, unaffected by the CPU's own domain state) to perform the
write on its behalf:
  1. Store MODE_CPU_OFF (0x1) to SRAM word 0 (byte 0x2000).
  2. D-cache flush (CSRW 0x7C0) + spin-wait, so the DMA's SRAM read (which
     bypasses the D-cache) sees the just-written value (same pattern as
     periph_fw/gen_periph_hex.py's DMA setup).
  3. Program DMA: SRC=0x0000_2000 (SRAM word 0), DST=0x2000_8000 (PMU
     CTRL), LEN=4 bytes; pulse CTRL.start.
  4. Fall into an infinite busy-loop incrementing a free-running counter
     at SRAM word 1 (byte 0x2004). This is deliberately NOT a
     poll-then-EBREAK pattern: the whole point of this test is that the
     CPU domain's own clock is gated out from under this loop mid-flight,
     with no drain/quiesce step (a documented, pre-existing, non-blocking
     gap — see soc_top.sv's PMU integration comments and
     design_state.json's gh93_cdc_verification.residual_gaps). The
     testbench (not this firmware) observes the counter continuing to
     climb after the PMU sequences the CPU domain back to DOM_ON, proving
     architectural state (PC + registers) survived the clock-gate-only
     power cycle intact and the loop resumed exactly where it left off.

No PASS/FAIL branch, no EBREAK: this firmware never terminates by design.
test_soc_pmu_multiclock.py owns all pass/fail assertions via backdoor
observation (PMU sequencer state, SRAM counter progression).
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    ADDI, SW, LW, BNE, JAL,
)


def CSRRW(rd: int, csr: int, rs1: int) -> int:
    """CSRRW rd, csr, rs1 — atomic CSR read-write.
    CSRW csr, rs1 is the pseudo-instruction alias (rd=x0)."""
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73


ROM_BASE  = 0x0000_1000
ROM_WORDS = 1024
NOP       = 0x00000013   # ADDI x0, x0, 0

SRAM_BASE = 0x0000_2000
DMA_BASE  = 0x2000_5000
PMU_BASE  = 0x2000_8000

# SRAM word offsets (bytes from SRAM_BASE)
CTRLVAL_BYTE_OFFSET = 0x00   # word 0: MODE_CPU_OFF value the DMA will copy
COUNTER_BYTE_OFFSET = 0x04   # word 1: free-running busy-loop counter

MODE_CPU_OFF = 0x1

# Testbench-facing constants (mirrored in test_soc_pmu_multiclock.py; kept
# here too so a firmware-only reader has the full picture without
# cross-referencing the test file).
CTRLVAL_WORD_IDX = CTRLVAL_BYTE_OFFSET // 4
COUNTER_WORD_IDX = COUNTER_BYTE_OFFSET // 4


# ---------------------------------------------------------------------------
# LUI+ADDI materialiser with bit-11 sign-extension compensation (ported
# verbatim from periph_fw/gen_periph_hex.py / boot_fw/gen_boot_hex.py).
# ---------------------------------------------------------------------------
def lui_addi(rd: int, value32: int):
    from sim.riscv_encoder import LUI
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}): "
        f"upper=0x{upper20:05x} lower_signed={lower_signed} -> 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


# ---------------------------------------------------------------------------
# Minimal two-pass label assembler (ported verbatim from gen_periph_hex.py).
# ---------------------------------------------------------------------------
class Assembler:
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


# ---------------------------------------------------------------------------
# Firmware builder
# ---------------------------------------------------------------------------
def build_firmware(asm: Assembler):
    # x2 = SRAM_BASE (0x0000_2000) — also equals the byte address of the
    # CTRLVAL word (offset 0), so x2 doubles as the DMA SRC value directly.
    l2, a2 = lui_addi(2, SRAM_BASE)
    asm.emit(l2)
    asm.emit(a2)

    # x5 = DMA_BASE (0x2000_5000)
    l5, a5 = lui_addi(5, DMA_BASE)
    asm.emit(l5)
    asm.emit(a5)

    # ── Step 1: store MODE_CPU_OFF to SRAM[CTRLVAL] ──────────────────────────
    asm.emit(ADDI(8, 0, MODE_CPU_OFF))
    asm.emit(SW(8, 2, CTRLVAL_BYTE_OFFSET))

    # ── Step 1b: init busy-loop counter to 0 ─────────────────────────────────
    asm.emit(SW(0, 2, COUNTER_BYTE_OFFSET))

    # ── Step 1c: D-cache flush + spin-wait (same pattern as periph_fw) ──────
    asm.emit(CSRRW(0, 0x7C0, 0))   # dcache_flush
    asm.emit(ADDI(16, 0, 0))       # x16 = 0 (counter)
    l17, a17 = lui_addi(17, 1024)  # x17 = 1024 (spin limit)
    asm.emit(l17)
    asm.emit(a17)
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH_WAIT"] - pc))

    # ── Step 2: program DMA to write MODE_CPU_OFF into PMU CTRL ─────────────
    asm.emit(SW(2, 5, 0))     # DMA SRC = x2 = 0x0000_2000

    l8, a8 = lui_addi(8, PMU_BASE)
    asm.emit(l8)
    asm.emit(a8)
    asm.emit(SW(8, 5, 4))     # DMA DST = 0x2000_8000 (PMU CTRL)

    asm.emit(ADDI(8, 0, 4))
    asm.emit(SW(8, 5, 8))     # DMA LEN = 4 bytes

    asm.emit(ADDI(8, 0, 1))
    asm.emit(SW(8, 5, 12))    # DMA CTRL = 1 (start pulse)
    asm.emit(SW(0, 5, 12))    # DMA CTRL = 0 (deassert)

    # ── Step 3: free-running busy loop — deliberately never terminates.
    # The CPU domain's clock is gated out from under this loop by the PMU
    # once the DMA write above lands; the loop resumes on the exact next
    # instruction once the PMU sequences the CPU domain back to DOM_ON.
    #
    # bead claude_verilog_test-2k8 fix note: the loop body includes a
    # per-iteration CSRW dcache_flush (0x7C0). SRAM_BASE is below MMIO_BASE
    # (rv32i_dcache.sv's cacheable-address check), so without an explicit
    # flush the counter store only dirties the write-back D-cache's line —
    # it never reaches real SRAM, and the testbench observes the counter
    # via a BACKDOOR read of u_soc.u_sram.mem (bypassing the D-cache
    # entirely), which would then never see the increment regardless of
    # whether the CPU is actually executing correctly. This is the same
    # flush-before-external-observation pattern Step 1c above already uses
    # (D-cache flush before the DMA's own SRAM read) and that
    # docs/M9's "SW coherency (D$ flush->GPU->D$ inval)" convention
    # establishes elsewhere in this repo. dc_stall_o is asserted for the
    # full duration of CS_FLUSH_SCAN (rv32i_dcache.sv), so the pipeline
    # naturally blocks the following JAL until the flush (and any
    # resulting single-line writeback) completes — no software spin-wait
    # is needed here, unlike Step 1c's cross-domain DMA-visibility case.
    asm.label("LOOP")
    asm.emit(LW(9, 2, COUNTER_BYTE_OFFSET))
    asm.emit(ADDI(9, 9, 1))
    asm.emit(SW(9, 2, COUNTER_BYTE_OFFSET))
    asm.emit(CSRRW(0, 0x7C0, 0))   # dcache_flush -- make the store SRAM-visible
    asm.thunk(lambda lbl, pc: JAL(0, lbl["LOOP"] - pc))


def print_listing(words: list, labels: dict) -> None:
    pc_to_label = {v: k for k, v in labels.items()}
    print("\n=== PMU Cycle Firmware Listing ===")
    print(f"{'PC':>10}  {'Word':>10}  Annotation")
    print("-" * 60)
    for i, w in enumerate(words):
        if w == NOP and i >= 40:
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

    for req in ('FLUSH_WAIT', 'LOOP'):
        assert req in labels, f"Label {req!r} not found; got {list(labels)}"

    loop_pc = labels['LOOP']
    print(f"LOOP_PC = 0x{loop_pc:08x}  (word {(loop_pc - ROM_BASE)//4})")

    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} > ROM_WORDS={ROM_WORDS}"
    )

    padded = list(words)
    padded.extend([NOP] * (ROM_WORDS - len(padded)))

    hex_path = os.path.join(out_dir, 'pmu_cycle.hex')
    os.makedirs(out_dir, exist_ok=True)
    with open(hex_path, 'w') as f:
        for w in padded:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded)} words to {hex_path}")

    addrs_path = os.path.join(out_dir, 'pmu_cycle_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_pmu_cycle_hex.py — do not edit.\n")
        f.write(f"LOOP_PC              = 0x{loop_pc:08x}\n")
        f.write(f"CTRLVAL_WORD_IDX     = {CTRLVAL_WORD_IDX}\n")
        f.write(f"COUNTER_WORD_IDX     = {COUNTER_WORD_IDX}\n")
        f.write(f"MODE_CPU_OFF         = 0x{MODE_CPU_OFF:x}\n")
    print(f"Wrote {addrs_path}")
