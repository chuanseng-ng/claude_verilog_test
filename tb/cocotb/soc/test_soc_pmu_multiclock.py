"""
test_soc_pmu_multiclock.py -- PMU-driven live CPU-domain power-cycle at a divergent clock ratio.
DUT: tb_soc_top (target soc_pmu_multiclock). It exercises the PMU (rtl/soc/pmu.sv) POWERING DOWN and
BACK UP the live CPU domain through its own sequencer while the fabric runs at an
asynchronous ratio.
Mechanism (rationale: pmu_cycle_fw/gen_pmu_cycle_hex.py): the CPU CANNOT power itself back on once
the PMU gates its clock, so the trigger is split. The CPU firmware programs the DMA engine (a
fabric-domain AXI4 master) to write MODE_CPU_OFF into PMU CTRL (0x2000_8000), then spins in a loop
that increments an SRAM counter. The PMU gates the CPU clock out from under that loop, by design:
the "no drain/quiesce step" gap is a known, accepted, non-blocking risk (soc_top.sv) that this test
does not fix. The power-UP trigger is a backdoor deposit into the PMU CTRL storage flop
(u_soc.u_pmu.u_regbank.regs[0], the cell apb4_register_bank.sv writes on an APB write).
Ratio: CPU period 3 / fabric period 7, as test_soc_multiclock.py. The PMU runs on core_clk, so
dom_state_q polling uses RisingEdge(dut.clk_i). cpu_clk_i free-runs; only the DERIVED gated clock in
u_cpu_cg stops.
Hazards under test: (1) pmu.sv power-up ordering (reset release before clock ungate), closed in
soc_top.sv by gating u_cpu_cg with the CPU-native pmu_cpu_rst_n_cpu_sync; the ordering assertion is
its first live check. (2) u_cpu_axi_cdc's s_rst_n_i is wired to cpu_core_rst_n (the CPU domain's
true POR / PLL-lock reset) and NOT to cpu_domain_rst_n, which folds in the PMU retention-hold reset.
The bridge therefore keeps its state across a PMU power-cycle, like u_cpu; this test
regression-guards that wiring. (3) The PMU power-down has NO drain/quiesce step: a CPU AXI
transaction or D-cache writeback in flight when the clock gates is a documented non-blocking gap.
The firmware is minimal (2-word SRAM working set, no fabric AXI traffic after the DMA trigger) to
stay clear of it. The settling-delay injector in cdc_sync.sv exists; this suite does not enable it.
Run: make -C tb/cocotb/soc soc_pmu_multiclock
Doc: tm:suite:soc-test-soc-pmu-multiclock
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, with_timeout
from cocotb.utils import get_sim_time

from common.hier import read_only
from soc_clocks import start_soc_clocks
from sram_backdoor import sram_mem

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_CFW_DIR = Path(__file__).resolve().parent / "pmu_cycle_fw"
if str(_CFW_DIR) not in sys.path:
    sys.path.insert(0, str(_CFW_DIR))

import gen_pmu_confirm_fw as cfw  # noqa: E402

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
DIAG_RESUME_WINDOW_CPU_CLK_CYCLES = 2_500  # more than 2x the measured
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
    await read_only()
    sram = sram_mem(dut)
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

    # Let the CDC synchronisers (cpu_domain_rst_n's cdc_sync into the
    # free-running cpu_core_clk domain) catch up to the now-settled OFF state
    # before sampling steady-state -- the transition edge itself was already
    # covered by the per-cycle ordering assertion above.
    await ClockCycles(dut.clk_i, 10)

    # While OFF: zero *request initiation* at u_cpu_axi_cdc's s_* face, zero
    # commit activity, and the busy-loop counter frozen (clock genuinely
    # gated, not merely stalled).
    #
    # Note: this block used to assert
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
    # DIAGNOSTIC (wedge-hypothesis evidence): snapshot
    # the CPU's own AXI request/stall state at the moment the OFF window is
    # sampled -- if a request was left outstanding (valid asserted, no ready/
    # response) when the domain froze, that is the strongest available signal
    # (short of a full waveform) that the no-drain/quiesce gap
    # (see soc_top.sv) left the CPU's cache/arbiter FSM parked waiting on a
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
    # Survival is a property of the model, not a guarantee (DS-PMU-181).
    #
    # Note on DIAG_RESUME_WINDOW_CPU_CLK_CYCLES's
    # size: the loop body's per-iteration CSRW dcache_flush (see
    # pmu_cycle_fw/gen_pmu_cycle_hex.py's LOOP note) is what makes the
    # counter observable via the backdoor SRAM read below at all (SRAM_BASE
    # is cacheable/write-back, so a store alone only dirties the D-cache
    # line -- see that file's note), but a full CS_FLUSH_SCAN (256 sets) is
    # the dominant per-iteration cost, not the 4-instruction loop body
    # itself. Measured: the first post-resume SRAM-visible increment lands
    # ~1000 cpu_clk_i cycles after DOM_ON (one-time settle cost: draining
    # any beat the fabric-side CDC bridge retained in flight across the
    # power-cycle, per the reset rewiring above, plus the loop's own first
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
                # Evidence trail: CPU-side stall + AXI request/
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
# FIXED. This test used to fail against
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
# CPU domain keeps its state with zero corruption (a model property, DS-PMU-181) under a
# genuinely asynchronous CPU/fabric clock ratio. Do not re-add
# expect_fail=True, and do not "fix" a future regression here by weakening
# the assertions above -- trace it back to soc_top.sv's u_cpu_axi_cdc
# reset wiring first.
@cocotb.test()
async def test_pmu_live_power_cycle(dut):
    await with_timeout(_pmu_live_cycle_body(dut), 400, "us")


# =============================================================================
# Directed confirmation of two reviewed behaviours (P2 and P3, SoC level).
# Doc: ds:mod:pmu
#
# A review read these behaviours from the RTL and no simulation had shown them:
#   P2  The CPU clock runs while the CPU clamp is active, at the start of a power-down and at the
#       end of a power-up. A bus handshake that u_cpu completes in such an edge does not reach
#       u_cpu_axi_cdc: the clamp holds the valid and ready outputs of u_cpu at 0, not its inputs
#       (DS-PMU-100, DS-PMU-182, DS-PMU-183).
#   P3  A register access to the GPU control slave while the GPU domain is off does not end
#       (DS-PMU-185). The slave takes the address and never answers.
# The RTL is not changed. Each test that asserts the specified behaviour is marked expect_fail: it
# must fail while the behaviour exists. If one of them passes, the review was wrong or the RTL
# changed. Then replace it by a normal test that proves the rule. A harness fault raises
# RuntimeError, not AssertionError, so expect_fail cannot hide it. Each expect_fail test has a
# normal companion test that proves the checker and the stimulus. The firmware images are built in
# the test process (pmu_cycle_fw/gen_pmu_confirm_fw.py), so no binary is committed.
# =============================================================================

# CPU clock periods: equal to the fabric, faster, three times slower.
CONFIRM_RATIOS = (FABRIC_PERIOD_NS, CPU_PERIOD_NS, 3 * FABRIC_PERIOD_NS)
CONFIRM_ROM_CLEAR_WORDS = 64
CONFIRM_SETTLE_FABRIC = 40
CONFIRM_SETTLE_CPU = 8
CHANNELS = ("aw", "w", "ar", "b", "r")
GPU_WINDOW_PAGE = cfw.GPU_BASE >> 12


def _now_ns() -> int:
    return int(round(get_sim_time("ns")))


async def _confirm_reset_and_rom(dut, cpu_ns: int, words: list) -> None:
    """Clocks, idle inputs, both resets asserted, ROM image loaded. The resets stay asserted."""
    _kill_active_tasks()
    clk_task, cpu_clk_task = start_soc_clocks(dut, FABRIC_PERIOD_NS, cpu_period_ns=cpu_ns)
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
    dut.gpio_in_i.value = 0
    dut.i2c_scl_i.value = 1
    dut.i2c_sda_i.value = 1
    mem = dut.u_soc.u_boot_rom.mem
    for i in range(CONFIRM_ROM_CLEAR_WORDS):
        mem[i].value = 0
    _load_rom(dut, words)
    await ClockCycles(dut.clk_i, 6)
    await ClockCycles(dut.cpu_clk_i, 6)


async def _confirm_release(dut) -> None:
    """Release both resets and wait for the PLL stub lock and the synchroniser fill."""
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 60)
    await ClockCycles(dut.cpu_clk_i, 60)


async def _confirm_set_mode(dut, mode: int) -> None:
    """Backdoor write of PMU CTRL, the cell that a bus write to 0x2000_8000 reaches."""
    await RisingEdge(dut.clk_i)
    dut.u_soc.u_pmu.u_regbank.regs[0].value = mode
    await ReadOnly()


async def _confirm_settle(dut) -> None:
    await ClockCycles(dut.clk_i, CONFIRM_SETTLE_FABRIC)
    await ClockCycles(dut.cpu_clk_i, CONFIRM_SETTLE_CPU)


# --- P2. Handshakes of u_cpu while the clamp is active ------------------------------------------

P2_MAX_POINTS = 16          # most trigger offsets per clock ratio in the sweep
P2_WARMUP_READS = 3         # PMU STATUS reads of the noisy loop before the trigger
P2_PERIOD_READS = 6         # reads used to measure the period of the noisy loop
P2_QUIET_SETTLE_CPU_CYCLES = 400
P2_QUIET_MIN_CPU_CYCLES = 150
P2_POST_CPU_CYCLES = 300
P2_QUIET_OFFSETS = (0, 1, 2, 3)
_P2_CACHE: dict = {}


class _ClampMonitor:
    """Passive monitor of the bus edges of u_cpu. It never drives a signal.

    At each falling edge of cpu_clk_i it records the nets that the next rising edge acts on, so the
    record is the state before the edge. At the rising edge it checks that cpu_gated_clk pulsed.
    The monitor reads nets of u_cpu, u_cpu_axi_cdc and the clamp, and no value of a helper of this
    file. Per epoch it counts the gated edges, the gated edges with the clamp active
    (pmu_cpu_iso_en_sync high before the edge) and the handshakes of u_cpu on each channel. A
    handshake of u_cpu is raw valid with ready on AW, W and AR, and raw ready with valid on B and R.
    `lost` counts the handshakes at edges with the clamp active: the bridge sees valid and ready
    of u_cpu as 0 there, so it does not see the handshake.
    """

    def __init__(self, dut) -> None:
        self.dut = dut
        self.epoch = "boot"
        self.edges: dict = defaultdict(int)
        self.clamped: dict = defaultdict(int)
        self.hs: dict = defaultdict(lambda: dict.fromkeys(CHANNELS, 0))
        self.lost: dict = defaultdict(lambda: dict.fromkeys(CHANNELS, 0))
        self.ar_log: list = []
        self.last_hs_ns = None
        self.pcs: dict = defaultdict(set)
        self._task = None

    def start(self):
        self._task = cocotb.start_soon(self._run())
        _active_tasks.append(self._task)
        return self

    def stop(self) -> None:
        if self._task is not None:
            self._task.kill()
            self._task = None

    def _snap(self) -> tuple:
        s = self.dut.u_soc
        return (
            int(s.pmu_cpu_iso_en_sync.value),
            int(s.cpu_axi_awvalid_raw.value) & int(s.cpu_bridge_s_awready.value),
            int(s.cpu_axi_wvalid_raw.value) & int(s.cpu_bridge_s_wready.value),
            int(s.cpu_axi_arvalid_raw.value) & int(s.cpu_bridge_s_arready.value),
            int(s.cpu_axi_bready_raw.value) & int(s.cpu_bridge_s_bvalid.value),
            int(s.cpu_axi_rready_raw.value) & int(s.cpu_bridge_s_rvalid.value),
            int(s.cpu_bridge_s_araddr.value),
        )

    async def _run(self) -> None:
        s = self.dut.u_soc
        clk = self.dut.cpu_clk_i
        while True:
            await FallingEdge(clk)
            await ReadOnly()
            pre = self._snap()
            await RisingEdge(clk)
            await ReadOnly()
            if not int(s.cpu_gated_clk.value):
                continue
            self._edge(pre)
            if int(s.cpu_commit_valid_raw.value):
                self.pcs[self.epoch].add(int(self.dut.commit_pc_o.value))

    def _edge(self, pre: tuple) -> None:
        iso = pre[0]
        ep = self.epoch
        now = _now_ns()
        self.edges[ep] += 1
        if iso:
            self.clamped[ep] += 1
        for name, val in zip(CHANNELS, pre[1:6]):
            if val:
                self.hs[ep][name] += 1
                self.last_hs_ns = now
                if iso:
                    self.lost[ep][name] += 1
        if pre[3]:
            self.ar_log.append((now, pre[6]))

    def status_reads(self) -> list:
        return [t for t, addr in self.ar_log if addr == cfw.PMU_BASE + cfw.PMU_STATUS]


async def _wait_status_reads(dut, mon, count: int, limit: int = 4000) -> None:
    for _ in range(limit):
        if len(mon.status_reads()) >= count:
            return
        await RisingEdge(dut.clk_i)
    raise RuntimeError(
        f"harness: {len(mon.status_reads())} PMU STATUS reads of the CPU in {limit} fabric cycles, "
        f"{count} needed")


async def _p2_period(dut, cpu_ns: int) -> int:
    """Period of the noisy loop in cpu_clk_i cycles: the median gap between its STATUS reads."""
    words, _labels = cfw.noisy_image()
    await _confirm_reset_and_rom(dut, cpu_ns, words)
    mon = _ClampMonitor(dut).start()
    mon.epoch = "pre"
    await _confirm_release(dut)
    await _wait_status_reads(dut, mon, P2_PERIOD_READS)
    mon.stop()
    times = mon.status_reads()
    gaps = sorted(b - a for a, b in zip(times, times[1:]))
    period = max(1, round(gaps[len(gaps) // 2] / cpu_ns))
    if period < 2:
        raise RuntimeError(f"harness: noisy loop period of {period} cpu cycles is implausible")
    return period


async def _p2_experiment(dut, cpu_ns: int, fw: str, off: int) -> dict:
    """One power cycle of the CPU domain while the CPU runs image fw ("noisy" or "quiet").

    The request goes in `off` cpu_clk_i cycles after the third PMU STATUS read of the noisy loop,
    or after a fixed settle time plus `off` for the quiet image."""
    words, labels = cfw.noisy_image() if fw == "noisy" else cfw.quiet_image()
    await _confirm_reset_and_rom(dut, cpu_ns, words)
    mon = _ClampMonitor(dut).start()
    mon.epoch = "pre"
    await _confirm_release(dut)
    if fw == "noisy":
        await _wait_status_reads(dut, mon, P2_WARMUP_READS)
        if off:
            await ClockCycles(dut.cpu_clk_i, off)
    else:
        await ClockCycles(dut.cpu_clk_i, P2_QUIET_SETTLE_CPU_CYCLES + off)
    t_request = _now_ns()
    quiet_ns = None if mon.last_hs_ns is None else t_request - mon.last_hs_ns
    mon.epoch = "down"
    await _confirm_set_mode(dut, MODE_CPU_OFF)
    await _wait_for_dom_state(dut, {DOM_OFF}, 4000, "p2 power-down")
    await _confirm_settle(dut)
    mon.epoch = "up"
    await _confirm_set_mode(dut, MODE_NORMAL)
    await _wait_for_dom_state(dut, {DOM_ON}, 4000, "p2 power-up")
    await _confirm_settle(dut)
    mon.epoch = "post"
    await ClockCycles(dut.cpu_clk_i, P2_POST_CPU_CYCLES)
    mon.stop()
    return {
        "cpu_ns": cpu_ns,
        "fw": fw,
        "off": off,
        "clamped": {ep: mon.clamped[ep] for ep in ("down", "up")},
        "edges": {ep: mon.edges[ep] for ep in ("down", "up", "post")},
        "lost": {ep: dict(mon.lost[ep]) for ep in ("down", "up")},
        "hs": {ep: dict(mon.hs[ep]) for ep in ("pre", "down", "up", "post")},
        "quiet_ns": quiet_ns,
        "pcs": {ep: set(mon.pcs[ep]) for ep in ("pre", "post")},
        "loop_pc": labels.get("QUIET_LOOP"),
    }


def _lost_total(row: dict) -> int:
    return sum(sum(row["lost"][ep].values()) for ep in ("down", "up"))


def _fmt_p2(row: dict) -> str:
    lost = {ep: {k: v for k, v in row["lost"][ep].items() if v} for ep in ("down", "up")}
    return (
        f"cpu={row['cpu_ns']}ns off={row['off']} clamped edges down/up="
        f"{row['clamped']['down']}/{row['clamped']['up']} lost down={lost['down']} "
        f"up={lost['up']} ar after power-up={row['hs']['post']['ar']}"
    )


async def _p2_sweep(dut) -> dict:
    """Noisy image, trigger offsets over one loop period, at every clock ratio. Cached."""
    if "noisy" not in _P2_CACHE:
        out: dict = {}
        for cpu_ns in CONFIRM_RATIOS:
            period = await _p2_period(dut, cpu_ns)
            step = max(2, -(-period // P2_MAX_POINTS))
            rows = []
            for off in range(0, period, step):
                rows.append(await _p2_experiment(dut, cpu_ns, "noisy", off))
            out[cpu_ns] = {"period": period, "step": step, "rows": rows}
            dut._log.info(f"P2 noisy cpu={cpu_ns}ns loop period {period} cpu cycles, step {step}")
            for row in rows:
                dut._log.info("  " + _fmt_p2(row))
        _P2_CACHE["noisy"] = out
    return _P2_CACHE["noisy"]


@cocotb.test(expect_fail=True)
async def test_p2_no_cpu_handshake_while_clamp_active(dut):
    """Asserts: no handshake of u_cpu completes at a gated edge while the clamp control in the CPU
    domain is active, because the bridge does not see such a handshake (DS-PMU-100, DS-PMU-182).
    Stimulus: the CPU reads PMU STATUS in a loop, so every pass is one AXI read. The power-down and
    the power-up are requested at offsets over one loop period, at three clock ratios.

    expect_fail: the review reads that the clock runs for some edges with the clamp active and
    that u_cpu sees ready and valid inputs that the clamp does not hold. The failure message lists
    the points. If this test passes, the reading was wrong or the RTL changed."""
    sweep = await with_timeout(_p2_sweep(dut), 6000, "us")
    bad = [row for entry in sweep.values() for row in entry["rows"] if _lost_total(row)]
    total = sum(len(entry["rows"]) for entry in sweep.values())
    assert not bad, (
        f"{len(bad)} of {total} point(s) had a handshake of u_cpu at a gated edge with the clamp "
        "active, which the bridge does not see: " + "; ".join(_fmt_p2(r) for r in bad[:6])
    )


@cocotb.test()
async def test_p2_control_clamp_window_reached(dut):
    """Proves the stimulus of the P2 test reaches the window. At 1:1 and with the CPU faster, some
    trigger offset has at least one gated edge with the clamp active in the power-down and in the
    power-up. The counts at every ratio are logged. At 3x slower the count can be 0 by phase, so it
    is logged and not asserted. The hand derivation at 1:1 gives four and two edges."""
    sweep = await with_timeout(_p2_sweep(dut), 6000, "us")
    for cpu_ns, entry in sweep.items():
        down = [r["clamped"]["down"] for r in entry["rows"]]
        up = [r["clamped"]["up"] for r in entry["rows"]]
        reads = [r["hs"]["pre"]["ar"] for r in entry["rows"]]
        dut._log.info(
            f"P2 window cpu={cpu_ns}ns: clamped edges in the power-down {min(down)}..{max(down)}, "
            f"in the power-up {min(up)}..{max(up)} (hand derivation at 1:1: 4 and 2)")
        assert all(n > 0 for n in reads), f"cpu={cpu_ns}ns: no CPU read before a trigger"
        if cpu_ns <= FABRIC_PERIOD_NS:
            assert max(down) >= 1, f"cpu={cpu_ns}ns: no clamped gated edge at power-down"
            assert max(up) >= 1, f"cpu={cpu_ns}ns: no clamped gated edge at power-up"


@cocotb.test()
async def test_p2_control_quiet_firmware_loses_no_handshake(dut):
    """Software that follows the stop-traffic rule (DS-PMU-183): the CPU runs register instructions
    only, and the request goes in when no handshake has happened for a long time. Then no handshake
    of u_cpu falls in the power-down or the power-up, at three clock ratios and four alignments.
    The clamp window exists at these runs (see the control above). The CPU runs its loop before and
    after the power cycle, which shows that it is alive and resumed."""

    async def body():
        rows = []
        for cpu_ns in CONFIRM_RATIOS:
            for off in P2_QUIET_OFFSETS:
                rows.append(await _p2_experiment(dut, cpu_ns, "quiet", off))
        return rows

    rows = await with_timeout(body(), 3000, "us")
    for row in rows:
        tag = f"cpu={row['cpu_ns']}ns off={row['off']}"
        min_quiet_ns = P2_QUIET_MIN_CPU_CYCLES * row["cpu_ns"]
        if row["loop_pc"] not in row["pcs"]["pre"]:
            raise RuntimeError(f"harness: {tag}: the quiet loop did not run before the request")
        if row["quiet_ns"] is not None and row["quiet_ns"] < min_quiet_ns:
            raise RuntimeError(
                f"harness: {tag}: bus traffic {row['quiet_ns']}ns before the request")
        assert _lost_total(row) == 0, f"{tag}: a handshake fell in a clamp window: {_fmt_p2(row)}"
        for ep in ("down", "up"):
            assert not any(row["hs"][ep].values()), (
                f"{tag}: bus traffic in the {ep} epoch: {row['hs'][ep]}")
        assert row["loop_pc"] in row["pcs"]["post"], f"{tag}: no loop commit after the power-up"
    seen_down = max(r["clamped"]["down"] for r in rows)
    seen_up = max(r["clamped"]["up"] for r in rows)
    assert seen_down >= 1 and seen_up >= 1, (
        f"the clamp window held no gated edge (down {seen_down}, up {seen_up}): nothing is proved")
    dut._log.info(
        f"P2 quiet: {len(rows)} power cycles, no lost handshake, "
        f"most clamped edges: down {seen_down}, up {seen_up}")


# --- P3. A GPU register access while the GPU domain is off --------------------------------------

P3_BOUND_CYCLES = 4000             # fabric cycles that the access under test may take
P3_AFTER_POWER_UP_CYCLES = 2000    # fabric cycles observed after the GPU is powered up again
P3_RESET_LOG_FROM_CYCLE = 20       # skip the first cycles: the flops have not seen a clock yet
_P3_CACHE: dict = {}


class _P3Monitor:
    """Passive monitor of the GPU control access path. It never drives a signal.

    CPU interface: an AXI scoreboard on the s_* face of u_cpu_axi_cdc, sampled before each gated
    edge. It follows the requests of u_cpu in order, so a response is matched to its request. A
    transaction in the GPU window (0x2000_1000 page) is an `op` with the time of its request and of
    its response. GPU slot: the control slave signals at the interconnect, sampled before each
    fabric edge, counted per phase. Commits: the commit PC at the marker labels of the image.
    """

    def __init__(self, dut, labels: dict) -> None:
        self.dut = dut
        self.pc_label = {pc: name for name, pc in labels.items()}
        self.commits: dict = {}
        self.phase = "on"
        self.cycle = 0
        self.phase_start = {"on": 0}
        self.ops: list = []
        self._wq: list = []
        self._rq: list = []
        self.reset_ready: Counter = Counter()
        self.slot: dict = defaultdict(lambda: defaultdict(int))
        self.first: dict = defaultdict(dict)
        self._tasks: list = []

    def start(self):
        for coro in (self._run_cpu(), self._run_slot()):
            task = cocotb.start_soon(coro)
            self._tasks.append(task)
            _active_tasks.append(task)
        return self

    def stop(self) -> None:
        for task in self._tasks:
            task.kill()
        self._tasks = []

    def set_phase(self, name: str) -> None:
        self.phase = name
        self.phase_start[name] = self.cycle

    def ops_since(self, t_ns: int) -> list:
        return [op for op in self.ops if op["t_req"] >= t_ns]

    async def _run_cpu(self) -> None:
        s = self.dut.u_soc
        clk = self.dut.cpu_clk_i
        while True:
            await FallingEdge(clk)
            await ReadOnly()
            pre = (
                int(s.cpu_bridge_s_awvalid.value) & int(s.cpu_bridge_s_awready.value),
                int(s.cpu_bridge_s_awaddr.value),
                int(s.cpu_bridge_s_bvalid.value) & int(s.cpu_bridge_s_bready.value),
                int(s.cpu_bridge_s_arvalid.value) & int(s.cpu_bridge_s_arready.value),
                int(s.cpu_bridge_s_araddr.value),
                int(s.cpu_bridge_s_arlen.value),
                int(s.cpu_bridge_s_rvalid.value) & int(s.cpu_bridge_s_rready.value),
                int(s.cpu_bridge_s_rdata.value),
                int(s.cpu_bridge_s_rlast.value),
            )
            await RisingEdge(clk)
            await ReadOnly()
            if not int(s.cpu_gated_clk.value):
                continue
            now = _now_ns()
            self._scoreboard(pre, now)
            if int(self.dut.commit_valid_o.value):
                name = self.pc_label.get(int(self.dut.commit_pc_o.value))
                if name is not None and name not in self.commits:
                    self.commits[name] = now

    def _scoreboard(self, pre: tuple, now: int) -> None:
        aw, awaddr, bh, ar, araddr, arlen, rh, rdata, rlast = pre
        if aw:
            op = None
            if awaddr >> 12 == GPU_WINDOW_PAGE:
                op = {"kind": "write", "addr": awaddr, "t_req": now, "t_resp": None, "data": None}
                self.ops.append(op)
            self._wq.append(op)
        if bh and self._wq:
            op = self._wq.pop(0)
            if op is not None:
                op["t_resp"] = now
        if ar:
            op = None
            if araddr >> 12 == GPU_WINDOW_PAGE:
                op = {"kind": "read", "addr": araddr, "t_req": now, "t_resp": None, "data": None}
                self.ops.append(op)
            self._rq.append([op, arlen + 1])
        if rh and self._rq:
            head = self._rq[0]
            if head[0] is not None and head[0]["data"] is None:
                head[0]["data"] = rdata
            head[1] -= 1
            if rlast or head[1] <= 0:
                self._rq.pop(0)
                if head[0] is not None:
                    head[0]["t_resp"] = now

    async def _run_slot(self) -> None:
        s = self.dut.u_soc
        while True:
            await FallingEdge(self.dut.clk_i)
            await ReadOnly()
            self.cycle += 1
            rst_n = int(s.gpu_domain_rst_n.value)
            v = {
                "aw": int(s.bus_axil_gpu_awvalid.value), "awr": int(s.bus_axil_gpu_awready.value),
                "w": int(s.bus_axil_gpu_wvalid.value), "wr": int(s.bus_axil_gpu_wready.value),
                "ar": int(s.bus_axil_gpu_arvalid.value), "arr": int(s.bus_axil_gpu_arready.value),
                "b": int(s.bus_axil_gpu_bvalid.value), "r": int(s.bus_axil_gpu_rvalid.value),
            }
            if not rst_n and self.cycle > P3_RESET_LOG_FROM_CYCLE:
                self.reset_ready[(v["awr"], v["wr"], v["arr"], v["r"], v["b"])] += 1
            counts = self.slot[self.phase]
            rel = self.cycle - self.phase_start[self.phase]
            for key, on in (
                ("aw_valid", v["aw"]), ("aw_hs", v["aw"] and v["awr"]),
                ("w_valid", v["w"]), ("w_hs", v["w"] and v["wr"]),
                ("ar_valid", v["ar"]), ("ar_hs", v["ar"] and v["arr"]),
                ("b_valid", v["b"]), ("r_valid", v["r"]),
            ):
                if on:
                    counts[key] += 1
                    self.first[self.phase].setdefault(key, rel)


async def _wait_marker(dut, mon, name: str, limit: int) -> bool:
    for _ in range(limit):
        if name in mon.commits:
            return True
        await RisingEdge(dut.clk_i)
    return name in mon.commits


def _p3_op_summary(op) -> dict:
    if op is None:
        return {"issued": False}
    return {
        "issued": True,
        "t_req": op["t_req"],
        "completed": op["t_resp"] is not None,
        "cycles": None if op["t_resp"] is None
        else round((op["t_resp"] - op["t_req"]) / FABRIC_PERIOD_NS),
        "data": op["data"],
    }


async def _p3_poll_op(dut, mon, t_begin: int, limit: int):
    """Poll up to `limit` fabric cycles for the response of the first GPU op since t_begin."""
    for cyc in range(limit):
        await RisingEdge(dut.clk_i)
        ops = mon.ops_since(t_begin)
        if ops and ops[0]["t_resp"] is not None:
            return cyc + 1
    return limit


async def _p3_experiment(dut, cpu_ns: int, kind: str) -> dict:
    words, labels = cfw.gpu_access_image(kind)
    await _confirm_reset_and_rom(dut, cpu_ns, words)
    mon = _P3Monitor(dut, labels).start()
    await _confirm_release(dut)
    row: dict = {"cpu_ns": cpu_ns, "kind": kind, "aborted": None}
    if not await _wait_marker(dut, mon, "ON_ACCESS_DONE", P3_BOUND_CYCLES):
        mon.stop()
        row["aborted"] = "the access with the GPU on did not complete"
        row["on_done"] = False
        row["on_ops"] = [_p3_op_summary(op) for op in mon.ops]
        return row
    row["on_done"] = True
    if not await _wait_marker(dut, mon, "ACCESS_BEGIN", P3_BOUND_CYCLES):
        mon.stop()
        row["aborted"] = "the firmware did not reach the access with the GPU off"
        return row
    if int(dut.u_soc.gpu_domain_rst_n.value) != 0:
        mon.stop()
        row["aborted"] = "the GPU domain reset is not asserted at the access"
        return row
    t_begin = mon.commits["ACCESS_BEGIN"]
    row["fail_seen"] = "FAIL" in mon.commits
    row["on_ops"] = [_p3_op_summary(op) for op in mon.ops if op["t_req"] < t_begin]
    mon.set_phase("off_access")
    waited = await _p3_poll_op(dut, mon, t_begin, P3_BOUND_CYCLES)
    ops = mon.ops_since(t_begin)
    row["off_op"] = _p3_op_summary(ops[0] if ops else None)
    row["off_waited"] = waited
    row["off_commits"] = {n: n in mon.commits for n in ("ACCESS_DONE", "NEXT_DONE")}
    row["off_slot"] = {k: v for k, v in mon.slot["off_access"].items()}
    row["off_first"] = dict(mon.first["off_access"])
    mon.set_phase("after_power_up")
    await _confirm_set_mode(dut, MODE_NORMAL)
    for _ in range(P3_BOUND_CYCLES):
        await RisingEdge(dut.clk_i)
        if int(dut.u_soc.u_pmu.dom_state_q[1].value) == DOM_ON:
            break
    else:
        mon.stop()
        raise RuntimeError("harness: the GPU domain did not return to DOM_ON")
    waited_after = await _p3_poll_op(dut, mon, t_begin, P3_AFTER_POWER_UP_CYCLES)
    ops = mon.ops_since(t_begin)
    row["after_op"] = _p3_op_summary(ops[0] if ops else None)
    row["after_waited"] = waited_after
    row["after_commits"] = {n: n in mon.commits for n in ("ACCESS_DONE", "NEXT_DONE")}
    row["after_slot"] = {k: v for k, v in mon.slot["after_power_up"].items()}
    row["reset_ready"] = dict(mon.reset_ready)
    mon.stop()
    return row


def _p3_describe(row: dict) -> str:
    tag = f"{row['kind']} cpu={row['cpu_ns']}ns"
    if row["aborted"]:
        return f"P3 {tag}: ABORTED: {row['aborted']}"
    op = row["off_op"]
    first = row["off_first"]
    slot = row["off_slot"]
    if not op["issued"]:
        cpu_line = "CPU AXI: no request in the GPU window left the CPU"
    elif op["completed"]:
        cpu_line = f"CPU AXI: request issued, response after {op['cycles']} fabric cycles"
    else:
        cpu_line = (
            f"CPU AXI: request issued, NO response in {row['off_waited']} fabric cycles")
    kind_valid = "ar_valid" if row["kind"] == "read" else "aw_valid"
    kind_hs = "ar_hs" if row["kind"] == "read" else "aw_hs"
    slot_line = (
        f"GPU slot: {kind_valid[:2]} valid first at +{first.get(kind_valid)}, accepted "
        f"(valid and ready) first at +{first.get(kind_hs)}, accepted {slot.get(kind_hs, 0)}x; "
        f"w valid {slot.get('w_valid', 0)} cycles, w accepted {slot.get('w_hs', 0)}x; "
        f"b valid {slot.get('b_valid', 0)} cycles; r valid {slot.get('r_valid', 0)} cycles")
    after = row["after_op"]
    after_line = (
        "after GPU power-up: " +
        ("response arrived" if after.get("completed") else f"still no response in "
         f"{row['after_waited']} fabric cycles"))
    ready = ", ".join(
        f"awready={a} wready={w} arready={ar} rvalid={r} bvalid={b} x{n}"
        for (a, w, ar, r, b), n in sorted(row["reset_ready"].items()))
    return (
        f"P3 {tag}: {cpu_line}; {slot_line}; commits after the access {row['off_commits']}; "
        f"{after_line}; slave outputs while its reset is asserted: {ready}")


async def _p3_sweep(dut) -> list:
    """Read and write at each clock ratio. Cached for the whole file."""
    if "rows" not in _P3_CACHE:
        rows = []
        for cpu_ns in CONFIRM_RATIOS:
            for kind in ("read", "write"):
                row = await _p3_experiment(dut, cpu_ns, kind)
                rows.append(row)
                dut._log.info(_p3_describe(row))
        _P3_CACHE["rows"] = rows
    return _P3_CACHE["rows"]


def _p3_require_reached(rows: list) -> None:
    for row in rows:
        if row["aborted"]:
            raise RuntimeError(f"harness: {row['kind']} cpu={row['cpu_ns']}ns: {row['aborted']}")


@cocotb.test(expect_fail=True)
async def test_p3_gpu_access_while_off_completes_within_bound(dut):
    """Asserts: a register access to the GPU control slave while the GPU domain is off ends within
    a long bound, with an error response or defined data (DS-PMU-185). Stimulus: the CPU reads and
    writes GPU_KERNEL_PC after it has requested GPU_OFF and read STATUS as off, at three clock
    ratios. The bound is P3_BOUND_CYCLES fabric cycles; the control access takes far fewer.

    expect_fail: the review reads that the slave shows arready=1 and awready=1 while in reset and
    never answers, so the master waits. If this test passes, the reading was wrong or the RTL
    changed (an upstream timeout or an error response). The log says what happened at each
    interface."""
    rows = await with_timeout(_p3_sweep(dut), 6000, "us")
    _p3_require_reached(rows)
    bad = [r for r in rows if not r["off_op"].get("completed")]
    assert not bad, (
        f"{len(bad)} of {len(rows)} access(es) did not end within {P3_BOUND_CYCLES} fabric cycles: "
        + "; ".join(f"{r['kind']} cpu={r['cpu_ns']}ns {r['off_op']}" for r in bad[:6]))


@cocotb.test(expect_fail=True)
async def test_p3_control_slave_ready_low_while_in_reset(dut):
    """Asserts: while the GPU domain reset is asserted, awready and arready of the control slave
    are low (AGENTS.md rule 6: a reset value must not advertise availability).

    expect_fail: the review reads awready = ~aw_cap_q and arready = ~ar_cap_q, which are 1 in
    reset. The values are in the log of every access."""
    rows = await with_timeout(_p3_sweep(dut), 6000, "us")
    _p3_require_reached(rows)
    bad = {}
    for row in rows:
        for (awr, _wr, arr, _r, _b), n in row["reset_ready"].items():
            if awr or arr:
                bad[(row["kind"], row["cpu_ns"], f"awready={awr} arready={arr}")] = n
    assert not bad, (
        "the control slave advertised availability while in reset: "
        + "; ".join(f"{k[0]} cpu={k[1]}ns {k[2]} for {n} cycles" for k, n in bad.items()))


@cocotb.test()
async def test_p3_control_access_with_gpu_on_completes(dut):
    """Proves the stimulus and the scoreboard of the P3 tests. With the GPU on, the same image
    writes GPU_KERNEL_PC and reads it back. Both transactions get a response at the CPU interface,
    the read returns the value that was written, and the firmware does not reach its FAIL label.
    The access under test is reached with the GPU domain reset asserted, in every run."""
    rows = await with_timeout(_p3_sweep(dut), 6000, "us")
    _p3_require_reached(rows)
    for row in rows:
        tag = f"{row['kind']} cpu={row['cpu_ns']}ns"
        assert row["on_done"], f"{tag}: the access with the GPU on did not complete"
        assert not row["fail_seen"], f"{tag}: the firmware read back a wrong value"
        on_ops = row["on_ops"]
        assert [o["issued"] and o["completed"] for o in on_ops] == [True, True], f"{tag}: {on_ops}"
        assert on_ops[1]["data"] == cfw.SENTINEL, f"{tag}: read back {on_ops[1]['data']:#x}"
    dut._log.info(f"P3 control: {len(rows)} runs, GPU on: write and read back complete")
