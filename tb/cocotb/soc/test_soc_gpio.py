"""
test_soc_gpio.py — Phase 6a SoC-level GPIO test (bead claude_verilog_test-8qn4 item 1).

`test_gpio` (tb_gpio.sv / Makefile `gpio` target) drives gpio_controller's APB4
face directly and has never exercised it through the real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 7 (APB_GPIO, 0x2000_A000)

This test closes that gap using a self-checking RV32I firmware
(gpio_fw/gen_gpio_hex.py) that runs entirely via CPU MMIO through that path,
combined with a cocotb driver that observes/drives the tb_soc_top boundary
ports (gpio_out_o, gpio_oe_o, gpio_in_i) at three points synchronised via
commit_pc_o marker PCs (OUTPUT_DONE_PC, INPUT_READY_PC, IRQ_READY_PC) — the
same scoreboarding technique test_periph_loopback / test_cpu_gpu_irq already
use for PASS_PC/FAIL_PC.

Coverage:
  1. OUTPUT PATH: firmware writes GPIO_DIR/GPIO_DATA_OUT; test asserts
     gpio_oe_o/gpio_out_o at the SoC boundary match — proves the write
     reached slave 7 through the whole fabric.
  2. INPUT PATH: test drives gpio_in_i; firmware reads GPIO_DATA_IN back and
     self-checks in a bounded poll loop (naturally tolerant of the pin's
     3-clock-edge synchroniser latency: 2-stage cdc_2ff_sync + 1
     register-bank cycle).
  3. INTERRUPT PATH, end to end: firmware unmasks a rising-edge interrupt on
     one GPIO pin, unmasks bit 5 (GPIO) in interrupt_controller's IRQ_MASK,
     and enables CPU MEIE/MIE. The test toggles gpio_in_i and this test
     independently watches commit_pc_o for ISR_PC — proof the CPU actually
     took the trap, not merely that a status bit got set — then samples the
     internal gpio_irq/ext_irq nets both at trap entry (must be asserted,
     the cause of the trap) and ~50 cycles later (must be deasserted, after
     the ISR's GPIO_IRQ_CLR write) — proof of deassertion at the RTL level,
     independent of firmware self-report. Firmware itself teeth-checks
     ISR_COUNT == 1 (no spurious re-trigger after MRET re-enables MIE) and
     GPIO_IRQ_STAT bit cleared.
  4. Cheap register-bank policy checks: GPIO_IRQ_CLR always reads 0; the
     first out-of-range word (offset 0x20, N_REGS=8) reads 0.

GOLDEN-MODEL NOTE (same as test_periph_loopback): SoCModel cannot be used
here since it rejects 0x2000_xxxx MMIO. The firmware is self-checking and
the testbench scoreboards commit_pc_o for the marker PCs / PASS_PC / FAIL_PC.
As an additional independent check, ISR_COUNT is backdoor-read from SRAM
after PASS and compared against the value the firmware itself already
verified.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.gpio_fw.gpio_fw_addrs import (
    PASS_PC,
    FAIL_PC,
    ISR_PC,
    OUTPUT_DONE_PC,
    INPUT_READY_PC,
    IRQ_READY_PC,
    TEST_DIR_VAL,
    TEST_DATA_VAL,
    INPUT_MASK,
    IRQ_PIN_IDX,
    ISR_COUNT_WI,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_HEX = str(Path(__file__).parent / "gpio_fw" / "gpio_fw.hex")

# Generous bound: WFI_POLL_LIMIT (2000) iterations of a several-cycle poll
# loop, plus INPUT poll + full-fabric MMIO round trips for every register
# access (this path is far slower per-access than the unit-level test_gpio).
GPIO_TEST_TIMEOUT_CYCLES = 200_000

# Cycles to wait after first observing the ISR entry PC before checking that
# the GPIO/ext interrupt lines have deasserted. Generous vs. a single APB
# MMIO round trip through the full crossbar -> axi4_to_axilite ->
# axi_lite_interconnect -> axil_to_apb -> apb_interconnect chain.
DEASSERT_CHECK_DELAY_CYCLES = 50

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


_FW_WORDS: list | None = None


def _rom_words() -> list:
    global _FW_WORDS
    if _FW_WORDS is None:
        words: list = []
        with open(_FW_HEX) as f:
            for line in f:
                tok = line.strip()
                if not tok or tok.startswith("//") or tok.startswith("@"):
                    continue
                words.append(int(tok, 16))
        _FW_WORDS = words
    return _FW_WORDS


def _load_rom(dut) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    words = _rom_words()
    assert len(words) <= len(mem), (
        f"Firmware image ({len(words)} words) exceeds boot ROM capacity "
        f"({len(mem)} words) — regenerate gpio_fw.hex"
    )
    for i, word in enumerate(words):
        mem[i].value = word


async def _setup(dut) -> None:
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
    dut.gpio_in_i.value     = 0

    _load_rom(dut)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_soc_gpio(dut):
    """Drive gpio_controller through the real SoC fabric: output, input, IRQ."""
    await _setup(dut)

    seen_output_done = False
    seen_input_ready = False
    seen_irq_ready   = False
    seen_isr_pc      = False
    checked_deassert = False
    saw_pass         = False

    isr_seen_at_cycle = None
    pending_action = None

    last_pc = 0
    recent: list = []

    for cycle_idx in range(GPIO_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)

        # Write-permitted phase: apply any action queued from the previous
        # cycle's ReadOnly observation (writes are illegal during ReadOnly).
        if pending_action == "drive_input":
            dut.gpio_in_i.value = INPUT_MASK
            pending_action = None
        elif pending_action == "drive_irq_edge":
            dut.gpio_in_i.value = INPUT_MASK | (1 << IRQ_PIN_IDX)
            pending_action = None

        await ReadOnly()

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — a GPIO SoC-level "
                f"check failed (or a bounded poll timed out)"
            )

            if pc == OUTPUT_DONE_PC and not seen_output_done:
                seen_output_done = True
                oe  = int(dut.gpio_oe_o.value)
                out = int(dut.gpio_out_o.value)
                assert oe == TEST_DIR_VAL, (
                    f"gpio_oe_o = 0x{oe:08x}, expected 0x{TEST_DIR_VAL:08x} "
                    f"after firmware wrote GPIO_DIR — write did not reach "
                    f"slave 7 through the fabric"
                )
                assert out == TEST_DATA_VAL, (
                    f"gpio_out_o = 0x{out:08x}, expected 0x{TEST_DATA_VAL:08x} "
                    f"after firmware wrote GPIO_DATA_OUT — write did not "
                    f"reach slave 7 through the fabric"
                )

            if pc == INPUT_READY_PC and not seen_input_ready:
                seen_input_ready = True
                pending_action = "drive_input"

            if pc == IRQ_READY_PC and not seen_irq_ready:
                seen_irq_ready = True
                pending_action = "drive_irq_edge"

            if pc == ISR_PC and not seen_isr_pc:
                seen_isr_pc = True
                isr_seen_at_cycle = cycle_idx
                irq_at_trap     = int(dut.u_soc.gpio_irq.value)
                ext_irq_at_trap = int(dut.u_soc.ext_irq.value)
                assert irq_at_trap == 1, (
                    "CPU vectored to ISR_PC but dut.u_soc.gpio_irq is not "
                    "asserted — trap entry inconsistent with an asserted "
                    "GPIO interrupt source"
                )
                assert ext_irq_at_trap == 1, (
                    "CPU vectored to ISR_PC but dut.u_soc.ext_irq is not "
                    "asserted"
                )

            if pc == PASS_PC:
                saw_pass = True
                break

        if (
            seen_isr_pc
            and not checked_deassert
            and cycle_idx >= isr_seen_at_cycle + DEASSERT_CHECK_DELAY_CYCLES
        ):
            checked_deassert = True
            irq_after     = int(dut.u_soc.gpio_irq.value)
            ext_irq_after = int(dut.u_soc.ext_irq.value)
            assert irq_after == 0, (
                f"dut.u_soc.gpio_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} "
                f"cycles after the ISR ran — GPIO_IRQ_CLR did not deassert "
                f"the source"
            )
            assert ext_irq_after == 0, (
                f"dut.u_soc.ext_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} "
                f"cycles after the ISR ran"
            )

    if not saw_pass:
        dut._log.info(
            "last_pc=0x%08x; recent committed PCs: %s",
            last_pc, " ".join(f"0x{p:08x}" for p in recent),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within "
        f"{GPIO_TEST_TIMEOUT_CYCLES} cycles"
    )
    assert seen_output_done, "OUTPUT_DONE_PC was never committed"
    assert seen_input_ready, "INPUT_READY_PC was never committed"
    assert seen_irq_ready, "IRQ_READY_PC was never committed"
    assert seen_isr_pc, "ISR_PC was never committed — CPU never took the GPIO trap"
    assert checked_deassert, "post-ISR deassertion window was never reached"

    # Independent backdoor check: ISR_COUNT (SRAM word ISR_COUNT_WI) must be
    # exactly 1, matching the firmware's own teeth check.
    sram = dut.u_soc.u_sram.mem
    isr_count = int(sram[ISR_COUNT_WI].value)
    assert isr_count == 1, (
        f"backdoor SRAM read: ISR_COUNT (word {ISR_COUNT_WI}) = {isr_count}, "
        f"expected exactly 1"
    )
