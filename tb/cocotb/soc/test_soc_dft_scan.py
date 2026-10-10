"""
test_soc_dft_scan.py -- bead claude_verilog_test-j41m.2 (DFT Stage 1a), SoC level.

DUT: tb_soc_pll -> soc_top (PLL_IMPL=STUB). soc_top is exercised through its new
test-access ports (scan_mode_i, scan_en_i, scan_rst_ni, scan_clk_i, scan_in_i /
scan_out_o). What is OBSERVABLE at a port is checked at the port (pll_locked_o,
cpu_pll_locked_o, scan_out_o); what is internal is read through hierarchy
(--public-flat-rw is on for every suite in this Makefile).

What this proves, and what it does not:
  * PROVES  the test controls reach the right places: both PLL reference roots
    run on scan_clk_i in scan mode (functional clocks held stopped), the derived
    resets inside pll_subsystem follow the scan reset and ignore the functional
    pins, the CPU clock gate opens in scan mode while its functional enable is
    closed, gpu_domain_rst_n follows the scan reset, and the scan_out placeholder
    is a defined 0.
  * DOES NOT prove that EVERY async reset and clock in the netlist is
    controllable: that is an all-nets property and is checked structurally by
    tools/dft/check_scan_clk_rst.py on the synthesised netlist (see
    docs/design/DFT_ARCHITECTURE.md section 14).
  * Functional-mode bit-identity is established by the existing suites, which
    run with these ports tied inactive by soc_clocks.drive_dft_inactive().

Tests:
  test_functional_baseline_locks            scan ports inactive: both PLLs lock on clk_i
  test_scan_mode_runs_on_test_clk_only      scan mode, clk_i/cpu_clk_i STOPPED: PLL lock
                                            counters advance on scan_clk_i alone
  test_functional_clocks_ignored_in_scan    scan mode: toggling clk_i/cpu_clk_i moves nothing
  test_scan_reset_overrides_functional      scan mode: rst_n_i/cpu_rst_n_i low is ignored,
                                            scan_rst_ni low resets (async)
  test_internal_resets_follow_scan_reset    core/cpu_core/cpu_domain/gpu_domain resets
                                            equal scan_rst_ni in scan mode
  test_cpu_clock_gate_forced_open           cpu_gated_clk toggles in scan mode while the
                                            functional enable is 0
  test_scan_out_placeholder_is_zero         defined 0 until Stage 2 insertion
  test_exit_scan_restores_functional        scan_mode back to 0: functional reset works again
  test_scan_gpu_reset_with_pmu_gpu_off      PMU holds the GPU domain in reset (real CPU-firmware
                                            power-down), THEN scan mode: gpu_domain_rst_n must
                                            follow scan_rst_ni (j41m.9, mutant g)
  test_scan_cpu_reset_with_pmu_cpu_off      same for the CPU domain: PMU holds the CPU in reset
                                            (firmware -> DMA -> PMU CTRL), then scan mode:
                                            cpu_domain_rst_n must follow scan_rst_ni

The last two tests exist because every other reset check here runs with the PMU idle, where
the functional reset already equals scan_rst_ni and a mux that ignores scan mode is invisible
(j41m.9, mutant g). The PMU is driven by the same CPU-firmware path the PMU SoC suites use;
nothing is deposited on a net. scan_rst_ni stays 1 across scan entry so the PMU keeps its
power-down state (it is reset by core_rst_n, which equals scan_rst_ni in scan mode).
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge, Timer
from soc_clocks import drive_dft_inactive, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sim.riscv_encoder import ADDI, JAL, LUI, SW  # noqa: E402

PERIOD_NS = 10
LOCK_CYCLES = 16  # STUB_LOCK_CYCLES in soc_top


async def _toggle(sig, n, half_ns=5):
    """Toggle a (non-Clock()-managed) signal n full cycles by hand."""
    for _ in range(n):
        sig.value = 1
        await Timer(half_ns, units="ns")
        sig.value = 0
        await Timer(half_ns, units="ns")


async def _idle(dut):
    drive_dft_inactive(dut)
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    for name in ("apb_psel_i", "apb_penable_i", "apb_pwrite_i", "uart_rx_i", "spi_miso_i"):
        getattr(dut, name).value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0
    await Timer(2, units="ns")


@cocotb.test()
async def test_functional_baseline_locks(dut):
    """Scan ports inactive: the pre-DFT behaviour (both PLL stubs lock on clk_i)."""
    await _idle(dut)
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    cocotb.start_soon(Clock(dut.clk_i, PERIOD_NS, units="ns").start())
    cocotb.start_soon(Clock(dut.cpu_clk_i, PERIOD_NS, units="ns").start())
    await ClockCycles(dut.clk_i, 4)
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    await ClockCycles(dut.clk_i, LOCK_CYCLES + 6)
    assert int(dut.pll_locked_o.value) == 1
    assert int(dut.cpu_pll_locked_o.value) == 1


@cocotb.test()
async def test_scan_mode_runs_on_test_clk_only(dut):
    """Functional clocks stopped: the lock counters advance on scan_clk_i alone."""
    await _idle(dut)
    dut.scan_mode_i.value = 1
    dut.scan_rst_ni.value = 0  # hold every scan-controlled reset asserted
    await Timer(5, units="ns")
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0
    dut.scan_rst_ni.value = 1
    await Timer(5, units="ns")
    # 30 test-clock cycles: the 16-count lock must complete on BOTH roots.
    await _toggle(dut.scan_clk_i, LOCK_CYCLES + 6)
    assert int(dut.pll_locked_o.value) == 1, "fabric PLL reference did not run on scan_clk_i"
    assert int(dut.cpu_pll_locked_o.value) == 1, "CPU PLL reference did not run on scan_clk_i"


@cocotb.test()
async def test_functional_clocks_ignored_in_scan(dut):
    """Scan mode: clk_i / cpu_clk_i toggling must not advance anything."""
    await _idle(dut)
    dut.scan_mode_i.value = 1
    dut.scan_rst_ni.value = 0
    await Timer(5, units="ns")
    dut.scan_rst_ni.value = 1
    await Timer(5, units="ns")
    cocotb.start_soon(Clock(dut.clk_i, PERIOD_NS, units="ns").start())
    cocotb.start_soon(Clock(dut.cpu_clk_i, PERIOD_NS, units="ns").start())
    await ClockCycles(dut.clk_i, 4 * LOCK_CYCLES)
    assert int(dut.pll_locked_o.value) == 0, "clk_i advanced the lock counter in scan mode"
    assert int(dut.cpu_pll_locked_o.value) == 0, "cpu_clk_i advanced the lock counter in scan mode"


@cocotb.test()
async def test_scan_reset_overrides_functional(dut):
    """Scan mode: functional reset pins are ignored; scan_rst_ni resets asynchronously."""
    await _idle(dut)
    dut.scan_mode_i.value = 1
    dut.scan_rst_ni.value = 0
    await Timer(5, units="ns")
    dut.scan_rst_ni.value = 1
    await Timer(5, units="ns")
    await _toggle(dut.scan_clk_i, LOCK_CYCLES + 6)
    assert int(dut.pll_locked_o.value) == 1 and int(dut.cpu_pll_locked_o.value) == 1
    # Functional reset pins low across several test clocks: must change nothing.
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    await _toggle(dut.scan_clk_i, 6)
    assert int(dut.pll_locked_o.value) == 1, "rst_n_i reset the PLL block in scan mode"
    assert int(dut.cpu_pll_locked_o.value) == 1, "cpu_rst_n_i reset the PLL block in scan mode"
    # Scan reset: asynchronous, no clock edge needed.
    dut.scan_rst_ni.value = 0
    await Timer(2, units="ns")
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0


@cocotb.test()
async def test_internal_resets_follow_scan_reset(dut):
    """In scan mode every domain reset equals scan_rst_ni, whatever the functional side does."""
    await _idle(dut)
    soc = dut.u_soc
    dut.scan_mode_i.value = 1
    for scan_rst in (0, 1, 0, 1):
        dut.scan_rst_ni.value = scan_rst
        # Functional pins disagree with the scan reset on purpose.
        dut.rst_n_i.value = 1 - scan_rst
        dut.cpu_rst_n_i.value = 1 - scan_rst
        await Timer(2, units="ns")
        for name in ("core_rst_n", "cpu_core_rst_n", "cpu_domain_rst_n", "gpu_domain_rst_n"):
            got = int(getattr(soc, name).value)
            assert got == scan_rst, f"{name}={got}, expected scan_rst_ni={scan_rst}"


@cocotb.test()
async def test_cpu_clock_gate_forced_open(dut):
    """Scan mode opens u_cpu_cg although its functional enable is 0; functional mode does not."""
    await _idle(dut)
    soc = dut.u_soc

    async def _count_gated_edges(n_cycles):
        edges = 0
        prev = int(soc.cpu_gated_clk.value)
        for _ in range(n_cycles):
            dut.cpu_clk_i.value = 1
            dut.scan_clk_i.value = 1
            await Timer(2, units="ns")
            cur = int(soc.cpu_gated_clk.value)
            edges += int(cur and not prev)
            prev = cur
            await Timer(3, units="ns")
            dut.cpu_clk_i.value = 0
            dut.scan_clk_i.value = 0
            await Timer(5, units="ns")
            prev = int(soc.cpu_gated_clk.value)
        return edges

    # Scan mode, scan reset asserted: pmu_cpu_rst_n_cpu_sync = scan_rst_ni = 0, so the
    # functional enable cpu_gated_clk_en = ~dis_sync & sync = 0 DETERMINISTICALLY.
    # test_en must force the gate open anyway, so the gated clock follows the test
    # clock. (The en=0, test_en=0 closed-gate baseline is test_clock_gate_scan's.)
    dut.scan_mode_i.value = 1
    dut.scan_rst_ni.value = 0
    await _toggle(dut.scan_clk_i, 3)
    assert int(soc.cpu_gated_clk_en.value) == 0, "precondition: functional enable must be 0"
    assert await _count_gated_edges(8) == 8, "cpu_gated_clk did not follow scan_clk_i in scan mode"


@cocotb.test()
async def test_scan_out_placeholder_is_zero(dut):
    """scan_out_o is a defined 0 until Stage 2 insertion drives it."""
    await _idle(dut)
    dut.scan_in_i.value = 0xFF
    await Timer(2, units="ns")
    assert int(dut.scan_out_o.value) == 0
    dut.scan_mode_i.value = 1
    dut.scan_en_i.value = 1
    await _toggle(dut.scan_clk_i, 4)
    assert int(dut.scan_out_o.value) == 0
    # Return every test input to its inactive value (also exercises both toggle directions).
    dut.scan_en_i.value = 0
    dut.scan_in_i.value = 0
    dut.scan_mode_i.value = 0
    await Timer(2, units="ns")
    assert int(dut.scan_out_o.value) == 0


@cocotb.test()
async def test_exit_scan_restores_functional(dut):
    """Leaving scan mode hands the resets back to the functional pins."""
    await _idle(dut)
    soc = dut.u_soc
    dut.scan_mode_i.value = 1
    dut.scan_rst_ni.value = 1
    dut.rst_n_i.value = 0
    await Timer(2, units="ns")
    assert int(soc.core_rst_n.value) == 1, "scan mode must ignore rst_n_i"
    dut.scan_mode_i.value = 0
    await Timer(2, units="ns")
    assert int(soc.core_rst_n.value) == 0, "functional rst_n_i must regain control"


# ---------------------------------------------------------------------------
# j41m.9: scan-mode resets while the PMU holds a domain in reset (mutant g).
# ---------------------------------------------------------------------------
PMU_CTRL_UPPER20 = 0x20008  # PMU CTRL @ 0x2000_8000 (docs/design/MEMORY_MAP.md)
MODE_GPU_OFF = 0x2  # pmu.sv CTRL[1:0]: CPU on, GPU off
DOM_OFF = 4  # pmu.sv pmu_dom_state_e
DOM_CPU, DOM_GPU = 0, 1  # pmu.sv N_DOM index
POWERDOWN_TIMEOUT_CLK_I_CYCLES = 6_000
_CPU_OFF_HEX = Path(__file__).parent / "pmu_cycle_fw" / "pmu_cycle.hex"  # DMA writes CPU_OFF


def _gpu_off_firmware():
    """CPU firmware at the reset PC: store MODE_GPU_OFF to PMU CTRL, then spin."""
    return [
        LUI(5, PMU_CTRL_UPPER20),
        ADDI(6, 0, MODE_GPU_OFF),
        SW(6, 5, 0),
        JAL(0, 0),  # self-loop
    ]


def _cpu_off_firmware():
    words = []
    for line in _CPU_OFF_HEX.read_text().splitlines():
        tok = line.strip()
        if tok and not tok.startswith(("//", "@")):
            words.append(int(tok, 16))
    return words


async def _power_down_domain(dut, words, dom):
    """Boot `words` as CPU firmware in functional mode and wait until the PMU has walked
    domain `dom` to DOM_OFF (reset asserted, clock gated). Returns the two clock tasks."""
    mem = dut.u_soc.u_boot_rom.mem
    assert len(words) <= len(mem)
    for i, w in enumerate(words):
        mem[i].value = w
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    clk_task, cpu_clk_task = start_soc_clocks(
        dut, 7, cpu_period_ns=3
    )  # test_soc_pmu_multiclock ratio
    dut.uart_rx_i.value = 1  # idle-high line
    for _ in range(5):
        await RisingEdge(dut.clk_i)
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    for _ in range(POWERDOWN_TIMEOUT_CLK_I_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.u_soc.u_pmu.dom_state_q[dom].value) == DOM_OFF:
            break
    else:
        raise TimeoutError(f"PMU domain {dom} never reached DOM_OFF")
    # Let the CPU-domain reset synchroniser (cpu_core_clk) see the asserted PMU reset.
    await ClockCycles(dut.cpu_clk_i, 6)
    return clk_task, cpu_clk_task


async def _enter_scan_keeping_pmu(dut, clk_task, cpu_clk_task):
    """Stop the functional clocks and enter scan mode with scan_rst_ni held at 1, so the PMU
    (reset by core_rst_n == scan_rst_ni in scan mode) keeps its power-down state."""
    clk_task.kill()
    cpu_clk_task.kill()
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.scan_rst_ni.value = 1
    dut.scan_mode_i.value = 1
    await Timer(2, units="ns")
    await _toggle(dut.scan_clk_i, 8)  # several test clocks: any synchroniser chain has settled


@cocotb.test()
async def test_scan_gpu_reset_with_pmu_gpu_off(dut):
    """In scan mode gpu_domain_rst_n follows scan_rst_ni although the PMU holds the GPU in reset."""
    await _idle(dut)
    soc = dut.u_soc
    tasks = await _power_down_domain(dut, _gpu_off_firmware(), DOM_GPU)

    # Precondition, functional mode: the PMU really holds the GPU domain in reset and that
    # reaches the net under test.
    assert int(soc.pmu_gpu_rst_n.value) == 0, "precondition: PMU must hold the GPU in reset"
    assert int(soc.gpu_domain_rst_n_func.value) == 0
    assert int(soc.gpu_domain_rst_n.value) == 0

    await _enter_scan_keeping_pmu(dut, *tasks)

    # Precondition, scan mode: the PMU state survived the entry, so the functional term is
    # still low and only the scan override can raise gpu_domain_rst_n.
    assert int(soc.u_pmu.dom_state_q[DOM_GPU].value) == DOM_OFF, "PMU lost its power-down state"
    assert int(soc.pmu_gpu_rst_n.value) == 0, "precondition: PMU must still hold the GPU in reset"
    assert int(soc.gpu_domain_rst_n_func.value) == 0, "precondition: functional term must be 0"
    assert int(soc.gpu_domain_rst_n.value) == 1, (
        "gpu_domain_rst_n ignored scan_rst_ni=1 while the PMU held the GPU in reset"
    )

    # The other direction: scan reset asserted. This also resets the PMU (reset default is
    # gpu_rst_n=1), so here the functional PMU term is HIGH and scan_rst_ni must still win.
    dut.scan_rst_ni.value = 0
    await _toggle(dut.scan_clk_i, 4)  # PMU reset is synchronous: needs test clocks to take effect
    assert int(soc.pmu_gpu_rst_n.value) == 1, (
        "precondition: PMU released the GPU (its reset default)"
    )
    assert int(soc.gpu_domain_rst_n.value) == 0, "gpu_domain_rst_n did not follow scan_rst_ni=0"
    dut.scan_rst_ni.value = 1
    await Timer(2, units="ns")
    assert int(soc.gpu_domain_rst_n.value) == 1


@cocotb.test()
async def test_scan_cpu_reset_with_pmu_cpu_off(dut):
    """In scan mode cpu_domain_rst_n follows scan_rst_ni although the PMU holds the CPU in reset."""
    await _idle(dut)
    soc = dut.u_soc
    tasks = await _power_down_domain(dut, _cpu_off_firmware(), DOM_CPU)

    assert int(soc.pmu_cpu_rst_n.value) == 0, "precondition: PMU must hold the CPU in reset"
    assert int(soc.pmu_cpu_rst_n_cpu_sync.value) == 0
    assert int(soc.cpu_domain_rst_n.value) == 0, "precondition: functional cpu_domain_rst_n low"

    await _enter_scan_keeping_pmu(dut, *tasks)

    assert int(soc.u_pmu.dom_state_q[DOM_CPU].value) == DOM_OFF, "PMU lost its power-down state"
    assert int(soc.pmu_cpu_rst_n.value) == 0, "precondition: PMU must still hold the CPU in reset"
    assert int(soc.cpu_domain_rst_n.value) == 1, (
        "cpu_domain_rst_n ignored scan_rst_ni=1 while the PMU held the CPU in reset"
    )
    dut.scan_rst_ni.value = 0
    await Timer(2, units="ns")
    assert int(soc.cpu_domain_rst_n.value) == 0, "cpu_domain_rst_n did not follow scan_rst_ni=0"
    dut.scan_rst_ni.value = 1
    await _toggle(dut.scan_clk_i, 4)
    assert int(soc.cpu_domain_rst_n.value) == 1
