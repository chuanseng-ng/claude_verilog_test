"""
test_soc_multiclock.py — GH #93 multiclock SoC CDC exercise.
Bead: feat/cpu-domain-cdc-gh93 verification task.

DUT: tb_soc_top (same SOC_BOOT_SOURCES as soc_boot / soc_periph / soc_cpu_gpu).

BLOCKER NOTE #1 (2026-08-01, commit 66a9af1) — RESOLVED by commit 4398c2e
("[Fix] GH #93: keep cpu_gated_clk running through cpu_domain_rst_n"). The
original symptom (0 committed instructions on every ratio including 1:1,
`make soc_boot` itself red) was a CPU clock-gate/synchronous-reset race:
u_cpu_clk_en_sync (a cdc_2ff_sync, reset-to-0) gated cpu_gated_clk directly,
so the CPU saw zero clock edges during its own reset window and its
synchronous reset was never sampled. Fixed by synchronising the INVERTED
enable (pmu_cpu_clk_dis_sync) so the synchroniser's reset-to-0 state means
"not disabled" instead of "disabled". `make soc_boot` now passes 3/3
(100/100 stability); see design_state.json fix_requests[]
fr_57f49b7f9b29_20260801_000000_00 (status: fixed).

BLOCKER NOTE #2 (2026-08-01, still open) — a SECOND, DISTINCT bug, found by
running this suite after fix #1 landed. This suite (and soc_pll_multiclock)
still FAIL, but no longer with the BLOCKER NOTE #1 symptom -- pc_q now
correctly loads RESET_PC=0x1000 (confirmed via cpu_gated_clk free-running
Timer probe: toggles normally, ~1333 edges/2000ns at the 3 ns CPU period;
pc_q holds exactly 0x1000, never advancing). The new failure is a genuine
CDC-bridge bug, reproduced and root-caused via a throwaway diagnostic
(not committed) that scanned cpu_domain_rst_n / core_rst_n / the AR-channel
handshake signals with 1 ns free-running Timer() sampling from t=0:

  t=0ns:  cpu_domain_rst_n=0 core_rst_n=0                       (both in reset)
  t=33ns: cpu_domain_rst_n=1 core_rst_n=0                       (CPU domain releases FIRST --
                                                                  its PLL locks in 16 * 3ns = 48ns,
                                                                  fabric's PLL needs 16 * 7ns = 112ns)
  t=45ns: cpu_axi_arvalid_raw=1 s_arvalid=1 s_arready=1          (CPU's first I$-miss AR fires;
                                                                  u_cpu_axi_cdc's s_arready_o reads
                                                                  1 -- "ready" -- even though
                                                                  core_rst_n is STILL 0)
  t=48ns: cpu_axi_arvalid_raw=0                                 (arvalid&&arready on the previous
                                                                  edge = AXI4-legal completed
                                                                  handshake; CPU never re-asserts)
  t=98ns: core_rst_n=1                                          (fabric reset finally releases --
                                                                  40ns too late; the request is gone)

  Root cause: rtl/soc/cdc/cdc_gray_fifo.sv's `assign wr_ready_o = !full_q;`
  with `full_q <= 1'b0` on `!wr_rst_n_i` (async reset default). wr_rst_n_i is
  s_rst_sync_n, itself gated by rst_both_n = s_rst_n_i & m_rst_n_i (see
  async_axi_fifo.sv). While core_rst_n (m_rst_n_i) is still low, rst_both_n
  and therefore s_rst_sync_n are ALSO still low -- the write-pointer/push
  logic in cdc_gray_fifo's `always_ff @(posedge wr_clk_i or negedge
  wr_rst_n_i) if (!wr_rst_n_i) ... else if (push) ...` can only take the
  reset branch, so no push ever happens -- yet wr_ready_o already reads 1
  (not-full is a true statement about an empty, reset FIFO, but it is NOT a
  safe thing to expose externally as "ready" while the write side is still
  held in an unreleased cross-coupled reset). The CPU's AXI master sees
  arvalid && arready complete on that cycle, which is a legal, final AXI4
  handshake -- it never re-issues the request, but the data was silently
  dropped. This is a genuine accept-and-drop CDC bridge bug: the fix would
  need `wr_ready_o` (and likely equivalent read-side logic) to also be
  gated by the reset, e.g. `assign wr_ready_o = wr_rst_n_i && !full_q;`.

  Why this is NEW and could not have been caught by any 1:1-ratio suite,
  including async_axi_fifo's own 22/22 unit tests: at a 1:1 clock ratio
  (the only ratio ever exercised end-to-end pre-GH#93, since cpu_clk_i and
  clk_i were the same net), both domains' PLL-lock-based resets release in
  lockstep -- there is no window where one side is out of reset while the
  other is still in it. Only a genuinely asynchronous ratio (this suite's
  entire reason for existing) can expose a release-order/skew hazard like
  this. async_axi_fifo.sv's own header explicitly documents the "common
  root" reset assumption (`rst_both_n = s_rst_n_i & m_rst_n_i`) but that
  assumption is violated at the SoC level: cpu_domain_rst_n and core_rst_n
  are each derived from an INDEPENDENT PLL lock counter (16 cycles of EACH
  PLL's own, different-period reference clock), so they do not actually
  release simultaneously once the two clocks genuinely differ.

  apb_cdc_bridge (GH #93's other new CDC primitive, exercised by
  soc_pll_multiclock) is NOT expected to share this exact defect by design:
  its s_pready_o is `assign s_pready_o = (s_state_q == S_DONE);`, and
  s_state_q resets to S_IDLE (!= S_DONE) via the same s_rst_sync_n
  mechanism -- so its APB4 "ready" output correctly reads 0 (NOT ready)
  while held in the cross-coupled reset, unlike cdc_gray_fifo's
  `!full_q`-only default. This cannot be confirmed empirically at the SoC
  level, though, because soc_pll_multiclock's firmware needs the CPU to
  boot first, and boot itself is blocked by the bug above -- see
  soc_pll_multiclock's own FAIL (last_pc=0x00000000) in the regression
  results, which is this SAME bug masking any PLL2/apb_cdc_bridge-specific
  behaviour, not independent evidence against apb_cdc_bridge.

  Until this is fixed, soc_boot / soc_periph / soc_coherency / soc_cpu_gpu
  DO pass (the CPU's own D$/I$ traffic through u_cpu_axi_cdc at the 1:1
  ratio never hits the reset-skew window), but BOTH multiclock suites
  remain red. See design_state.json fix_requests[] for the filed report
  and the Makefile's soc_all comment.

Purpose: every pre-existing SoC-level cocotb suite drives clk_i (fabric
domain) and cpu_clk_i (CPU domain, GH #93) at a 1:1 ratio via
soc_clocks.start_soc_clocks() — see that module's header. At 1:1, the two
Clock() coroutines start in phase and never drift apart, so the CPU<->fabric
CDC boundary (rtl/soc/async_axi_fifo.sv's u_cpu_axi_cdc bridge, plus the
cdc_2ff_sync/cdc_reset_sync instances synchronising the PMU control signals
and ext_irq/timer_irq into the CPU domain — see soc_top.sv's GH #93 header
comment) is exercised only in its degenerate synchronous-clock case. This
suite is the one place in the regression that drives a genuinely
asynchronous ratio, to prove the CDC primitives (registered-gray-pointer
2-FF sync, cdc_2ff_sync level synchronisers, cdc_reset_sync) work when the
two domains are NOT clock-aligned.

Clock periods (see also soc_clocks.py's module docstring):
  CPU_PERIOD_NS    = 3   (CPU domain, cpu_clk_i)
  FABRIC_PERIOD_NS = 7   (fabric/GPU/peripheral domain, clk_i)

  Reasoning:
    - This repo's real target split is CPU ~1282 MHz (~0.780 ns) vs
      fabric/GPU ~571 MHz (~1.751 ns) — a ratio of ~2.245, CPU faster than
      fabric. 7/3 ~= 2.333 preserves that same direction (CPU faster) at a
      ratio close to the real target, while staying small enough that a sim
      run completes in a reasonable time.
    - 3 and 7 are coprime (gcd=1), so the two clock edges are never in a
      small-integer-multiple relationship (e.g. 2:1, 4:1) that would let a
      lucky fixed-phase alignment quietly paper over a CDC bug — the
      relative phase between clk_i and cpu_clk_i edges only repeats every
      LCM(3,7) = 21 ns, walking through 7 distinct cpu_clk_i-edge phases
      relative to each clk_i edge (and vice versa) before it does. Every
      async_axi_fifo AR/AW/W/B/R handshake and every cdc_2ff_sync sample in
      this suite therefore lands at a genuinely different, non-repeating
      phase offset rather than a single fixed one.
    - Both values are deliberately small (single-digit ns) so total wall
      simulation time for boot / periph-loopback / cpu-gpu-irq traffic stays
      comparable to the existing 1:1 SoC suites (all of which use a 2 ns
      period) rather than blowing up runtime — this is a functional
      CDC-correctness check, not a timing/performance benchmark.

Firmware reuse ONLY (no new firmware/C source is written here):
  1. boot_fw/boot.hex + tb.models.soc_model.SoCModel — CPU->SRAM
     instruction fetch (I$ refill, AXI4 AR/R channel) and data write
     (D$ writeback, AXI4 AW/W/B channel) through u_cpu_axi_cdc, exactly the
     pattern in test_boot.py (test_boot_pc_scoreboard /
     test_boot_sram_sentinels), adapted to poll cpu_clk_i.
  2. periph_fw/periph_loopback.hex — DMA mem->mem + UART/SPI MMIO issued by
     the CPU over the crossbar -> axi4_to_axilite path (test_periph_loopback.py
     pattern), all CPU-issued traffic through u_cpu_axi_cdc's AW/W/B and
     AR/R channels for MMIO reads/writes, adapted to poll cpu_clk_i.
  3. cpu_gpu_irq_fw/cpu_gpu_irq_fw.hex — GPU (fabric domain) completion IRQ
     crossing into the CPU domain via u_ext_irq_sync (cdc_2ff_sync),
     triggering a real trap/ISR (test_cpu_gpu_irq.py positive-path pattern),
     adapted to poll cpu_clk_i. Only the positive path is included here — see
     the module-level "scope decisions" note near the bottom of this file.

Bug-class note (see also test_pll_lock.py's _wait_for_cpu_lock docstring):
  commit_valid_o / commit_pc_o are combinationally re-exported from the
  CPU-domain (cpu_gated_clk) commit bus inside soc_top (see
  `assign commit_valid_o = pmu_cpu_iso_en_sync ? 1'b0 : cpu_commit_valid_raw;`)
  — every polling loop in this file that observes them MUST use
  RisingEdge(dut.cpu_clk_i), never dut.clk_i, or at this non-1:1 ratio the
  poll would alias/miss single-cycle commit pulses. Loops that only touch
  fabric-domain bus/reset timing (e.g. the post-commit SRAM-writeback drain
  wait, or the initial reset hold) use dut.clk_i, which is fine because
  reset is a level, not a pulse, and the drain wait only needs to outlast
  the fabric-domain burst FSM.

Timeout budgets (all expressed in cpu_clk_i cycles, since every scoreboard
loop below polls RisingEdge(dut.cpu_clk_i)):
  The pre-existing 1:1 suites' cycle constants were counted against a clock
  that was simultaneously the CPU-instruction-retirement clock AND the
  fabric/peripheral-FSM clock. Splitting the domains means a bound that
  used to cover both jobs with one number now has to separately cover:
    (a) CPU-domain instruction/poll-loop cycles (unchanged in count, just a
        different period), and
    (b) fabric-domain FSM cycles (AXI burst beats, UART/SPI bit dividers,
        GPU kernel execution, CDC synchroniser latency) — unchanged in
        *cycle* count (these are cycle-based dividers/FSMs, not real-time
        based), but each such cycle now costs FABRIC_PERIOD_NS/CPU_PERIOD_NS
        = 7/3 ~= 2.33x as many cpu_clk_i edges to "wait out" as it did at
        the old 1:1, 2 ns/2 ns ratio.
  Each budget below is therefore the old bound's cycle count converted from
  its historical clk_i-cycle-cost basis into cpu_clk_i-cycle-cost via that
  ~2.33x factor, then rounded up generously (this suite runs once per
  target, not 100x like test_boot.py's stability gate, so a generous
  constant is cheap).
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

# ---------------------------------------------------------------------------
# Project root on Python path so tb.models / tb.cocotb imports work
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.models.soc_model import SoCModel
from tb.cocotb.soc.periph_fw.periph_fw_addrs import (
    PASS_PC as PERIPH_PASS_PC,
    FAIL_PC as PERIPH_FAIL_PC,
    DMA_SRC_IDX,
    DMA_DST_IDX,
)
from tb.cocotb.soc.cpu_gpu_irq_fw.cpu_gpu_irq_fw_addrs import (
    PASS_PC as IRQ_PASS_PC,
    FAIL_PC as IRQ_FAIL_PC,
    SRC_IDX as IRQ_SRC_IDX,
    DST_IDX as IRQ_DST_IDX,
    ISR_FLAG_WI,
    N_SRC_WORDS as IRQ_N_SRC_WORDS,
)

# ---------------------------------------------------------------------------
# Clock periods — see module docstring for the ratio-choice rationale.
# ---------------------------------------------------------------------------
CPU_PERIOD_NS    = 3   # CPU domain (cpu_clk_i) — faster, matches real target direction
FABRIC_PERIOD_NS = 7   # fabric/GPU/peripheral domain (clk_i)

# ---------------------------------------------------------------------------
# Module-level task handle tracking (coroutine leakage guard per knowledge.md)
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Firmware hex loader (backdoor into u_boot_rom.mem — see test_boot.py)
# ---------------------------------------------------------------------------
def _read_hex_words(path: str) -> list:
    """Parse a $readmemh-style hex image into a list of 32-bit words."""
    words: list = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, words: list) -> None:
    """Backdoor-load a firmware image into tb_soc_top.u_soc.u_boot_rom.mem."""
    mem = dut.u_soc.u_boot_rom.mem
    assert len(words) <= len(mem), (
        f"firmware image ({len(words)} words) exceeds boot ROM capacity "
        f"({len(mem)} words)"
    )
    for i, word in enumerate(words):
        mem[i].value = word


def _zero_sram_range(dut, start_wi: int, n: int) -> None:
    """Zero n SRAM words starting at word index start_wi (backdoor)."""
    sram = dut.u_soc.u_sram.mem
    for i in range(n):
        sram[start_wi + i].value = 0


# ---------------------------------------------------------------------------
# Shared setup helper — starts BOTH clocks at the multiclock ratio
# ---------------------------------------------------------------------------
async def _setup(dut, fw_words: list, extra_backdoor=None) -> None:
    """Start clk_i/cpu_clk_i at the multiclock ratio, idle inputs, backdoor-
    load firmware (+ optional extra_backdoor callback), apply + release
    reset on both domains.

    Reset is held for 5 RisingEdge(dut.clk_i) (the SLOWER, fabric-domain
    clock) — since FABRIC_PERIOD_NS > CPU_PERIOD_NS, 5 fabric edges always
    span MORE than 5 cpu_clk_i edges (~11-12 at this ratio), so both
    domains' cdc_reset_sync/reset trees see at least as much reset-asserted
    time as the 1:1 suites' "5 cycles" convention.
    """
    _kill_active_tasks()

    clk_task, cpu_clk_task = start_soc_clocks(
        dut, FABRIC_PERIOD_NS, cpu_period_ns=CPU_PERIOD_NS
    )
    _active_tasks.append(clk_task)
    _active_tasks.append(cpu_clk_task)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1   # idle high
    dut.spi_miso_i.value    = 0

    _load_rom(dut, fw_words)
    if extra_backdoor is not None:
        extra_backdoor(dut)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    # Settling — again counted on the slower fabric clock for the same
    # "at least this many edges in both domains" reasoning as above.
    for _ in range(2):
        await RisingEdge(dut.clk_i)


# =============================================================================
# Test 1 — CPU<->SRAM read/write through the CDC (boot_fw/boot.hex)
# Exercises: I$ refill (AXI4 AR/R channel through u_cpu_axi_cdc), D$ writeback
# (AXI4 AW/W/B channel through u_cpu_axi_cdc), and the crossbar/SRAM path on
# the fabric side of the bridge.
# =============================================================================
_BOOT_HEX = str(Path(__file__).parent / "boot_fw" / "boot.hex")
_SOC_MODEL = SoCModel(_BOOT_HEX)
_SOC_MODEL.boot(max_insns=200)
_GOLDEN_PCS   = list(_SOC_MODEL.committed_pcs)
_GOLDEN_STATE = _SOC_MODEL.final_state()

SRAM_BASE      = 0x0000_2000
SENTINEL_0     = 0xDEAD_BEEF
SENTINEL_1     = 0x1234_5678
_SENTINEL_0_WI = 0   # SRAM[0x2000]
_SENTINEL_1_WI = 1   # SRAM[0x2004]

# test_boot.py's BOOT_TIMEOUT_CYCLES=5000 @ CLK_PERIOD_NS=2 ns is a
# clk_i-cycle bound (10,000 ns of wall budget at the old 1:1 ratio).
# Converted to cpu_clk_i cycles at the new ratio (7/3 ~= 2.33x) and rounded
# up generously: 5000 * 2.33 ~= 11,667 -> 12,000 cpu_clk_i cycles.
BOOT_TIMEOUT_CYCLES = 12_000


@cocotb.test()
async def test_multiclock_boot_pc_scoreboard(dut):
    """Boot the SoC at the CPU<->fabric multiclock ratio; verify every
    committed PC matches the golden model (I$ refill through the CDC)."""
    fw_words = _read_hex_words(_BOOT_HEX)
    dut._log.info(
        f"Multiclock boot: cpu_clk_i={CPU_PERIOD_NS} ns, clk_i={FABRIC_PERIOD_NS} ns; "
        f"golden PC stream ({len(_GOLDEN_PCS)} PCs): "
        + ", ".join(f"0x{p:08x}" for p in _GOLDEN_PCS)
    )

    await _setup(dut, fw_words)

    collected: list = []
    mismatches: list = []
    n_expected = len(_GOLDEN_PCS)

    for _ in range(BOOT_TIMEOUT_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            idx = len(collected)
            collected.append(pc)
            if idx < n_expected:
                exp = _GOLDEN_PCS[idx]
                if pc != exp:
                    mismatches.append(
                        f"commit[{idx}]: got 0x{pc:08x}, expected 0x{exp:08x}"
                    )
            else:
                mismatches.append(
                    f"commit[{idx}]: extra commit 0x{pc:08x} "
                    f"(expected {n_expected} total)"
                )
            if len(collected) >= n_expected:
                break

    if len(collected) < n_expected:
        mismatches.append(
            f"timeout: collected {len(collected)}/{n_expected} commits "
            f"within {BOOT_TIMEOUT_CYCLES} cpu_clk_i cycles"
        )

    dut._log.info(
        f"Collected {len(collected)} commits, {len(mismatches)} mismatches"
    )

    assert not mismatches, (
        f"Multiclock PC scoreboard FAIL — {len(mismatches)} mismatch(es):\n"
        + "\n".join(mismatches)
    )
    dut._log.info("test_multiclock_boot_pc_scoreboard PASS")


@cocotb.test()
async def test_multiclock_boot_sram_sentinels(dut):
    """Fresh multiclock boot; verify DUT hardware SRAM sentinels landed via
    the D$ writeback burst through u_cpu_axi_cdc (AXI4 AW/W/B channels)."""
    golden_sram = _GOLDEN_STATE["sram_words"]
    w0_golden = golden_sram.get(SRAM_BASE, None)
    w1_golden = golden_sram.get(SRAM_BASE + 4, None)
    assert w0_golden == SENTINEL_0, (
        f"Golden model SRAM[0x2000] = 0x{w0_golden:08x}, expected 0x{SENTINEL_0:08x}"
    )
    assert w1_golden == SENTINEL_1, (
        f"Golden model SRAM[0x2004] = 0x{w1_golden:08x}, expected 0x{SENTINEL_1:08x}"
    )

    fw_words = _read_hex_words(_BOOT_HEX)
    await _setup(dut, fw_words)

    collected_pcs: list = []
    for _ in range(BOOT_TIMEOUT_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value:
            collected_pcs.append(int(dut.commit_pc_o.value))
            if len(collected_pcs) >= len(_GOLDEN_PCS):
                break

    assert collected_pcs == _GOLDEN_PCS, (
        f"PC trace mismatch (got {len(collected_pcs)} commits, "
        f"expected {len(_GOLDEN_PCS)}): "
        + ", ".join(f"0x{p:08x}" for p in collected_pcs)
    )

    # Drain wait for the final dirty-line writeback burst to fully settle in
    # the backing store. test_boot.py uses 20 clk_i cycles @ 2 ns (40 ns) at
    # the 1:1 ratio; the burst itself completes entirely in the fabric
    # domain (u_cpu_axi_cdc's m_* face -> crossbar -> sram_controller), so
    # this wait is counted in fabric-domain (dut.clk_i) cycles, not
    # cpu_clk_i. Bumped to 40 fabric cycles (280 ns) — generous margin for
    # the extra registered-gray-pointer 2-FF sync latency the CDC bridge
    # adds on top of the plain 4-beat AXI burst that test_boot.py budgeted
    # for.
    for _ in range(40):
        await RisingEdge(dut.clk_i)
    await ReadOnly()

    sram = dut.u_soc.u_sram.mem
    dut_w0 = int(sram[_SENTINEL_0_WI].value)
    dut_w1 = int(sram[_SENTINEL_1_WI].value)

    dut._log.info(
        "DUT SRAM backdoor read (multiclock): "
        f"mem[{_SENTINEL_0_WI}]=0x{dut_w0:08x}, mem[{_SENTINEL_1_WI}]=0x{dut_w1:08x}"
    )

    assert dut_w0 == SENTINEL_0, (
        f"DUT SRAM[0x{SRAM_BASE:08x}] = 0x{dut_w0:08x}, expected 0x{SENTINEL_0:08x} "
        f"— D$ writeback burst through u_cpu_axi_cdc did not complete/land correctly"
    )
    assert dut_w1 == SENTINEL_1, (
        f"DUT SRAM[0x{SRAM_BASE+4:08x}] = 0x{dut_w1:08x}, expected 0x{SENTINEL_1:08x} "
        f"— D$ writeback burst through u_cpu_axi_cdc did not complete/land correctly"
    )
    dut._log.info("test_multiclock_boot_sram_sentinels PASS")


# =============================================================================
# Test 2 — CPU MMIO through the CDC (periph_fw/periph_loopback.hex)
# Exercises: DMA + UART + SPI MMIO writes/reads issued by the CPU, all
# crossing u_cpu_axi_cdc's AW/W/B (writes) and AR/R (reads) channels on the
# way to axi4_to_axilite -> axi_lite_interconnect -> axil_to_apb.
# =============================================================================
_PERIPH_HEX = str(Path(__file__).parent / "periph_fw" / "periph_loopback.hex")
DMA_N_WORDS = 4

# test_periph_loopback.py's PERIPH_TIMEOUT_CYCLES=200_000 @ 2 ns is a
# clk_i-cycle bound dominated by UART/SPI bit-banging (16 clk cycles/bit —
# a cycle-count-based divider, unaffected by the literal ns value of the
# period it's counted against). Converted to cpu_clk_i cycles at the new
# ratio (7/3 ~= 2.33x) and rounded up generously: 200,000 * 2.33 ~= 466,667
# -> 480,000 cpu_clk_i cycles.
PERIPH_TIMEOUT_CYCLES = 480_000


@cocotb.test()
async def test_multiclock_periph_loopback(dut):
    """Run the self-checking DMA/UART/SPI firmware at the multiclock ratio;
    require PASS_PC committed, FAIL_PC never seen."""
    fw_words = _read_hex_words(_PERIPH_HEX)
    await _setup(dut, fw_words)

    saw_pass = False
    last_pc = 0
    recent: list = []
    for _ in range(PERIPH_TIMEOUT_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)
            assert pc != PERIPH_FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — a DMA/UART/SPI "
                f"loopback check failed (or a bounded poll timed out) at the "
                f"multiclock ratio (cpu={CPU_PERIOD_NS} ns, fabric={FABRIC_PERIOD_NS} ns)"
            )
            if pc == PERIPH_PASS_PC:
                saw_pass = True
                break

    if not saw_pass:
        dut._log.info(
            "last_pc=0x%08x; recent committed PCs: %s",
            last_pc, " ".join(f"0x{p:08x}" for p in recent),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PERIPH_PASS_PC:08x}) never committed within "
        f"{PERIPH_TIMEOUT_CYCLES} cpu_clk_i cycles"
    )

    # Independent DMA data check: destination SRAM region must equal source
    # (the DMA engine's own AXI4 master does not cross the CDC — only the
    # CPU's programming MMIO writes/polls do — so this confirms the MMIO
    # commands that crossed u_cpu_axi_cdc actually landed correctly).
    sram = dut.u_soc.u_sram.mem
    for i in range(DMA_N_WORDS):
        src = int(sram[DMA_SRC_IDX + i].value)
        dst = int(sram[DMA_DST_IDX + i].value)
        assert src == dst, (
            f"DMA dst[{i}] (SRAM word {DMA_DST_IDX + i}) = 0x{dst:08x} != "
            f"src[{i}] (SRAM word {DMA_SRC_IDX + i}) = 0x{src:08x}"
        )
    dut._log.info("test_multiclock_periph_loopback PASS")


# =============================================================================
# Test 3 — fabric-domain IRQ crossing into the CPU domain
# (cpu_gpu_irq_fw/cpu_gpu_irq_fw.hex, positive path only — see "scope
# decisions" note below)
# Exercises: gpu_irq_o (fabric domain) -> interrupt_controller -> ext_irq
# (fabric domain) -> u_ext_irq_sync (cdc_2ff_sync, clocked by cpu_core_clk)
# -> ext_irq_cpu_sync -> rv32i_cpu_top.ext_irq_i -> real trap/ISR entry.
# =============================================================================
_IRQ_HEX = str(Path(__file__).parent / "cpu_gpu_irq_fw" / "cpu_gpu_irq_fw.hex")

# test_cpu_gpu_irq.py's TIMEOUT_CYCLES=800_000 @ 2 ns covers the WORST-CASE
# (negative) path; its own docstring estimates the POSITIVE path (the only
# one reused here) completes in ~100,000 clk_i cycles. Converted to
# cpu_clk_i cycles at the new ratio (7/3 ~= 2.33x) and rounded up
# generously: 100,000 * 2.33 ~= 233,333 -> 500,000 cpu_clk_i cycles (extra
# headroom vs. a bare 1x conversion, since this positive path also carries
# the new ext_irq cdc_2ff_sync latency plus the u_cpu_axi_cdc traffic for
# the D$ flush/kernel-write/launch MMIO sequence, none of which existed in
# the plain boot/periph paths' timing budgets).
IRQ_TIMEOUT_CYCLES = 500_000


def _irq_backdoor(dut) -> None:
    """Zero the ISR flag + dst SRAM region before reset release (see
    test_cpu_gpu_irq.py's _setup — SRAM state persists across cocotb tests
    within the same Vtop binary, so a stale flag/dst from a prior test would
    make the teeth check meaningless)."""
    _zero_sram_range(dut, ISR_FLAG_WI, 1)
    _zero_sram_range(dut, IRQ_DST_IDX, IRQ_N_SRC_WORDS)


@cocotb.test()
async def test_multiclock_cpu_gpu_irq_pass(dut):
    """
    Positive path only (see module-level scope note): CPU enables GPU IRQ,
    launches the GPU kernel, the GPU (fabric domain) completion IRQ crosses
    u_ext_irq_sync into the CPU domain at the multiclock ratio, the ISR
    fires, and firmware reaches PASS_PC with corrected dst SRAM values.

    Pass criteria: PASS_PC committed + ISR_FLAG_WI == 1 (teeth: ISR actually
    ran, not just a stale flag) + SRAM backdoor check dst[i] == src[i] + 1.
    """
    fw_words = _read_hex_words(_IRQ_HEX)
    await _setup(dut, fw_words, extra_backdoor=_irq_backdoor)

    saw_pass = False
    saw_fail = False
    last_pc = 0
    for _ in range(IRQ_TIMEOUT_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            if pc == IRQ_PASS_PC:
                saw_pass = True
                break
            if pc == IRQ_FAIL_PC:
                saw_fail = True
                break

    if not saw_pass:
        dut._log.error(
            "test_multiclock_cpu_gpu_irq_pass: last_pc=0x%08x saw_fail=%s",
            last_pc, saw_fail,
        )
        try:
            sram = dut.u_soc.u_sram.mem
            flag = int(sram[ISR_FLAG_WI].value)
            dut._log.error("  ISR_FLAG (SRAM[%d]) = %d (expect 1)", ISR_FLAG_WI, flag)
        except Exception as exc:  # pragma: no cover - debug aid only
            dut._log.error("  DBG backdoor read failed: %s", exc)

    assert saw_pass, (
        f"PASS_PC (0x{IRQ_PASS_PC:08x}) never committed within "
        f"{IRQ_TIMEOUT_CYCLES} cpu_clk_i cycles at the multiclock ratio "
        f"(cpu={CPU_PERIOD_NS} ns, fabric={FABRIC_PERIOD_NS} ns) "
        f"(last_pc=0x{last_pc:08x}, saw_fail={saw_fail})"
    )

    sram = dut.u_soc.u_sram.mem

    isr_flag = int(sram[ISR_FLAG_WI].value)
    assert isr_flag == 1, (
        f"Teeth check failed: ISR_FLAG (SRAM word {ISR_FLAG_WI}) = {isr_flag}, "
        f"expected 1 — the ISR did not run even though PASS_PC was committed. "
        f"This would indicate the fabric-domain ext_irq -> u_ext_irq_sync "
        f"(cdc_2ff_sync) -> CPU-domain ext_irq_i crossing failed to deliver "
        f"the interrupt at this clock ratio."
    )

    for i in range(IRQ_N_SRC_WORDS):
        src_val  = int(sram[IRQ_SRC_IDX + i].value)
        dst_val  = int(sram[IRQ_DST_IDX + i].value)
        expected = src_val + 1
        assert dst_val == expected, (
            f"Backdoor SRAM check failed at word {i}: "
            f"dst=0x{dst_val:08x} expected=0x{expected:08x} (src=0x{src_val:08x})"
        )

    dut._log.info("test_multiclock_cpu_gpu_irq_pass PASS")


# =============================================================================
# Scope decisions (documented here per the task's reporting requirement):
#
# - test_cpu_gpu_irq_no_irq_enable (negative path) is NOT reused here. That
#   test proves interrupt_controller's IRQ_MASK gating logic (a purely
#   fabric-domain concern) rather than the CDC crossing itself — masking
#   ext_irq to 0 before it ever reaches u_ext_irq_sync exercises no new
#   cross-domain behaviour beyond what the positive test already covers
#   (the synchroniser sees a held-low input the whole time either way).
#   Adding it here would roughly double this test's runtime for no
#   incremental CDC-boundary coverage.
# - test_boot_stability_100 (100-attempt boot-stability gate) is NOT reused
#   here either, for the analogous reason: it stresses reset-phase timing
#   variation within a single (1:1) clock domain relationship, which is a
#   different concern from proving the CDC works at a fixed asynchronous
#   ratio. A single multiclock boot (this file's two boot tests) already
#   exercises the CDC's AR/AW/W/B/R channels end-to-end; repeating it 100x
#   would mostly re-prove the same crossing at the same phase-cycling
#   pattern (LCM(3,7)=21 ns) for a large runtime cost.
# - The PLL2/apb_cdc_bridge MMIO test (test_pll_lock.py's
#   test_pll2_apb_slot_decode) is intentionally NOT included in this file —
#   see test_soc_multiclock_pll2.py (separate DUT: tb_soc_pll, separate
#   Makefile target: soc_pll_multiclock) for that coverage, and this file's
#   sibling module's docstring for the rationale.
# - timer_irq is NOT exercised by anything in this file (or, as far as this
#   author can tell, by any pre-existing SoC-level suite): no reused
#   firmware here programs the `timer` peripheral to actually pulse
#   irq_src_i[2]/timer_irq. u_timer_irq_sync (cdc_2ff_sync, identical
#   structure to u_ext_irq_sync) is therefore UNEXERCISED by this suite —
#   this is a real, explicitly-acknowledged coverage gap, not an oversight
#   papered over. Closing it would require either new firmware (out of
#   scope per this task's constraints) or a bespoke backdoor drive of the
#   timer's internal counter/compare registers, which was judged out of
#   scope for this pass.
# =============================================================================
