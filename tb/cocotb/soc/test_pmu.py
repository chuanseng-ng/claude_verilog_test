"""
test_pmu.py — GH #101 cocotb verification for the behavioral PMU (rtl/soc/pmu.sv).

DUT: tb_pmu (standalone wrapper, directly instantiates pmu)

Register map (pmu.sv, ADDR_W=12 local byte offset):
  0x000  CTRL      [RW]  [1:0] pmu_mode_req (WMASK=0x3); reset 0x0 (NORMAL)
  0x004  STATUS    [RO]  [0] cpu_domain_on [1] gpu_domain_on [2] busy
  0x008  DOMAIN_EN [RO]  live per-signal bitmap (see pmu.sv header for bit map)

Mode encoding: 00 NORMAL, 01 CPU_OFF, 10 GPU_OFF, 11 IDLE.

Per-domain FSM (9-state linear chain, one action per clock):
  DOM_ON -> PD_SAVE -> PD_ISO -> PD_GATE -> DOM_OFF
         -> PU_RST -> PU_CLK -> PU_RESTORE -> PU_ISO -> DOM_ON

Timing contract exercised by every test below (empirically calibrated
against this RTL + the APB4Master BFM under Verilator; see the diagnostic
trace captured during development in test_pmu_mid_sequence_mode_change_no_reversal):
  Immediately after `await bfm.write(CTRL, ...)` returns, the domain
  sequencer is STILL showing its pre-write state, and it remains there for
  one further `RisingEdge` (i.e. two full cycles of no visible change)
  before the FSM's next-state logic reacts to the new target and begins
  walking the down/up sequence one state per cycle thereafter. Every
  ordering test below accounts for this two-cycle hold explicitly in its
  expected sample list (e.g. `[ON, ON, PD_SAVE, PD_ISO, PD_GATE, OFF, OFF]`)
  rather than assuming the FSM reacts on the very next edge.

Tests:
  test_pmu_reset_defaults
      CTRL=0, STATUS=0x3, GPU/CPU un-isolated/un-reset at reset.
  test_pmu_cpu_power_down_ordering / test_pmu_gpu_power_down_ordering
      Per-cycle ordering assertion (not end-state): ret_save -> iso_en ->
      clk-gate -> reset-assert, one action per cycle, no collapsing/reorder.
  test_pmu_cpu_power_up_ordering / test_pmu_gpu_power_up_ordering
      Per-cycle ordering assertion: reset-release -> clk-ungate ->
      ret_restore -> iso de-assert.
  test_pmu_idle_both_domains_ordering
      Both domains sequence down and back up in lockstep under IDLE.
  test_pmu_busy_semantics
      STATUS.busy tracks "either domain mid-sequence"; 0 once both settled.
  test_pmu_ctrl_wmask
      CTRL WMASK=0x3: writing 0xFFFF_FFFF leaves only bits[1:0].
  test_pmu_status_domain_en_readonly
      STATUS/DOMAIN_EN SW writes are no-ops (WMASK=0).
  test_pmu_mid_sequence_mode_change_no_reversal
      GH #101 documented intent: CTRL write mid-descent does not reverse
      the in-flight sequence; it completes to OFF, then powers back up.
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10  # 100 MHz — matches SoC reference clock

CTRL_OFFSET      = 0x000
STAT_OFFSET      = 0x004
DOMAIN_EN_OFFSET = 0x008

MODE_NORMAL  = 0x0
MODE_CPU_OFF = 0x1
MODE_GPU_OFF = 0x2
MODE_IDLE    = 0x3

CTRL_WMASK = 0x3

# Per-state output tuples: (clk_en, iso_en, rst_n, ret_save, ret_restore).
# Note some tuples coincide numerically across distinct FSM states (e.g.
# DOM_PU_ISO == DOM_ON, DOM_PD_ISO == DOM_PU_CLK, DOM_PD_GATE == DOM_PU_RST)
# — the tests below disambiguate by SEQUENCE POSITION, not tuple identity
# alone, which is why every ordering test asserts a full observed list
# against a full expected list rather than checking isolated samples.
ON         = (1, 0, 1, 0, 0)
PD_SAVE    = (1, 0, 1, 1, 0)
PD_ISO     = (1, 1, 1, 0, 0)
PD_GATE    = (0, 1, 1, 0, 0)
OFF        = (0, 1, 0, 0, 0)
PU_RST     = (0, 1, 1, 0, 0)
PU_CLK     = (1, 1, 1, 0, 0)
PU_RESTORE = (1, 1, 1, 0, 1)
PU_ISO     = (1, 0, 1, 0, 0)

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
    """Start 100 MHz clock and apply synchronous reset. Idle the APB4 bus."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

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
    EXACT sequence ON -> PD_SAVE -> PD_ISO -> PD_GATE -> OFF (steady), one
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
    expected = [ON, ON, PD_SAVE, PD_ISO, PD_GATE, OFF, OFF]
    assert observed == expected, f"CPU power-down ordering mismatch: {observed} != {expected}"
    dut._log.info("CPU power-down ordering: ON->PD_SAVE->PD_ISO->PD_GATE->OFF confirmed per-cycle")


@cocotb.test()
async def test_pmu_cpu_power_up_ordering(dut):
    """Drive CPU domain to settled OFF, then write CTRL=NORMAL and sample
    cpu_* every cycle. Assert the EXACT sequence OFF -> PU_RST -> PU_CLK ->
    PU_RESTORE -> PU_ISO -> ON: reset released -> clock ungated ->
    ret_restore -> iso de-asserted."""
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

    expected = [OFF, OFF, PU_RST, PU_CLK, PU_RESTORE, PU_ISO, ON]
    assert observed == expected, f"CPU power-up ordering mismatch: {observed} != {expected}"
    dut._log.info("CPU power-up ordering: OFF->PU_RST->PU_CLK->PU_RESTORE->PU_ISO->ON confirmed per-cycle")


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

    expected = [ON, ON, PD_SAVE, PD_ISO, PD_GATE, OFF, OFF]
    assert observed == expected, f"GPU power-down ordering mismatch: {observed} != {expected}"
    dut._log.info("GPU power-down ordering: ON->PD_SAVE->PD_ISO->PD_GATE->OFF confirmed per-cycle")


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

    expected = [OFF, OFF, PU_RST, PU_CLK, PU_RESTORE, PU_ISO, ON]
    assert observed == expected, f"GPU power-up ordering mismatch: {observed} != {expected}"
    dut._log.info("GPU power-up ordering: OFF->PU_RST->PU_CLK->PU_RESTORE->PU_ISO->ON confirmed per-cycle")


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

    expected_down = [ON, ON, PD_SAVE, PD_ISO, PD_GATE, OFF, OFF]
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

    expected_up = [OFF, OFF, PU_RST, PU_CLK, PU_RESTORE, PU_ISO, ON]
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

    # ON,ON -> PD_SAVE -> PD_ISO: definitely mid-sequence.
    await ClockCycles(dut.clk, 3)
    assert _sample_cpu(dut) == PD_ISO, "sanity: expected PD_ISO mid-descent"

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
    """GH #101 documented design intent: a domain's target is only
    re-sampled while settled at DOM_ON or DOM_OFF. Writing CTRL=NORMAL while
    the CPU domain is mid-descent (fired at PD_SAVE, the earliest possible
    point) must NOT reverse the in-flight power-down — it must complete
    PD_SAVE -> PD_ISO -> PD_GATE -> OFF exactly as if the write had never
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
    # UNREVERSED (ON,ON,PD_SAVE,PD_ISO,PD_GATE) despite the reversal write
    # landing mid-descent; OFF is visited for exactly one cycle; only then
    # does the ascent begin (PU_RST,PU_CLK,PU_RESTORE,PU_ISO/ON).
    expected = [
        ON, ON, PD_SAVE, PD_ISO, PD_GATE,   # full descent completes, no reversal
        OFF,                                 # settles OFF for exactly one cycle
        PU_RST, PU_CLK, PU_RESTORE, ON,     # then powers back up in order (PU_ISO==ON tuple)
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
