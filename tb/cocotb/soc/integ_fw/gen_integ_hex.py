#!/usr/bin/env python3
"""
gen_integ_hex.py -- firmware images for the SoC-level integration suite
(test_soc_integration.py, bead claude_verilog_test-oez2).

One generator, three ROM images, all in the repo's existing hand-assembled style
(two-pass label assembler + sim/riscv_encoder.py, same JAL trampoline + ISR-at-word-1
layout as gpio_fw / cpu_gpu_irq_fw).  Every image is self-checking: it branches to
FAIL (x31=-1, EBREAK) on any mismatch and ends at PASS (x31=1, EBREAK); the cocotb
test scoreboards commit_pc_o for the marker PCs written to integ_fw_addrs.py.

IMAGE 1  irq_spi.hex -- one interrupt phase per peripheral, CPU actually takes the trap
  Phase 1 TIMER : timer (APB4 0x2000_4000) -> timer_irq -> CPU MTIP DIRECT (it is NOT an
                  interrupt_controller source; irq_src_i[2] is tied 0), mcause 0x8000_0007.
  Phase 2 UART  : loopback TX 0xA5, irq_rx_valid_en -> uart_irq -> interrupt_controller[0]
                  -> ext_irq -> MEIP, mcause 0x8000_000B.  Handler pops RX.
  Phase 3 SPI   : NON-loopback, CPOL=CPHA=0, CS asserted via SPI_CS_CTRL, TX 0x3C.  The
                  testbench's SPI slave model drives spi_miso_i with 0xA6 (this is the
                  suite's only spi_miso_i stimulus); irq_done_en -> spi_irq ->
                  interrupt_controller[1].  Handler pops RX, which must read 0xA6.
  Phase 4 DMA   : 16-byte copy with CTRL.irq_en -> dma_irq -> interrupt_controller[3].
                  Handler soft-resets the engine (CTRL[2]), the only way to clear the
                  sticky IRQ_STATUS.
  The ISR is generic and phase-driven: it logs mcause, the interrupt_controller
  IRQ_PENDING_MASKED value and (UART/SPI) the popped RX byte into SRAM slots indexed by
  the PHASE word, clears the source, sets FLAG and bumps COUNT.  MAIN then checks COUNT ==
  phase (a stuck-asserted line would re-vector and bump COUNT again), the logged mcause /
  pending / data, and that IRQ_PENDING_MASKED reads 0 once the handler has run.

IMAGE 2  pll_prog.hex -- both PLLs' divider fields programmed through the real fabric
  PLL1 (0x2000_7000, via u_apb_pll_cdc) and PLL2 (0x2000_9000, via u_apb_pll2_cdc):
  CONTROL[7:4]=div_n, [9:8]=post_div_sel are written, read back, STATUS.locked re-checked.
  Marker PCs let the testbench read pll_fb_div / pll_post_div of BOTH instances after each
  write and prove the other instance was untouched.

IMAGE 3  gpu_iso.hex -- GPU power-down/up with a level-held gpu_irq_o
  Launches the existing cpu_gpu_irq kernel with GPU_CTRL.irq_enable but interrupts masked,
  so gpu_irq_o is HIGH and stays high.  PMU CTRL=GPU_OFF (0x2000_8000) walks ret_save ->
  iso_en -> clock gate -> reset; PMU CTRL=NORMAL walks the reverse.  GPU registers are
  never touched while isolated (gif_axil_arvalid is clamped, a read would hang).
  FINDING: the GPU's flops are async-reset, so the domain reset clears ALL GPU state (irq
  latch, irq_enable, done) even though its clock is gated -- unlike the CPU, the GPU does
  not "survive by construction" as pmu.sv's header claims.  The image therefore checks
  state-LOSS (irq_enable and done read 0 after power-up) and then proves the GPU works
  again: a second launch on new data completes and gpu_irq_o rises through the released
  isolation.  The clamp itself is observable only in the window between iso_en rising and
  the reset asserting, where gpu_irq_raw is still 1.

IMAGE 4  dma_walk.hex -- the DMA as the SoC's only software-programmable bus master walk
  (beads 0ntg + xkw5).  No interrupts: the DMA is polled through its STATUS register.
  Phase 1 ALIAS  : sixteen 16-byte copies whose SRC and DST each have one more high address bit
                  set (bits 12..27, the whole 256 MB SRAM window).  The behavioural SRAM only
                  realises 4 KB and aliases the rest (sram_controller.sv word_index), so every
                  copy lands in the same 4 KB and is checkable by backdoor; the point is that
                  each address bit of the crossbar, the SRAM slave port and the DMA master
                  port is driven both ways on a transfer that really completes.
  Phase 2 ROMWR  : nine copies SRAM -> boot-ROM window (len 4..128 B, varied word addresses).
                  boot_rom has no write path by design (ej6j): every attempt must end in
                  STATUS.error with ERR_INFO = SLVERR / write (0b010), and the ROM must be
                  bit-identical afterwards.  This is the first SoC-level drive of
                  crossbar -> boot_rom AW/W/B.
  Phase 3 DECERR : DMA reads from, and writes to, four unmapped addresses (bits 28, 17 of the
                  hole above the peripheral window, 30, 31).  The crossbar's default slave
                  answers DECERR: read -> ERR_INFO = 0b111, write -> 0b011.

  Phase 4 UNALIGN: four single-word DMA reads from byte offsets +1/+2/+3 and then +0 of an unmapped timer-window
                  word.  Only a DMA can put a non-zero address[1:0] on the peripheral ring (the
                  D-cache word-aligns uncached accesses), and apb_interconnect broadcasts paddr to
                  every slave, so this one probe toggles paddr[1:0] of all peripherals.
IMAGE 5  gpu_walk.hex -- the GPU's two bus masters walked through the fabric (bead xkw5)
  The GPU is the only master that can put an arbitrary 32-bit address on the crossbar from a
  software-written program, on BOTH of its ports: the instruction-fetch port (crossbar M1, the
  kernel PC) and the data port (M2, VLD/VST addresses).  The CPU writes sixteen copies of a tiny kernel, each with
  its own patched immediate, and launches them one after the other.
  Phase A ALIAS  : launch k (k = 12..27) fetches the kernel from KERNEL_PC | (1 << k) and the
                  kernel loads 8 words from, and stores 8 words to, (1 << k) | 0x2000 + offset.
                  The behavioural SRAM realises 4 KB and aliases the rest, so every launch
                  really completes on the same words; each launch stores src[lane] + k.
  Phase B ROMRD  : 8 lanes read the first 8 boot-ROM words and copy them to SRAM.
  Phase C PERIPH : 8 lanes write the timer's COMPARE register (one APB write per lane through
                  M2 -> axi4_to_axilite -> ring), read it back and copy it to SRAM.
  Phase D ROMWR  : 8 lanes store to the boot ROM; the ROM refuses every write with SLVERR.
  Phase E DECERR : loads and stores to four unmapped addresses, answered DECERR.
  The GPU ignores read and write responses (gpu_top.sv leaves rresp/bresp unused), so a refused
  or unmapped access never stalls it; the testbench scores the responses at the crossbar port.
Registers: IMAGE 1 MAIN uses x1-x23 (x2=VAR_BASE x3=TIMER x4=UART x5=SPI x6=DMA x7=IRQ);
the ISR uses only x24-x31.
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (  # noqa: E402
    ADDI, ADD, ANDI, OR, SW, LW, BNE, BEQ, JAL, EBREAK, SLLI, XORI, CSRRW, CSRRS, MRET,
)
from tb.cocotb.soc.gpio_fw.gen_gpio_hex import Assembler, lui_addi, NOP  # noqa: E402
from tb.cocotb.soc.cpu_gpu_irq_fw import gen_cpu_gpu_irq_hex as gpuirq  # noqa: E402

ROM_BASE = 0x0000_1000
ROM_WORDS = 1024
ISR_OFFSET_WORDS = 1

# ---- address map ------------------------------------------------------------
SRAM_BASE = 0x0000_2000
UART_BASE = 0x2000_2000
SPI_BASE = 0x2000_3000
TIMER_BASE = 0x2000_4000
DMA_BASE = 0x2000_5000
IRQ_BASE = 0x2000_6000
PLL1_BASE = 0x2000_7000
PMU_BASE = 0x2000_8000
PLL2_BASE = 0x2000_9000

# ---- IMAGE 1 SRAM variables (word 400 = 0x2640; far from the DMA 0x2000/0x2040 window) --
VAR_WI = 400
VAR_BASE = SRAM_BASE + VAR_WI * 4
OFF_PHASE, OFF_FLAG, OFF_COUNT = 0, 4, 8
OFF_LOG_MCAUSE = 16   # + 4*phase
OFF_LOG_PEND = 48
OFF_LOG_DATA = 80

MCAUSE_MTI = 0x8000_0007
MCAUSE_MEI = 0x8000_000B
UART_TX_BYTE = 0xA5
SPI_TX_BYTE = 0x3C
SPI_SLAVE_RESP = 0xA6
POLL_LIMIT = 20000
TIMER_COMPARE = 64
SPI_CLK_DIV = 7

# ---- IMAGE 2 -----------------------------------------------------------------
PLL1_VAL_A = 0x2A1   # div_n=0xA, post_div_sel=2, pll_enable=1
PLL2_VAL = 0x151     # div_n=5,   post_div_sel=1
PLL1_VAL_B = 0x0F1   # div_n=15,  post_div_sel=0
PLL_RESET_VAL = 0x1

# ---- IMAGE 3 -----------------------------------------------------------------
GPU_BASE = gpuirq.GPU_BASE
PMU_GPU_OFF = 0x2
PMU_STATUS_GPU_OFF = 0x1   # cpu_on=1 gpu_on=0 busy=0
PMU_STATUS_NORMAL = 0x3


def li(asm, rd, value):
    lo, hi = lui_addi(rd, value)
    asm.emit(lo)
    asm.emit(hi)


def br(asm, op, rs1, rs2, target):
    asm.thunk(lambda lbl, pc, op=op, a=rs1, b=rs2, t=target: op(a, b, lbl[t] - pc))


def jmp(asm, target):
    asm.thunk(lambda lbl, pc, t=target: JAL(0, lbl[t] - pc))


def trampoline(asm):
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))


def tail(asm):
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


def expect_word(asm, base_reg, off, value):
    """FAIL unless mem[base_reg+off] == value (scratch x10/x11)."""
    asm.emit(LW(10, base_reg, off))
    li(asm, 11, value)
    br(asm, BNE, 10, 11, "FAIL")


def flush_dcache(asm, tag):
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(16, 0, 0))
    li(asm, 17, 2048)
    asm.label(tag)
    asm.emit(ADDI(16, 16, 1))
    br(asm, BNE, 16, 17, tag)


# =============================================================================
# IMAGE 1: interrupts + SPI MISO
# =============================================================================
def build_irq_spi(asm):
    trampoline(asm)

    # ---- ISR (word 1) ----------------------------------------------------------
    asm.label("ISR")
    asm.emit(CSRRS(28, 0x342, 0))                 # x28 = mcause
    li(asm, 29, VAR_BASE)
    asm.emit(LW(30, 29, OFF_PHASE))               # x30 = phase
    asm.emit(SLLI(31, 30, 2))
    asm.emit(ADD(31, 31, 29))                     # x31 = &VAR + 4*phase
    asm.emit(SW(28, 31, OFF_LOG_MCAUSE))
    li(asm, 27, IRQ_BASE)
    asm.emit(LW(26, 27, 0x08))                    # IRQ_PENDING_MASKED
    asm.emit(SW(26, 31, OFF_LOG_PEND))
    for ph, name in ((1, "H_TIMER"), (2, "H_UART"), (3, "H_SPI"), (4, "H_DMA")):
        asm.emit(ADDI(25, 0, ph))
        br(asm, BEQ, 30, 25, name)
    jmp(asm, "H_DONE")
    asm.label("H_TIMER")
    li(asm, 24, TIMER_BASE)
    asm.emit(ADDI(25, 0, 4))                      # CTRL = autoclear edge, disabled
    asm.emit(SW(25, 24, 0x08))
    jmp(asm, "H_DONE")
    asm.label("H_UART")
    li(asm, 24, UART_BASE)
    asm.emit(LW(25, 24, 0x04))                    # pop RX
    asm.emit(SW(25, 31, OFF_LOG_DATA))
    jmp(asm, "H_DONE")
    asm.label("H_SPI")
    li(asm, 24, SPI_BASE)
    asm.emit(LW(25, 24, 0x04))                    # pop RX
    asm.emit(SW(25, 31, OFF_LOG_DATA))
    jmp(asm, "H_DONE")
    asm.label("H_DMA")
    li(asm, 24, DMA_BASE)
    asm.emit(ADDI(25, 0, 4))                      # CTRL[2] soft reset clears IRQ_STATUS
    asm.emit(SW(25, 24, 0x0C))
    asm.label("H_DONE")
    asm.emit(ADDI(25, 0, 1))
    asm.emit(SW(25, 29, OFF_FLAG))
    asm.emit(LW(25, 29, OFF_COUNT))
    asm.emit(ADDI(25, 25, 1))
    asm.emit(SW(25, 29, OFF_COUNT))
    asm.emit(MRET())

    asm.pad_to_word(80)

    # ---- MAIN ------------------------------------------------------------------
    asm.label("MAIN")
    li(asm, 2, VAR_BASE)
    li(asm, 3, TIMER_BASE)
    li(asm, 4, UART_BASE)
    li(asm, 5, SPI_BASE)
    li(asm, 6, DMA_BASE)
    li(asm, 7, IRQ_BASE)
    li(asm, 1, ROM_BASE + ISR_OFFSET_WORDS * 4)
    asm.emit(CSRRW(0, 0x305, 1))                  # mtvec
    for off in (OFF_PHASE, OFF_FLAG, OFF_COUNT):
        asm.emit(SW(0, 2, off))
    li(asm, 1, 0x880)                             # MTIE | MEIE
    asm.emit(CSRRW(0, 0x304, 1))
    asm.emit(ADDI(1, 0, 8))                       # mstatus.MIE
    asm.emit(CSRRW(0, 0x300, 1))

    def start_phase(ph):
        asm.emit(ADDI(8, 0, ph))
        asm.emit(SW(8, 2, OFF_PHASE))
        asm.emit(SW(0, 2, OFF_FLAG))

    def wait_and_check(ph, mcause, pend, data):
        tag = f"P{ph}"
        li(asm, 20, POLL_LIMIT)
        asm.emit(ADDI(21, 0, 0))
        asm.label(f"{tag}_POLL")
        asm.emit(LW(22, 2, OFF_FLAG))
        br(asm, BNE, 22, 0, f"{tag}_GOT")
        asm.emit(ADDI(21, 21, 1))
        br(asm, BNE, 21, 20, f"{tag}_POLL")
        jmp(asm, "FAIL")
        asm.label(f"{tag}_GOT")
        expect_word(asm, 2, OFF_COUNT, ph)                       # exactly one trap so far
        expect_word(asm, 2, OFF_LOG_MCAUSE + 4 * ph, mcause)
        expect_word(asm, 2, OFF_LOG_PEND + 4 * ph, pend)
        if data is not None:
            expect_word(asm, 2, OFF_LOG_DATA + 4 * ph, data)
        asm.emit(LW(10, 7, 0x08))                                # source cleared at the controller
        br(asm, BNE, 10, 0, "FAIL")

    # Phase 1: timer -> MTIP direct
    start_phase(1)
    li(asm, 8, TIMER_COMPARE)
    asm.emit(SW(8, 3, 0x04))
    asm.emit(SW(0, 3, 0x0C))
    asm.emit(ADDI(8, 0, 3))                        # enable | irq_en
    asm.label("TIMER_ARMED")
    asm.emit(SW(8, 3, 0x08))
    wait_and_check(1, MCAUSE_MTI, 0, None)

    # Phase 2: UART rx-valid -> IRQ controller bit 0
    start_phase(2)
    asm.emit(ADDI(8, 0, 1))
    asm.emit(SW(8, 7, 0x04))                       # IRQ_MASK = UART
    asm.emit(SW(0, 4, 0x10))                       # BAUD = 0
    asm.emit(ADDI(8, 0, 0x1B))                     # tx_en|rx_en|irq_rx_valid_en|loopback
    asm.emit(SW(8, 4, 0x0C))
    asm.emit(ADDI(8, 0, UART_TX_BYTE))
    asm.emit(SW(8, 4, 0x00))
    wait_and_check(2, MCAUSE_MEI, 1 << 0, UART_TX_BYTE)
    asm.emit(SW(0, 4, 0x0C))

    # Phase 3: SPI, real MISO from the testbench slave -> IRQ controller bit 1
    start_phase(3)
    asm.emit(ADDI(8, 0, 2))
    asm.emit(SW(8, 7, 0x04))
    asm.emit(ADDI(8, 0, SPI_CLK_DIV))
    asm.emit(SW(8, 5, 0x10))
    asm.emit(SW(0, 5, 0x14))                       # SPI_CS_CTRL = 0 -> spi_cs_n_o low
    asm.emit(ADDI(8, 0, 9))                        # enable | irq_done_en, NOT loopback
    asm.emit(SW(8, 5, 0x0C))
    asm.emit(ADDI(8, 0, SPI_TX_BYTE))
    asm.label("SPI_ARMED")
    asm.emit(SW(8, 5, 0x00))
    wait_and_check(3, MCAUSE_MEI, 1 << 1, SPI_SLAVE_RESP)
    asm.emit(ADDI(8, 0, 1))
    asm.emit(SW(8, 5, 0x14))                       # release CS
    asm.emit(SW(0, 5, 0x0C))

    # Phase 4: DMA done -> IRQ controller bit 3
    start_phase(4)
    asm.emit(ADDI(8, 0, 8))
    asm.emit(SW(8, 7, 0x04))
    li(asm, 8, SRAM_BASE)
    asm.emit(SW(8, 6, 0x00))                       # SRC
    li(asm, 8, SRAM_BASE + 0x40)
    asm.emit(SW(8, 6, 0x04))                       # DST
    asm.emit(ADDI(8, 0, 16))
    asm.emit(SW(8, 6, 0x08))                       # LEN
    asm.emit(ADDI(8, 0, 3))                        # start | irq_en
    asm.emit(SW(8, 6, 0x0C))
    wait_and_check(4, MCAUSE_MEI, 1 << 3, None)
    expect_word(asm, 6, 0x14, 0)                   # DMA IRQ_STATUS cleared by the handler
    asm.emit(SW(0, 7, 0x04))                       # IRQ_MASK = 0
    jmp(asm, "PASS")
    tail(asm)


# =============================================================================
# IMAGE 2: PLL divider programming
# =============================================================================
def build_pll_prog(asm):
    trampoline(asm)
    asm.label("MAIN")
    li(asm, 2, PLL1_BASE)
    li(asm, 3, PLL2_BASE)

    def prog(base_reg, value, marker):
        li(asm, 5, value)
        asm.emit(SW(5, base_reg, 0x00))
        asm.emit(LW(6, base_reg, 0x00))
        br(asm, BNE, 6, 5, "FAIL")                 # CONTROL reads back what was written
        asm.emit(LW(7, base_reg, 0x04))
        asm.emit(ANDI(7, 7, 1))
        br(asm, BEQ, 7, 0, "FAIL")                 # still locked
        asm.label(marker)
        asm.emit(NOP)

    # Data-pattern + address sweep through the whole fabric path (pwdata / paddr / prdata
    # bits of the pll APB nets).  CONTROL's WMASK is 0x3F0 (bit0 pll_enable is non-clearable,
    # GH #89), so the readback of every pattern is (pattern & 0x3F0) | 1; offsets beyond the
    # two registers read 0 (apb4_register_bank out-of-range policy).
    for base in (2, 3):
        for pat in (0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x0):
            li(asm, 5, pat)
            asm.emit(SW(5, base, 0x00))
            expect_word(asm, base, 0x00, (pat & 0x3F0) | 1)
        for sh in range(3, 11):
            asm.emit(LW(10, base, 1 << sh))
            br(asm, BNE, 10, 0, "FAIL")
        asm.emit(ADDI(8, base, 0x7FF))             # +0x800 does not fit a signed imm12
        asm.emit(LW(10, 8, 1))
        br(asm, BNE, 10, 0, "FAIL")
    for base in (2, 3):                            # reset state, both
        expect_word(asm, base, 0x00, PLL_RESET_VAL)
    asm.label("PLL_RESET_OK")
    asm.emit(NOP)
    prog(2, PLL1_VAL_A, "PLL1_A")
    prog(3, PLL2_VAL, "PLL2_PROGRAMMED")
    prog(2, PLL1_VAL_B, "PLL1_B")
    jmp(asm, "PASS")
    tail(asm)


# =============================================================================
# IMAGE 3: GPU isolation through the PMU
# =============================================================================
def build_gpu_iso(asm):
    trampoline(asm)
    asm.label("MAIN")
    li(asm, 3, gpuirq.SRC_BASE)
    li(asm, 5, gpuirq.KERNEL_PC)
    li(asm, 6, GPU_BASE)
    li(asm, 9, PMU_BASE)
    # NOTE: no mtvec / mie / mstatus / IRQ_MASK -- gpu_irq_o must just sit high.

    def write_src(scale):
        for i in range(gpuirq.N_SRC_WORDS):
            asm.emit(ADDI(7, 0, (i + 1) * scale))
            asm.emit(SW(7, 3, i * 4))

    def launch():
        asm.emit(SW(5, 6, gpuirq.GPU_OFF_KERNEL_PC))
        asm.emit(ADDI(7, 0, 1))
        for off in (gpuirq.GPU_OFF_GRID_X, gpuirq.GPU_OFF_GRID_Y, gpuirq.GPU_OFF_GRID_Z,
                    gpuirq.GPU_OFF_BLOCK_Y, gpuirq.GPU_OFF_BLOCK_Z):
            asm.emit(SW(7, 6, off))
        asm.emit(ADDI(7, 0, 8))
        asm.emit(SW(7, 6, gpuirq.GPU_OFF_BLOCK_X))
        asm.emit(ADDI(7, 0, 0x05))                 # irq_enable | launch
        asm.emit(SW(7, 6, gpuirq.GPU_OFF_CTRL))

    def poll(tag, status_reg_base, off, mask, extra_eq=None):
        li(asm, 20, POLL_LIMIT)
        asm.emit(ADDI(21, 0, 0))
        asm.label(f"{tag}_POLL")
        asm.emit(LW(22, status_reg_base, off))
        if extra_eq is None:
            asm.emit(ANDI(22, 22, mask))
            br(asm, BNE, 22, 0, f"{tag}_GOT")
        else:
            asm.emit(ADDI(23, 0, extra_eq))
            br(asm, BEQ, 22, 23, f"{tag}_GOT")
        asm.emit(ADDI(21, 21, 1))
        br(asm, BNE, 21, 20, f"{tag}_POLL")
        jmp(asm, "FAIL")
        asm.label(f"{tag}_GOT")

    write_src(0x10)
    flush_dcache(asm, "FL1")
    for i, kw in enumerate(gpuirq.build_gpu_kernel()):
        li(asm, 7, kw)
        asm.emit(SW(7, 5, i * 4))
    flush_dcache(asm, "FL2")
    asm.emit(LW(7, 6, gpuirq.GPU_OFF_CTRL))        # irq_enable not yet set
    launch()
    poll("GDONE", 6, gpuirq.GPU_OFF_STATUS, 2)
    asm.label("GPU_DONE")
    asm.emit(NOP)

    asm.emit(ADDI(7, 0, PMU_GPU_OFF))
    asm.emit(SW(7, 9, 0x00))
    poll("POFF", 9, 0x04, 0, extra_eq=PMU_STATUS_GPU_OFF)
    asm.label("GPU_OFF")
    asm.emit(NOP)
    asm.emit(ADDI(16, 0, 0))                       # dwell while isolated
    asm.emit(ADDI(17, 0, 200))
    asm.label("DWELL")
    asm.emit(ADDI(16, 16, 1))
    br(asm, BNE, 16, 17, "DWELL")

    asm.emit(SW(0, 9, 0x00))                       # NORMAL
    poll("PON", 9, 0x04, 0, extra_eq=PMU_STATUS_NORMAL)
    asm.label("GPU_ON")
    asm.emit(NOP)

    # The GPU's flops use ASYNC reset (posedge clk or negedge rst_n), so asserting the
    # domain reset clears its state even with the clock gated: unlike the CPU, nothing
    # survives a PMU power cycle.  Prove it from software: GPU_CTRL.irq_enable (was 1),
    # and GPU_STATUS.done (was 1) both read back 0.
    asm.emit(LW(7, 6, gpuirq.GPU_OFF_CTRL))
    asm.emit(ANDI(7, 7, 4))
    br(asm, BNE, 7, 0, "FAIL")
    asm.emit(LW(7, 6, gpuirq.GPU_OFF_STATUS))
    asm.emit(ANDI(7, 7, 2))
    br(asm, BNE, 7, 0, "FAIL")

    # ... and the GPU is fully functional again, through the released isolation: a second
    # kernel on new source data completes and its level-held irq reaches gpu_irq_o.
    write_src(0x20)
    flush_dcache(asm, "FL3")
    launch()
    poll("GDONE2", 6, gpuirq.GPU_OFF_STATUS, 2)
    asm.label("GPU_RELAUNCHED")
    asm.emit(NOP)
    asm.emit(ADDI(7, 0, 1))
    asm.label("IRQ_CLR")
    asm.emit(SW(7, 6, gpuirq.GPU_OFF_IRQ_CLR))
    flush_dcache(asm, "FL4")
    jmp(asm, "PASS")
    tail(asm)


# =============================================================================
# IMAGE 4: DMA walk -- SRAM aliases, boot-ROM write (SLVERR), unmapped addresses (DECERR)
# =============================================================================
# SRAM layout (all below the 4 KB the behavioural SRAM realises; SRAM_BASE = 0x2000)
WALK_SRC_A = SRAM_BASE + 0x100   # 4-word pattern A (alias-walk sources, even iterations)
WALK_SRC_B = SRAM_BASE + 0x140   # 4-word pattern B (odd iterations)
WALK_SRC_ROM = SRAM_BASE + 0x200  # 32-word source for the ROM-write copies
WALK_DST = SRAM_BASE + 0x400     # + 0x10 * i : alias-walk destinations
WALK_SCRATCH = SRAM_BASE + 0x600  # destination of the failing-read copies (never written)
WALK_PAT_A = (0xDEADBEEF, 0x12345678, 0xA5A5A5A5, 0x5A5A5A5A)
WALK_PAT_B = (0xFFFFFFFF, 0x00000000, 0xAAAAAAAA, 0x55555555)
WALK_ALIAS_BITS = tuple(range(12, 28))   # address bit k of the 256 MB SRAM window
WALK_ROM_FILL_SEED = 0xA5A5A5A5
WALK_ROM_FILL_STEP = 0x9E3779B1
WALK_ROM_FILL_WORDS = 32
# (length in bytes, destination) of the boot-ROM write attempts; every one stays inside the
# 4 KB ROM window and inside one 4 KB page (the DMA splits bursts there anyway).
WALK_ROM_COPIES = (
    (4, 0x1FFC), (8, 0x1FF8), (16, 0x1FF0), (32, 0x1FE0), (64, 0x1FC0), (128, 0x1F80),
    (16, 0x1554), (16, 0x1AA8), (16, 0x1000),
)
WALK_DECERR_ADDRS = (0x1000_0000, 0x2002_0000, 0x4000_0000, 0x8000_0000)
# Unaligned single-word DMA reads from an UNMAPPED word inside the timer's APB window (reads 0, no
# side effect).  No other master can put a non-zero address[1:0] on the peripheral ring: the
# D-cache word-aligns every uncached access (rv32i_dcache.sv axi_{ar,aw}addr_o).
WALK_UNAL_BASE = 0x2000_4000 + 0x100
WALK_UNAL_OFFS = (1, 2, 3, 0)   # the trailing aligned read drops address[1:0] again
WALK_UNAL_DST = SRAM_BASE + 0x700   # pre-filled with all-ones; the DMA must overwrite each word
ERRINFO_ROM_WRITE = 0b010     # SLVERR, error on the write channel
ERRINFO_DECERR_READ = 0b111   # DECERR, error on the read channel
ERRINFO_DECERR_WRITE = 0b011  # DECERR, error on the write channel
DMA_STATUS_DONE, DMA_STATUS_ERR = 0x2, 0x4


def build_dma_walk(asm):
    trampoline(asm)
    asm.label("MAIN")
    li(asm, 6, DMA_BASE)
    li(asm, 2, SRAM_BASE)

    # ---- source patterns -------------------------------------------------------------
    for base, pat in ((WALK_SRC_A, WALK_PAT_A), (WALK_SRC_B, WALK_PAT_B)):
        for i, v in enumerate(pat):
            li(asm, 5, v)
            li(asm, 7, base + 4 * i)
            asm.emit(SW(5, 7, 0))
    li(asm, 5, 0xFFFFFFFF)
    for k in range(len(WALK_UNAL_OFFS)):
        li(asm, 7, WALK_UNAL_DST + 4 * k)
        asm.emit(SW(5, 7, 0))
    li(asm, 12, WALK_ROM_FILL_SEED)
    li(asm, 13, WALK_SRC_ROM)
    li(asm, 14, WALK_ROM_FILL_STEP)
    asm.emit(ADDI(11, 0, 0))
    asm.emit(ADDI(15, 0, WALK_ROM_FILL_WORDS))
    asm.label("FILL")
    asm.emit(SW(12, 13, 0))
    asm.emit(ADD(12, 12, 14))
    asm.emit(ADDI(13, 13, 4))
    asm.emit(ADDI(11, 11, 1))
    br(asm, BNE, 11, 15, "FILL")
    flush_dcache(asm, "FLW")                      # the DMA reads SRAM behind the D-cache

    def program(src_reg, dst_reg, nbytes):
        asm.emit(SW(src_reg, 6, 0x00))
        asm.emit(SW(dst_reg, 6, 0x04))
        asm.emit(ADDI(8, 0, nbytes))
        asm.emit(SW(8, 6, 0x08))

    def run(tag, errinfo=None):
        """Start the programmed copy, poll STATUS.{done,error}, check it, soft-reset."""
        asm.emit(ADDI(8, 0, 1))
        asm.emit(SW(8, 6, 0x0C))                  # CTRL.start
        asm.emit(ADDI(14, 0, 0))
        li(asm, 15, 3000)
        asm.label(f"{tag}_P")
        asm.emit(LW(9, 6, 0x10))                  # STATUS
        asm.emit(ANDI(10, 9, DMA_STATUS_DONE | DMA_STATUS_ERR))
        br(asm, BNE, 10, 0, f"{tag}_D")
        asm.emit(ADDI(14, 14, 1))
        br(asm, BNE, 14, 15, f"{tag}_P")
        jmp(asm, "FAIL")                          # never completed
        asm.label(f"{tag}_D")
        if errinfo is None:
            asm.emit(ADDI(11, 0, DMA_STATUS_DONE))  # done and NOT error
            br(asm, BNE, 10, 11, "FAIL")
        else:
            asm.emit(ADDI(11, 0, DMA_STATUS_ERR))   # error and NOT done
            br(asm, BNE, 10, 11, "FAIL")
            asm.emit(LW(9, 6, 0x18))              # ERR_INFO
            asm.emit(ADDI(11, 0, errinfo))
            br(asm, BNE, 9, 11, "FAIL")
        asm.emit(ADDI(8, 0, 4))
        asm.emit(SW(8, 6, 0x0C))                  # CTRL.soft_reset: clears the sticky bits

    # ---- phase 1: SRAM alias walk ----------------------------------------------------
    li(asm, 22, 1 << WALK_ALIAS_BITS[0])          # x22 = one-hot address bit
    li(asm, 24, 1 << (WALK_ALIAS_BITS[-1] + 1))   # loop end
    li(asm, 23, WALK_DST)                         # x23 = running destination offset
    asm.emit(ADDI(25, 0, 0))                      # x25 = pattern select (0 / 0x40)
    asm.label("ALIAS")
    li(asm, 7, WALK_SRC_A)
    asm.emit(ADD(7, 7, 25))
    asm.emit(OR(7, 7, 22))                        # src = pattern | (1 << k)
    asm.emit(OR(5, 23, 22))                       # dst = slot    | (1 << k)
    program(7, 5, 16)
    run("AL")
    asm.emit(ADDI(23, 23, 0x10))
    asm.emit(XORI(25, 25, 0x40))
    asm.emit(SLLI(22, 22, 1))
    br(asm, BNE, 22, 24, "ALIAS")
    asm.label("ALIAS_DONE")
    asm.emit(NOP)

    # ---- phase 2: boot-ROM write attempts -> SLVERR ----------------------------------
    li(asm, 7, WALK_SRC_ROM)
    for n, (nbytes, dst) in enumerate(WALK_ROM_COPIES):
        li(asm, 5, dst)
        program(7, 5, nbytes)
        run(f"RW{n}", ERRINFO_ROM_WRITE)
    asm.label("ROM_DONE")
    asm.emit(NOP)

    # ---- phase 3: unmapped addresses -> DECERR ---------------------------------------
    li(asm, 5, WALK_SCRATCH)
    for n, addr in enumerate(WALK_DECERR_ADDRS):
        li(asm, 7, addr)
        program(7, 5, 16)
        run(f"DR{n}", ERRINFO_DECERR_READ)
    li(asm, 7, WALK_SRC_ROM)
    for n, addr in enumerate(WALK_DECERR_ADDRS):
        li(asm, 5, addr)
        program(7, 5, 16)
        run(f"DW{n}", ERRINFO_DECERR_WRITE)
    asm.label("DECERR_DONE")
    asm.emit(NOP)

    # ---- phase 4: unaligned reads put non-zero paddr[1:0] on the whole peripheral ring ------
    for n, off in enumerate(WALK_UNAL_OFFS):
        li(asm, 7, WALK_UNAL_BASE + off)
        li(asm, 5, WALK_UNAL_DST + 4 * n)
        program(7, 5, 4)
        run(f"UA{n}")
    asm.label("UNAL_DONE")
    asm.emit(NOP)
    jmp(asm, "PASS")
    tail(asm)


# =============================================================================
# IMAGE 5: GPU walk -- both GPU bus masters, SRAM aliases, ROM, peripheral, unmapped
# =============================================================================
GW_KBASE = SRAM_BASE + 0x800        # kernel image (16..48 words)
GW_SRC = SRAM_BASE + 0x100          # 8 source words (phase A)
GW_SRC_VALS = (0xDEADBEEF, 0x12345678, 0xA5A5A5A5, 0x5A5A5A5A,
               0xFFFFFFFF, 0x00000000, 0xAAAAAAAA, 0x55555555)
GW_ALIAS_BITS = tuple(range(12, 28))
GW_LD_OFF, GW_ST_OFF = 0x100, 0x400  # phase A: load at A + 0x100, store at A + 0x400
GW_SCR_B = SRAM_BASE + 0x500        # phase B copy of the first 8 ROM words
GW_SCR_C = SRAM_BASE + 0x540        # phase C read-back of the timer COMPARE register
GW_TIMER_CMP = 0x2000_4000 + 0x04   # TMR_COMPARE (RW, reset 0xFFFFFFFF)
GW_ROM_WR = 0x1F00                  # phase D: eight words inside the 4 KB boot ROM
GW_DECERR_LD = (0x1000_0000, 0x2002_0000, 0x8000_0000)
GW_DECERR_ST = (0x4000_0000, 0x2001_1000, 0xC000_0000)
GW_DATA_BASE = 0x5A5                # phase B..E store data = 0x5A5 + 4 * lane (VADDI imm12)
GW_PATCH_WORD = 4                   # kernel word holding the "VADDI r5, r0, k" immediate
GW_POLL_LIMIT = 4000
GW_COPY_STRIDE = 0x40               # phase A: byte distance between the kernel copies

_G_ADDI_R5_K0 = gpuirq.gpu_vaddi(5, 0, 0)


def gpu_vor(rd, rs1, rs2):
    return gpuirq._r_instr(0x05, rd, rs1, rs2)


def gpu_vori(rd, rs1, imm):
    return gpuirq._i_instr(0x13, rd, rs1, imm)


def _g_const(rd, value):
    """GPU words that load a 32-bit constant into vector register rd (r11 must hold 8)."""
    out = [gpuirq.gpu_vaddi(rd, 0, 0)]
    for shift in (24, 16, 8, 0):
        out.append(gpuirq.gpu_vsll(rd, rd, 11))
        out.append(gpu_vori(rd, rd, (value >> shift) & 0xFF))
    return out


def _g_prolog():
    return [
        gpuirq.gpu_vmov_tid_x(1),
        gpuirq.gpu_vaddi(2, 0, 2),
        gpuirq.gpu_vsll(3, 1, 2),                 # r3 = lane * 4
        gpuirq.gpu_vaddi(11, 0, 8),               # r11 = 8 (the byte shift)
        gpuirq.gpu_vaddi(8, 3, GW_DATA_BASE),     # r8 = store data
    ]


def _g_addr(addr, stride):
    """r6 = addr (+ lane * 4 when stride)."""
    out = _g_const(4, addr)
    out.append(gpuirq.gpu_vadd(6, 4, 3) if stride else gpuirq.gpu_vadd(6, 4, 0))
    return out


def _g_load(addr, stride):
    return _g_addr(addr, stride) + [gpuirq.gpu_vld(7, 6, 0)]


def _g_store(addr, stride, data_reg):
    # VST: effective address = rs1 + imm, imm[4:0] = the data register index
    return _g_addr(addr, stride) + [
        gpuirq.gpu_vaddi(10, 6, -data_reg),
        gpuirq.gpu_vst(data_reg, 10, 0),
    ]


def gw_kernel_alias():
    """Phase A kernel; word GW_PATCH_WORD is rewritten with k before every launch."""
    words = [
        gpuirq.gpu_vmov_tid_x(1),
        gpuirq.gpu_vaddi(2, 0, 2),
        gpuirq.gpu_vsll(3, 1, 2),                 # r3 = lane * 4
        gpuirq.gpu_vaddi(4, 0, 1),
        _G_ADDI_R5_K0,                            # r5 = k          <- patched
        gpuirq.gpu_vsll(4, 4, 5),                 # r4 = 1 << k
        gpuirq.gpu_vaddi(9, 0, 1),
        gpuirq.gpu_vaddi(10, 0, 13),
        gpuirq.gpu_vsll(9, 9, 10),                # r9 = 0x2000
        gpu_vor(4, 4, 9),                         # r4 = A = (1 << k) | 0x2000
        gpuirq.gpu_vadd(6, 4, 3),                 # r6 = A + lane * 4
        gpuirq.gpu_vld(7, 6, GW_LD_OFF),          # r7 = mem[A + 0x100 + 4 lane]
        gpuirq.gpu_vadd(8, 7, 5),                 # r8 = src + k
        gpuirq.gpu_vaddi(10, 6, -8),
        gpuirq.gpu_vst(8, 10, GW_ST_OFF),         # mem[A + 0x400 + 4 lane] = r8
        gpuirq.gpu_vret(),
    ]
    assert words[GW_PATCH_WORD] == _G_ADDI_R5_K0
    return words


def gw_kernel_rom_read():
    return (_g_prolog() + _g_load(ROM_BASE, True) + _g_store(GW_SCR_B, True, 7)
            + [gpuirq.gpu_vret()])


def gw_kernel_periph():
    return (_g_prolog() + _g_store(GW_TIMER_CMP, False, 8) + _g_load(GW_TIMER_CMP, False)
            + _g_store(GW_SCR_C, True, 7) + [gpuirq.gpu_vret()])


def gw_kernel_rom_write():
    return _g_prolog() + _g_store(GW_ROM_WR, True, 8) + [gpuirq.gpu_vret()]


def gw_kernel_decerr():
    out = _g_prolog()
    for addr in GW_DECERR_LD:
        out += _g_load(addr, False)
    for addr in GW_DECERR_ST:
        out += _g_store(addr, False, 8)
    return out + [gpuirq.gpu_vret()]


def build_gpu_walk(asm):
    trampoline(asm)
    asm.label("MAIN")
    li(asm, 6, GPU_BASE)
    li(asm, 5, GW_KBASE)
    li(asm, 3, GW_SRC)
    for i, v in enumerate(GW_SRC_VALS):
        li(asm, 7, v)
        asm.emit(SW(7, 3, 4 * i))
    asm.emit(ADDI(7, 0, 1))
    for off in (gpuirq.GPU_OFF_GRID_X, gpuirq.GPU_OFF_GRID_Y, gpuirq.GPU_OFF_GRID_Z,
                gpuirq.GPU_OFF_BLOCK_Y, gpuirq.GPU_OFF_BLOCK_Z):
        asm.emit(SW(7, 6, off))
    asm.emit(ADDI(7, 0, 8))
    asm.emit(SW(7, 6, gpuirq.GPU_OFF_BLOCK_X))

    def write_kernel(words):
        for i, kw in enumerate(words):
            li(asm, 7, kw)
            asm.emit(SW(7, 5, 4 * i))

    def poll_status(tag, mask):
        """Spin until GPU_STATUS & mask is non-zero; FAIL on timeout or when STATUS.error is set."""
        li(asm, 9, GW_POLL_LIMIT)
        asm.emit(ADDI(10, 0, 0))
        asm.label(f"{tag}_P")
        asm.emit(LW(11, 6, gpuirq.GPU_OFF_STATUS))
        asm.emit(ANDI(12, 11, 4))
        br(asm, BNE, 12, 0, "FAIL")               # STATUS.error
        asm.emit(ANDI(12, 11, mask))
        br(asm, BNE, 12, 0, f"{tag}_G")
        asm.emit(ADDI(10, 10, 1))
        br(asm, BNE, 10, 9, f"{tag}_P")
        jmp(asm, "FAIL")
        asm.label(f"{tag}_G")

    def run_kernel(tag):
        """Launch, wait for DONE, then GPU_CTRL.reset and wait for IDLE (ready for the next)."""
        asm.emit(ADDI(7, 0, 1))
        asm.emit(SW(7, 6, gpuirq.GPU_OFF_CTRL))
        poll_status(f"{tag}D", 2)
        asm.emit(ADDI(7, 0, 2))
        asm.emit(SW(7, 6, gpuirq.GPU_OFF_CTRL))
        poll_status(f"{tag}I", 1)

    # ---- phase A: alias walk on both GPU ports ----------------------------------------
    # Sixteen patched copies of the kernel (64 bytes apart) are written first and flushed ONCE;
    # a D-cache flush costs ~12k cycles, so one per launch would dominate the test.
    template = gw_kernel_alias()
    li(asm, 22, 1 << GW_ALIAS_BITS[0])            # x22 = one-hot bit k
    li(asm, 24, 1 << (GW_ALIAS_BITS[-1] + 1))     # loop end
    asm.emit(ADDI(25, 0, GW_ALIAS_BITS[0]))       # x25 = k
    asm.emit(ADDI(26, 5, 0))                      # x26 = kernel copy
    asm.label("GA_W")
    for i, kw in enumerate(template):
        if i == GW_PATCH_WORD:
            li(asm, 13, _G_ADDI_R5_K0)
            asm.emit(SLLI(15, 25, 20))
            asm.emit(OR(13, 13, 15))              # VADDI r5, r0, k
            asm.emit(SW(13, 26, 4 * i))
        else:
            li(asm, 7, kw)
            asm.emit(SW(7, 26, 4 * i))
    asm.emit(ADDI(26, 26, GW_COPY_STRIDE))
    asm.emit(SLLI(22, 22, 1))
    asm.emit(ADDI(25, 25, 1))
    br(asm, BNE, 22, 24, "GA_W")
    flush_dcache(asm, "GAFL")
    li(asm, 22, 1 << GW_ALIAS_BITS[0])
    asm.emit(ADDI(26, 5, 0))
    asm.label("GA_L")
    asm.emit(OR(14, 26, 22))
    asm.emit(SW(14, 6, gpuirq.GPU_OFF_KERNEL_PC))  # KERNEL_PC = copy | (1 << k)
    run_kernel("GA")
    asm.emit(ADDI(26, 26, GW_COPY_STRIDE))
    asm.emit(SLLI(22, 22, 1))
    br(asm, BNE, 22, 24, "GA_L")
    asm.label("GA_DONE")
    asm.emit(NOP)

    # ---- phases B..E: one fresh kernel each, fetched from its plain address -----------------
    for name, kernel in (("GB", gw_kernel_rom_read()), ("GC", gw_kernel_periph()),
                         ("GD", gw_kernel_rom_write()), ("GE", gw_kernel_decerr())):
        write_kernel(kernel)
        flush_dcache(asm, f"{name}FL")
        asm.emit(SW(5, 6, gpuirq.GPU_OFF_KERNEL_PC))
        run_kernel(name)
        asm.label(f"{name}_DONE")
        asm.emit(NOP)
    flush_dcache(asm, "GFIN")
    jmp(asm, "PASS")
    tail(asm)


IMAGES = {
    "irq_spi": (build_irq_spi, ("ISR", "MAIN", "PASS", "FAIL", "TIMER_ARMED", "SPI_ARMED")),
    "pll_prog": (build_pll_prog, ("MAIN", "PASS", "FAIL", "PLL_RESET_OK", "PLL1_A",
                                  "PLL2_PROGRAMMED", "PLL1_B")),
    "gpu_iso": (build_gpu_iso, ("MAIN", "PASS", "FAIL", "GPU_DONE", "GPU_OFF", "GPU_ON",
                                "GPU_RELAUNCHED", "IRQ_CLR")),
    "dma_walk": (build_dma_walk, ("MAIN", "PASS", "FAIL", "ALIAS_DONE", "ROM_DONE",
                                  "DECERR_DONE", "UNAL_DONE")),
    "gpu_walk": (build_gpu_walk, ("MAIN", "PASS", "FAIL", "GA_DONE", "GB_DONE", "GC_DONE",
                                  "GD_DONE", "GE_DONE")),
}


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    addr_lines = ["# Auto-generated by gen_integ_hex.py -- do not edit.\n"]
    for name, (builder, wanted) in IMAGES.items():
        asm = Assembler(origin=ROM_BASE)
        builder(asm)
        words = asm.resolve()
        assert len(words) <= ROM_WORDS, f"{name}: {len(words)} words > {ROM_WORDS}"
        for lab in wanted:
            assert lab in asm.labels, f"{name}: label {lab!r} missing"
        with open(os.path.join(out_dir, f"{name}.hex"), "w") as f:
            for w in words + [NOP] * (ROM_WORDS - len(words)):
                f.write(f"{w:08x}\n")
        print(f"{name}: {len(words)} words")
        for lab in wanted:
            addr_lines.append(f"{name.upper()}_{lab} = 0x{asm.labels[lab]:08x}\n")
    consts = {
        "VAR_WI": VAR_WI, "OFF_LOG_MCAUSE": OFF_LOG_MCAUSE, "OFF_LOG_PEND": OFF_LOG_PEND,
        "OFF_LOG_DATA": OFF_LOG_DATA, "MCAUSE_MTI": MCAUSE_MTI, "MCAUSE_MEI": MCAUSE_MEI,
        "UART_TX_BYTE": UART_TX_BYTE, "SPI_TX_BYTE": SPI_TX_BYTE,
        "SPI_SLAVE_RESP": SPI_SLAVE_RESP, "PLL1_VAL_A": PLL1_VAL_A, "PLL2_VAL": PLL2_VAL,
        "PLL1_VAL_B": PLL1_VAL_B, "SPI_CLK_DIV": SPI_CLK_DIV,
        "WALK_SRC_A": WALK_SRC_A, "WALK_SRC_B": WALK_SRC_B, "WALK_SRC_ROM": WALK_SRC_ROM,
        "WALK_DST": WALK_DST, "WALK_SCRATCH": WALK_SCRATCH,
        "WALK_ROM_FILL_SEED": WALK_ROM_FILL_SEED, "WALK_ROM_FILL_STEP": WALK_ROM_FILL_STEP,
        "WALK_ROM_FILL_WORDS": WALK_ROM_FILL_WORDS,
        "WALK_UNAL_DST": WALK_UNAL_DST, "WALK_N_UNAL": len(WALK_UNAL_OFFS),
        "WALK_N_ALIAS": len(WALK_ALIAS_BITS), "WALK_N_ROM_COPIES": len(WALK_ROM_COPIES),
        "WALK_ROM_BEATS": sum(n // 4 for n, _ in WALK_ROM_COPIES),
        "GW_KBASE": GW_KBASE, "GW_SRC": GW_SRC, "GW_LD_OFF": GW_LD_OFF, "GW_ST_OFF": GW_ST_OFF,
        "GW_SCR_B": GW_SCR_B, "GW_SCR_C": GW_SCR_C, "GW_TIMER_CMP": GW_TIMER_CMP,
        "GW_ROM_WR": GW_ROM_WR, "GW_DATA_BASE": GW_DATA_BASE, "GW_N_ALIAS": len(GW_ALIAS_BITS),
        "GW_ALIAS_LO": GW_ALIAS_BITS[0], "GW_COPY_STRIDE": GW_COPY_STRIDE,
    }
    for k, v in consts.items():
        addr_lines.append(f"{k} = 0x{v:x}\n" if v > 255 else f"{k} = {v}\n")
    with open(os.path.join(out_dir, "integ_fw_addrs.py"), "w") as f:
        f.writelines(addr_lines)


if __name__ == "__main__":
    main()
