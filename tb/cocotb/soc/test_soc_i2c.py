"""
test_soc_i2c.py — Phase 6a-5 SoC-level I2C FABRIC test (bead claude_verilog_test-f7vs.9,
docs/PHASE6_IP_EXPANSION_PLAN.md §7 "6a-5 -- I2C", L2 testability).

`test_i2c` (tb_i2c.sv / Makefile `i2c` target) owns every I2C protocol behaviour with a real bus
BFM, driving i2c_controller's APB4 face directly. It has never exercised the controller through the
real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 11 (APB_I2C, 0x2000_E000)

nor its IRQ into interrupt_controller bit 9. This suite proves exactly that, CHEAPLY: at
CLK_PERIOD_NS = 2 a protocol BFM over thousands of cycles is expensive and brittle, so firmware
drives the DUT's internal LOOPBACK mode (I2C_CTRL[1], the SPI_CTRL[4] precedent) and NO bus BFM and
NO protocol traffic runs at this level. Firmware comes from a committed pure-Python hand-assembler
(i2c_fw/gen_i2c_hex.py, sharing trng_fw's assembler) — no riscv32 cross toolchain, so the suite is
CI-safe. Synchronisation and scoring are by commit_pc_o marker PCs, the technique test_soc_trng.py
uses.

One test, one image, two phases (see the generator header for the firmware side).

PHASE 1 — polled, I2C_IRQ_EN = 0
  Firmware reads the I2C reset values through the fabric (CTRL, CLKDIV, TIMEOUT, FIFO_STAT, and a
  reserved word — values that differ from every neighbouring APB slot, so a mis-decoded slave index
  fails), writes CLKDIV and reads it back, then runs a loopback write (0x5A) and a loopback read.
  Scored here:
    * the controller completed both transfers (IRQ_STAT exactly `done`) and the loopback slave
      returned the byte written (RX_DATA == 0x5A) — registers, TX push snoop, CMD snoop, RX pop
      snoop and the engine all work through the fabric;
    * the IE gate: `done` is pending for a long stretch of phase 1 (done_q), the interrupt path is
      armed the whole time, and i2c_irq / the interrupt controller's irq_src_i[9] / ext_irq stay
      LOW;
    * the loopback leaves the REAL pads alone: i2c_*_oe_o and the dead i2c_*_o pins never move
      for the whole run.

PHASE 2 — interrupt driven, I2C_IRQ_EN = done
  One loopback write; `done` -> i2c_irq -> interrupt_controller.irq_src_i[9] -> ext_irq -> CPU MEIP.
  Scored here:
    * irq_src_i[9] of the interrupt controller equals i2c_irq on EVERY phase-2 cycle (the bit-9
      wiring) and i2c_irq rises with done_q set (a level source, not a pulse);
    * the CPU vectors (ISR_PC commits) with i2c_irq AND ext_irq asserted — EXACTLY ONE trap, because
      the ISR drops the level source with a single IRQ_CLR write;
    * after the ISR both lines deassert and stay low;
    * backdoor SRAM: ISR_COUNT == 1, the ISR saw `done`, and the interrupt controller's
      PENDING_MASKED bit 9 was set (the controller really received the source).

GOLDEN-MODEL NOTE (same as test_soc_gpio / test_soc_trng): SoCModel cannot be used here since it
rejects 0x2000_xxxx MMIO. The firmware is self-checking and the testbench scoreboards commit_pc_o
for the marker PCs / PASS_PC / FAIL_PC.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge
from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.i2c_fw.i2c_fw_addrs import (  # noqa: E402
    BYTE1,
    CLKDIV_RUN,
    FAIL_PC,
    IRQ_READY_PC,
    ISR_PC,
    P1_CMD_PC,
    P1_DONE_PC,
    P2_ARMED_PC,
    PASS_PC,
    RES_BASE_WI,
    RES_CLKDIV_READBK,
    RES_CLKDIV_RESET,
    RES_CTRL_RESET,
    RES_FIFO_RESET,
    RES_ISR_COUNT,
    RES_ISR_I2C_STAT,
    RES_ISR_IRQC_PEND,
    RES_P1_READ_STAT,
    RES_P1_RX_DATA,
    RES_P1_STATUS,
    RES_P1_WRITE_STAT,
    RES_RESERVED_READ,
    RES_TIMEOUT_RESET,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_HEX = str(Path(__file__).parent / "i2c_fw" / "i2c_fw.hex")

# Two loopback transfers (~20 bit-times at ~15 clk each, plus MMIO polling over the fabric), the
# 600-cycle settle and the 2000-cycle D-cache-flush delay loops. Headroom for fabric latency.
I2C_TEST_TIMEOUT_CYCLES = 80_000

# Cycles after the ISR entry before checking that the IRQ lines have deasserted: the ISR issues two
# reads, an IRQ_CLR write, SRAM stores and a read-back before MRET; comfortably larger.
DEASSERT_CHECK_DELAY_CYCLES = 400

# Minimum number of phase-1 cycles `done` must be pending with the IRQ armed-but-gated, for the
# "IE gate" observation to be non-vacuous.
MIN_GATED_PENDING_CYCLES = 50

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
        f"({len(mem)} words) — regenerate with i2c_fw/gen_i2c_hex.py"
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
    dut.apb_paddr_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0
    dut.gpio_in_i.value = 0
    dut.i2c_scl_i.value = 1  # external pull-ups: a released bus reads high
    dut.i2c_sda_i.value = 1

    _load_rom(dut, hex_path)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


def _i(sig) -> int:
    return int(sig.value)


@cocotb.test()
async def test_soc_i2c(dut):
    """Reach i2c_controller through the real fabric at 0x2000_E000, run loopback transfers, and take
    the done IRQ through interrupt_controller[9] to the CPU."""
    await _setup(dut, _FW_HEX)

    seen = {"irq_ready": False, "p1_cmd": False, "p1_done": False, "p2_armed": False}
    phase = 0  # 0 = pre-arm, 1 = phase 1 (IE=0), 2 = phase 2 (IE=1)
    isr_entries: list = []  # (cycle, i2c_irq, ext_irq) at each ISR_PC commit
    deassert_checked = False
    saw_pass = False
    prev_irq = 0
    irq_rise_cycle = None
    irq_rise_done = None
    gated_pending_cycles = 0  # phase 1: done pending, IRQ armed but gated off
    post_isr_irq_high = 0
    pad_activity: list = []  # cycles where a real pad output moved
    wiring_mismatch: list = []  # phase 2: irq_src_i[9] != i2c_irq

    last_pc = 0
    recent: list = []

    for cycle_idx in range(I2C_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        i2c_irq = _i(dut.u_soc.i2c_irq)
        ext_irq = _i(dut.u_soc.ext_irq)
        src9 = (_i(dut.u_soc.u_irq_ctrl.irq_src_i) >> 9) & 1
        done_q = _i(dut.u_soc.u_i2c.done_q)

        # Loopback must never drive the real pads; the `*_o` pins are hard-tied 0.
        if _i(dut.i2c_scl_oe_o) or _i(dut.i2c_sda_oe_o) or _i(dut.i2c_scl_o) or _i(dut.i2c_sda_o):
            pad_activity.append(cycle_idx)

        # Boundary edge, independent of commit_pc_o.
        if i2c_irq and not prev_irq and irq_rise_cycle is None:
            irq_rise_cycle = cycle_idx
            irq_rise_done = done_q
        prev_irq = i2c_irq

        # Phase 1 (IRQ path armed, I2C_IRQ_EN == 0): nothing may fire, however `done` is pending.
        if phase == 1:
            assert i2c_irq == 0, (
                f"i2c_irq asserted at cycle {cycle_idx} in phase 1 with I2C_IRQ_EN == 0 "
                f"(done_q={done_q}) — the IRQ_EN gate is broken"
            )
            assert src9 == 0 and ext_irq == 0, (
                f"irq_src_i[9]/ext_irq asserted at cycle {cycle_idx} in phase 1"
            )
            if done_q:
                gated_pending_cycles += 1

        if phase == 2:
            if src9 != i2c_irq:
                wiring_mismatch.append((cycle_idx, i2c_irq, src9))
            if deassert_checked and (i2c_irq or ext_irq):
                post_isr_irq_high += 1

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — an I2C SoC-level check failed "
                f"(reset value / loopback data / IRQ_STAT / interrupt-controller pending, or a "
                f"bounded poll timed out)"
            )

            if pc == IRQ_READY_PC and not seen["irq_ready"]:
                seen["irq_ready"] = True
                phase = 1
            if pc == P1_CMD_PC and not seen["p1_cmd"]:
                seen["p1_cmd"] = True
            if pc == P1_DONE_PC and not seen["p1_done"]:
                seen["p1_done"] = True
            if pc == P2_ARMED_PC and not seen["p2_armed"]:
                seen["p2_armed"] = True
                phase = 2
                assert irq_rise_cycle is None, (
                    f"i2c_irq rose at cycle {irq_rise_cycle}, before phase 2 was armed"
                )

            if pc == ISR_PC:
                assert len(isr_entries) < 1, (
                    f"CPU took a SECOND trap (ISR_PC committed at cycle {cycle_idx}) — a stale "
                    f"level-held I2C/ext IRQ re-vectored after MRET, or IRQ_CLR did not drop it"
                )
                isr_entries.append((cycle_idx, i2c_irq, ext_irq))
                assert phase == 2, "CPU vectored to the ISR outside phase 2"
                assert i2c_irq == 1, "trap: CPU vectored but u_soc.i2c_irq is not asserted"
                assert ext_irq == 1, "trap: CPU vectored but u_soc.ext_irq is not asserted"

            if pc == PASS_PC:
                saw_pass = True
                break

        if (
            isr_entries
            and not deassert_checked
            and cycle_idx >= isr_entries[0][0] + DEASSERT_CHECK_DELAY_CYCLES
        ):
            deassert_checked = True
            assert i2c_irq == 0, (
                f"u_soc.i2c_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the ISR "
                f"— the IRQ_CLR write did not drop the level source"
            )
            assert ext_irq == 0, (
                f"u_soc.ext_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after the ISR"
            )

    if not saw_pass:
        dut._log.info(
            "last_pc=0x%08x; recent committed PCs: %s",
            last_pc,
            " ".join(f"0x{p:08x}" for p in recent),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within {I2C_TEST_TIMEOUT_CYCLES} cycles"
    )
    for name, ok in seen.items():
        assert ok, f"marker {name} was never committed"
    assert len(isr_entries) == 1, f"expected exactly 1 trap, got {len(isr_entries)}"
    assert deassert_checked, "deassert window never reached"
    assert post_isr_irq_high == 0, (
        f"i2c_irq/ext_irq re-asserted {post_isr_irq_high} cycle(s) after the ISR cleared done"
    )
    assert not pad_activity, (
        f"loopback moved a real pad output at cycles {pad_activity[:5]} (i2c_*_oe_o / *_o must "
        f"stay 0 in loopback)"
    )
    assert not wiring_mismatch, (
        f"interrupt_controller.irq_src_i[9] != i2c_irq in phase 2: {wiring_mismatch[:5]}"
    )

    # ---- boundary: the done IRQ ------------------------------------------------------------
    assert irq_rise_cycle is not None, "i2c_irq never rose in phase 2"
    assert irq_rise_done == 1, "i2c_irq rose without the done flag set"
    dut._log.info(
        f"timing: irq_rise={irq_rise_cycle} isr={isr_entries[0][0]}; "
        f"gated_pending_cycles={gated_pending_cycles}"
    )
    assert gated_pending_cycles >= MIN_GATED_PENDING_CYCLES, (
        f"only {gated_pending_cycles} phase-1 cycles had `done` pending with the IRQ armed — the "
        f"IE-gate observation is too thin to mean anything"
    )

    # ---- backdoor SRAM: firmware-visible values ---------------------------------------------
    sram = dut.u_soc.u_sram.mem

    def res(idx: int) -> int:
        return int(sram[RES_BASE_WI + idx].value)

    assert res(RES_ISR_COUNT) == 1, f"backdoor SRAM: ISR_COUNT = {res(RES_ISR_COUNT)}, expected 1"
    assert res(RES_ISR_I2C_STAT) & 0x1, (
        f"ISR saw I2C_IRQ_STAT=0x{res(RES_ISR_I2C_STAT):x}: done clear at the trap"
    )
    assert res(RES_ISR_IRQC_PEND) & 0x200, (
        f"interrupt controller PENDING_MASKED=0x{res(RES_ISR_IRQC_PEND):x}: bit 9 (I2C) was never "
        f"pending — irq_src_i[9] did not reach the controller"
    )
    assert res(RES_CTRL_RESET) == 0x0, f"CTRL reset read 0x{res(RES_CTRL_RESET):x}"
    assert res(RES_CLKDIV_RESET) == 0xFF, f"CLKDIV reset read 0x{res(RES_CLKDIV_RESET):x}"
    assert res(RES_TIMEOUT_RESET) == 0xFFFF, f"TIMEOUT reset read 0x{res(RES_TIMEOUT_RESET):x}"
    assert res(RES_FIFO_RESET) == 0xA00, f"FIFO_STAT reset read 0x{res(RES_FIFO_RESET):x}"
    assert res(RES_RESERVED_READ) == 0x0, f"reserved word read 0x{res(RES_RESERVED_READ):x}"
    assert res(RES_CLKDIV_READBK) == CLKDIV_RUN, (
        f"CLKDIV read-back 0x{res(RES_CLKDIV_READBK):x}, expected 0x{CLKDIV_RUN:x}"
    )
    assert res(RES_P1_WRITE_STAT) & 0xF == 0x1, f"write IRQ_STAT 0x{res(RES_P1_WRITE_STAT):x}"
    assert res(RES_P1_READ_STAT) & 0xF == 0x1, f"read IRQ_STAT 0x{res(RES_P1_READ_STAT):x}"
    assert res(RES_P1_RX_DATA) == BYTE1, (
        f"loopback read returned 0x{res(RES_P1_RX_DATA):02x}, expected the byte written "
        f"0x{BYTE1:02x}"
    )
    assert res(RES_P1_STATUS) & 0x1F == 0, f"STATUS after phase 1: 0x{res(RES_P1_STATUS):x}"
