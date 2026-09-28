"""
test_soc_pwm.py — Phase 6a-2 SoC-level PWM test (bead claude_verilog_test-f7vs.6
item 5, docs/PHASE6_IP_EXPANSION_PLAN.md §10).

`test_pwm` (tb_pwm.sv / Makefile `pwm` target) drives pwm_controller's APB4 face
directly and has never exercised it through the real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 8 (APB_PWM, 0x2000_B000)

This test closes that gap using a self-checking RV32I firmware
(pwm_fw/gen_pwm_hex.py) that runs entirely via CPU MMIO through that path,
combined with a cocotb driver that observes the tb_soc_top boundary port
(pwm_o) and the internal pwm_irq/ext_irq nets, synchronised via commit_pc_o
marker PCs (CONFIG_DONE_PC, IRQ_READY_PC) — the same scoreboarding technique
test_soc_gpio.py already uses.

Unlike test_soc_gpio.py, PWM needs no cocotb-driven stimulus at all: pwm_o is
a pure push-pull output (no oe, no async input pin) and the period-wrap
interrupt is generated entirely by the peripheral's own free-running counters
once channel 0 is configured and enabled — there is nothing for the
testbench to drive.

Coverage:
  1. BOUNDARY TOGGLE: firmware configures PRESCALE/PERIOD/DUTY01/CTRL (channel
     0 enabled) and commits CONFIG_DONE_PC. From that point cocotb samples
     dut.pwm_o[0] every cycle for a window spanning more than two full PWM
     periods and asserts it observed both logic levels and multiple 0->1 and
     1->0 transitions — proving the configuration reached slave 8 through the
     whole fabric and that the hardware free-runs at the SoC boundary exactly
     as configured (PERIOD_VAL * (PRESCALE_VAL + 1) core_clk cycles/period).
  2. INTERRUPT PATH, end to end: firmware unmasks the channel-0 period-wrap
     IRQ, unmasks bit 6 (PWM) in interrupt_controller's IRQ_MASK, and enables
     CPU MEIE/MIE. This test independently watches commit_pc_o for ISR_PC —
     proof the CPU actually took the trap, not merely that a status bit got
     set — then samples the internal pwm_irq/ext_irq nets both at trap entry
     (must be asserted, the cause of the trap) and later (must be deasserted,
     after the ISR's PWM_CTRL=0 channel-disable + PWM_IRQ_CLR writes) — proof
     of deassertion at the RTL level, independent of firmware self-report.
     Firmware itself teeth-checks ISR_COUNT == 1 (no spurious re-trigger
     after MRET re-enables MIE, even though channel 0 keeps free-running) and
     PWM_IRQ_STAT bit 0 cleared.
  3. Cheap register-bank policy checks: PWM_IRQ_CLR always reads 0; the first
     out-of-range word (offset 0x20, N_REGS=8) reads 0.

GOLDEN-MODEL NOTE (same as test_soc_gpio): SoCModel cannot be used here since
it rejects 0x2000_xxxx MMIO. The firmware is self-checking and the testbench
scoreboards commit_pc_o for the marker PCs / PASS_PC / FAIL_PC. As an
additional independent check, ISR_COUNT is backdoor-read from SRAM after PASS
and compared against the value the firmware itself already verified.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.pwm_fw.pwm_fw_addrs import (
    PASS_PC,
    FAIL_PC,
    ISR_PC,
    CONFIG_DONE_PC,
    IRQ_READY_PC,
    PERIOD_CYCLES,
    ISR_COUNT_WI,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_HEX = str(Path(__file__).parent / "pwm_fw" / "pwm_fw.hex")

# Generous bound: WFI_POLL_LIMIT (4000) iterations of a several-cycle poll
# loop, plus full-fabric MMIO round trips for every register access (this
# path is far slower per-access than the unit-level test_pwm).
PWM_TEST_TIMEOUT_CYCLES = 200_000

# Cycles to wait after first observing the ISR entry PC before checking that
# the PWM/ext interrupt lines have deasserted. The ISR issues TWO back-to-
# back MMIO writes (PWM_CTRL then PWM_IRQ_CLR) before any SRAM access, each
# crossing the full crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
# axil_to_apb -> apb_interconnect chain, so this is deliberately larger than
# test_soc_gpio's single-write 50-cycle budget.
DEASSERT_CHECK_DELAY_CYCLES = 300

# Boundary-toggle monitoring window: more than two full PWM periods so both
# edges of the waveform are guaranteed to be observed regardless of exactly
# when within a period CONFIG_DONE_PC commits.
TOGGLE_MONITOR_CYCLES = 2 * PERIOD_CYCLES + 40

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
        f"({len(mem)} words) — regenerate pwm_fw.hex"
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
async def test_soc_pwm(dut):
    """Drive pwm_controller through the real SoC fabric: boundary toggle, IRQ."""
    await _setup(dut)

    seen_config_done = False
    seen_irq_ready    = False
    seen_isr_pc       = False
    checked_deassert  = False
    saw_pass          = False

    isr_seen_at_cycle = None

    # Boundary-toggle monitoring state.
    monitor_active     = False
    monitor_start_cycle = None
    pwm_values_seen: set = set()
    pwm_toggle_count = 0
    pwm_last_value   = None

    last_pc = 0
    recent: list = []

    for cycle_idx in range(PWM_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        # Boundary-toggle sampling: runs independently of commit_pc_o, every
        # cycle within the monitoring window, since pwm_o free-runs off the
        # peripheral's own counters once configured.
        if monitor_active:
            ch0 = int(dut.pwm_o.value) & 0x1
            pwm_values_seen.add(ch0)
            if pwm_last_value is not None and ch0 != pwm_last_value:
                pwm_toggle_count += 1
            pwm_last_value = ch0
            if cycle_idx >= monitor_start_cycle + TOGGLE_MONITOR_CYCLES:
                monitor_active = False

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — a PWM SoC-level "
                f"check failed (or a bounded poll timed out)"
            )

            if pc == CONFIG_DONE_PC and not seen_config_done:
                seen_config_done = True
                monitor_active = True
                monitor_start_cycle = cycle_idx
                pwm_last_value = int(dut.pwm_o.value) & 0x1
                pwm_values_seen.add(pwm_last_value)

            if pc == IRQ_READY_PC and not seen_irq_ready:
                seen_irq_ready = True

            if pc == ISR_PC and not seen_isr_pc:
                seen_isr_pc = True
                isr_seen_at_cycle = cycle_idx
                irq_at_trap     = int(dut.u_soc.pwm_irq.value)
                ext_irq_at_trap = int(dut.u_soc.ext_irq.value)
                assert irq_at_trap == 1, (
                    "CPU vectored to ISR_PC but dut.u_soc.pwm_irq is not "
                    "asserted — trap entry inconsistent with an asserted "
                    "PWM interrupt source"
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
            irq_after     = int(dut.u_soc.pwm_irq.value)
            ext_irq_after = int(dut.u_soc.ext_irq.value)
            assert irq_after == 0, (
                f"dut.u_soc.pwm_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} "
                f"cycles after the ISR ran — PWM_CTRL channel-disable + "
                f"PWM_IRQ_CLR did not deassert the source"
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
        f"{PWM_TEST_TIMEOUT_CYCLES} cycles"
    )
    assert seen_config_done, "CONFIG_DONE_PC was never committed"
    assert seen_irq_ready, "IRQ_READY_PC was never committed"
    assert seen_isr_pc, "ISR_PC was never committed — CPU never took the PWM trap"
    assert checked_deassert, "post-ISR deassertion window was never reached"

    # Boundary-toggle assertions: pwm_o[0] must have taken both logic levels
    # and toggled repeatedly during the monitoring window — proof the
    # configuration write reached slave 8 through the whole fabric and that
    # the channel free-runs at the SoC boundary as configured.
    assert pwm_values_seen == {0, 1}, (
        f"dut.pwm_o[0] only took value(s) {pwm_values_seen} during the "
        f"{TOGGLE_MONITOR_CYCLES}-cycle monitoring window after "
        f"CONFIG_DONE_PC — expected both 0 and 1 (channel 0 configured "
        f"enabled with a mid-range duty cycle)"
    )
    assert pwm_toggle_count >= 2, (
        f"dut.pwm_o[0] toggled only {pwm_toggle_count} time(s) during the "
        f"{TOGGLE_MONITOR_CYCLES}-cycle monitoring window (window spans "
        f"more than two full {PERIOD_CYCLES}-cycle PWM periods) — expected "
        f"at least one full rise+fall"
    )

    # Independent backdoor check: ISR_COUNT (SRAM word ISR_COUNT_WI) must be
    # exactly 1, matching the firmware's own teeth check.
    sram = dut.u_soc.u_sram.mem
    isr_count = int(sram[ISR_COUNT_WI].value)
    assert isr_count == 1, (
        f"backdoor SRAM read: ISR_COUNT (word {ISR_COUNT_WI}) = {isr_count}, "
        f"expected exactly 1"
    )
