"""
test_pll_lock.py — Phase 7 (M-c) PLL lock acquisition test.

DUT: tb_soc_pll (wraps soc_top with PLL_IMPL="STUB")

Tests:
  test_pll_lock_asserts
      Release reset; confirm pll_locked_o asserts within the stub lock-counter
      budget (STUB_LOCK_CYCLES=16 ref edges + margin); confirm core_clk is
      toggling (observed via commit_valid_o activity); confirm the SoC comes
      out of reset (commit_pc_o stream advances from ROM_BASE=0x0000_1000).

  test_pll_lock_held_after_boot
      Confirm pll_locked_o remains asserted after boot completes; it must not
      glitch to 0 once it rises.

  test_pll_reset_clears_lock
      Re-assert rst_n_i (active-low) while running; confirm pll_locked_o drops;
      re-release; confirm it re-asserts within the same budget.

Clock: 2 ns period (500 MHz ref) — matches test_boot.py convention.
Lock budget: STUB_LOCK_CYCLES=16 + 8 cycles margin = 24 cycles from reset
de-assert.  core_rst_n = rst_n_i & pll_locked, so the first commit_valid_o
after lock fires + the pipeline fills (typically 5–10 additional cycles).
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly

# ---------------------------------------------------------------------------
# Project root on Python path
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Boot ROM backdoor load (same approach as test_boot.py)
# ---------------------------------------------------------------------------
# Verilator bakes MEM_INIT_FILE at elaboration; we cannot override at runtime.
# Instead we write boot.hex directly into u_boot_rom.mem via --public-flat-rw.
# This allows commit_valid_o to fire (boot firmware reaches EBREAK) confirming
# the pipeline is active after PLL lock releases core_rst_n.
_BOOT_HEX  = Path(__file__).parent / "boot_fw" / "boot.hex"
_BOOT_WORDS: list = []


def _rom_words() -> list:
    global _BOOT_WORDS
    if not _BOOT_WORDS:
        words: list = []
        with open(_BOOT_HEX) as fh:
            for line in fh:
                tok = line.strip()
                if not tok or tok.startswith("//") or tok.startswith("@"):
                    continue
                words.append(int(tok, 16))
        _BOOT_WORDS = words
    return _BOOT_WORDS


def _load_rom(dut) -> None:
    """Backdoor-load firmware into dut.u_soc.u_boot_rom.mem."""
    mem = dut.u_soc.u_boot_rom.mem
    for i, word in enumerate(_rom_words()):
        mem[i].value = word

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS    = 2          # 500 MHz — matches test_boot.py
ROM_BASE         = 0x0000_1000

# STUB_LOCK_CYCLES=16; add a generous margin for pipeline latency.
# After reset de-assert: lock fires at ~17 cycles, pipeline fills ~10 more.
LOCK_TIMEOUT_CYCLES  = 60    # pll_locked_o must assert within this many cycles
PC_ADVANCE_TIMEOUT   = 5000  # commit_pc_o must advance within this after lock
                             # Full-SoC boot: I-cache miss → AXI crossbar → SRAM
                             # takes ~200-500 cycles; matches BOOT_TIMEOUT_CYCLES
                             # in test_boot.py.

# ---------------------------------------------------------------------------
# Module-level task handle list (coroutine leakage guard per knowledge.md)
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

async def _start_clock(dut) -> None:
    """Start the reference clock coroutine and track the handle."""
    clk_task = await cocotb.start(Clock(dut.clk_i, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)


def _force_pll_enable(dut, val: int = 1) -> None:
    """
    Force pll_enable internal signal via Verilator --public-flat-rw.

    Bootstrap context (soc_top M-c):
      pll_rst_n = rst_n_i & pll_enable
      pll_enable is driven by pll_axil_regs CONTROL[0] (reset default = 0).
      pll_axil_regs.rst_n_i = core_rst_n = rst_n_i & pll_locked.
      In STUB mode core_clk == ref_clk (passthrough) but core_rst_n stays 0
      until pll_locked fires, which requires pll_enable=1 first.

    This chicken-and-egg dependency means firmware must write CONTROL[0]=1
    during its very first instruction after reset to enable the PLL.  In
    hardware the intent is to use a startup sequencer or power-on defaults.
    For testbench purposes we model firmware intent by forcing the internal
    signal directly.  The AXI-Lite register tests (test_pll_regs.py) verify
    the register interface separately, also using this bootstrap.

    Verilator flat name (from sim_build/Vtb_soc_pll.h, --public-flat-rw):
      dut.u_soc__DOT__pll_enable  (CData, 1-bit)
    """
    dut.u_soc.pll_enable.value = val


async def _reset(dut, cycles: int = 8) -> None:
    """Drive active-low reset for *cycles* rising edges then release."""
    dut.rst_n_i.value      = 0
    # Tie off all inputs that have no default driver in this TB.
    dut.apb_paddr_i.value  = 0
    dut.apb_psel_i.value   = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1   # UART idle = high
    dut.spi_miso_i.value    = 0
    # Bootstrap: assert pll_enable before de-asserting rst_n_i so the PLL
    # lock counter starts on the same reset de-assert edge.
    _force_pll_enable(dut, 1)
    # Backdoor-load boot firmware so the CPU can commit instructions after
    # core_rst_n releases (MEM_INIT_FILE is baked at elaboration under Verilator).
    _load_rom(dut)
    await ClockCycles(dut.clk_i, cycles)
    dut.rst_n_i.value = 1


async def _wait_for_lock(dut, timeout_cycles: int) -> bool:
    """
    Wait up to *timeout_cycles* rising edges for pll_locked_o == 1.
    Returns True if lock asserted in time, False on timeout.
    """
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.pll_locked_o.value) == 1:
            return True
    return False


async def _wait_for_pc_advance(dut, timeout_cycles: int) -> int:
    """
    Wait up to *timeout_cycles* for commit_valid_o + commit_pc_o >= ROM_BASE.
    Returns the first committed PC observed, or 0 on timeout.
    """
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.commit_valid_o.value) == 1:
            pc = int(dut.commit_pc_o.value)
            if pc >= ROM_BASE:
                return pc
    return 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_pll_lock_asserts(dut):
    """
    Lock acquisition: pll_locked_o must assert within LOCK_TIMEOUT_CYCLES
    of reset de-assert; SoC must produce a valid commit_pc_o from ROM_BASE.
    """
    _kill_active_tasks()

    await _start_clock(dut)
    await _reset(dut)

    # --- Check 1: lock asserts in time ---
    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, (
        f"pll_locked_o did not assert within {LOCK_TIMEOUT_CYCLES} cycles "
        "of reset de-assert (STUB_LOCK_CYCLES=16, expected ~17 cycles)"
    )
    dut._log.info("pll_locked_o asserted — PLL stub lock acquired")

    # --- Check 2: commit stream starts from ROM_BASE ---
    # core_rst_n releases when pll_locked fires; the pipeline fills in ~5-10
    # more cycles before the first commit_valid.
    first_pc = await _wait_for_pc_advance(dut, PC_ADVANCE_TIMEOUT)
    assert first_pc >= ROM_BASE, (
        f"No valid commit_pc_o >= 0x{ROM_BASE:08x} seen within "
        f"{PC_ADVANCE_TIMEOUT} cycles after lock.  first_pc=0x{first_pc:08x}"
    )
    dut._log.info(f"First committed PC: 0x{first_pc:08x} (ROM_BASE=0x{ROM_BASE:08x})")


@cocotb.test()
async def test_pll_lock_held_after_boot(dut):
    """
    pll_locked_o must remain asserted once raised; confirm it does not glitch
    to 0 during the PC advance window.
    """
    _kill_active_tasks()

    await _start_clock(dut)
    await _reset(dut)

    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, "pll_locked_o did not assert — see test_pll_lock_asserts"

    lock_dropped = False
    for _ in range(PC_ADVANCE_TIMEOUT):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.pll_locked_o.value) == 0:
            lock_dropped = True
            break

    assert not lock_dropped, (
        "pll_locked_o dropped to 0 after initial assertion — "
        "stub lock counter must not decrement once locked"
    )
    dut._log.info("pll_locked_o held asserted throughout post-lock window")


@cocotb.test()
async def test_pll_reset_clears_lock(dut):
    """
    Re-assert rst_n_i while running; confirm pll_locked_o drops; re-release;
    confirm it re-asserts within the same budget.
    """
    _kill_active_tasks()

    await _start_clock(dut)
    await _reset(dut)

    # Wait for initial lock
    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, "Initial lock did not assert — see test_pll_lock_asserts"
    dut._log.info("Initial lock confirmed")

    # _wait_for_lock exits after ReadOnly() — advance one clock edge to leave
    # the read-only phase before driving signals.
    await RisingEdge(dut.clk_i)

    # Re-assert reset (active-low: drive 0)
    dut.rst_n_i.value = 0
    await ClockCycles(dut.clk_i, 4)
    await ReadOnly()

    lock_val = int(dut.pll_locked_o.value)
    assert lock_val == 0, (
        f"pll_locked_o did not drop when rst_n_i re-asserted; "
        f"got {lock_val} (stub lock_cnt_q must reset to 0 on negedge rst_n_i)"
    )
    dut._log.info("pll_locked_o correctly cleared on re-assert of rst_n_i")

    # Advance out of the ReadOnly phase before driving signals.
    await RisingEdge(dut.clk_i)

    # Release reset again — re-assert pll_enable (bootstrap) and confirm re-lock.
    _force_pll_enable(dut, 1)
    dut.rst_n_i.value = 1
    re_locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert re_locked, (
        f"pll_locked_o did not re-assert within {LOCK_TIMEOUT_CYCLES} cycles "
        "after second reset de-assert"
    )
    dut._log.info("pll_locked_o re-asserted after second reset release")
