#!/usr/bin/env python3
"""
gen_periph_hex.py — generate periph_loopback.hex for the M9 DMA+peripheral loopback test.

Firmware runs from ROM @ 0x0000_1000 (RESET_PC after RTL fix).
Tests:
  1. DMA mem->mem copy: SRAM[0x2000..0x200C] -> SRAM[0x2040..0x204C]  (4 words = 16 bytes)
  2. UART internal loopback: TX=0xA5 -> poll STATUS[5] -> read RX -> compare
  3. SPI  internal loopback: TX=0x3C -> poll STATUS[4] -> read RX -> compare

Self-checking: branches to PASS_PC on full success, FAIL_PC on any failure.
Testbench scoreboards commit_pc_o and backdoor-reads SRAM dst region.

Address map (verified against rtl/soc/soc_periph_map_pkg.sv):
  SRAM base   : 0x0000_2000  (crossbar S1, sram_controller u_sram)
  DMA ctrl    : 0x2000_5000  regs: SRC@+0x00, DST@+0x04, LEN@+0x08, CTRL@+0x0C, STATUS@+0x10
  UART ctrl   : 0x2000_2000  regs: TX@+0x00, RX@+0x04, STATUS@+0x08, CTRL@+0x0C, BAUD@+0x10
  SPI  ctrl   : 0x2000_3000  regs: TX@+0x00, RX@+0x04, STATUS@+0x08, CTRL@+0x0C, CLK_DIV@+0x10

All peripheral base addresses have bits[11:0]=0x000 so no LUI sign-extension compensation needed.

DMA SRC region : SRAM word index 0  (byte addr 0x2000 - SRAM_BASE=0x2000) / 4 = 0
DMA DST region : SRAM word index 16 (byte addr 0x2040 - SRAM_BASE=0x2000) / 4 = 16

Register config:
  UART CTRL = 0x13  : tx_en[0]=1, rx_en[1]=1, loopback[4]=1
  UART BAUD = 0     : 1 bit = 16*(0+1) = 16 clocks (fastest legal)
  SPI  CTRL = 0x11  : enable[0]=1, loopback[4]=1  (CPOL=CPHA=0)
  SPI  CLK_DIV = 2  : SCLK half-period = (2+1)=3 clocks
  DMA  start pulse  : write CTRL=1 then CTRL=0

Poll limit: 100000 iterations (100000 * pipeline_overhead >> UART 160 cycles, DMA ~100 cycles).

Register allocation:
  x2  = SRAM base  0x0000_2000
  x5  = DMA base   0x2000_5000
  x6  = UART base  0x2000_2000
  x7  = SPI base   0x2000_3000
  x8  = scratch (patterns, temporaries)
  x9  = scratch (readback, comparison)
  x10 = scratch (src load for DMA compare)
  x11 = scratch (dst load for DMA compare)
  x12 = loop bound (16 bytes)
  x13 = poll counter
  x14 = poll limit (100000)
  x15 = loop byte offset (DMA compare loop)
  x31 = result marker (1=pass, -1=fail)
"""

import os
import sys

# Add project root to path so we can import riscv_encoder
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, ADD, ANDI, SW, LW, BNE, JAL, EBREAK,
)


def CSRRW(rd: int, csr: int, rs1: int) -> int:
    """CSRRW rd, csr, rs1 — atomic CSR read-write.
    CSRW csr, rs1 is the pseudo-instruction alias (rd=x0)."""
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73

ROM_BASE  = 0x0000_1000
ROM_WORDS = 1024
NOP       = 0x00000013   # ADDI x0, x0, 0

# SRAM word indices for backdoor check in testbench
DMA_SRC_IDX = 0    # (0x2000 - 0x2000) >> 2 = 0
DMA_DST_IDX = 16   # (0x2040 - 0x2000) >> 2 = 16


# ---------------------------------------------------------------------------
# LUI+ADDI materialiser with bit-11 sign-extension compensation
# ---------------------------------------------------------------------------
def lui_addi(rd: int, value32: int):
    """Return (lui_word, addi_word) encoding: rd = value32.

    LUI sets bits[31:12]; ADDI adds sign-extended imm[11:0].
    When bit 11 of value32 is set, ADDI's sign-extension subtracts 4096,
    so we add 1 to the LUI immediate to pre-compensate.
    If value32[11:0] == 0, emit ADDI x0,x0,0 (NOP) to keep pair structure
    consistent (callers always emit both words).
    """
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    # Verify
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}): "
        f"upper=0x{upper20:05x} lower_signed={lower_signed} → 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        # Both zero: emit ADDI rd, x0, 0 twice (edge case, but consistent)
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        # No LUI needed, but emit NOP to keep pair structure
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


# ---------------------------------------------------------------------------
# Two-pass label assembler
# ---------------------------------------------------------------------------
class Assembler:
    """Minimal two-pass label resolver.

    Usage:
        asm = Assembler()
        asm.emit(word)             # emit a literal 32-bit word
        asm.label("FOO")           # mark current position as label FOO
        asm.thunk(fn)              # fn(labels, cur_pc) -> int32 (resolved pass 2)
        words = asm.resolve()      # returns list[int] of 32-bit words
        labels = asm.labels        # dict label_name -> byte_address
    """
    def __init__(self):
        self._items = []   # list of ('word'|'label'|'thunk', value)
        self.labels = {}

    def emit(self, word: int):
        self._items.append(('word', word & 0xFFFF_FFFF))

    def label(self, name: str):
        self._items.append(('label', name))

    def thunk(self, fn):
        """fn(labels: dict, cur_pc: int) -> int"""
        self._items.append(('thunk', fn))

    def resolve(self):
        # Pass 1: assign label addresses
        self.labels = {}
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                self.labels[val] = ROM_BASE + idx * 4
            else:
                idx += 1

        # Pass 2: emit words
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
    """Populate assembler with the self-checking firmware.

    All branch/jump targets use thunks so they resolve after labels are placed.
    """
    # ── Prologue: materialise base registers ─────────────────────────────────
    # x2 = 0x0000_2000  (SRAM base)
    l2, a2 = lui_addi(2, 0x0000_2000)
    asm.emit(l2)
    asm.emit(a2)

    # x5 = 0x2000_5000  (DMA base)
    l5, a5 = lui_addi(5, 0x2000_5000)
    asm.emit(l5)
    asm.emit(a5)

    # x6 = 0x2000_2000  (UART base)
    l6, a6 = lui_addi(6, 0x2000_2000)
    asm.emit(l6)
    asm.emit(a6)

    # x7 = 0x2000_3000  (SPI base)
    l7, a7 = lui_addi(7, 0x2000_3000)
    asm.emit(l7)
    asm.emit(a7)

    # x14 = 100000 = 0x1_86A0  (poll limit)
    # 100000 = 0x186A0; upper=0x18=24, lower=0x6A0=1696; bit11 of 0x6A0 = 0 → no comp
    l14, a14 = lui_addi(14, 100000)
    asm.emit(l14)
    asm.emit(a14)

    # ── Step 1: Store 4 pattern words to SRAM src region ────────────────────
    # All 4 patterns have lower 12 bits < 0x800 → no sign-extension complication.
    # 0xA1B2C3D4: lower=0x3D4 (bit11=0) → upper=0xA1B2C, addi=+0x3D4=+980
    l8, a8 = lui_addi(8, 0xA1B2_C3D4)
    asm.emit(l8)
    asm.emit(a8)
    asm.emit(SW(8, 2, 0))    # SRAM[0x2000] = 0xA1B2C3D4

    # 0x11223344: lower=0x344 (bit11=0) → upper=0x11223, addi=+0x344=+836
    l8, a8 = lui_addi(8, 0x1122_3344)
    asm.emit(l8)
    asm.emit(a8)
    asm.emit(SW(8, 2, 4))    # SRAM[0x2004] = 0x11223344

    # 0x00003333: lower=0x333 (bit11=0) → no LUI needed, just ADDI
    l8, a8 = lui_addi(8, 0x0000_3333)
    asm.emit(l8)
    asm.emit(a8)
    asm.emit(SW(8, 2, 8))    # SRAM[0x2008] = 0x00003333

    # 0x00004444: lower=0x444 (bit11=0) → no LUI needed, just ADDI
    l8, a8 = lui_addi(8, 0x0000_4444)
    asm.emit(l8)
    asm.emit(a8)
    asm.emit(SW(8, 2, 12))   # SRAM[0x200C] = 0x00004444

    # ── Step 1b: D-cache flush (software coherency for DMA) ─────────────────
    # The 4 stores above are cached (addr < MMIO_BASE). The DMA engine accesses
    # SRAM directly (bypasses D-cache). Write CSR 0x7C0 to trigger CS_FLUSH_SCAN,
    # which writes all dirty cache lines back to SRAM before DMA starts.
    #
    # CSRW 0x7C0, x0  →  CSRRW x0, 0x7C0, x0  (funct3=001 → always fires)
    # The CSRW commits immediately (no mem_rd/mem_wr, no dc_stall feedback).
    # The dcache runs CS_FLUSH_SCAN asynchronously: 256 line scans, 1 dirty line
    # → ~1 writeback + 255 skip cycles ≈ 300 cycles total.
    # Spin for 1024 iterations (each = LW+ADDI+BNE ≈ 3-4 cycles, so ~4096 cycles)
    # to guarantee the flush completes before DMA is programmed.
    asm.emit(CSRRW(0, 0x7C0, 0))   # dcache_flush: write 0 triggers flush-all

    # Spin-wait for flush: x16 = 1024 iteration countdown
    asm.emit(ADDI(16, 0, 0))        # x16 = 0 (counter)
    # x17 = 1024 (spin limit)
    l17, a17 = lui_addi(17, 1024)
    asm.emit(l17); asm.emit(a17)
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(16, 16, 1))       # x16++
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH_WAIT"] - pc))

    # ── Step 2: Program DMA ──────────────────────────────────────────────────
    # SRC = x2 = 0x2000
    asm.emit(SW(2, 5, 0))    # DMA SRC

    # DST = 0x0000_2040
    l8, a8 = lui_addi(8, 0x0000_2040)
    asm.emit(l8)
    asm.emit(a8)
    asm.emit(SW(8, 5, 4))    # DMA DST

    # LEN = 16 (bytes)
    asm.emit(ADDI(8, 0, 16))
    asm.emit(SW(8, 5, 8))    # DMA LEN

    # CTRL = 1 (start pulse 0→1)
    asm.emit(ADDI(8, 0, 1))
    asm.emit(SW(8, 5, 12))   # DMA CTRL = 1

    # CTRL = 0 (deassert)
    asm.emit(ADDI(8, 0, 0))
    asm.emit(SW(8, 5, 12))   # DMA CTRL = 0

    # ── Step 3: Poll DMA STATUS[1] = done ────────────────────────────────────
    asm.emit(ADDI(13, 0, 0))   # x13 = 0
    asm.label("DMA_POLL")
    asm.emit(LW(9, 5, 16))     # x9 = DMA STATUS (offset 0x10=16)
    asm.emit(ANDI(9, 9, 2))    # isolate bit[1]
    asm.thunk(lambda lbl, pc: BNE(9, 0, lbl["DMA_DONE"] - pc))
    asm.emit(ADDI(13, 13, 1))
    asm.thunk(lambda lbl, pc: BNE(13, 14, lbl["DMA_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))
    asm.label("DMA_DONE")

    # ── Step 4: Verify DMA copy ───────────────────────────────────────────────
    asm.emit(ADDI(15, 0, 0))   # x15 = byte offset, starts at 0
    asm.label("DMA_CMP")
    # src word: mem[x2 + x15]
    asm.emit(ADD(10, 2, 15))
    asm.emit(LW(10, 10, 0))
    # dst word: mem[x2 + 0x40 + x15]  (0x40 fits in a 7-bit positive immediate)
    asm.emit(ADDI(11, 2, 0x40))  # 0x40 = 64, bit11=0 OK
    asm.emit(ADD(11, 11, 15))
    asm.emit(LW(11, 11, 0))
    # compare
    asm.thunk(lambda lbl, pc: BNE(10, 11, lbl["FAIL"] - pc))
    asm.emit(ADDI(15, 15, 4))
    asm.emit(ADDI(12, 0, 16))  # x12 = 16
    asm.thunk(lambda lbl, pc: BNE(15, 12, lbl["DMA_CMP"] - pc))

    # ── Step 5: UART loopback ─────────────────────────────────────────────────
    # BAUD = 0
    asm.emit(ADDI(8, 0, 0))
    asm.emit(SW(8, 6, 16))    # UART BAUD @ +0x10

    # CTRL = 0x13 = 19  (tx_en | rx_en | loopback)
    asm.emit(ADDI(8, 0, 0x13))
    asm.emit(SW(8, 6, 12))    # UART CTRL @ +0x0C

    # TX = 0xA5 = 165
    asm.emit(ADDI(8, 0, 0xA5))
    asm.emit(SW(8, 6, 0))     # UART TX @ +0x00

    # Poll STATUS[5] = rx_valid  (0x20 = 32)
    asm.emit(ADDI(13, 0, 0))
    asm.label("UART_POLL")
    asm.emit(LW(9, 6, 8))     # UART STATUS @ +0x08
    asm.emit(ANDI(9, 9, 0x20))
    asm.thunk(lambda lbl, pc: BNE(9, 0, lbl["UART_DONE"] - pc))
    asm.emit(ADDI(13, 13, 1))
    asm.thunk(lambda lbl, pc: BNE(13, 14, lbl["UART_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))
    asm.label("UART_DONE")

    # Read RX, mask, compare
    asm.emit(LW(9, 6, 4))     # UART RX @ +0x04
    asm.emit(ANDI(9, 9, 0xFF))
    asm.emit(ADDI(10, 0, 0xA5))
    asm.thunk(lambda lbl, pc: BNE(9, 10, lbl["FAIL"] - pc))

    # ── Step 6: SPI loopback ──────────────────────────────────────────────────
    # CLK_DIV = 2
    asm.emit(ADDI(8, 0, 2))
    asm.emit(SW(8, 7, 16))    # SPI CLK_DIV @ +0x10

    # CTRL = 0x11 = 17  (enable | loopback)
    asm.emit(ADDI(8, 0, 0x11))
    asm.emit(SW(8, 7, 12))    # SPI CTRL @ +0x0C

    # TX = 0x3C = 60
    asm.emit(ADDI(8, 0, 0x3C))
    asm.emit(SW(8, 7, 0))     # SPI TX @ +0x00

    # Poll STATUS[4] = rx_valid  (0x10 = 16)
    asm.emit(ADDI(13, 0, 0))
    asm.label("SPI_POLL")
    asm.emit(LW(9, 7, 8))     # SPI STATUS @ +0x08
    asm.emit(ANDI(9, 9, 0x10))
    asm.thunk(lambda lbl, pc: BNE(9, 0, lbl["SPI_DONE"] - pc))
    asm.emit(ADDI(13, 13, 1))
    asm.thunk(lambda lbl, pc: BNE(13, 14, lbl["SPI_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))
    asm.label("SPI_DONE")

    # Read RX, mask, compare
    asm.emit(LW(9, 7, 4))     # SPI RX @ +0x04
    asm.emit(ANDI(9, 9, 0xFF))
    asm.emit(ADDI(10, 0, 0x3C))
    asm.thunk(lambda lbl, pc: BNE(9, 10, lbl["FAIL"] - pc))

    # ── Step 7: Success path ──────────────────────────────────────────────────
    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    # ── FAIL ──────────────────────────────────────────────────────────────────
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))  # x31 = -1
    asm.emit(EBREAK())

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))   # x31 = 1
    asm.emit(EBREAK())


def print_listing(words: list, labels: dict):
    pc_to_label = {v: k for k, v in labels.items()}
    print("\n=== Periph Loopback Firmware Listing ===")
    print(f"{'PC':>10}  {'Word':>10}  Annotation")
    print("-" * 60)
    for i, w in enumerate(words):
        if w == NOP and i >= 80:
            break  # stop printing NOP padding
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

    # Print listing
    print_listing(words, labels)

    # Verify label existence
    for req in ('FAIL', 'PASS', 'DMA_POLL', 'DMA_DONE', 'DMA_CMP',
                'UART_POLL', 'UART_DONE', 'SPI_POLL', 'SPI_DONE'):
        assert req in labels, f"Label {req!r} not found; got {list(labels)}"

    pass_pc = labels['PASS']
    fail_pc = labels['FAIL']
    print(f"PASS_PC = 0x{pass_pc:08x}  (word {(pass_pc - ROM_BASE)//4})")
    print(f"FAIL_PC = 0x{fail_pc:08x}  (word {(fail_pc - ROM_BASE)//4})")

    # Guard: firmware must fit in ROM before padding
    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} > ROM_WORDS={ROM_WORDS}"
    )

    # Pad to ROM_WORDS
    padded = list(words)
    padded.extend([NOP] * (ROM_WORDS - len(padded)))

    # Write hex
    hex_path = os.path.join(out_dir, 'periph_loopback.hex')
    os.makedirs(out_dir, exist_ok=True)
    with open(hex_path, 'w') as f:
        for w in padded:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded)} words to {hex_path}")

    # Write periph_fw_addrs.py
    addrs_path = os.path.join(out_dir, 'periph_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_periph_hex.py — do not edit.\n")
        f.write(f"PASS_PC     = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC     = 0x{fail_pc:08x}\n")
        f.write(f"DMA_SRC_IDX = {DMA_SRC_IDX}   "
                "# SRAM word index: (0x2000 - 0x2000) >> 2\n")
        f.write(f"DMA_DST_IDX = {DMA_DST_IDX}  "
                "# SRAM word index: (0x2040 - 0x2000) >> 2\n")
    print(f"Wrote {addrs_path}")
    print(f"  PASS_PC     = 0x{pass_pc:08x}")
    print(f"  FAIL_PC     = 0x{fail_pc:08x}")
    print(f"  DMA_SRC_IDX = {DMA_SRC_IDX}")
    print(f"  DMA_DST_IDX = {DMA_DST_IDX}")
