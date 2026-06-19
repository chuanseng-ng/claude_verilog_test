#!/usr/bin/env python3
"""
gen_coherency_hex.py — generate coherency_fw.hex + kernel.hex for the M9
software-managed-coherency test (bead claude_verilog_test-777).

Two separate images are produced:

  1. coherency_fw.hex   — CPU firmware loaded into boot ROM @ 0x0000_1000
  2. coherency_kernel.hex — GPU kernel loaded by the firmware into SRAM @ KERNEL_PC

CPU firmware sequence
──────────────────────────────────────────────────────────────────────
 [A] Write 8 source words  SRAM[SRC_BASE..SRC_BASE+28]    (cacheable)
 [B] CSRW 0x7C0 (dcache_flush)  + spin 2048 iters          (flush dirty lines)
 [C] Write GPU kernel image into SRAM[KERNEL_PC..] via SW   (also cacheable)
 [D] CSRW 0x7C0 (dcache_flush)  + spin 2048 iters          (flush kernel image)
 [E] Program GPU ctrl registers (KERNEL_PC, GRID_X, BLOCK_X, CTRL=launch)
 [F] Poll GPU_STATUS[1] (done bit) up to POLL_LIMIT iters
 [G] CSRW 0x7C1 (dcache_inval) + spin 2048 iters           (drop stale cached copies)
 [H] Load 8 dst words + compare against expected (src+1)
 [I] Jump to PASS / FAIL

GPU kernel (1 warp, 8 lanes)
──────────────────────────────────────────────────────────────────────
  vmov_tid_x  r1          # r1[l] = lane id l (0..7)
  vsll        r2, r1, 2   # r2[l] = l * 4  (byte stride)
  vaddi       r3, r0, SRC_LO  # r3[l] = SRC_BASE (lo12)  ← x0 base + imm
  # For addresses > 12-bit imm, we pre-load via a scalar instruction in the
  # firmware and pass via ARG_PTR. But SRAM base 0x0000_2000 fits in 12 bits
  # only if upper bits are 0 — gpu_pkg encodes I-type with 12-bit signed imm.
  # 0x2000 = 8192 = 0b0010_0000_0000_0000. As signed 12-bit: overflows (>2047).
  #
  # Solution: use GPU_ARG_PTR register (0x2000_1024) to pass SRC_BASE and
  # DST_BASE. But the GPU uses VLD/VST with base+imm; we need the base in a
  # vector register.  Since all lanes share the same base, we broadcast it
  # using VADDI r_base, x0, 0 with the upper bits pre-loaded via a second
  # ARG_PTR word — this is complex for a simple kernel.
  #
  # Simpler: use SRAM addresses near 0x0000_2000 that are accessible with
  # a 12-bit unsigned offset from x0 — but 0x2000 = 8192 > 2047 signed max.
  #
  # The right approach for the SoC level: place src and dst at the start of
  # SRAM (0x0000_2000...) and encode base as a two-step GPU VLD: load a
  # "pointer" word from a known small address into a register, then use that.
  # But GPU has no indirect VLD-from-register-of-addresses.
  #
  # Simplest working approach: place SRC at SRAM offset 0 (byte addr 0x2000)
  # and use ARG_PTR to hold the base.  The GPU kernel reads arg_ptr via a
  # special VMOV_SPECIAL encoding (SREG_ARG_PTR).  In Phase 4 ISA this is
  # actually not available — the VMOV_SPECIAL only covers tid/bid.
  #
  # Pragmatic resolution: offset SRC to a lower SRAM address that fits in a
  # signed 12-bit immediate from 0 — not possible since SRAM starts at 0x2000.
  #
  # FINAL APPROACH: Use VADDI with a two-instruction LUI-style sequence.
  # GPU instruction set has no LUI. But VADDI imm is 12-bit signed so max is
  # 0x7FF=2047. SRAM starts at 0x2000=8192 which does not fit.
  #
  # The only clean solution is to pass the base address via a pre-loaded
  # scalar register broadcast using a VADDI chain on x0:
  #   vaddi r3, x0, upper_part * 2048 -- not possible, no shift-immediate
  #
  # Therefore: use a 2-instruction sequence with VST/VLD of a "constant" stored
  # at the beginning of the ROM (0x1000 range) — also > 2047 so same problem.
  #
  # ROOT CAUSE: GPU I-type imm is 12 bits. SRAM @ 0x2000 cannot be reached
  # from x0. Resolution: store BASE_SRC / BASE_DST as literal constants in
  # SRAM word 0 (byte 0x2000) and SRAM word 1 (byte 0x2004) before launching,
  # then GPU VLD word-0 → r_src_base, VLD word-1 → r_dst_base.
  # With GPU r_base = mem[0x2000] = SRC_BASE and r_dst = mem[0x2004] = DST_BASE.
  # But VLD base must also be a register — and we're back to needing 0x2000 in r.
  #
  # THE REAL SOLUTION: The GPU instruction VLD/VST encodes  addr = rs1 + imm.
  # We need rs1 to hold 0x2000.  In RISC-V style: use VADDI r1, x0, 0 then
  # shift — but no shift-immediate in GPU ISA for scalars.
  # However: VADDI with imm=0 + VSLL can get powers-of-2 starting from small
  # values. 0x2000 = 8192 = 2^13.  Via VSLL 13 times from 1 ... or in one
  # shot: vaddi r1,x0,1 then vsll r1,r1,13 (shift by 13).
  # VSLL rd, rs1, rs2 — rs2 is a register, not immediate.
  # vaddi r2, x0, 13; vsll r1, r1, r2 — YES, this works.

Address constants for the firmware and kernel:
  SRC_BASE   = 0x0000_2100  (SRAM word index 64)
  DST_BASE   = 0x0000_2140  (SRAM word index 80)
  KERNEL_PC  = 0x0000_2200  (SRAM word index 128)

  SRC_BASE = 0x2100 = 8448.  1 + 0x2100:
    vaddi r5, x0, 1   # r5 = 1
    vaddi r6, x0, 13  # r6 = 13 (shift amount)
    vsll  r5, r5, r6  # r5 = 0x2000
    vaddi r5, r5, 0x100  # r5 = 0x2100  (imm=256, fits in 12 bits)
  Similarly DST_BASE = 0x2140:
    (copy r5 to r7 using vaddi r7,r5,0)
    vaddi r7, r5, 0x40   # r7 = 0x2140

  GPU kernel (VLD-VADDI-VST per lane):
    vmov_tid_x r1        # r1[l] = l
    vaddi r2, x0, 2      # r2 = 2 (shift by 2 = multiply by 4)
    vsll  r3, r1, r2     # r3[l] = l*4
    vaddi r4, x0, 1      # r4 = 1 (base calc: shift by 13 = 0x2000)
    vaddi r5, x0, 13     # r5 = 13
    vsll  r4, r4, r5     # r4 = 0x2000
    vaddi r4, r4, 0x100  # r4 = 0x2100 = SRC_BASE (imm 256 OK)
    vadd  r6, r4, r3     # r6[l] = SRC_BASE + l*4
    vld   r7, r6, 0      # r7[l] = mem[SRC_BASE + l*4]
    vaddi r8, r7, 1      # r8[l] = r7[l] + 1
    vaddi r9, x0, 1      # r9 = 1
    vaddi r10, x0, 13    # r10 = 13
    vsll  r9, r9, r10    # r9 = 0x2000
    vaddi r9, r9, 0x140  # r9 = 0x2140 = DST_BASE (imm 320 OK)
    vadd  r10, r9, r3    # r10[l] = DST_BASE + l*4
    vst   r8, r10, 0     # mem[DST_BASE + l*4] = r8[l]
    vret

  14 instructions. Lane 0 reads 0x2100, writes 0x2140 (expected = src+1).

GPU register allocation:
  r0  = x0 (always 0)
  r1  = lane id (tid.x)
  r2  = shift amount for byte stride
  r3  = byte offset (lane * 4)
  r4  = src base ptr
  r5  = shift amount 13
  r6  = src element address
  r7  = loaded src value
  r8  = result (src + 1)
  r9  = dst base ptr
  r10 = dst element address
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, ADD, SW, LW, BNE, BEQ, JAL, EBREAK, ANDI,
)

# ---------------------------------------------------------------------------
# GPU instruction encoders (from gpu_pkg.sv opcode table)
# ---------------------------------------------------------------------------

def _r_instr(opcode7: int, rd: int, rs1: int, rs2: int, funct3: int = 0, funct7: int = 0) -> int:
    return ((funct7 & 0x7F) << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | \
           ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | (opcode7 & 0x7F)

def _i_instr(opcode7: int, rd: int, rs1: int, imm12: int, funct3: int = 0) -> int:
    imm = imm12 & 0xFFF
    return (imm << 20) | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) | \
           ((rd & 0x1F) << 7) | (opcode7 & 0x7F)

def _s_instr(opcode7: int, rs1: int, rs2: int, imm12: int, funct3: int = 0) -> int:
    imm = imm12 & 0xFFF
    imm_hi = (imm >> 5) & 0x7F
    imm_lo = imm & 0x1F
    return (imm_hi << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | \
           ((funct3 & 0x7) << 12) | (imm_lo << 7) | (opcode7 & 0x7F)

# GPU opcodes from gpu_pkg.sv
_OP_VADD        = 0x01  # gpu_pkg.sv VADD    = 7'h01
_OP_VSLL        = 0x07  # gpu_pkg.sv VSLL    = 7'h07
_OP_VADDI       = 0x11  # gpu_pkg.sv VADDI   = 7'h11
_OP_VLD         = 0x20  # gpu_pkg.sv VLD     = 7'h20
_OP_VST         = 0x21  # gpu_pkg.sv VST     = 7'h21
_OP_VRET        = 0x3F  # gpu_pkg.sv VRET    = 7'h3F
_OP_VMOV_TID_X  = 0x40  # gpu_pkg.sv VMOV_TID_X = 7'h40

def gpu_vmov_tid_x(rd: int) -> int:
    """VMOV rd, tid.x — I-type, rs1=0, imm=0"""
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
    # GPU RTL decodes dec_imm = instr[31:20] and dec_rs2 = instr[24:20].
    # These share the same 5 bits: dec_imm[4:0] == dec_rs2 == rs2_data index.
    # The RTL effective store address is: rs1_base[lane] + sign_extend(dec_imm)
    # where dec_imm = {imm[11:5], rs2_data_index}.
    # Must bake rs2_data index into imm[4:0] and put base_offset in imm[11:5].
    # This matches the encoding used by gpu_asm.py vst().
    imm = (base_offset & ~0x1F) | (rs2_data & 0x1F)
    return (imm << 20) | ((rs1_base & 0x1F) << 15) | _OP_VST

def gpu_vret() -> int:
    return _i_instr(_OP_VRET, 0, 0, 0)

# ---------------------------------------------------------------------------
# RV32I firmware helpers (reuse periph_fw pattern)
# ---------------------------------------------------------------------------

ROM_BASE   = 0x0000_1000
ROM_WORDS  = 1024
NOP        = 0x00000013

# Address constants
SRC_BASE   = 0x0000_2100   # SRAM byte addr (word index 64)
DST_BASE   = 0x0000_2140   # SRAM byte addr (word index 80)
KERNEL_PC  = 0x0000_2200   # SRAM byte addr (word index 128)
N_SRC_WORDS = 8

# SRAM word indices for backdoor check
SRC_IDX    = (SRC_BASE - 0x2000) >> 2   # = 64
DST_IDX    = (DST_BASE - 0x2000) >> 2   # = 80
KERNEL_IDX = (KERNEL_PC - 0x2000) >> 2  # = 128

# GPU AXI-Lite control base (0x2000_1000)
GPU_BASE   = 0x2000_1000
# GPU register offsets
GPU_OFF_CTRL      = 0x000
GPU_OFF_STATUS    = 0x004
GPU_OFF_KERNEL_PC = 0x008
GPU_OFF_GRID_X    = 0x00C
GPU_OFF_GRID_Y    = 0x010
GPU_OFF_GRID_Z    = 0x014
GPU_OFF_BLOCK_X   = 0x018
GPU_OFF_BLOCK_Y   = 0x01C
GPU_OFF_BLOCK_Z   = 0x020
GPU_OFF_ARG_PTR   = 0x024
GPU_OFF_IRQ_CLR   = 0x028

def CSRRW(rd: int, csr: int, rs1: int) -> int:
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73


def lui_addi(rd: int, value32: int):
    """Return (lui_word, addi_word) for rd = value32."""
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}): upper=0x{upper20:05x} "
        f"lower_signed={lower_signed} → 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


class Assembler:
    """Two-pass label assembler (same as periph_fw pattern)."""
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
            w = val(self.labels, cur_pc) & 0xFFFF_FFFF if typ == 'thunk' else val
            words.append(w)
            idx += 1
        return words


# ---------------------------------------------------------------------------
# GPU kernel builder
# ---------------------------------------------------------------------------
def build_gpu_kernel() -> list:
    """
    Build GPU kernel machine code.

    1 warp, 8 lanes.
    Each lane l: dst[l] = src[l] + 1
      src[l] = mem[SRC_BASE + l*4]
      dst[l] = mem[DST_BASE + l*4]

    Returns list of 32-bit instruction words.
    """
    instrs = []

    # r1[l] = lane id (tid.x)
    instrs.append(gpu_vmov_tid_x(1))

    # r2 = 2 (shift amount for *4)
    instrs.append(gpu_vaddi(2, 0, 2))

    # r3[l] = l * 4  (byte offset)
    instrs.append(gpu_vsll(3, 1, 2))

    # Build SRC_BASE = 0x2100 in r4:
    # r4 = 1
    instrs.append(gpu_vaddi(4, 0, 1))
    # r5 = 13
    instrs.append(gpu_vaddi(5, 0, 13))
    # r4 = 1 << 13 = 0x2000
    instrs.append(gpu_vsll(4, 4, 5))
    # r4 = 0x2000 + 0x100 = 0x2100  (imm=256, fits in 12-bit signed: 256 < 2048)
    instrs.append(gpu_vaddi(4, 4, 0x100))

    # r6[l] = SRC_BASE + l*4
    instrs.append(gpu_vadd(6, 4, 3))

    # r7[l] = mem[r6[l] + 0]  = src[l]
    instrs.append(gpu_vld(7, 6, 0))

    # r8[l] = src[l] + 1
    instrs.append(gpu_vaddi(8, 7, 1))

    # Build DST_BASE = 0x2140 in r9:
    # r9 = 1
    instrs.append(gpu_vaddi(9, 0, 1))
    # r10 = 13
    instrs.append(gpu_vaddi(10, 0, 13))
    # r9 = 0x2000
    instrs.append(gpu_vsll(9, 9, 10))
    # r9 = 0x2000 + 0x138 = 0x2138  (DST_BASE - rs2_idx = 0x2140 - 8)
    # RTL VST effective addr = rs1[lane] + dec_imm where dec_imm[4:0] = rs2_idx = 8.
    # So addr = (r10[lane]) + 8 = (r9 + l*4) + 8 = (0x2138 + l*4) + 8 = 0x2140 + l*4.
    instrs.append(gpu_vaddi(9, 9, 0x138))

    # r10[l] = DST_BASE + l*4
    instrs.append(gpu_vadd(10, 9, 3))

    # mem[r10[l]] = r8[l]
    instrs.append(gpu_vst(8, 10, 0))

    # Done
    instrs.append(gpu_vret())

    return instrs


# ---------------------------------------------------------------------------
# CPU firmware builder
# ---------------------------------------------------------------------------
def build_firmware(asm: Assembler, kernel_words: list):
    """
    Populate assembler with the self-checking coherency firmware.

    Register allocation:
      x2  = SRAM base      0x0000_2000
      x3  = SRC base       0x0000_2100
      x4  = DST base       0x0000_2140
      x5  = KERNEL_PC      0x0000_2200
      x6  = GPU base       0x2000_1000
      x7  = scratch / pattern
      x8  = scratch / poll counter
      x9  = scratch / readback
      x10 = scratch (comparison)
      x11 = loop counter
      x12 = loop limit
      x13 = poll limit    (50000)
      x14 = word index (0..7)
      x15 = byte offset   (x14 * 4)
      x16 = spin counter  (flush wait)
      x17 = spin limit    (2048)
    """

    # ── Prologue: materialise base registers ──────────────────────────────────
    # x2 = 0x0000_2000
    l2, a2 = lui_addi(2, 0x0000_2000)
    asm.emit(l2); asm.emit(a2)

    # x3 = SRC_BASE = 0x0000_2100
    l3, a3 = lui_addi(3, SRC_BASE)
    asm.emit(l3); asm.emit(a3)

    # x4 = DST_BASE = 0x0000_2140
    l4, a4 = lui_addi(4, DST_BASE)
    asm.emit(l4); asm.emit(a4)

    # x5 = KERNEL_PC = 0x0000_2200
    l5, a5 = lui_addi(5, KERNEL_PC)
    asm.emit(l5); asm.emit(a5)

    # x6 = GPU_BASE = 0x2000_1000
    l6, a6 = lui_addi(6, GPU_BASE)
    asm.emit(l6); asm.emit(a6)

    # x13 = 50000  (poll limit)
    l13, a13 = lui_addi(13, 50000)
    asm.emit(l13); asm.emit(a13)

    # ── Step A: Write 8 source words to SRAM[SRC_BASE..SRC_BASE+28] ──────────
    # Patterns: 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80
    # (small positive ints; each fits in ADDI immediate)
    for i in range(N_SRC_WORDS):
        pat = (i + 1) * 0x10   # 0x10, 0x20 … 0x80
        asm.emit(ADDI(7, 0, pat))
        asm.emit(SW(7, 3, i * 4))  # SW x7, i*4(x3)

    # ── Step B: D-cache flush #1 — flush source words to SRAM ─────────────────
    # CSRW 0x7C0, x0 → fires dc_flush_i pulse in rv32i_csr_file
    asm.emit(CSRRW(0, 0x7C0, 0))

    # Spin 2048 iterations to let CS_FLUSH_SCAN complete
    # (256 lines × ~2 cycles/line = ~512 cycles; 2048 iters × 3 cyc = 6144 cyc)
    asm.emit(ADDI(16, 0, 0))         # x16 = 0
    l17, a17 = lui_addi(17, 2048)
    asm.emit(l17); asm.emit(a17)
    asm.label("FLUSH1_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH1_WAIT"] - pc))

    # ── Step C: Write GPU kernel image into SRAM[KERNEL_PC..] ─────────────────
    # x5 already = KERNEL_PC
    for i, kw in enumerate(kernel_words):
        # Load kw into x7 using LUI+ADDI then store
        lk, ak = lui_addi(7, kw)
        asm.emit(lk); asm.emit(ak)
        asm.emit(SW(7, 5, i * 4))   # SW x7, i*4(x5)

    # ── Step D: D-cache flush #2 — flush kernel image to SRAM ────────────────
    asm.emit(CSRRW(0, 0x7C0, 0))

    asm.emit(ADDI(16, 0, 0))
    # x17 already = 2048 from step B; reuse
    asm.label("FLUSH2_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH2_WAIT"] - pc))

    # ── Step E: Program and launch GPU ───────────────────────────────────────
    # GPU_KERNEL_PC = KERNEL_PC (x5 = 0x0000_2200)
    asm.emit(SW(5, 6, GPU_OFF_KERNEL_PC))    # offset 0x008

    # GPU_GRID_X = 1 (one block)
    asm.emit(ADDI(7, 0, 1))
    asm.emit(SW(7, 6, GPU_OFF_GRID_X))       # offset 0x00C

    # GPU_GRID_Y = 1
    asm.emit(SW(7, 6, GPU_OFF_GRID_Y))       # offset 0x010

    # GPU_GRID_Z = 1
    asm.emit(SW(7, 6, GPU_OFF_GRID_Z))       # offset 0x014

    # GPU_BLOCK_X = 8 (8 lanes = 1 warp)
    asm.emit(ADDI(7, 0, 8))
    asm.emit(SW(7, 6, GPU_OFF_BLOCK_X))      # offset 0x018

    # GPU_BLOCK_Y = 1
    asm.emit(ADDI(7, 0, 1))
    asm.emit(SW(7, 6, GPU_OFF_BLOCK_Y))      # offset 0x01C

    # GPU_BLOCK_Z = 1
    asm.emit(SW(7, 6, GPU_OFF_BLOCK_Z))      # offset 0x020

    # GPU_CTRL = 0x05 (irq_enable[2]=1, launch[0]=1)
    asm.emit(ADDI(7, 0, 0x05))
    asm.emit(SW(7, 6, GPU_OFF_CTRL))         # offset 0x000

    # ── Step F: Poll GPU_STATUS[1] = done ─────────────────────────────────────
    asm.emit(ADDI(8, 0, 0))    # x8 = poll counter
    asm.label("GPU_POLL")
    asm.emit(LW(9, 6, GPU_OFF_STATUS))       # x9 = GPU_STATUS (offset 0x004)
    asm.emit(ANDI(9, 9, 2))                  # isolate done bit[1]
    asm.thunk(lambda lbl, pc: BNE(9, 0, lbl["GPU_DONE"] - pc))
    asm.emit(ADDI(8, 8, 1))
    asm.thunk(lambda lbl, pc: BNE(8, 13, lbl["GPU_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))
    asm.label("GPU_DONE")

    # Clear GPU IRQ (write 1 to GPU_IRQ_CLR[0])
    asm.emit(ADDI(7, 0, 1))
    asm.emit(SW(7, 6, GPU_OFF_IRQ_CLR))      # offset 0x028

    # ── Step G: D-cache invalidate — drop stale cached copies ─────────────────
    # CSRW 0x7C1, x0 → fires dc_inval_i pulse in rv32i_csr_file
    asm.emit(CSRRW(0, 0x7C1, 0))

    asm.emit(ADDI(16, 0, 0))
    # x17 still = 2048
    asm.label("INVAL_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["INVAL_WAIT"] - pc))

    # ── Step H: Read dst words and compare against src+1 ─────────────────────
    # Load and compare 8 words: dst[i] == src[i] + 1 == (i+1)*0x10 + 1
    for i in range(N_SRC_WORDS):
        expected = (i + 1) * 0x10 + 1    # 0x11, 0x21, ..., 0x81
        asm.emit(LW(9, 4, i * 4))        # x9 = dst[i]
        asm.emit(ADDI(10, 0, expected))   # x10 = expected
        asm.thunk(lambda lbl, pc: BNE(9, 10, lbl["FAIL"] - pc))

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    # ── FAIL ──────────────────────────────────────────────────────────────────
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))   # x31 = -1
    asm.emit(EBREAK())

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))    # x31 = 1
    asm.emit(EBREAK())


def print_listing(words: list, labels: dict, name: str = ""):
    pc_to_label = {v: k for k, v in labels.items()}
    print(f"\n=== {name} Firmware Listing ===")
    print(f"{'PC':>10}  {'Word':>10}  Annotation")
    print("-" * 60)
    for i, w in enumerate(words):
        if w == NOP and i >= 100:
            break
        pc = ROM_BASE + i * 4
        lbl = f"<{pc_to_label[pc]}>" if pc in pc_to_label else ""
        print(f"0x{pc:08x}  0x{w:08x}  {lbl}")
    print()


def print_gpu_listing(words: list):
    print("\n=== GPU Kernel Listing ===")
    print(f"{'PC':>10}  {'Word':>10}")
    print("-" * 30)
    for i, w in enumerate(words):
        pc = KERNEL_PC + i * 4
        print(f"0x{pc:08x}  0x{w:08x}")
    print()


if __name__ == '__main__':
    out_dir = os.path.dirname(os.path.abspath(__file__))

    # Build GPU kernel
    kernel_words = build_gpu_kernel()
    print_gpu_listing(kernel_words)
    print(f"GPU kernel: {len(kernel_words)} instructions")

    # Build CPU firmware
    asm = Assembler()
    build_firmware(asm, kernel_words)
    words = asm.resolve()
    labels = asm.labels

    print_listing(words, labels, "Coherency")

    # Verify required labels
    for req in ('FAIL', 'PASS', 'FLUSH1_WAIT', 'FLUSH2_WAIT',
                'GPU_POLL', 'GPU_DONE', 'INVAL_WAIT'):
        assert req in labels, f"Label {req!r} not found in: {list(labels)}"

    pass_pc = labels['PASS']
    fail_pc = labels['FAIL']
    print(f"PASS_PC = 0x{pass_pc:08x}  (word {(pass_pc - ROM_BASE)//4})")
    print(f"FAIL_PC = 0x{fail_pc:08x}  (word {(fail_pc - ROM_BASE)//4})")

    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} words > {ROM_WORDS}"
    )

    # Pad and write firmware hex
    padded_fw = list(words) + [NOP] * (ROM_WORDS - len(words))
    fw_path = os.path.join(out_dir, 'coherency_fw.hex')
    with open(fw_path, 'w') as f:
        for w in padded_fw:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded_fw)} words to {fw_path}")

    # Write kernel hex (not padded — loaded word-by-word by firmware SW)
    kernel_path = os.path.join(out_dir, 'coherency_kernel.hex')
    with open(kernel_path, 'w') as f:
        for w in kernel_words:
            f.write(f'{w:08x}\n')
    print(f"Wrote {len(kernel_words)} words to {kernel_path}")

    # Write coherency_fw_addrs.py
    addrs_path = os.path.join(out_dir, 'coherency_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_coherency_hex.py — do not edit.\n")
        f.write(f"PASS_PC      = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC      = 0x{fail_pc:08x}\n")
        f.write(f"SRC_IDX      = {SRC_IDX}    # SRAM word index for src buffer\n")
        f.write(f"DST_IDX      = {DST_IDX}    # SRAM word index for dst buffer\n")
        f.write(f"KERNEL_IDX   = {KERNEL_IDX}  # SRAM word index for kernel image\n")
        f.write(f"N_SRC_WORDS  = {N_SRC_WORDS}\n")
        f.write(f"SRC_BASE     = 0x{SRC_BASE:08x}\n")
        f.write(f"DST_BASE     = 0x{DST_BASE:08x}\n")
        f.write(f"KERNEL_PC    = 0x{KERNEL_PC:08x}\n")
    print(f"Wrote {addrs_path}")
    print(f"  PASS_PC     = 0x{pass_pc:08x}")
    print(f"  FAIL_PC     = 0x{fail_pc:08x}")
    print(f"  SRC_IDX     = {SRC_IDX}")
    print(f"  DST_IDX     = {DST_IDX}")
    print(f"  KERNEL_IDX  = {KERNEL_IDX}")
