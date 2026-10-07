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
  so gpu_irq_o is HIGH and stays high.  PMU CTRL=GPU_OFF (0x2000_8000) then isolates it:
  gpu_irq_raw stays 1 (state kept: the domain's clock is gated before its reset asserts)
  while gpu_irq_o must read 0.  PMU CTRL=NORMAL un-isolates it and gpu_irq_o must come
  back.  GPU registers are never touched while isolated (gif_axil_arvalid is clamped, a
  read would hang).

Registers: IMAGE 1 MAIN uses x1-x23 (x2=VAR_BASE x3=TIMER x4=UART x5=SPI x6=DMA x7=IRQ);
the ISR uses only x24-x31.
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (  # noqa: E402
    ADDI, ADD, ANDI, SW, LW, BNE, BEQ, JAL, EBREAK, SLLI, CSRRW, CSRRS, MRET,
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
    for i in range(gpuirq.N_SRC_WORDS):
        asm.emit(ADDI(7, 0, (i + 1) * 0x10))
        asm.emit(SW(7, 3, i * 4))
    flush_dcache(asm, "FL1")
    for i, kw in enumerate(gpuirq.build_gpu_kernel()):
        li(asm, 7, kw)
        asm.emit(SW(7, 5, i * 4))
    flush_dcache(asm, "FL2")
    asm.emit(SW(5, 6, gpuirq.GPU_OFF_KERNEL_PC))
    asm.emit(ADDI(7, 0, 1))
    for off in (gpuirq.GPU_OFF_GRID_X, gpuirq.GPU_OFF_GRID_Y, gpuirq.GPU_OFF_GRID_Z,
                gpuirq.GPU_OFF_BLOCK_Y, gpuirq.GPU_OFF_BLOCK_Z):
        asm.emit(SW(7, 6, off))
    asm.emit(ADDI(7, 0, 8))
    asm.emit(SW(7, 6, gpuirq.GPU_OFF_BLOCK_X))
    asm.emit(ADDI(7, 0, 0x05))                     # irq_enable | launch
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

    asm.emit(LW(7, 6, gpuirq.GPU_OFF_STATUS))      # done bit survived the power cycle
    asm.emit(ANDI(7, 7, 2))
    br(asm, BEQ, 7, 0, "FAIL")
    asm.emit(ADDI(7, 0, 1))
    asm.label("IRQ_CLR")
    asm.emit(SW(7, 6, gpuirq.GPU_OFF_IRQ_CLR))
    flush_dcache(asm, "FL3")
    jmp(asm, "PASS")
    tail(asm)


IMAGES = {
    "irq_spi": (build_irq_spi, ("ISR", "MAIN", "PASS", "FAIL", "TIMER_ARMED", "SPI_ARMED")),
    "pll_prog": (build_pll_prog, ("MAIN", "PASS", "FAIL", "PLL_RESET_OK", "PLL1_A",
                                  "PLL2_PROGRAMMED", "PLL1_B")),
    "gpu_iso": (build_gpu_iso, ("MAIN", "PASS", "FAIL", "GPU_DONE", "GPU_OFF", "GPU_ON",
                                "IRQ_CLR")),
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
    }
    for k, v in consts.items():
        addr_lines.append(f"{k} = 0x{v:x}\n" if v > 255 else f"{k} = {v}\n")
    with open(os.path.join(out_dir, "integ_fw_addrs.py"), "w") as f:
        f.writelines(addr_lines)


if __name__ == "__main__":
    main()
