"""
test_soc_trng.py — Phase 6a-4 SoC-level TRNG test (bead claude_verilog_test-f7vs.8 steps 4-5,
docs/PHASE6_IP_EXPANSION_PLAN.md §10).

`test_trng` (tb_trng.sv / Makefile `trng` target) drives trng's APB4 face directly and has never
exercised it through the real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 10 (APB_TRNG, 0x2000_D000)

nor its IRQ into interrupt_controller bit 8. Firmware comes from a committed pure-Python
hand-assembler (trng_fw/gen_trng_hex.py) — no riscv32 cross toolchain, so the suite is CI-safe.
Synchronisation and scoring are by commit_pc_o marker PCs, the technique test_soc_wdt.py /
test_soc_pwm.py use.

One test, one image, two phases (see the generator header for the firmware side).

PHASE 1 — polled, CTRL.IE = 0, SEED1
  Firmware reads STATUS (must be exactly 0x8), reads DATA on the empty FIFO (0), checks the SEED
  reset value, writes and reads back SEED1, enables, waits for FIFO-full (STATUS == 0xB) and pops
  PHASE1_WORDS words into SRAM. Scored here:
    * VALUE-EXACT: the words firmware popped equal tb/models/trng_lfsr_model.py for SEED1, in
      order. The words are a pure function of the seed, so this pins the SEED write, the
      enable-edge sampling, and every DATA read as a pop, all through the real fabric — not merely
      "some data arrived".
    * TRNG_STATUS[3] (INSECURE) read 1 in every STATUS value firmware saw. That bit is the only
      marker that the default build is a deterministic LFSR rather than entropy; it must be
      visible to firmware, and here it demonstrably is.
    * the IE gate: the FIFO holds data for a long stretch of phase 1 (level_q >= THRESHOLD), the
      interrupt path is armed the whole time, and trng_irq / ext_irq stay LOW — a single trap here
      would mean CTRL.IE is not gating irq_o.

PHASE 2 — interrupt driven, SEED2, THRESHOLD = 2
  Firmware disables, writes SEED2, then ONE write CTRL = EN | IE | THRESHOLD<<2. Scored here:
    * trng_irq rises exactly when the FIFO level reaches THRESHOLD (level_q == 2 on the rising
      edge) — the threshold field crossed the fabric, and the IRQ is the level source, not a
      pulse.
    * trng_irq -> interrupt_controller[8] -> CPU MEIP: the CPU vectors (ISR_PC commits) with
      trng_irq AND ext_irq asserted. EXACTLY ONE trap: the ISR clears the level source with a
      single CTRL write (IE cleared), so there is no clear-then-disable window for the condition
      to re-fire in (the PWM L2 lesson), and a stale level-held IRQ would produce a second trap.
    * after the ISR, trng_irq and ext_irq deassert and stay low.
    * VALUE-EXACT: the phase-2 words popped after the trap equal the model for SEED2 — which also
      proves the enable edge restarted the session (fresh LFSR load, FIFO cleared) rather than
      continuing phase 1's stream.
    * backdoor SRAM: ISR_COUNT == 1; the STATUS the ISR saw had data-ready and INSECURE set.

GOLDEN-MODEL NOTE (same as test_soc_gpio / test_soc_pwm / test_soc_wdt): SoCModel cannot be used
here since it rejects 0x2000_xxxx MMIO. The firmware is self-checking and the testbench
scoreboards commit_pc_o for the marker PCs / PASS_PC / FAIL_PC; the entropy words are checked
against trng_lfsr_model.py instead.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.trng_fw.trng_fw_addrs import (
    PASS_PC,
    FAIL_PC,
    ISR_PC,
    IRQ_READY_PC,
    P1_ENABLED_PC,
    P1_DONE_PC,
    P2_ENABLED_PC,
    SEED_RESET_VAL,
    SEED1,
    SEED2,
    PHASE1_WORDS,
    PHASE2_WORDS,
    THRESHOLD,
    RES_BASE_WI,
    RES_ISR_COUNT,
    RES_ISR_STATUS,
    RES_STATUS_PRE,
    RES_EMPTY_READ,
    RES_SEED_RESET,
    RES_SEED_READBACK,
    RES_STATUS_FULL,
    RES_P1_WORDS,
    RES_P2_WORDS,
)
from tb.models.trng_lfsr_model import TrngLfsrModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_HEX = str(Path(__file__).parent / "trng_fw" / "trng_fw.hex")

# ~12 words at >=128 raw cycles each, MMIO polling over the fabric, plus the 600-cycle settle and
# 2000-cycle D-cache-flush delay loops. Measured well under this; headroom for fabric latency.
TRNG_TEST_TIMEOUT_CYCLES = 80_000

# Cycles after the ISR entry before checking that the IRQ lines have deasserted. The ISR issues a
# STATUS read, a CTRL write, SRAM stores and a CTRL read-back before MRET; comfortably larger.
DEASSERT_CHECK_DELAY_CYCLES = 400

# Minimum number of phase-1 cycles the FIFO must hold >= THRESHOLD words with the IRQ gated off,
# for the "IE gate" observation to be non-vacuous.
MIN_GATED_DATA_CYCLES = 200

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _read_hex(path: str) -> list:
    words: list = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, hex_path: str) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    words = _read_hex(hex_path)
    assert len(words) <= len(mem), (
        f"Firmware image {hex_path} ({len(words)} words) exceeds boot ROM capacity "
        f"({len(mem)} words) — regenerate with trng_fw/gen_trng_hex.py"
    )
    for i, word in enumerate(words):
        mem[i].value = word


async def _setup(dut, hex_path: str) -> None:
    """Start clocks, idle inputs, backdoor-load firmware, apply + release reset."""
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

    _load_rom(dut, hex_path)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


def _i(sig) -> int:
    return int(sig.value)


@cocotb.test()
async def test_soc_trng(dut):
    """Pop model-exact LFSR words and take the threshold IRQ through the real SoC fabric."""
    await _setup(dut, _FW_HEX)

    seen = {"irq_ready": False, "p1_enabled": False, "p1_done": False, "p2_enabled": False}
    phase = 0                        # 0 = pre-arm, 1 = phase 1 (IE=0), 2 = phase 2 (IE=1)
    isr_entries: list = []           # (cycle, trng_irq, ext_irq) at each ISR_PC commit
    deassert_checked = False
    saw_pass = False
    prev_irq = 0
    irq_rise_cycle = None
    irq_rise_level = None
    p1_cycle = p2_cycle = None
    gated_data_cycles = 0            # phase 1: FIFO >= THRESHOLD, IRQ armed but gated off
    post_isr_irq_high = 0            # trng_irq/ext_irq high after the deassert check

    last_pc = 0
    recent: list = []

    for cycle_idx in range(TRNG_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        trng_irq = _i(dut.u_soc.trng_irq)
        ext_irq = _i(dut.u_soc.ext_irq)
        level = _i(dut.u_soc.u_trng.level_q)

        # Boundary edge, independent of commit_pc_o.
        if trng_irq and not prev_irq and irq_rise_cycle is None:
            irq_rise_cycle = cycle_idx
            irq_rise_level = level
        prev_irq = trng_irq

        # Phase 1 (IRQ path armed, CTRL.IE == 0): nothing may fire, however full the FIFO is.
        if phase == 1:
            assert trng_irq == 0, (
                f"trng_irq asserted at cycle {cycle_idx} in phase 1 with CTRL.IE == 0 "
                f"(fifo level {level}) — the IE gate is broken"
            )
            assert ext_irq == 0, f"ext_irq asserted at cycle {cycle_idx} in phase 1"
            if level >= THRESHOLD:
                gated_data_cycles += 1

        if phase == 2 and deassert_checked:
            if trng_irq or ext_irq:
                post_isr_irq_high += 1

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — a TRNG SoC-level check failed "
                f"(STATUS/DATA/SEED value, FIFO-full poll, or a bounded poll timed out)"
            )

            if pc == IRQ_READY_PC and not seen["irq_ready"]:
                seen["irq_ready"] = True
                phase = 1
            if pc == P1_ENABLED_PC and not seen["p1_enabled"]:
                seen["p1_enabled"] = True
                p1_cycle = cycle_idx
            if pc == P1_DONE_PC and not seen["p1_done"]:
                seen["p1_done"] = True
            if pc == P2_ENABLED_PC and not seen["p2_enabled"]:
                seen["p2_enabled"] = True
                p2_cycle = cycle_idx
                phase = 2
                assert irq_rise_cycle is None, (
                    f"trng_irq rose at cycle {irq_rise_cycle}, before phase 2 was enabled"
                )

            if pc == ISR_PC:
                assert len(isr_entries) < 1, (
                    f"CPU took a SECOND trap (ISR_PC committed at cycle {cycle_idx}) — a stale "
                    f"level-held TRNG/ext IRQ re-vectored after MRET, or CTRL.IE was not cleared"
                )
                isr_entries.append((cycle_idx, trng_irq, ext_irq))
                assert phase == 2, "CPU vectored to the ISR outside phase 2"
                assert trng_irq == 1, "trap: CPU vectored but u_soc.trng_irq is not asserted"
                assert ext_irq == 1, "trap: CPU vectored but u_soc.ext_irq is not asserted"

            if pc == PASS_PC:
                saw_pass = True
                break

        if isr_entries and not deassert_checked \
                and cycle_idx >= isr_entries[0][0] + DEASSERT_CHECK_DELAY_CYCLES:
            deassert_checked = True
            assert trng_irq == 0, (
                f"u_soc.trng_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the "
                f"ISR — the CTRL write did not drop the level source"
            )
            assert ext_irq == 0, (
                f"u_soc.ext_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the ISR"
            )

    if not saw_pass:
        dut._log.info(
            "last_pc=0x%08x; recent committed PCs: %s",
            last_pc, " ".join(f"0x{p:08x}" for p in recent),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within {TRNG_TEST_TIMEOUT_CYCLES} cycles"
    )
    for name, ok in seen.items():
        assert ok, f"marker {name} was never committed"
    assert len(isr_entries) == 1, f"expected exactly 1 trap, got {len(isr_entries)}"
    assert deassert_checked, "deassert window never reached"
    assert post_isr_irq_high == 0, (
        f"trng_irq/ext_irq re-asserted {post_isr_irq_high} cycle(s) after the ISR cleared IE"
    )

    # ---- boundary: the threshold IRQ ------------------------------------------------------
    assert irq_rise_cycle is not None, "trng_irq never rose in phase 2"
    assert irq_rise_level == THRESHOLD, (
        f"trng_irq rose with FIFO level {irq_rise_level}, expected exactly THRESHOLD={THRESHOLD} "
        f"— the threshold field did not cross the fabric, or the IRQ is not the level source"
    )
    dut._log.info(
        f"timing: p1_enabled={p1_cycle} p2_enabled={p2_cycle} irq_rise={irq_rise_cycle} "
        f"(level {irq_rise_level}) isr={isr_entries[0][0]}; gated_data_cycles={gated_data_cycles}"
    )
    assert gated_data_cycles >= MIN_GATED_DATA_CYCLES, (
        f"only {gated_data_cycles} phase-1 cycles had FIFO level >= {THRESHOLD} with the IRQ "
        f"armed — the IE-gate observation is too thin to mean anything"
    )

    # ---- backdoor SRAM: firmware-visible values, then value-exact words ----------------------
    sram = dut.u_soc.u_sram.mem

    def res(idx: int) -> int:
        return int(sram[RES_BASE_WI + idx].value)

    isr_count = res(RES_ISR_COUNT)
    assert isr_count == 1, f"backdoor SRAM: ISR_COUNT = {isr_count}, expected exactly 1"

    status_pre = res(RES_STATUS_PRE)
    status_full = res(RES_STATUS_FULL)
    isr_status = res(RES_ISR_STATUS)
    assert status_pre == 0x8, f"STATUS before enable = 0x{status_pre:x}, expected 0x8"
    assert status_full == 0xB, f"STATUS at FIFO-full = 0x{status_full:x}, expected 0xB"
    for name, val in (("pre-enable", status_pre), ("fifo-full", status_full),
                      ("ISR", isr_status)):
        assert val & 0x8, (
            f"TRNG_STATUS[3] (INSECURE) read 0 in the {name} STATUS (0x{val:x}) — the default "
            f"LFSR build must advertise that it is not real entropy"
        )
    assert isr_status & 0x1, f"ISR saw STATUS=0x{isr_status:x}: data-ready clear at the trap"
    assert not isr_status & 0x4, f"ISR saw STATUS=0x{isr_status:x}: health_fail set"

    assert res(RES_EMPTY_READ) == 0, f"DATA read on empty FIFO = 0x{res(RES_EMPTY_READ):x}"
    assert res(RES_SEED_RESET) == SEED_RESET_VAL, (
        f"SEED reset read = 0x{res(RES_SEED_RESET):08x}, expected 0x{SEED_RESET_VAL:08x}"
    )
    assert res(RES_SEED_READBACK) == SEED1, (
        f"SEED read-back = 0x{res(RES_SEED_READBACK):08x}, expected 0x{SEED1:08x}"
    )

    got1 = [res(RES_P1_WORDS + k) for k in range(PHASE1_WORDS)]
    want1 = TrngLfsrModel(SEED1).words(PHASE1_WORDS)
    got2 = [res(RES_P2_WORDS + k) for k in range(PHASE2_WORDS)]
    want2 = TrngLfsrModel(SEED2).words(PHASE2_WORDS)
    dut._log.info("phase 1 words: %s", [f"0x{w:08x}" for w in got1])
    dut._log.info("phase 2 words: %s", [f"0x{w:08x}" for w in got2])
    assert got1 == want1, (
        f"phase-1 words differ from trng_lfsr_model for seed 0x{SEED1:08x}:\n"
        f"  got  {[f'0x{w:08x}' for w in got1]}\n  want {[f'0x{w:08x}' for w in want1]}"
    )
    assert got2 == want2, (
        f"phase-2 words differ from trng_lfsr_model for seed 0x{SEED2:08x}:\n"
        f"  got  {[f'0x{w:08x}' for w in got2]}\n  want {[f'0x{w:08x}' for w in want2]}"
    )
    # Teeth: the two sequences are genuinely different, so a session that failed to restart from
    # the new seed could not have passed the phase-2 comparison by accident.
    assert want1[:PHASE2_WORDS] != want2, "SEED1 and SEED2 model streams coincide — test is vacuous"
