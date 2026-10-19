"""
test_soc_pmu_iso_ack.py -- bead 3ogd: PMU / soc_top isolation-before-reset ordering.

DUT: tb_soc_top (same SOC_BOOT_SOURCES / soc_boot_lint as soc_pmu_multiclock -- see the
soc_pmu_iso_ack target in tb/cocotb/soc/Makefile).

THE PROPERTY (UPF order, pmu.sv header): on a CPU power-down the isolation clamp must be ACTIVE IN
THE CPU DOMAIN before that domain's reset asserts, and before its clock gate closes.

Before bead 3ogd this held only by accident of ratio.  pmu_cpu_iso_en reaches the clamp through a
2-flop cdc_sync clocked by cpu_core_clk, while pmu_cpu_rst_n reaches u_cpu_pmu_rst_sync's ASYNC
clear directly: the reset takes effect on the very core_clk edge the PMU drops it, the clamp two
cpu_core_clk edges after it was raised.  The PMU spaces the two by 2 core_clk cycles, so the order
held only while 2 x cpu_core_clk period < 2 core_clk periods; with the CPU clock slower than the
fabric clock the reset beat the clamp.  The fix is an iso-ack handshake: the CPU-domain clamp
(pmu_cpu_iso_en_sync) is synchronised back to core_clk (u_cpu_iso_ack_sync -> pmu_cpu_iso_ack) and
the PMU sequencer waits in DOM_PD_ISO for it before it gates the clock / asserts reset, and waits in
DOM_PU_ISO for it to drop (the 4-phase return-to-zero half) before a new power-down may start.

Tests (all drive the power cycle by a backdoor deposit into the PMU CTRL storage cell, exactly as
test_soc_pmu_multiclock's power-up leg does; the CPU runs whatever the all-zero boot ROM makes it
run, which keeps its AXI request lines busy so the clamp has something to clamp):

  test_iso_before_reset_{cpu_3x_slower,cpu_8x_slower,ratio_1_1,cpu_faster}
      The invariant monitor (below) runs through a full CPU off->on cycle at that ratio.  The two
      slow-CPU ratios FAIL on origin/main (the reset asserts with the clamp still open) and are the
      regression test for part 1 of the bead.
  test_back_to_back_power_cycle_no_stale_ack
      Power the CPU off, on, and off again with no idle gap, at the 3x-slower ratio.  The second
      power-down must not be satisfied by the first cycle's still-high ack.
  test_dead_cpu_clock_does_not_hang_pmu
      cpu_rst_n_i held low (the CPU PLL domain is dead, the case a firmware write of PLL2
      pll_enable=0 produces): the ack can never arrive.  The PMU must not hang; it proceeds after
      ISO_ACK_TIMEOUT cycles, sets STATUS[3], and the GPU domain is unaffected.  Releasing the
      reset and power-cycling again clears the flag and takes the normal (acked) path.
  test_gpu_isolation_clamps_follow_pmu_iso_en
      Part 2 of the bead: every ISO_GPU handshake clamp in soc_top -- including
      m_axil_if_rready, added by PR #301 (h3lm) and until now untested -- equals
      `raw & ~pmu_gpu_iso_en` on every cycle of a GPU power cycle, and the GPU needs no ack
      (same clock domain: its iso/reset are both PMU flops on core_clk).

THE INVARIANT MONITOR (sampled after every clk_i AND every cpu_clk_i rising edge, ReadOnly):
  INV1  pmu_cpu_rst_n_cpu_sync == 0  ->  pmu_cpu_iso_en_sync == 1   (reset implies clamp active)
  INV2  cpu_gated_clk_en == 0        ->  pmu_cpu_iso_en_sync == 1   (clock gated implies clamp)
  INV4  pmu_cpu_iso_ack changes only on clk_i edges (it is a synchroniser output into core_clk)
  INV3  pmu_cpu_iso_en_sync == 0     ->  pmu_cpu_rst_n_cpu_sync == 1  (power-UP: clamp not released
        while the PMU reset is still observed asserted).  NOMINAL-ONLY: in this zero-delay model both
        release paths are 2-flop syncs on the same clock so the order is deterministic; in silicon a
        metastable first stage can swap them by one cpu_core_clk edge.  That is benign by structure
        (see the power-up note in pmu.sv): the clamp consumers are clocked by cpu_gated_clk, which
        cannot tick before reset release is observed.  The check is kept as a nominal-order guard.
The monitor is armed only after the synchroniser chains have filled (their pre-fill 0s are not
violations).
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge, with_timeout
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
# Part 2: ISO_GPU clamps, including m_axil_if_rready (PR #301 / h3lm)
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

    m_axil_if_rready (gif_axil_rready) is the clamp PR #301 added: the GPU ifetch R-channel accept
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
                    out = int((out_h[idx] if idx is not None else out_h).value)
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
