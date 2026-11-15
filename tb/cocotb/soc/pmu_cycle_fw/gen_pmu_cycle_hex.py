#!/usr/bin/env python3
"""
gen_pmu_cycle_hex.py -- generate pmu_cycle.hex for the PMU-driven live CPU-domain power-cycle test
(test_soc_pmu_multiclock.py). Firmware runs from ROM at 0x0000_1000.
The CPU cannot power itself back up once the PMU gates its clock, so the firmware programs only the
power-DOWN. It does not write PMU CTRL (0x2000_8000) itself, because the write could land as its
clock is gated. It programs the DMA engine (a core_clk master) to write MODE_CPU_OFF into CTRL. The
testbench gives the power-UP trigger. The firmware follows two PMU rules of the book: stop the bus
traffic before the request (DS-PMU-182), and clear STATUS[3] by a write to STATUS_CLR (DS-PMU-187).
Steps:
  1. Store MODE_CPU_OFF to SRAM word 0 and clear the result words 1 to 3.
  2. D-cache flush and a spin-wait, so the DMA's SRAM read (it bypasses the D-cache) sees word 0.
     The flush ends before the request. After it, no cache line is dirty.
  3. Program the DMA: SRC=0x2000, DST=PMU CTRL, LEN=4. Store 1 to DMA CTRL.start: the last bus
     access before the request. The hardware clears the bit. The store and the wait loop are in one
     16-byte instruction cache line, so the loop makes no fetch.
  4. Wait loop of register instructions: x9 counts to LOOP_LIMIT. The PMU gates the CPU clock out
     from under the loop, and the loop resumes on the next instruction after the power-up.
  5. Read STATUS. If bit 3 is 1, store 1 to SRAM word 1 and write 1 to STATUS_CLR.
  6. Read STATUS again and store it to word 3. Store 1 to word 2 and flush. The result words are in
     one cache line. Then spin in a jump to itself: no PASS/FAIL branch and no EBREAK.
test_soc_pmu_multiclock.py owns every pass and fail check, by backdoor observation.
Doc: tm:suite:soc-pmu-cycle-fw-gen-pmu-cycle-hex
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    ADDI, ANDI, SW, LW, BEQ, BNE, JAL,
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

# SRAM words (bytes from SRAM_BASE). All four are in one 16-byte cache line.
CTRLVAL_BYTE_OFFSET = 0x00   # word 0: MODE_CPU_OFF value the DMA will copy
FAULT_BYTE_OFFSET   = 0x04   # word 1: 1 if STATUS[3] read 1 after the power cycle, else 0
DONE_BYTE_OFFSET    = 0x08   # word 2: 1 when the firmware has finished
STATUS_BYTE_OFFSET  = 0x0C   # word 3: STATUS as read after the clear

PMU_STATUS_OFFSET     = 0x04
PMU_STATUS_CLR_OFFSET = 0x0C
STATUS_TIMEOUT_BIT    = 0x8   # STATUS[3], sticky

MODE_CPU_OFF = 0x1

LOOP_REG   = 9      # register that counts the wait loop
LOOP_LIMIT = 1024   # iterations; more than the DMA copy and the power-down take at any tested ratio

# Testbench-facing constants (kept in pmu_cycle_fw_addrs.py for test_soc_pmu_multiclock.py).
CTRLVAL_WORD_IDX = CTRLVAL_BYTE_OFFSET // 4
FAULT_WORD_IDX = FAULT_BYTE_OFFSET // 4
DONE_WORD_IDX = DONE_BYTE_OFFSET // 4
STATUS_WORD_IDX = STATUS_BYTE_OFFSET // 4


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

    def align_line(self):
        """Pad with NOPs to the next 16-byte instruction cache line (ROM_BASE is aligned)."""
        n = sum(1 for typ, _ in self._items if typ != 'label')
        while n % 4:
            self.emit(NOP)
            n += 1

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

    # x5 = DMA_BASE (0x2000_5000), x6 = PMU_BASE (0x2000_8000)
    l5, a5 = lui_addi(5, DMA_BASE)
    asm.emit(l5)
    asm.emit(a5)
    l6, a6 = lui_addi(6, PMU_BASE)
    asm.emit(l6)
    asm.emit(a6)

    # ── Step 1: store MODE_CPU_OFF to SRAM[CTRLVAL]; clear the result words ──
    asm.emit(ADDI(8, 0, MODE_CPU_OFF))
    asm.emit(SW(8, 2, CTRLVAL_BYTE_OFFSET))
    asm.emit(SW(0, 2, FAULT_BYTE_OFFSET))
    asm.emit(SW(0, 2, DONE_BYTE_OFFSET))
    asm.emit(SW(0, 2, STATUS_BYTE_OFFSET))

    # ── Step 2: D-cache flush + spin-wait (same pattern as periph_fw) ────────
    # The flush ends here, before the power-down request. SRAM_BASE is below MMIO_BASE
    # (rv32i_dcache.sv's cacheable-address check), so the stores above only dirty the write-back
    # D-cache until this flush writes them to the SRAM, where the DMA reads them. The spin-wait
    # gives the writeback time to finish.
    asm.emit(CSRRW(0, 0x7C0, 0))   # dcache_flush
    asm.emit(ADDI(16, 0, 0))       # x16 = 0 (counter)
    l17, a17 = lui_addi(17, 1024)  # x17 = 1024 (spin limit)
    asm.emit(l17)
    asm.emit(a17)
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH_WAIT"] - pc))

    # ── Step 3: program DMA to write MODE_CPU_OFF into PMU CTRL ─────────────
    asm.emit(SW(2, 5, 0))     # DMA SRC = x2 = 0x0000_2000
    asm.emit(SW(6, 5, 4))     # DMA DST = 0x2000_8000 (PMU CTRL)
    asm.emit(ADDI(8, 0, 4))
    asm.emit(SW(8, 5, 8))     # DMA LEN = 4 bytes

    # ── Step 4: start the DMA, then wait with register instructions only ────
    # Setup of the wait loop happens before the start store, so nothing but the start store, the
    # loop and the first instruction after the loop sit in the line that the store executes from.
    asm.emit(ADDI(8, 0, 1))
    asm.emit(ADDI(LOOP_REG, 0, 0))
    l20, a20 = lui_addi(20, LOOP_LIMIT)
    asm.emit(l20)
    asm.emit(a20)
    asm.align_line()
    asm.label("START")
    asm.emit(SW(8, 5, 12))    # DMA CTRL = 1: start pulse, cleared by the hardware
    # Step 5: the wait loop. No memory access: the line holds START, LOOP and the first
    # instruction of POST, so the loop makes no instruction fetch either.
    asm.label("LOOP")
    asm.emit(ADDI(LOOP_REG, LOOP_REG, 1))
    asm.thunk(lambda lbl, pc: BNE(LOOP_REG, 20, lbl["LOOP"] - pc))

    # ── Step 6: after the wake-up, read STATUS; clear the timeout flag ──────
    asm.label("POST")
    asm.emit(LW(10, 6, PMU_STATUS_OFFSET))
    asm.emit(ANDI(11, 10, STATUS_TIMEOUT_BIT))
    asm.thunk(lambda lbl, pc: BEQ(11, 0, lbl["CLEARED"] - pc))
    asm.emit(ADDI(12, 0, 1))
    asm.emit(SW(12, 2, FAULT_BYTE_OFFSET))             # record the fault
    asm.emit(SW(12, 6, PMU_STATUS_CLR_OFFSET))         # STATUS_CLR[0] = 1 (W1C)
    asm.label("CLEARED")

    # ── Step 7: record STATUS after the clear and the end marker ────────────
    asm.emit(LW(10, 6, PMU_STATUS_OFFSET))
    asm.emit(SW(10, 2, STATUS_BYTE_OFFSET))
    asm.emit(ADDI(12, 0, 1))
    asm.emit(SW(12, 2, DONE_BYTE_OFFSET))
    asm.emit(CSRRW(0, 0x7C0, 0))   # dcache_flush -- make the result words SRAM-visible

    # ── Step 8: final loop ──────────────────────────────────────────────────
    asm.label("DONE")
    asm.thunk(lambda lbl, pc: JAL(0, lbl["DONE"] - pc))


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

    for req in ('FLUSH_WAIT', 'START', 'LOOP', 'POST', 'DONE'):
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
        f.write(f"LOOP_REG             = {LOOP_REG}\n")
        f.write(f"LOOP_LIMIT           = {LOOP_LIMIT}\n")
        f.write(f"CTRLVAL_WORD_IDX     = {CTRLVAL_WORD_IDX}\n")
        f.write(f"FAULT_WORD_IDX       = {FAULT_WORD_IDX}\n")
        f.write(f"DONE_WORD_IDX        = {DONE_WORD_IDX}\n")
        f.write(f"STATUS_WORD_IDX      = {STATUS_WORD_IDX}\n")
        f.write(f"MODE_CPU_OFF         = 0x{MODE_CPU_OFF:x}\n")
    print(f"Wrote {addrs_path}")
