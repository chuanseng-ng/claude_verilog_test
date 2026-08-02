"""
test_soc_pmu_multiclock.py — GH #95 (Group C): PMU-driven live CPU-domain
power-cycle at a divergent clock ratio (bead claude_verilog_test-2k8).

DUT: tb_soc_top (same SOC_BOOT_SOURCES / soc_boot_lint as soc_boot / soc_periph
/ soc_multiclock / soc_multiclock_reset — see tb/cocotb/soc/Makefile's
soc_pmu_multiclock target).

Purpose: every prior GH #93/#95 suite exercises the CPU<->fabric CDC boundary
via the two PHYSICAL reset inputs (rst_n_i / cpu_rst_n_i) or via natural
PLL-lock skew at boot. None of them exercise the PMU (rtl/soc/pmu.sv)
actually POWERING DOWN and BACK UP the live CPU domain through its own
sequencer while the fabric domain keeps running at a genuinely asynchronous
ratio — the residual gap design_state.json's gh93_cdc_verification record and
this repo's rtl-design-orchestrator history both explicitly flag ("no suite
exercises a live PMU-driven CPU power-cycle at a divergent clock ratio").
This file closes that gap.

Mechanism (see pmu_cycle_fw/gen_pmu_cycle_hex.py's own docstring for the full
rationale):
  - The CPU CANNOT power itself back on once its own clock is gated by the
    PMU, so this test splits the trigger: the CPU's firmware programs the
    DMA engine (a fabric-domain AXI4 master, unaffected by the CPU domain's
    own state) to write MODE_CPU_OFF into PMU CTRL (0x2000_8000) on its
    behalf, then falls into a free-running busy-loop that increments a
    counter in SRAM. The PMU sequencer gates the CPU's clock out from under
    that loop mid-flight — by design, exercising exactly the "no
    drain/quiesce step" gap documented in soc_top.sv/CLAUDE.md as a known,
    accepted, non-blocking residual risk (not something this test is meant
    to fix).
  - The power-UP trigger is supplied directly by this testbench: a backdoor
    deposit into the PMU's own CTRL register storage flip-flop
    (u_soc.u_pmu.u_regbank.regs[0], the exact array apb4_register_bank.sv's
    `always_ff` writes on a real APB4 SW write — see that file's register
    file block). This is a deliberate scope split, not a shortcut: it
    decouples "does the PMU sequencer correctly walk the CPU domain back up
    under real cross-domain traffic conditions" (novel, the actual subject
    of this test) from "can an AXI4 master reach the PMU's APB slot with a
    correctly-masked write" (already exhaustively covered — DMA already
    writes to every other register on this same APB ring in
    test_periph_loopback, and PMU's own APB write/WMASK/read-only semantics
    are already covered end-to-end by test_pmu.py's standalone suite). The
    backdoor deposit hits the identical storage cell address 0 in a real APB
    write would, so the sequencer FSM downstream reacts identically either
    way.

Ratio: CPU=3ns / fabric=7ns, the established coprime pair from
test_soc_multiclock.py/test_soc_multiclock_reset.py (test 2). The PMU itself
(rtl/soc/pmu.sv) runs on core_clk (== clk_i / the fabric domain here), so all
dom_state_q observation below polls RisingEdge(dut.clk_i); cpu_clk_i keeps
free-running the entire test (only the DERIVED gated clock inside u_cpu_cg
stops — the PLL-driven cpu_core_clk reference and cpu_clk_i itself never
stop), matching every other suite's "Clock() coroutines are never
reset/gate-gated, only the RTL's internal state is" convention.

Known hazards under test:
  - pmu.sv's power-up ordering (rst-release-before-clk-ungate) was closed in
    soc_top.sv (commit 30beab3) by gating u_cpu_cg with the CPU-domain-native
    pmu_cpu_rst_n_cpu_sync. This test's power-up ordering assertion is the
    first live exercise of that fix under real cross-domain traffic.
  - u_cpu_axi_cdc's reset-semantics asymmetry (bead claude_verilog_test-2k8,
    FIXED — see the "BEAD claude_verilog_test-2k8" note below
    @cocotb.test): u_cpu_axi_cdc's s_rst_n_i used to be wired to
    cpu_domain_rst_n, which folds in the PMU's own retention-hold reset —
    every PMU power-down therefore hard-flushed the CDC bridge's in-flight
    state even though u_cpu itself (synchronous reset, gated clock) was
    correctly RETAINING its own state across the same event. The fix
    rewires s_rst_n_i to cpu_core_rst_n (the CPU domain's true POR/PLL-lock
    reset), so the bridge now retains, not flushes, across a PMU power-
    cycle, matching u_cpu's own contract. This test is what regression-
    guards that fix.
  - The PMU power-down path still has NO drain/quiesce step (soc_top.sv:
    83-93) — a mid-burst CPU AXI transaction or D-cache writeback in flight
    when the clock gates is a pre-existing, documented, non-blocking gap,
    DISTINCT from the bead-2k8 fix above (that gap is about the crossbar's
    per-slave engine having no drain FSM at all, not about this CDC
    bridge's reset semantics). This test's firmware is deliberately minimal
    (a 2-word SRAM working set, no fabric AXI traffic after the DMA-trigger
    write) specifically to stay clear of that gap rather than exercise it.

Metastability injection: corrected claim (bead claude_verilog_test-rvs). Earlier
revisions of this docstring said this was "not modelable in Verilator/cocotb" --
that was imprecise. rtl/soc/cdc/cdc_2ff_sync.sv now carries an optional,
per-instance, simulation-only randomised EXTRA-CYCLE-OF-DELAY injector
(RAND_CDC_DELAY_EN, default OFF at every instantiation site in this repo,
including every synchroniser this test exercises) -- see that file's header
for the full model and provenance (ported concept, not code, from OpenTitan's
prim_cdc_rand_delay.sv). This test runs with the injector at its default OFF
and so still characterises the synchronised, deterministic RTL behaviour only
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
# Firmware hex loader (identical convention to test_soc_multiclock_reset.py).
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


_FW_HEX = str(Path(__file__).parent / "pmu_cycle_fw" / "pmu_cycle.hex")

CTRLVAL_WORD_IDX = 0  # SRAM word 0 (byte 0x2000) — DMA-copied MODE_CPU_OFF value
COUNTER_WORD_IDX = 1  # SRAM word 1 (byte 0x2004) — free-running busy-loop counter

MODE_NORMAL  = 0x0
MODE_CPU_OFF = 0x1

CPU_PERIOD_NS = 3
FABRIC_PERIOD_NS = 7

# pmu.sv pmu_dom_state_e encoding (mirrored here; see that file's `typedef enum`).
DOM_ON         = 0
DOM_PD_SAVE    = 1
DOM_PD_ISO     = 2
DOM_PD_GATE    = 3
DOM_OFF        = 4
DOM_PU_RST     = 5
DOM_PU_CLK     = 6
DOM_PU_RESTORE = 7
DOM_PU_ISO     = 8

DOM_CPU = 0  # pmu.sv N_DOM index for the CPU domain

POWERDOWN_TIMEOUT_CLK_I_CYCLES = 6_000
POWERUP_TIMEOUT_CLK_I_CYCLES = 6_000
FROZEN_WINDOW_CPU_CLK_CYCLES = 200
DIAG_RESUME_WINDOW_CPU_CLK_CYCLES = 2_500  # bead 2k8: >2x the measured
                                            # first-SRAM-visible-increment
                                            # latency (~1000 cycles, see the
                                            # note above this constant's use)

ROM_BASE = 0x0000_1000
LOOP_PC = 0x0000_1058  # pmu_cycle_fw/pmu_cycle_fw_addrs.py LOOP_PC


async def _wait_for_dom_state(dut, target_states, timeout_cycles, label) -> list:
    """Poll dom_state_q[DOM_CPU] once per clk_i RisingEdge+ReadOnly (the PMU's
    own domain) until it settles into one of target_states, recording the
    full de-duplicated per-cycle sequence of DISTINCT states observed along
    the way (for ordering assertions, matching test_pmu.py's own
    per-cycle-ordering discipline, now exercised through the real DMA/
    backdoor triggers instead of a standalone APB4Master)."""
    seq: list = []
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        st = int(dut.u_soc.u_pmu.dom_state_q[DOM_CPU].value)
        if not seq or seq[-1] != st:
            seq.append(st)
        if st in target_states:
            return seq
    raise TimeoutError(
        f"{label}: dom_state_q[DOM_CPU] did not reach {target_states} within "
        f"{timeout_cycles} clk_i cycles (observed sequence so far: {seq})"
    )


async def _read_counter(dut) -> int:
    await ReadOnly()
    sram = dut.u_soc.u_sram.mem
    return int(sram[COUNTER_WORD_IDX].value)


async def _pmu_live_cycle_body(dut) -> None:
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

    fw_words = _read_hex_words(_FW_HEX)
    _load_rom(dut, fw_words)

    for _ in range(5):
        await RisingEdge(dut.clk_i)
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 3)
    await ClockCycles(dut.cpu_clk_i, 3)

    # Sanity: the CPU-domain sequencer starts settled at DOM_ON.
    await RisingEdge(dut.clk_i)
    await ReadOnly()
    assert int(dut.u_soc.u_pmu.dom_state_q[DOM_CPU].value) == DOM_ON, (
        "CPU-domain PMU sequencer did not start at DOM_ON after reset release"
    )

    # =========================================================================
    # Phase 1: power-DOWN, driven by the CPU's own firmware (via DMA — see
    # module docstring for why the CPU cannot write PMU CTRL directly).
    # =========================================================================
    powerdown_seq = await _wait_for_dom_state(
        dut, {DOM_OFF}, POWERDOWN_TIMEOUT_CLK_I_CYCLES, "power-down"
    )
    expected_powerdown = [DOM_ON, DOM_PD_SAVE, DOM_PD_ISO, DOM_PD_GATE, DOM_OFF]
    assert powerdown_seq == expected_powerdown, (
        "CPU-domain power-down sequence deviated from the UPF-mandated order "
        f"(ret_save -> iso_en -> clk-gate -> reset-assert): got {powerdown_seq}, "
        f"expected {expected_powerdown}"
    )
    dut._log.info(
        "CPU domain reached DOM_OFF via firmware-triggered DMA write to PMU CTRL "
        f"(sequence: {powerdown_seq})"
    )

    # Let the CDC synchronisers (cpu_domain_rst_n's cdc_2ff_sync into the
    # free-running cpu_core_clk domain) catch up to the now-settled OFF state
    # before sampling steady-state -- the transition edge itself was already
    # covered by the per-cycle ordering assertion above.
    await ClockCycles(dut.clk_i, 10)

    # While OFF: zero *request initiation* at u_cpu_axi_cdc's s_* face, zero
    # commit activity, and the busy-loop counter frozen (clock genuinely
    # gated, not merely stalled).
    #
    # Bead claude_verilog_test-2k8 fix note: this block used to assert
    # cpu_bridge_s_{aw,w,ar}ready == 0 as its "zero acceptance" proxy. That
    # was correct ONLY under the pre-fix hard-flush wiring (s_rst_n_i =
    # cpu_domain_rst_n), where those *_ready signals read 0 purely as a
    # side effect of the bridge itself being held in reset during OFF -- not
    # because anything genuinely clamped them. Post-fix (s_rst_n_i =
    # cpu_core_rst_n), the bridge correctly stays UN-reset and running
    # during a PMU-only power-cycle (that is the entire point of the fix --
    # it retains, not flushes), so those *_ready signals legitimately read 1
    # (idle-ready, nothing pending) throughout OFF. Asserting them ==0 now
    # would be asserting a stale implementation artifact, not a real safety
    # property, and per this task's "do not weaken any assertion" rule the
    # right move is to replace it with the actual property that matters --
    # not delete it.
    #
    # The REAL "zero acceptance" guarantee comes from the ISO_CPU clamp
    # forcing cpu_bridge_s_{aw,w,ar}valid to 0 while pmu_cpu_iso_en_sync is
    # asserted (soc_top.sv, "ISO_CPU functional-isolation clamp" note, and
    # the RTL header's clamp-scope note): per AXI4, a transfer requires BOTH
    # valid AND ready in the same cycle, so valid==0 is sufficient on its
    # own to guarantee no CPU-initiated request is ever accepted-and-dropped
    # while OFF, regardless of what the bridge's *_ready happens to read.
    # Checking valid==0 directly is a strictly more precise formulation of
    # the same "accept-and-drop hazard" the original assertion named.
    counter_before = await _read_counter(dut)
    for i in range(FROZEN_WINDOW_CPU_CLK_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        assert int(dut.u_soc.cpu_bridge_s_awvalid.value) == 0, (
            f"cpu_bridge_s_awvalid asserted at cpu_clk_i cycle {i} while the CPU "
            "domain is PMU-gated OFF -- ISO_CPU clamp failure / accept-and-drop hazard"
        )
        assert int(dut.u_soc.cpu_bridge_s_wvalid.value) == 0, (
            f"cpu_bridge_s_wvalid asserted at cpu_clk_i cycle {i} while the CPU "
            "domain is PMU-gated OFF -- ISO_CPU clamp failure"
        )
        assert int(dut.u_soc.cpu_bridge_s_arvalid.value) == 0, (
            f"cpu_bridge_s_arvalid asserted at cpu_clk_i cycle {i} while the CPU "
            "domain is PMU-gated OFF -- ISO_CPU clamp failure"
        )
        assert not (
            int(dut.u_soc.cpu_bridge_s_awvalid.value) and int(dut.u_soc.cpu_bridge_s_awready.value)
        ), (
            f"AW transfer (valid && ready) occurred at cpu_clk_i cycle {i} while "
            "the CPU domain is PMU-gated OFF -- accept-and-drop hazard"
        )
        assert not (
            int(dut.u_soc.cpu_bridge_s_wvalid.value) and int(dut.u_soc.cpu_bridge_s_wready.value)
        ), (
            f"W transfer (valid && ready) occurred at cpu_clk_i cycle {i} while "
            "the CPU domain is PMU-gated OFF -- accept-and-drop hazard"
        )
        assert not (
            int(dut.u_soc.cpu_bridge_s_arvalid.value) and int(dut.u_soc.cpu_bridge_s_arready.value)
        ), (
            f"AR transfer (valid && ready) occurred at cpu_clk_i cycle {i} while "
            "the CPU domain is PMU-gated OFF -- accept-and-drop hazard"
        )
        assert int(dut.commit_valid_o.value) == 0, (
            f"commit_valid_o asserted at cpu_clk_i cycle {i} while the CPU domain "
            "is PMU-gated OFF"
        )
    counter_after = await _read_counter(dut)
    assert counter_after == counter_before, (
        f"busy-loop counter advanced ({counter_before} -> {counter_after}) over "
        f"{FROZEN_WINDOW_CPU_CLK_CYCLES} cpu_clk_i cycles while the CPU domain was "
        "PMU-gated OFF -- the gated clock leaked through"
    )
    # DIAGNOSTIC (bead claude_verilog_test-2k8, wedge-hypothesis evidence): snapshot
    # the CPU's own AXI request/stall state at the moment the OFF window is
    # sampled -- if a request was left outstanding (valid asserted, no ready/
    # response) when the domain froze, that is the strongest available signal
    # (short of a full waveform) that the no-drain/quiesce gap
    # (soc_top.sv:83-93) left the CPU's cache/arbiter FSM parked waiting on a
    # response the fabric will never deliver.
    frozen_axi_snapshot = {
        "ic_stall": int(dut.u_soc.u_cpu.u_core.ic_stall.value),
        "dc_stall": int(dut.u_soc.u_cpu.u_core.dc_stall.value),
        "s_awvalid": int(dut.u_soc.cpu_bridge_s_awvalid.value),
        "s_wvalid": int(dut.u_soc.cpu_bridge_s_wvalid.value),
        "s_bvalid": int(dut.u_soc.cpu_bridge_s_bvalid.value),
        "s_arvalid": int(dut.u_soc.cpu_bridge_s_arvalid.value),
        "s_rvalid": int(dut.u_soc.cpu_bridge_s_rvalid.value),
    }
    dut._log.info(f"DIAGNOSTIC frozen-domain AXI/stall snapshot: {frozen_axi_snapshot}")
    dut._log.info(
        f"CPU domain OFF steady-state confirmed: zero CDC-bridge acceptance, zero "
        f"commits, counter frozen at {counter_after} over "
        f"{FROZEN_WINDOW_CPU_CLK_CYCLES} cpu_clk_i cycles"
    )

    # =========================================================================
    # Phase 2: power-UP, driven externally by this testbench (see module
    # docstring for the scope rationale) -- a backdoor deposit into the exact
    # storage flip-flop a real APB4 write to PMU CTRL would hit.
    # =========================================================================
    await RisingEdge(dut.clk_i)
    dut.u_soc.u_pmu.u_regbank.regs[0].value = MODE_NORMAL
    await ReadOnly()

    # NOTE: _wait_for_dom_state's own first RisingEdge(dut.clk_i) is the edge
    # at which dom_target_on (already combinationally 1 from the deposit
    # above) is sampled by the DOM_OFF->PU_RST transition, so DOM_OFF itself
    # is never re-observed here -- it was already confirmed as the terminal
    # state of the power-down phase above. The first state this helper can
    # possibly see is DOM_PU_RST, one transition past DOM_OFF.
    powerup_seq = await _wait_for_dom_state(
        dut, {DOM_ON}, POWERUP_TIMEOUT_CLK_I_CYCLES, "power-up"
    )
    expected_powerup = [
        DOM_PU_RST, DOM_PU_CLK, DOM_PU_RESTORE, DOM_PU_ISO, DOM_ON,
    ]
    assert powerup_seq == expected_powerup, (
        "CPU-domain power-up sequence deviated from the UPF-mandated order "
        "(reset-release -> clk-ungate -> ret_restore -> iso de-assert): got "
        f"{powerup_seq}, expected {expected_powerup}"
    )
    dut._log.info(f"CPU domain reached DOM_ON via power-up (sequence: {powerup_seq})")

    # Zero-corruption check: the busy-loop counter must resume climbing from
    # exactly where it was frozen -- proving architectural state (PC +
    # registers) survived the live, clock-gate-only power cycle intact and
    # the loop resumed on the exact next instruction, not from RESET_PC.
    #
    # Bead claude_verilog_test-2k8 fix note on DIAG_RESUME_WINDOW_CPU_CLK_CYCLES's
    # size: the loop body's per-iteration CSRW dcache_flush (see
    # pmu_cycle_fw/gen_pmu_cycle_hex.py's LOOP note) is what makes the
    # counter observable via the backdoor SRAM read below at all (SRAM_BASE
    # is cacheable/write-back, so a store alone only dirties the D-cache
    # line -- see that file's note), but a full CS_FLUSH_SCAN (256 sets) is
    # the dominant per-iteration cost, not the 4-instruction loop body
    # itself. Measured: the first post-resume SRAM-visible increment lands
    # ~1000 cpu_clk_i cycles after DOM_ON (one-time settle cost: draining
    # any beat the fabric-side CDC bridge retained in flight across the
    # power-cycle, per the bead 2k8 fix above, plus the loop's own first
    # flush), then roughly every ~300 cycles thereafter in steady state.
    # DIAG_RESUME_WINDOW_CPU_CLK_CYCLES is sized with margin above the
    # measured first-increment latency so this assertion is not flaky.
    #
    # This loop intentionally does NOT break early on commit count (an
    # earlier revision did, and broke well before even one flush-writeback
    # round-trip could complete, which produced a "0 -> 0" false failure
    # that briefly looked like a resume deadlock but was purely a test-
    # timing-budget artifact -- see git history for that investigation). It
    # always runs the full window so real wall-clock cycles reliably elapse
    # regardless of how bursty commits are.
    await ClockCycles(dut.clk_i, 10)
    counter_resumed_start = await _read_counter(dut)
    commits_seen = []
    signal_trace = []
    prev_gated_clk = None
    toggle_count = 0
    for i in range(DIAG_RESUME_WINDOW_CPU_CLK_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if dut.commit_valid_o.value and len(commits_seen) < 64:
            commits_seen.append((i, int(dut.commit_pc_o.value)))
        gated_clk = int(dut.u_soc.cpu_gated_clk.value)
        if prev_gated_clk is not None and gated_clk != prev_gated_clk:
            toggle_count += 1
        prev_gated_clk = gated_clk
        if i < 60:
            signal_trace.append((
                i,
                gated_clk,
                int(dut.u_soc.cpu_gated_clk_en.value),
                int(dut.u_soc.pmu_cpu_clk_dis_sync.value),
                int(dut.u_soc.pmu_cpu_rst_n_cpu_sync.value),
                int(dut.u_soc.cpu_domain_rst_n.value),
                int(dut.u_soc.pmu_cpu_iso_en_sync.value) if hasattr(dut.u_soc, "pmu_cpu_iso_en_sync") else -1,
                # bead 2k8 evidence trail: CPU-side stall + AXI request/
                # response valid state across resume, kept as a regression
                # trace even though the wedge hypothesis this originally
                # tested for is now fixed (see u_cpu_axi_cdc's s_rst_n_i
                # rewiring in soc_top.sv).
                int(dut.u_soc.u_cpu.u_core.ic_stall.value),
                int(dut.u_soc.u_cpu.u_core.dc_stall.value),
                int(dut.u_soc.cpu_bridge_s_awvalid.value),
                int(dut.u_soc.cpu_bridge_s_wvalid.value),
                int(dut.u_soc.cpu_bridge_s_bvalid.value),
                int(dut.u_soc.cpu_bridge_s_arvalid.value),
                int(dut.u_soc.cpu_bridge_s_rvalid.value),
            ))
    counter_resumed_end = await _read_counter(dut)
    dut._log.info(
        f"DIAGNOSTIC: commits observed after power-up (cycle, pc): {commits_seen} "
        f"(scanned up to {DIAG_RESUME_WINDOW_CPU_CLK_CYCLES} cpu_clk_i cycles); "
        f"counter {counter_resumed_start} -> {counter_resumed_end}; "
        f"LOOP_PC=0x{LOOP_PC:08x} ROM_BASE=0x{ROM_BASE:08x}; "
        f"cpu_gated_clk toggle_count over window={toggle_count}"
    )
    dut._log.info(
        "DIAGNOSTIC signal_trace (i, cpu_gated_clk, cpu_gated_clk_en, "
        "pmu_cpu_clk_dis_sync, pmu_cpu_rst_n_cpu_sync, cpu_domain_rst_n, "
        "pmu_cpu_iso_en_sync, ic_stall, dc_stall, s_awvalid, s_wvalid, "
        f"s_bvalid, s_arvalid, s_rvalid): {signal_trace}"
    )
    assert counter_resumed_end > counter_resumed_start, (
        "busy-loop counter did not resume climbing after the CPU domain returned "
        f"to DOM_ON ({counter_resumed_start} -> {counter_resumed_end} over "
        f"{DIAG_RESUME_WINDOW_CPU_CLK_CYCLES} cpu_clk_i cycles) -- architectural "
        f"state did not survive the live PMU-driven power cycle. commits observed: "
        f"{commits_seen}"
    )
    assert counter_resumed_start == counter_after, (
        f"busy-loop counter changed between the OFF-window's last sample "
        f"({counter_after}) and the post-power-up first sample "
        f"({counter_resumed_start}) -- counter moved with no active clock, "
        "or the OFF-window settle margin was insufficient"
    )
    dut._log.info(
        "test_pmu_live_power_cycle PASS: CPU-domain PMU sequencer walked a full "
        "OFF->ON live power cycle in the UPF-mandated order under real "
        f"cross-domain traffic at the {CPU_PERIOD_NS}ns/{FABRIC_PERIOD_NS}ns "
        f"coprime ratio; busy-loop counter resumed cleanly "
        f"({counter_resumed_start} -> {counter_resumed_end}), proving zero "
        "corruption across the cycle"
    )


#
# BEAD claude_verilog_test-2k8 (P1): FIXED. This test used to fail against
# RTL prior to the fix below, and was pinned @cocotb.test(expect_fail=True)
# while the root cause was open. Root cause was NOT in this test's subject
# (pmu.sv's sequencer): the diagnostic trace proved the sequencer was correct
# in both directions (power-down [0,1,2,3,4] and power-up [5,6,7,8,0] both
# match the exact UPF-mandated order) and that every cross-domain control
# signal was restored correctly on power-up (cpu_gated_clk_en=1,
# pmu_cpu_clk_dis_sync=0, pmu_cpu_rst_n_cpu_sync=1, cpu_domain_rst_n=1,
# pmu_cpu_iso_en_sync=0 -- a fully ungated, unreset, unisolated CPU domain).
# Yet the CPU never committed another instruction (zero commits over 1000
# cpu_clk_i cycles post-DOM_ON). rv32i_cpu_top.sv is synchronous-reset
# throughout, and commit 30beab3 deliberately forbids cpu_gated_clk from
# ticking until pmu_cpu_rst_n_cpu_sync is already 1 specifically so the CPU
# never sees a clock edge while reset -- i.e. u_cpu is retention-by-
# construction and MUST resume from wherever it was, not reboot.
#
# Actual root cause (confirmed, not the earlier no-drain/quiesce hypothesis):
# a reset-semantics ASYMMETRY between u_cpu and u_cpu_axi_cdc (the CDC
# bridge to the fabric). u_cpu_axi_cdc's s_rst_n_i was wired to
# cpu_domain_rst_n -- the SAME signal that folds in the PMU's own
# retention-hold reset (pmu_cpu_rst_n_cpu_sync) -- so every PMU power-down
# hard-FLUSHED the bridge's gray-code pointers and any FIFO'd beats
# (async_axi_fifo's reset is a hard flush, not a graceful abort -- see that
# file's header) at the exact same moment u_cpu was correctly RETAINING its
# own architectural state. On resume, u_cpu's D-cache/AXI-arbiter FSM was
# still waiting for the response to its outstanding request (its own state
# WAS retained), but the bridge that was supposed to deliver that response
# had already discarded it -- permanent deadlock. Fix (soc_top.sv, near
# u_cpu_axi_cdc's instantiation): s_rst_n_i is now cpu_core_rst_n, the CPU
# domain's TRUE POR/PLL-lock reset, which stays asserted-high (1) throughout
# a PMU-only power-cycle -- so the bridge now retains its state exactly like
# u_cpu does, and the response the D-cache was waiting for survives the
# power-cycle in the bridge's R FIFO for the CPU to consume on resume.
#
# This test regression-guards that fix: it must keep PASSING (no
# expect_fail) to prove a live, firmware-triggered PMU power-cycle of the
# CPU domain survives with zero architectural-state corruption under a
# genuinely asynchronous CPU/fabric clock ratio. Do not re-add
# expect_fail=True, and do not "fix" a future regression here by weakening
# the assertions above -- trace it back to soc_top.sv's u_cpu_axi_cdc
# reset wiring first.
@cocotb.test()
async def test_pmu_live_power_cycle(dut):
    await with_timeout(_pmu_live_cycle_body(dut), 400, "us")
