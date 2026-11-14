"""
test_soc_pmu_iso_ack.py -- PMU / soc_top isolation-before-reset ordering. DUT: tb_soc_top
(as soc_pmu_multiclock).
THE PROPERTY (UPF order, pmu.sv header): on a CPU power-down the isolation clamp must be ACTIVE IN
THE CPU DOMAIN before that domain's reset asserts and before its clock gate closes. This held only
by accident of ratio: pmu_cpu_iso_en reaches the clamp through a 2-flop cdc_sync on cpu_core_clk,
while pmu_cpu_rst_n reaches u_cpu_pmu_rst_sync's ASYNC clear directly. The PMU spaces the two by 2
core_clk cycles, so with the CPU clock slower than the fabric clock the reset beat the clamp. The
fix is an iso-ack handshake: the CPU-domain clamp (pmu_cpu_iso_en_sync) is synchronised back to
core_clk (u_cpu_iso_ack_sync -> pmu_cpu_iso_ack). The PMU sequencer waits in DOM_PD_ISO for it
before it gates the clock or asserts reset, and waits in DOM_PU_ISO for it to drop (the 4-phase
return-to-zero half) before a new power-down may start.
Tests drive the power cycle by a backdoor deposit into the PMU CTRL cell (as
  test_soc_pmu_multiclock's power-up leg).
  test_iso_before_reset_{cpu_3x_slower,cpu_8x_slower,ratio_1_1,cpu_faster}: the invariant monitor
      runs through a full CPU off->on cycle at that ratio. The two slow-CPU ratios fail without the
      ack handshake.
  test_back_to_back_power_cycle_no_stale_ack: off, on, off with no idle gap; the 2nd power-down must
      not use the old ack.
  test_dead_cpu_clock_does_not_hang_pmu: cpu_rst_n_i held low, so the ack never arrives; the PMU
      proceeds after ISO_ACK_TIMEOUT cycles, sets STATUS[3], and the GPU domain is unaffected.
  test_gpu_isolation_clamps_follow_pmu_iso_en: every ISO_GPU clamp in soc_top equals `raw &
      ~pmu_gpu_iso_en` on every cycle of a GPU power cycle. The GPU needs no ack (same
      clock domain).
INVARIANT MONITOR (after every clk_i and cpu_clk_i rising edge, ReadOnly; armed once the
synchroniser chains fill): INV1 pmu_cpu_rst_n_cpu_sync == 0 -> pmu_cpu_iso_en_sync == 1. INV2
cpu_gated_clk_en == 0 -> pmu_cpu_iso_en_sync == 1. INV3 pmu_cpu_iso_en_sync == 0 ->
pmu_cpu_rst_n_cpu_sync == 1 (power-UP; NOMINAL-ONLY, silicon can swap the order by one edge, benign
by structure, see pmu.sv). INV4 pmu_cpu_iso_ack changes only on clk_i edges.
Run: make -C tb/cocotb/soc soc_pmu_iso_ack
Doc: tm:suite:soc-test-soc-pmu-iso-ack
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, with_timeout
from cocotb.utils import get_sim_time

from soc_clocks import start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# pmu_dom_state_e encoding (pmu.sv `typedef enum`).
DOM_ON, DOM_PD_SAVE, DOM_PD_ISO, DOM_PD_GATE, DOM_OFF = 0, 1, 2, 3, 4
DOM_PU_RST, DOM_PU_CLK, DOM_PU_RESTORE, DOM_PU_ISO = 5, 6, 7, 8
DOM_CPU, DOM_GPU = 0, 1

MODE_NORMAL, MODE_CPU_OFF, MODE_GPU_OFF, MODE_IDLE = 0x0, 0x1, 0x2, 0x3

ISO_ACK_TIMEOUT = 255  # pmu.sv default (soc_top does not override it)
STATUS_ISO_ACK_TIMEOUT_BIT = 3  # PMU STATUS[3], sticky

FABRIC_NS = 7

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------------------------
async def _setup(dut, cpu_ns: int, *, hold_cpu_reset: bool = False) -> None:
    """Clocks at FABRIC_NS / cpu_ns, idle inputs, reset (held long enough for the SLOWER clock).

    hold_cpu_reset leaves cpu_rst_n_i low (the CPU PLL domain stays dead) after the fabric is
    released.  The boot ROM is left all-zero: the CPU traps and re-fetches forever, which keeps its
    AXI request lines active without any firmware dependency.
    """
    _kill_active_tasks()
    clk_task, cpu_clk_task = start_soc_clocks(dut, FABRIC_NS, cpu_period_ns=cpu_ns)
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

    await ClockCycles(dut.clk_i, 6)
    await ClockCycles(dut.cpu_clk_i, 6)
    dut.rst_n_i.value = 1
    if not hold_cpu_reset:
        dut.cpu_rst_n_i.value = 1
    # PLL-stub lock (16 ref cycles) + synchroniser fill on both sides, in the slower domain's time.
    await ClockCycles(dut.clk_i, 60)
    await ClockCycles(dut.cpu_clk_i, 60)


def _soc(dut):
    return dut.u_soc


def _dom_state(dut, dom: int = DOM_CPU) -> int:
    return int(_soc(dut).u_pmu.dom_state_q[dom].value)


def _has_ack(dut) -> bool:
    try:
        _ = _soc(dut).pmu_cpu_iso_ack
        return True
    except AttributeError:
        return False


async def _set_mode(dut, mode: int) -> None:
    """Backdoor write of PMU CTRL (the storage cell a real APB write to 0x2000_8000 hits)."""
    await RisingEdge(dut.clk_i)
    _soc(dut).u_pmu.u_regbank.regs[0].value = mode
    await ReadOnly()


class IsoMonitor:
    """Samples the invariants on every clk_i and cpu_clk_i edge and logs PMU state dwell times."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.violations: list = []
        self.samples = 0
        self.has_ack = _has_ack(dut)
        # (sim_time_ns, dom_state_q[CPU]) on each change, sampled on clk_i.
        self.transitions: list = []
        # sim time of the first high sample of each observed net after it last went low
        self.iso_sync_rise_ns: list = []
        self.ack_rise_ns: list = []
        self.rst_sync_fall_ns: list = []
        self._prev = {"iso_s": None, "ack": None, "rst_s": None, "state": None}
        self.core_phase = None  # sim time (ns) modulo FABRIC_NS of a clk_i rising edge
        self._tasks: list = []

    def start(self) -> None:
        self._tasks = [
            cocotb.start_soon(self._run(self.dut.clk_i, True)),
            cocotb.start_soon(self._run(self.dut.cpu_clk_i, False)),
        ]
        _active_tasks.extend(self._tasks)

    def stop(self) -> None:
        for t in self._tasks:
            t.kill()

    async def _run(self, clk, is_core: bool) -> None:
        soc = _soc(self.dut)
        while True:
            await RisingEdge(clk)
            await ReadOnly()
            self.samples += 1
            now = get_sim_time("ns")
            rst_s = int(soc.pmu_cpu_rst_n_cpu_sync.value)
            iso_s = int(soc.pmu_cpu_iso_en_sync.value)
            gate_en = int(soc.cpu_gated_clk_en.value)
            if rst_s == 0 and iso_s == 0:
                self.violations.append(
                    (now, "INV1", "PMU reset observed asserted in the CPU domain while the "
                                  "isolation clamp is NOT yet active there"))
            if gate_en == 0 and iso_s == 0:
                self.violations.append(
                    (now, "INV2", "CPU clock gate closed while the isolation clamp is NOT yet "
                                  "active in the CPU domain"))
            ack = int(soc.pmu_cpu_iso_ack.value) if self.has_ack else None
            state = _dom_state(self.dut) if is_core else self._prev["state"]
            p = self._prev
            if p["iso_s"] is not None:
                if iso_s == 1 and p["iso_s"] == 0:
                    self.iso_sync_rise_ns.append(now)
                if rst_s == 0 and p["rst_s"] == 1:
                    self.rst_sync_fall_ns.append(now)
                # INV3 (power-up, nominal order): the clamp releases only once the PMU reset has
                # been observed released.
                if iso_s == 0 and p["iso_s"] == 1 and rst_s == 0:
                    self.violations.append(
                        (now, "INV3", "isolation clamp released in the CPU domain while the PMU "
                                      "reset is still observed asserted (nominal order)"))
            if is_core and self.core_phase is None:
                self.core_phase = now % FABRIC_NS
            if ack is not None and p["ack"] is not None and ack != p["ack"]:
                if ack == 1:
                    self.ack_rise_ns.append(now)
                # INV4: the ack is the output of a synchroniser INTO core_clk, so it may only
                # change on a clk_i edge.  A change first seen on a cpu_clk_i edge that is not
                # also a clk_i edge means the return crossing is clocked by the wrong clock (or
                # is a bare wire): the PMU would be sampling an unsynchronised cpu_clk signal.
                if self.core_phase is not None and (now - self.core_phase) % FABRIC_NS != 0:
                    self.violations.append(
                        (now, "INV4", "cpu_iso_ack changed off a core_clk edge: the return "
                                      "crossing is not synchronised into core_clk"))
            if is_core and state != p["state"]:
                self.transitions.append((now, state))
            p["iso_s"], p["rst_s"], p["ack"] = iso_s, rst_s, ack
            if is_core:
                p["state"] = state

    def sequence(self) -> list:
        return [s for _, s in self.transitions]


async def _wait_state(dut, targets: set, timeout_cycles: int, label: str) -> None:
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if _dom_state(dut) in targets:
            return
    raise TimeoutError(f"{label}: dom_state_q[CPU] never reached {targets}; stuck at "
                       f"{_dom_state(dut)}")


def _dwell_cycles(mon: IsoMonitor, state: int, occurrence: int = 0) -> int:
    """Core-clock cycles dom_state_q[CPU] stayed in `state` (the occurrence-th visit)."""
    seen = -1
    for i, (t, s) in enumerate(mon.transitions):
        if s != state:
            continue
        seen += 1
        if seen == occurrence:
            t_next = mon.transitions[i + 1][0] if i + 1 < len(mon.transitions) else None
            assert t_next is not None, f"state {state} visit {occurrence} never ended"
            return round((t_next - t) / FABRIC_NS)
    raise AssertionError(f"state {state} visit {occurrence} not observed: {mon.sequence()}")


# ---------------------------------------------------------------------------------------------
# Part 1: iso-before-reset, across clock ratios
# ---------------------------------------------------------------------------------------------
async def _cpu_off_on_cycle(dut, cpu_ns: int) -> IsoMonitor:
    await _setup(dut, cpu_ns)
    assert _dom_state(dut) == DOM_ON, "CPU PMU domain did not start at DOM_ON"
    mon = IsoMonitor(dut)
    mon.start()

    await _set_mode(dut, MODE_CPU_OFF)
    await _wait_state(dut, {DOM_OFF}, 4000, "power-down")
    # Let the CPU-domain synchronisers settle on the OFF state, then power back up.
    await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    await _set_mode(dut, MODE_NORMAL)
    await _wait_state(dut, {DOM_ON}, 4000, "power-up")
    await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    mon.stop()
    return mon


def _check_cycle(dut, mon: IsoMonitor, label: str) -> None:
    assert mon.samples > 100, f"{label}: monitor barely ran ({mon.samples} samples)"
    seq = [s for s in mon.sequence() if s in (
        DOM_PD_SAVE, DOM_PD_ISO, DOM_PD_GATE, DOM_OFF, DOM_PU_RST, DOM_PU_CLK, DOM_PU_RESTORE,
        DOM_PU_ISO, DOM_ON)]
    expected = [DOM_ON, DOM_PD_SAVE, DOM_PD_ISO, DOM_PD_GATE, DOM_OFF, DOM_PU_RST, DOM_PU_CLK,
                DOM_PU_RESTORE, DOM_PU_ISO, DOM_ON]
    # The first ON is the initial value (the monitor records it as the first "change").
    assert seq == expected, f"{label}: UPF-order walk deviated: {seq} != {expected}"
    assert mon.rst_sync_fall_ns, f"{label}: the PMU reset never asserted in the CPU domain"
    assert not mon.violations, (
        f"{label}: isolation ordering violated {len(mon.violations)}x: "
        + "; ".join(f"[{n}] t={t:.0f}ns {m}" for t, n, m in mon.violations[:4]))
    if mon.has_ack:
        # The handshake itself: the ack must rise strictly before the gate/reset steps.
        t_gate = next(t for t, s in mon.transitions if s == DOM_PD_GATE)
        assert mon.ack_rise_ns and mon.ack_rise_ns[0] < t_gate, (
            f"{label}: PD_GATE entered at {t_gate}ns without a prior ack rise "
            f"({mon.ack_rise_ns})")
        dut._log.info(
            f"{label}: PD_ISO dwell {_dwell_cycles(mon, DOM_PD_ISO)} core cycles, "
            f"PU_ISO dwell {_dwell_cycles(mon, DOM_PU_ISO)} core cycles")


@cocotb.test()
async def test_iso_before_reset_cpu_3x_slower(dut):
    """CPU clock 3x SLOWER than the fabric: fails on origin/main (reset beats the clamp)."""
    mon = await with_timeout(_cpu_off_on_cycle(dut, 3 * FABRIC_NS), 800, "us")
    _check_cycle(dut, mon, "cpu 3x slower")


@cocotb.test()
async def test_iso_before_reset_cpu_8x_slower(dut):
    """CPU clock 8x slower: the same property at a far larger ratio."""
    mon = await with_timeout(_cpu_off_on_cycle(dut, 8 * FABRIC_NS), 1500, "us")
    _check_cycle(dut, mon, "cpu 8x slower")


@cocotb.test()
async def test_iso_before_reset_ratio_1_1(dut):
    """1:1, identical phase: the ordering the single-clock regressions have always run at."""
    mon = await with_timeout(_cpu_off_on_cycle(dut, FABRIC_NS), 400, "us")
    _check_cycle(dut, mon, "1:1")


@cocotb.test()
async def test_iso_before_reset_cpu_faster(dut):
    """CPU 7:3 faster (the coprime pair test_soc_pmu_multiclock uses): must not regress."""
    mon = await with_timeout(_cpu_off_on_cycle(dut, 3), 400, "us")
    _check_cycle(dut, mon, "cpu 7:3 faster")


# ---------------------------------------------------------------------------------------------
# Stale-ack guard: back-to-back power cycles
# ---------------------------------------------------------------------------------------------
@cocotb.test()
async def test_back_to_back_power_cycle_no_stale_ack(dut):
    """off -> on -> off with no idle gap at the 3x-slower ratio.

    After the first cycle the CPU-domain clamp has just released, but its release is still
    travelling through two synchronisers (cpu_core_clk then core_clk), so the PMU's ack input is
    STALE-HIGH for several core cycles.  The second power-down must not take that as its ack: the
    PU_ISO wait-for-ack-low (4-phase RZ) is what prevents it.
    """

    async def body():
        await _setup(dut, 3 * FABRIC_NS)
        mon = IsoMonitor(dut)
        mon.start()
        stale_at_iso_entry = []
        for cycle in range(3):
            await _set_mode(dut, MODE_CPU_OFF)
            # Catch the first cycle of DOM_PD_ISO of THIS power-down and record the ack there.
            for _ in range(4000):
                await RisingEdge(dut.clk_i)
                await ReadOnly()
                if _dom_state(dut) == DOM_PD_ISO:
                    if mon.has_ack:
                        stale_at_iso_entry.append(int(_soc(dut).pmu_cpu_iso_ack.value))
                    break
            else:
                raise TimeoutError("never reached DOM_PD_ISO")
            await _wait_state(dut, {DOM_OFF}, 4000, f"power-down {cycle}")
            await _set_mode(dut, MODE_NORMAL)
            await _wait_state(dut, {DOM_ON}, 4000, f"power-up {cycle}")
            # No idle gap: the next iteration writes CPU_OFF on the very next clk_i edge.
        mon.stop()
        return mon, stale_at_iso_entry

    mon, stale = await with_timeout(body(), 1500, "us")
    assert not mon.violations, "ordering violated: " + "; ".join(
        f"[{n}] t={t:.0f}ns {m}" for t, n, m in mon.violations[:4])
    if mon.has_ack:
        assert stale == [0, 0, 0], (
            f"the ack was already high when a new power-down entered DOM_PD_ISO ({stale}): a "
            "stale ack from the previous cycle can satisfy the wait before the new clamp exists")
    assert len(mon.rst_sync_fall_ns) == 3, mon.rst_sync_fall_ns


# ---------------------------------------------------------------------------------------------
# Dead CPU clock: the handshake must not hang the always-on PMU
# ---------------------------------------------------------------------------------------------
@cocotb.test()
async def test_dead_cpu_clock_does_not_hang_pmu(dut):
    """cpu_rst_n_i held low: u_cpu_iso_en_sync is held at 0 and no ack can ever come back."""

    async def body():
        await _setup(dut, 3 * FABRIC_NS, hold_cpu_reset=True)
        assert int(_soc(dut).cpu_core_rst_n.value) == 0, "precondition: CPU PLL domain not dead"
        soc = _soc(dut)

        # IDLE: both domains down at once, so the GPU's independence is observed on the same run.
        await _set_mode(dut, MODE_IDLE)
        gpu_seq, cpu_seq = [DOM_ON], [DOM_ON]
        gpu_off_cycle = cpu_off_cycle = None
        for cyc in range(2000):
            await RisingEdge(dut.clk_i)
            await ReadOnly()
            g, c = _dom_state(dut, DOM_GPU), _dom_state(dut, DOM_CPU)
            if not gpu_seq or gpu_seq[-1] != g:
                gpu_seq.append(g)
            if not cpu_seq or cpu_seq[-1] != c:
                cpu_seq.append(c)
            if g == DOM_OFF and gpu_off_cycle is None:
                gpu_off_cycle = cyc
            if c == DOM_OFF and cpu_off_cycle is None:
                cpu_off_cycle = cyc
                break
        assert cpu_off_cycle is not None, f"CPU PMU domain hung in the iso wait: {cpu_seq}"
        assert gpu_off_cycle is not None and gpu_off_cycle < 20, (
            f"GPU domain was slowed by the CPU handshake (reached OFF at cycle {gpu_off_cycle})")
        assert cpu_seq == [DOM_ON, DOM_PD_SAVE, DOM_PD_ISO, DOM_PD_GATE, DOM_OFF], cpu_seq
        # The wait lasted the whole timeout, the flag is set, and is visible in STATUS[3].
        assert cpu_off_cycle - gpu_off_cycle >= ISO_ACK_TIMEOUT - 2, (
            f"CPU gated/reset after only {cpu_off_cycle - gpu_off_cycle} cycles without an ack")
        status = int(soc.u_pmu.u_regbank.regs[1].value)
        assert (status >> STATUS_ISO_ACK_TIMEOUT_BIT) & 1, f"STATUS[3] not set: 0x{status:x}"

        # Power back up: the dead domain's ack is (correctly) low, so the PU_ISO wait is trivial.
        await _set_mode(dut, MODE_NORMAL)
        await _wait_state(dut, {DOM_ON}, 2000, "power-up with a dead CPU domain")
        await ClockCycles(dut.clk_i, 4)

        # Revive the CPU PLL domain and power-cycle again: the flag clears, the ack is real.
        dut.cpu_rst_n_i.value = 1
        await ClockCycles(dut.cpu_clk_i, 60)
        await ClockCycles(dut.clk_i, 60)
        mon = IsoMonitor(dut)
        mon.start()
        await _set_mode(dut, MODE_CPU_OFF)
        await _wait_state(dut, {DOM_OFF}, 4000, "power-down after revival")
        status = int(soc.u_pmu.u_regbank.regs[1].value)
        assert not (status >> STATUS_ISO_ACK_TIMEOUT_BIT) & 1, (
            f"STATUS[3] not cleared by the next power-down: 0x{status:x}")
        await ClockCycles(dut.clk_i, 40)
        await _set_mode(dut, MODE_NORMAL)
        await _wait_state(dut, {DOM_ON}, 4000, "power-up after revival")
        mon.stop()
        assert not mon.violations, "ordering violated after revival: " + "; ".join(
            f"[{n}] t={t:.0f}ns {m}" for t, n, m in mon.violations[:4])

    await with_timeout(body(), 1500, "us")


# ---------------------------------------------------------------------------------------------
# Part 2: ISO_GPU clamps, including m_axil_if_rready
# ---------------------------------------------------------------------------------------------
GPU_CLAMPS = (
    # (clamped net in soc_top, raw net, human name)
    ("xbar_m_awvalid", "gpu_axi_awvalid_raw", 2),
    ("xbar_m_wvalid", "gpu_axi_wvalid_raw", 2),
    ("xbar_m_arvalid", "gpu_axi_arvalid_raw", 2),
    ("xbar_m_bready", "gpu_axi_bready_raw", 2),
    ("xbar_m_rready", "gpu_axi_rready_raw", 2),
    ("gif_axil_arvalid", "gpu_gif_arvalid_raw", None),
    ("gif_axil_rready", "gpu_gif_rready_raw", None),
)


@cocotb.test()
async def test_gpu_isolation_clamps_follow_pmu_iso_en(dut):
    """Every ISO_GPU clamp is `raw & ~pmu_gpu_iso_en` on EVERY cycle of a GPU power cycle.

    m_axil_if_rready (gif_axil_rready) is the newest clamp: the GPU ifetch R-channel accept
    is a constant 1 in gpu_compute_unit, so it is the one handshake output that is HIGH while the
    GPU is idle -- the only clamp whose action (raw=1, out=0) is visible with no GPU traffic.  The
    other six are checked against the same equation on every cycle (they read 0 when idle).  The
    GPU's reset must assert only with the clamp already active, and release only after reset is
    back (same clock domain: both are PMU flops on core_clk, so no ack is needed).
    """

    async def body():
        await _setup(dut, FABRIC_NS)
        soc = _soc(dut)
        # Only the ifetch R-channel accept (gpu_compute_unit: `if_rready_o = 1'b1`) is HIGH while the
        # GPU is idle; the other handshake outputs are 0 with no GPU traffic, so for them the
        # equation check below is all an idle GPU can show.
        acted = {"gif_axil_rready": 0}
        released_high = {"gif_axil_rready": 0}
        iso_cycles = rst_low_cycles = 0
        violations = []

        async def run_cycle(mode: int, until_state: int):
            nonlocal iso_cycles, rst_low_cycles
            await _set_mode(dut, mode)
            for _ in range(400):
                await RisingEdge(dut.clk_i)
                await ReadOnly()
                iso = int(soc.pmu_gpu_iso_en.value)
                rst_n = int(soc.pmu_gpu_rst_n.value)
                iso_cycles += iso
                rst_low_cycles += 1 - rst_n
                if rst_n == 0 and iso == 0:
                    violations.append("GPU reset asserted with the GPU clamp inactive")
                for out_name, raw_name, idx in GPU_CLAMPS:
                    out_h = getattr(soc, out_name)
                    out = (int(out_h.value) >> idx) & 1 if idx is not None else int(out_h.value)
                    raw = int(getattr(soc, raw_name).value)
                    if out != (raw & (1 - iso)):
                        violations.append(f"{out_name}={out} raw={raw} iso={iso}")
                    if out_name in acted:
                        if iso and raw and not out:
                            acted[out_name] += 1
                        if not iso and raw and out:
                            released_high[out_name] += 1
                if _dom_state(dut, DOM_GPU) == until_state:
                    return
            raise TimeoutError(f"GPU domain never reached {until_state}")

        await run_cycle(MODE_GPU_OFF, DOM_OFF)
        await ClockCycles(dut.clk_i, 6)
        await run_cycle(MODE_NORMAL, DOM_ON)
        return acted, released_high, iso_cycles, rst_low_cycles, violations

    acted, released_high, iso_cycles, rst_low_cycles, violations = await with_timeout(
        body(), 400, "us")
    assert not violations, "clamp mismatch: " + "; ".join(violations[:5])
    assert iso_cycles >= 4 and rst_low_cycles >= 1, (iso_cycles, rst_low_cycles)
    assert acted["gif_axil_rready"] >= 1, (
        "m_axil_if_rready was never seen clamped (raw=1, out=0, iso=1): the clamp never acted")
    assert released_high["gif_axil_rready"] > 0, (
        "the clamp never released again (out stayed 0 with iso=0)")


# =============================================================================
# Directed confirmation of one reviewed behaviour (P4, SoC level).
# Doc: ds:mod:pmu
#
# A review read from the RTL that a PMU reset while the CPU domain is in DOM_OFF sets the clock
# enable, the clamp and the reset of the domain to their DOM_ON values at one edge. The three
# controls then cross synchronisers of the same depth into the CPU domain and are released at the
# same edge of cpu_clk_i, so the power-up order of DS-PMU-022 does not apply there. No simulation
# had shown this. The RTL is not changed. The test that asserts the specified order (the clamp is
# released after the domain reset and after the clock enable, DS-PMU-100) is marked expect_fail: it
# must fail while the behaviour exists. If it passes, the review was wrong or the RTL changed. Then
# replace it by a normal test that proves the rule. A harness fault raises RuntimeError, not
# AssertionError, so expect_fail cannot hide it. A normal test runs the same monitor over a
# power-up that the PMU sequences. The order is only asserted strictly at 1:1 and with the CPU
# faster, where each release falls on its own edge by the spacing of the PMU outputs. At slower CPU
# clocks the spacing is below one CPU clock, so two releases can share an edge by design. There the
# order is logged and only the weaker rule (no earlier clamp release) is asserted.
# =============================================================================

P4_RATIOS = (FABRIC_NS, 3, 3 * FABRIC_NS, 8 * FABRIC_NS)
P4_STRICT_RATIOS = (FABRIC_NS, 3)
_P4_CACHE: dict = {}


class _ReleaseMonitor:
    """Passive monitor of the three releases in the CPU domain. It never drives a signal.

    It samples after every rising edge of cpu_clk_i, the clock of the three synchronisers, and
    numbers the edges. Once armed it records the number of the first edge at which each release is
    seen: the clamp control falls (iso), the PMU reset rises (rst), the clock gate enable rises (en)
    and cpu_gated_clk pulses (clk). For the first gated edge it keeps the clamp and reset values
    from before the edge.
    """

    def __init__(self, dut) -> None:
        self.dut = dut
        self.n = 0
        self.armed = False
        self.ev: dict = {}
        self.before: tuple = ()
        self._prev = None
        self._task = None

    def start(self) -> None:
        self._task = cocotb.start_soon(self._run())
        _active_tasks.append(self._task)

    def stop(self) -> None:
        if self._task is not None:
            self._task.kill()
            self._task = None

    async def _run(self) -> None:
        soc = _soc(self.dut)
        while True:
            await RisingEdge(self.dut.cpu_clk_i)
            await ReadOnly()
            self.n += 1
            cur = (int(soc.pmu_cpu_iso_en_sync.value), int(soc.pmu_cpu_rst_n_cpu_sync.value),
                   int(soc.cpu_gated_clk_en.value))
            prev = self._prev
            if self.armed and prev is not None:
                if prev[0] == 1 and cur[0] == 0:
                    self.ev.setdefault("iso", self.n)
                if prev[1] == 0 and cur[1] == 1:
                    self.ev.setdefault("rst", self.n)
                if prev[2] == 0 and cur[2] == 1:
                    self.ev.setdefault("en", self.n)
                if int(soc.cpu_gated_clk.value) and "clk" not in self.ev:
                    self.ev["clk"] = self.n
                    self.before = prev
            self._prev = cur


def _p4_strict(ev: dict) -> bool:
    return ev["rst"] < ev["iso"] and ev["en"] < ev["iso"]


async def _p4_experiment(dut, cpu_ns: int, how: str) -> dict:
    """CPU domain to OFF, then a PMU-sequenced power-up (how = "sequenced") or a reset of rst_n_i
    alone (how = "reset"). Returns the release events of _ReleaseMonitor."""
    await _setup(dut, cpu_ns)
    soc = _soc(dut)
    if _dom_state(dut) != DOM_ON:
        raise RuntimeError("harness: the CPU PMU domain did not start at DOM_ON")
    await _set_mode(dut, MODE_CPU_OFF)
    await _wait_state(dut, {DOM_OFF}, 4000, "power-down")
    await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    settled = (int(soc.pmu_cpu_iso_en_sync.value), int(soc.pmu_cpu_rst_n_cpu_sync.value),
               int(soc.cpu_gated_clk_en.value))
    if settled != (1, 0, 0):
        raise RuntimeError(
            f"harness: the CPU domain is not settled in OFF (iso, rst, en): {settled}")
    mon = _ReleaseMonitor(dut)
    mon.start()
    await ClockCycles(dut.cpu_clk_i, 3)
    mon.armed = True
    if how == "reset":
        await RisingEdge(dut.clk_i)
        dut.rst_n_i.value = 0
        await ClockCycles(dut.clk_i, 6)
        dut.rst_n_i.value = 1
        await ClockCycles(dut.clk_i, 60)
    else:
        await _set_mode(dut, MODE_NORMAL)
        await _wait_state(dut, {DOM_ON}, 4000, "power-up")
        await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    mon.stop()
    missing = {"iso", "rst", "en", "clk"} - set(mon.ev)
    if missing:
        raise RuntimeError(f"harness: {how} cpu={cpu_ns}ns: release(s) not seen: {sorted(missing)}")
    return {**mon.ev, "before_iso": mon.before[0], "before_rst": mon.before[1]}


def _fmt_p4(cpu_ns: int, how: str, ev: dict) -> str:
    return (
        f"cpu={cpu_ns}ns {how}: edge of the clamp release {ev['iso']}, reset release {ev['rst']}, "
        f"clock enable {ev['en']}, first gated edge {ev['clk']} "
        f"(clamp before it {ev['before_iso']}, reset before it {ev['before_rst']}); "
        f"strict order {_p4_strict(ev)}")


async def _p4_sweep(dut) -> dict:
    """Both power-ups at every ratio. Cached for the whole file."""
    if "rows" not in _P4_CACHE:
        rows = {}
        for cpu_ns in P4_RATIOS:
            for how in ("sequenced", "reset"):
                rows[(cpu_ns, how)] = await _p4_experiment(dut, cpu_ns, how)
                dut._log.info("P4 " + _fmt_p4(cpu_ns, how, rows[(cpu_ns, how)]))
        _P4_CACHE["rows"] = rows
    return _P4_CACHE["rows"]


@cocotb.test(expect_fail=True)
async def test_p4_pmu_reset_from_off_releases_cpu_clamp_last(dut):
    """Asserts: after a PMU reset while the CPU domain is in OFF, the clamp control in the CPU
    domain is released after the domain reset and after the clock gate enable (DS-PMU-022,
    DS-PMU-100). Checked at 1:1 and with the CPU clock faster. The order at the other ratios is in
    the log.

    expect_fail: the review reads that the reset branch of the PMU loads the three controls
    together and that their synchronisers have the same depth, so the three releases fall on one
    edge. If this test passes, the reading was wrong or the RTL changed."""
    rows = await with_timeout(_p4_sweep(dut), 3000, "us")
    bad = [_fmt_p4(c, "reset", rows[(c, "reset")]) for c in P4_STRICT_RATIOS
           if not _p4_strict(rows[(c, "reset")])]
    assert not bad, "the clamp was not released last: " + "; ".join(bad)


@cocotb.test()
async def test_p4_control_sequenced_power_up_releases_cpu_clamp_last(dut):
    """Proves the monitor and the check of the P4 test can pass. After a PMU-sequenced power-up
    from OFF the clamp is released after the domain reset and after the clock enable at 1:1 and with
    the CPU faster. At every ratio the clamp is not released before either of them."""
    rows = await with_timeout(_p4_sweep(dut), 3000, "us")
    for cpu_ns in P4_RATIOS:
        ev = rows[(cpu_ns, "sequenced")]
        tag = _fmt_p4(cpu_ns, "sequenced", ev)
        assert ev["iso"] >= ev["rst"] and ev["iso"] >= ev["en"], f"clamp released early: {tag}"
        if cpu_ns in P4_STRICT_RATIOS:
            assert _p4_strict(ev), f"sequenced power-up did not release the clamp last: {tag}"


# =============================================================================
# The reset term of the CPU clock gate enable.
# Doc: ds:mod:pmu
#
# cpu_gated_clk_en is ~pmu_cpu_clk_dis_sync & pmu_cpu_rst_n_cpu_sync. The two terms reach the CPU
# domain by different paths. The clock disable passes SYNC_STAGES_TO_CPU flops. The PMU reset
# asserts at the reset synchroniser without a clock edge. At 1:1 the PMU asserts the reset one
# core_clk edge after it disables the clock. The reset has then already reached the CPU domain,
# but the clock disable is one edge away. Without the reset term u_cpu_cg passes that edge, and
# cpu_gated_clk pulses while the domain is in reset. The rule below is the one the comment of
# cpu_gated_clk_en states: cpu_gated_clk does not tick while the PMU reset is asserted in
# cpu_core_clk. No other test sees the term, because INV2 of the invariant monitor only needs the
# clamp, which is active at that time.
# =============================================================================

GATE_RATIOS = (FABRIC_NS, 3 * FABRIC_NS, 8 * FABRIC_NS, 3)
_GATE_CACHE: dict = {}


class _GateTickMonitor:
    """Passive monitor. At every falling edge of cpu_clk_i it records pmu_cpu_rst_n_cpu_sync and
    pmu_cpu_clk_dis_sync. At the next rising edge it reads cpu_gated_clk, which is 1 after the edge
    only if u_cpu_cg passed that edge. A tick is a violation when the reset was already asserted at
    the falling edge before it. The enable latch of u_cpu_cg is transparent while cpu_core_clk is
    low, so the value at the falling edge decides the tick."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.ticks_reset_high = 0
        self.ticks_reset_low: list = []
        self.low_reset_edges = 0
        self.low_reset_edges_clock_enabled = 0
        self._task = None

    def start(self) -> None:
        self._task = cocotb.start_soon(self._run())
        _active_tasks.append(self._task)

    def stop(self) -> None:
        if self._task is not None:
            self._task.kill()
            self._task = None

    async def _run(self) -> None:
        soc = _soc(self.dut)
        while True:
            await FallingEdge(self.dut.cpu_clk_i)
            await ReadOnly()
            rst = int(soc.pmu_cpu_rst_n_cpu_sync.value)
            dis = int(soc.pmu_cpu_clk_dis_sync.value)
            await RisingEdge(self.dut.cpu_clk_i)
            await ReadOnly()
            ticked = int(soc.cpu_gated_clk.value)
            if rst == 0:
                self.low_reset_edges += 1
                if dis == 0:
                    self.low_reset_edges_clock_enabled += 1
                if ticked:
                    self.ticks_reset_low.append((get_sim_time("ns"), dis))
            elif ticked:
                self.ticks_reset_high += 1


async def _gate_experiment(dut, cpu_ns: int) -> dict:
    await _setup(dut, cpu_ns)
    if _dom_state(dut) != DOM_ON:
        raise RuntimeError("harness: the CPU PMU domain did not start at DOM_ON")
    mon = _GateTickMonitor(dut)
    mon.start()
    await ClockCycles(dut.cpu_clk_i, 8)
    await _set_mode(dut, MODE_CPU_OFF)
    await _wait_state(dut, {DOM_OFF}, 4000, "power-down")
    await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    await _set_mode(dut, MODE_NORMAL)
    await _wait_state(dut, {DOM_ON}, 4000, "power-up")
    await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    mon.stop()
    return {
        "cpu_ns": cpu_ns,
        "ticks_reset_high": mon.ticks_reset_high,
        "ticks_reset_low": list(mon.ticks_reset_low),
        "low_reset_edges": mon.low_reset_edges,
        "low_reset_edges_clock_enabled": mon.low_reset_edges_clock_enabled,
    }


async def _gate_sweep(dut) -> list:
    if "rows" not in _GATE_CACHE:
        rows = []
        for cpu_ns in GATE_RATIOS:
            rows.append(await _gate_experiment(dut, cpu_ns))
            r = rows[-1]
            dut._log.info(
                f"gate cpu={cpu_ns}ns: ticks outside reset {r['ticks_reset_high']}, "
                f"reset-low edges {r['low_reset_edges']} "
                f"(with the clock disable not yet seen: {r['low_reset_edges_clock_enabled']}), "
                f"ticks in reset {r['ticks_reset_low']}")
        _GATE_CACHE["rows"] = rows
    return _GATE_CACHE["rows"]


@cocotb.test()
async def test_cpu_clock_never_ticks_while_pmu_reset_asserted(dut):
    """Asserts: cpu_gated_clk does not tick at an edge of cpu_core_clk that follows a half cycle
    with pmu_cpu_rst_n_cpu_sync low. A CPU power-down and a power-up run at 1:1, 3x and 8x slower
    CPU clocks and with the CPU faster. The reset term of cpu_gated_clk_en is what holds this at
    1:1 and with a slower CPU clock; the mutant that removes the term fails here. This view depends
    on the order of the PMU actions: if the PMU disables the clock earlier, the clock disable term
    stops the clock first and this test stops telling whether the reset term exists. The forced
    test below does not depend on the order."""
    rows = await with_timeout(_gate_sweep(dut), 3000, "us")
    bad = [r for r in rows if r["ticks_reset_low"]]
    assert not bad, "cpu_gated_clk ticked while the PMU reset was asserted: " + "; ".join(
        f"cpu={r['cpu_ns']}ns ticks (ns, clock disable seen) {r['ticks_reset_low']}" for r in bad)


@cocotb.test()
async def test_cpu_clock_gate_control_monitor_sees_ticks_and_reset_window(dut):
    """Companion of the test above. Proves the monitor can see both sides of its rule at every
    ratio: the gated clock ticks while the reset is released (the monitor does not read a stuck
    clock), the PMU reset is asserted in the CPU domain for several edges, and at the first of
    those edges the clock disable has not reached the CPU domain yet at 1:1 and with a slower CPU
    clock (the window in which only the reset term stops the clock)."""
    rows = await with_timeout(_gate_sweep(dut), 3000, "us")
    for r in rows:
        tag = f"cpu={r['cpu_ns']}ns"
        assert r["ticks_reset_high"] > 10, f"{tag}: gated clock barely ticked outside reset"
        assert r["low_reset_edges"] >= 4, f"{tag}: the PMU reset was never seen asserted"
        if r["cpu_ns"] >= FABRIC_NS:
            assert r["low_reset_edges_clock_enabled"] >= 1, (
                f"{tag}: the clock disable always arrived first, so the reset term was not "
                "exercised")


# The sequenced power-down above stops the clock by the reset term only because the PMU asserts the
# reset one edge after it disables the clock and the reset crosses without a clock edge. A change of
# the PMU order (clock disable before the reset by more edges) moves the first stop to the clock
# disable term, and the sequenced test then no longer tells whether the reset term exists. The
# forced test below keeps the clock enable of the PMU high and asserts only the PMU reset of the
# CPU domain, by a deposit into the output flop. The clock disable term cannot stop the clock then,
# so the reset term is the only guard, whatever order the PMU uses.
_FORCED_CACHE: dict = {}


async def _forced_reset_experiment(dut, cpu_ns: int) -> dict:
    await _setup(dut, cpu_ns)
    soc = _soc(dut)
    if _dom_state(dut) != DOM_ON:
        raise RuntimeError("harness: the CPU PMU domain did not start at DOM_ON")
    mon = _GateTickMonitor(dut)
    mon.start()
    await ClockCycles(dut.cpu_clk_i, 8)
    hold = 3 * max(1, -(-cpu_ns // FABRIC_NS)) + 4
    for _ in range(hold):
        await RisingEdge(dut.clk_i)
        soc.u_pmu.rst_n_q[DOM_CPU].value = 0
    await RisingEdge(dut.clk_i)
    await ReadOnly()
    if int(soc.pmu_cpu_clk_dis_sync.value) != 0 or _dom_state(dut) != DOM_ON:
        raise RuntimeError("harness: the clock disable or the PMU state changed")
    await ClockCycles(dut.cpu_clk_i, 12)
    await ClockCycles(dut.clk_i, 12)
    mon.stop()
    return {
        "cpu_ns": cpu_ns,
        "hold": hold,
        "ticks_reset_high": mon.ticks_reset_high,
        "ticks_reset_low": list(mon.ticks_reset_low),
        "low_reset_edges": mon.low_reset_edges,
        "low_reset_edges_clock_enabled": mon.low_reset_edges_clock_enabled,
    }


async def _forced_sweep(dut) -> list:
    if "rows" not in _FORCED_CACHE:
        rows = []
        for cpu_ns in GATE_RATIOS:
            rows.append(await _forced_reset_experiment(dut, cpu_ns))
            r = rows[-1]
            dut._log.info(
                f"forced reset cpu={cpu_ns}ns: reset-low edges {r['low_reset_edges']} "
                f"(clock disable not seen: {r['low_reset_edges_clock_enabled']}), ticks outside "
                f"reset {r['ticks_reset_high']}, ticks in reset {r['ticks_reset_low']}")
        _FORCED_CACHE["rows"] = rows
    return _FORCED_CACHE["rows"]


@cocotb.test()
async def test_cpu_clock_never_ticks_while_forced_pmu_reset_and_clock_enabled(dut):
    """Asserts: with the PMU clock enable high, a PMU reset of the CPU domain stops cpu_gated_clk
    (no tick at an edge that follows a half cycle with pmu_cpu_rst_n_cpu_sync low). Only the reset
    term of cpu_gated_clk_en can stop the clock here. The reset is forced for several periods of
    clk_i by a deposit into the PMU output flop. Ratios 1:1, 3x and 8x slower, and the CPU faster."""
    rows = await with_timeout(_forced_sweep(dut), 3000, "us")
    bad = [r for r in rows if r["ticks_reset_low"]]
    assert not bad, "cpu_gated_clk ticked while the PMU reset was asserted: " + "; ".join(
        f"cpu={r['cpu_ns']}ns ticks (ns, clock disable seen) {r['ticks_reset_low']}" for r in bad)


@cocotb.test()
async def test_cpu_clock_gate_control_forced_reset_window_reached(dut):
    """Companion of the forced test. Proves the stimulus reaches the window: at every ratio the PMU
    reset is seen asserted in the CPU domain for several edges, the clock disable never reached the
    CPU domain in them (so only the reset term can stop the clock), and the gated clock ticks
    outside the reset (the monitor does not read a stuck clock)."""
    rows = await with_timeout(_forced_sweep(dut), 3000, "us")
    for r in rows:
        tag = f"cpu={r['cpu_ns']}ns"
        assert r["low_reset_edges"] >= 2, f"{tag}: the forced reset was seen on too few edges"
        assert r["low_reset_edges_clock_enabled"] == r["low_reset_edges"], (
            f"{tag}: the clock disable arrived during the reset, so the reset term is not the "
            "sole guard")
        assert r["ticks_reset_high"] > 10, f"{tag}: gated clock barely ticked outside reset"
