"""
test_soc_multiclock_pll2.py — GH #93 multiclock APB_PLL2 / apb_cdc_bridge
exercise (bonus item 4 of the GH #93 multiclock verification task).

DUT: tb_soc_pll (NOT tb_soc_top — separate TOPLEVEL/VERILOG_SOURCES; see
tb/cocotb/soc/Makefile's PLL_SOURCES / soc_pll target, which test_pll_lock.py
uses). Kept in its own module + Makefile target (soc_pll_multiclock) rather
than folded into test_soc_multiclock.py, because this Makefile's convention
is one VERILOG_SOURCES/TOPLEVEL pair per recursive `make` invocation and one
MODULE (= one cocotb Python file) drives exactly one compiled DUT binary
(sim_build/Vtop, always named Vtop regardless of TOPLEVEL — see every other
target's "clean first" comment). Mixing tb_soc_top and tb_soc_pll traffic in
one cocotb test module would need two different VERILOG_SOURCES elaborated
under one MODULE, which this Makefile has no mechanism for without a second
`make clean && make` sub-invocation — against the grain of every existing
target here.

BLOCKER NOTE (2026-08-01): like test_soc_multiclock.py, this suite cannot pass
until the GH #93 CPU-clock-gating boot regression is fixed — it is driven by
CPU firmware, and the CPU never executes an instruction. See
test_soc_multiclock.py's BLOCKER NOTE for the full root-cause analysis and
the reproduction on a pristine worktree at commit 66a9af1.

Purpose: verify rtl/soc/apb_cdc_bridge.sv (u_apb_pll2_cdc, the 2-phase
toggle-handshake APB4 bridge in front of the APB_PLL2 slot at 0x2000_9000 —
the CPU-domain pll_apb_regs instance, soc_top.sv's u_cpu_pll_sub) works at a
genuinely asynchronous CPU<->fabric clock ratio, not just the 1:1 ratio every
other suite (including test_pll_lock.py's test_pll2_apb_slot_decode, which
this test reuses the firmware from) exercises it at.

Clock periods: same CPU_PERIOD_NS=3 / FABRIC_PERIOD_NS=7 as
test_soc_multiclock.py — see that module's docstring for the full ratio
rationale (7/3 ~= 2.33, coprime, matches the real CPU-faster-than-fabric
target direction).

Firmware reuse: pll2_fw/pll2_decode.hex (test_pll_lock.py's
test_pll2_apb_slot_decode firmware, unmodified) — self-checking CPU MMIO
that verifies APB_PLL (0x2000_7000), APB_PMU (0x2000_8000, slot unaffected),
and APB_PLL2 (0x2000_9000, the new CDC-bridged slot) all decode correctly,
plus the GH #89 anti-brick invariant (CONTROL[0] non-clearable) on the
second pll_apb_regs instance. No new firmware/C source is written here.

Bug-class note: commit_valid_o / commit_pc_o are CPU-domain signals (see
test_soc_multiclock.py's docstring) — every polling loop here uses
RisingEdge(dut.cpu_clk_i), never dut.clk_i.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.pll2_fw.pll2_decode_fw_addrs import (
    PASS_PC as PLL2_PASS_PC,
    FAIL_PC as PLL2_FAIL_PC,
)

# ---------------------------------------------------------------------------
# Clock periods — see test_soc_multiclock.py's docstring for the rationale.
# ---------------------------------------------------------------------------
CPU_PERIOD_NS    = 3
FABRIC_PERIOD_NS = 7

# ---------------------------------------------------------------------------
# Firmware hex loader (backdoor into u_boot_rom.mem — see test_pll_lock.py)
# ---------------------------------------------------------------------------
_PLL2_HEX = Path(__file__).parent / "pll2_fw" / "pll2_decode.hex"
_PLL2_WORDS: list = []


def _pll2_rom_words() -> list:
    global _PLL2_WORDS
    if not _PLL2_WORDS:
        words: list = []
        with open(_PLL2_HEX) as fh:
            for line in fh:
                tok = line.strip()
                if not tok or tok.startswith("//") or tok.startswith("@"):
                    continue
                words.append(int(tok, 16))
        _PLL2_WORDS = words
    return _PLL2_WORDS


def _load_pll2_rom(dut) -> None:
    """Backdoor-load the PLL2-decode self-checking firmware."""
    mem = dut.u_soc.u_boot_rom.mem
    words = _pll2_rom_words()
    assert len(words) <= len(mem), (
        f"pll2_decode.hex ({len(words)} words) exceeds boot ROM capacity "
        f"({len(mem)} words)"
    )
    for i, word in enumerate(words):
        mem[i].value = word


# ---------------------------------------------------------------------------
# Module-level task handle tracking (coroutine leakage guard per knowledge.md)
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _force_pll_enable(dut, val: int = 1) -> None:
    """Force the fabric-domain PLL's pll_enable directly (see
    test_pll_lock.py's _force_pll_enable for the full bootstrap rationale) —
    ensures the lock counter starts on the same reset de-assert edge. The
    CPU-domain PLL (u_cpu_pll_sub, feeding APB_PLL2) is NOT forced here,
    mirroring test_pll_lock.py's test_cpu_pll_locked_asserts / _reset(),
    which relies on pll_apb_regs' CONTROL[0] reset default (=1) instead."""
    dut.u_soc.u_pll_sub.pll_enable.value = val


async def _reset(dut, cycles: int = 5) -> None:
    """Start both clocks at the multiclock ratio, idle inputs, backdoor-load
    the pll2_decode firmware, apply + release reset on both domains.

    Reset held for `cycles` RisingEdge(dut.clk_i) (the slower fabric clock) —
    same "at least this many edges in both domains" reasoning as
    test_soc_multiclock.py's _setup.
    """
    _kill_active_tasks()

    clk_task, cpu_clk_task = start_soc_clocks(
        dut, FABRIC_PERIOD_NS, cpu_period_ns=CPU_PERIOD_NS
    )
    _active_tasks.append(clk_task)
    _active_tasks.append(cpu_clk_task)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1
    dut.spi_miso_i.value    = 0

    _force_pll_enable(dut, 1)
    _load_pll2_rom(dut)

    for _ in range(cycles):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)


# test_pll_lock.py's PLL2_TIMEOUT_CYCLES=5000 @ CLK_PERIOD_NS=2 ns covers a
# short (~35-word) self-checking firmware plus PLL lock + pipeline fill.
# Converted to cpu_clk_i cycles at the new ratio (7/3 ~= 2.33x) and rounded
# up generously, same methodology as test_soc_multiclock.py's
# BOOT_TIMEOUT_CYCLES: 5000 * 2.33 ~= 11,667 -> 12,000 cpu_clk_i cycles.
PLL2_TIMEOUT_CYCLES = 12_000


@cocotb.test()
async def test_multiclock_pll2_apb_slot_decode(dut):
    """
    Self-checking firmware verifies PLL/PMU/PLL2 APB slot decode + the
    GH #89 anti-brick invariant, driven entirely through the CPU's real MMIO
    path — for PLL2 specifically, through apb_cdc_bridge (u_apb_pll2_cdc) at
    the multiclock CPU<->fabric ratio. Pass criterion: PASS_PC committed,
    FAIL_PC never seen.
    """
    await _reset(dut)

    saw_fail = False
    last_pc = 0
    for _ in range(PLL2_TIMEOUT_CYCLES):
        await RisingEdge(dut.cpu_clk_i)
        await ReadOnly()
        if int(dut.commit_valid_o.value) == 1:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            if pc == PLL2_FAIL_PC:
                saw_fail = True
                break
            if pc == PLL2_PASS_PC:
                break

    assert not saw_fail, (
        f"pll2_decode firmware reached FAIL_PC=0x{PLL2_FAIL_PC:08x} at the "
        f"multiclock ratio (cpu={CPU_PERIOD_NS} ns, fabric={FABRIC_PERIOD_NS} ns) "
        "— one of the PLL/PMU/PLL2 APB decode or anti-brick checks failed "
        "through apb_cdc_bridge (see gen_pll2_decode_hex.py for the exact "
        "assertion order)"
    )
    assert last_pc == PLL2_PASS_PC, (
        f"pll2_decode firmware did not reach PASS_PC=0x{PLL2_PASS_PC:08x} "
        f"within {PLL2_TIMEOUT_CYCLES} cpu_clk_i cycles at the multiclock "
        f"ratio; last committed PC=0x{last_pc:08x}"
    )
    dut._log.info(
        f"pll2_decode firmware reached PASS_PC=0x{PLL2_PASS_PC:08x} at the "
        f"multiclock ratio — APB_PLL2 slot decodes correctly through "
        "apb_cdc_bridge; PLL/PMU slots unaffected; CONTROL[0] non-clearable "
        "on the second pll_apb_regs instance — PASS"
    )
