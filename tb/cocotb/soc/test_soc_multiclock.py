"""
test_soc_multiclock.py -- multiclock SoC CDC exercise. DUT: tb_soc_top (same SOC_BOOT_SOURCES as
soc_boot, soc_periph and soc_cpu_gpu).
Resolved blockers (root causes: cr:suite:soc-test-soc-multiclock): a CPU clock-gate /
synchronous-reset race, and a cdc_gray_fifo accept-and-drop bug (wr_ready_o read 1 while the write
side was still in reset). Only a genuinely asynchronous ratio exposes this release-skew hazard; no
1:1 suite could.
Purpose: most SoC-level cocotb suites drive clk_i (fabric) and cpu_clk_i (CPU) at 1:1 through
soc_clocks.start_soc_clocks(), so the CPU<->fabric CDC boundary (u_cpu_axi_cdc, and the cdc_sync /
cdc_reset_sync instances for the PMU control signals, ext_irq and timer_irq) runs only in its
degenerate synchronous case. This suite drives an asynchronous ratio.
Clock periods: CPU_PERIOD_NS = 3 (cpu_clk_i) and FABRIC_PERIOD_NS = 7 (clk_i; fabric, GPU,
peripherals). 7/3 ~= 2.33 keeps the real direction (CPU faster) near the real split, with small
periods for runtime. 3 and 7 are coprime, so no small-integer relationship lets a lucky fixed phase
hide a CDC bug; the relative phase repeats only every LCM(3,7) = 21 time units, through 7
distinct phases.
Firmware reuse ONLY (adapted to poll cpu_clk_i): boot_fw/boot.hex + SoCModel,
periph_fw/periph_loopback.hex, cpu_gpu_irq_fw/cpu_gpu_irq_fw.hex (positive path only).
RULE: commit_valid_o and commit_pc_o come from the CPU-domain (cpu_gated_clk) commit bus, so every
loop that observes them MUST use RisingEdge(dut.cpu_clk_i), never dut.clk_i, or the poll aliases
single-cycle commit pulses at this ratio. Loops on fabric-domain timing (the SRAM-writeback drain,
the initial reset hold) use dut.clk_i.
Timeout budgets are in cpu_clk_i cycles. One fabric-domain FSM cycle costs FABRIC_PERIOD_NS /
CPU_PERIOD_NS ~= 2.33 cpu_clk_i edges, so each old 1:1 bound is converted by that factor and rounded
up generously.
Run: make -C tb/cocotb/soc soc_multiclock
Doc: tm:suite:soc-test-soc-multiclock
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks
from sram_backdoor import sram_mem

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
    sram = sram_mem(dut)
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

# test_boot.py's BOOT_TIMEOUT_CYCLES=5000 is a
# clk_i-cycle bound at the old 1:1 ratio.
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

    # Breaking out of the loop the instant
    # len(collected) reached n_expected made the "extra commit" branch below
    # dead code -- it could never actually fire, so this scoreboard could
    # never detect over-execution (the CPU spuriously committing one more
    # instruction than the golden model). Fix: once the n_expected-th commit
    # lands, keep polling for a bounded grace window (EXTRA_COMMIT_WATCH_CYCLES
    # more cpu_clk_i cycles) so a genuine extra commit has a real chance to be
    # observed and recorded as a mismatch before the loop exits successfully.
    EXTRA_COMMIT_WATCH_CYCLES = 20
    watch_until_cyc = None

    for cyc in range(BOOT_TIMEOUT_CYCLES):
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
                if idx == n_expected - 1:
                    # Just received the LAST expected commit -- arm the
                    # over-execution watch window instead of breaking here.
                    watch_until_cyc = cyc + EXTRA_COMMIT_WATCH_CYCLES
            else:
                mismatches.append(
                    f"commit[{idx}]: extra commit 0x{pc:08x} "
                    f"(expected {n_expected} total) -- over-execution detected"
                )
                break
        if watch_until_cyc is not None and cyc >= watch_until_cyc:
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
    # the backing store. test_boot.py uses 20 clk_i cycles at
    # the 1:1 ratio; the burst itself completes entirely in the fabric
    # domain (u_cpu_axi_cdc's m_* face -> crossbar -> sram_controller), so
    # this wait is counted in fabric-domain (dut.clk_i) cycles, not
    # cpu_clk_i. Bumped to 40 fabric cycles — generous margin for
    # the extra registered-gray-pointer 2-FF sync latency the CDC bridge
    # adds on top of the plain 4-beat AXI burst that test_boot.py budgeted
    # for.
    for _ in range(40):
        await RisingEdge(dut.clk_i)
    await ReadOnly()

    sram = sram_mem(dut)
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

# test_periph_loopback.py's PERIPH_TIMEOUT_CYCLES=200_000 is a
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
    sram = sram_mem(dut)
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
# (fabric domain) -> u_ext_irq_sync (cdc_sync, clocked by cpu_core_clk)
# -> ext_irq_cpu_sync -> rv32i_cpu_top.ext_irq_i -> real trap/ISR entry.
# =============================================================================
_IRQ_HEX = str(Path(__file__).parent / "cpu_gpu_irq_fw" / "cpu_gpu_irq_fw.hex")

# test_cpu_gpu_irq.py's TIMEOUT_CYCLES=800_000 covers the WORST-CASE
# (negative) path; its own docstring estimates the POSITIVE path (the only
# one reused here) completes in ~100,000 clk_i cycles. Converted to
# cpu_clk_i cycles at the new ratio (7/3 ~= 2.33x) and rounded up
# generously: 100,000 * 2.33 ~= 233,333 -> 500,000 cpu_clk_i cycles (extra
# headroom vs. a bare 1x conversion, since this positive path also carries
# the new ext_irq cdc_sync latency plus the u_cpu_axi_cdc traffic for
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
            sram = sram_mem(dut)
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

    sram = sram_mem(dut)

    isr_flag = int(sram[ISR_FLAG_WI].value)
    assert isr_flag == 1, (
        f"Teeth check failed: ISR_FLAG (SRAM word {ISR_FLAG_WI}) = {isr_flag}, "
        f"expected 1 — the ISR did not run even though PASS_PC was committed. "
        f"This would indicate the fabric-domain ext_irq -> u_ext_irq_sync "
        f"(cdc_sync) -> CPU-domain ext_irq_i crossing failed to deliver "
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
#   pattern (LCM(3,7)=21) for a large runtime cost.
# - The PLL2/apb_cdc_bridge MMIO test (test_pll_lock.py's
#   test_pll2_apb_slot_decode) is intentionally NOT included in this file —
#   see test_soc_multiclock_pll2.py (separate DUT: tb_soc_pll, separate
#   Makefile target: soc_pll_multiclock) for that coverage, and this file's
#   sibling module's docstring for the rationale.
# - timer_irq is NOT exercised by anything in this file (or, as far as this
#   author can tell, by any pre-existing SoC-level suite): no reused
#   firmware here programs the `timer` peripheral to actually pulse
#   irq_src_i[2]/timer_irq. u_timer_irq_sync (cdc_sync, identical
#   structure to u_ext_irq_sync) is therefore UNEXERCISED by this suite —
#   this is a real, explicitly-acknowledged coverage gap, not an oversight
#   papered over. Closing it would require either new firmware (out of
#   scope per this task's constraints) or a bespoke backdoor drive of the
#   timer's internal counter/compare registers, which was judged out of
#   scope for this pass.
# =============================================================================
