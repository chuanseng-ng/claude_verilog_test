"""
test_soc_multiclock_reset.py — GH #95 (Group A) SoC-level reset-asymmetry
class: verification-orchestrator directed-test half of GH #95.

DUT: tb_soc_top (same SOC_BOOT_SOURCES / soc_boot_lint as soc_boot / soc_periph
/ soc_cpu_gpu / soc_multiclock — see tb/cocotb/soc/Makefile's soc_multiclock_reset
target).

Purpose: design_state.json's gh93_cdc_verification record documents that both
RTL bugs GH #93 found (commit 4398c2e — soc_top.sv's cpu_gated_clk stopped
during the CPU's own reset window; commit 7a9f9d4 — rtl/soc/cdc/cdc_gray_fifo.sv's
wr_ready_o not gated by wr_rst_n_i) share one root signature: "a reset value
that advertises availability while cross-domain readiness has not actually
been established ... invisible whenever both domains reset together, which is
every scenario before GH #93." test_soc_multiclock.py's own boot tests already
exercise a *naturally* staggered release (cpu_domain_rst_n and core_rst_n each
derive from an INDEPENDENT PLL-lock counter once cpu_clk_i != clk_i — see that
file's BLOCKER NOTE #2 for the exact skew trace that found fr_280f3ac18c66),
but only for the specific skew the PLL stub's fixed 16-cycle lock counters
happen to produce. This file adds the complementary case those tests do not
cover: holding one physical domain's reset input low FOR AN EXTENDED,
DELIBERATE WINDOW (well beyond the PLL-lock skew) while the other domain is
fully released and actively offering real traffic (CPU instruction fetch/
SRAM store through u_cpu_axi_cdc, or fabric peripheral MMIO), proving:
  (a) zero acceptance at the CDC bridge while either physical reset input is
      low (the exact property 7a9f9d4 fixed, at full-SoC scale, through the
      real CPU AXI master and real crossbar/SRAM path rather than a
      standalone-DUT synthetic driver — see test_async_axi_fifo.py's
      test_reset_asym_* for the unit-level version of this same property),
  (b) zero corruption once the held domain finally releases — the complete
      golden PC / SRAM-sentinel sequence lands exactly as it would from a
      normal boot, proving the extended hold did not desynchronise anything.

Firmware reuse ONLY (boot_fw/boot.hex, unmodified — same firmware and golden
model as test_soc_multiclock.py's test_multiclock_boot_pc_scoreboard /
test_multiclock_boot_sram_sentinels).

Bug-class note (same as test_soc_multiclock.py): commit_valid_o / commit_pc_o
are combinationally re-exported from the CPU-domain (cpu_gated_clk) commit bus
— every polling loop here that observes them uses RisingEdge(dut.cpu_clk_i),
never dut.clk_i.

Internal (public-flat-rw, --top-module tb_soc_top) hierarchical signals used
as backdoor observation points (all declared inside soc_top.sv, one level
under dut.u_soc):
  cpu_bridge_s_awready / cpu_bridge_s_wready / cpu_bridge_s_arready —
    u_cpu_axi_cdc's s_* face ready outputs (CPU-domain side of the CDC
    bridge) — the exact signals 7a9f9d4 fixed the gating on.
  cpu_domain_rst_n / core_rst_n — the two composed per-domain reset trees
    the CDC bridge's s_rst_n_i / m_rst_n_i are wired from (soc_top.sv:601-603).

Metastability injection: corrected claim (bead claude_verilog_test-rvs). Earlier
revisions of this docstring said this was "not modelable in Verilator/cocotb" --
that was imprecise. rtl/soc/cdc/cdc_2ff_sync.sv now carries an optional,
per-instance, simulation-only randomised EXTRA-CYCLE-OF-DELAY injector
(RAND_CDC_DELAY_EN, default OFF at every instantiation site in this repo,
including every synchroniser these tests exercise) -- see that file's header
for the full model and provenance (ported concept, not code, from OpenTitan's
prim_cdc_rand_delay.sv). These tests run with the injector at its default OFF
and so still characterise the synchronised, deterministic RTL behaviour only
-- opting a synchroniser in here is future work, not something this file does
today. What remains genuinely NOT modelable in a 2-state simulator (Verilator,
or any cocotb-driven flow) is true analog metastability itself: an
intermediate, non-01, potentially-oscillating flop output. The injector models
a randomised settling DELAY, not that voltage-domain physics.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge, with_timeout

from soc_clocks import start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.models.soc_model import SoCModel

# ---------------------------------------------------------------------------
# Module-level task handle tracking (coroutine leakage guard, matching every
# other suite in this directory).
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Firmware hex loader + golden model (boot_fw/boot.hex — unmodified, shared
# with test_soc_multiclock.py).
# ---------------------------------------------------------------------------
def _read_hex_words(path: str) -> list:
    words: list = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, words: list) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    assert len(words) <= len(mem), (
        f"firmware image ({len(words)} words) exceeds boot ROM capacity ({len(mem)} words)"
    )
    for i, word in enumerate(words):
        mem[i].value = word


_BOOT_HEX = str(Path(__file__).parent / "boot_fw" / "boot.hex")
_SOC_MODEL = SoCModel(_BOOT_HEX)
_SOC_MODEL.boot(max_insns=200)
_GOLDEN_PCS = list(_SOC_MODEL.committed_pcs)
_GOLDEN_STATE = _SOC_MODEL.final_state()

SRAM_BASE = 0x0000_2000
SENTINEL_0 = 0xDEAD_BEEF
SENTINEL_1 = 0x1234_5678
_SENTINEL_0_WI = 0
_SENTINEL_1_WI = 1


async def _collect_boot_pcs(dut, timeout_cycles: int) -> list:
    """Poll RisingEdge(cpu_clk_i)+ReadOnly() (the only sound sampling
    discipline for commit_valid_o/commit_pc_o at a divergent ratio — see
    test_soc_multiclock.py's "Bug-class note") until the full golden PC
    stream has been collected or timeout_cycles is exhausted."""
    collected: list = []
    for _ in range(timeout_cycles):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value:
            collected.append(int(dut.commit_pc_o.value))
            if len(collected) >= len(_GOLDEN_PCS):
                break
    return collected


# =============================================================================
# Test 1 — fabric domain (clk_i / core_rst_n) held in reset for an extended
# window while the CPU domain (cpu_clk_i) is fully released and free-running,
# attempting real instruction fetch through u_cpu_axi_cdc.
#
# Ratio: CPU=3ns / fabric=13ns (~4.3x, wide per the GH #95 task's "at least
# one wide (>=4x)" requirement, coprime with the established 3ns CPU period).
# =============================================================================
CPU_PERIOD_NS_WIDE = 3
FABRIC_PERIOD_NS_WIDE = 13

# Held window: long enough to be well beyond the ordinary PLL-lock skew
# (16 cycles of the respective clock) that test_soc_multiclock.py's own boot
# tests already exercise -- this is a DELIBERATE extended hold, not a
# lock-latency artifact.
FABRIC_HELD_CPU_CYCLES = 300

# test_soc_multiclock.py's BOOT_TIMEOUT_CYCLES=12_000 @ 7ns fabric / 3ns cpu.
# Converted to the wider 13ns fabric ratio (13/7 ~= 1.857x) and rounded up
# generously, plus headroom for the extended fabric-held window above.
BOOT_TIMEOUT_CYCLES_WIDE = 24_000 + FABRIC_HELD_CPU_CYCLES


async def _fabric_held_cpu_free_body(dut) -> None:
    _kill_active_tasks()
    clk_task, cpu_clk_task = start_soc_clocks(
        dut, FABRIC_PERIOD_NS_WIDE, cpu_period_ns=CPU_PERIOD_NS_WIDE
    )
    _active_tasks.extend([clk_task, cpu_clk_task])

    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0

    fw_words = _read_hex_words(_BOOT_HEX)
    _load_rom(dut, fw_words)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    # Release ONLY cpu_rst_n_i -- rst_n_i (fabric) stays low for
    # FABRIC_HELD_CPU_CYCLES cpu_clk_i cycles. The CPU domain's own PLL
    # (u_cpu_pll_sub, driven by cpu_clk_i) is independent of clk_i, so the
    # CPU genuinely boots and starts issuing AXI requests through
    # u_cpu_axi_cdc while the fabric domain (and therefore m_rst_n_i at the
    # bridge) is still held.
    dut.cpu_rst_n_i.value = 1

    zero_commits_seen = 0
    for i in range(FABRIC_HELD_CPU_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        # The exact property 7a9f9d4 fixed, exercised here through the real
        # CPU AXI master + real crossbar path instead of a synthetic driver.
        assert int(dut.u_soc.cpu_bridge_s_awready.value) == 0, (
            f"cpu_bridge_s_awready asserted at cycle {i} while the fabric domain "
            "(m_rst_n_i at the CDC bridge) is still held in reset -- accept-and-drop hazard"
        )
        assert int(dut.u_soc.cpu_bridge_s_wready.value) == 0, (
            f"cpu_bridge_s_wready asserted at cycle {i} while the fabric domain "
            "(m_rst_n_i at the CDC bridge) is still held in reset -- accept-and-drop hazard"
        )
        assert int(dut.u_soc.cpu_bridge_s_arready.value) == 0, (
            f"cpu_bridge_s_arready asserted at cycle {i} while the fabric domain "
            "is still held in reset -- accept-and-drop hazard"
        )
        if dut.commit_valid_o.value:
            zero_commits_seen += 1
    await RisingEdge(dut.cpu_clk_i)

    dut._log.info(
        f"fabric-held window: {zero_commits_seen} commit_valid_o pulses observed "
        f"over {FABRIC_HELD_CPU_CYCLES} cpu_clk_i cycles while fabric was held "
        "(informational -- the CPU is free to fetch and stall on I$ miss, but "
        "must never silently commit a fetch it never actually received)"
    )

    # Release the fabric domain and confirm a fully clean boot follows --
    # zero corruption from the extended hold.
    dut.rst_n_i.value = 0  # already 0; explicit for clarity
    await ClockCycles(dut.clk_i, 2)
    dut.rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 2)
    await ClockCycles(dut.cpu_clk_i, 2)

    collected = await _collect_boot_pcs(dut, BOOT_TIMEOUT_CYCLES_WIDE)
    assert collected == _GOLDEN_PCS, (
        f"post-fabric-hold boot PC mismatch (got {len(collected)}, expected "
        f"{len(_GOLDEN_PCS)}): " + ", ".join(f"0x{p:08x}" for p in collected[:20])
    )

    for _ in range(40):
        await RisingEdge(dut.clk_i)
    await ReadOnly()
    sram = dut.u_soc.u_sram.mem
    dut_w0 = int(sram[_SENTINEL_0_WI].value)
    dut_w1 = int(sram[_SENTINEL_1_WI].value)
    assert dut_w0 == SENTINEL_0, f"SRAM sentinel 0 mismatch after fabric-held boot: {dut_w0:#x}"
    assert dut_w1 == SENTINEL_1, f"SRAM sentinel 1 mismatch after fabric-held boot: {dut_w1:#x}"
    dut._log.info(
        "test_soc_reset_asym_fabric_held_cpu_free PASS: zero acceptance at "
        "u_cpu_axi_cdc's s_* face throughout the fabric-held window, clean "
        "full boot + SRAM sentinels after release"
    )


@cocotb.test()
async def test_soc_reset_asym_fabric_held_cpu_free(dut):
    await with_timeout(_fabric_held_cpu_free_body(dut), 400, "us")


# =============================================================================
# Test 2 — mirror: CPU domain (cpu_clk_i / cpu_domain_rst_n) held in reset for
# an extended window while the fabric domain (clk_i) is fully released and
# free-running. Zero CPU activity must be observable throughout; a clean full
# boot must follow once cpu_rst_n_i finally releases.
#
# Ratio: the established CPU=3ns / fabric=7ns coprime pair (test_soc_multiclock.py's
# convention) -- ratio choice matters less here since the CPU is fully idle
# for the whole held window.
# =============================================================================
CPU_PERIOD_NS = 3
FABRIC_PERIOD_NS = 7
CPU_HELD_FABRIC_CYCLES = 150
BOOT_TIMEOUT_CYCLES = 12_000 + 400  # test_soc_multiclock.py's own budget + headroom


async def _cpu_held_fabric_free_body(dut) -> None:
    _kill_active_tasks()
    clk_task, cpu_clk_task = start_soc_clocks(
        dut, FABRIC_PERIOD_NS, cpu_period_ns=CPU_PERIOD_NS
    )
    _active_tasks.extend([clk_task, cpu_clk_task])

    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0

    fw_words = _read_hex_words(_BOOT_HEX)
    _load_rom(dut, fw_words)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    # Release ONLY rst_n_i (fabric) -- cpu_rst_n_i stays low. The fabric
    # domain (crossbar, SRAM controller, peripherals, PMU) is free to run;
    # nothing in this SoC drives fabric-side traffic autonomously without
    # CPU/DMA programming, so the meaningful check is that the CPU domain
    # itself stays completely silent.
    dut.rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 3)

    for i in range(CPU_HELD_FABRIC_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        assert int(dut.commit_valid_o.value) == 0, (
            f"commit_valid_o asserted at fabric cycle {i} while cpu_rst_n_i is "
            "still held low -- CPU domain must be completely silent"
        )
        # Mirror of test 1's exact 7a9f9d4 property, from the other side: with
        # cpu_rst_n_i held low, u_cpu_axi_cdc's s_rst_n_i (CPU-domain reset)
        # feeds the shared rst_both_n root, so the write-domain gray FIFOs'
        # wr_ready_o must stay gated to 0 regardless of the fabric domain's
        # own state -- the same reset-gates-own-ready contract, checked here
        # through the CPU-held mirror rather than the fabric-held case above.
        assert int(dut.u_soc.cpu_bridge_s_awready.value) == 0, (
            f"cpu_bridge_s_awready asserted at fabric cycle {i} while cpu_rst_n_i "
            "is still held low -- accept-and-drop hazard"
        )
        assert int(dut.u_soc.cpu_bridge_s_wready.value) == 0, (
            f"cpu_bridge_s_wready asserted at fabric cycle {i} while cpu_rst_n_i "
            "is still held low -- accept-and-drop hazard"
        )
        assert int(dut.u_soc.cpu_bridge_s_arready.value) == 0, (
            f"cpu_bridge_s_arready asserted at fabric cycle {i} while cpu_rst_n_i "
            "is still held low -- accept-and-drop hazard"
        )
    await RisingEdge(dut.clk_i)

    dut.cpu_rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 2)
    await ClockCycles(dut.cpu_clk_i, 2)

    collected = await _collect_boot_pcs(dut, BOOT_TIMEOUT_CYCLES)
    assert collected == _GOLDEN_PCS, (
        f"post-cpu-hold boot PC mismatch (got {len(collected)}, expected "
        f"{len(_GOLDEN_PCS)}): " + ", ".join(f"0x{p:08x}" for p in collected[:20])
    )

    for _ in range(40):
        await RisingEdge(dut.clk_i)
    await ReadOnly()
    sram = dut.u_soc.u_sram.mem
    dut_w0 = int(sram[_SENTINEL_0_WI].value)
    dut_w1 = int(sram[_SENTINEL_1_WI].value)
    assert dut_w0 == SENTINEL_0, f"SRAM sentinel 0 mismatch after cpu-held boot: {dut_w0:#x}"
    assert dut_w1 == SENTINEL_1, f"SRAM sentinel 1 mismatch after cpu-held boot: {dut_w1:#x}"
    dut._log.info(
        "test_soc_reset_asym_cpu_held_fabric_free PASS: zero commit_valid_o "
        f"activity and zero acceptance at u_cpu_axi_cdc's s_* face for "
        f"{CPU_HELD_FABRIC_CYCLES} clk_i cycles while cpu_rst_n_i "
        "was held low, clean full boot + SRAM sentinels after release"
    )


@cocotb.test()
async def test_soc_reset_asym_cpu_held_fabric_free(dut):
    await with_timeout(_cpu_held_fabric_free_body(dut), 400, "us")
