"""
soc_clocks.py — shared dual-clock start/reset helper for tb_soc_top / tb_soc_pll.

GH #93 made cpu_clk_i/cpu_rst_n_i genuine top-level ports on both wrappers
(previously tied internally to clk_i/rst_n_i under GH #92). Every pre-#93 SoC
suite (test_boot / test_boot_diag / test_periph_loopback / test_soc_coherency /
test_cpu_gpu_irq / test_soc_stress / test_l2_bench / test_pll_lock) now drives
cpu_clk_i/cpu_rst_n_i through this module at a 1:1 ratio, identical phase,
matching the old internal tie exactly — zero behaviour change for those
suites. Only the new multiclock suite (test_soc_multiclock.py) passes a
genuinely independent cpu_period_ns to exercise the CPU<->fabric CDC
boundary (async_axi_fifo + apb_cdc_bridge + the pmu_cpu_*/ext_irq/timer_irq
synchronisers) at a non-1:1 ratio.

Does not manage the module-level `_active_tasks` leakage guard used by each
test file — callers append the returned handles to their own list exactly as
they already do for the clk_i task (or ignore the return, mirroring whichever
convention that file used before GH #93).
"""

import cocotb
from cocotb.clock import Clock


def start_soc_clocks(dut, period_ns, cpu_period_ns=None):
    """Start clk_i and cpu_clk_i as two independent Clock() coroutines.

    cpu_period_ns defaults to period_ns (1:1 ratio — the pre-GH#93 baseline
    behaviour). Returns (clk_task, cpu_clk_task).
    """
    if cpu_period_ns is None:
        cpu_period_ns = period_ns
    clk_task = cocotb.start_soon(Clock(dut.clk_i, period_ns, units="ns").start())
    cpu_clk_task = cocotb.start_soon(Clock(dut.cpu_clk_i, cpu_period_ns, units="ns").start())
    return clk_task, cpu_clk_task


def drive_soc_reset(dut, asserted: bool) -> None:
    """Drive rst_n_i and cpu_rst_n_i together (active-low reset).

    asserted=True holds both domains in reset (value 0); asserted=False
    releases both (value 1). Existing suites always release both domains on
    the same edge (1:1-safe); the multiclock suite may release them on
    different absolute times if a test specifically wants to exercise
    independent-domain reset skew — call dut.rst_n_i.value / dut.cpu_rst_n_i.value
    directly for that case instead of this helper.
    """
    val = 0 if asserted else 1
    dut.rst_n_i.value = val
    dut.cpu_rst_n_i.value = val
