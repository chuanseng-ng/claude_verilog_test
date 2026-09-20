"""test_gpio.py -- Phase 6a cocotb verification for gpio_controller (rtl/periph/gpio_controller.sv,
bead claude_verilog_test-ckc).

DUT: tb_gpio (standalone wrapper, directly instantiates gpio_controller, N_PINS=32 default)

Register map (gpio_controller.sv, ADDR_W=12 local byte offset):
  0x000  GPIO_DATA_IN   [RO]   live synchronised pin levels (HW-written)
  0x004  GPIO_DATA_OUT  [RW]   output-drive value per pin (WMASK=PIN_MASK)
  0x008  GPIO_DIR       [RW]   1 = pin driven as output, 0 = input (WMASK=PIN_MASK)
  0x00C  GPIO_IRQ_EN    [RW]   1 = pin's IRQ event masked into irq_o (WMASK=PIN_MASK)
  0x010  GPIO_IRQ_TYPE  [RW]   0 = level-sensitive, 1 = edge-sensitive (WMASK=PIN_MASK)
  0x014  GPIO_IRQ_POL   [RW]   0 = active-low/falling, 1 = active-high/rising (WMASK=PIN_MASK)
  0x018  GPIO_IRQ_STAT  [RO]   per-pin pending: sticky in edge mode, live in level mode (HW-written)
  0x01C  GPIO_IRQ_CLR   [W1C]  APB-write-snoop clear (edge pins only); always reads 0
  >=0x020 (word index >= 8)    out-of-range: writes dropped, reads return 0, pslverr=0

N_PINS defaults to 32 in tb_gpio, so PIN_MASK == 0xFFFF_FFFF and every RW register's WMASK
covers the full 32 bits used below (elaboration guard in gpio_controller.sv separately rejects
N_PINS == 0 or N_PINS > 32; not exercised here -- no other suite in this Makefile tests an
elaboration-time $fatal guard via cocotb either).

Sync / edge latency contract (see gpio_controller.sv header for the RTL's own description, and
test_gpio_data_in_sync_latency's docstring for the exact empirical calibration against this
cocotb/Verilator environment): gpio_in_i is synchronised by a 2-stage cdc_2ff_sync per pin, and
apb4_register_bank's own HW-write path is itself a further registered mirror of the synchronised
wire before a pin change is visible through an APB read of GPIO_DATA_IN or (via edge/level
detection built on the same synchronised wire) GPIO_IRQ_STAT. Measured directly against this RTL
by sampling every single intervening edge (test_gpio_data_in_sync_latency below): a pin change is
visible through the register bank exactly 3 clock edges after it is driven -- one per flop in
on-paper trace of the 2 sync flops + 1 register-bank stage would suggest (see that test's
docstring for the extra edge's likely source). All latency-sensitive tests below peek the live
register value combinationally (see _peek()) rather than going through an APB read transaction,
so the edge count asserted is exact and not conflated with the BFM's own SETUP/ACCESS overhead.

GPIO_IRQ_STAT capture rule, by GPIO_IRQ_TYPE (see gpio_controller.sv header):
  edge  (TYPE=1): STICKY. stat = (stat & ~clr) | edge_event -- a GPIO_IRQ_CLR write landing the
                  same edge as a fresh qualifying transition leaves the bit SET (set beats clear,
                  falls out of the OR with edge_event).
  level (TYPE=0): LIVE. stat = level_event -- GPIO_IRQ_CLR has NO effect on a level-mode bit.
At reset (TYPE=0 level, POL=0 active-low, gpio_in_i driven all-zero by _start_clock_and_reset) every
pin's level condition is true, so GPIO_IRQ_STAT reads all-ones a couple of cycles out of reset --
test_gpio_reset_defaults asserts that deliberately, matching the RTL header's own rationale.

irq_o = |(GPIO_IRQ_STAT & GPIO_IRQ_EN), purely combinational and level-held (never a pulse).

Tests:
  test_gpio_reset_defaults
      All RW regs 0, GPIO_IRQ_STAT == all-ones (level defaults + all-zero pins), irq_o == 0
      (GPIO_IRQ_EN == 0 masks it), gpio_out_o/gpio_oe_o == 0.
  test_gpio_rw_roundtrip_all_registers
      Write/read-back round trip on DATA_OUT, DIR, IRQ_EN, IRQ_TYPE, IRQ_POL.
  test_gpio_output_pins_mirror_data_out_and_dir
      gpio_out_o mirrors DATA_OUT, gpio_oe_o mirrors DIR, visible immediately after the write.
  test_gpio_data_in_sync_latency
      Cycle-exact: DATA_IN is stale through edges 1-2, matches the new pin value at edge 3.
  test_gpio_edge_capture_rising
      TYPE=edge, POL=rising: STAT bit sets exactly 4 edges after a 0->1 pin transition.
  test_gpio_edge_capture_falling
      TYPE=edge, POL=falling (default): STAT bit sets exactly 4 edges after a 1->0 transition.
  test_gpio_level_high
      TYPE=level (default), POL=rising: STAT bit tracks the pin level live (set when high).
  test_gpio_level_low
      TYPE=level, POL=falling (default): STAT bit tracks the pin level live (set when low).
  test_gpio_edge_sticky_and_clear
      Edge-mode STAT bit stays set until a GPIO_IRQ_CLR write targets it.
  test_gpio_edge_set_beats_same_cycle_clear
      A GPIO_IRQ_CLR write landing on the SAME edge as a fresh qualifying transition leaves the
      bit SET, not cleared.
  test_gpio_level_clr_has_no_effect
      GPIO_IRQ_CLR does not affect a level-mode bit; only the level condition (or GPIO_IRQ_EN)
      controls it.
  test_gpio_irq_clr_pstrb_partial_word
      A strobed GPIO_IRQ_CLR write clears only the strobed byte's bits.
  test_gpio_irq_en_masks_output_only
      GPIO_IRQ_EN gates irq_o only; GPIO_IRQ_STAT capture is unaffected by it.
  test_gpio_irq_level_held_across_cycles
      irq_o stays asserted across many consecutive cycles once its condition is enabled (no pulse).
  test_gpio_irq_clr_reads_as_zero
      GPIO_IRQ_CLR always reads back 0, regardless of what was last written to it.
  test_gpio_out_of_range_access
      Word index >= 8 (byte offset >= 0x020): write silently dropped, read returns 0, pslverr=0.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bfm.apb4_master import APB4Master

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 10  # 100 MHz -- matches SoC reference clock (same convention as test_pmu.py)

GPIO_DATA_IN = 0x000
GPIO_DATA_OUT = 0x004
GPIO_DIR = 0x008
GPIO_IRQ_EN = 0x00C
GPIO_IRQ_TYPE = 0x010
GPIO_IRQ_POL = 0x014
GPIO_IRQ_STAT = 0x018
GPIO_IRQ_CLR = 0x01C
GPIO_OUT_OF_RANGE = 0x020  # word index 8 -- first address past the 8-register map

N_PINS = 32
ALL_PINS_MASK = 0xFFFF_FFFF

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
    """Start 100 MHz clock and apply synchronous reset. Idle the APB4 bus and drive every
    GPIO pin low (the DUT contract's own reset scenario assumes gpio_in_i is all-zero)."""
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n.value = 0
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = 0
    dut.pwdata.value = 0
    dut.pstrb.value = 0xF
    dut.gpio_in_i.value = 0

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def _make_apb_bfm(dut) -> APB4Master:
    """Construct APB4Master BFM targeting the DUT's flat APB4 ports."""
    return APB4Master(dut, "", dut.clk)


async def _peek(dut, addr: int) -> int:
    """Point the idle APB4 bus's read-data path at `addr` and return the value it shows right
    now. apb4_register_bank drives prdata purely combinationally off paddr/pwrite -- independent
    of psel/penable -- so with the bus otherwise idle (psel=0, penable=0, pwrite=0, the state
    _start_clock_and_reset and APB4Master.write()/read() both leave it in) this samples the live
    register value with NO APB transaction and NO side effects: no write can occur since access
    (psel & penable) is 0.

    Bug found + fixed during development (bead claude_verilog_test-ckc): a bare synchronous
    version of this helper (set paddr/pwrite, read prdata immediately, no intervening trigger)
    read STALE prdata whenever the target address differed from whatever address a real clock
    edge had last settled prdata against -- cocotb's VPI signal write does not itself force
    Verilator to re-run combinational logic; only an actual simulator time-step boundary does.
    Symptom was silent and address-independent-looking (e.g. peeking GPIO_IRQ_TYPE right after
    peeking GPIO_DATA_IN returned GPIO_DATA_IN's value instead of GPIO_IRQ_TYPE's), and it
    happened to go unnoticed wherever a real RisingEdge already separated two peeks of different
    addresses (the common case) -- only a same-instant, back-to-back multi-address peek exposed
    it. `await Timer(1, units="step")` (a single simulator time step -- 1 ps at this suite's
    1ns/1ps timescale, i.e. 1/10000 of one clock period) forces that settle without disturbing
    any clock-edge-relative cycle count elsewhere in this file."""
    dut.pwrite.value = 0
    dut.paddr.value = addr
    await Timer(1, units="step")
    return int(dut.prdata.value)


def _raw_write_setup(dut, addr: int, data: int) -> None:
    """Drive the SETUP phase of a raw APB4 write (bypasses APB4Master so the caller can align
    the write's own ACCESS-phase commit edge with a specific internal DUT event, cycle-exact)."""
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 1
    dut.paddr.value = addr
    dut.pwdata.value = data
    dut.pstrb.value = 0xF


def _raw_write_access(dut) -> None:
    """Drive the ACCESS phase (pready is hardwired 1 -- commits this edge)."""
    dut.penable.value = 1


def _raw_write_idle(dut) -> None:
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_gpio_reset_defaults(dut):
    """After reset: DATA_OUT/DIR/IRQ_EN/IRQ_TYPE/IRQ_POL == 0, IRQ_CLR reads 0, DATA_IN == 0
    (gpio_in_i driven all-zero), IRQ_STAT == all-ones (level defaults + all-zero pins => every
    pin's level condition is true -- deliberate, not a bug, see gpio_controller.sv header), and
    irq_o == 0 (IRQ_EN == 0 masks the all-ones IRQ_STAT out of the output)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    data_out, ok1 = await bfm.read(GPIO_DATA_OUT)
    gdir, ok2 = await bfm.read(GPIO_DIR)
    irq_en, ok3 = await bfm.read(GPIO_IRQ_EN)
    irq_type, ok4 = await bfm.read(GPIO_IRQ_TYPE)
    irq_pol, ok5 = await bfm.read(GPIO_IRQ_POL)
    irq_stat, ok6 = await bfm.read(GPIO_IRQ_STAT)
    irq_clr, ok7 = await bfm.read(GPIO_IRQ_CLR)
    data_in, ok8 = await bfm.read(GPIO_DATA_IN)

    assert all([ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8]), "reset-default reads returned SLVERR"
    assert data_out == 0, f"GPIO_DATA_OUT expected 0 at reset, got 0x{data_out:08x}"
    assert gdir == 0, f"GPIO_DIR expected 0 at reset, got 0x{gdir:08x}"
    assert irq_en == 0, f"GPIO_IRQ_EN expected 0 at reset, got 0x{irq_en:08x}"
    assert irq_type == 0, f"GPIO_IRQ_TYPE expected 0 at reset, got 0x{irq_type:08x}"
    assert irq_pol == 0, f"GPIO_IRQ_POL expected 0 at reset, got 0x{irq_pol:08x}"
    assert irq_clr == 0, f"GPIO_IRQ_CLR expected to read 0 at reset, got 0x{irq_clr:08x}"
    assert data_in == 0, f"GPIO_DATA_IN expected 0 at reset (pins driven low), got 0x{data_in:08x}"
    assert irq_stat == ALL_PINS_MASK, (
        f"GPIO_IRQ_STAT expected all-ones at reset (level defaults + all-zero pins => every "
        f"pin's condition true), got 0x{irq_stat:08x}"
    )
    assert int(dut.gpio_out_o.value) == 0, f"gpio_out_o expected 0 at reset, got 0x{int(dut.gpio_out_o.value):08x}"
    assert int(dut.gpio_oe_o.value) == 0, f"gpio_oe_o expected 0 at reset, got 0x{int(dut.gpio_oe_o.value):08x}"
    assert int(dut.irq_o.value) == 0, (
        f"irq_o expected 0 at reset (IRQ_EN==0 masks the all-ones IRQ_STAT), got {int(dut.irq_o.value)}"
    )
    dut._log.info(f"Reset defaults OK: IRQ_STAT=0x{irq_stat:08x} irq_o={int(dut.irq_o.value)}")


@cocotb.test()
async def test_gpio_rw_roundtrip_all_registers(dut):
    """Write/read-back round trip on every RW register: DATA_OUT, DIR, IRQ_EN, IRQ_TYPE, IRQ_POL.
    N_PINS==32 means PIN_MASK==0xFFFFFFFF, so the pattern below must read back byte-identical."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    pattern = 0xA5A5_A5A5
    rw_regs = {
        "GPIO_DATA_OUT": GPIO_DATA_OUT,
        "GPIO_DIR": GPIO_DIR,
        "GPIO_IRQ_EN": GPIO_IRQ_EN,
        "GPIO_IRQ_TYPE": GPIO_IRQ_TYPE,
        "GPIO_IRQ_POL": GPIO_IRQ_POL,
    }

    for name, addr in rw_regs.items():
        ok_w = await bfm.write(addr, pattern)
        assert ok_w, f"{name} write returned SLVERR"
        data, ok_r = await bfm.read(addr)
        assert ok_r, f"{name} readback returned SLVERR"
        assert data == pattern, f"{name} readback: got 0x{data:08x}, expected 0x{pattern:08x}"
        # Restore to 0 so later registers in this loop aren't affected by an earlier write.
        ok_clear = await bfm.write(addr, 0x0000_0000)
        assert ok_clear, f"{name} clear-back-to-0 write returned SLVERR"
    dut._log.info("RW round trip confirmed on DATA_OUT/DIR/IRQ_EN/IRQ_TYPE/IRQ_POL")


@cocotb.test()
async def test_gpio_output_pins_mirror_data_out_and_dir(dut):
    """gpio_out_o mirrors GPIO_DATA_OUT and gpio_oe_o mirrors GPIO_DIR, visible immediately after
    the write commits (both are pure combinational mirrors of the register bank's regs_o)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    out_pattern = 0x0000_00F0
    dir_pattern = 0x0000_0F0F

    ok1 = await bfm.write(GPIO_DATA_OUT, out_pattern)
    assert ok1, "GPIO_DATA_OUT write returned SLVERR"
    ok2 = await bfm.write(GPIO_DIR, dir_pattern)
    assert ok2, "GPIO_DIR write returned SLVERR"
    # One extra clock edge of settle margin: this test checks that the mirrors are correct at
    # all, not the exact edge they land on (that's test_gpio_data_in_sync_latency's job).
    await RisingEdge(dut.clk)

    gpio_out = int(dut.gpio_out_o.value)
    gpio_oe = int(dut.gpio_oe_o.value)
    assert gpio_out == out_pattern, f"gpio_out_o expected 0x{out_pattern:08x}, got 0x{gpio_out:08x}"
    assert gpio_oe == dir_pattern, f"gpio_oe_o expected 0x{dir_pattern:08x}, got 0x{gpio_oe:08x}"
    dut._log.info(f"gpio_out_o=0x{gpio_out:08x} gpio_oe_o=0x{gpio_oe:08x} mirror confirmed")


@cocotb.test()
async def test_gpio_data_in_sync_latency(dut):
    """Cycle-exact: GPIO_DATA_IN is stale through the first 2 clock edges after a pin change and
    becomes visible on the 3rd -- one edge per flop in the path, exactly as the RTL reads:
    gpio_in_i -> cdc_2ff_sync stage 0 (edge 1) -> stage 1, i.e. gpio_in_sync_q (edge 2) ->
    apb4_register_bank's GPIO_DATA_IN HW-write mirror (edge 3).

    Note this count only holds because every pin change in this file is driven while the
    simulator sits a step or two PAST a clock edge (each _peek() ends with `await Timer(1,
    units="step")`), so the new value is already settled when the very next edge samples it.
    Driving a pin in the same instant a RisingEdge fires would push everything one edge later.
    Sampled via _peek() -- no APB transaction, so no ambiguity from the BFM's own SETUP/ACCESS
    overhead is mixed into the count."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    test_pin = 5
    mask = 1 << test_pin

    # Idle-reset state already has paddr=0 (GPIO_DATA_IN), pwrite=0 -- _peek()'s precondition.
    data0 = await _peek(dut, GPIO_DATA_IN)
    assert data0 == 0, f"GPIO_DATA_IN must read 0 before any pin change, got 0x{data0:08x}"

    dut.gpio_in_i.value = mask  # T0: pin driven high

    data_t0 = await _peek(dut, GPIO_DATA_IN)
    assert data_t0 == 0, (
        f"GPIO_DATA_IN changed combinationally on a pin edge -- impossible for a synchronised "
        f"register, got 0x{data_t0:08x}"
    )

    for edge in (1, 2):
        await RisingEdge(dut.clk)
        data_n = await _peek(dut, GPIO_DATA_IN)
        assert data_n == 0, (
            f"GPIO_DATA_IN updated after only {edge} clock edge(s) -- expected still stale, "
            f"got 0x{data_n:08x}"
        )

    await RisingEdge(dut.clk)  # edge 3
    data_e3 = await _peek(dut, GPIO_DATA_IN)
    assert data_e3 == mask, (
        f"GPIO_DATA_IN must reflect the pin change exactly 3 clock edges after it, got "
        f"0x{data_e3:08x} at edge 3, expected 0x{mask:08x}"
    )
    dut._log.info("GPIO_DATA_IN sync latency confirmed: stale at edges 1-2, correct at edge 3")


@cocotb.test()
async def test_gpio_edge_capture_rising(dut):
    """TYPE=edge, POL=rising for one pin: GPIO_IRQ_STAT's bit for that pin sets exactly 3 clock
    edges after a 0->1 transition on gpio_in_i -- the same latency as GPIO_DATA_IN, because edge
    detection is built directly on gpio_in_sync_q (see test_gpio_data_in_sync_latency)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 2
    mask = 1 << test_pin

    ok1 = await bfm.write(GPIO_IRQ_TYPE, mask)
    assert ok1, "GPIO_IRQ_TYPE write returned SLVERR"
    ok2 = await bfm.write(GPIO_IRQ_POL, mask)
    assert ok2, "GPIO_IRQ_POL write returned SLVERR"
    # Clear the pending bit: it was left over from the level-mode reset default (see
    # test_gpio_reset_defaults) and the sticky formula preserves it across a TYPE/POL switch
    # unless a CLR write or a fresh edge is observed.
    ok3 = await bfm.write(GPIO_IRQ_CLR, mask)
    assert ok3, "GPIO_IRQ_CLR write returned SLVERR"

    stat0 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat0 & mask == 0, f"test pin's IRQ_STAT bit must be 0 after CLR, got stat=0x{stat0:08x}"

    dut.gpio_in_i.value = mask  # T0: rising transition on the test pin

    await ClockCycles(dut.clk, 2)
    stat_e2 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_e2 & mask == 0, (
        f"IRQ_STAT set after only 2 clock edges -- edge capture needs the full 3-edge latency, "
        f"got stat=0x{stat_e2:08x}"
    )

    await RisingEdge(dut.clk)  # edge 3
    stat_e3 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_e3 & mask == mask, (
        f"IRQ_STAT bit for pin {test_pin} must be set exactly 3 edges after the rising "
        f"transition, got stat=0x{stat_e3:08x}"
    )
    dut._log.info(f"Rising-edge capture confirmed at edge 3: stat=0x{stat_e3:08x}")


@cocotb.test()
async def test_gpio_edge_capture_falling(dut):
    """TYPE=edge, POL=falling (default POL=0): GPIO_IRQ_STAT's bit sets exactly 3 clock edges
    after a 1->0 transition on gpio_in_i (see test_gpio_data_in_sync_latency for the latency
    derivation)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 7
    mask = 1 << test_pin

    # Drive the pin high FIRST and let it settle -- this is only establishing a stable starting
    # level, not the latency-critical transition, so a generous margin is fine here.
    dut.gpio_in_i.value = mask
    await ClockCycles(dut.clk, 6)

    ok1 = await bfm.write(GPIO_IRQ_TYPE, mask)  # POL left at default 0 == falling
    assert ok1, "GPIO_IRQ_TYPE write returned SLVERR"
    ok2 = await bfm.write(GPIO_IRQ_CLR, mask)
    assert ok2, "GPIO_IRQ_CLR write returned SLVERR"

    stat0 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat0 & mask == 0, f"test pin's IRQ_STAT bit must be 0 after CLR, got stat=0x{stat0:08x}"

    dut.gpio_in_i.value = 0  # T0: falling transition on the test pin

    await ClockCycles(dut.clk, 2)
    stat_e2 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_e2 & mask == 0, (
        f"IRQ_STAT set after only 2 clock edges -- edge capture needs the full 3-edge latency, "
        f"got stat=0x{stat_e2:08x}"
    )

    await RisingEdge(dut.clk)  # edge 3
    stat_e3 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_e3 & mask == mask, (
        f"IRQ_STAT bit for pin {test_pin} must be set exactly 3 edges after the falling "
        f"transition, got stat=0x{stat_e3:08x}"
    )
    dut._log.info(f"Falling-edge capture confirmed at edge 3: stat=0x{stat_e3:08x}")


@cocotb.test()
async def test_gpio_level_high(dut):
    """TYPE=level (default), POL=rising: the STAT bit for the test pin LIVE-tracks the pin --
    0 while low, set (with the usual 3-edge sync latency) once driven high."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 9
    mask = 1 << test_pin

    ok = await bfm.write(GPIO_IRQ_POL, mask)  # TYPE left at default 0 == level
    assert ok, "GPIO_IRQ_POL write returned SLVERR"

    # GPIO_IRQ_POL commits on the write's ACCESS edge; GPIO_IRQ_STAT is recomputed from it and
    # registered on the NEXT edge. Peeking without this wait reads the pre-write STAT, where
    # this pin was still POL=0 (active-LOW) and therefore set.
    await RisingEdge(dut.clk)

    stat0 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat0 & mask == 0, f"level-high bit must be 0 while the pin is low, got stat=0x{stat0:08x}"

    dut.gpio_in_i.value = mask
    await ClockCycles(dut.clk, 4)  # comfortably past the 3-edge sync/capture latency

    stat1 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat1 & mask == mask, f"level-high bit must be set once the pin is high, got stat=0x{stat1:08x}"
    dut._log.info(f"Level-high tracking confirmed: stat=0x{stat1:08x}")


@cocotb.test()
async def test_gpio_level_low(dut):
    """TYPE=level, POL=falling (default POL=0): the STAT bit LIVE-tracks the pin's low state --
    driving the pin high clears it, driving it back low sets it again."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)

    test_pin = 11
    mask = 1 << test_pin

    # gpio_in_i defaults to 0 out of reset, so the level-low condition starts TRUE (matches
    # test_gpio_reset_defaults); no register writes are needed for TYPE=0/POL=0 defaults.
    dut.gpio_in_i.value = mask  # drive high: level-low condition goes FALSE
    await ClockCycles(dut.clk, 10)
    stat_high = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_high & mask == 0, (
        f"level-low bit must clear once the pin is driven high, got stat=0x{stat_high:08x}"
    )

    dut.gpio_in_i.value = 0  # drive back low: level-low condition goes TRUE again
    await ClockCycles(dut.clk, 4)
    stat_low = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_low & mask == mask, (
        f"level-low bit must set once the pin is driven back low, got stat=0x{stat_low:08x}"
    )
    dut._log.info(f"Level-low tracking confirmed: high->0x{stat_high:08x} low->0x{stat_low:08x}")


@cocotb.test()
async def test_gpio_edge_sticky_and_clear(dut):
    """Edge-mode STAT bit stays set once captured (sticky) until a GPIO_IRQ_CLR write targeting
    it lands, with no coincident fresh edge."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 4
    mask = 1 << test_pin

    ok1 = await bfm.write(GPIO_IRQ_TYPE, mask)
    assert ok1
    ok2 = await bfm.write(GPIO_IRQ_POL, mask)  # rising
    assert ok2
    ok3 = await bfm.write(GPIO_IRQ_CLR, mask)
    assert ok3

    dut.gpio_in_i.value = mask
    await ClockCycles(dut.clk, 10)  # comfortably past the 4-edge capture latency

    stat_set = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_set & mask == mask, f"IRQ_STAT bit must be set (sticky) after the edge, got 0x{stat_set:08x}"

    # Sticky: it must STAY set for many cycles with no further activity.
    await ClockCycles(dut.clk, 10)
    stat_still_set = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_still_set & mask == mask, (
        f"IRQ_STAT bit must remain sticky-set with no CLR write, got 0x{stat_still_set:08x}"
    )

    ok4 = await bfm.write(GPIO_IRQ_CLR, mask)
    assert ok4, "GPIO_IRQ_CLR write returned SLVERR"
    stat_cleared = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_cleared & mask == 0, f"IRQ_STAT bit must clear after the CLR write, got 0x{stat_cleared:08x}"
    dut._log.info("Edge-mode sticky + clear-by-CLR confirmed")


@cocotb.test()
async def test_gpio_edge_set_beats_same_cycle_clear(dut):
    """A GPIO_IRQ_CLR write whose ACCESS-phase commit edge coincides EXACTLY with the edge that
    latches a fresh qualifying transition into IRQ_STAT must leave the bit SET, not cleared (the
    RTL's (stat & ~clr) | edge_event formula ORs edge_event in unconditionally -- see
    gpio_controller.sv header). Raw APB signals (not APB4Master) are used so the CLR write's own
    SETUP/ACCESS edges can be aligned cycle-exact against the pin transition's own 3-edge
    latency (see test_gpio_data_in_sync_latency)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 6
    mask = 1 << test_pin

    ok1 = await bfm.write(GPIO_IRQ_TYPE, mask)
    assert ok1
    ok2 = await bfm.write(GPIO_IRQ_POL, mask)  # rising
    assert ok2
    ok3 = await bfm.write(GPIO_IRQ_CLR, mask)  # start from a known-clear state
    assert ok3
    stat0 = await _peek(dut, GPIO_IRQ_STAT)
    assert stat0 & mask == 0, f"precondition failed: test pin's IRQ_STAT bit not clear, got 0x{stat0:08x}"

    dut.gpio_in_i.value = mask  # T0: rising transition -- natural capture lands at edge 3
    # (see test_gpio_data_in_sync_latency for the 3-edge derivation)

    await RisingEdge(dut.clk)  # edge 1 (rel T0)
    # Arm the CLR write's SETUP phase now, so its own SETUP edge is edge 2 and its ACCESS
    # (commit) edge is edge 3 -- exactly the natural capture edge.
    _raw_write_setup(dut, GPIO_IRQ_CLR, mask)
    await RisingEdge(dut.clk)  # edge 2 (rel T0) -- CLR write's SETUP edge
    _raw_write_access(dut)
    await RisingEdge(dut.clk)  # edge 3 (rel T0) -- CLR write's ACCESS/commit edge == capture edge
    _raw_write_idle(dut)

    stat_race = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_race & mask == mask, (
        f"a GPIO_IRQ_CLR write landing on the SAME edge as a fresh qualifying transition must "
        f"leave the bit SET (set beats clear), got 0x{stat_race:08x}"
    )
    dut._log.info(f"Set-beats-same-cycle-clear confirmed: stat=0x{stat_race:08x}")


@cocotb.test()
async def test_gpio_level_clr_has_no_effect(dut):
    """GPIO_IRQ_CLR has NO effect on a level-mode bit -- only the level condition itself (or
    GPIO_IRQ_EN, which only gates irq_o) controls it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 13
    mask = 1 << test_pin

    ok = await bfm.write(GPIO_IRQ_POL, mask)  # TYPE left at default 0 == level, active-high
    assert ok

    dut.gpio_in_i.value = mask
    await ClockCycles(dut.clk, 10)
    stat_before = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_before & mask == mask, f"level bit must be set with the pin driven high, got 0x{stat_before:08x}"

    ok2 = await bfm.write(GPIO_IRQ_CLR, mask)
    assert ok2, "GPIO_IRQ_CLR write returned SLVERR"
    await ClockCycles(dut.clk, 2)

    stat_after = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_after & mask == mask, (
        f"level-mode IRQ_STAT bit must be UNAFFECTED by a GPIO_IRQ_CLR write, "
        f"before=0x{stat_before:08x} after=0x{stat_after:08x}"
    )
    dut._log.info("Level-mode CLR-has-no-effect confirmed")


@cocotb.test()
async def test_gpio_irq_clr_pstrb_partial_word(dut):
    """A partial-word GPIO_IRQ_CLR write (pstrb selecting only byte 0) must clear only the pins
    in that byte -- a pin in a non-strobed byte must remain set."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    pin_byte0 = 3    # bit 3, byte 0
    pin_byte1 = 12   # bit 12, byte 1
    mask_byte0 = 1 << pin_byte0
    mask_byte1 = 1 << pin_byte1
    mask_both = mask_byte0 | mask_byte1

    ok1 = await bfm.write(GPIO_IRQ_TYPE, mask_both)
    assert ok1
    ok2 = await bfm.write(GPIO_IRQ_POL, mask_both)  # both rising
    assert ok2
    ok3 = await bfm.write(GPIO_IRQ_CLR, mask_both)  # start clear
    assert ok3

    dut.gpio_in_i.value = mask_both
    await ClockCycles(dut.clk, 10)
    stat_set = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_set & mask_both == mask_both, f"both pins must be set before the partial clear, got 0x{stat_set:08x}"

    # strb=0x1 selects byte 0 only -- pin_byte0's bit must clear, pin_byte1's bit must survive.
    ok4 = await bfm.write(GPIO_IRQ_CLR, mask_both, strb=0x1)
    assert ok4, "partial-word GPIO_IRQ_CLR write returned SLVERR"

    stat_after = await _peek(dut, GPIO_IRQ_STAT)
    assert stat_after & mask_byte0 == 0, (
        f"pin {pin_byte0} (strobed byte) must be cleared by the partial-word CLR, got 0x{stat_after:08x}"
    )
    assert stat_after & mask_byte1 == mask_byte1, (
        f"pin {pin_byte1} (non-strobed byte) must remain SET by the partial-word CLR, got 0x{stat_after:08x}"
    )
    dut._log.info(f"pstrb partial-word IRQ_CLR confirmed: stat=0x{stat_after:08x}")


@cocotb.test()
async def test_gpio_irq_en_masks_output_only(dut):
    """GPIO_IRQ_EN masks irq_o only -- GPIO_IRQ_STAT capture happens regardless of it. Enabling
    the pin afterwards asserts irq_o immediately (purely combinational, no extra latency)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 8
    mask = 1 << test_pin

    ok1 = await bfm.write(GPIO_IRQ_TYPE, mask)
    assert ok1
    ok2 = await bfm.write(GPIO_IRQ_POL, mask)  # rising
    assert ok2
    ok3 = await bfm.write(GPIO_IRQ_CLR, mask)
    assert ok3
    # GPIO_IRQ_EN left at its reset default (0) -- this pin's event must still be captured.

    dut.gpio_in_i.value = mask
    await ClockCycles(dut.clk, 10)

    stat = await _peek(dut, GPIO_IRQ_STAT)
    assert stat & mask == mask, f"IRQ_STAT must capture the event even with IRQ_EN==0, got 0x{stat:08x}"
    # irq_o is combinational off regs_o. As with _peek(), cocotb's VPI write/read alone does not
    # make Verilator re-evaluate combinational logic -- a simulator time step must elapse first.
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 0, (
        f"irq_o must stay 0 while IRQ_EN==0 for this pin, got {int(dut.irq_o.value)}"
    )

    ok4 = await bfm.write(GPIO_IRQ_EN, mask)
    assert ok4, "GPIO_IRQ_EN write returned SLVERR"
    await Timer(1, units="step")
    assert int(dut.irq_o.value) == 1, (
        f"irq_o must assert immediately once IRQ_EN is set for a pending pin, got {int(dut.irq_o.value)}"
    )
    dut._log.info("IRQ_EN masks irq_o only, independent of IRQ_STAT capture -- confirmed")


@cocotb.test()
async def test_gpio_irq_level_held_across_cycles(dut):
    """irq_o stays asserted across many consecutive clock cycles once its condition holds --
    level-held, never a single-cycle pulse (required so the SoC's plain 2-FF IRQ synchroniser
    can observe it, per gpio_controller.sv header)."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    test_pin = 15
    mask = 1 << test_pin

    ok1 = await bfm.write(GPIO_IRQ_POL, mask)  # level, active-high
    assert ok1
    ok2 = await bfm.write(GPIO_IRQ_EN, mask)
    assert ok2

    dut.gpio_in_i.value = mask
    await ClockCycles(dut.clk, 10)
    assert int(dut.irq_o.value) == 1, f"irq_o must be asserted before the hold-check window, got {int(dut.irq_o.value)}"

    for cycle in range(50):
        await RisingEdge(dut.clk)
        assert int(dut.irq_o.value) == 1, (
            f"irq_o dropped at cycle {cycle} of the 50-cycle hold window -- must be level-held, not a pulse"
        )
    dut._log.info("irq_o level-held across 50 consecutive cycles -- confirmed")


@cocotb.test()
async def test_gpio_irq_clr_reads_as_zero(dut):
    """GPIO_IRQ_CLR always reads back 0, regardless of what pattern was last written to it."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for pattern in (0xFFFF_FFFF, 0x1234_5678, 0x0000_0001):
        ok_w = await bfm.write(GPIO_IRQ_CLR, pattern)
        assert ok_w, f"GPIO_IRQ_CLR write(0x{pattern:08x}) returned SLVERR"
        data, ok_r = await bfm.read(GPIO_IRQ_CLR)
        assert ok_r, "GPIO_IRQ_CLR read returned SLVERR"
        assert data == 0, f"GPIO_IRQ_CLR must always read 0, got 0x{data:08x} after writing 0x{pattern:08x}"
    dut._log.info("GPIO_IRQ_CLR reads-as-zero confirmed across multiple written patterns")


@cocotb.test()
async def test_gpio_out_of_range_access(dut):
    """Word index >= 8 (byte offset >= 0x020, within the 12-bit ADDR_W slot) is out of range:
    writes are silently dropped and reads return 0, both with pslverr==0 (OKAY) per the register
    bank's out-of-range policy."""
    _kill_active_tasks()
    await _start_clock_and_reset(dut)
    bfm = _make_apb_bfm(dut)

    for addr in (GPIO_OUT_OF_RANGE, 0x0FC):
        ok_w = await bfm.write(addr, 0xFFFF_FFFF)
        assert ok_w, f"out-of-range write to 0x{addr:03x} must return OKAY (pslverr=0), got SLVERR"
        data, ok_r = await bfm.read(addr)
        assert ok_r, f"out-of-range read from 0x{addr:03x} must return OKAY (pslverr=0), got SLVERR"
        assert data == 0, f"out-of-range read from 0x{addr:03x} must return 0, got 0x{data:08x}"
    dut._log.info("out-of-range access policy (drop write, read 0, pslverr=0) confirmed")
