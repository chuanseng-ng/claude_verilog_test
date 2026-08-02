"""
test_cpu_gpu_irq.py — Phase 5 (M9) interrupt-driven CPU-GPU integration test.
Bead: claude_verilog_test-ov2

Verifies the complete interrupt-driven CPU-GPU data-plane handoff through
tb_soc_top:

  1. CPU programs mtvec to point at the ROM ISR, enables MEIE (mie[11])
     and MIE (mstatus[3]), and writes 0x10 to interrupt_controller IRQ_MASK
     to enable GPU IRQ source (bit 4).
  2. CPU writes 8 source words to SRAM (dirty in D-cache), flushes, writes
     and flushes the GPU kernel image.
  3. CPU launches GPU via AXI-Lite GPU ctrl register write.
  4. CPU waits in a bounded spin loop polling a flag in SRAM at ISR_FLAG_WI
     (word 200 = 0x0000_2320).  When the GPU completes, gpu_irq_o asserts,
     propagates through interrupt_controller (irq_src_i[4]) → ext_irq →
     rv32i_interrupt_ctrl (irq_valid) → trap entry: MIE cleared, mepc saved,
     mcause = 0x8000_000B (MEIP), PC → mtvec.
  5. ISR at mtvec (ROM_BASE):
       a. Clears GPU IRQ via GPU_IRQ_CLR register (deasserts gpu_irq_o).
       b. Writes 1 to ISR_FLAG_ADDR in SRAM.
       c. MRET — restores PC from mepc, MIE from MPIE.
  6. Main firmware detects the flag set, verifies ISR actually ran (teeth
     check), performs dcache_inval, reads 8 dst words, checks each == src+1.

IRQ wiring path (soc_top.sv confirmed):
  gpu_top.gpu_irq_o
    → irq_src_i[4] of interrupt_controller
    → irq_o = ext_irq (when IRQ_MASK[4]=1)
    → rv32i_cpu_top.ext_irq_i
    → rv32i_csr_file: mip[11] = MEIP
    → rv32i_interrupt_ctrl: irq_valid when mstatus_mie & mie_meie & ext_irq_i
    → trap_entry: mcause=0x8000_000B, mepc=next_PC, PC→mtvec

Teeth checks:
  - If GPU never completes (irq never fires), WFI_LOOP times out →
    firmware jumps to FAIL_PC.  The test asserts PASS_PC, so it fails.
  - If the ISR flag at SRAM word 200 is 0 after ISR_DONE, firmware
    jumps to FAIL_PC explicitly.  This rules out a spurious path where
    the loop exits due to a flag already non-zero from a prior test run
    (we zero the flag before launch).
  - Negative test: IRQ path disabled — confirms FAIL_PC is reached within
    timeout when the GPU IRQ cannot reach the CPU.

Negative test variants:
  test_cpu_gpu_irq_no_irq_enable:
    Firmware with IRQ mask left at 0 (GPU bit not enabled in irq_ctrl).
    GPU completes and sets gpu_irq_o, but interrupt_controller gates it
    (IRQ_MASK[4]=0 → masked=0 → irq_o=0 → CPU never gets MEIP).
    ISR never runs; WFI_LOOP times out; firmware reaches FAIL_PC.
    Pass criterion: FAIL_PC committed.

Architecture notes:
  - GPU_BASE = 0x2000_1000  (AXIL_GPU slot in control ring).
  - IRQ_CTRL_BASE = 0x2000_6000 (AXIL_IRQ slot).
  - SRAM addresses used here (SRC=0x2180, DST=0x21C0, KERNEL=0x2280)
    are distinct from the coherency test (SRC=0x2100, DST=0x2140,
    KERNEL=0x2200) to avoid cross-test SRAM contamination in soc_all.
  - ISR_FLAG_ADDR = SRAM word 200 = 0x0000_2320.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.cpu_gpu_irq_fw.cpu_gpu_irq_fw_addrs import (
    PASS_PC,
    FAIL_PC,
    ISR_PC,
    SRC_IDX,
    DST_IDX,
    KERNEL_IDX,
    ISR_FLAG_WI,
    N_SRC_WORDS,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2   # 500 MHz

_FW_HEX     = str(Path(__file__).parent / "cpu_gpu_irq_fw" / "cpu_gpu_irq_fw.hex")
_KERNEL_HEX = str(Path(__file__).parent / "cpu_gpu_irq_fw" / "cpu_gpu_irq_kernel.hex")

# IRQ_MASK offset within irq_ctrl AXI-Lite register bank (word 1 = offset 0x004)
IRQ_MASK_OFF = 0x004

# Timeout: the negative test (test_cpu_gpu_irq_no_irq_enable) must exhaust
# the WFI_LOOP POLL_LIMIT (50,000 iters × ~5 cycles = ~250,000 cycles) plus
# firmware setup (INIT, FLUSH1+FLUSH2+FLUSH_WAIT+INVAL_WAIT ≈ 4×2048×5 = 40k
# cycles, KWRITE, LAUNCH MMIO writes ≈ 10k cycles).  Total ≈ 300k cycles.
# Positive test (test_cpu_gpu_irq_pass) completes much earlier (ISR fires
# shortly after GPU kernel completes, kernel ≈ 30k cycles → total ≈ 100k).
# 800_000 cycles gives 2.5× headroom for the negative path.
TIMEOUT_CYCLES = 800_000

# ---------------------------------------------------------------------------
# Firmware loader helpers
# ---------------------------------------------------------------------------
_FW_WORDS_CACHE: dict = {}


def _load_hex(hex_path: str) -> list:
    if hex_path in _FW_WORDS_CACHE:
        return _FW_WORDS_CACHE[hex_path]
    words = []
    with open(hex_path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    _FW_WORDS_CACHE[hex_path] = words
    return words


def _load_rom(dut, hex_path: str) -> None:
    """Backdoor-load hex into tb_soc_top.u_soc.u_boot_rom.mem."""
    mem = dut.u_soc.u_boot_rom.mem
    for i, word in enumerate(_load_hex(hex_path)):
        mem[i].value = word


def _zero_sram_range(dut, start_wi: int, n: int) -> None:
    """Zero n SRAM words starting at word index start_wi."""
    sram = dut.u_soc.u_sram.mem
    for i in range(n):
        sram[start_wi + i].value = 0


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


async def _setup(dut, hex_path: str = _FW_HEX) -> None:
    """Start clock, idle inputs, backdoor-load firmware, apply + release reset."""
    _kill_active_tasks()

    clk_task, cpu_clk_task = start_soc_clocks(dut, CLK_PERIOD_NS)
    _active_tasks.append(clk_task)
    _active_tasks.append(cpu_clk_task)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1
    dut.spi_miso_i.value    = 0

    _load_rom(dut, hex_path)

    # Zero the ISR flag slot to guarantee the teeth check is meaningful.
    # (SRAM retains state across cocotb tests within the same Vtop binary.)
    _zero_sram_range(dut, ISR_FLAG_WI, 1)
    # Also zero SRAM dst region to ensure stale values from a prior run don't
    # cause a false PASS in the verify step.
    _zero_sram_range(dut, DST_IDX, N_SRC_WORDS)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


# ---------------------------------------------------------------------------
# PC-scoreboard runner
# ---------------------------------------------------------------------------
async def _run_to_ebreak(dut, *, test_name: str) -> tuple[bool, bool, int]:
    """
    Run until PASS_PC or FAIL_PC is committed, or timeout.

    Returns (saw_pass, saw_fail, last_pc).
    """
    saw_pass = False
    saw_fail = False
    last_pc  = 0

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            if pc == PASS_PC:
                saw_pass = True
                break
            if pc == FAIL_PC:
                saw_fail = True
                break

    return saw_pass, saw_fail, last_pc


# ---------------------------------------------------------------------------
# Test 1 — positive path: interrupt-driven GPU completion
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_cpu_gpu_irq_pass(dut):
    """
    Positive path: CPU enables GPU IRQ, launches kernel, ISR fires on
    completion, firmware reads corrected dst values and reaches PASS_PC.

    Firmware steps:
      A. Install ISR at mtvec = ROM_BASE = 0x0000_1000
      B. Enable MEIE (mie[11]) and MIE (mstatus[3])
      C. Enable GPU IRQ in interrupt_controller (IRQ_MASK bit 4 = 0x10)
      D. Zero ISR flag; write 8 src words to SRAM; flush D-cache
      E. Write GPU kernel to SRAM; flush D-cache
      F. Launch GPU (CTRL=0x05: irq_enable|launch)
      G. Spin checking ISR flag (bounded POLL_LIMIT iters)
         — IRQ fires: trap to mtvec, ISR clears IRQ, sets flag, MRET
      H. Assert ISR flag == 1 (teeth: ISR actually ran)
      I. CSRW 0x7C1 (dcache_inval); read 8 dst words; compare src+1
      J. PASS_PC if all match; FAIL_PC on mismatch or poll timeout

    Pass criteria: PASS_PC committed + SRAM backdoor check dst[i] == src[i]+1
    + ISR_FLAG_WI == 1 (ISR ran).
    """
    await _setup(dut)

    saw_pass, saw_fail, last_pc = await _run_to_ebreak(
        dut, test_name="test_cpu_gpu_irq_pass"
    )

    if not saw_pass:
        dut._log.error(
            "test_cpu_gpu_irq_pass: last_pc=0x%08x  saw_fail=%s",
            last_pc, saw_fail
        )
        try:
            sram = dut.u_soc.u_sram.mem
            flag = int(sram[ISR_FLAG_WI].value)
            dut._log.error("  ISR_FLAG (SRAM[%d]) = %d  (expect 1)", ISR_FLAG_WI, flag)
            for i in range(N_SRC_WORDS):
                sv = int(sram[SRC_IDX + i].value)
                dv = int(sram[DST_IDX + i].value)
                dut._log.error(
                    "  SRAM src[%d]=0x%08x  dst[%d]=0x%08x  exp=0x%08x",
                    i, sv, i, dv, sv + 1
                )
        except Exception as exc:
            dut._log.error("  DBG backdoor read failed: %s", exc)

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within "
        f"{TIMEOUT_CYCLES} cycles "
        f"(last_pc=0x{last_pc:08x}, saw_fail={saw_fail})"
    )

    # Backdoor checks
    sram = dut.u_soc.u_sram.mem

    # 1. ISR-ran teeth check: ISR_FLAG_WI must be 1
    isr_flag = int(sram[ISR_FLAG_WI].value)
    assert isr_flag == 1, (
        f"Teeth check failed: ISR_FLAG (SRAM word {ISR_FLAG_WI}) = {isr_flag}, "
        f"expected 1. The ISR did not run even though PASS_PC was committed — "
        f"indicates the WFI loop exited via a path that bypassed the ISR check."
    )

    # 2. SRAM dst correctness check: dst[i] == src[i] + 1
    for i in range(N_SRC_WORDS):
        src_val  = int(sram[SRC_IDX + i].value)
        dst_val  = int(sram[DST_IDX + i].value)
        expected = src_val + 1
        assert dst_val == expected, (
            f"Backdoor SRAM check failed at word {i}: "
            f"dst=0x{dst_val:08x} expected=0x{expected:08x} "
            f"(src=0x{src_val:08x})"
        )


# ---------------------------------------------------------------------------
# Test 2 — negative: GPU IRQ not enabled in interrupt_controller
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_cpu_gpu_irq_no_irq_enable(dut):
    """
    Negative teeth test: GPU IRQ source not enabled in interrupt_controller.

    We patch the firmware ROM after reset: we find the SW instruction that
    writes to IRQ_MASK and NOP it out.  With IRQ_MASK[4]=0, the
    interrupt_controller gates gpu_irq_o — irq_o stays 0 — the CPU never
    sees MEIP — the ISR never fires.

    The WFI_LOOP hits POLL_LIMIT and jumps to FAIL_PC.

    Pass criterion: FAIL_PC committed (not PASS_PC).
    """
    await _setup(dut)

    # Find the SW that writes GPU_IRQ_MASK_BIT (0x10 = 16) to x11+0x004.
    # Encoding: SW x7, 4(x11)
    #   rs2=x7=7, rs1=x11=11, imm12=4, funct3=2, opcode=0b0100011
    # SW format: imm[11:5] | rs2 | rs1 | funct3 | imm[4:0] | opcode
    # imm=4: imm[11:5]=0b0000000, imm[4:0]=0b00100
    # = (0<<25)|(7<<20)|(11<<15)|(2<<12)|(4<<7)|0x23 = 0x0075a223
    SW_IRQ_MASK = 0x0075a223
    NOP_INSTR   = 0x00000013

    fw     = _load_hex(_FW_HEX)
    mem    = dut.u_soc.u_boot_rom.mem

    idx = None
    for i, w in enumerate(fw):
        if w == SW_IRQ_MASK:
            idx = i
            break

    assert idx is not None, (
        f"Could not locate SW x7, 4(x11) (0x{SW_IRQ_MASK:08x}) in firmware. "
        f"Check that the IRQ_MASK write instruction encoding matches."
    )

    # NOP-out the IRQ_MASK write (GPU IRQ source stays masked)
    mem[idx].value = NOP_INSTR

    saw_pass, saw_fail, last_pc = await _run_to_ebreak(
        dut, test_name="test_cpu_gpu_irq_no_irq_enable"
    )

    assert saw_fail and not saw_pass, (
        f"Expected FAIL_PC (0x{FAIL_PC:08x}) when GPU IRQ is not enabled in "
        f"interrupt_controller, but got: saw_pass={saw_pass}, "
        f"saw_fail={saw_fail}, last_pc=0x{last_pc:08x}. "
        f"This means the ISR fired despite the IRQ mask being 0, which would "
        f"indicate an IRQ wiring bug."
    )

    # Confirm ISR did NOT run
    sram    = dut.u_soc.u_sram.mem
    isr_flag = int(sram[ISR_FLAG_WI].value)
    assert isr_flag == 0, (
        f"ISR_FLAG is {isr_flag} but should be 0 — ISR ran even though "
        f"IRQ_MASK[4] was 0. This is an RTL bug in the interrupt_controller "
        f"or interrupt routing."
    )
