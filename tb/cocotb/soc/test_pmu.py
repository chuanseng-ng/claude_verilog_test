"""
test_pmu.py -- cocotb verification for the behavioral PMU (rtl/soc/pmu.sv). DUT: tb_pmu. Register
map: pmu.sv header (CTRL WMASK=0x3; STATUS and DOMAIN_EN read-only). Mode: 00 NORMAL, 01 CPU_OFF, 10
GPU_OFF, 11 IDLE.
Per-domain FSM (9 states, one action per clock): DOM_ON -> PD_SAVE -> PD_GATE -> PD_ISO -> DOM_OFF
-> PU_RST -> PU_RESTORE -> PU_ISO -> PU_CLK -> DOM_ON. The clock is gated before the clamp rises and the
clamp is released before the clock runs.
Timing contract of every test (calibrated against this RTL and the APB4Master BFM under Verilator;
see test_pmu_mid_sequence_mode_change_no_reversal): right after `await bfm.write(CTRL, ...)`
returns, the sequencer still shows its pre-write state and stays there for one more `RisingEdge`
(two cycles of no visible change). Then it walks one state per cycle. Every ordering test lists the
hold in its expected samples (e.g. `[ON, ON, PD_SAVE, PD_GATE, PD_ISO, OFF, OFF]`).
Tests: reset defaults. Power-down and power-up ordering per domain, per cycle and not only the end
state (ret_save -> iso_en -> clk-gate -> reset-assert and the reverse, no collapse or reorder). A
CTRL write mid-descent does not reverse the in-flight sequence: it completes to OFF, then powers up.
Isolation handshake: tb_pmu models the CPU-domain ack round trip with a configurable latency
(ack_lat_i, 0 = pass-through as in the tests above), a stuck ack (ack_stuck_i) and a forced ack
(ack_force_i, ack_force_val_i). Power-down: the clock is gated before the clamp rises, DOM_PD_ISO lasts ack_lat+1 cycles, and the reset
follows the ack by one cycle, never before it. An ack that is already high when the wait begins does not
end it. Power-up: DOM_PU_ISO lasts ack_lat+1 cycles (4-phase return-to-zero wait) and an ack that is already
low when the wait begins does not end it. A dead ack does not hang: the sequencer proceeds after
ISO_ACK_TIMEOUT cycles in either wait and sets sticky STATUS[3]. Only a reset or a write of 1 to
STATUS_CLR[0] clears it. The GPU walk ignores the CPU ack. A reset restarts the wait counter.
Run: make -C tb/cocotb/soc pmu
Doc: tm:suite:soc-test-pmu
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.apb4_master import APB4Master
import reg_maps  # noqa: E402
from reg_walk import walk_bank  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10  # matches the SoC reference clock

CTRL_OFFSET      = 0x000
STAT_OFFSET      = 0x004
DOMAIN_EN_OFFSET = 0x008
STATUS_CLR_OFFSET = 0x00C

MODE_NORMAL  = 0x0
MODE_CPU_OFF = 0x1
MODE_GPU_OFF = 0x2
MODE_IDLE    = 0x3

CTRL_WMASK = 0x3

# Per-state output tuples: (clk_en, iso_en, rst_n, ret_save, ret_restore).
# Note some tuples coincide numerically across distinct FSM states (e.g.
# DOM_PU_CLK == DOM_ON, DOM_PD_ISO == DOM_PU_RST, DOM_PD_GATE == DOM_PU_ISO)
# — the tests below disambiguate by SEQUENCE POSITION, not tuple identity
# alone, which is why every ordering test asserts a full observed list
# against a full expected list rather than checking isolated samples.
ON         = (1, 0, 1, 0, 0)
PD_SAVE    = (1, 0, 1, 1, 0)
PD_GATE    = (0, 0, 1, 0, 0)
PD_ISO     = (0, 1, 1, 0, 0)
OFF        = (0, 1, 0, 0, 0)
PU_RST     = (0, 1, 1, 0, 0)
PU_RESTORE = (0, 1, 1, 0, 1)
PU_ISO     = (0, 0, 1, 0, 0)
PU_CLK     = (1, 0, 1, 0, 0)

# ---------------------------------------------------------------------------
# Module-level task handle list (guard against cross-test coroutine leakage)
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _start_clock_and_reset(dut) -> None:
    """Start the clock and apply synchronous reset. Idle the APB4 bus."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.ack_lat_i.value       = 0
    dut.ack_stuck_i.value     = 0
    dut.ack_force_i.value     = 0
    dut.ack_force_val_i.value = 0
    dut.rst_n.value    = 0
    dut.psel.value     = 0
    dut.penable.value  = 0
    dut.pwrite.value   = 0
    dut.paddr.value    = 0
    dut.pwdata.value   = 0
    dut.pstrb.value    = 0xF

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def _make_apb_bfm(dut) -> APB4Master:
    """Construct APB4Master BFM targeting the DUT's flat APB4 ports."""
    return APB4Master(dut, "", dut.clk)


def _sample_cpu(dut) -> tuple:
    return (
        int(dut.cpu_clk_en_o.value),
        int(dut.cpu_iso_en_o.value),
        int(dut.cpu_rst_n_o.value),
        int(dut.cpu_ret_save_o.value),
        int(dut.cpu_ret_restore_o.value),
    )


def _sample_gpu(dut) -> tuple:
    return (
        int(dut.gpu_clk_en_o.value),
        int(dut.gpu_iso_en_o.value),
        int(dut.gpu_rst_n_o.value),
        int(dut.gpu_ret_save_o.value),
        int(dut.gpu_ret_restore_o.value),
    )


def _raw_write_setup(dut, addr: int, data: int) -> None:
    """Drive the SETUP phase of a raw APB4 write (bypasses APB4Master so the
    caller can interleave per-cycle DUT sampling with the write's own
    clock edges instead of losing visibility during a blocking bfm.write())."""
    dut.psel.value    = 1
    dut.penable.value = 0
    dut.pwrite.value  = 1
    dut.paddr.value   = addr
    dut.pwdata.value  = data
    dut.pstrb.value   = 0xF


def _raw_write_access(dut) -> None:
    """Drive the ACCESS phase (pready is hardwired 1 — commits this edge)."""
    dut.penable.value = 1


def _raw_write_idle(dut) -> None:
    dut.psel.value    = 0
    dut.penable.value = 0
    dut.pwrite.value  = 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_pmu_reset_defaults(dut):
    """After reset: CTRL=0, STATUS=0x3, DOMAIN_EN=0x33; both domains on,
    un-isolated, un-reset (matches pre-PMU soc_top defaults)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ctrl, ok1 = await bfm.read(CTRL_OFFSET)
    status, ok2 = await bfm.read(STAT_OFFSET)
    domain_en, ok3 = await bfm.read(DOMAIN_EN_OFFSET)

    assert ok1 and ok2 and ok3, "reset-default reads returned SLVERR"
    assert ctrl == 0x0000_0000, f"CTRL expected 0 at reset, got 0x{ctrl:08x}"
    assert status == 0x0000_0003, f"STATUS expected 0x3 at reset, got 0x{status:08x}"
    assert domain_en == 0x0000_0033, f"DOMAIN_EN expected 0x33 at reset, got 0x{domain_en:08x}"

    assert _sample_cpu(dut) == ON, "CPU domain outputs must show DOM_ON at reset"
    assert _sample_gpu(dut) == ON, "GPU domain outputs must show DOM_ON at reset"
    dut._log.info(f"Reset defaults OK: CTRL=0x{ctrl:08x} STATUS=0x{status:08x} DOMAIN_EN=0x{domain_en:08x}")


@cocotb.test()
async def test_pmu_cpu_power_down_ordering(dut):
    """Write CTRL=CPU_OFF; sample cpu_* every single clock cycle. Assert the
    EXACT sequence ON -> PD_SAVE -> PD_GATE -> PD_ISO -> OFF (steady), one
    action per cycle. GPU must remain at ON throughout (independence)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    assert ok, "CTRL write (CPU_OFF) returned SLVERR"

    observed = [_sample_cpu(dut)]
    for _ in range(6):
        await RisingEdge(dut.clk)
        observed.append(_sample_cpu(dut))
        assert _sample_gpu(dut) == ON, "GPU domain perturbed by a CPU-only mode request"

    # Empirically calibrated APB4Master.write() timing: the FSM holds its
    # pre-write state for one extra cycle beyond the write's own return
    # (SW commit propagation through the register bank + comb re-decode),
    # THEN walks the down sequence one state per cycle.
    expected = [ON, ON, PD_SAVE, PD_GATE, PD_ISO, OFF, OFF]
    assert observed == expected, f"CPU power-down ordering mismatch: {observed} != {expected}"
    dut._log.info("CPU power-down ordering: ON->PD_SAVE->PD_GATE->PD_ISO->OFF confirmed per-cycle")


@cocotb.test()
async def test_pmu_cpu_power_up_ordering(dut):
    """Drive CPU domain to settled OFF, then write CTRL=NORMAL and sample
    cpu_* every cycle. Assert the EXACT sequence OFF -> PU_RST -> PU_RESTORE ->
    PU_ISO -> PU_CLK -> ON: reset released -> ret_restore -> iso de-asserted
    -> clock ungated."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    assert ok
    await ClockCycles(dut.clk, 6)  # ON,ON -> SAVE -> ISO -> GATE -> OFF -> OFF(settle margin)
    assert _sample_cpu(dut) == OFF, "precondition failed: CPU domain not settled OFF"

    ok2 = await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    assert ok2, "CTRL write (NORMAL) returned SLVERR"

    observed = [_sample_cpu(dut)]
    for _ in range(6):
        await RisingEdge(dut.clk)
        observed.append(_sample_cpu(dut))

    expected = [OFF, OFF, PU_RST, PU_RESTORE, PU_ISO, PU_CLK, ON]
    assert observed == expected, f"CPU power-up ordering mismatch: {observed} != {expected}"
    dut._log.info("CPU power-up ordering: OFF->PU_RST->PU_RESTORE->PU_ISO->PU_CLK->ON confirmed per-cycle")


@cocotb.test()
async def test_pmu_gpu_power_down_ordering(dut):
    """GPU_OFF counterpart of test_pmu_cpu_power_down_ordering. CPU must
    remain at ON throughout (independence)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, MODE_GPU_OFF)
    assert ok, "CTRL write (GPU_OFF) returned SLVERR"

    observed = [_sample_gpu(dut)]
    for _ in range(6):
        await RisingEdge(dut.clk)
        observed.append(_sample_gpu(dut))
        assert _sample_cpu(dut) == ON, "CPU domain perturbed by a GPU-only mode request"

    expected = [ON, ON, PD_SAVE, PD_GATE, PD_ISO, OFF, OFF]
    assert observed == expected, f"GPU power-down ordering mismatch: {observed} != {expected}"
    dut._log.info("GPU power-down ordering: ON->PD_SAVE->PD_GATE->PD_ISO->OFF confirmed per-cycle")


@cocotb.test()
async def test_pmu_gpu_power_up_ordering(dut):
    """GPU_OFF counterpart of test_pmu_cpu_power_up_ordering."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, MODE_GPU_OFF)
    assert ok
    await ClockCycles(dut.clk, 6)
    assert _sample_gpu(dut) == OFF, "precondition failed: GPU domain not settled OFF"

    ok2 = await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    assert ok2, "CTRL write (NORMAL) returned SLVERR"

    observed = [_sample_gpu(dut)]
    for _ in range(6):
        await RisingEdge(dut.clk)
        observed.append(_sample_gpu(dut))

    expected = [OFF, OFF, PU_RST, PU_RESTORE, PU_ISO, PU_CLK, ON]
    assert observed == expected, f"GPU power-up ordering mismatch: {observed} != {expected}"
    dut._log.info("GPU power-up ordering: OFF->PU_RST->PU_RESTORE->PU_ISO->PU_CLK->ON confirmed per-cycle")


@cocotb.test()
async def test_pmu_idle_both_domains_ordering(dut):
    """IDLE (both domains off): both CPU and GPU sequencers (identical
    generate-replicated FSMs, same mode register) walk the down ordering in
    lockstep, then the up ordering in lockstep after a NORMAL write."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, MODE_IDLE)
    assert ok, "CTRL write (IDLE) returned SLVERR"

    observed_cpu = [_sample_cpu(dut)]
    observed_gpu = [_sample_gpu(dut)]
    for _ in range(6):
        await RisingEdge(dut.clk)
        observed_cpu.append(_sample_cpu(dut))
        observed_gpu.append(_sample_gpu(dut))

    expected_down = [ON, ON, PD_SAVE, PD_GATE, PD_ISO, OFF, OFF]
    assert observed_cpu == expected_down, f"CPU IDLE power-down mismatch: {observed_cpu}"
    assert observed_gpu == expected_down, f"GPU IDLE power-down mismatch: {observed_gpu}"

    ok2 = await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    assert ok2, "CTRL write (NORMAL, from IDLE) returned SLVERR"

    observed_cpu2 = [_sample_cpu(dut)]
    observed_gpu2 = [_sample_gpu(dut)]
    for _ in range(6):
        await RisingEdge(dut.clk)
        observed_cpu2.append(_sample_cpu(dut))
        observed_gpu2.append(_sample_gpu(dut))

    expected_up = [OFF, OFF, PU_RST, PU_RESTORE, PU_ISO, PU_CLK, ON]
    assert observed_cpu2 == expected_up, f"CPU IDLE power-up mismatch: {observed_cpu2}"
    assert observed_gpu2 == expected_up, f"GPU IDLE power-up mismatch: {observed_gpu2}"
    dut._log.info("IDLE: both domains sequence down and up in lockstep, correctly")


@cocotb.test()
async def test_pmu_busy_semantics(dut):
    """STATUS[2] (busy) is 1 while either domain is mid-sequence (neither
    settled DOM_ON nor DOM_OFF), 0 once both are settled. APB reads never
    assert pwrite, so they cannot perturb the sequencer being observed."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    status0, ok = await bfm.read(STAT_OFFSET)
    assert ok
    assert (status0 >> 2) & 0x1 == 0, "busy must be 0 at reset"
    assert status0 & 0x3 == 0x3, "both domains must read on at reset"

    ok = await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    assert ok
    assert _sample_cpu(dut) == ON, "target not yet re-sampled immediately after write"

    # ON,ON -> PD_SAVE -> PD_GATE: definitely mid-sequence.
    await ClockCycles(dut.clk, 3)
    assert _sample_cpu(dut) == PD_GATE, "sanity: expected PD_GATE mid-descent"

    status_mid, ok = await bfm.read(STAT_OFFSET)
    assert ok
    assert (status_mid >> 2) & 0x1 == 1, "busy must be 1 while CPU domain mid-sequence"
    assert status_mid & 0x1 == 0, "cpu_domain_on must be 0 while mid-sequence"
    assert (status_mid >> 1) & 0x1 == 1, "gpu_domain_on must stay 1 (GPU untouched)"

    # Margin covers the STATUS register's one-cycle HW-latch delay and the
    # extra edges consumed by the STATUS read above.
    await ClockCycles(dut.clk, 6)
    assert _sample_cpu(dut) == OFF, "sanity: expected CPU settled OFF"

    status_off, ok = await bfm.read(STAT_OFFSET)
    assert ok
    assert (status_off >> 2) & 0x1 == 0, "busy must be 0 once CPU settled OFF"
    assert status_off & 0x1 == 0, "cpu_domain_on must be 0 when settled OFF"
    assert (status_off >> 1) & 0x1 == 1, "gpu_domain_on must remain 1"

    ok = await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    assert ok
    await ClockCycles(dut.clk, 9)
    assert _sample_cpu(dut) == ON, "sanity: expected CPU settled back ON"

    status_on, ok = await bfm.read(STAT_OFFSET)
    assert ok
    assert (status_on >> 2) & 0x1 == 0, "busy must be 0 once both domains settled ON"
    assert status_on & 0x3 == 0x3, "both domains must read on again after power-up"
    dut._log.info("busy semantics confirmed: 1 mid-sequence, 0 once settled (both directions)")


@cocotb.test()
async def test_pmu_ctrl_wmask(dut):
    """Writing 0xFFFF_FFFF to CTRL must leave only bits[1:0] set (WMASK=0x3);
    bits[31:2] must read back 0."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, 0xFFFF_FFFF)
    assert ok, "CTRL write returned SLVERR"
    await ClockCycles(dut.clk, 2)

    data, ok2 = await bfm.read(CTRL_OFFSET)
    assert ok2, "CTRL readback returned SLVERR"
    assert data == CTRL_WMASK, (
        f"CTRL WMASK violation: expected only bits[1:0] set (0x{CTRL_WMASK:x}), "
        f"got 0x{data:08x}"
    )
    assert (data & ~CTRL_WMASK) == 0, f"CTRL[31:2] must read 0, got 0x{data:08x}"
    dut._log.info(f"CTRL WMASK confirmed: write 0xFFFFFFFF -> readback 0x{data:08x}")


@cocotb.test()
async def test_pmu_status_domain_en_readonly(dut):
    """STATUS and DOMAIN_EN are RO (WMASK=0): SW writes must not change them.
    apb4_register_bank gives SW-write-wins-over-HW-write on a same-cycle
    collision, but WMASK=0 masks the SW write to a no-op at the mask-and
    stage (regs & ~0 | pwdata & 0 == regs) independent of that priority
    rule — this test confirms that invariant explicitly for the PMU's RO
    registers."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    status_before, ok1 = await bfm.read(STAT_OFFSET)
    domain_before, ok2 = await bfm.read(DOMAIN_EN_OFFSET)
    assert ok1 and ok2, "pre-write reads returned SLVERR"

    ok3 = await bfm.write(STAT_OFFSET, 0xFFFF_FFFF)
    ok4 = await bfm.write(DOMAIN_EN_OFFSET, 0xFFFF_FFFF)
    assert ok3 and ok4, "APB4 does not error on RO writes — expected OKAY, write silently dropped"

    await ClockCycles(dut.clk, 2)

    status_after, ok5 = await bfm.read(STAT_OFFSET)
    domain_after, ok6 = await bfm.read(DOMAIN_EN_OFFSET)
    assert ok5 and ok6, "post-write reads returned SLVERR"

    assert status_after == status_before, (
        f"STATUS changed after RO write attempt: before=0x{status_before:08x}, "
        f"after=0x{status_after:08x}"
    )
    assert domain_after == domain_before, (
        f"DOMAIN_EN changed after RO write attempt: before=0x{domain_before:08x}, "
        f"after=0x{domain_after:08x}"
    )
    dut._log.info("STATUS/DOMAIN_EN RO property confirmed — writes silently discarded")


@cocotb.test()
async def test_pmu_mid_sequence_mode_change_no_reversal(dut):
    """Design intent: a domain's target is only
    re-sampled while settled at DOM_ON or DOM_OFF. Writing CTRL=NORMAL while
    the CPU domain is mid-descent (fired at PD_SAVE, the earliest possible
    point) must NOT reverse the in-flight power-down — it must complete
    PD_SAVE -> PD_GATE -> PD_ISO -> OFF exactly as if the write had never
    happened, settle at OFF for exactly one cycle, and only then begin
    powering back up.

    The mid-sequence write is driven with raw APB signals (not APB4Master)
    so cpu_* outputs can be sampled on every single clock edge with no gap,
    including during the write's own SETUP/ACCESS cycles."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    ok = await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    assert ok, "CTRL write (CPU_OFF) returned SLVERR"

    observed = [_sample_cpu(dut)]  # sample 0: ON (target not yet re-sampled)
    await RisingEdge(dut.clk)
    observed.append(_sample_cpu(dut))  # sample 1: ON (still not re-sampled)
    assert observed[-1] == ON, f"expected ON (pre-transition hold), got {observed[-1]}"
    await RisingEdge(dut.clk)
    observed.append(_sample_cpu(dut))  # sample 2: expect PD_SAVE
    assert observed[-1] == PD_SAVE, f"expected PD_SAVE before firing reversal, got {observed[-1]}"

    # Fire the reversal write (CTRL=NORMAL) at the earliest possible point
    # in the descent, interleaved cycle-by-cycle with sampling.
    _raw_write_setup(dut, CTRL_OFFSET, MODE_NORMAL)
    await RisingEdge(dut.clk)          # SETUP edge
    observed.append(_sample_cpu(dut))  # sample 3
    _raw_write_access(dut)
    await RisingEdge(dut.clk)          # ACCESS edge -- CTRL commits here
    observed.append(_sample_cpu(dut))  # sample 4
    _raw_write_idle(dut)

    for _ in range(5):
        await RisingEdge(dut.clk)
        observed.append(_sample_cpu(dut))
        assert _sample_gpu(dut) == ON, "GPU perturbed by a CPU-only mid-sequence write"

    # Exact per-cycle trace (calibrated against this same RTL/BFM timing as
    # the other ordering tests): the descent completes in full and
    # UNREVERSED (ON,ON,PD_SAVE,PD_GATE,PD_ISO) despite the reversal write
    # landing mid-descent; OFF is visited for exactly one cycle; only then
    # does the ascent begin (PU_RST,PU_RESTORE,PU_ISO,PU_CLK).
    expected = [
        ON, ON, PD_SAVE, PD_GATE, PD_ISO,   # full descent completes, no reversal
        OFF,                                 # settles OFF for exactly one cycle
        PU_RST, PU_RESTORE, PU_ISO, PU_CLK, # then powers back up in order
    ]
    assert observed == expected, (
        f"mid-sequence CTRL write reversed or corrupted the FSM ordering: "
        f"{observed} != {expected}"
    )
    # Belt-and-braces semantic checks, independent of the exact list above:
    # no reversal to ON before OFF is reached, and the ascent-only tuple
    # (PU_RESTORE) never appears before the descent settles at OFF.
    off_idx = observed.index(OFF)
    assert ON not in observed[2:off_idx], f"reversal detected before OFF: {observed}"
    assert PU_RESTORE not in observed[:off_idx], f"ascent observed before descent reached OFF: {observed}"
    dut._log.info(
        "mid-sequence mode change confirmed: in-flight power-down completes "
        "unreversed, power-up begins only after settling at OFF"
    )

# ---------------------------------------------------------------------------
# Isolation handshake
# ---------------------------------------------------------------------------

ISO_ACK_TIMEOUT = 16  # tb_pmu's ISO_ACK_TIMEOUT parameter default
STATUS_TO_BIT = 3

DOM_ON, DOM_PD_SAVE, DOM_PD_ISO, DOM_PD_GATE, DOM_OFF = 0, 1, 2, 3, 4
DOM_PU_RST, DOM_PU_CLK, DOM_PU_RESTORE, DOM_PU_ISO = 5, 6, 7, 8


def _snap(dut, dom: int = 0) -> tuple:
    """(dom_state_q, ack as the PMU sees it, cpu output tuple) at the current instant."""
    return (
        int(dut.u_dut.dom_state_q[dom].value),
        int(dut.cpu_iso_ack_o.value),
        _sample_cpu(dut),
    )


async def _trace(dut, n: int, dom: int = 0) -> list:
    out = [_snap(dut, dom)]
    for _ in range(n):
        await RisingEdge(dut.clk)
        out.append(_snap(dut, dom))
    return out


def _rle(states: list) -> list:
    out: list = []
    for s_ in states:
        if out and out[-1][0] == s_:
            out[-1][1] += 1
        else:
            out.append([s_, 1])
    return [tuple(x) for x in out]


async def _wait_state(dut, target: int, limit: int = 200, dom: int = 0) -> None:
    for _ in range(limit):
        if int(dut.u_dut.dom_state_q[dom].value) == target:
            return
        await RisingEdge(dut.clk)
    raise AssertionError(f"dom_state_q[{dom}] never reached {target}")


async def _status(bfm) -> int:
    val, ok = await bfm.read(STAT_OFFSET)
    assert ok, "STATUS read returned SLVERR"
    return val


async def _down(dut, bfm, lat: int, n: int = 0) -> list:
    """CPU_OFF from a settled-ON domain; returns the per-cycle trace until well past OFF."""
    dut.ack_lat_i.value = lat
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    return await _trace(dut, n or (12 + lat))


@cocotb.test()
async def test_pmu_cpu_power_down_waits_for_ack(dut):
    """The clock is gated before the clamp rises. DOM_PD_ISO lasts ack_lat+1 cycles and the reset
    follows the first high ack by one cycle."""
    for lat in (0, 1, 2, 5, 10):
        _kill_active_tasks()
        await _start_clock_and_reset(dut)
        bfm = _make_apb_bfm(dut)
        tr = await _down(dut, bfm, lat)
        states = [t[0] for t in tr]
        rle = _rle(states)
        assert rle[:4] == [(DOM_ON, 2), (DOM_PD_SAVE, 1), (DOM_PD_GATE, 1), (DOM_PD_ISO, lat + 1)], (
            f"lat={lat}: walk {rle}")
        assert rle[4][0] == DOM_OFF, f"lat={lat}: walk {rle}"
        o = states.index(DOM_OFF)
        first_ack = [t[1] for t in tr].index(1)
        assert o == first_ack + 1, f"lat={lat}: reset must follow the first high ack by one cycle"
        # The ack is low through the wait and high on its last cycle.
        iso_acks = [t[1] for t in tr if t[0] == DOM_PD_ISO]
        assert iso_acks == [0] * lat + [1], f"lat={lat}: ack during PD_ISO {iso_acks}"
        # The clock is gated whenever the clamp request is high, and the reset never moves before the ack.
        for i, t in enumerate(tr):
            if t[2][1] == 1:
                assert t[2][0] == 0, f"lat={lat}: clamp request high with the clock enabled @{i}"
            if i <= first_ack:
                assert t[2][2] == 1, f"lat={lat}: reset moved before the ack @{i}"
    dut._log.info("power-down waits exactly for the ack across latency 0/1/2/5/10")


@cocotb.test()
async def test_pmu_cpu_power_up_waits_for_ack_release(dut):
    """DOM_PU_ISO lasts ack_lat+1 cycles (iso_en already low, clock still gated); the clock is
    ungated only after the ack falls."""
    for lat in (0, 1, 3, 10):
        _kill_active_tasks()
        await _start_clock_and_reset(dut)
        bfm = _make_apb_bfm(dut)
        await _down(dut, bfm, lat)
        await _wait_state(dut, DOM_OFF)
        assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
        tr = await _trace(dut, 14 + lat)
        states = [t[0] for t in tr]
        rle = _rle(states)
        assert rle[:6] == [(DOM_OFF, 2), (DOM_PU_RST, 1), (DOM_PU_RESTORE, 1), (DOM_PU_ISO, lat + 1),
                           (DOM_PU_CLK, 1), (DOM_ON, rle[5][1])], f"lat={lat}: walk {rle}"
        pu = [t for t in tr if t[0] == DOM_PU_ISO]
        assert all(t[2][1] == 0 and t[2][0] == 0 for t in pu), (
            "iso_en must already be de-asserted and the clock still gated in DOM_PU_ISO")
        assert [t[1] for t in pu] == [1] * lat + [0], f"lat={lat}: ack during PU_ISO {[t[1] for t in pu]}"
    dut._log.info("power-up waits exactly for the ack release across latency 0/1/3/10")


@cocotb.test()
async def test_pmu_back_to_back_no_stale_ack(dut):
    """Power-down requested immediately after a power-up must not be satisfied by the old ack."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    lat = 10
    await _down(dut, bfm, lat)
    await _wait_state(dut, DOM_OFF)
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    await _wait_state(dut, DOM_ON)
    # No idle gap: the next request goes in the very cycle the domain reads ON.
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    tr = await _trace(dut, 30)
    pd = [t for t in tr if t[0] == DOM_PD_ISO]
    assert pd, "second power-down never reached DOM_PD_ISO"
    assert pd[0][1] == 0, "ack was still high on entry to DOM_PD_ISO: stale ack from the last cycle"
    assert len(pd) == lat + 1, (
        f"second power-down spent {len(pd)} cycles in DOM_PD_ISO, expected {lat + 1}: the wait was "
        "satisfied by a stale ack")
    dut._log.info("back-to-back power cycle: the second power-down waited its full ack latency")


@cocotb.test()
async def test_pmu_iso_ack_timeout_power_down(dut):
    """A dead ack: proceed after ISO_ACK_TIMEOUT cycles and flag STATUS[3]. The flag is sticky: a
    power-up and a healthy power-down leave it set and only STATUS_CLR clears it. Every wait gets
    the FULL timeout (the counter does not carry over). With the ack stuck low the power-up wait
    cannot see a high ack, so it times out too."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    assert (await _status(bfm)) == 0x3, "STATUS[3] must be 0 at reset"

    dut.ack_stuck_i.value = 1                      # ack frozen low
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    tr = await _trace(dut, ISO_ACK_TIMEOUT + 12)
    rle = _rle([t[0] for t in tr])
    assert rle[3] == (DOM_PD_ISO, ISO_ACK_TIMEOUT), f"timeout wait length: {rle}"
    assert [r[0] for r in rle[:5]] == [DOM_ON, DOM_PD_SAVE, DOM_PD_GATE, DOM_PD_ISO, DOM_OFF], rle
    assert (await _status(bfm)) == 0b1010, "STATUS[3] must be set (cpu off, gpu on, timeout)"

    # Up with the ack still low: the wait has no high ack to qualify it, so it burns the full timeout.
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    tr = await _trace(dut, ISO_ACK_TIMEOUT + 14)
    assert dict(_rle([t[0] for t in tr])).get(DOM_PU_ISO) == ISO_ACK_TIMEOUT
    await _wait_state(dut, DOM_ON)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "STATUS[3] must be sticky through the power-up"

    # Clear it, then a second dead-ack power-down gets the full timeout and re-flags.
    assert await bfm.write(STATUS_CLR_OFFSET, 1)
    assert not (await _status(bfm)) >> STATUS_TO_BIT & 1, "STATUS_CLR must clear the flag"
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    tr = await _trace(dut, ISO_ACK_TIMEOUT + 12)
    assert _rle([t[0] for t in tr])[3] == (DOM_PD_ISO, ISO_ACK_TIMEOUT), "counter carried over"
    await _wait_state(dut, DOM_OFF)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "the second timeout must re-flag"
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    await _wait_state(dut, DOM_ON, limit=ISO_ACK_TIMEOUT + 30)

    # A healthy power-down does not clear the flag. Only STATUS_CLR does.
    dut.ack_stuck_i.value = 0
    dut.ack_lat_i.value = 3
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    tr = await _trace(dut, 20)
    assert _rle([t[0] for t in tr])[3] == (DOM_PD_ISO, 4), "healthy power-down must wait lat+1"
    await _wait_state(dut, DOM_OFF)
    assert (await _status(bfm)) == 0b1010, "STATUS[3] must survive a healthy power-down"
    assert await bfm.write(STATUS_CLR_OFFSET, 1)
    assert (await _status(bfm)) == 0b0010, "STATUS_CLR must clear the flag"


@cocotb.test()
async def test_pmu_iso_ack_timeout_power_up(dut):
    """The power-up wait (ack must FALL) times out too, and flags STATUS[3]. The flag is low before it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _down(dut, bfm, 2)
    await _wait_state(dut, DOM_OFF)
    assert not (await _status(bfm)) >> STATUS_TO_BIT & 1, "healthy power-down must not flag"

    dut.ack_force_val_i.value = 1                  # the ack never falls
    dut.ack_force_i.value = 1
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    tr = await _trace(dut, ISO_ACK_TIMEOUT + 14)
    rle = _rle([t[0] for t in tr])
    pu = [r for r in rle if r[0] == DOM_PU_ISO]
    assert pu == [(DOM_PU_ISO, ISO_ACK_TIMEOUT)], f"PU_ISO timeout length: {rle}"
    assert rle[-1][0] == DOM_ON, rle
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "PU_ISO timeout must set STATUS[3]"


@cocotb.test()
async def test_pmu_gpu_ignores_cpu_ack(dut):
    """The GPU walk is bit-identical whatever the CPU ack does (same clock, no ack)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    dut.ack_lat_i.value = 10
    dut.ack_force_val_i.value = 0
    dut.ack_force_i.value = 1                      # CPU ack never comes
    assert await bfm.write(CTRL_OFFSET, MODE_IDLE)
    tr = await _trace(dut, 8, dom=1)
    rle = _rle([t[0] for t in tr])
    assert rle[:5] == [(DOM_ON, 2), (DOM_PD_SAVE, 1), (DOM_PD_GATE, 1), (DOM_PD_ISO, 1),
                       (DOM_OFF, rle[4][1])], f"GPU walk disturbed by the CPU ack: {rle}"
    # While the CPU is still waiting, the GPU is already off.
    assert int(dut.u_dut.dom_state_q[0].value) == DOM_PD_ISO
    await _wait_state(dut, DOM_OFF, dom=0)
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    tr = await _trace(dut, 10, dom=1)
    rle = _rle([t[0] for t in tr])
    assert rle[:6] == [(DOM_OFF, 2), (DOM_PU_RST, 1), (DOM_PU_RESTORE, 1), (DOM_PU_ISO, 1),
                       (DOM_PU_CLK, 1), (DOM_ON, rle[5][1])], f"GPU power-up disturbed: {rle}"


@cocotb.test()
async def test_pmu_reset_during_iso_wait(dut):
    """A reset restarts the wait and clears the sticky flag (reset-clear of STATUS[3] included)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    dut.ack_stuck_i.value = 1

    # Leg 1: a timeout sets the flag, a reset clears it (a flag with no reset would survive).
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    await _wait_state(dut, DOM_OFF, limit=ISO_ACK_TIMEOUT + 20)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "precondition: the timeout must set STATUS[3]"
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    assert (await _status(bfm)) == 0x3, "reset must clear STATUS[3] and return both domains to ON"

    # Leg 2: a reset in the middle of a wait restarts the counter.
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    await _wait_state(dut, DOM_PD_ISO)
    await ClockCycles(dut.clk, 8)                  # counter now ~8 of 16
    assert int(dut.u_dut.dom_state_q[0].value) == DOM_PD_ISO

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    assert int(dut.u_dut.dom_state_q[0].value) == DOM_ON, "reset must return the domain to ON"

    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    tr = await _trace(dut, ISO_ACK_TIMEOUT + 12)
    assert _rle([t[0] for t in tr])[3] == (DOM_PD_ISO, ISO_ACK_TIMEOUT), (
        "the wait counter survived the reset: the post-reset wait was shorter than the timeout")
    await _wait_state(dut, DOM_OFF)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1


@cocotb.test()
async def test_pmu_mid_wait_mode_flip_no_reversal(dut):
    """CTRL=NORMAL written while the CPU waits for the ack does not reverse the power-down."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    lat = 10
    dut.ack_lat_i.value = lat
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    await _wait_state(dut, DOM_PD_ISO)
    await ClockCycles(dut.clk, 2)
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)       # flip mid-wait
    tr = await _trace(dut, 40)
    rle = _rle([t[0] for t in tr])
    order = [r[0] for r in rle]
    assert order[:5] == [DOM_PD_ISO, DOM_OFF, DOM_PU_RST, DOM_PU_RESTORE, DOM_PU_ISO], order
    assert DOM_ON not in order[:order.index(DOM_OFF)], f"reversed before OFF: {order}"
    assert order[-1] == DOM_ON



# -- Register walk: reset/idle values, RO/RW masks, byte lanes, unmapped words ------

@cocotb.test()
async def test_register_walk(dut):
    """Walk every PMU register against the documented map (reg_maps.PMU); the power-mode request field is never driven."""
    await _start_clock_and_reset(dut)
    m = _make_apb_bfm(dut)
    regs, first = reg_maps.BANKS["pmu"]
    await walk_bank(m, regs, first, log=dut._log)


# ---------------------------------------------------------------------------
# DOMAIN_EN read-back across a full power cycle
# ---------------------------------------------------------------------------

def _domain_en_bitmap(cpu: tuple, gpu: tuple) -> int:
    """DOMAIN_EN word (pmu.sv hw_wdata[2]): clk_en, iso_en, rst_n, ret_save, ret_restore per domain."""
    c_clk, c_iso, c_rst, c_save, c_rest = cpu
    g_clk, g_iso, g_rst, g_save, g_rest = gpu
    return (
        c_clk | (g_clk << 1) | (c_iso << 2) | (g_iso << 3) | (c_rst << 4) | (g_rst << 5)
        | (c_save << 6) | (c_rest << 7) | (g_save << 8) | (g_rest << 9)
    )


@cocotb.test()
async def test_pmu_domain_en_mirrors_sequencer(dut):
    """PMU_DOMAIN_EN, read back every cycle through a full IDLE power cycle, is the registered image
    of the ten sequencer outputs one cycle later -- including the isolation and retention flags that
    are high only for one or two cycles of the sequence.  Down and up are both walked, so every
    DOMAIN_EN bit [9:0] is observed high and low through the real read path."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    seen = set()
    for mode in (MODE_IDLE, MODE_NORMAL):
        assert await bfm.write(CTRL_OFFSET, mode)
        dut.pwrite.value = 0
        dut.paddr.value = DOMAIN_EN_OFFSET
        prev = None
        for _ in range(9):
            await RisingEdge(dut.clk)
            got = int(dut.prdata.value)
            if prev is not None:
                assert got == prev, f"mode {mode}: DOMAIN_EN {got:#05x}, outputs one cycle earlier gave {prev:#05x}"
                seen.add(prev)
            prev = _domain_en_bitmap(_sample_cpu(dut), _sample_gpu(dut))
    ever_high = ever_low = 0
    for word in seen:
        ever_high |= word
        ever_low |= ~word & 0x3FF
    assert ever_high == 0x3FF, f"DOMAIN_EN bits never seen high: {0x3FF & ~ever_high:#05x}"
    assert ever_low == 0x3FF, f"DOMAIN_EN bits never seen low: {0x3FF & ~ever_low:#05x}"


# =============================================================================
# Stale acknowledge and PMU reset from OFF (unit level).
# Doc: ds:mod:pmu
#
#   P1  After a power-up whose acknowledge wait timed out, the acknowledge input can still be
#       high. The power-down wait accepts only an acknowledge that it saw low first, so the stale
#       level cannot end it: the wait runs the full ISO_ACK_TIMEOUT and sets STATUS[3]. The
#       power-up wait mirrors this: it accepts only an acknowledge that it saw high first.
#   P4  A PMU reset in DOM_OFF sets the clock enable, the clamp and the reset of the domain to
#       their DOM_ON values at one edge, so the power-up order of DS-PMU-022 does not apply. The
#       owner accepted this behaviour, so the test that asserts the sequenced order is marked
#       expect_fail: it must fail while the behaviour exists.
# A harness fault raises RuntimeError, not AssertionError, so expect_fail cannot hide it. The
# expect_fail test has a normal companion test that proves the checker and the stimulus.
# =============================================================================

# ack_lat_i for the power-up wait of the stale case: longer than ISO_ACK_TIMEOUT, so the wait times
# out while the acknowledge is still high.
P1_SLOW_RELEASE_LATENCY = 60
P1_HEALTHY_LATENCY = 3


async def _harness_wait_state(dut, target: int, limit: int = 200) -> None:
    """_wait_state with a harness fault as RuntimeError, which expect_fail cannot hide."""
    try:
        await _wait_state(dut, target, limit=limit)
    except AssertionError as exc:
        raise RuntimeError(f"harness: {exc}") from None


async def _harness_status(bfm) -> int:
    try:
        return await _status(bfm)
    except AssertionError as exc:
        raise RuntimeError(f"harness: {exc}") from None


async def _p1_experiment(dut, up_lat: int) -> dict:
    """Healthy power-down, power-up with ack latency up_lat, flag cleared, power-down at once.

    Returns what the harness and the checker need. A step that does not happen raises
    RuntimeError. STATUS[3] is cleared before the second power-down, so a flag set after it was
    set by that power-down."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _down(dut, bfm, P1_HEALTHY_LATENCY)
    await _harness_wait_state(dut, DOM_OFF)
    dut.ack_lat_i.value = up_lat
    if not await bfm.write(CTRL_OFFSET, MODE_NORMAL):
        raise RuntimeError("harness: the power-up CTRL write returned an error")
    await _harness_wait_state(dut, DOM_ON)
    status_up = await _harness_status(bfm)
    ack_at_on = int(dut.cpu_iso_ack_o.value)
    if not await bfm.write(STATUS_CLR_OFFSET, 1):
        raise RuntimeError("harness: the STATUS_CLR write returned an error")
    if (await _harness_status(bfm)) >> STATUS_TO_BIT & 1:
        raise RuntimeError("harness: STATUS_CLR did not clear STATUS[3]")
    if not await bfm.write(CTRL_OFFSET, MODE_CPU_OFF):
        raise RuntimeError("harness: the power-down CTRL write returned an error")
    tr = await _trace(dut, 40 + 2 * max(up_lat, P1_HEALTHY_LATENCY))
    states = [t[0] for t in tr]
    if DOM_PD_ISO not in states or DOM_OFF not in states:
        raise RuntimeError(f"harness: the power-down did not walk through PD_ISO: {_rle(states)}")
    i_pd = states.index(DOM_PD_ISO)
    i_off = states.index(DOM_OFF)
    window = tr[i_pd:i_off]
    await _harness_wait_state(dut, DOM_OFF)
    status_down = await _harness_status(bfm)
    return {
        "up_lat": up_lat,
        "status_up": status_up,
        "ack_at_on": ack_at_on,
        "pd_cycles": i_off - i_pd,
        "acks": [t[1] for t in window],
        "status_down": status_down,
    }


def _p1_verdict(row: dict) -> tuple:
    """(saw_fresh_ack, reported_fault) of one power-down.

    A fresh acknowledge is one that the PMU saw low after the isolation request began and high
    afterwards, so the isolation step cannot end on the acknowledge of an earlier request."""
    fresh = any(a == 0 for a in row["acks"])
    fault = bool((row["status_down"] >> STATUS_TO_BIT) & 1)
    return fresh, fault


@cocotb.test()
async def test_p1_power_down_after_timed_out_power_up_needs_fresh_ack(dut):
    """Asserts: a power-down that follows a power-up with a timed-out acknowledge wait does not end
    on the stale acknowledge. Stimulus: the power-up wait lasts ISO_ACK_TIMEOUT cycles while the
    acknowledge stays high, STATUS[3] is cleared, then CPU_OFF is written with no gap. The verdict
    is exact: the acknowledge is high on every cycle of DOM_PD_ISO (it was never seen low), the wait
    lasts the full ISO_ACK_TIMEOUT, and STATUS[3] is set by this wait. The flag was cleared before,
    so a flag left over from the power-up cannot satisfy the check."""
    row = await _p1_experiment(dut, P1_SLOW_RELEASE_LATENCY)
    fresh, fault = _p1_verdict(row)
    dut._log.info(
        f"P1 stale ack: STATUS after power-up {row['status_up']:#x}, ack at ON {row['ack_at_on']}, "
        f"DOM_PD_ISO lasted {row['pd_cycles']} cycle(s), ack per cycle {row['acks']}, "
        f"STATUS after power-down {row['status_down']:#x}"
    )
    assert not fresh, f"the stale case saw a low ack in DOM_PD_ISO: {row['acks']}"
    assert row["pd_cycles"] == ISO_ACK_TIMEOUT, (
        f"the power-down left DOM_PD_ISO after {row['pd_cycles']} cycle(s) on ack {row['acks']}: "
        f"it must burn the full ISO_ACK_TIMEOUT ({ISO_ACK_TIMEOUT}) when the ack was never seen low")
    assert fault, (
        f"STATUS after the power-down is {row['status_down']:#x} (bit {STATUS_TO_BIT} low): "
        "the timed-out handshake was not reported")


@cocotb.test()
async def test_p1_control_timed_out_power_up_leaves_ack_high(dut):
    """Proves the stimulus of the P1 test reaches the window. The power-up wait timed out, so
    STATUS[3] is set at ON, the acknowledge is still high at ON, and it is still high on entry to
    DOM_PD_ISO of the next power-down. This test asserts the precondition only, not the rule."""
    row = await _p1_experiment(dut, P1_SLOW_RELEASE_LATENCY)
    assert (row["status_up"] >> STATUS_TO_BIT) & 1, (
        f"the power-up wait did not time out: STATUS {row['status_up']:#x}")
    assert row["ack_at_on"] == 1, "the acknowledge was already low at ON: the case is not stale"
    assert row["acks"] and row["acks"][0] == 1, (
        f"the acknowledge was low on entry to DOM_PD_ISO: {row['acks']}")
    dut._log.info("P1 control: timed-out power-up leaves the acknowledge high at the next request")


@cocotb.test()
async def test_p1_control_normal_power_cycle_full_handshake(dut):
    """Proves the verdict of the P1 test can pass. After a normal power-up the power-down waits
    for ack_lat+1 cycles in DOM_PD_ISO, sees the acknowledge low and then high, and the flag
    stays low."""
    row = await _p1_experiment(dut, P1_HEALTHY_LATENCY)
    fresh, fault = _p1_verdict(row)
    assert row["pd_cycles"] == P1_HEALTHY_LATENCY + 1, (
        f"DOM_PD_ISO lasted {row['pd_cycles']} cycles, expected {P1_HEALTHY_LATENCY + 1}")
    assert row["acks"] == [0] * P1_HEALTHY_LATENCY + [1], f"ack per cycle {row['acks']}"
    assert fresh and not fault, f"fresh={fresh} fault={fault}"
    assert not (row["status_up"] >> STATUS_TO_BIT) & 1, "a healthy power-up must not flag"


async def _stale_low_power_up(dut, down_lat: int) -> dict:
    """Mirror of the P1 case for the power-up wait.

    The power-down times out with the ack frozen low, so the ack is still low when the domain
    reaches OFF. The power-up then starts with the ack released at latency down_lat. The wait
    must not end on the low level it found at its start."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    dut.ack_stuck_i.value = 1
    if not await bfm.write(CTRL_OFFSET, MODE_CPU_OFF):
        raise RuntimeError("harness: the power-down CTRL write returned an error")
    await _harness_wait_state(dut, DOM_OFF, limit=ISO_ACK_TIMEOUT + 30)
    if not (await _harness_status(bfm)) >> STATUS_TO_BIT & 1:
        raise RuntimeError("harness: the power-down did not time out")
    if not await bfm.write(STATUS_CLR_OFFSET, 1):
        raise RuntimeError("harness: the STATUS_CLR write returned an error")
    dut.ack_lat_i.value = down_lat
    if not await bfm.write(CTRL_OFFSET, MODE_NORMAL):
        raise RuntimeError("harness: the power-up CTRL write returned an error")
    tr = await _trace(dut, ISO_ACK_TIMEOUT + 30)
    states = [t[0] for t in tr]
    if DOM_PU_ISO not in states or DOM_PU_CLK not in states:
        raise RuntimeError(f"harness: the power-up did not walk through PU_ISO: {_rle(states)}")
    i_pu = states.index(DOM_PU_ISO)
    i_clk = states.index(DOM_PU_CLK)
    status = await _harness_status(bfm)
    return {"pu_cycles": i_clk - i_pu, "acks": [t[1] for t in tr[i_pu:i_clk]], "status": status}


@cocotb.test()
async def test_p1_power_up_does_not_end_on_stale_low_ack(dut):
    """The power-up wait accepts only an acknowledge it saw high. The ack is low when the wait
    begins (a timed-out power-down left it there) and the model never raises it, so the wait must
    last the full ISO_ACK_TIMEOUT and set STATUS[3]. The clock enable stays low throughout."""
    row = await _stale_low_power_up(dut, 0)
    assert row["acks"] == [0] * ISO_ACK_TIMEOUT, f"ack per cycle in DOM_PU_ISO {row['acks']}"
    assert row["pu_cycles"] == ISO_ACK_TIMEOUT, f"DOM_PU_ISO lasted {row['pu_cycles']} cycles"
    assert (row["status"] >> STATUS_TO_BIT) & 1, f"the timed-out power-up wait was not reported: {row['status']:#x}"


@cocotb.test()
async def test_p1_control_power_up_ends_on_fresh_release(dut):
    """Proves the mirror verdict can pass. After a healthy power-down the ack is high at the start of
    the power-up wait, falls, and ends the wait after ack_lat+1 cycles with the flag low."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _down(dut, bfm, 4)
    await _harness_wait_state(dut, DOM_OFF)
    if not await bfm.write(CTRL_OFFSET, MODE_NORMAL):
        raise RuntimeError("harness: the power-up CTRL write returned an error")
    tr = await _trace(dut, 30)
    states = [t[0] for t in tr]
    i_pu = states.index(DOM_PU_ISO)
    i_clk = states.index(DOM_PU_CLK)
    assert i_clk - i_pu == 5, f"DOM_PU_ISO lasted {i_clk - i_pu} cycles, expected 5"
    assert [t[1] for t in tr[i_pu:i_clk]] == [1, 1, 1, 1, 0]
    assert not (await _status(bfm)) >> STATUS_TO_BIT & 1


# --- STATUS_CLR (W1C, word 3) -------------------------------------------------------------------

async def _flag_set(dut, bfm) -> None:
    """Set STATUS[3] with one dead-ack power-down, then return the domain to ON with the ack released."""
    dut.ack_stuck_i.value = 1
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    await _harness_wait_state(dut, DOM_OFF, limit=ISO_ACK_TIMEOUT + 30)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "precondition: the timeout must set STATUS[3]"


async def _quiet_status_clr(bfm, data: int, strb: int = 0xF, addr: int = STATUS_CLR_OFFSET) -> None:
    assert await bfm.write(addr, data, strb=strb)


@cocotb.test()
async def test_status_clr_w1c_reads_zero_and_clears(dut):
    """A write of 1 to STATUS_CLR[0] clears STATUS[3]. STATUS_CLR reads 0 before and after, whatever
    was written. Only bit 0 acts: a write of 0xFFFF_FFFE leaves the flag set."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _flag_set(dut, bfm)
    assert (await bfm.read(STATUS_CLR_OFFSET))[0] == 0, "STATUS_CLR must read 0 while the flag is set"
    await _quiet_status_clr(bfm, 0xFFFF_FFFE)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "bits other than bit 0 must not clear the flag"
    await _quiet_status_clr(bfm, 0x1)
    assert not (await _status(bfm)) >> STATUS_TO_BIT & 1, "a write of 1 must clear the flag"
    assert (await bfm.read(STATUS_CLR_OFFSET))[0] == 0, "STATUS_CLR must read 0 after the clear"
    # Other STATUS bits are untouched: cpu off, gpu on, idle.
    assert (await _status(bfm)) == 0b0010


@cocotb.test()
async def test_status_clr_noop_when_flag_low(dut):
    """A write of 1 with the flag low changes nothing, and does not disturb the sequencer or the
    other registers."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    before = (await _status(bfm), (await bfm.read(DOMAIN_EN_OFFSET))[0], (await bfm.read(CTRL_OFFSET))[0])
    await _quiet_status_clr(bfm, 0x1)
    await _quiet_status_clr(bfm, 0x0)
    after = (await _status(bfm), (await bfm.read(DOMAIN_EN_OFFSET))[0], (await bfm.read(CTRL_OFFSET))[0])
    assert before == after, f"registers moved: {before} -> {after}"
    assert _sample_cpu(dut) == ON and _sample_gpu(dut) == ON


@cocotb.test()
async def test_status_clr_write_zero_keeps_flag(dut):
    """A write of 0 to STATUS_CLR does not clear the flag."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _flag_set(dut, bfm)
    await _quiet_status_clr(bfm, 0x0)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1


@cocotb.test()
async def test_status_clr_honours_pstrb(dut):
    """The clear needs pstrb[0]. A write of 1 with pstrb=0b1110 must not clear the flag, and one
    with pstrb=0b0001 must."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _flag_set(dut, bfm)
    await _quiet_status_clr(bfm, 0x1, strb=0b1110)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "a write without pstrb[0] must not clear"
    await _quiet_status_clr(bfm, 0x1, strb=0b0001)
    assert not (await _status(bfm)) >> STATUS_TO_BIT & 1, "a write with pstrb[0] must clear"


@cocotb.test()
async def test_status_clr_only_decodes_its_word(dut):
    """A write of 1 to the other three words never clears the flag. Writes to the RO words are
    dropped by their zero write masks. CTRL is not written here."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _flag_set(dut, bfm)
    await _quiet_status_clr(bfm, 0x1, addr=STAT_OFFSET)
    await _quiet_status_clr(bfm, 0x1, addr=DOMAIN_EN_OFFSET)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1


@cocotb.test()
async def test_status_clr_survives_power_down_start_and_reset_clears(dut):
    """The flag survives the start of a later power-down (no auto-clear) and only a reset or a
    STATUS_CLR write removes it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _flag_set(dut, bfm)
    dut.ack_stuck_i.value = 0
    dut.ack_lat_i.value = 2
    assert await bfm.write(CTRL_OFFSET, MODE_NORMAL)
    await _harness_wait_state(dut, DOM_ON, limit=ISO_ACK_TIMEOUT + 30)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "the power-up must not clear the flag"
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    await _wait_state(dut, DOM_PD_GATE)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "the start of a power-down must not clear the flag"
    await _harness_wait_state(dut, DOM_OFF)
    assert (await _status(bfm)) >> STATUS_TO_BIT & 1, "a healthy power-down must not clear the flag"
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    assert (await _status(bfm)) == 0x3, "a reset must clear the flag"


@cocotb.test()
async def test_status_clr_set_beats_clear(dut):
    """A timeout in the cycle of a STATUS_CLR write wins: the flag is set afterwards. The write
    access phase is swept across the cycles around the end of the wait. While the sequencer is
    still in DOM_PD_ISO at the access edge, the flag is low or sets at that very edge, so the flag
    must end set, and one offset of the sweep lands on the timeout edge. An access edge after the
    wait finds the flag set and clears it, which proves the write path."""
    before = after = 0
    for n_idle in range(ISO_ACK_TIMEOUT - 6, ISO_ACK_TIMEOUT + 3):
        _kill_active_tasks()
        await _start_clock_and_reset(dut)
        bfm = _make_apb_bfm(dut)
        dut.ack_stuck_i.value = 1
        assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
        await _harness_wait_state(dut, DOM_PD_ISO)
        for _ in range(n_idle):
            await RisingEdge(dut.clk)
        _raw_write_setup(dut, STATUS_CLR_OFFSET, 1)
        await RisingEdge(dut.clk)
        _raw_write_access(dut)
        await RisingEdge(dut.clk)
        # A read after an edge shows the state the sequencer held at that edge.
        in_wait = int(dut.u_dut.dom_state_q[0].value) == DOM_PD_ISO
        _raw_write_idle(dut)
        await _harness_wait_state(dut, DOM_OFF, limit=ISO_ACK_TIMEOUT + 30)
        await ClockCycles(dut.clk, 2)
        flag = (await _status(bfm)) >> STATUS_TO_BIT & 1
        if in_wait:
            assert flag, f"offset {n_idle}: a clear racing the timeout hid it"
            before += 1
        else:
            assert not flag, f"offset {n_idle}: a clear after the timeout did not clear the flag"
            after += 1
    assert before >= 3 and after >= 1, f"harness: sweep covered {before} in-wait and {after} after-wait offsets"


@cocotb.test()
async def test_status_clr_guard_ack_high_forced(dut):
    """Negative control for the flag source: with a healthy ack the flag never sets, so the tests
    above cannot pass on a flag stuck high."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    dut.ack_lat_i.value = 2
    assert await bfm.write(CTRL_OFFSET, MODE_CPU_OFF)
    await _harness_wait_state(dut, DOM_OFF)
    assert not (await _status(bfm)) >> STATUS_TO_BIT & 1


# --- P4 (unit). PMU reset from DOM_OFF ---------------------------------------------------------

def _release_events(cpu_tuples: list) -> dict:
    """Index of the first sample of each release, from samples that start in OFF."""
    if cpu_tuples[0] != OFF:
        raise RuntimeError(f"harness: the CPU outputs do not start in OFF: {cpu_tuples[0]}")
    ev: dict = {}
    for i, (clk_en, iso_en, rst_n, _save, _restore) in enumerate(cpu_tuples):
        if rst_n == 1:
            ev.setdefault("rst", i)
        if clk_en == 1:
            ev.setdefault("clk", i)
        if iso_en == 0:
            ev.setdefault("iso", i)
    if set(ev) != {"rst", "clk", "iso"}:
        raise RuntimeError(f"harness: not every release was seen: {ev}")
    return ev


async def _p4_unit_events(dut, how: str) -> dict:
    """Release events of the CPU outputs after a PMU reset in OFF, or after a normal power-up."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)
    await _down(dut, bfm, 0)
    await _harness_wait_state(dut, DOM_OFF)
    await ClockCycles(dut.clk, 3)
    if how == "reset":
        samples = [_sample_cpu(dut)]
        dut.rst_n.value = 0
        for _ in range(3):
            await RisingEdge(dut.clk)
            samples.append(_sample_cpu(dut))
        dut.rst_n.value = 1
        for _ in range(8):
            await RisingEdge(dut.clk)
            samples.append(_sample_cpu(dut))
    else:
        samples = [_sample_cpu(dut)]
        if not await bfm.write(CTRL_OFFSET, MODE_NORMAL):
            raise RuntimeError("harness: the power-up CTRL write returned an error")
        for _ in range(14):
            await RisingEdge(dut.clk)
            samples.append(_sample_cpu(dut))
    ev = _release_events(samples)
    dut._log.info(f"P4 unit ({how}): release sample index {ev}, outputs {samples[:8]}")
    return ev


@cocotb.test(expect_fail=True)
async def test_p4_unit_pmu_reset_from_off_releases_in_power_up_order(dut):
    """Asserts: after a PMU reset in DOM_OFF the domain reset is released before the clamp, and the
    clamp before the clock enable (DS-PMU-022: reset, restore, clamp release, clock).

    expect_fail: the reset branch loads clk_en, iso_en and rst_n together, so the three releases
    fall on one sample. The owner accepted this behaviour. If this test passes, the reading was
    wrong or the RTL changed."""
    ev = await _p4_unit_events(dut, "reset")
    assert ev["rst"] < ev["iso"] < ev["clk"], (
        f"release samples after the PMU reset: reset {ev['rst']}, clamp {ev['iso']}, "
        f"clock enable {ev['clk']}: not in the order reset, clamp, clock")


@cocotb.test()
async def test_p4_unit_control_sequenced_power_up_order(dut):
    """Proves the checker of the P4 unit test can pass. A normal sequenced power-up from OFF
    releases the reset, then the clamp, then the clock enable, one sample apart or more."""
    ev = await _p4_unit_events(dut, "sequenced")
    assert ev["rst"] < ev["iso"] < ev["clk"], f"sequenced power-up release samples: {ev}"
