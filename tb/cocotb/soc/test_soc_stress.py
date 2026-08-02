"""
test_soc_stress.py — Phase 5 M9 SoC stress + benchmark test.

Drives tb_soc_top with self-checking stress firmware (stress_fw/stress_fw.hex) that
exercises the complete SoC through STRESS_ITER (10) outer iterations, each containing:

  [A] CPU 32-word SRAM burst write + read-back verify
  [B] DMA mem→mem (BUF_A → BUF_B) + word-by-word verify
  [C] GPU vector kernel (8 lanes, src+1) with D-cache flush/inval + verify
  [D] UART internal loopback byte + verify
  [E] SPI internal loopback byte + verify
  [F] Timer register read (AXI-Lite path exercise)

Stress invariants checked continuously by this testbench:
  - commit_pc_o never reaches FAIL_PC
  - PASS_PC is committed within STRESS_TIMEOUT_CYCLES
  - No X/Z on commit bus (Verilator booleans: cocotb sees 0/1 cleanly)

Benchmark results are backdoor-read from SRAM scratch words after PASS and logged.

Simulation is run without --trace (EXTRA_ARGS="") in the soc_stress Makefile target
to avoid a multi-GB VCD dump at 1M+ cycles.

Design note: the stress firmware performs STRESS_ITER = 10 outer loops.  Each outer
loop takes approximately 110 000 sim cycles (measured at 6-iter run).
Total expected sim cycles: ~1 100 000.  STRESS_TIMEOUT_CYCLES is set to 4 000 000
to give ample headroom.
"""

import sys
import time
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.stress_fw.stress_fw_addrs import (
    PASS_PC,
    FAIL_PC,
    STRESS_ITER,
    BURST_N_WORDS,
    GPU_N_WORDS,
    BM_CPU_WI,
    BM_DMA_WI,
    BM_GPU_WI,
    TIMER_WI,
    ITER_WI,
    BUF_A_WI,
    BUF_B_WI,
    GPU_SRC_WI,
    GPU_DST_WI,
)

# ── Constants ────────────────────────────────────────────────────────────────
CLK_PERIOD_NS = 2                    # 500 MHz — matches all other SoC tests

# Path to stress firmware hex image
_FW_HEX = str(Path(__file__).parent / "stress_fw" / "stress_fw.hex")

# Maximum cycles before we declare a hang (4M cycles @ 500 MHz = 8 ms wall-clock)
# This far exceeds the expected ~1M–1.5M for 6 stress iterations.
STRESS_TIMEOUT_CYCLES = 4_000_000

# ── Firmware loader (same pattern as test_periph_loopback, test_boot, etc.) ──
_FW_WORDS: list | None = None


def _rom_words() -> list:
    """Parse stress_fw.hex into a list of 32-bit words."""
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
    """Backdoor-load stress firmware into tb_soc_top.u_soc.u_boot_rom.mem."""
    mem = dut.u_soc.u_boot_rom.mem
    for i, word in enumerate(_rom_words()):
        mem[i].value = word


# ── Setup helper ─────────────────────────────────────────────────────────────
async def _setup(dut) -> None:
    """Start clock, idle inputs, backdoor-load firmware, apply + release reset."""
    start_soc_clocks(dut, CLK_PERIOD_NS)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1   # idle high
    dut.spi_miso_i.value    = 0

    _load_rom(dut)

    # Assert reset for 5 cycles
    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    # 2-cycle settling
    for _ in range(2):
        await RisingEdge(dut.clk_i)


# ── Main stress test ─────────────────────────────────────────────────────────
@cocotb.test()
async def test_soc_stress(dut):
    """
    1M+ cycle SoC stress with self-checking firmware.

    Invariants:
      - FAIL_PC never committed (each fires an assertion)
      - PASS_PC committed within STRESS_TIMEOUT_CYCLES
      - Iteration counter in SRAM increments to STRESS_ITER

    Post-pass benchmark readout:
      - BM_CPU_WI : CPU 32-word store+load mcycle delta
      - BM_DMA_WI : DMA mem→mem mcycle delta
      - BM_GPU_WI : GPU kernel (incl. flush/inval) mcycle delta
      - TIMER_WI  : Timer counter snapshot (last iteration)
      - ITER_WI   : Completed iterations (must == STRESS_ITER)
    """
    await _setup(dut)

    wall_start = time.monotonic()
    sim_cycle  = 0
    saw_pass   = False
    last_pc    = 0
    recent: list = []

    dut._log.info(
        "SoC stress started: STRESS_ITER=%d, TIMEOUT=%d cycles, FW=%s",
        STRESS_ITER, STRESS_TIMEOUT_CYCLES, _FW_HEX,
    )

    for sim_cycle in range(STRESS_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 32:
                recent.pop(0)

            # Invariant: FAIL_PC must never be committed
            assert pc != FAIL_PC, (
                f"[STRESS FAIL] firmware reached FAIL_PC=0x{FAIL_PC:08x} at "
                f"sim_cycle={sim_cycle}. A data-integrity check failed inside the "
                f"stress loop. Last committed PCs: "
                + " ".join(f"0x{p:08x}" for p in recent[-8:])
            )

            if pc == PASS_PC:
                saw_pass = True
                break

        # Progress heartbeat every 100k cycles
        if sim_cycle > 0 and sim_cycle % 100_000 == 0:
            dut._log.info(
                "  Heartbeat @ cycle %d: last_pc=0x%08x",
                sim_cycle, last_pc,
            )

    wall_elapsed = time.monotonic() - wall_start

    if not saw_pass:
        dut._log.error(
            "TIMEOUT at cycle %d: PASS_PC (0x%08x) never committed. "
            "last_pc=0x%08x. Recent PCs: %s",
            sim_cycle, PASS_PC, last_pc,
            " ".join(f"0x{p:08x}" for p in recent[-16:]),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within "
        f"{STRESS_TIMEOUT_CYCLES} cycles (last_pc=0x{last_pc:08x})"
    )

    total_cycles = sim_cycle + 1
    dut._log.info("PASS_PC reached at sim_cycle=%d", sim_cycle)

    # ── Post-pass SRAM backdoor readout ──────────────────────────────────────
    sram = dut.u_soc.u_sram.mem

    iter_done  = int(sram[ITER_WI].value)
    bm_cpu     = int(sram[BM_CPU_WI].value)
    bm_dma     = int(sram[BM_DMA_WI].value)
    bm_gpu     = int(sram[BM_GPU_WI].value)
    timer_snap = int(sram[TIMER_WI].value)

    # ── Verify iteration counter ──────────────────────────────────────────────
    assert iter_done == STRESS_ITER, (
        f"SRAM iteration counter = {iter_done}, expected {STRESS_ITER}. "
        f"Firmware loop exited early or ITER_WI wrong."
    )

    # ── Verify DMA destination still matches source (spot-check last iteration) ─
    for i in range(BURST_N_WORDS):
        src_word = int(sram[BUF_A_WI + i].value)
        dst_word = int(sram[BUF_B_WI + i].value)
        assert src_word == dst_word, (
            f"Post-pass DMA check: BUF_A[{i}]=0x{src_word:08x} != "
            f"BUF_B[{i}]=0x{dst_word:08x}"
        )

    # ── Verify GPU source / destination coherency (spot-check last iteration) ─
    # Firmware GPU_SRC_UPDATE copies GPU_DST → GPU_SRC at the end of each
    # iteration (after in-loop GPU_VERIFY passes), so by PASS time:
    #   GPU_SRC[l] == GPU_DST[l] == initial_src[l] + STRESS_ITER
    # where initial_src[l] = l + 0x11.
    # The firmware's in-loop GPU_VERIFY already asserts DST==SRC+1 each
    # iteration and jumps to FAIL if wrong — so reaching PASS guarantees
    # correctness.  The post-pass check here confirms both buffers converged
    # to the expected final value in SRAM.
    for i in range(GPU_N_WORDS):
        src_w = int(sram[GPU_SRC_WI + i].value)
        dst_w = int(sram[GPU_DST_WI + i].value)
        expected = (i + 0x11 + STRESS_ITER) & 0xFFFFFFFF
        assert src_w == expected, (
            f"Post-pass GPU_SRC[{i}]=0x{src_w:08x} != expected 0x{expected:08x} "
            f"(initial=0x{i+0x11:02x} + STRESS_ITER={STRESS_ITER})"
        )
        assert dst_w == expected, (
            f"Post-pass GPU_DST[{i}]=0x{dst_w:08x} != expected 0x{expected:08x} "
            f"(GPU_SRC_UPDATE should have set DST==SRC after last GPU_VERIFY)"
        )

    # ── Verify timer is non-zero (proves AXI-Lite timer path was reached) ─────
    assert timer_snap != 0, (
        f"Timer snapshot is 0 — timer AXI-Lite read path not exercised or "
        "timer counter never incremented (check timer enable)"
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    dut._log.info("=" * 60)
    dut._log.info("SoC STRESS GATE: PASS")
    dut._log.info("  Total sim cycles   : %d", total_cycles)
    dut._log.info("  Wall-clock elapsed : %.1f s", wall_elapsed)
    dut._log.info("  Stress iterations  : %d / %d", iter_done, STRESS_ITER)
    dut._log.info("")
    dut._log.info("  --- BENCHMARK (last iteration, mcycle deltas) ---")
    dut._log.info("  CPU 32-word burst  : %d cycles", bm_cpu)
    dut._log.info("  DMA mem->mem       : %d cycles", bm_dma)
    dut._log.info("  GPU kernel+flush   : %d cycles", bm_gpu)
    dut._log.info("  Timer CNT0 snap    : 0x%08x", timer_snap)
    dut._log.info("=" * 60)
