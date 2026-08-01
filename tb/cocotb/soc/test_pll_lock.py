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

GH #92 (dual PLL) additions:
  test_cpu_pll_locked_asserts
      cpu_pll_locked_o (second, CPU-domain stub PLL) must assert within the
      same lock budget as pll_locked_o, and must not glitch once asserted.
      Runs with the stock boot.hex firmware (no MMIO needed — this is a pure
      signal-level check on the new tb_soc_pll port).

  test_pll2_apb_slot_decode
      Self-checking firmware (pll2_fw/pll2_decode.hex) verifies, via real
      CPU MMIO through the crossbar -> axi4_to_axilite -> axi_lite_interconnect
      -> axil_to_apb -> apb_interconnect path:
        - PLL  (APB_PLL=4,  0x2000_7000) CONTROL[0]==1, STATUS[0]==1 (existing
          slot unaffected by the map extension).
        - PMU  (APB_PMU=5,  0x2000_8000) STATUS==0x3 (slot did not move).
        - PLL2 (APB_PLL2=6, 0x2000_9000) CONTROL==0x0000_0001 (new slot
          decodes to pll_apb_regs' RESET_VAL, not DECERR/garbage/another
          slave), STATUS[0]==1 (second stub PLL locked).
        - Anti-brick (GH #89, applies to instance 2 via the shared
          pll_apb_regs module): writing CONTROL=0 does NOT clear bit[0];
          readback stays 0x0000_0001, and STATUS[0] (lock) is unaffected.
      See pll2_fw/gen_pll2_decode_hex.py for the full firmware listing and the
      rationale for CPU-firmware-based MMIO (a live cocotb AXI-Lite/APB BFM
      against soc_top's internal, continuously-RTL-driven nets hangs under
      Verilator — documented in test_pll_regs.py's module docstring).
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

from tb.cocotb.soc.pll2_fw.pll2_decode_fw_addrs import (
    PASS_PC as PLL2_PASS_PC,
    FAIL_PC as PLL2_FAIL_PC,
)

# ---------------------------------------------------------------------------
# Boot ROM backdoor load (same approach as test_boot.py)
# ---------------------------------------------------------------------------
# Verilator bakes MEM_INIT_FILE at elaboration; we cannot override at runtime.
# Instead we write boot.hex directly into u_boot_rom.mem via --public-flat-rw.
# This allows commit_valid_o to fire (boot firmware reaches EBREAK) confirming
# the pipeline is active after PLL lock releases core_rst_n.
_BOOT_HEX  = Path(__file__).parent / "boot_fw" / "boot.hex"
_BOOT_WORDS: list = []

# GH #92: PLL2 APB-slot-decode self-checking firmware image.
_PLL2_HEX = Path(__file__).parent / "pll2_fw" / "pll2_decode.hex"
_PLL2_WORDS: list = []


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
        f"({len(mem)} words) — regenerate via gen_pll2_decode_hex.py"
    )
    for i, word in enumerate(words):
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

# PLL2 firmware runs a handful of MMIO reads/writes after lock+boot fill —
# generous bound consistent with PC_ADVANCE_TIMEOUT (test_periph_loopback.py
# uses a much larger bound for a much longer firmware; this one is ~35 words).
PLL2_TIMEOUT_CYCLES = 5000
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

    Bootstrap context (soc_top, post-APB-migration + pll_subsystem wrapper):
      pll_rst_n = rst_n_i & pll_enable
      pll_enable is driven by pll_apb_regs CONTROL[0] (reset default = 1, so the
      PLL is enabled out of reset — no firmware bring-up step required).
      pll_apb_regs runs on clk_i / rst_n_i (always-on ref domain), NOT
      core_rst_n — config regs survive a core reset, so there is no
      chicken-and-egg dependency on pll_locked.
      In STUB mode core_clk == ref_clk (passthrough); core_rst_n stays 0 only
      until pll_locked fires (a few ref cycles after reset, since pll_enable=1).

    This helper forces the internal pll_enable directly so a test can model
    firmware toggling CONTROL[0] without driving the APB bus.  The APB register
    interface is verified separately by test_pll_apb_regs.py.
    NOTE: clearing pll_enable at runtime drops core_rst_n (resets CPU+bus) — a
    firmware self-brick path tracked as a separate design follow-up (not a
    refactor concern).

    Verilator flat name (from sim_build/Vtb_soc_pll.h, --public-flat-rw):
      dut.u_soc.u_pll_sub.pll_enable  (CData, 1-bit)

    pll_enable moved into pll_subsystem (u_pll_sub) by the 1xb wrapper refactor
    (commit a513f9c). Old path dut.u_soc.pll_enable was removed from soc_top.
    """
    dut.u_soc.u_pll_sub.pll_enable.value = val


async def _reset(dut, cycles: int = 8, rom_loader=None) -> None:
    """Drive active-low reset for *cycles* rising edges then release.

    rom_loader defaults to _load_rom (stock boot.hex); GH #92 tests pass
    _load_pll2_rom to run the self-checking PLL2-decode firmware instead.
    """
    if rom_loader is None:
        rom_loader = _load_rom
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
    rom_loader(dut)
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


async def _wait_for_cpu_lock(dut, timeout_cycles: int) -> bool:
    """
    Wait up to *timeout_cycles* rising edges for cpu_pll_locked_o == 1
    (GH #92 second, CPU-domain stub PLL).
    """
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.cpu_pll_locked_o.value) == 1:
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


@cocotb.test()
async def test_cpu_pll_locked_asserts(dut):
    """
    GH #92: cpu_pll_locked_o (second, CPU-domain stub PLL, u_cpu_pll_sub) must
    assert within the same lock budget as pll_locked_o and must not glitch
    once asserted.  tb_soc_pll ties cpu_clk_i/cpu_rst_n_i to clk_i/rst_n_i
    (single-clock suite — see tb_soc_pll.sv header), so both stub lock
    counters start on the same reset de-assert edge and are expected to
    assert together.

    Uses the stock boot.hex firmware (no MMIO needed for this check).
    """
    _kill_active_tasks()

    await _start_clock(dut)
    await _reset(dut)

    locked = await _wait_for_lock(dut, LOCK_TIMEOUT_CYCLES)
    assert locked, "pll_locked_o did not assert — see test_pll_lock_asserts"

    cpu_locked_now = int(dut.cpu_pll_locked_o.value)
    dut._log.info(
        f"pll_locked_o asserted; cpu_pll_locked_o={cpu_locked_now} at same instant"
    )

    # cpu_pll_locked_o may assert on the same edge as pll_locked_o (both stub
    # counters share STUB_LOCK_CYCLES=16 and the same reset de-assert edge) or
    # within a few cycles either side depending on elaboration order — poll
    # forward with the same budget rather than requiring exact simultaneity.
    if cpu_locked_now == 0:
        cpu_locked = await _wait_for_cpu_lock(dut, LOCK_TIMEOUT_CYCLES)
        assert cpu_locked, (
            f"cpu_pll_locked_o did not assert within {LOCK_TIMEOUT_CYCLES} "
            "cycles of reset de-assert, even though pll_locked_o did "
            "(u_cpu_pll_sub lock counter — see soc_top.sv u_cpu_pll_sub)"
        )
    dut._log.info("cpu_pll_locked_o asserted — CPU-domain stub PLL lock acquired")

    # Confirm both lock signals are held (no glitch) through the boot window.
    dropped = []
    for _ in range(PC_ADVANCE_TIMEOUT):
        await RisingEdge(dut.clk_i)
        await ReadOnly()
        if int(dut.pll_locked_o.value) == 0:
            dropped.append("pll_locked_o")
        if int(dut.cpu_pll_locked_o.value) == 0:
            dropped.append("cpu_pll_locked_o")
        if dropped:
            break

    assert not dropped, (
        f"{dropped[0]} dropped to 0 after initial assertion during the boot "
        "window — stub lock counters must not decrement once locked"
    )
    dut._log.info(
        "pll_locked_o and cpu_pll_locked_o both held asserted through boot — PASS"
    )


@cocotb.test()
async def test_pll2_apb_slot_decode(dut):
    """
    GH #92: verify the new APB_PLL2 slot (0x2000_9000-0x2000_9FFF) decodes
    correctly at the SoC level, that the pre-existing PLL (0x2000_7000) and
    PMU (0x2000_8000) slots are unaffected, and that the GH #89 anti-brick
    fix (CONTROL[0] non-clearable) holds for the second pll_apb_regs
    instance.  Driven entirely by real CPU MMIO (self-checking firmware —
    see pll2_fw/gen_pll2_decode_hex.py for the full check list and firmware
    listing); the firmware branches to PASS_PC on full success or FAIL_PC on
    any single check failing.
    """
    _kill_active_tasks()

    await _start_clock(dut)
    await _reset(dut, rom_loader=_load_pll2_rom)

    saw_fail = False
    last_pc = 0
    for _ in range(PLL2_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
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
        f"pll2_decode firmware reached FAIL_PC=0x{PLL2_FAIL_PC:08x} — one of "
        "the PLL/PMU/PLL2 APB decode or anti-brick checks failed "
        "(see gen_pll2_decode_hex.py check list for the exact assertion order)"
    )
    assert last_pc == PLL2_PASS_PC, (
        f"pll2_decode firmware did not reach PASS_PC=0x{PLL2_PASS_PC:08x} "
        f"within {PLL2_TIMEOUT_CYCLES} cycles; last committed PC=0x{last_pc:08x}"
    )
    dut._log.info(
        f"pll2_decode firmware reached PASS_PC=0x{PLL2_PASS_PC:08x} — PLL2 "
        "APB slot decodes correctly; PLL/PMU slots unaffected; CONTROL[0] "
        "non-clearable on the second pll_apb_regs instance — PASS"
    )
