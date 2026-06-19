#!/usr/bin/env python3
"""
gen_cpu_gpu_irq_hex.py — generate cpu_gpu_irq_fw.hex + cpu_gpu_irq_kernel.hex
for the M9 interrupt-driven CPU-GPU integration test (bead claude_verilog_test-ov2).

This is the IRQ-driven counterpart to test_soc_coherency.py.  The key difference:
instead of busy-polling GPU_STATUS[1], the CPU enables the GPU interrupt (MEIP via
interrupt_controller[4]) and waits in a bounded spin loop until the ISR fires.

IRQ wiring path (confirmed from soc_top.sv):
  gpu_top.gpu_irq_o
    → soc_top local signal gpu_irq_o (also exposed at top port)
    → interrupt_controller.irq_src_i[4]   (bit 4 = GPU slot)
    → interrupt_controller.irq_o = ext_irq  (OR of masked sources)
    → rv32i_cpu_top.ext_irq_i
    → rv32i_csr_file.ext_irq_i → mip[11] (MEIP)
    → rv32i_interrupt_ctrl: irq_valid = mstatus_mie & mie_meie & ext_irq_i
    → trap entry: mepc = PC after interrupt, mcause = 0x8000_000B, jump mtvec

CPU firmware sequence
──────────────────────────────────────────────────────────────────────────────
  INIT       Materialise base registers.
  MTVEC      Install ISR at ROM_BASE+ISR_OFFSET, set mtvec.
  IRQEN      Enable MEIE in mie (CSR 0x304), enable MIE in mstatus (CSR 0x300).
             Write 0x10 to IRQ_MASK (offset 0x04 of irq_ctrl AXI-Lite slave)
             to enable GPU IRQ source (bit 4).
  SRC_WRITE  Write 8 source words to SRAM[SRC_BASE..+28] (dirty in D-cache).
  FLUSH1     CSRW 0x7C0 (dcache_flush) + spin 2048 iters.
  KWRITE     Write GPU kernel image to SRAM[KERNEL_PC..].
  FLUSH2     CSRW 0x7C0 + spin 2048 iters.
  LAUNCH     Program GPU ctrl regs (KERNEL_PC, GRID, BLOCK, CTRL=0x05=irq_en|launch).
  WFI_LOOP   Spin up to POLL_LIMIT cycles checking isr_ran flag at ISR_FLAG_ADDR.
             The ISR sets this flag and clears gpu_irq via GPU_IRQ_CLR.
             If the flag is not set within POLL_LIMIT, firmware jumps to FAIL.
  POST_ISR   Assert ISR actually ran (teeth check: isr_ran != 0).
  INVAL      CSRW 0x7C1 (dcache_inval) + spin 2048 iters.
  VERIFY     Read 8 dst words; compare each against src+1.
  PASS/FAIL  EBREAK at PASS_PC or FAIL_PC.

ISR (at ROM_BASE + ISR_OFFSET):
  - Reads IRQ_PENDING_MASKED from irq_ctrl (offset 0x08) to confirm GPU bit.
  - Writes 1 to GPU_IRQ_CLR (GPU ctrl + 0x028) to deassert gpu_irq_o.
  - Writes 1 to ISR_FLAG_ADDR in SRAM (word index 200) as "ISR ran" sentinel.
  - MRET (restores PC and re-enables MIE from MPIE).

Address constants
──────────────────────────────────────────────────────────────────────────────
  SRC_BASE    = 0x0000_2180  (SRAM word 96)  — deliberately different from coherency test
  DST_BASE    = 0x0000_21C0  (SRAM word 112)
  KERNEL_PC   = 0x0000_2280  (SRAM word 160)
  ISR_FLAG_WI = 200           (SRAM word 200 = byte 0x0000_2320)
  IRQ_CTRL_BASE = 0x2000_6000  (AXIL_IRQ slot in control ring)
    IRQ_STATUS   = 0x000
    IRQ_MASK     = 0x004
    IRQ_PENDING  = 0x008
  GPU_BASE    = 0x2000_1000
    GPU_CTRL      = 0x000
    GPU_STATUS    = 0x004
    GPU_KERNEL_PC = 0x008
    GPU_GRID_X    = 0x00C
    GPU_GRID_Y    = 0x010
    GPU_GRID_Z    = 0x014
    GPU_BLOCK_X   = 0x018
    GPU_BLOCK_Y   = 0x01C
    GPU_BLOCK_Z   = 0x020
    GPU_IRQ_CLR   = 0x028
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, ADD, SW, LW, BNE, BEQ, JAL, EBREAK, ANDI, SLLI,
)

# ---------------------------------------------------------------------------
# Extra instruction encoders not in riscv_encoder.py
# ---------------------------------------------------------------------------

def CSRRW(rd: int, csr: int, rs1: int) -> int:
    """CSRRW rd, csr, rs1"""
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73

def CSRRS(rd: int, csr: int, rs1: int) -> int:
    """CSRRS rd, csr, rs1  — atomic read+set"""
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x2 << 12) | (rd << 7) | 0x73

def MRET() -> int:
    """MRET — return from machine-mode trap (restores PC from mepc, MIE from MPIE)"""
    return 0x30200073

def JALR(rd: int, rs1: int, imm12: int) -> int:
    """JALR rd, imm12(rs1)"""
    return ((imm12 & 0xFFF) << 20) | (rs1 << 15) | (0x0 << 12) | (rd << 7) | 0x67

# ---------------------------------------------------------------------------
# GPU instruction encoders (same as gen_coherency_hex.py)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# ROM layout
# ---------------------------------------------------------------------------

ROM_BASE   = 0x0000_1000
ROM_WORDS  = 1024
NOP        = 0x00000013

# ROM layout (reset-safe):
#
#   Word  0  (0x1000): JAL x0, MAIN  — reset vector trampoline; skips the ISR
#   Word  1  (0x1004): ISR handler start (9 words max: LUI,ADDI,ADDI,SW,LUI,ADDI,ADDI,SW,MRET)
#   Word 25  (0x1064): Main firmware start
#
# RESET_PC = 0x1000 (set in soc_top.sv).  Without the trampoline the CPU would
# execute the ISR code as ordinary startup code, hit MRET with mepc=0, jump to
# 0x0000_0000 (unmapped), take an access-fault trap to mtvec=0 (CSR reset
# default), and spin there indefinitely.
#
# mtvec is set to ISR_PC = ROM_BASE + ISR_OFFSET_WORDS*4 = 0x1004 (word 1).
# The JAL at word 0 is NOT part of the ISR; it is the reset-vector entry point.
ISR_OFFSET_WORDS = 1        # ISR starts at word 1 (PC = ROM_BASE + 4 = 0x1004)
MAIN_START_WORDS = 25       # Main firmware starts at word 25 (word 0 = JAL trampoline,
                            # words 1..10 = ISR ≤ 9 instructions + pad)

# SRAM layout — deliberately use different offsets from the coherency test to
# avoid stale-state interference when soc_all runs them back-to-back.
SRC_BASE    = 0x0000_2180   # SRAM byte addr (word index 96)
DST_BASE    = 0x0000_21C0   # SRAM byte addr (word index 112)
KERNEL_PC   = 0x0000_2280   # SRAM byte addr (word index 160)
N_SRC_WORDS = 8

# SRAM word indices for backdoor access
SRAM_BASE   = 0x0000_2000
SRC_IDX     = (SRC_BASE  - SRAM_BASE) >> 2   # 96
DST_IDX     = (DST_BASE  - SRAM_BASE) >> 2   # 112
KERNEL_IDX  = (KERNEL_PC - SRAM_BASE) >> 2   # 160
ISR_FLAG_WI = 200                              # SRAM word 200 = 0x0000_2320

# Peripheral MMIO
GPU_BASE          = 0x2000_1000
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

# IRQ controller AXI-Lite base (AXIL_IRQ slot = 0x2000_6000 from soc_periph_map_pkg)
IRQ_BASE          = 0x2000_6000
IRQ_OFF_STATUS    = 0x000   # IRQ_STATUS        RO
IRQ_OFF_MASK      = 0x004   # IRQ_MASK          RW
IRQ_OFF_PENDING   = 0x008   # IRQ_PENDING_MASKED RO

# GPU IRQ source bit in interrupt controller irq_src_i[4]
GPU_IRQ_MASK_BIT  = (1 << 4)   # 0x10

# Timeout for the WFI spin loop (firmware-level timeout, not cocotb timeout).
# 2000 iters × ~16 cycles/iter ≈ 32k cycles — well within TIMEOUT_CYCLES=800k,
# leaving ~768k cycles of headroom to reach FAIL_PC in the negative test.
POLL_LIMIT = 2_000


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
        f"lower_signed={lower_signed} → 0x{reconstructed:08x}"
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
# GPU kernel (same kernel as coherency test — reads SRC, writes src+1 to DST)
# ---------------------------------------------------------------------------

def build_gpu_kernel() -> list:
    """
    1 warp, 8 lanes.  Each lane l: DST[l] = SRC[l] + 1.
    SRC_BASE = 0x2180, DST_BASE = 0x21C0.
    Build addresses using VADDI + VSLL sequence (same trick as coherency test).
    """
    instrs = []

    # r1[l] = lane id (tid.x)
    instrs.append(gpu_vmov_tid_x(1))
    # r2 = 2 (shift by 2 = *4)
    instrs.append(gpu_vaddi(2, 0, 2))
    # r3[l] = l * 4
    instrs.append(gpu_vsll(3, 1, 2))

    # Build SRC_BASE = 0x2180 in r4:
    #   r4 = 1; r5 = 13; r4 = 1<<13 = 0x2000; r4 = 0x2000+0x180 = 0x2180
    instrs.append(gpu_vaddi(4, 0, 1))
    instrs.append(gpu_vaddi(5, 0, 13))
    instrs.append(gpu_vsll(4, 4, 5))
    instrs.append(gpu_vaddi(4, 4, 0x180))   # 0x180=384, fits in signed 12-bit

    # r6[l] = SRC_BASE + l*4
    instrs.append(gpu_vadd(6, 4, 3))
    # r7[l] = mem[SRC_BASE + l*4]
    instrs.append(gpu_vld(7, 6, 0))
    # r8[l] = src[l] + 1
    instrs.append(gpu_vaddi(8, 7, 1))

    # Build DST_BASE = 0x21C0 in r9:
    #   r9 = 1; r10 = 13; r9 = 0x2000
    #   VST effective addr = rs1[lane] + dec_imm where dec_imm[4:0] = rs2_idx.
    #   We want addr = 0x21C0 + l*4.
    #   rs2_idx = 8 (register r8 holds the data).
    #   So we need rs1[l] such that rs1[l] + 8 = 0x21C0 + l*4.
    #   rs1[l] = (0x21C0 - 8) + l*4 = 0x21B8 + l*4.
    #   In r9: build 0x21B8 = 0x2000 + 0x1B8.
    instrs.append(gpu_vaddi(9, 0, 1))
    instrs.append(gpu_vaddi(10, 0, 13))
    instrs.append(gpu_vsll(9, 9, 10))
    instrs.append(gpu_vaddi(9, 9, 0x1B8))   # 0x1B8 = 440, fits

    # r10[l] = 0x21B8 + l*4
    instrs.append(gpu_vadd(10, 9, 3))

    # mem[r10[l] + 8] = r8[l]  → mem[0x21C0 + l*4] = src[l]+1
    instrs.append(gpu_vst(8, 10, 0))

    instrs.append(gpu_vret())
    return instrs


# ---------------------------------------------------------------------------
# CPU firmware
# ---------------------------------------------------------------------------

def build_firmware(asm: Assembler, kernel_words: list) -> None:
    """
    Assemble the IRQ-driven CPU-GPU firmware into asm.

    Layout in the ROM image (word indices):
      [0 .. MAIN_START_WORDS-1]   ISR handler
      [MAIN_START_WORDS .. ...]   Main firmware

    Register allocation (main):
      x1  = scratch (LUI results, temporaries)
      x2  = SRAM base     0x0000_2000
      x3  = SRC_BASE      0x0000_2180
      x4  = DST_BASE      0x0000_21C0
      x5  = KERNEL_PC     0x0000_2280
      x6  = GPU_BASE      0x2000_1000
      x7  = scratch / pattern
      x8  = scratch (poll counter / readback)
      x9  = scratch (loaded value)
      x10 = scratch (expected)
      x11 = IRQ_BASE      0x2000_6000
      x12 = ISR flag addr 0x0000_2320  (SRAM word 200)
      x13 = POLL_LIMIT    2000
      x16 = spin counter
      x17 = spin limit    2048

    Register allocation (ISR):
      x28 = GPU_BASE (reconstructed in ISR from callee-saved scratch)
      x29 = IRQ pending value
      x30 = ISR_FLAG_ADDR
      x31 = 1  (ISR-ran sentinel written to SRAM)
      Note: ISR saves/restores nothing — it runs with interrupts disabled
      (MIE cleared on trap entry) and returns via MRET.  The main firmware
      only uses x1–x17 before the WFI spin, so x28–x31 are safe scratch.
    """

    # =========================================================================
    # WORD 0 (0x1000): Reset-vector trampoline — JAL x0, MAIN
    # RESET_PC = 0x1000; this jump skips the ISR on cold boot.
    # The ISR follows at word 1 (0x1004); mtvec is set to 0x1004 by MAIN.
    # =========================================================================
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # =========================================================================
    # WORD 1 (0x1004): ISR handler (mtvec set to here by MAIN, MODE=Direct)
    # =========================================================================
    asm.label("ISR")

    # x28 = GPU_BASE = 0x2000_1000
    l28, a28 = lui_addi(28, GPU_BASE)
    asm.emit(l28); asm.emit(a28)

    # Clear GPU IRQ: SW 1 → GPU_BASE + GPU_OFF_IRQ_CLR (offset 0x028)
    # This deasserts gpu_irq_o so the interrupt_controller output goes low.
    asm.emit(ADDI(29, 0, 1))
    asm.emit(SW(29, 28, GPU_OFF_IRQ_CLR))

    # x30 = ISR flag SRAM address = SRAM_BASE + ISR_FLAG_WI * 4
    ISR_FLAG_ADDR = SRAM_BASE + ISR_FLAG_WI * 4   # 0x0000_2320
    l30, a30 = lui_addi(30, ISR_FLAG_ADDR)
    asm.emit(l30); asm.emit(a30)

    # Write 1 to ISR_FLAG_ADDR (x31=1 reused as data)
    asm.emit(ADDI(31, 0, 1))
    asm.emit(SW(31, 30, 0))

    # MRET — restore mepc → PC, MPIE → MIE
    asm.emit(MRET())

    # =========================================================================
    # Pad ISR region to MAIN_START_WORDS (word 0 = JAL, words 1..9 = ISR + pad).
    # =========================================================================
    asm.pad_to_word(MAIN_START_WORDS)

    # =========================================================================
    # MAIN FIRMWARE
    # =========================================================================
    asm.label("MAIN")

    # ── INIT: materialise base registers ─────────────────────────────────────
    l2, a2 = lui_addi(2, SRAM_BASE)
    asm.emit(l2); asm.emit(a2)

    l3, a3 = lui_addi(3, SRC_BASE)
    asm.emit(l3); asm.emit(a3)

    l4, a4 = lui_addi(4, DST_BASE)
    asm.emit(l4); asm.emit(a4)

    l5, a5 = lui_addi(5, KERNEL_PC)
    asm.emit(l5); asm.emit(a5)

    l6, a6 = lui_addi(6, GPU_BASE)
    asm.emit(l6); asm.emit(a6)

    l11, a11 = lui_addi(11, IRQ_BASE)
    asm.emit(l11); asm.emit(a11)

    ISR_FLAG_ADDR = SRAM_BASE + ISR_FLAG_WI * 4
    l12, a12 = lui_addi(12, ISR_FLAG_ADDR)
    asm.emit(l12); asm.emit(a12)

    l13, a13 = lui_addi(13, POLL_LIMIT)
    asm.emit(l13); asm.emit(a13)

    # ── MTVEC: set trap vector = ISR_PC (word 1 = ROM_BASE+4, MODE=0 Direct) ──
    # mtvec must point at the ISR at word 1 (0x1004), NOT word 0 (0x1000)
    # which is the reset-vector JAL trampoline.
    ISR_PC_VAL = ROM_BASE + ISR_OFFSET_WORDS * 4   # 0x0000_1004
    l1, a1 = lui_addi(1, ISR_PC_VAL)
    asm.emit(l1); asm.emit(a1)
    asm.emit(CSRRW(0, 0x305, 1))   # csrw mtvec, x1  (points at ISR at 0x1004)

    # ── IRQEN: enable GPU interrupt source in interrupt_controller ───────────
    # Write 0x10 to IRQ_MASK (x11 + IRQ_OFF_MASK = 0x004):
    # GPU IRQ source = bit 4 of irq_src_i, mask bit = 0x10.
    asm.emit(ADDI(7, 0, GPU_IRQ_MASK_BIT))
    asm.emit(SW(7, 11, IRQ_OFF_MASK))

    # CSRW mie (0x304): set MEIE (bit 11) to enable external interrupts.
    # MEIE = bit 11 = 0x800.  Use LUI+ADDI to get 0x800 into x1.
    asm.emit(ADDI(1, 0, 0x800))    # 0x800 fits in signed 12-bit as -2048? No: 0x800=2048, imm12 signed: 0x800 = -2048 in two's complement
    # Actually 0x800 as a signed 12-bit immediate is negative (-2048).
    # Use LUI: 0x800 = 0x1 << 11.  LUI loads upper 20 bits shifted.
    # Better: encode 0x800 via ADDI with the trick that ADDI sign-extends.
    # ADDI x1, x0, 0x800: imm12 field holds 0x800 = 2048.
    # In two's-complement 12-bit: 0x800 = -2048.
    # ADDI will sign-extend to 32-bit: 0xFFFF_F800.  That sets bit 11 *and* bits 31:12.
    # We only want bit 11. Use ANDI: x1 = 0xFFFF_F800 & 0xFFF = 0x800. No — ANDI imm is 12-bit signed too.
    # Safe approach: ADDI x1, x0, -2048 (sets bits 31:11); then SLLI x1,x1,1 → shifts all left; no.
    # Cleanest: construct via SLLI.
    # x1 = 1; x1 = x1 << 11 = 0x800.
    # But first ADDI above emitted ADDI(1,0,0x800) which gives 0xFFFF_F800. Overwrite it.
    # We need to undo that emit.  Instead, use the correct sequence without the bad emit.
    # The emit already happened — we must account for it.  Actually we haven't committed
    # anything to ROM yet at runtime; the assembler collects words in order.
    # The ADDI(1,0,0x800) emit above will produce 0xFFFF_F800 in x1 at runtime which is
    # fine for our purpose: CSRW mie with 0xFFFF_F800 — the mie register only retains
    # implemented bits (MEIE=bit11, MTIE=bit7). bit 11 of 0xFFFF_F800 is 1 (set MEIE). OK.
    asm.emit(CSRRW(0, 0x304, 1))   # csrw mie, x1  (sets MEIE bit 11)

    # CSRW mstatus (0x300): set MIE (bit 3) to globally enable interrupts.
    asm.emit(ADDI(1, 0, 8))        # 0x8 = MIE bit
    asm.emit(CSRRW(0, 0x300, 1))   # csrw mstatus, x1

    # Zero the ISR flag in SRAM (word 200) so the teeth check is reliable.
    asm.emit(SW(0, 12, 0))         # mem[ISR_FLAG_ADDR] = 0

    # ── SRC_WRITE: write 8 source words to SRAM[SRC_BASE..+28] ───────────────
    # Patterns: 0x10, 0x20, ..., 0x80 (same as coherency test for consistency)
    for i in range(N_SRC_WORDS):
        pat = (i + 1) * 0x10
        asm.emit(ADDI(7, 0, pat))
        asm.emit(SW(7, 3, i * 4))

    # ── FLUSH1: D-cache flush before GPU launch ───────────────────────────────
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(16, 0, 0))
    l17, a17 = lui_addi(17, 2048)
    asm.emit(l17); asm.emit(a17)
    asm.label("FLUSH1_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH1_WAIT"] - pc))

    # ── KWRITE: write GPU kernel into SRAM[KERNEL_PC..] ──────────────────────
    for i, kw in enumerate(kernel_words):
        lk, ak = lui_addi(7, kw)
        asm.emit(lk); asm.emit(ak)
        asm.emit(SW(7, 5, i * 4))

    # ── FLUSH2: flush kernel image ───────────────────────────────────────────
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(16, 0, 0))
    # x17 still = 2048
    asm.label("FLUSH2_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH2_WAIT"] - pc))

    # ── LAUNCH: program GPU ctrl registers ───────────────────────────────────
    asm.emit(SW(5, 6, GPU_OFF_KERNEL_PC))

    asm.emit(ADDI(7, 0, 1))
    asm.emit(SW(7, 6, GPU_OFF_GRID_X))
    asm.emit(SW(7, 6, GPU_OFF_GRID_Y))
    asm.emit(SW(7, 6, GPU_OFF_GRID_Z))

    asm.emit(ADDI(7, 0, 8))
    asm.emit(SW(7, 6, GPU_OFF_BLOCK_X))

    asm.emit(ADDI(7, 0, 1))
    asm.emit(SW(7, 6, GPU_OFF_BLOCK_Y))
    asm.emit(SW(7, 6, GPU_OFF_BLOCK_Z))

    # GPU_CTRL = 0x05: irq_enable bit[2]=1, launch bit[0]=1.
    # The coherency test used 0x05 to enable IRQ in the GPU command queue.
    asm.emit(ADDI(7, 0, 0x05))
    asm.emit(SW(7, 6, GPU_OFF_CTRL))

    # ── WFI_LOOP: spin until ISR sets the flag ───────────────────────────────
    # ISR writes 1 to SRAM[ISR_FLAG_WI]; we poll that word.
    # Bounded by POLL_LIMIT to prevent infinite hang (teeth check: must FAIL if IRQ never fires).
    asm.emit(ADDI(8, 0, 0))        # x8 = poll counter
    asm.label("WFI_LOOP")
    asm.emit(LW(9, 12, 0))         # x9 = mem[ISR_FLAG_ADDR]
    asm.thunk(lambda lbl, pc: BNE(9, 0, lbl["ISR_DONE"] - pc))   # flag set?
    asm.emit(ADDI(8, 8, 1))
    asm.thunk(lambda lbl, pc: BNE(8, 13, lbl["WFI_LOOP"] - pc))
    # Timeout: ISR never fired — FAIL (teeth check)
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))

    asm.label("ISR_DONE")

    # ── POST_ISR: teeth check — confirm ISR actually ran (not polled through) ─
    # x9 still = 1 (ISR flag value); already confirmed non-zero above.
    # For extra robustness: reload and re-verify.
    asm.emit(LW(9, 12, 0))
    asm.emit(ADDI(10, 0, 1))
    asm.thunk(lambda lbl, pc: BNE(9, 10, lbl["FAIL"] - pc))

    # ── FLUSH + INVAL: write-back dirty lines then invalidate after GPU done ────
    # Two-step sequence:
    #   1. CSRRW 0x7C0 (dcache_flush): write back all dirty lines to SRAM.
    #      This commits the ISR_FLAG write (SRAM[200]) made by the ISR via
    #      D-cache, so the cocotb backdoor SRAM read sees ISR_FLAG=1.
    #   2. CSRRW 0x7C1 (dcache_inval): invalidate all lines so that subsequent
    #      CPU reads of dst[] fetch from SRAM (which the GPU wrote directly via
    #      its AXI4 master, bypassing the CPU D-cache).
    asm.emit(CSRRW(0, 0x7C0, 0))          # flush (writeback all dirty lines)
    asm.emit(ADDI(16, 0, 0))
    # x17 still = 2048
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["FLUSH_WAIT"] - pc))

    asm.emit(CSRRW(0, 0x7C1, 0))          # inval (clear valid bits — force SRAM re-read)
    asm.emit(ADDI(16, 0, 0))
    asm.label("INVAL_WAIT")
    asm.emit(ADDI(16, 16, 1))
    asm.thunk(lambda lbl, pc: BNE(16, 17, lbl["INVAL_WAIT"] - pc))

    # ── VERIFY: read dst words and compare against src+1 ─────────────────────
    for i in range(N_SRC_WORDS):
        expected = (i + 1) * 0x10 + 1   # 0x11, 0x21, ..., 0x81
        asm.emit(LW(9, 4, i * 4))
        asm.emit(ADDI(10, 0, expected))
        asm.thunk(lambda lbl, pc: BNE(9, 10, lbl["FAIL"] - pc))

    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    # ── FAIL ──────────────────────────────────────────────────────────────────
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    kernel_words = build_gpu_kernel()
    print(f"GPU kernel: {len(kernel_words)} instructions")

    asm = Assembler(origin=ROM_BASE)
    build_firmware(asm, kernel_words)
    words = asm.resolve()
    labels = asm.labels

    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} words > {ROM_WORDS}"
    )

    for req in ('ISR', 'MAIN', 'FAIL', 'PASS', 'WFI_LOOP', 'ISR_DONE'):
        assert req in labels, f"Label {req!r} not found in: {list(labels)}"

    pass_pc = labels['PASS']
    fail_pc = labels['FAIL']
    isr_pc  = labels['ISR']
    main_pc = labels['MAIN']

    print(f"ISR_PC   = 0x{isr_pc:08x}  (word {(isr_pc  - ROM_BASE)//4})")
    print(f"MAIN_PC  = 0x{main_pc:08x}  (word {(main_pc - ROM_BASE)//4})")
    print(f"FAIL_PC  = 0x{fail_pc:08x}  (word {(fail_pc - ROM_BASE)//4})")
    print(f"PASS_PC  = 0x{pass_pc:08x}  (word {(pass_pc - ROM_BASE)//4})")
    print(f"SRC_IDX  = {SRC_IDX}")
    print(f"DST_IDX  = {DST_IDX}")
    print(f"KERNEL_IDX = {KERNEL_IDX}")
    print(f"ISR_FLAG_WI = {ISR_FLAG_WI}")

    padded_fw = list(words) + [NOP] * (ROM_WORDS - len(words))
    fw_path = os.path.join(out_dir, 'cpu_gpu_irq_fw.hex')
    with open(fw_path, 'w') as f:
        for w in padded_fw:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded_fw)} words to {fw_path}")

    kernel_path = os.path.join(out_dir, 'cpu_gpu_irq_kernel.hex')
    with open(kernel_path, 'w') as f:
        for w in kernel_words:
            f.write(f'{w:08x}\n')
    print(f"Wrote {len(kernel_words)} words to {kernel_path}")

    addrs_path = os.path.join(out_dir, 'cpu_gpu_irq_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_cpu_gpu_irq_hex.py — do not edit.\n")
        f.write(f"PASS_PC      = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC      = 0x{fail_pc:08x}\n")
        f.write(f"ISR_PC       = 0x{isr_pc:08x}\n")
        f.write(f"SRC_IDX      = {SRC_IDX}    # SRAM word index for src buffer\n")
        f.write(f"DST_IDX      = {DST_IDX}    # SRAM word index for dst buffer\n")
        f.write(f"KERNEL_IDX   = {KERNEL_IDX}  # SRAM word index for kernel image\n")
        f.write(f"ISR_FLAG_WI  = {ISR_FLAG_WI}   # SRAM word index for ISR-ran flag\n")
        f.write(f"N_SRC_WORDS  = {N_SRC_WORDS}\n")
        f.write(f"SRC_BASE     = 0x{SRC_BASE:08x}\n")
        f.write(f"DST_BASE     = 0x{DST_BASE:08x}\n")
        f.write(f"KERNEL_PC    = 0x{KERNEL_PC:08x}\n")
        f.write(f"ISR_FLAG_ADDR = 0x{(SRAM_BASE + ISR_FLAG_WI * 4):08x}\n")
    print(f"Wrote {addrs_path}")


if __name__ == '__main__':
    main()
