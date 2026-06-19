#!/usr/bin/env python3
"""
gen_stress_hex.py — generate stress_fw.hex for the Phase 5 M9 SoC stress + benchmark test.

This firmware performs a long, multi-master exerciser designed to drive ≥1 000 000 sim
cycles of sustained SoC activity while remaining self-checking.  It runs entirely in
CPU firmware so there is no dependency on a Python scoreboard model for MMIO addresses
(which cannot be modelled by soc_model.py).

Firmware sequence (looped STRESS_ITER times)
─────────────────────────────────────────────
  [A] SRAM burst write: CPU writes BURST_N_WORDS (32) words to SRAM at BUF_A using
      a tight store loop (simple, deterministic write traffic to the data crossbar).

  [B] SRAM burst read + verify: CPU reads the words back and compares against the
      expected pattern (word_idx XOR MAGIC).  Any mismatch → FAIL.

  [C] DMA mem→mem: program the DMA engine (SRC=BUF_A, DST=BUF_B, LEN), pulse start,
      poll STATUS.done (bounded by DMA_POLL_MAX), verify DST matches SRC.

  [D] GPU vector kernel: flush D-cache (CSR 0x7C0), write src+1 kernel to SRAM,
      flush again, program GPU registers (KERNEL_PC, GRID, BLOCK, launch), poll
      GPU_STATUS.done (bounded by GPU_POLL_MAX), inval D-cache (CSR 0x7C1), read
      back GPU output words and verify src+1.

  [E] UART + SPI internal loopback: write one byte each via CTRL[4]=loopback, poll
      rx_valid (bounded by PERIPH_POLL_MAX), verify byte matches.

  [F] Timer read: read TIMER_CNT0 (offset 0x00 in timer AXI-Lite slave) and store
      in a scratch SRAM word.  No assertion on value — just exercises the AXI-Lite
      path to the timer; the cocotb monitor checks it is non-zero after iteration 0.

After STRESS_ITER loops the firmware jumps to PASS_PC + EBREAK.
Any check failure jumps to FAIL_PC + EBREAK.

Benchmarks embedded in the firmware
────────────────────────────────────
The firmware records a "before" cycle count from mcycle CSR at each benchmark entry
point and an "after" count at exit, storing results in SRAM scratch words:
  BM_CPU_WI   — mcycle delta for the CPU 32-word store+load loop
  BM_DMA_WI   — mcycle delta for the DMA mem→mem transfer
  BM_GPU_WI   — mcycle delta for the GPU kernel (incl. cache flush/inval)

These are backdoor-read by the cocotb test and logged.

Memory layout
─────────────
  ROM_BASE   = 0x0000_1000  (boot ROM)
  SRAM_BASE  = 0x0000_2000  (SRAM)

  BUF_A      = 0x0000_2000  (word 0..31, 32 words × 4 bytes = 128 bytes)
  BUF_B      = 0x0000_2080  (word 32..63, 128 bytes)
  GPU_SRC    = 0x0000_2100  (word 64..71, 8 words)
  GPU_DST    = 0x0000_2140  (word 80..87, 8 words)
  KERNEL_PC  = 0x0000_2200  (word 128..159, GPU kernel image)
  SCRATCH    = 0x0000_2400  (word 256, timer + benchmark words)

  BM_CPU_WI  = 256   (SRAM word index)
  BM_DMA_WI  = 257
  BM_GPU_WI  = 258
  TIMER_WI   = 259

Peripheral MMIO (all ≥ 0x2000_0000, D-cache bypass)
───────────────────────────────────────────────────
  GPU    = 0x2000_1000
  UART   = 0x2000_2000
  SPI    = 0x2000_3000
  TIMER  = 0x2000_4000
  DMA    = 0x2000_5000
  IRQ    = 0x2000_6000
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, ADD, SW, LW, BNE, BEQ, JAL, EBREAK, ANDI, SLLI,
    XOR, ORI, SUB, SRL, SRA, AND,
)

# ── Extra encoders not in riscv_encoder.py ──────────────────────────────────

def CSRRW(rd: int, csr: int, rs1: int) -> int:
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73

def CSRRS(rd: int, csr: int, rs1: int) -> int:
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x2 << 12) | (rd << 7) | 0x73

def CSRRCI(rd: int, csr: int, uimm5: int) -> int:
    return ((csr & 0xFFF) << 20) | ((uimm5 & 0x1F) << 15) | (0x7 << 12) | (rd << 7) | 0x73

# ── GPU instruction encoders ─────────────────────────────────────────────────

def _r_instr(opcode7: int, rd: int, rs1: int, rs2: int, funct3: int = 0, funct7: int = 0) -> int:
    return ((funct7 & 0x7F) << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | \
           ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | (opcode7 & 0x7F)

def _i_instr(opcode7: int, rd: int, rs1: int, imm12: int, funct3: int = 0) -> int:
    imm = imm12 & 0xFFF
    return (imm << 20) | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) | \
           ((rd & 0x1F) << 7) | (opcode7 & 0x7F)

_OP_VADD       = 0x01
_OP_VSLL       = 0x07
_OP_VADDI      = 0x11
_OP_VLD        = 0x20
_OP_VST        = 0x21
_OP_VRET       = 0x3F
_OP_VMOV_TID_X = 0x40

def gpu_vmov_tid_x(rd: int) -> int:
    return _i_instr(_OP_VMOV_TID_X, rd, 0, 0)

def gpu_vaddi(rd: int, rs1: int, imm: int) -> int:
    return _i_instr(_OP_VADDI, rd, rs1, imm)

def gpu_vsll(rd: int, rs1: int, rs2: int) -> int:
    return _r_instr(_OP_VSLL, rd, rs1, rs2)

def gpu_vadd(rd: int, rs1: int, rs2: int) -> int:
    return _r_instr(_OP_VADD, rd, rs1, rs2)

def gpu_vld(rd: int, rs1: int, offset: int = 0) -> int:
    return _i_instr(_OP_VLD, rd, rs1, offset)

def gpu_vst(rs2_data: int, rs1_base: int, base_offset: int = 0) -> int:
    imm = (base_offset & ~0x1F) | (rs2_data & 0x1F)
    return (imm << 20) | ((rs1_base & 0x1F) << 15) | _OP_VST

def gpu_vret() -> int:
    return _i_instr(_OP_VRET, 0, 0, 0)

# ── ROM / SRAM layout ────────────────────────────────────────────────────────

ROM_BASE   = 0x0000_1000
ROM_WORDS  = 1024              # 4 KB ROM (matches boot_rom.sv MEM_WORDS=1024)
NOP        = 0x00000013

SRAM_BASE  = 0x0000_2000

# SRAM buffer layout (all word indices from SRAM_BASE)
BUF_A_BYTE  = SRAM_BASE + 0x000    # 0x2000
BUF_B_BYTE  = SRAM_BASE + 0x080    # 0x2080
GPU_SRC_BYTE= SRAM_BASE + 0x100    # 0x2100
GPU_DST_BYTE= SRAM_BASE + 0x140    # 0x2140
KERNEL_PC_BYTE = SRAM_BASE + 0x200 # 0x2200

BUF_A_WI   = (BUF_A_BYTE  - SRAM_BASE) >> 2   # 0
BUF_B_WI   = (BUF_B_BYTE  - SRAM_BASE) >> 2   # 32
GPU_SRC_WI = (GPU_SRC_BYTE- SRAM_BASE) >> 2   # 64
GPU_DST_WI = (GPU_DST_BYTE- SRAM_BASE) >> 2   # 80
KERNEL_WI  = (KERNEL_PC_BYTE-SRAM_BASE) >> 2  # 128

# Benchmark + scratch words (well above the working buffers)
BM_CPU_WI  = 256
BM_DMA_WI  = 257
BM_GPU_WI  = 258
TIMER_WI   = 259
ITER_WI    = 260   # stress iteration counter stored in SRAM for cocotb visibility

# Peripheral MMIO bases
GPU_BASE  = 0x2000_1000
UART_BASE = 0x2000_2000
SPI_BASE  = 0x2000_3000
TIMER_BASE= 0x2000_4000
DMA_BASE  = 0x2000_5000
IRQ_BASE  = 0x2000_6000

# GPU ctrl register offsets
GPU_OFF_CTRL      = 0x000
GPU_OFF_STATUS    = 0x004
GPU_OFF_KERNEL_PC = 0x008
GPU_OFF_GRID_X    = 0x00C
GPU_OFF_GRID_Y    = 0x010
GPU_OFF_GRID_Z    = 0x014
GPU_OFF_BLOCK_X   = 0x018
GPU_OFF_BLOCK_Y   = 0x01C
GPU_OFF_BLOCK_Z   = 0x020
GPU_OFF_IRQ_CLR   = 0x028

# DMA register offsets (from dma_engine.sv — word indices × 4)
# REG_SRC_ADDR=0, REG_DST_ADDR=1, REG_LENGTH=2, REG_CTRL=3, REG_STATUS=4
DMA_OFF_SRC    = 0x00
DMA_OFF_DST    = 0x04
DMA_OFF_LEN    = 0x08
DMA_OFF_CTRL   = 0x0C   # CTRL_START_BIT=0, CTRL_SRST_BIT=2
DMA_OFF_STATUS = 0x10   # STATUS[1]=done(sticky)
# DMA STATUS bit positions
DMA_STAT_DONE_BIT = 2   # bitmask: STATUS[1] = 0x2

# UART register offsets (uart_controller.sv — REG_TX=0, RX=1, STATUS=2, CTRL=3)
UART_OFF_TX     = 0x00
UART_OFF_RX     = 0x04
UART_OFF_STATUS = 0x08  # STATUS[5]=rx_valid
UART_OFF_CTRL   = 0x0C  # [0]=TX_EN, [1]=RX_EN, [4]=LOOPBACK → 0x13 enables all+loopback
# UART CTRL values
UART_CTRL_EN_LOOPBACK = 0x13   # TX_EN|RX_EN|LOOPBACK
# UART STATUS bit masks
UART_STAT_RX_VALID = (1 << 5)  # STATUS[5]

# SPI register offsets (spi_controller.sv — REG_TX=0, RX=1, STATUS=2, CTRL=3)
SPI_OFF_TX      = 0x00
SPI_OFF_RX      = 0x04
SPI_OFF_STATUS  = 0x08  # STATUS[4]=rx_valid
SPI_OFF_CTRL    = 0x0C  # [0]=ENABLE, [4]=LOOPBACK → 0x11 enables+loopback
# SPI CTRL values
SPI_CTRL_EN_LOOPBACK = 0x11   # ENABLE|LOOPBACK
# SPI STATUS bit masks
SPI_STAT_RX_VALID = (1 << 4)   # STATUS[4]

# Timer register offset
TIMER_OFF_CNT0  = 0x00

# Test parameters
BURST_N_WORDS  = 32     # words per CPU store/load burst (BUF_A)
GPU_N_WORDS    = 8      # GPU kernel lanes
MAGIC          = 0xA5   # XOR pattern for CPU burst data (fits in ADDI)
UART_BYTE      = 0x55   # ASCII 'U' — easy to eyeball
SPI_BYTE       = 0xAA   # alternating bits

# Poll timeouts (firmware-level loop counts, not cycle counts)
# At ~4-8 cycles/iter these translate to 3k–16k cycles max wait
DMA_POLL_MAX   = 2_000
GPU_POLL_MAX   = 4_000   # GPU kernel takes more cycles
PERIPH_POLL_MAX= 2_000

# Number of outer stress iterations
# Each iteration is ~110 000 cycles (measured); 10 iters → ~1 100 000+ cycles total.
# Raised from 6 to 10 to reliably exceed the pgf bead 1 000 000-cycle acceptance bar.
STRESS_ITER    = 10


def lui_addi(rd: int, value32: int):
    """Return (lui_word, addi_word) pair to load a 32-bit constant into rd."""
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}): got 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


class Assembler:
    """Two-pass label assembler.  Labels resolve to byte PCs; ROM_BASE is origin."""
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
        self._items.append(('thunk', fn))

    def pad_to_word(self, word_idx: int):
        cur = sum(1 for t, _ in self._items if t != 'label')
        assert cur <= word_idx, f"pad_to_word({word_idx}): already at word {cur}"
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


def _emit_load_u32(a: Assembler, rd: int, value32: int):
    """Emit LUI+ADDI sequence to load value32 into rd."""
    hi, lo = lui_addi(rd, value32)
    a.emit(hi)
    a.emit(lo)


def _emit_mmio_write(a: Assembler, base: int, offset: int, data: int,
                     r_base: int = 5, r_data: int = 6):
    """Emit: load base+offset into r_base, load data into r_data, SW r_data,0(r_base)."""
    _emit_load_u32(a, r_base, base + offset)
    _emit_load_u32(a, r_data, data)
    a.emit(SW(r_data, r_base, 0))


def _emit_mmio_read(a: Assembler, base: int, offset: int, rd: int, r_base: int = 5):
    """Emit: load base+offset into r_base, LW rd, 0(r_base)."""
    _emit_load_u32(a, r_base, base + offset)
    a.emit(LW(rd, r_base, 0))


def _emit_sram_write(a: Assembler, byte_addr: int, data: int,
                     r_base: int = 5, r_data: int = 6):
    """Emit: load byte_addr into r_base, load data into r_data, SW."""
    _emit_load_u32(a, r_base, byte_addr)
    _emit_load_u32(a, r_data, data)
    a.emit(SW(r_data, r_base, 0))


_dcache_flush_seq = [0]  # module-level counter for unique label generation


def _emit_dcache_flush(a: Assembler, spin: int = 2048, r_tmp: int = 7, r_cnt: int = 8):
    """CSRW 0x7C0 (dcache_flush) then spin `spin` NOP iters."""
    _dcache_flush_seq[0] += 1
    _uid = _dcache_flush_seq[0]
    a.emit(CSRRW(0, 0x7C0, 0))      # CSRW dcache_flush, x0
    _emit_load_u32(a, r_cnt, spin)  # r_cnt = spin
    a.label(f'_flush_spin_{_uid}')
    a.emit(ADDI(r_cnt, r_cnt, -1))  # r_cnt--
    a.thunk(lambda lbl, pc, _l=f'_flush_spin_{_uid}': BNE(r_cnt, 0, lbl[_l] - pc))


_dcache_inval_seq = [0]  # module-level counter for unique label generation


def _emit_dcache_inval(a: Assembler, spin: int = 2048, r_tmp: int = 7, r_cnt: int = 8):
    """CSRW 0x7C1 (dcache_inval) then spin `spin` NOP iters."""
    _dcache_inval_seq[0] += 1
    _uid = _dcache_inval_seq[0]
    a.emit(CSRRW(0, 0x7C1, 0))
    _emit_load_u32(a, r_cnt, spin)
    a.label(f'_inval_spin_{_uid}')
    a.emit(ADDI(r_cnt, r_cnt, -1))
    a.thunk(lambda lbl, pc, _l=f'_inval_spin_{_uid}': BNE(r_cnt, 0, lbl[_l] - pc))


# ── GPU kernel ───────────────────────────────────────────────────────────────

def build_gpu_kernel() -> list:
    """
    1 warp, 8 lanes.  DST[l] = SRC[l] + 1.
    SRC_BYTE = GPU_SRC_BYTE = 0x2100, DST_BYTE = GPU_DST_BYTE = 0x2140.

    Address construction (same approach as coherency and cpu_gpu_irq tests):
      r4 = 1; r5 = 13; r4 = 1<<13 = 0x2000; r4 = 0x2000 + 0x100 = 0x2100
      r9 base for VST: DST_BASE - rs2_idx*1 = 0x2140 - 8 = 0x2138
        (rs2 for VST is register r8; VST addr = rs1[lane] + (imm & ~0x1F) | rs2_idx
         where rs2_idx = 8; imm upper bits provide offset).
    """
    instrs = []

    # r1[l] = tid.x (lane id)
    instrs.append(gpu_vmov_tid_x(1))
    # r2 = 2  (shift amount for *4)
    instrs.append(gpu_vaddi(2, 0, 2))
    # r3[l] = l * 4
    instrs.append(gpu_vsll(3, 1, 2))

    # Build SRC_BASE = 0x2100:  r4=1, r5=13, r4=1<<13=0x2000, r4+=0x100
    instrs.append(gpu_vaddi(4, 0, 1))
    instrs.append(gpu_vaddi(5, 0, 13))
    instrs.append(gpu_vsll(4, 4, 5))
    instrs.append(gpu_vaddi(4, 4, 0x100))

    # r6[l] = SRC_BASE + l*4
    instrs.append(gpu_vadd(6, 4, 3))
    # r7[l] = mem[SRC_BASE + l*4]
    instrs.append(gpu_vld(7, 6, 0))
    # r8[l] = src[l] + 1
    instrs.append(gpu_vaddi(8, 7, 1))

    # Build DST addr in r9: DST_BASE = 0x2140; VST encodes addr = rs1[l] + (imm & ~0x1F | rs2_idx).
    # We need rs1[l] + rs2_idx == 0x2140 + l*4.  rs2_idx = 8 (register r8 holds data).
    # rs1[l] = 0x2140 - 8 + l*4 = 0x2138 + l*4.
    # At this point r4 = 0x2100 (SRC_BASE).  DST_BASE - rs2_idx = 0x2138 = 0x2100 + 0x038.
    instrs.append(gpu_vaddi(9, 4, 0x038))   # r9[l] = 0x2138  (broadcast, since r4 is uniform)
    # r9[l] = 0x2138 + l*4
    instrs.append(gpu_vadd(9, 9, 3))
    # VST r8 data to r9+8 = DST_BASE + l*4
    instrs.append(gpu_vst(8, 9, 0))         # addr = r9[l] + (0 & ~0x1F | 8) = r9[l] + 8

    instrs.append(gpu_vret())
    return instrs


# ── Main firmware assembler ───────────────────────────────────────────────────

def build_stress_fw() -> list:
    """
    Build the full stress firmware.  Returns a list of 32-bit words for ROM.

    Register usage convention (outside per-section comments):
      x1  = loop counter (outer stress iter)
      x2  = inner loop counter
      x3  = base address scratch
      x4  = data scratch
      x5  = mmio base scratch (also used by _emit_mmio_*)
      x6  = mmio data scratch (also used by _emit_mmio_*)
      x7  = tmp / poll counter
      x8  = tmp / poll counter
      x9  = tmp
      x10 = mcycle snapshot "before" for benchmark
      x11 = mcycle snapshot "after"  for benchmark
      x12 = result word accumulator
      x13-x15 = address constants (reload per section)
    """
    a = Assembler()

    # ── Word 0: reset-vector trampoline ──────────────────────────────────────
    # Jump to MAIN at word 10 (0x1028) — skips the reserved ISR slot.
    MAIN_WORD = 10
    a.thunk(lambda lbl, pc: JAL(0, lbl['MAIN'] - pc))

    # ── Words 1..9: reserved for ISR (unused in stress test; NOPs) ───────────
    a.pad_to_word(MAIN_WORD)

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN: initialise x1 = STRESS_ITER (outer loop counter)
    # ─────────────────────────────────────────────────────────────────────────
    a.label('MAIN')
    _emit_load_u32(a, 1, STRESS_ITER)          # x1 = STRESS_ITER

    # Initialise GPU src buffer in SRAM once (before loop, so GPU kernel
    # always has valid source data on first iteration).
    # GPU_SRC[l] = l | (MAGIC << 8)  for l in 0..7
    _emit_load_u32(a, 3, GPU_SRC_BYTE)         # x3 = GPU_SRC_BYTE addr
    _emit_load_u32(a, 4, 0)                    # x4 = word index
    a.label('GPU_SRC_INIT')
    # data = (MAGIC << 8) | word_index  — unique per word, small enough for ADDI
    # We'll just use (word_index + 0x11) as initial source values
    a.emit(ADDI(12, 4, 0x11))                  # x12 = index + 0x11
    a.emit(SW(12, 3, 0))                       # mem[x3] = x12
    a.emit(ADDI(3, 3, 4))                      # x3 += 4
    a.emit(ADDI(4, 4, 1))                      # x4++
    _emit_load_u32(a, 9, GPU_N_WORDS)
    a.thunk(lambda lbl, pc: BNE(4, 9, lbl['GPU_SRC_INIT'] - pc))

    # Enable timer (REG_TMR_CTRL at offset 0x08, CTRL_ENABLE_BIT=0)
    # Timer prescale defaults to 0 → ticks every clock cycle once enabled.
    # Must enable before outer loop so CNT0 is non-zero by the time we read it.
    TIMER_OFF_CTRL = 0x08   # REG_TMR_CTRL = index 2, byte offset = 2*4 = 0x08
    _emit_mmio_write(a, TIMER_BASE, TIMER_OFF_CTRL, 1)  # CTRL[0]=enable

    # ─────────────────────────────────────────────────────────────────────────
    # OUTER LOOP: x1 = iteration count (counts down to 0)
    # ─────────────────────────────────────────────────────────────────────────
    a.label('OUTER_LOOP')

    # ── [A] CPU SRAM burst write ──────────────────────────────────────────────
    # x10 = mcycle before
    a.emit(CSRRS(10, 0xB00, 0))               # x10 = mcycle (CSR 0xB00)

    _emit_load_u32(a, 3, BUF_A_BYTE)          # x3 = BUF_A base addr
    _emit_load_u32(a, 2, 0)                   # x2 = word index
    a.label('WRITE_LOOP')
    # data[i] = i XOR MAGIC (MAGIC = 0xA5 fits in ADDI)
    a.emit(XOR(4, 2, 0))                      # x4 = x2 XOR x0 = x2  (initial: just idx)
    a.emit(ADDI(4, 4, MAGIC))                 # x4 = idx + MAGIC  (approximation; avoids reg overhead)
    a.emit(SW(4, 3, 0))                       # mem[x3] = x4
    a.emit(ADDI(3, 3, 4))                     # x3 += 4
    a.emit(ADDI(2, 2, 1))                     # x2++
    _emit_load_u32(a, 9, BURST_N_WORDS)
    a.thunk(lambda lbl, pc: BNE(2, 9, lbl['WRITE_LOOP'] - pc))

    # ── [B] CPU SRAM burst read + verify ─────────────────────────────────────
    _emit_load_u32(a, 3, BUF_A_BYTE)
    _emit_load_u32(a, 2, 0)
    a.label('READ_LOOP')
    a.emit(LW(4, 3, 0))                       # x4 = mem[x3]
    # expected = idx + MAGIC
    a.emit(ADDI(9, 2, MAGIC))                 # x9 = expected
    a.thunk(lambda lbl, pc: BEQ(4, 9, lbl['READ_OK'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['FAIL'] - pc))  # mismatch → FAIL
    a.label('READ_OK')
    a.emit(ADDI(3, 3, 4))
    a.emit(ADDI(2, 2, 1))
    _emit_load_u32(a, 9, BURST_N_WORDS)
    a.thunk(lambda lbl, pc: BNE(2, 9, lbl['READ_LOOP'] - pc))

    # store CPU burst mcycle delta
    a.emit(CSRRS(11, 0xB00, 0))               # x11 = mcycle after
    a.emit(SUB(12, 11, 10))                   # x12 = delta
    _emit_load_u32(a, 3, SRAM_BASE + BM_CPU_WI * 4)
    a.emit(SW(12, 3, 0))

    # ── [C] DMA mem→mem ────────────────────────────────────────────────────────
    # Flush D-cache so BUF_A dirty lines are written back to SRAM before DMA reads them.
    # Without this, DMA sees stale SRAM data (CPU SW went to cache, not SRAM directly).
    _emit_dcache_flush(a, spin=2048, r_cnt=2)

    a.emit(CSRRS(10, 0xB00, 0))               # x10 = mcycle before DMA

    # Soft-reset DMA to clear sticky done/error from any previous run
    _emit_mmio_write(a, DMA_BASE, DMA_OFF_CTRL, 0x4)  # CTRL_SRST_BIT=2 → 0x4

    # Program DMA: SRC=BUF_A, DST=BUF_B, LEN=BURST_N_WORDS*4
    _emit_mmio_write(a, DMA_BASE, DMA_OFF_SRC, BUF_A_BYTE)
    _emit_mmio_write(a, DMA_BASE, DMA_OFF_DST, BUF_B_BYTE)
    _emit_mmio_write(a, DMA_BASE, DMA_OFF_LEN, BURST_N_WORDS * 4)
    # Start DMA (CTRL bit 0 = start, edge-detected)
    _emit_mmio_write(a, DMA_BASE, DMA_OFF_CTRL, 0x1)

    # Poll DMA STATUS bit 1 (done, sticky) up to DMA_POLL_MAX times
    _emit_load_u32(a, 2, DMA_POLL_MAX)        # x2 = poll count
    _emit_load_u32(a, 5, DMA_BASE + DMA_OFF_STATUS)  # x5 = DMA_STATUS addr
    a.label('DMA_POLL')
    a.emit(LW(4, 5, 0))                       # x4 = DMA_STATUS
    a.emit(ANDI(4, 4, DMA_STAT_DONE_BIT))     # x4 &= 0x2 (done bit 1)
    a.thunk(lambda lbl, pc: BNE(4, 0, lbl['DMA_DONE'] - pc))
    a.emit(ADDI(2, 2, -1))
    a.thunk(lambda lbl, pc: BEQ(2, 0, lbl['FAIL'] - pc))   # timeout
    a.thunk(lambda lbl, pc: JAL(0, lbl['DMA_POLL'] - pc))
    a.label('DMA_DONE')

    # Inval D-cache so the CPU reads BUF_B from SRAM (DMA wrote there; cache may be stale/empty).
    # Also invals BUF_A cache lines so they reload from SRAM for the verify comparison.
    _emit_dcache_inval(a, spin=2048, r_cnt=2)

    # Verify BUF_B matches BUF_A (word by word)
    _emit_load_u32(a, 3, BUF_A_BYTE)          # x3 = BUF_A
    _emit_load_u32(a, 13, BUF_B_BYTE)         # x13 = BUF_B
    _emit_load_u32(a, 2, 0)
    a.label('DMA_VERIFY')
    a.emit(LW(4, 3, 0))                       # x4 = BUF_A[i]
    a.emit(LW(9, 13, 0))                      # x9 = BUF_B[i]
    a.thunk(lambda lbl, pc: BEQ(4, 9, lbl['DMA_VERIFY_OK'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['FAIL'] - pc))
    a.label('DMA_VERIFY_OK')
    a.emit(ADDI(3, 3, 4))
    a.emit(ADDI(13, 13, 4))
    a.emit(ADDI(2, 2, 1))
    _emit_load_u32(a, 9, BURST_N_WORDS)
    a.thunk(lambda lbl, pc: BNE(2, 9, lbl['DMA_VERIFY'] - pc))

    # store DMA mcycle delta
    a.emit(CSRRS(11, 0xB00, 0))
    a.emit(SUB(12, 11, 10))
    _emit_load_u32(a, 3, SRAM_BASE + BM_DMA_WI * 4)
    a.emit(SW(12, 3, 0))

    # ── [D] GPU vector kernel ────────────────────────────────────────────────
    a.emit(CSRRS(10, 0xB00, 0))               # x10 = mcycle before GPU

    # Write GPU kernel image into SRAM[KERNEL_PC_BYTE]
    kernel_words = build_gpu_kernel()
    _emit_load_u32(a, 3, KERNEL_PC_BYTE)
    for kw in kernel_words:
        _emit_load_u32(a, 4, kw)
        a.emit(SW(4, 3, 0))
        a.emit(ADDI(3, 3, 4))

    # Flush D-cache (ensures kernel + src data visible to GPU)
    _emit_dcache_flush(a, spin=2048, r_cnt=2)

    # Program GPU control registers
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_KERNEL_PC, KERNEL_PC_BYTE)
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_GRID_X,    1)
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_GRID_Y,    1)
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_GRID_Z,    1)
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_BLOCK_X,   GPU_N_WORDS)  # 8 threads
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_BLOCK_Y,   1)
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_BLOCK_Z,   1)
    # Launch: CTRL = 0x01 (launch bit, no irq_en)
    _emit_mmio_write(a, GPU_BASE, GPU_OFF_CTRL, 0x01)

    # Poll GPU_STATUS bit 1 (done) up to GPU_POLL_MAX times
    _emit_load_u32(a, 2, GPU_POLL_MAX)
    _emit_load_u32(a, 5, GPU_BASE + GPU_OFF_STATUS)
    a.label('GPU_POLL')
    a.emit(LW(4, 5, 0))
    a.emit(ANDI(4, 4, 2))                     # done bit is bit 1
    a.thunk(lambda lbl, pc: BNE(4, 0, lbl['GPU_DONE'] - pc))
    a.emit(ADDI(2, 2, -1))
    a.thunk(lambda lbl, pc: BEQ(2, 0, lbl['FAIL'] - pc))   # timeout
    a.thunk(lambda lbl, pc: JAL(0, lbl['GPU_POLL'] - pc))
    a.label('GPU_DONE')

    # Invalidate D-cache (flush GPU's writes back into CPU view)
    _emit_dcache_inval(a, spin=2048, r_cnt=2)

    # Verify GPU output: GPU_DST[l] == GPU_SRC[l] + 1
    _emit_load_u32(a, 3, GPU_SRC_BYTE)
    _emit_load_u32(a, 13, GPU_DST_BYTE)
    _emit_load_u32(a, 2, 0)
    a.label('GPU_VERIFY')
    a.emit(LW(4, 3, 0))                       # x4 = src[l]
    a.emit(LW(9, 13, 0))                      # x9 = dst[l]
    a.emit(ADDI(4, 4, 1))                     # x4 = src[l] + 1
    a.thunk(lambda lbl, pc: BEQ(4, 9, lbl['GPU_VERIFY_OK'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['FAIL'] - pc))
    a.label('GPU_VERIFY_OK')
    a.emit(ADDI(3, 3, 4))
    a.emit(ADDI(13, 13, 4))
    a.emit(ADDI(2, 2, 1))
    _emit_load_u32(a, 9, GPU_N_WORDS)
    a.thunk(lambda lbl, pc: BNE(2, 9, lbl['GPU_VERIFY'] - pc))

    # Update GPU_SRC so next iteration uses fresh data (GPU output → next input)
    # GPU_SRC[l] = GPU_DST[l] (already verified equal to old_src+1)
    # Just copy DST back to SRC
    _emit_load_u32(a, 3, GPU_SRC_BYTE)
    _emit_load_u32(a, 13, GPU_DST_BYTE)
    _emit_load_u32(a, 2, 0)
    a.label('GPU_SRC_UPDATE')
    a.emit(LW(4, 13, 0))
    a.emit(SW(4, 3, 0))
    a.emit(ADDI(3, 3, 4))
    a.emit(ADDI(13, 13, 4))
    a.emit(ADDI(2, 2, 1))
    _emit_load_u32(a, 9, GPU_N_WORDS)
    a.thunk(lambda lbl, pc: BNE(2, 9, lbl['GPU_SRC_UPDATE'] - pc))

    # store GPU mcycle delta
    a.emit(CSRRS(11, 0xB00, 0))
    a.emit(SUB(12, 11, 10))
    _emit_load_u32(a, 3, SRAM_BASE + BM_GPU_WI * 4)
    a.emit(SW(12, 3, 0))

    # ── [E] UART internal loopback ─────────────────────────────────────────────
    # Enable TX_EN|RX_EN|LOOPBACK: CTRL = 0x13 (bits 0,1,4)
    _emit_mmio_write(a, UART_BASE, UART_OFF_CTRL, UART_CTRL_EN_LOOPBACK)
    # Write TX byte to UART_TX register (offset 0x00)
    _emit_mmio_write(a, UART_BASE, UART_OFF_TX, UART_BYTE)
    # Poll STATUS[5] (rx_valid) up to PERIPH_POLL_MAX
    _emit_load_u32(a, 2, PERIPH_POLL_MAX)
    _emit_load_u32(a, 5, UART_BASE + UART_OFF_STATUS)
    a.label('UART_POLL')
    a.emit(LW(4, 5, 0))
    # UART_STAT_RX_VALID = 0x20 = 32. ANDI only takes signed 12-bit imm.
    # 0x20 = 32 fits fine; use ANDI directly.
    a.emit(ANDI(4, 4, 0x20))                  # rx_valid = STATUS[5] mask 0x20
    a.thunk(lambda lbl, pc: BNE(4, 0, lbl['UART_RX_READY'] - pc))
    a.emit(ADDI(2, 2, -1))
    a.thunk(lambda lbl, pc: BEQ(2, 0, lbl['FAIL'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['UART_POLL'] - pc))
    a.label('UART_RX_READY')
    # Read back RX byte from UART_RX register (offset 0x04)
    _emit_mmio_read(a, UART_BASE, UART_OFF_RX, 4)
    a.emit(ANDI(4, 4, 0xFF))                  # mask to 8 bits
    _emit_load_u32(a, 9, UART_BYTE)
    a.thunk(lambda lbl, pc: BEQ(4, 9, lbl['UART_OK'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['FAIL'] - pc))
    a.label('UART_OK')

    # ── [E'] SPI internal loopback ─────────────────────────────────────────────
    # Enable ENABLE|LOOPBACK: CTRL = 0x11 (bits 0,4)
    _emit_mmio_write(a, SPI_BASE, SPI_OFF_CTRL, SPI_CTRL_EN_LOOPBACK)
    # Write TX byte to SPI_TX register (offset 0x00)
    _emit_mmio_write(a, SPI_BASE, SPI_OFF_TX, SPI_BYTE)
    # Poll STATUS[4] (rx_valid): mask = 0x10
    _emit_load_u32(a, 2, PERIPH_POLL_MAX)
    _emit_load_u32(a, 5, SPI_BASE + SPI_OFF_STATUS)
    a.label('SPI_POLL')
    a.emit(LW(4, 5, 0))
    a.emit(ANDI(4, 4, 0x10))                  # rx_valid = STATUS[4] mask 0x10
    a.thunk(lambda lbl, pc: BNE(4, 0, lbl['SPI_RX_READY'] - pc))
    a.emit(ADDI(2, 2, -1))
    a.thunk(lambda lbl, pc: BEQ(2, 0, lbl['FAIL'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['SPI_POLL'] - pc))
    a.label('SPI_RX_READY')
    # Read back from SPI_RX register (offset 0x04)
    _emit_mmio_read(a, SPI_BASE, SPI_OFF_RX, 4)
    a.emit(ANDI(4, 4, 0xFF))
    _emit_load_u32(a, 9, SPI_BYTE)
    a.thunk(lambda lbl, pc: BEQ(4, 9, lbl['SPI_OK'] - pc))
    a.thunk(lambda lbl, pc: JAL(0, lbl['FAIL'] - pc))
    a.label('SPI_OK')

    # ── [F] Timer read ─────────────────────────────────────────────────────────
    _emit_mmio_read(a, TIMER_BASE, TIMER_OFF_CNT0, 4)
    _emit_load_u32(a, 3, SRAM_BASE + TIMER_WI * 4)
    a.emit(SW(4, 3, 0))

    # ── Iteration counter ──────────────────────────────────────────────────────
    _emit_load_u32(a, 3, SRAM_BASE + ITER_WI * 4)
    a.emit(LW(4, 3, 0))
    a.emit(ADDI(4, 4, 1))
    a.emit(SW(4, 3, 0))

    # ── Outer loop decrement ──────────────────────────────────────────────────
    a.emit(ADDI(1, 1, -1))                    # x1-- (outer iter count)
    a.thunk(lambda lbl, pc: BNE(1, 0, lbl['OUTER_LOOP'] - pc))

    # ── Flush D-cache before PASS so all scratch/benchmark SW writes are visible
    # to the cocotb backdoor SRAM read (which bypasses the D-cache).  Without
    # this flush, ITER_WI / BM_* / GPU_SRC / GPU_DST dirty lines remain in the
    # D-cache and SRAM still holds stale values when cocotb reads them.
    _emit_dcache_flush(a, spin=2048, r_cnt=2)

    # ── PASS ──────────────────────────────────────────────────────────────────
    a.label('PASS')
    a.emit(NOP)                                # PASS_PC lands here
    a.emit(EBREAK())

    # ── FAIL ──────────────────────────────────────────────────────────────────
    a.label('FAIL')
    a.emit(NOP)                                # FAIL_PC lands here
    a.emit(EBREAK())

    words = a.resolve()
    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} words > ROM_WORDS={ROM_WORDS}"
    )
    return words, a.labels


def write_hex(words: list, path: str) -> None:
    """Write words as a $readmemh-compatible hex file (one 8-hex-digit word per line)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        for w in words:
            f.write(f"{w:08x}\n")
        # Pad remainder with NOPs so $readmemh fills the entire ROM
        for _ in range(ROM_WORDS - len(words)):
            f.write(f"{NOP:08x}\n")


if __name__ == '__main__':
    out_dir = os.path.dirname(__file__)
    hex_path = os.path.join(out_dir, 'stress_fw.hex')
    addr_path = os.path.join(out_dir, 'stress_fw_addrs.py')

    words, labels = build_stress_fw()
    write_hex(words, hex_path)

    # Write address file
    pass_pc  = labels.get('PASS', 0)
    fail_pc  = labels.get('FAIL', 0)
    main_pc  = labels.get('MAIN', 0)
    outer_pc = labels.get('OUTER_LOOP', 0)

    with open(addr_path, 'w') as f:
        f.write("# Auto-generated by gen_stress_hex.py — do not edit.\n")
        f.write(f"PASS_PC       = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC       = 0x{fail_pc:08x}\n")
        f.write(f"MAIN_PC       = 0x{main_pc:08x}\n")
        f.write(f"OUTER_LOOP_PC = 0x{outer_pc:08x}\n")
        f.write(f"BM_CPU_WI     = {BM_CPU_WI}   # SRAM word index for CPU burst cycles\n")
        f.write(f"BM_DMA_WI     = {BM_DMA_WI}   # SRAM word index for DMA cycles\n")
        f.write(f"BM_GPU_WI     = {BM_GPU_WI}   # SRAM word index for GPU cycles\n")
        f.write(f"TIMER_WI      = {TIMER_WI}   # SRAM word index for timer snapshot\n")
        f.write(f"ITER_WI       = {ITER_WI}   # SRAM word index for iteration counter\n")
        f.write(f"STRESS_ITER   = {STRESS_ITER}\n")
        f.write(f"BURST_N_WORDS = {BURST_N_WORDS}\n")
        f.write(f"GPU_N_WORDS   = {GPU_N_WORDS}\n")
        f.write(f"BUF_A_WI      = {BUF_A_WI}\n")
        f.write(f"BUF_B_WI      = {BUF_B_WI}\n")
        f.write(f"GPU_SRC_WI    = {GPU_SRC_WI}\n")
        f.write(f"GPU_DST_WI    = {GPU_DST_WI}\n")
        f.write(f"KERNEL_WI     = {KERNEL_WI}\n")

    print(f"Generated: {hex_path}")
    print(f"Generated: {addr_path}")
    print(f"  PASS_PC = 0x{pass_pc:08x}")
    print(f"  FAIL_PC = 0x{fail_pc:08x}")
    print(f"  Firmware size: {len(words)} / {ROM_WORDS} words")
    print(f"  Outer iterations: {STRESS_ITER}")
