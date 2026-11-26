"""
test_soc_pmu_iso_ack.py -- PMU / soc_top isolation-before-reset ordering. DUT: tb_soc_top
(as soc_pmu_multiclock).
THE PROPERTY (UPF order, pmu.sv header): on a CPU power-down the isolation clamp must be ACTIVE IN
THE CPU DOMAIN before that domain's reset asserts, and the clamp must never be active while the CPU
clock gate is open. The PMU gates the clock first, then raises the clamp request, and waits for the
iso-ack: the CPU-domain clamp (cpu_iso_clamp, the synchronised request qualified by the closed
gate) is registered (cpu_iso_clamp_q) and synchronised back to core_clk (u_cpu_iso_ack_sync ->
pmu_cpu_iso_ack). The PMU waits in DOM_PD_ISO for a rising ack before it asserts reset, and waits in
DOM_PU_ISO for a falling ack (the 4-phase return-to-zero half) before it ungates the clock. A wait
accepts only an ack level that it saw change after the wait began.
Tests drive the power cycle by a backdoor deposit into the PMU CTRL cell (as
  test_soc_pmu_multiclock's power-up leg).
  test_iso_before_reset_{cpu_3x_slower,cpu_8x_slower,ratio_1_1,cpu_faster}: the invariant monitor
      runs through a full CPU off->on cycle at that ratio. The two slow-CPU ratios fail without the
      ack handshake.
  test_back_to_back_power_cycle_no_stale_ack: off, on, off with no idle gap; the 2nd power-down must
      not use the old ack.
  test_dead_cpu_clock_does_not_hang_pmu: cpu_rst_n_i held low, so the ack never arrives; the PMU
      proceeds after ISO_ACK_TIMEOUT cycles in both waits, sets STATUS[3], and the GPU domain is
      unaffected. The flag is sticky across the later power cycle.
  test_gpu_isolation_clamps_follow_pmu_iso_en: every ISO_GPU clamp in soc_top equals `raw &
      ~pmu_gpu_iso_en` on every cycle of a GPU power cycle. The GPU needs no ack (same
      clock domain).
INVARIANT MONITOR (after every clk_i and cpu_clk_i rising edge, ReadOnly; armed once the
synchroniser chains fill): INV1 pmu_cpu_rst_n_cpu_sync == 0 -> pmu_cpu_iso_en_sync == 1. INV2
cpu_iso_clamp == 1 -> cpu_gated_clk_en == 0 (the clamp is active only while the clock gate is
closed). INV3 pmu_cpu_iso_en_sync == 0 -> pmu_cpu_rst_n_cpu_sync == 1 (power-UP; NOMINAL-ONLY, silicon can swap the order by one edge, benign
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
from sram_backdoor import sram_mem

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# pmu_dom_state_e encoding (pmu.sv `typedef enum`). The power-down order is SAVE, GATE, ISO and the
# power-up order is RST, RESTORE, ISO, CLK.
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
async def _setup(dut, cpu_ns: int, *, hold_cpu_reset: bool = False, rom_words=None) -> None:
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

    if rom_words is not None:
        for i, w in enumerate(rom_words):
            dut.u_soc.u_boot_rom.mem[i].value = w
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
            if int(soc.cpu_iso_clamp.value) == 1 and gate_en == 1:
                self.violations.append(
                    (now, "INV2", "CPU isolation clamp active while the clock gate is open"))
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
    expected = [DOM_ON, DOM_PD_SAVE, DOM_PD_GATE, DOM_PD_ISO, DOM_OFF, DOM_PU_RST, DOM_PU_RESTORE,
                DOM_PU_ISO, DOM_PU_CLK, DOM_ON]
    # The first ON is the initial value (the monitor records it as the first "change").
    assert seq == expected, f"{label}: UPF-order walk deviated: {seq} != {expected}"
    assert mon.rst_sync_fall_ns, f"{label}: the PMU reset never asserted in the CPU domain"
    assert not mon.violations, (
        f"{label}: isolation ordering violated {len(mon.violations)}x: "
        + "; ".join(f"[{n}] t={t:.0f}ns {m}" for t, n, m in mon.violations[:4]))
    if mon.has_ack:
        # The handshake itself: the ack must rise strictly before the reset step.
        t_off = next(t for t, s in mon.transitions if s == DOM_OFF)
        assert mon.ack_rise_ns and mon.ack_rise_ns[0] < t_off, (
            f"{label}: DOM_OFF entered at {t_off}ns without a prior ack rise "
            f"({mon.ack_rise_ns})")
        pd_dwell = _dwell_cycles(mon, DOM_PD_ISO)
        pu_dwell = _dwell_cycles(mon, DOM_PU_ISO)
        dut._log.info(f"{label}: PD_ISO dwell {pd_dwell} core cycles, PU_ISO dwell {pu_dwell} core cycles")
        # A real ack ends each wait long before the timeout. A tied-off ack only ends it by timing out.
        assert pd_dwell < ISO_ACK_TIMEOUT // 2 and pu_dwell < ISO_ACK_TIMEOUT // 2, (
            f"{label}: a wait ran to its timeout (PD_ISO {pd_dwell}, PU_ISO {pu_dwell} cycles)")
        status = int(_soc(dut).u_pmu.u_regbank.regs[1].value)
        assert not (status >> STATUS_ISO_ACK_TIMEOUT_BIT) & 1, f"{label}: STATUS[3] set by a healthy cycle: {status:#x}"


@cocotb.test()
async def test_iso_before_reset_cpu_3x_slower(dut):
    """CPU clock 3x SLOWER than the fabric: the ack gates the reset and the clamp never overlaps an open clock gate."""
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
    travelling through the registered clamp and two synchronisers, so a stale ack could still be
    high for several core cycles.  The second power-down must not take that as its ack: the
    PU_ISO wait-for-ack-low (4-phase RZ) and the ack_low_seen qualifier prevent it.
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
        assert cpu_seq == [DOM_ON, DOM_PD_SAVE, DOM_PD_GATE, DOM_PD_ISO, DOM_OFF], cpu_seq
        # The wait lasted the whole timeout, the flag is set, and is visible in STATUS[3].
        assert cpu_off_cycle - gpu_off_cycle >= ISO_ACK_TIMEOUT - 2, (
            f"CPU gated/reset after only {cpu_off_cycle - gpu_off_cycle} cycles without an ack")
        await ClockCycles(dut.clk_i, 3)  # the STATUS word lags the flag by a cycle or two
        status = int(soc.u_pmu.u_regbank.regs[1].value)
        assert (status >> STATUS_ISO_ACK_TIMEOUT_BIT) & 1, f"STATUS[3] not set: 0x{status:x}"

        # Power back up: the dead domain's ack never rises, so the PU_ISO wait cannot see a high ack
        # and runs the full timeout too.
        await _set_mode(dut, MODE_NORMAL)
        pu_iso_cycles = 0
        for _ in range(2000):
            await RisingEdge(dut.clk_i)
            await ReadOnly()
            if _dom_state(dut) == DOM_PU_ISO:
                pu_iso_cycles += 1
            elif _dom_state(dut) == DOM_ON:
                break
        else:
            raise TimeoutError("power-up with a dead CPU domain never reached DOM_ON")
        assert pu_iso_cycles >= ISO_ACK_TIMEOUT - 2, (
            f"the power-up wait ended after {pu_iso_cycles} cycles with no ack")
        await ClockCycles(dut.clk_i, 4)

        # Revive the CPU PLL domain and power-cycle again: the ack is real and the flag is sticky.
        dut.cpu_rst_n_i.value = 1
        await ClockCycles(dut.cpu_clk_i, 60)
        await ClockCycles(dut.clk_i, 60)
        mon = IsoMonitor(dut)
        mon.start()
        await _set_mode(dut, MODE_CPU_OFF)
        await _wait_state(dut, {DOM_OFF}, 4000, "power-down after revival")
        await ClockCycles(dut.clk_i, 3)
        status = int(soc.u_pmu.u_regbank.regs[1].value)
        assert (status >> STATUS_ISO_ACK_TIMEOUT_BIT) & 1, (
            f"STATUS[3] was cleared by a power-down: 0x{status:x}")
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
# A PMU reset while the CPU domain is in DOM_OFF sets the clock enable, the clamp and the reset of
# the domain to their DOM_ON values at one edge. The three controls then cross synchronisers of the
# same depth into the CPU domain and are released at the same edge of cpu_clk_i, so the power-up
# order of DS-PMU-022 (reset, clamp release, clock) does not apply there. The owner accepted this
# behaviour. The test that asserts the specified order is marked expect_fail: it must fail while
# the behaviour exists. If it passes, the RTL changed. Then replace it by a normal test that proves
# the rule. A harness fault raises RuntimeError, not AssertionError, so expect_fail cannot hide it.
# A normal test runs the same monitor over a power-up that the PMU sequences. The clock enable
# follows the clamp release at every ratio, because the ack round trip sits between them. The
# reset release and the clamp release are only strictly ordered at 1:1 and with the CPU faster,
# where each release falls on its own edge by the spacing of the PMU outputs. At slower CPU clocks
# the spacing is below one CPU clock, so those two can share an edge by design. There the order is
# logged and only the weaker rule (no earlier clamp release) is asserted.
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
    return ev["rst"] < ev["iso"] < ev["en"]


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
    """Asserts: after a PMU reset while the CPU domain is in OFF, the domain reset is released
    first, then the clamp control in the CPU domain, then the clock gate enable (DS-PMU-022).
    Checked at 1:1 and with the CPU clock faster. The order at the other ratios is in the log.

    expect_fail: the reset branch of the PMU loads the three controls together and their
    synchronisers have the same depth, so the three releases fall on one edge. The owner accepted
    this. If this test passes, the RTL changed."""
    rows = await with_timeout(_p4_sweep(dut), 3000, "us")
    bad = [_fmt_p4(c, "reset", rows[(c, "reset")]) for c in P4_STRICT_RATIOS
           if not _p4_strict(rows[(c, "reset")])]
    assert not bad, "the clock was not released last: " + "; ".join(bad)


@cocotb.test()
async def test_p4_control_sequenced_power_up_releases_cpu_clamp_last(dut):
    """Proves the monitor and the check of the P4 test can pass. After a PMU-sequenced power-up
    from OFF the order is reset, clamp release, clock enable at 1:1 and with the CPU faster. At every
    ratio the clamp is not released before the reset and the clock enable follows the clamp."""
    rows = await with_timeout(_p4_sweep(dut), 3000, "us")
    for cpu_ns in P4_RATIOS:
        ev = rows[(cpu_ns, "sequenced")]
        tag = _fmt_p4(cpu_ns, "sequenced", ev)
        assert ev["iso"] >= ev["rst"] and ev["en"] > ev["iso"], f"release order broken: {tag}"
        if cpu_ns in P4_STRICT_RATIOS:
            assert _p4_strict(ev), f"sequenced power-up did not release the clock last: {tag}"


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
    CPU clocks and with the CPU faster. The PMU gates the clock before it asserts the reset, so the
    clock disable term is the first stop and this test does not tell whether the reset term of
    cpu_gated_clk_en exists. It guards the sequenced behaviour. The forced test below checks the
    reset term."""
    rows = await with_timeout(_gate_sweep(dut), 3000, "us")
    bad = [r for r in rows if r["ticks_reset_low"]]
    assert not bad, "cpu_gated_clk ticked while the PMU reset was asserted: " + "; ".join(
        f"cpu={r['cpu_ns']}ns ticks (ns, clock disable seen) {r['ticks_reset_low']}" for r in bad)


@cocotb.test()
async def test_cpu_clock_gate_control_monitor_sees_ticks_and_reset_window(dut):
    """Companion of the test above. Proves the monitor can see both sides of its rule at every
    ratio: the gated clock ticks while the reset is released (the monitor does not read a stuck
    clock), the PMU reset is asserted in the CPU domain for several edges, and at the first of
    those edges the clock disable has already reached the CPU domain. The PMU gates the clock
    before it asserts the reset, so in a sequenced power-down the reset term is never the first
    stop: this view no longer tells whether the reset term exists. The forced test below does."""
    rows = await with_timeout(_gate_sweep(dut), 3000, "us")
    for r in rows:
        tag = f"cpu={r['cpu_ns']}ns"
        assert r["ticks_reset_high"] > 10, f"{tag}: gated clock barely ticked outside reset"
        assert r["low_reset_edges"] >= 4, f"{tag}: the PMU reset was never seen asserted"
        assert r["low_reset_edges_clock_enabled"] == 0, (
            f"{tag}: the clock was still enabled at an edge with the PMU reset asserted, so the "
            "PMU did not gate the clock before the reset")


# The sequenced power-down above does not test the reset term: the PMU gates the clock before it
# asserts the reset, so the clock disable term stops the clock first. The forced test below keeps
# the clock enable of the PMU high and asserts only the PMU reset of the CPU domain, by a deposit
# into the output flop. The clock disable term cannot stop the clock then, so the reset term is
# the only guard, whatever order the PMU uses.
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


# ---------------------------------------------------------------------------------------------
# Part 5: debug access while the CPU domain is off
# ---------------------------------------------------------------------------------------------
DBG_CTRL, DBG_STATUS = 0x000, 0x004
OFF_RDATA = 0xDEAD_BEEF
DBG_MAX_WAIT_FABRIC = 600


async def _dbg_xfer(dut, addr: int, write: bool = False, data: int = 0) -> tuple:
    """One APB3 transfer on the debug port (clk_i domain). Returns (rdata, pslverr, completed)."""
    dut.apb_paddr_i.value = addr
    dut.apb_pwrite_i.value = 1 if write else 0
    dut.apb_pwdata_i.value = data
    dut.apb_psel_i.value = 1
    dut.apb_penable_i.value = 0
    await RisingEdge(dut.clk_i)
    dut.apb_penable_i.value = 1
    await RisingEdge(dut.clk_i)
    waited = 0
    result = None
    while result is None:
        if int(dut.apb_pready_o.value):
            result = (
                int(dut.apb_prdata_o.value),
                bool(int(dut.apb_pslverr_o.value)),
                True,
            )
        else:
            waited += 1
            if waited > DBG_MAX_WAIT_FABRIC:
                result = (0, False, False)
            else:
                await RisingEdge(dut.clk_i)
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    return result


async def _debug_while_off_body(dut, cpu_ns: int) -> dict:
    await _setup(dut, cpu_ns)
    assert _dom_state(dut) == DOM_ON
    await _set_mode(dut, MODE_CPU_OFF)
    during = []
    for _ in range(400):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        st_issue = _dom_state(dut)
        await RisingEdge(dut.clk_i)
        rd, err, ok = await _dbg_xfer(dut, DBG_STATUS)
        during.append((st_issue, _dom_state(dut), rd, err, ok))
        if st_issue == DOM_OFF and len(during) >= 3:
            break
    else:
        raise RuntimeError("harness: the CPU domain never reached DOM_OFF")
    await ClockCycles(dut.clk_i, 40)
    await ClockCycles(dut.cpu_clk_i, 8)
    off_read = await _dbg_xfer(dut, DBG_STATUS)
    off_write = await _dbg_xfer(dut, DBG_CTRL, True, 1)
    gone = await _dbg_xfer(dut, DBG_STATUS)
    await _set_mode(dut, MODE_NORMAL)
    await _wait_state(dut, {DOM_ON}, 4000, "power-up")
    await ClockCycles(dut.clk_i, 80)
    await ClockCycles(dut.cpu_clk_i, 16)
    on_read = await _dbg_xfer(dut, DBG_STATUS)
    return {
        "cpu_ns": cpu_ns,
        "during": during,
        "off_read": off_read,
        "off_write": off_write,
        "gone": gone,
        "on_read": on_read,
    }


async def _debug_while_off_sweep(dut) -> list:
    return [
        await _debug_while_off_body(dut, ns)
        for ns in (FABRIC_NS, 3 * FABRIC_NS, 8 * FABRIC_NS, 3)
    ]


@cocotb.test()
async def test_debug_access_while_cpu_off_completes_with_error(dut):
    """A debug APB access while the PMU has powered the CPU domain off completes with PSLVERR and
    OFF_RDATA (0xDEAD_BEEF) instead of hanging, at CPU clocks 1:1, 3x slower, 8x slower and 7:3
    faster. The access that reaches the bridge cannot be answered by the CPU domain: its clock is
    gated and its reset is asserted. Back to back accesses run from the request until the domain is
    off: each ends within the bound, and an access that starts after the domain is off returns the
    error. After the power-up the debug port reads STATUS with no error."""
    rows = await with_timeout(_debug_while_off_sweep(dut), 6000, "us")
    for r in rows:
        tag = f"cpu={r['cpu_ns']}ns"
        assert all(ok for *_x, ok in r["during"]), (
            f"{tag}: an access did not end: {r['during']}"
        )
        for st_issue, st_done, rd, err, _ok in r["during"]:
            if st_issue == DOM_OFF and st_done == DOM_OFF:
                assert err and rd == OFF_RDATA, (
                    f"{tag}: access in DOM_OFF gave err={err} rd={rd:#x}"
                )
        errs = [x for x in r["during"] if x[3]]
        assert errs, (
            f"{tag}: no access during the power-down saw the off error: {r['during']}"
        )
        assert all(x[2] == OFF_RDATA for x in errs), (
            f"{tag}: error data {[hex(x[2]) for x in errs]}"
        )
        for name in ("off_read", "off_write", "gone"):
            rd, err, ok = r[name]
            assert ok, f"{tag}: {name} hung while the CPU domain was off"
            assert err and rd == OFF_RDATA, f"{tag}: {name} gave err={err} rd={rd:#x}"
        rd, err, ok = r["on_read"]
        assert ok and not err and rd != OFF_RDATA, (
            f"{tag}: after power-up gave ok={ok} err={err} rd={rd:#x}"
        )
    dut._log.info(
        "debug access while the CPU domain is off: "
        + "; ".join(
            f"cpu={r['cpu_ns']}ns {len(r['during'])} accesses to DOM_OFF, "
            f"{sum(1 for x in r['during'] if x[3])} with the off error"
            for r in rows
        )
    )
# =============================================================================
# Part 3: GPU instruction-fetch adapter across a GPU domain reset (SoC level).
#
# u_gif_adapter turns the GPU ifetch AXI4-Lite port into the AXI4 master on crossbar M1. It
# holds an AR request in a skid buffer until the crossbar accepts it and passes the R channel
# through. The GPU is reset by gpu_domain_rst_n (core_rst_n AND pmu_gpu_rst_n) when the PMU
# power-cycles it. A GPU power cycle must leave no fetch of the old GPU behind: no AR that
# reaches the crossbar after the reset, no R beat that reaches the new GPU, and no crossbar
# read engine that stays locked on a beat that nobody will take.
# The firmware is the gpu_iso image: it runs a kernel on the GPU, so the GPU fetches. The test
# makes the crossbar SRAM read engine busy for another master by a backdoor write of its state
# (R_DATA for master 0, no response ever comes). That is the state of a slave that is slow for
# another master. The GPU fetch then waits at the adapter. A release writes R_IDLE again.
# A second backdoor holds the SRAM controller itself busy: the crossbar accepts the AR but the
# R beat is late, and a free of the controller sets when the beat arrives.
# The relaunch tests use a second image that waits in a loop without bus access while the
# testbench power-cycles the GPU, then runs a second kernel on new source data.
# The PMU power cycles are driven by the PMU CTRL backdoor, as in Part 1 and Part 2.
# =============================================================================
GIF_SRAM_SLAVE = 1
XBAR_R_IDLE, XBAR_R_AR, XBAR_R_DATA = 0, 1, 2
SRAM_CTRL_R_BUSY = 1  # sram_controller read FSM: R_IDLE is 0
GIF_CPU_NS = 3  # CPU clock faster than the fabric clock (the GPU path is in the fabric domain)
GIF_SLOW_CPU_NS = 9  # CPU clock slower than the fabric clock
GIF_LAUNCH_TIMEOUT = 120_000
GIF_HOLD_CYCLES = 3
GIF_KERNEL_WINDOW = 3000  # a kernel needs a few hundred fabric cycles
GIF_RELAUNCH_TIMEOUT = 150_000
GIF_DWELL = 600  # loop count of the relaunch image, longer than any power cycle of these tests
GIF_RESULT_WORD = 112  # first word of the kernel result in SRAM
GIF_RESULT_SCALE = 0x20  # source scale of the second kernel of the relaunch image
GIF_HAMMER_A = 0x2800  # SRAM word range the CPU hammers, clear of the kernel, its source and result
GIF_HAMMER_B = GIF_HAMMER_A + 0x1000  # the same SRAM words through the 4 KB alias: same D-cache set
GIF_HAMMER_LOOPS = 40
GIF_STATUS_POLLS = 20000
GIF_STATUS_DONE = 2  # GPU STATUS done bit
GIF_CONTENTION_TIMEOUT = 120_000
GIF_FW_HEX = Path(__file__).resolve().parent / "integ_fw" / "gpu_iso.hex"
_GIF_CACHE: dict = {}


def _read_hex_words(path: Path) -> list:
    words = []
    with open(path) as fh:
        for line in fh:
            tok = line.strip()
            if tok and not tok.startswith("//") and not tok.startswith("@"):
                words.append(int(tok, 16))
    return words


def _gif_relaunch_image() -> tuple:
    """Return (ROM words, PASS pc, FAIL pc) of the relaunch image: kernel 1 is launched, then a loop
    of register instructions runs while the testbench power-cycles the GPU, then the image waits for
    the PMU to report both domains on and runs kernel 2 on new source data."""
    if "image" in _GIF_CACHE:
        return _GIF_CACHE["image"]
    from tb.cocotb.soc.integ_fw import gen_integ_hex as gen

    gi = gen.gpuirq
    asm = gen.Assembler(origin=gen.ROM_BASE)
    gen.trampoline(asm)
    asm.label("MAIN")
    gen.li(asm, 3, gi.SRC_BASE)
    gen.li(asm, 5, gi.KERNEL_PC)
    gen.li(asm, 6, gen.GPU_BASE)
    gen.li(asm, 9, gen.PMU_BASE)

    def write_src(scale):
        for i in range(gi.N_SRC_WORDS):
            asm.emit(gen.ADDI(7, 0, (i + 1) * scale))
            asm.emit(gen.SW(7, 3, i * 4))

    def launch():
        asm.emit(gen.SW(5, 6, gi.GPU_OFF_KERNEL_PC))
        asm.emit(gen.ADDI(7, 0, 1))
        for off in (gi.GPU_OFF_GRID_X, gi.GPU_OFF_GRID_Y, gi.GPU_OFF_GRID_Z,
                    gi.GPU_OFF_BLOCK_Y, gi.GPU_OFF_BLOCK_Z):
            asm.emit(gen.SW(7, 6, off))
        asm.emit(gen.ADDI(7, 0, 8))
        asm.emit(gen.SW(7, 6, gi.GPU_OFF_BLOCK_X))
        asm.emit(gen.ADDI(7, 0, 0x05))
        asm.emit(gen.SW(7, 6, gi.GPU_OFF_CTRL))

    def poll(tag, base, off, mask=None, eq=None):
        gen.li(asm, 20, 20000)
        asm.emit(gen.ADDI(21, 0, 0))
        asm.label(f"{tag}_POLL")
        asm.emit(gen.LW(22, base, off))
        if eq is None:
            asm.emit(gen.ANDI(22, 22, mask))
            gen.br(asm, gen.BNE, 22, 0, f"{tag}_GOT")
        else:
            asm.emit(gen.ADDI(23, 0, eq))
            gen.br(asm, gen.BEQ, 22, 23, f"{tag}_GOT")
        asm.emit(gen.ADDI(21, 21, 1))
        gen.br(asm, gen.BNE, 21, 20, f"{tag}_POLL")
        gen.jmp(asm, "FAIL")
        asm.label(f"{tag}_GOT")

    write_src(0x10)
    gen.flush_dcache(asm, "FL1")
    for i, kw in enumerate(gi.build_gpu_kernel()):
        gen.li(asm, 7, kw)
        asm.emit(gen.SW(7, 5, i * 4))
    gen.flush_dcache(asm, "FL2")
    asm.emit(gen.LW(7, 6, gi.GPU_OFF_CTRL))
    launch()
    asm.emit(gen.ADDI(16, 0, 0))
    gen.li(asm, 17, GIF_DWELL)
    asm.label("DWELL")
    asm.emit(gen.ADDI(16, 16, 1))
    gen.br(asm, gen.BNE, 16, 17, "DWELL")
    poll("PON", 9, 0x04, eq=gen.PMU_STATUS_NORMAL)
    write_src(GIF_RESULT_SCALE)
    gen.flush_dcache(asm, "FL3")
    launch()
    poll("GDONE2", 6, gi.GPU_OFF_STATUS, mask=2)
    gen.flush_dcache(asm, "FL4")
    gen.jmp(asm, "PASS")
    gen.tail(asm)
    words = asm.resolve()
    assert len(words) <= gen.ROM_WORDS
    image = (words + [gen.NOP] * (gen.ROM_WORDS - len(words)), asm.labels["PASS"],
             asm.labels["FAIL"])
    _GIF_CACHE["image"] = image
    return image


def _xbar(dut):
    return _soc(dut).u_bus.u_xbar


def _sram_rstate(dut) -> int:
    return (int(_xbar(dut).rstate.value) >> (2 * GIF_SRAM_SLAVE)) & 3


def _force_sram_rstate(dut, state: int, master: int = 0) -> None:
    """Backdoor write of the crossbar read-engine state of the SRAM slave and its master grant."""
    xb = _xbar(dut)
    sh = 2 * GIF_SRAM_SLAVE
    xb.rstate.value = (int(xb.rstate.value) & ~(3 << sh)) | (state << sh)
    xb.rsel.value = (int(xb.rsel.value) & ~(3 << sh)) | (master << sh)


def _hold_sram_ctrl(dut) -> None:
    """Make the SRAM controller refuse an AR: busy, with a full head register that nobody takes,
    because the crossbar read engine is not in R_DATA."""
    ctrl = _soc(dut).u_sram
    ctrl.r_active.value = 0
    ctrl.r_valid_q.value = 1
    ctrl.rstate.value = SRAM_CTRL_R_BUSY


def _free_sram_ctrl(dut) -> None:
    _soc(dut).u_sram.r_valid_q.value = 0


def _gif_row(dut, cyc: int) -> dict:
    soc = _soc(dut)
    return dict(
        cyc=cyc,
        rst_n=int(soc.gpu_domain_rst_n.value),
        iso=int(soc.pmu_gpu_iso_en.value),
        m_arv=int(soc.gif_axi_arvalid.value),
        m_arr=int(soc.gif_axi_arready.value),
        m_addr=int(soc.gif_axi_araddr.value),
        m_rv=int(soc.gif_axi_rvalid.value),
        m_rr=int(soc.gif_axi_rready.value),
        al_arv=int(soc.gif_axil_arvalid.value),
        al_arr=int(soc.gif_axil_arready.value),
        al_addr=int(soc.gif_axil_araddr.value),
        rv=int(soc.gif_axil_rvalid.value),
        rr=int(soc.gif_axil_rready.value),
        rstate=_sram_rstate(dut),
        irq=int(soc.gpu_irq_raw.value),
        st=int(soc.u_pmu.dom_state_q[DOM_GPU].value),
        clk_en=int(soc.pmu_gpu_clk_en.value),
        gpu_aw=int(soc.bus_axil_gpu_awvalid.value) & int(soc.bus_axil_gpu_awready.value),
        gpu_ar=int(soc.bus_axil_gpu_arvalid.value) & int(soc.bus_axil_gpu_arready.value),
        gpu_araddr=int(soc.bus_axil_gpu_araddr.value) & 0xFFF,
        gpu_awaddr=int(soc.bus_axil_gpu_awaddr.value) & 0xFFF,
    )


def _gpu_off(r: dict) -> bool:
    """The level of gpu_dom_off in soc_top."""
    return bool(r["iso"] or not r["rst_n"] or not r["clk_en"])


class _GifRun:
    """One cycle-by-cycle run. step() advances one fabric clock, samples a row and returns it;
    actions requested after a sample are applied at the next clock edge, before the next sample."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.rows: list = []
        self._pending: list = []
        self._commits: list = []
        self.hold_idx = 0
        _active_tasks.append(cocotb.start_soon(self._watch_commits()))

    async def _watch_commits(self) -> None:
        """Record every commit at the CPU clock. commit_valid_o lasts one CPU clock, so a sample at
        the fabric clock misses commits when the CPU clock is faster."""
        while True:
            await RisingEdge(self.dut.cpu_clk_i)
            await ReadOnly()
            if int(self.dut.commit_valid_o.value):
                self._commits.append(int(self.dut.commit_pc_o.value))

    def later(self, fn) -> None:
        self._pending.append(fn)

    async def step(self) -> dict:
        await RisingEdge(self.dut.clk_i)
        pending, self._pending = self._pending, []
        for fn in pending:
            fn()
        await ReadOnly()
        row = _gif_row(self.dut, len(self.rows))
        row["commits"], self._commits = self._commits, []
        self.rows.append(row)
        return row

    async def until(self, pred, limit: int, label: str) -> dict:
        for _ in range(limit):
            row = await self.step()
            if pred(row):
                return row
        raise RuntimeError(f"harness: {label} not reached in {limit} cycles")


async def _gif_held_start(dut, cpu_ns: int = GIF_CPU_NS, rom_words=None) -> _GifRun:
    """Boot the gpu_iso image, block the SRAM read engine when the GPU kernel is launched, and
    return once the GPU fetch AR has waited at the adapter for GIF_HOLD_CYCLES cycles."""
    words = _read_hex_words(GIF_FW_HEX) if rom_words is None else rom_words
    await _setup(dut, cpu_ns, rom_words=words)
    run = _GifRun(dut)
    # The launch is the GPU CTRL write at offset 0 (the registers before it are at other offsets).
    limit = GIF_LAUNCH_TIMEOUT if cpu_ns <= FABRIC_NS else 2 * GIF_LAUNCH_TIMEOUT
    await run.until(lambda r: r["gpu_aw"] and r["gpu_awaddr"] == 0, limit, "GPU launch")
    if _sram_rstate(dut) != XBAR_R_IDLE:
        raise RuntimeError("harness: the SRAM read engine was busy at the GPU launch")
    run.later(lambda: _force_sram_rstate(dut, XBAR_R_DATA))
    stable = 0
    for _ in range(64):
        row = await run.step()
        stable = stable + 1 if (row["m_arv"] and not row["m_arr"]) else 0
        if stable >= GIF_HOLD_CYCLES:
            run.hold_idx = len(run.rows) - GIF_HOLD_CYCLES
            return run
    raise RuntimeError("harness: the GPU fetch AR never waited at the adapter")


def _mode_now(dut, mode: int) -> None:
    _soc(dut).u_pmu.u_regbank.regs[0].value = mode


def _release_block(dut) -> None:
    _force_sram_rstate(dut, XBAR_R_IDLE)


async def _gif_power_up(run, wake_early: bool = False) -> dict:
    """Request NORMAL (unless it was requested early) and return the row in which the GPU domain is
    back to DOM_ON."""
    if not wake_early:
        run.later(lambda: _mode_now(run.dut, MODE_NORMAL))
    return await run.until(lambda r: r["st"] == DOM_ON, 400, "GPU power-up")


async def _gif_scenario_held_ar(dut, cpu_ns: int = GIF_CPU_NS, rom_words=None) -> dict:
    """Held AR across a GPU domain reset: the reset asserts while the AR waits at the adapter.
    The block is released when the reset has been low for 3 cycles, then the GPU powers up."""
    run = await _gif_held_start(dut, cpu_ns, rom_words)
    held_addr = run.rows[-1]["m_addr"]
    run.later(lambda: _mode_now(dut, MODE_GPU_OFF))
    first_rst = await run.until(lambda r: r["rst_n"] == 0, 400, "GPU domain reset")
    for _ in range(3):
        await run.step()
    run.later(lambda: _release_block(dut))
    for _ in range(14):
        await run.step()
    up = await _gif_power_up(run)
    for _ in range(40):
        await run.step()
    return {"rows": run.rows, "t_rst": first_rst["cyc"], "t_up": up["cyc"],
            "held_addr": held_addr, "run": run}


async def _gif_scenario_r_in_flight(
    dut, cpu_ns: int = GIF_CPU_NS, rom_words=None, *,
    wake_early: bool = False, late_r: bool = False, cycles: int = 1,
) -> dict:
    """AR accepted, R in flight at the GPU domain reset. The block is released in the cycle after
    the PMU enters its clock-gate state. The crossbar accepts the waiting AR in the cycle the
    isolation clamp becomes active, the R beat arrives three cycles later and waits on the clamped
    rready, and the GPU domain reset asserts one cycle after the clamp.
    wake_early: the mode returns to NORMAL one cycle after the power-down request, so the power-down
    is aborted by software and the PMU still has to complete it.
    late_r: the SRAM controller refuses the AR, so the R beat comes only after the GPU is back on.
    cycles: 2 repeats the power cycle with no idle gap."""
    run = await _gif_held_start(dut, cpu_ns, rom_words)
    run.later(lambda: _mode_now(dut, MODE_GPU_OFF))
    if wake_early:
        await run.step()
        run.later(lambda: _mode_now(dut, MODE_NORMAL))
    await run.until(lambda r: r["st"] == DOM_PD_GATE, 400, "GPU gate state")
    run.later(lambda: _release_block(dut))
    if late_r:
        run.later(lambda: _hold_sram_ctrl(dut))
    iso_row = await run.until(lambda r: r["iso"] == 1, 400, "GPU isolation")
    first_rst = await run.until(lambda r: r["rst_n"] == 0, 400, "GPU domain reset")
    t_rst = first_rst["cyc"]
    accepted = [r for r in run.rows[iso_row["cyc"] : t_rst] if r["m_arv"] and r["m_arr"]]
    if not accepted:
        raise RuntimeError("harness: the crossbar did not accept the AR before the GPU reset")
    # With a reset that waits, the R beat is still pending: nothing may have taken it.
    if not late_r and any(r["rv"] and r["rr"] for r in run.rows[iso_row["cyc"] : t_rst]):
        raise RuntimeError("harness: the GPU took the R beat before the reset")
    for _ in range(24):
        await run.step()
    up = await _gif_power_up(run, wake_early)
    t_rst2 = None
    if cycles > 1:
        run.later(lambda: _mode_now(dut, MODE_GPU_OFF))
        second = await run.until(lambda r: r["rst_n"] == 0, 400, "second GPU domain reset")
        t_rst2 = second["cyc"]
        for _ in range(8):
            await run.step()
        up = await _gif_power_up(run)
    if late_r:
        run.later(lambda: _free_sram_ctrl(dut))
    for _ in range(40):
        await run.step()
    return {"rows": run.rows, "t_rst": t_rst, "t_rst2": t_rst2, "t_up": up["cyc"],
            "t_iso": iso_row["cyc"], "accepted": accepted, "run": run}


async def _gif_scenario_early_r(dut, free_lead: int) -> dict:
    """AR accepted while the GPU is on, with the R beat held back by the SRAM controller. The
    controller is freed free_lead cycles before the PMU gets the power-down request, so the R beat
    arrives in the cycle after the clock gate closed, before the clamp and the reset."""
    run = await _gif_held_start(dut)
    run.later(lambda: _release_block(dut))
    run.later(lambda: _hold_sram_ctrl(dut))
    await run.until(lambda r: r["m_arv"] and r["m_arr"], 16, "AR accepted")
    run.later(lambda: _free_sram_ctrl(dut))
    for _ in range(free_lead):
        await run.step()
    run.later(lambda: _mode_now(dut, MODE_GPU_OFF))
    first_rst = await run.until(lambda r: r["rst_n"] == 0, 400, "GPU domain reset")
    for _ in range(24):
        await run.step()
    up = await _gif_power_up(run)
    for _ in range(40):
        await run.step()
    return {"rows": run.rows, "t_rst": first_rst["cyc"], "t_up": up["cyc"], "run": run}


async def _gif_scenario_no_reset(dut) -> dict:
    """Control: the same held AR, released while the GPU stays powered. No PMU action."""
    run = await _gif_held_start(dut)
    held_addr = run.rows[-1]["m_addr"]
    run.later(lambda: _release_block(dut))
    await run.until(lambda r: r["m_arv"] and r["m_arr"], 16, "held AR accepted")
    for _ in range(GIF_KERNEL_WINDOW):
        await run.step()
    return {"rows": run.rows, "hold_idx": run.hold_idx, "held_addr": held_addr}


async def _gif_scenario_idle_cycle(dut) -> dict:
    """Control: a GPU power cycle with no fetch in flight. The firmware runs the kernel to its end,
    then power-cycles the GPU through the PMU and launches again."""
    await _setup(dut, GIF_CPU_NS, rom_words=_read_hex_words(GIF_FW_HEX))
    run = _GifRun(dut)
    await run.until(lambda r: r["irq"] == 1, GIF_LAUNCH_TIMEOUT + 20_000, "first kernel done")
    first = len(run.rows)
    await run.until(
        lambda r: r["gpu_aw"] and r["gpu_awaddr"] == 0, GIF_RELAUNCH_TIMEOUT, "second launch"
    )
    return {"rows": run.rows[first:]}


def _end_pc(row: dict, pass_pc: int, fail_pc: int):
    """The PASS or FAIL pc committed since the previous sample, or None."""
    return next((pc for pc in row["commits"] if pc in (pass_pc, fail_pc)), None)


async def _gif_scenario_relaunch(dut, kind: str) -> dict:
    """A power cycle as in scenario kind, then the relaunch image runs kernel 2 to the end."""
    words, pass_pc, fail_pc = _gif_relaunch_image()
    if kind == "held":
        res = await _gif_scenario_held_ar(dut, rom_words=words)
    elif kind == "rflight":
        res = await _gif_scenario_r_in_flight(dut, rom_words=words)
    elif kind == "late":
        res = await _gif_scenario_r_in_flight(dut, rom_words=words, late_r=True)
    else:
        res = await _gif_scenario_r_in_flight(dut, rom_words=words, cycles=2)
    run = res["run"]
    for _ in range(GIF_RELAUNCH_TIMEOUT):
        end_pc = _end_pc(await run.step(), pass_pc, fail_pc)
        if end_pc is not None:
            break
    else:
        raise RuntimeError("harness: the relaunch image reached neither PASS nor FAIL")
    res["pass"] = end_pc == pass_pc
    mem = sram_mem(dut)
    res["result"] = [int(mem[GIF_RESULT_WORD + lane].value) for lane in range(8)]
    return res


def _gif_contention_image() -> tuple:
    """Return (ROM words, PASS pc, FAIL pc) of the contention image: the kernel is launched, then
    the CPU alternates stores and loads on two aliases of the same SRAM words. They map to one
    D-cache set, so every access is a miss with a write-back and a refill on the crossbar SRAM
    slave while the GPU fetches from the same slave. Each load must return the stored value.
    The image then polls GPU STATUS over MMIO until the done bit is set."""
    if "contention" in _GIF_CACHE:
        return _GIF_CACHE["contention"]
    from tb.cocotb.soc.integ_fw import gen_integ_hex as gen

    gi = gen.gpuirq
    asm = gen.Assembler(origin=gen.ROM_BASE)
    gen.trampoline(asm)
    asm.label("MAIN")
    gen.li(asm, 3, gi.SRC_BASE)
    gen.li(asm, 5, gi.KERNEL_PC)
    gen.li(asm, 6, gen.GPU_BASE)
    for i in range(gi.N_SRC_WORDS):
        asm.emit(gen.ADDI(7, 0, (i + 1) * GIF_RESULT_SCALE))
        asm.emit(gen.SW(7, 3, i * 4))
    gen.flush_dcache(asm, "FL1")
    for i, kw in enumerate(gi.build_gpu_kernel()):
        gen.li(asm, 7, kw)
        asm.emit(gen.SW(7, 5, i * 4))
    gen.flush_dcache(asm, "FL2")
    asm.emit(gen.LW(7, 6, gi.GPU_OFF_CTRL))
    asm.emit(gen.SW(5, 6, gi.GPU_OFF_KERNEL_PC))
    asm.emit(gen.ADDI(7, 0, 1))
    for off in (gi.GPU_OFF_GRID_X, gi.GPU_OFF_GRID_Y, gi.GPU_OFF_GRID_Z,
                gi.GPU_OFF_BLOCK_Y, gi.GPU_OFF_BLOCK_Z):
        asm.emit(gen.SW(7, 6, off))
    asm.emit(gen.ADDI(7, 0, 8))
    asm.emit(gen.SW(7, 6, gi.GPU_OFF_BLOCK_X))
    asm.emit(gen.ADDI(7, 0, 0x05))
    asm.emit(gen.SW(7, 6, gi.GPU_OFF_CTRL))
    gen.li(asm, 12, GIF_HAMMER_A)
    gen.li(asm, 13, GIF_HAMMER_B)
    asm.emit(gen.ADDI(24, 0, 0))
    gen.li(asm, 25, GIF_HAMMER_LOOPS)
    asm.label("HAMMER")
    asm.emit(gen.SW(24, 12, 0))
    asm.emit(gen.LW(26, 13, 0))
    gen.br(asm, gen.BNE, 26, 24, "FAIL")
    asm.emit(gen.SW(24, 13, 4))
    asm.emit(gen.LW(27, 12, 4))
    gen.br(asm, gen.BNE, 27, 24, "FAIL")
    asm.emit(gen.ADDI(24, 24, 1))
    gen.br(asm, gen.BNE, 24, 25, "HAMMER")
    gen.li(asm, 20, GIF_STATUS_POLLS)
    asm.emit(gen.ADDI(21, 0, 0))
    asm.label("GDONE_POLL")
    asm.emit(gen.LW(22, 6, gi.GPU_OFF_STATUS))
    asm.emit(gen.ANDI(22, 22, GIF_STATUS_DONE))
    gen.br(asm, gen.BNE, 22, 0, "GDONE_GOT")
    asm.emit(gen.ADDI(21, 21, 1))
    gen.br(asm, gen.BNE, 21, 20, "GDONE_POLL")
    gen.jmp(asm, "FAIL")
    asm.label("GDONE_GOT")
    gen.jmp(asm, "PASS")
    gen.tail(asm)
    words = asm.resolve()
    assert len(words) <= gen.ROM_WORDS
    image = (words + [gen.NOP] * (gen.ROM_WORDS - len(words)), asm.labels["PASS"],
             asm.labels["FAIL"])
    _GIF_CACHE["contention"] = image
    return image


async def _gif_scenario_contention(dut) -> dict:
    """The GPU kernel runs while the CPU thrashes the SRAM slave. No backdoor on the bus."""
    words, pass_pc, fail_pc = _gif_contention_image()
    await _setup(dut, GIF_CPU_NS, rom_words=words)
    run = _GifRun(dut)
    for _ in range(GIF_CONTENTION_TIMEOUT):
        end_pc = _end_pc(await run.step(), pass_pc, fail_pc)
        if end_pc is not None:
            break
    else:
        raise RuntimeError(
            f"harness: the contention image reached neither PASS nor FAIL in "
            f"{GIF_CONTENTION_TIMEOUT} cycles"
        )
    mem = sram_mem(dut)
    return {"rows": run.rows, "pass": end_pc == pass_pc,
            "result": [int(mem[GIF_RESULT_WORD + lane].value) for lane in range(8)]}


async def _gif_cached(dut, key: str, fn) -> dict:
    if key not in _GIF_CACHE:
        _GIF_CACHE[key] = await with_timeout(fn(dut), 3000, "us")
        await RisingEdge(dut.clk_i)  # leave the read-only phase
    return _GIF_CACHE[key]


def _first(rows, pred):
    return next((r for r in rows if pred(r)), None)


def _check_held(res) -> None:
    rows, t_rst = res["rows"], res["t_rst"]
    bad = [r for r in rows if r["rst_n"] == 0 and r["m_arv"]]
    assert not bad, f"m_axi_arvalid high in {len(bad)} cycles with gpu_domain_rst_n low"
    hs = [r for r in rows[t_rst:] if r["m_arv"] and r["m_arr"]]
    assert not hs, f"{len(hs)} AR handshake(s) after the GPU reset asserted at cycle {t_rst}"
    shown = [r for r in rows[t_rst:] if r["rv"]]
    assert not shown, f"R valid shown to the GPU in {len(shown)} cycles after its reset"


def _check_r_in_flight(res) -> None:
    rows, t_rst = res["rows"], res["t_rst"]
    off = [r for r in rows[t_rst:] if r["rst_n"] == 0 and r["iso"] == 1]
    assert len(off) >= 16, f"harness: only {len(off)} cycles with the GPU off"
    locked = [r for r in off[8:] if r["rstate"] != XBAR_R_IDLE]
    assert not locked, f"SRAM read engine busy in {len(locked)} cycles of the GPU-off window"
    shown = [r for r in rows[t_rst:] if r["rv"]]
    assert not shown, f"R valid shown to the GPU in {len(shown)} cycles after its reset"


# Scenario 1: held AR across a GPU domain reset.
@cocotb.test()
async def test_gif_held_ar_not_driven_in_gpu_reset(dut):
    """Required: while gpu_domain_rst_n is low the GPU fetch adapter does not drive m_axi_arvalid.
    The GPU fetch AR waits at the adapter because the crossbar is busy for another master. The
    PMU then powers the GPU domain off. A request of the old GPU must not outlive its reset."""
    res = await _gif_cached(dut, "held", _gif_scenario_held_ar)
    bad = [r for r in res["rows"] if r["rst_n"] == 0 and r["m_arv"]]
    assert not bad, (
        f"m_axi_arvalid still high in {len(bad)} cycles with gpu_domain_rst_n low "
        f"(first at cycle {bad[0]['cyc']}, reset asserted at {res['t_rst']}, "
        f"araddr {bad[0]['m_addr']:#x})"
    )


@cocotb.test()
async def test_gif_held_ar_never_reaches_crossbar_after_gpu_reset(dut):
    """Required: no AR handshake on the GPU fetch master after the GPU domain reset asserts. The
    crossbar is released while the GPU is still in reset; an AR of the old GPU that the adapter
    kept would be accepted then."""
    res = await _gif_cached(dut, "held", _gif_scenario_held_ar)
    hs = [r for r in res["rows"][res["t_rst"] :] if r["m_arv"] and r["m_arr"]]
    assert not hs, (
        f"{len(hs)} AR handshake(s) on the GPU fetch master after the GPU reset asserted at cycle "
        f"{res['t_rst']}: first at cycle {hs[0]['cyc']}, araddr {hs[0]['m_addr']:#x}"
    )


@cocotb.test()
async def test_gif_held_ar_no_r_beat_for_new_gpu(dut):
    """Required: after the GPU reset releases, the new GPU receives no R beat on the fetch port,
    because it has issued no fetch. A beat is a handshake of gif_axil_rvalid and gif_axil_rready
    after the reset."""
    res = await _gif_cached(dut, "held", _gif_scenario_held_ar)
    beats = [r for r in res["rows"][res["t_rst"] :] if r["rv"] and r["rr"]]
    assert not beats, (
        f"{len(beats)} unrequested R beat(s) reached the GPU after its reset (reset asserted at "
        f"cycle {res['t_rst']}, first beat at cycle {beats[0]['cyc']}, "
        f"gpu_domain_rst_n={beats[0]['rst_n']})"
    )


# Scenario 2: AR accepted, R in flight at the reset.
@cocotb.test()
async def test_gif_r_in_flight_does_not_lock_crossbar_while_gpu_off(dut):
    """Required: with an R beat in flight at the GPU reset, the crossbar read engine of the target
    slave is idle again while the GPU is still off. The beat is the response to a fetch that no
    GPU waits for; the engine must not hold the slave until the GPU powers up (any other master
    reading that slave would stall)."""
    res = await _gif_cached(dut, "rflight", _gif_scenario_r_in_flight)
    off = [r for r in res["rows"][res["t_rst"] :] if r["rst_n"] == 0 and r["iso"] == 1]
    assert len(off) >= 16, f"harness: only {len(off)} cycles with the GPU off"
    late = off[8:]
    locked = [r for r in late if r["rstate"] != XBAR_R_IDLE]
    assert not locked, (
        f"crossbar SRAM read engine busy (state {locked[0]['rstate']}) in {len(locked)} of "
        f"{len(late)} cycles of the GPU-off window, from cycle {locked[0]['cyc']} "
        f"(reset asserted at {res['t_rst']})"
    )


@cocotb.test()
async def test_gif_r_in_flight_no_r_beat_for_new_gpu(dut):
    """Required: after the GPU reset releases, the new GPU receives no R beat for the fetch of the
    old GPU that was in flight at the reset."""
    res = await _gif_cached(dut, "rflight", _gif_scenario_r_in_flight)
    beats = [r for r in res["rows"][res["t_rst"] :] if r["rv"] and r["rr"]]
    assert not beats, (
        f"{len(beats)} unrequested R beat(s) reached the GPU after its reset (reset asserted at "
        f"cycle {res['t_rst']}, first beat at cycle {beats[0]['cyc']}, "
        f"gpu_domain_rst_n={beats[0]['rst_n']}, isolation={beats[0]['iso']})"
    )


# Controls: the harness sees what the scenario tests rely on, and the rules hold when no reset
# or no fetch is in the way.
@cocotb.test()
async def test_gif_control_held_ar_without_reset_completes(dut):
    """Control for both scenarios: with no GPU reset, the AR that waits at the adapter keeps its
    address and valid, is accepted exactly once when the crossbar is released, its R beat reaches
    the GPU and the read engine returns to idle."""
    res = await _gif_cached(dut, "noreset", _gif_scenario_no_reset)
    rows, hold_idx, addr = res["rows"], res["hold_idx"], res["held_addr"]
    first_hs = next(i for i in range(hold_idx, len(rows)) if rows[i]["m_arv"] and rows[i]["m_arr"])
    held = rows[hold_idx:first_hs]
    assert len(held) >= GIF_HOLD_CYCLES
    assert all(r["m_arv"] and not r["m_arr"] and r["m_addr"] == addr for r in held), (
        "the held AR changed or dropped before it was accepted"
    )
    assert rows[first_hs]["m_addr"] == addr
    # The kernel runs on and fetches again, so the R beat of the held address is the first beat
    # after its AR handshake and the one before the next AR handshake.
    assert not any(r["rv"] and r["rr"] for r in rows[hold_idx:first_hs]), (
        "an R beat arrived before the held AR was accepted"
    )
    next_hs = next(
        (i for i in range(first_hs + 1, len(rows)) if rows[i]["m_arv"] and rows[i]["m_arr"]),
        len(rows),
    )
    beats = [r for r in rows[first_hs:next_hs] if r["rv"] and r["rr"]]
    assert len(beats) == 1, f"{len(beats)} R beats for the held AR, expected 1"
    assert rows[-1]["rstate"] == XBAR_R_IDLE
    assert all(r["rst_n"] == 1 for r in rows[hold_idx:next_hs]), "harness: the GPU was reset"


@cocotb.test()
async def test_gif_control_gpu_reset_without_fetch_in_flight_is_clean(dut):
    """Control for both scenarios: a PMU power cycle of the idle GPU (kernel finished, no fetch in
    flight) leaves no AR valid, no AR handshake and no R beat on the fetch port, and the crossbar
    read engine stays idle."""
    res = await _gif_cached(dut, "idle", _gif_scenario_idle_cycle)
    rows = res["rows"]
    assert _first(rows, lambda r: r["rst_n"] == 0), "harness: the GPU was not reset"
    assert _first(rows, lambda r: r["st"] == DOM_OFF), "harness: the GPU domain never reached OFF"
    # The kernel's last fetch is over once the interrupt is raised; look from two cycles later.
    win = rows[2:]
    assert not [r for r in win if r["m_arv"] or r["m_arr"] or r["rv"]], (
        "fetch-port activity during the idle power cycle"
    )
    assert all(r["rstate"] == XBAR_R_IDLE for r in win)


@cocotb.test()
async def test_gif_control_r_in_flight_window_is_reached(dut):
    """Control for scenario 2: the harness reaches the state the scenario 2 tests need, and the
    adapter handles it. The AR is accepted with the isolation clamp active and the GPU reset still
    released. The R beat of that fetch then becomes valid at the crossbar while the GPU is off. The
    adapter takes that beat itself; the GPU port never shows it."""
    res = await _gif_cached(dut, "rflight", _gif_scenario_r_in_flight)
    rows = res["rows"]
    acc = res["accepted"][0]
    assert acc["iso"] == 1 and acc["rst_n"] == 1 and acc["m_arr"] == 1
    taken = _first(rows[acc["cyc"] + 1 :], lambda r: r["m_rv"] and r["m_rr"])
    if taken is None:
        raise RuntimeError("harness: the R beat of the accepted AR never reached the adapter")
    assert taken["cyc"] > acc["cyc"]
    assert _gpu_off(taken), f"the R beat was taken at cycle {taken['cyc']} with the GPU on"
    shown = [r for r in rows[acc["cyc"] :] if r["rv"]]
    assert not shown, f"R valid shown to the GPU in {len(shown)} cycles, first at {shown[0]['cyc']}"
    assert rows[-1]["rstate"] == XBAR_R_IDLE


# Power-down sequence variants. The PMU has no state that gates the GPU clock and leaves the GPU
# out of reset (see the PMU sequencer chain), so a stale fetch can only be met in a full cycle.
@cocotb.test()
async def test_gif_wake_during_power_down_still_resets_and_drains(dut):
    """Software requests NORMAL one cycle after GPU_OFF. The PMU does not reverse the power-down:
    the clock gate closes, the clamp rises and the reset asserts for at least one cycle. The R beat
    in flight is taken by the adapter and never shown to the GPU, and the read engine is idle after.
    Every closing of the clock gate is followed by a reset before the clock opens again."""
    res = await _gif_cached(
        dut, "wake", lambda d: _gif_scenario_r_in_flight(d, wake_early=True)
    )
    rows, t_rst = res["rows"], res["t_rst"]
    assert rows[t_rst]["rst_n"] == 0
    assert _first(rows, lambda r: r["st"] == DOM_OFF), "the aborted power-down never reached OFF"
    shown = [r for r in rows[res["accepted"][0]["cyc"] :] if r["rv"]]
    assert not shown, f"R valid shown to the GPU in {len(shown)} cycles"
    assert rows[-1]["rstate"] == XBAR_R_IDLE
    assert rows[-1]["st"] == DOM_ON
    gated_without_reset = False
    seen_reset = True
    for prev, cur in zip(rows, rows[1:]):
        if prev["clk_en"] and not cur["clk_en"]:
            seen_reset = False
        if not cur["rst_n"]:
            seen_reset = True
        if not prev["clk_en"] and cur["clk_en"] and not seen_reset:
            gated_without_reset = True
    assert not gated_without_reset, "the GPU clock gate closed and opened with no GPU reset between"


@cocotb.test()
async def test_gif_r_beat_after_gpu_power_up_is_drained(dut):
    """The SRAM controller refuses the AR, so the R beat of the old GPU comes only after the GPU
    is back on and out of reset. The adapter still takes it: the new GPU sees no R valid, and the
    read engine is idle after."""
    res = await _gif_cached(dut, "late", lambda d: _gif_scenario_r_in_flight(d, late_r=True))
    rows, t_up = res["rows"], res["t_up"]
    beat = _first(rows[t_up:], lambda r: r["m_rv"] and r["m_rr"])
    if beat is None:
        raise RuntimeError("harness: the late R beat did not arrive after the GPU power-up")
    assert beat["st"] == DOM_ON and not _gpu_off(beat)
    shown = [r for r in rows[res["accepted"][0]["cyc"] :] if r["rv"]]
    assert not shown, f"R valid shown to the GPU in {len(shown)} cycles, first at {shown[0]['cyc']}"
    assert rows[-1]["rstate"] == XBAR_R_IDLE


# free_lead places the arrival of the R beat in the window of a closed clock gate and a released
# reset.
GIF_EARLY_FREE_LEAD = 1


@cocotb.test()
async def test_gif_r_beat_while_gpu_clock_gated_is_not_presented(dut):
    """An R beat that arrives after the GPU clock gate closed and before its reset asserts is taken
    by the adapter and is not presented to the GPU. The off level of the adapter includes the clock
    gate, so the drain starts there and not only at the reset."""
    res = await _gif_cached(
        dut, "early",
        lambda d: _gif_scenario_early_r(d, GIF_EARLY_FREE_LEAD),
    )
    rows, t_rst = res["rows"], res["t_rst"]
    beat = _first(rows, lambda r: r["m_rv"] and r["m_rr"] and not r["clk_en"] and r["rst_n"])
    if beat is None:
        raise RuntimeError("harness: no R beat arrived with the clock gated and the reset released")
    assert beat["cyc"] < t_rst
    shown = [r for r in rows if not r["clk_en"] and r["rv"]]
    assert not shown, f"R valid shown to the GPU in {len(shown)} cycles with its clock gated"
    assert rows[-1]["rstate"] == XBAR_R_IDLE


# Relaunch: after a power cycle with a stale fetch, a new kernel completes with correct data.
def _check_relaunch(res) -> None:
    assert res["pass"], "the relaunch image reached FAIL: the second kernel did not complete"
    want = [(lane + 1) * GIF_RESULT_SCALE + 1 for lane in range(8)]
    assert res["result"] == want, f"second kernel result {res['result']}, expected {want}"
    after = res["rows"][res["t_up"] :]
    n_ar = len([r for r in after if r["m_arv"] and r["m_arr"]])
    n_beats = len([r for r in after if r["rv"] and r["rr"]])
    assert n_ar > 0 and n_beats == n_ar, (
        f"{n_beats} R beats reached the GPU for {n_ar} fetches of the new GPU after power-up"
    )
    assert res["rows"][-1]["rstate"] == XBAR_R_IDLE


@cocotb.test()
async def test_gif_relaunch_after_held_ar_cycle(dut):
    """Scenario 1, then the second kernel completes with the right data and every fetch of the new
    GPU gets exactly one R beat."""
    _check_relaunch(await _gif_cached(dut, "rl_held", lambda d: _gif_scenario_relaunch(d, "held")))


@cocotb.test()
async def test_gif_relaunch_after_r_in_flight_cycle(dut):
    """Scenario 2, then the second kernel completes with the right data and no stale state is left
    in the adapter."""
    _check_relaunch(
        await _gif_cached(dut, "rl_rflight", lambda d: _gif_scenario_relaunch(d, "rflight"))
    )


@cocotb.test()
async def test_gif_relaunch_after_late_r_beat(dut):
    """The old fetch's R beat arrives after the power-up; the second kernel still completes with the
    right data."""
    _check_relaunch(await _gif_cached(dut, "rl_late", lambda d: _gif_scenario_relaunch(d, "late")))


@cocotb.test()
async def test_gif_relaunch_after_back_to_back_power_cycles(dut):
    """Two GPU power cycles with no idle gap, the first with an R beat in flight. Both resets
    assert, no R valid reaches the GPU, and the second kernel completes with the right data."""
    res = await _gif_cached(dut, "rl_b2b", lambda d: _gif_scenario_relaunch(d, "b2b"))
    assert res["t_rst2"] is not None and res["t_rst2"] > res["t_rst"]
    assert res["rows"][res["t_rst2"]]["rst_n"] == 0
    window = res["rows"][res["t_rst"] : res["t_up"]]
    assert not [r for r in window if r["rv"]], "R valid shown to the GPU during the two cycles"
    _check_relaunch(res)


# Both scenarios with the CPU clock slower than the fabric clock.
@cocotb.test()
async def test_gif_stale_fetch_cases_with_cpu_slower_than_fabric(dut):
    """Scenario 1 and scenario 2 with the CPU clock slower than the fabric clock: the same rules
    hold on the GPU fetch path, which stays in the fabric clock domain."""
    held = await _gif_cached(
        dut, "held_slow", lambda d: _gif_scenario_held_ar(d, GIF_SLOW_CPU_NS)
    )
    _check_held(held)
    rflight = await _gif_cached(
        dut, "rflight_slow", lambda d: _gif_scenario_r_in_flight(d, GIF_SLOW_CPU_NS)
    )
    _check_r_in_flight(rflight)


@cocotb.test()
async def test_gif_held_ar_fetch_not_lost_kernel_completes(dut):
    """Required: a GPU fetch whose AR waits at the adapter because the crossbar is busy is not lost.
    After the crossbar is released the GPU continues and the kernel runs to its end. The GPU
    compute unit records the fetch in its issue cycle and keeps ARVALID and the address until
    arready. No GPU reset is involved in this test."""
    res = await _gif_cached(dut, "noreset", _gif_scenario_no_reset)
    rows = res["rows"][res["hold_idx"] :]
    assert _first(rows, lambda r: r["irq"] == 1), (
        f"the GPU kernel did not finish within {GIF_KERNEL_WINDOW} cycles after the held AR was "
        f"accepted; AR handshakes after the held one: "
        f"{len([r for r in rows if r['m_arv'] and r['m_arr']]) - 1}"
    )


@cocotb.test()
async def test_gif_kernel_completes_under_sram_contention(dut):
    """The CPU thrashes the SRAM slave with D-cache misses on two aliases of the same words while
    the GPU kernel fetches from that slave. The fetch AR waits at the adapter for the crossbar,
    stays valid with its address on the GPU side, every AR gets one R beat, the CPU reads back
    what it stored and the kernel result is right. After the hammer loop the CPU reads GPU STATUS
    over MMIO and sees the done bit, so the read path to the GPU register slave is live."""
    from tb.cocotb.soc.integ_fw import gen_integ_hex as gen

    res = await _gif_cached(dut, "contention", _gif_scenario_contention)
    rows = res["rows"]
    assert res["pass"], "the contention image reached FAIL: a read-back or the STATUS poll failed"
    irq = _first(rows, lambda r: r["irq"] == 1)
    assert irq, "the GPU kernel did not finish (no done IRQ)"
    status_reads = [r for r in rows if r["gpu_ar"] and r["gpu_araddr"] == gen.gpuirq.GPU_OFF_STATUS]
    assert status_reads and status_reads[-1]["cyc"] > irq["cyc"], (
        "no CPU read of GPU STATUS reached the GPU slave after the done IRQ"
    )
    want = [(lane + 1) * GIF_RESULT_SCALE + 1 for lane in range(8)]
    assert res["result"] == want, f"kernel result {res['result']}, expected {want}"
    waits_gpu = [r for r in rows if r["al_arv"] and not r["al_arr"]]
    waits_xbar = [r for r in rows if r["m_arv"] and not r["m_arr"]]
    if not waits_gpu or not waits_xbar:
        raise RuntimeError(
            f"harness: no contention reached (GPU AR waits {len(waits_gpu)}, "
            f"crossbar AR waits {len(waits_xbar)})"
        )
    dut._log.info(f"AR wait cycles: GPU side {len(waits_gpu)}, crossbar side {len(waits_xbar)}")
    for prev, cur in zip(rows, rows[1:]):
        if prev["al_arv"] and not prev["al_arr"]:
            assert cur["al_arv"] and cur["al_addr"] == prev["al_addr"], (
                f"the GPU AR was withdrawn or changed before arready in cycle {cur['cyc']}"
            )
    ars = sum(1 for r in rows if r["al_arv"] and r["al_arr"])
    beats = sum(1 for r in rows if r["rv"] and r["rr"])
    assert ars == beats and ars > 0, f"{ars} GPU AR handshakes, {beats} R beats"


# ---------------------------------------------------------------------------------------------
# Wake of the CPU domain on the timer interrupt, through the real path. The firmware enables the
# timer wake and a DMA copy writes CPU_OFF into CTRL, so no test code writes CTRL. The control test
# proves the power-down and the timer.
# ---------------------------------------------------------------------------------------------
WAKE_CPU_NS = 5
WAKE_TIMER_COMPARE = (
    2500  # fabric cycles from the timer enable, long after the DMA-driven power-down
)
WAKE_VAR_WI = 400  # SRAM word of the firmware variables, clear of the DMA window
WAKE_W_CTRLVAL, WAKE_W_COUNT, WAKE_W_MCAUSE, WAKE_W_BOOTED = 0, 4, 8, 12
WAKE_MAGIC = 0x5A5A_C3C3
WAKE_LOOP = 128
WAKE_PMU_WAKE_EN, WAKE_PMU_STATUS, WAKE_PMU_STATUS_CLR = 0x10, 0x04, 0x0C
WAKE_SOC_TIMEOUT = 60_000
WAKE_SOC_ON_WINDOW = 400  # fabric cycles from the timer interrupt to the CPU domain ON
_WAKE_CACHE: dict = {}


def _wake_image() -> tuple:
    """(ROM words, PASS pc, FAIL pc). MAIN writes the variables and flushes the D-cache, enables the
    timer wake, starts the timer and the DMA copy of CPU_OFF into PMU CTRL, and waits in a loop of
    register instructions. The CPU is stopped there. After the wake (a resume, or a boot that sees
    the booted marker) it enables the timer interrupt, waits for the handler, then checks mcause,
    STATUS[4] and the STATUS_CLR[1] clear."""
    if "image" in _WAKE_CACHE:
        return _WAKE_CACHE["image"]
    from tb.cocotb.soc.integ_fw import gen_integ_hex as gen

    var_base = gen.SRAM_BASE + WAKE_VAR_WI * 4
    asm = gen.Assembler(origin=gen.ROM_BASE)
    gen.trampoline(asm)
    asm.label("ISR")
    gen.li(asm, 24, gen.TIMER_BASE)
    asm.emit(gen.ADDI(25, 0, 4))
    asm.emit(gen.SW(25, 24, 0x08))  # timer CTRL: clear the pending interrupt, disable
    gen.li(asm, 29, var_base)
    asm.emit(gen.CSRRS(28, 0x342, 0))
    asm.emit(gen.SW(28, 29, WAKE_W_MCAUSE))
    asm.emit(gen.LW(25, 29, WAKE_W_COUNT))
    asm.emit(gen.ADDI(25, 25, 1))
    asm.emit(gen.SW(25, 29, WAKE_W_COUNT))
    asm.emit(gen.MRET())
    asm.pad_to_word(40)

    asm.label("MAIN")
    gen.li(asm, 2, var_base)
    gen.li(asm, 3, gen.TIMER_BASE)
    gen.li(asm, 5, gen.DMA_BASE)
    gen.li(asm, 6, gen.PMU_BASE)
    gen.li(asm, 9, WAKE_MAGIC)
    asm.emit(gen.LW(8, 2, WAKE_W_BOOTED))
    gen.br(asm, gen.BEQ, 8, 9, "RESUME")
    asm.emit(gen.ADDI(8, 0, 1))
    asm.emit(gen.SW(8, 2, WAKE_W_CTRLVAL))  # CPU_OFF, the word the DMA copies
    asm.emit(gen.SW(0, 2, WAKE_W_COUNT))
    asm.emit(gen.SW(0, 2, WAKE_W_MCAUSE))
    asm.emit(gen.SW(9, 2, WAKE_W_BOOTED))
    gen.flush_dcache(asm, "FL1")
    asm.emit(gen.ADDI(8, 0, 2))
    asm.emit(gen.SW(8, 6, WAKE_PMU_WAKE_EN))  # WAKE_EN[1]: wake on the timer
    gen.li(asm, 8, WAKE_TIMER_COMPARE)
    asm.emit(gen.SW(8, 3, 0x04))
    asm.emit(gen.SW(0, 3, 0x0C))
    asm.emit(gen.SW(2, 5, 0))  # DMA SRC = the CTRL value word
    asm.emit(gen.SW(6, 5, 4))  # DMA DST = PMU CTRL
    asm.emit(gen.ADDI(8, 0, 4))
    asm.emit(gen.SW(8, 5, 8))
    asm.emit(gen.ADDI(10, 0, 3))  # timer CTRL: enable and irq_en
    asm.emit(gen.ADDI(11, 0, 1))  # DMA CTRL: start
    asm.emit(gen.ADDI(13, 0, 0))
    gen.li(asm, 14, WAKE_LOOP)
    words_so_far = sum(1 for t_, _ in asm._items if t_ != "label")
    asm.pad_to_word((words_so_far + 3) // 4 * 4)  # START and LOOP share one instruction cache line
    asm.emit(gen.SW(10, 3, 0x08))
    asm.emit(gen.SW(11, 5, 0x0C))
    asm.label("LOOP")
    asm.emit(gen.ADDI(13, 13, 1))
    gen.br(asm, gen.BNE, 13, 14, "LOOP")

    asm.label("RESUME")
    gen.li(asm, 1, gen.ROM_BASE + 4)
    asm.emit(gen.CSRRW(0, 0x305, 1))  # mtvec
    asm.emit(gen.ADDI(1, 0, 0x80))
    asm.emit(gen.CSRRW(0, 0x304, 1))  # mie.MTIE
    asm.emit(gen.ADDI(1, 0, 8))
    asm.emit(gen.CSRRW(0, 0x300, 1))  # mstatus.MIE
    gen.li(asm, 20, gen.POLL_LIMIT)
    asm.emit(gen.ADDI(21, 0, 0))
    asm.label("POLL")
    asm.emit(gen.LW(22, 2, WAKE_W_COUNT))
    gen.br(asm, gen.BNE, 22, 0, "GOT")
    asm.emit(gen.ADDI(21, 21, 1))
    gen.br(asm, gen.BNE, 21, 20, "POLL")
    gen.jmp(asm, "FAIL")
    asm.label("GOT")
    gen.expect_word(asm, 2, WAKE_W_COUNT, 1)
    gen.expect_word(asm, 2, WAKE_W_MCAUSE, gen.MCAUSE_MTI)
    asm.emit(gen.LW(10, 6, WAKE_PMU_STATUS))
    asm.emit(gen.ANDI(10, 10, 0x10))
    gen.br(asm, gen.BEQ, 10, 0, "FAIL")  # STATUS[4] must record the wake
    asm.emit(gen.ADDI(10, 0, 2))
    asm.emit(gen.SW(10, 6, WAKE_PMU_STATUS_CLR))  # STATUS_CLR[1]
    asm.emit(gen.LW(10, 6, WAKE_PMU_STATUS))
    asm.emit(gen.ANDI(10, 10, 0x10))
    gen.br(asm, gen.BNE, 10, 0, "FAIL")
    gen.jmp(asm, "PASS")
    gen.tail(asm)
    words = asm.resolve()
    assert len(words) <= gen.ROM_WORDS
    image = (
        words + [gen.NOP] * (gen.ROM_WORDS - len(words)),
        asm.labels["PASS"],
        asm.labels["FAIL"],
    )
    _WAKE_CACHE["image"] = image
    return image


async def _wake_soc_run(dut, through: str) -> dict:
    """Boot the wake image and watch the CPU domain. through is "irq" (stop at the timer interrupt)
    or "end" (also wait for the CPU domain ON and the PASS or FAIL marker). No test writes CTRL.
    Returns cycle numbers of off, irq, on, the end pc, and CTRL when the CPU domain was OFF."""
    words, pass_pc, fail_pc = _wake_image()
    mem = sram_mem(dut)
    for w_ in range(4):
        mem[WAKE_VAR_WI + w_].value = 0  # SRAM keeps the booted marker of an earlier run
    await _setup(dut, WAKE_CPU_NS, rom_words=words)
    run = _GifRun(dut)
    soc = _soc(dut)
    ev: dict = dict(off=None, irq=None, on=None, end=None, ctrl_off=None, pass_pc=pass_pc)
    for _ in range(WAKE_SOC_TIMEOUT):
        row = await run.step()
        cyc = row["cyc"]
        state = int(soc.u_pmu.dom_state_q[DOM_CPU].value)
        if ev["off"] is None and state == DOM_OFF:
            ev["off"], ev["ctrl_off"] = cyc, int(soc.u_pmu.u_regbank.regs[0].value)
        if ev["irq"] is None and int(soc.timer_irq.value):
            ev["irq"] = cyc
            if through == "irq":
                break
        if ev["irq"] is not None and ev["on"] is None:
            if state == DOM_ON and ev["off"] is not None:
                ev["on"] = cyc
            elif cyc - ev["irq"] > WAKE_SOC_ON_WINDOW:
                break
        end = _end_pc(row, pass_pc, fail_pc)
        if end is not None:
            ev["end"] = end
            break
    ev["ctrl_end"] = int(soc.u_pmu.u_regbank.regs[0].value)
    return ev


def _wake_check_stimulus(ev: dict) -> None:
    if ev["off"] is None:
        raise RuntimeError(
            "harness: the firmware did not power the CPU domain down through the DMA"
        )
    if ev["ctrl_off"] != MODE_CPU_OFF:
        raise RuntimeError(f"harness: CTRL was 0x{ev['ctrl_off']:x} when the CPU domain was OFF")
    if ev["irq"] is None:
        raise RuntimeError("harness: the timer interrupt never rose")
    if ev["irq"] <= ev["off"]:
        raise RuntimeError("harness: the timer interrupt rose before the CPU domain was OFF")


@cocotb.test()
async def test_wake_soc_control_firmware_powers_cpu_down_and_timer_fires_while_off(dut):
    """Control. The firmware powers the CPU domain down through the DMA with no backdoor write, and
    the timer interrupt rises while the domain is OFF. This is the stimulus of the wake test."""
    ev = await _wake_soc_run(dut, "irq")
    _wake_check_stimulus(ev)
    dut._log.info(f"CPU domain OFF at cycle {ev['off']}, timer irq at cycle {ev['irq']}")


@cocotb.test()
async def test_wake_soc_timer_irq_wakes_cpu_and_cpu_takes_it(dut):
    """The timer interrupt powers the CPU domain up with no write of CTRL, CTRL reads NORMAL, and
    the CPU takes the interrupt, checks mcause and STATUS[4], clears it by STATUS_CLR[1]: PASS."""
    ev = await _wake_soc_run(dut, "end")
    _wake_check_stimulus(ev)
    assert ev["on"] is not None, (
        f"the CPU domain was still not ON {WAKE_SOC_ON_WINDOW} cycles after the timer interrupt "
        f"(cycle {ev['irq']}, CTRL 0x{ev['ctrl_end']:x}): the PMU has no wake path"
    )
    assert ev["ctrl_end"] == MODE_NORMAL, (
        f"CTRL must read NORMAL after the wake, read 0x{ev['ctrl_end']:x}"
    )
    assert ev["end"] is not None, "the CPU did not reach the PASS or FAIL marker after the wake"
    assert ev["end"] == ev["pass_pc"], (
        "the CPU reached FAIL: mcause, STATUS[4] or the STATUS_CLR[1] clear"
    )
