"""test_i2c.py -- Phase 6a-5 cocotb L1 protocol verification for i2c_controller
(rtl/periph/i2c_controller.sv, bead claude_verilog_test-f7vs.9, docs/PHASE6_IP_EXPANSION_PLAN.md
Sec.7 "6a-5 -- I2C").

WRITTEN AFTER THE RTL -- READ THIS BEFORE TRUSTING A GREEN RUN.  Every other peripheral in this
tree had its suite written first.  The I2C bit engine could not be: the bus BFM
(tb/cocotb/bfm/i2c_slave.py) cannot be developed without a DUT to talk to.  A suite written
against an implementation can simply encode what the implementation does, bugs included, so a
green run proves nothing by itself.  The assertions below are therefore derived from the I2C
specification and from the DUT header's CONTRACT (register map, command semantics, timing rules),
never from reading the FSM, and the suite was then PROVEN NON-VACUOUS by mutation testing: the
RTL was broken one fault at a time (ACK polarity, clock-stretch wait, arbitration compare,
repeated-START path, sticky set-vs-clear precedence, plus further faults) and each mutant was
shown to be caught by a named test.  The mutation table lives in the bead notes / PR description;
the tests most responsible for each kill carry a "MUTATION TARGET" line in their docstring so a
future edit that weakens one is visible.

DUT: tb_i2c (standalone wrapper around i2c_controller, ADDR_W=12, CLKDIV_MIN=3).  The pad inputs
are plain top-level inputs: tb/cocotb/bfm/i2c_slave.py closes the loop (wired-AND of master oe,
slave drive, forced-low hooks, driven back on the clock's FALLING edge -- see its docstring for
the negedge trap), so the wrapper cannot mask a polarity bug.

Register map (word index * 4): CTRL 0x00, STATUS 0x04, CLKDIV 0x08, ADDR 0x0C, TX_DATA 0x10,
RX_DATA 0x14, CMD 0x18, FIFO_STAT 0x1C, TIMEOUT 0x20, IRQ_EN 0x24, IRQ_STAT 0x28, IRQ_CLR 0x2C;
word index >= 12 (0x030..0xFFC) reads 0, writes are dropped, pslverr stays 0.

Timing conventions used by the checks below.  A "tick" is CLKDIV_eff + 1 clk; one SCL period is
four ticks plus the synchroniser wait the bit engine inserts after it releases SCL (it must see
the SYNCHRONISED SCL high before it starts the high interval, so a bit costs 4 ticks + about
SYNC_STAGES + 1 clk).  The header's "f_scl = f_clk / (4 * (CLKDIV + 1))" is the no-stretch,
zero-latency ideal; test_i2c_clkdiv_100k_400k pins the measured behaviour and bounds the
difference.  Most protocol tests run at CLKDIV = 3 (the hardware minimum, tick = 4 clk) for speed
AND because it is the worst case for the synchroniser-latency margin.

Cycle-sampling hazard (learned on GPIO, repeated here): a value read straight after
`await RisingEdge` can be the PRE-edge value.  Every internal-state read below goes
RisingEdge -> Timer(1, "step") first (the settled post-edge state), and register reads that must
be side-effect free use _peek() (documented in test_gpio.py).

Tests (grouped; the name states the behaviour):
  register file   reset_defaults, rw_roundtrip_and_masks, pstrb_partial_word, out_of_range_access,
                  clkdiv_clamp_to_min, clkdiv_min_guard_rejects_elaboration
  data transfer   byte_write, byte_read, multibyte_write, multibyte_read,
  repeated_start_register_read,
                  back_to_back_transactions, cmd_count_zero_means_one, cmd_write_wins_over_read
  errors          address_nack, data_nack, nack_without_stop_holds_bus
  command accept  cmd_ignored_when_disabled_busy_or_illegal, en_disable_aborts_and_flushes,
                  reset_mid_transaction
  clock stretch   clock_stretch_honoured, clock_stretch_every_bit
  timeout         timeout_stuck_scl, timeout_scales_with_clkdiv_and_value, timeout_bus_busy_wait,
                  timeout_fifo_starvation, timeout_zero_disables
  arbitration     arbitration_loss_address_bit, arbitration_loss_data_bit,
                  arbitration_loss_read_nack_slot, arbitration_no_false_loss_when_sending_zero,
                  arbitration_loss_repeated_start_setup
  FIFOs           tx_fifo_fill_drain_and_stat, tx_fifo_refill_during_transfer,
                  rx_fifo_fill_drain_and_stat, rx_fifo_full_holds_scl_low, rx_empty_read_is_zero
  IRQ             rx_threshold_irq, irq_sources_and_w1c, sticky_set_wins_over_clear
  rate / loopback clkdiv_100k_400k, loopback_write_then_read, status_reflects_bus_levels
"""

import subprocess
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

_TB_DIR = Path(__file__).resolve().parent.parent
if str(_TB_DIR) not in sys.path:
    sys.path.insert(0, str(_TB_DIR))

from bfm.apb4_master import APB4Master  # noqa: E402
from bfm.i2c_slave import I2CSlave  # noqa: E402

_PROJ_ROOT = Path(__file__).resolve().parent.parent.parent.parent

CLK_PERIOD_NS = 10  # 100 MHz -- matches SoC reference clock (same convention as test_gpio.py)

I2C_CTRL = 0x000
I2C_STATUS = 0x004
I2C_CLKDIV = 0x008
I2C_ADDR = 0x00C
I2C_TX_DATA = 0x010
I2C_RX_DATA = 0x014
I2C_CMD = 0x018
I2C_FIFO_STAT = 0x01C
I2C_TIMEOUT = 0x020
I2C_IRQ_EN = 0x024
I2C_IRQ_STAT = 0x028
I2C_IRQ_CLR = 0x02C
I2C_OUT_OF_RANGE = 0x030  # word index 12 -- first address past the 12-register map

CTRL_EN = 0x1
CTRL_LOOP = 0x2

# I2C_STATUS bits
ST_BUSY, ST_TXN, ST_NACK, ST_ARB, ST_TOUT, ST_SCL, ST_SDA = (1 << i for i in range(7))
# I2C_IRQ_STAT / IRQ_EN / IRQ_CLR bits
IRQ_DONE, IRQ_NACK, IRQ_ARB, IRQ_TOUT, IRQ_RXTHR = 1, 2, 4, 8, 16
IRQ_STICKY = 0xF

SLAVE_ADDR = 0x50
FAST_DIV = 3  # hardware minimum (tick = 4 clk): fastest legal, worst sync-latency margin
TICK = FAST_DIV + 1  # clk cycles per engine tick at FAST_DIV
FIFO_DEPTH = 8
SYNC_STAGES = 2  # cdc_2ff_sync depth the DUT header documents for both pad inputs

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cmd(start=0, write=0, read=0, stop=0, nack_last=0, count=0) -> int:
    """Encode an I2C_CMD word: [0] START [1] WRITE [2] READ [3] STOP [4] NACK_LAST [15:8] COUNT."""
    return (
        start | (write << 1) | (read << 2) | (stop << 3) | (nack_last << 4) | ((count & 0xFF) << 8)
    )


async def _start_clock_and_reset(dut, address: int = SLAVE_ADDR):
    """Start the 100 MHz clock, idle the APB4 bus, release the pads, start the bus BFM and apply
    synchronous reset. Returns (apb, slave)."""
    _kill_active_tasks()
    clk_task = await cocotb.start(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())
    _active_tasks.append(clk_task)

    dut.rst_n.value = 0
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = 0
    dut.pwdata.value = 0
    dut.pstrb.value = 0xF

    slave = I2CSlave(dut, "i2c_", dut.clk, address=address)
    _active_tasks.append(slave.start())

    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 4)  # let the pad synchronisers fill with the released bus
    apb = APB4Master(dut, "", dut.clk)
    return apb, slave


async def _setup(
    dut, clkdiv: int = FAST_DIV, address: int = SLAVE_ADDR, timeout=None, enable: bool = True
):
    """Reset + enable the controller at `clkdiv`. Returns (apb, slave)."""
    apb, slave = await _start_clock_and_reset(dut, address)
    await apb.write(I2C_CLKDIV, clkdiv)
    if timeout is not None:
        await apb.write(I2C_TIMEOUT, timeout)
    if enable:
        await apb.write(I2C_CTRL, CTRL_EN)
    return apb, slave


async def _peek(dut, addr: int) -> int:
    """Side-effect-free live register sample (see test_gpio.py::_peek for the cocotb/Verilator
    gotcha it works around): point the idle bus's combinational prdata at `addr`, settle one
    simulator time step, read."""
    dut.pwrite.value = 0
    dut.paddr.value = addr
    await Timer(1, units="step")
    return int(dut.prdata.value)


def _raw_write_setup(dut, addr: int, data: int) -> None:
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 1
    dut.paddr.value = addr
    dut.pwdata.value = data
    dut.pstrb.value = 0xF


def _raw_write_access(dut) -> None:
    dut.penable.value = 1


def _raw_write_idle(dut) -> None:
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0


async def _settled_edge(dut) -> None:
    """Advance one clock edge and return in the settled post-edge state."""
    await RisingEdge(dut.clk)
    await Timer(1, units="step")


async def _wait_idle(dut, limit: int = 60000, what: str = "engine to go idle") -> int:
    """Poll I2C_STATUS.busy every cycle until it clears; return the IRQ_STAT snapshot taken
    two clocks later. STATUS/IRQ_STAT mirror the NEXT-state value (the DUT header's "so a read one
    transfer after an event cannot see stale data"), so busy drops one clock BEFORE the registered
    oe/state flops move; the two settle clocks make the line levels final before the caller looks
    at them. Fails (with the last STATUS) if busy never clears within `limit` cycles."""
    for _ in range(limit):
        await _settled_edge(dut)
        st = await _peek(dut, I2C_STATUS)
        if not st & ST_BUSY:
            await _settled_edge(dut)
            await _settled_edge(dut)
            return await _peek(dut, I2C_IRQ_STAT)
    raise AssertionError(
        f"timed out after {limit} cycles waiting for the {what}; "
        f"STATUS=0x{await _peek(dut, I2C_STATUS):x}"
    )


async def _run(dut, apb, word: int, limit: int = 60000) -> int:
    """Issue one I2C_CMD word and wait for the engine to go idle; returns IRQ_STAT."""
    await apb.write(I2C_CMD, word)
    return await _wait_idle(dut, limit)


async def _push(apb, data) -> None:
    for b in data:
        await apb.write(I2C_TX_DATA, b)


async def _drain_rx(apb) -> list:
    """Pop RX_DATA until FIFO_STAT says rx_empty; returns the bytes."""
    out = []
    for _ in range(FIFO_DEPTH + 2):
        fs, _ok = await apb.read(I2C_FIFO_STAT)
        if fs & 0x800:
            break
        v, _ok = await apb.read(I2C_RX_DATA)
        out.append(v)
    return out


async def _rd(apb, addr: int) -> int:
    v, ok = await apb.read(addr)
    assert ok, f"unexpected pslverr on read of 0x{addr:03x}"
    return v


def _bit_idx(byte_n: int, bit: int) -> int:
    """SCL-fall index (BFM numbering) preceding bit `bit` of byte `byte_n` (0 = address byte);
    byte_n's ACK slot is bit 8."""
    return 9 * byte_n + bit


# ---------------------------------------------------------------------------
# Data-transfer tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_byte_write(dut):
    """One data byte to the slave: START, address+W, byte, STOP. The slave must see exactly that
    event sequence with the byte value-exact, the master must report `done` only (no nack/arb/
    timeout), release both lines afterwards and leave the TX FIFO empty."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)  # write
    await _push(apb, [0xC3])
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))

    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0xC3, True),
        ("STOP",),
    ], slave.events
    assert stat == IRQ_DONE, f"IRQ_STAT=0x{stat:x}, expected only done"
    assert await _rd(apb, I2C_STATUS) & (ST_BUSY | ST_TXN | ST_NACK | ST_ARB | ST_TOUT) == 0
    assert (await _rd(apb, I2C_FIFO_STAT)) & 0xFF == 0, "TX FIFO not drained"
    assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0, (
        "lines not released after STOP"
    )
    slave.assert_clean()


@cocotb.test()
async def test_i2c_byte_read(dut):
    """One byte read: START, address+R, byte, NACK (NACK_LAST), STOP. The byte lands in the RX FIFO
    value-exact, the master NACKed it (the I2C way to end a read), and an APB read of RX_DATA pops
    it. IRQ_STAT[4] (rx threshold, a LIVE level, threshold 0 behaves as 1) follows the FIFO and is
    masked out of the sticky comparison."""
    apb, slave = await _setup(dut)
    slave.read_queue = [0x9E]
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    stat = await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1))

    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 1, True),
        ("RD", 0x9E, False),
        ("STOP",),
    ], slave.events
    assert stat & IRQ_STICKY == IRQ_DONE, f"IRQ_STAT=0x{stat:x}"
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert (fs >> 4) & 0xF == 1 and not fs & 0x800, f"FIFO_STAT=0x{fs:x}: rx_level should be 1"
    assert await _rd(apb, I2C_RX_DATA) == 0x9E
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert (fs >> 4) & 0xF == 0 and fs & 0x800, f"FIFO_STAT=0x{fs:x}: read must pop the byte"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_multibyte_write(dut):
    """Five bytes in one command (register pointer + 4 payload bytes) land in the slave's memory
    in order. Every byte is ACKed and logged value-exact."""
    apb, slave = await _setup(dut)
    payload = [0x20, 0x11, 0x22, 0x33, 0x44]
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, payload)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=len(payload)))

    want = (
        [("START",), ("ADDR", SLAVE_ADDR, 0, True)]
        + [("WR", b, True) for b in payload]
        + [("STOP",)]
    )
    assert slave.events == want, slave.events
    assert bytes(slave.mem[0x20:0x24]) == bytes([0x11, 0x22, 0x33, 0x44])
    assert stat & IRQ_STICKY == IRQ_DONE
    slave.assert_clean()


@cocotb.test()
async def test_i2c_multibyte_read(dut):
    """Seven bytes read in one command: the first six are ACKed, the seventh NACKed (NACK_LAST),
    all land in the RX FIFO in order. A second command with NACK_LAST = 0 ACKs EVERY byte
    including the last (the next byte the slave presents has its MSB high so it cannot hold SDA
    low and wedge the STOP)."""
    apb, slave = await _setup(dut)
    slave.mem[:] = b"\xff" * 256
    pattern = [0xA0 + i for i in range(7)]
    slave.read_queue = list(pattern)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=7))

    rds = [e for e in slave.events if e[0] == "RD"]
    assert [e[1] for e in rds] == pattern, rds
    assert [e[2] for e in rds] == [True] * 6 + [False], f"ACK pattern wrong: {rds}"
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert (fs >> 4) & 0xF == 7, f"FIFO_STAT=0x{fs:x}"
    got = await _drain_rx(apb)
    assert got == pattern, f"RX FIFO order/value mismatch: {got}"

    # NACK_LAST = 0: all three bytes ACKed; the bus is then held for a STOP-only command.
    slave.reset_log()
    slave.read_queue = [0x11, 0x22, 0x33]
    await _run(dut, apb, cmd(start=1, read=1, nack_last=0, count=3))
    rds = [e for e in slave.events if e[0] == "RD"]
    assert rds == [("RD", 0x11, True), ("RD", 0x22, True), ("RD", 0x33, True)], rds
    await _run(dut, apb, cmd(stop=1))
    assert slave.events[-1] == ("STOP",), slave.events
    assert await _drain_rx(apb) == [0x11, 0x22, 0x33]
    slave.assert_clean()


@cocotb.test()
async def test_i2c_repeated_start_register_read(dut):
    """THE register-read pattern the bead requires: write the register pointer WITHOUT a STOP, then
    a repeated START, address+R, read 4 bytes, NACK the last, STOP. The slave must log an RSTART
    (a START arriving with no STOP in between) and NO STOP before it; the bus must stay held
    between the two commands (txn_active = 1, SCL driven low); the data must come from the pointer.
    MUTATION TARGET: emitting STOP+START instead of a repeated START."""
    apb, slave = await _setup(dut)
    for i, b in enumerate([0x5A, 0xA5, 0x3C, 0xC3]):
        slave.mem[0x40 + i] = b
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x40)
    stat = await _run(dut, apb, cmd(start=1, write=1, count=1))  # no STOP
    assert stat & IRQ_STICKY == IRQ_DONE
    assert slave.events == [("START",), ("ADDR", SLAVE_ADDR, 0, True), ("WR", 0x40, True)], (
        f"first half must not end with a STOP: {slave.events}"
    )
    st = await _rd(apb, I2C_STATUS)
    assert st & ST_TXN, f"txn_active must stay set while the bus is held (STATUS=0x{st:x})"
    assert not st & ST_BUSY
    assert int(dut.i2c_scl_oe_o.value) == 1, "SCL must be held low between the two commands"

    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=4))
    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0x40, True),
        ("RSTART",),
        ("ADDR", SLAVE_ADDR, 1, True),
        ("RD", 0x5A, True),
        ("RD", 0xA5, True),
        ("RD", 0x3C, True),
        ("RD", 0xC3, False),
        ("STOP",),
    ], slave.events
    assert await _drain_rx(apb) == [0x5A, 0xA5, 0x3C, 0xC3]
    assert not await _rd(apb, I2C_STATUS) & ST_TXN, "STOP must clear txn_active"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_continuation_commands_without_start(dut):
    """WRITE-only and READ-only commands continue a held transfer WITHOUT a START: the bus is held
    (txn_active) after the first command, further bytes follow with no address phase and no
    START/STOP on the wire, and a final READ-only command with NACK_LAST + STOP closes it. (Found by
    the coverage pass: the `S_IDLE` accept path for a data-only command was never executed.)"""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x10)
    await _run(dut, apb, cmd(start=1, write=1, count=1))  # address + pointer, bus held
    await _push(apb, [0xA1, 0xA2, 0xA3])
    stat = await _run(dut, apb, cmd(write=1, count=3))  # WRITE-only continuation
    assert stat & IRQ_STICKY == IRQ_DONE
    assert await _rd(apb, I2C_STATUS) & ST_TXN, "bus must still be held after a stop-less WRITE"
    assert bytes(slave.mem[0x10:0x13]) == bytes([0xA1, 0xA2, 0xA3])

    slave.read_queue = [0x51, 0x52, 0x53, 0x54]
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, nack_last=0, count=2))  # RSTART + 2 bytes, all ACKed
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await _run(dut, apb, cmd(read=1, nack_last=1, stop=1, count=2))  # READ-only continuation

    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0x10, True),
        ("WR", 0xA1, True),
        ("WR", 0xA2, True),
        ("WR", 0xA3, True),
        ("RSTART",),
        ("ADDR", SLAVE_ADDR, 1, True),
        ("RD", 0x51, True),
        ("RD", 0x52, True),
        ("RD", 0x53, True),
        ("RD", 0x54, False),
        ("STOP",),
    ], slave.events
    assert await _drain_rx(apb) == [0x51, 0x52, 0x53, 0x54]
    assert not await _rd(apb, I2C_STATUS) & ST_TXN
    slave.assert_clean()


@cocotb.test()
async def test_i2c_back_to_back_transactions(dut):
    """Write then read-back as two complete transactions (STOP, then a fresh START that must wait
    for the bus-free time). The slave memory round-trips the byte."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, [0x70, 0x6E])  # pointer, data
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=2))
    await _push(apb, [0x70])  # set pointer again
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1))

    assert await _drain_rx(apb) == [0x6E]
    kinds = [e[0] for e in slave.events]
    assert kinds == [
        "START",
        "ADDR",
        "WR",
        "WR",
        "STOP",
        "START",
        "ADDR",
        "WR",
        "STOP",
        "START",
        "ADDR",
        "RD",
        "STOP",
    ], kinds
    slave.assert_clean()


@cocotb.test()
async def test_i2c_cmd_count_zero_means_one(dut):
    """COUNT = 0 transfers exactly ONE data byte (header: 'COUNT 0 means 1'); the rest of the TX
    FIFO is untouched."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, [0x31, 0x32, 0x33])
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=0))
    wr = [e for e in slave.events if e[0] == "WR"]
    assert wr == [("WR", 0x31, True)], wr
    assert (await _rd(apb, I2C_FIFO_STAT)) & 0xF == 2, "two bytes must remain queued"

    # The READ side matters separately: the last-byte NACK is decided from the remaining byte count,
    # so COUNT = 0 must be treated as ONE byte there too (found by mutation:
    # a write is insensitive).
    slave.reset_log()
    slave.read_queue = [0xB2, 0xB3]
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=0))
    rds = [e for e in slave.events if e[0] == "RD"]
    assert rds == [("RD", 0xB2, False)], f"COUNT=0 read must be one byte, NACKed: {rds}"
    assert await _drain_rx(apb) == [0xB2]
    slave.assert_clean()


@cocotb.test()
async def test_i2c_cmd_write_wins_over_read(dut):
    """WRITE and READ both set: WRITE wins (header). One byte is written, nothing is read."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x77)
    await _run(dut, apb, cmd(start=1, write=1, read=1, stop=1, count=1))
    kinds = [e[0] for e in slave.events]
    assert kinds == ["START", "ADDR", "WR", "STOP"], slave.events
    assert slave.events[2] == ("WR", 0x77, True)
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x800 and (fs >> 4) & 0xF == 0, "a read must not have pushed the RX FIFO"
    slave.assert_clean()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_address_nack(dut):
    """Nobody ACKs the address: `nack` sets (sticky), the data phase is ABANDONED (the queued TX
    bytes are never popped), STOP is still sent because it was requested, `done` sets (a NACK is a
    normal completion), and no arbitration/timeout bit appears. Run twice: the slave refusing, and
    the address simply not matching any slave. A READ command into a NACK pushes nothing.
    MUTATION TARGET: inverted ACK/NACK sample polarity."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)

    for label, refuse in (("slave refuses", True), ("address mismatch", False)):
        slave.reset_log()
        slave.ack_address = not refuse
        slave.address = SLAVE_ADDR if refuse else SLAVE_ADDR ^ 0x01
        await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
        await _push(apb, [0x01, 0x02])
        stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=2))
        assert slave.events == [("START",), ("ADDR", SLAVE_ADDR, 0, False), ("STOP",)], (
            f"[{label}] {slave.events}"
        )
        assert stat & IRQ_STICKY == IRQ_DONE | IRQ_NACK, f"[{label}] IRQ_STAT=0x{stat:x}"
        assert await _rd(apb, I2C_STATUS) & (ST_NACK | ST_ARB | ST_TOUT) == ST_NACK
        assert (await _rd(apb, I2C_FIFO_STAT)) & 0xF == 2, (
            f"[{label}] data phase not abandoned: TX bytes were consumed"
        )
        await apb.write(I2C_CTRL, 0)  # flush the FIFO for the next round
        await apb.write(I2C_CTRL, CTRL_EN)

    # A READ into a NACKed address pushes nothing.
    slave.reset_log()
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    stat = await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=3))
    assert stat & IRQ_STICKY == IRQ_DONE | IRQ_NACK
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x800 and (fs >> 4) & 0xF == 0, f"FIFO_STAT=0x{fs:x}"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_data_nack(dut):
    """The slave ACKs the address but NACKs the second data byte of four: `nack` sets, the
    remaining bytes are ABANDONED (still queued in the TX FIFO), the already-ACKed byte stands,
    STOP is still sent, `done` sets. MUTATION TARGET: inverted ACK/NACK sample polarity."""
    apb, slave = await _setup(dut)
    slave.data_acks = [True, False]
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, [0x10, 0x20, 0x30, 0x40])
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=4))

    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0x10, True),
        ("WR", 0x20, False),
        ("STOP",),
    ], slave.events
    assert slave.received == [0x10]
    assert stat & IRQ_STICKY == IRQ_DONE | IRQ_NACK, f"IRQ_STAT=0x{stat:x}"
    assert (await _rd(apb, I2C_FIFO_STAT)) & 0xF == 2, "two bytes must remain queued"
    st = await _rd(apb, I2C_STATUS)
    assert st & ST_NACK and not st & (ST_BUSY | ST_TXN)
    slave.assert_clean()


@cocotb.test()
async def test_i2c_nack_without_stop_holds_bus(dut):
    """A NACK with no STOP requested leaves the bus HELD (txn_active = 1, SCL driven low) so
    software can issue a STOP-only command or a repeated START; both are exercised."""
    apb, slave = await _setup(dut)
    slave.ack_address = False
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    stat = await _run(dut, apb, cmd(start=1, write=1, count=1))  # no STOP
    assert stat & IRQ_STICKY == IRQ_DONE | IRQ_NACK
    st = await _rd(apb, I2C_STATUS)
    assert st & ST_TXN and not st & ST_BUSY, f"bus must be held after a stop-less NACK 0x{st:x}"
    assert int(dut.i2c_scl_oe_o.value) == 1
    assert ("STOP",) not in slave.events

    # (a) software ends it with a STOP-only command
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    stat = await _run(dut, apb, cmd(stop=1))
    assert slave.events[-1] == ("STOP",)
    assert stat & IRQ_STICKY == IRQ_DONE
    assert not await _rd(apb, I2C_STATUS) & ST_TXN

    # (b) or retries with a repeated START once the slave is willing
    slave.reset_log()
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_CTRL, 0)
    await apb.write(I2C_CTRL, CTRL_EN)
    slave.ack_address = False
    await _run(dut, apb, cmd(start=1, write=1, count=1))  # NACK, held again
    slave.ack_address = True
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_TX_DATA, 0x5C)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    kinds = [e[0] for e in slave.events]
    assert kinds == ["START", "ADDR", "RSTART", "ADDR", "WR", "STOP"], slave.events
    assert slave.events[1][3] is False and slave.events[3][3] is True
    assert slave.received == [0x5C]


# ---------------------------------------------------------------------------
# Command acceptance
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_cmd_ignored_when_disabled_busy_or_illegal(dut):
    """A command is accepted only with EN = 1, an idle engine, and a legal shape (START, or
    txn_active for WRITE/READ/STOP-only). Every other write is IGNORED SILENTLY: busy never rises,
    no bus activity, no status bit. Strobes matter too: a CMD write without pstrb[0] is no
    command. Each ignored case is followed by a proof that the controller is still sane."""
    apb, slave = await _setup(dut, enable=False)
    await apb.write(I2C_ADDR, SLAVE_ADDR)

    async def quiet(label: str, cycles: int = 80) -> None:
        for _ in range(cycles):
            await _settled_edge(dut)
            st = await _peek(dut, I2C_STATUS)
            assert not st & ST_BUSY, f"[{label}] busy rose (STATUS=0x{st:x})"
            assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0, (
                f"[{label}] a line was driven"
            )
        assert slave.events == [], f"[{label}] bus activity {slave.events}"
        assert await _peek(dut, I2C_IRQ_STAT) & IRQ_STICKY == 0, f"[{label}] status bit set"

    # EN = 0
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    await quiet("EN=0")
    await apb.write(I2C_CTRL, CTRL_EN)
    await _settled_edge(dut)

    # illegal shapes with no START and the bus not held
    for label, word in (
        ("WRITE-only, no txn", cmd(write=1, count=1)),
        ("READ-only, no txn", cmd(read=1, count=1)),
        ("STOP-only, no txn", cmd(stop=1)),
        ("no op bits, COUNT only", cmd(count=3)),
        ("empty", 0),
    ):
        await apb.write(I2C_CMD, word)
        await quiet(label, 40)

    # pstrb: lane 0 absent -> no command, even though the data word is a valid START|WRITE|STOP
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1), strb=0b1110)
    await quiet("pstrb[0]=0", 40)

    # While busy a second command is dropped: only the first transaction reaches the bus.
    await apb.write(I2C_TX_DATA, 0xAA)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    await apb.write(I2C_CMD, cmd(start=1, read=1, stop=1, nack_last=1, count=4))  # dropped
    await _wait_idle(dut)
    kinds = [e[0] for e in slave.events]
    assert kinds == ["START", "ADDR", "WR", "STOP"], f"busy-time command leaked: {slave.events}"
    assert slave.events[2] == ("WR", 0xAA, True)
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x800, "the dropped READ must not have pushed anything"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_en_disable_aborts_and_flushes(dut):
    """CTRL.EN = 0 mid-transfer: both lines released AT ONCE, txn_active cleared, NO event bit
    (no done/nack/arb/timeout), BOTH FIFOs flushed (once, on the 1 -> 0 edge), registers and
    pre-existing sticky flags RETAINED. After re-enable the flushed TX bytes are not replayed."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    # A pre-existing sticky flag (address NACK) that the abort must retain.
    slave.ack_address = False
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    slave.ack_address = True
    assert await _rd(apb, I2C_STATUS) & ST_NACK
    # An unpopped RX byte so the RX flush is observable.
    slave.read_queue = [0x66]
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1))
    assert (await _rd(apb, I2C_FIFO_STAT) >> 4) & 0xF == 1
    await apb.write(I2C_IRQ_CLR, IRQ_DONE)  # keep nack, drop done
    before = await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY

    # Start a 3-byte write, abort in the middle of the second data byte.
    slave.reset_log()
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, [0xB1, 0xB2, 0xB3, 0xB4, 0xB5])
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=3))
    for _ in range(3000):
        await _settled_edge(dut)
        if len([e for e in slave.events if e[0] == "WR"]) >= 1:
            break
    else:
        raise AssertionError("first data byte never reached the slave")
    await ClockCycles(dut.clk, 3 * TICK * 4 + 9)  # now inside the 2nd byte's data bits
    assert await _rd(apb, I2C_STATUS) & ST_BUSY, "precondition: transfer must still be running"
    await apb.write(I2C_CTRL, 0)  # <- abort

    await ClockCycles(dut.clk, 2)
    assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0, (
        "lines must be released immediately on EN=0"
    )
    await ClockCycles(dut.clk, 4)
    st = await _rd(apb, I2C_STATUS)
    assert not st & (ST_BUSY | ST_TXN), f"STATUS=0x{st:x}: abort must clear busy and txn_active"
    after = await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY
    assert after == before == IRQ_NACK, (
        f"abort must set NO event bit and keep the old ones (before 0x{before:x} after 0x{after:x})"
    )
    assert await _rd(apb, I2C_FIFO_STAT) == 0xA00, "both FIFOs must be flushed (tx+rx empty)"
    assert await _rd(apb, I2C_ADDR) == SLAVE_ADDR and await _rd(apb, I2C_CLKDIV) == FAST_DIV
    n_wr_at_abort = len([e for e in slave.events if e[0] == "WR"])

    # Re-enable: the controller works, and the flushed bytes are NOT replayed.
    slave.reset_state()
    slave.reset_log()
    await apb.write(I2C_CTRL, CTRL_EN)
    await apb.write(I2C_TX_DATA, 0xD7)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    assert [e for e in slave.events if e[0] == "WR"] == [("WR", 0xD7, True)], slave.events
    assert n_wr_at_abort >= 1


@cocotb.test()
async def test_i2c_reset_mid_transaction(dut):
    """A synchronous reset in the middle of a transfer returns EVERYTHING to the documented reset
    state: lines released, FIFOs empty, sticky flags clear, registers at their defaults, irq low."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_IRQ_EN, 0x1F)
    await _push(apb, [0xE1, 0xE2, 0xE3])
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=3))
    for _ in range(3000):
        await _settled_edge(dut)
        if len([e for e in slave.events if e[0] == "WR"]) >= 1:
            break
    await ClockCycles(dut.clk, 3 * TICK * 4 + 9)
    assert await _rd(apb, I2C_STATUS) & ST_BUSY

    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 6)
    assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0
    assert int(dut.irq_o.value) == 0
    assert await _rd(apb, I2C_CTRL) == 0
    assert await _rd(apb, I2C_CLKDIV) == 0xFF
    assert await _rd(apb, I2C_ADDR) == 0
    assert await _rd(apb, I2C_TIMEOUT) == 0xFFFF
    assert await _rd(apb, I2C_IRQ_EN) == 0
    assert await _rd(apb, I2C_FIFO_STAT) == 0xA00
    assert await _rd(apb, I2C_IRQ_STAT) == 0
    assert await _rd(apb, I2C_STATUS) & (ST_BUSY | ST_TXN | ST_NACK | ST_ARB | ST_TOUT) == 0


# ---------------------------------------------------------------------------
# Clock stretching
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_clock_stretch_honoured(dut):
    """The slave holds SCL low for 60 clk (15 ticks) at five different points of a one-byte write:
    an address bit, the address ACK slot, a data bit, the data ACK slot and the clock after the data
    ACK (which is the STOP's SCL-release wait). The master must NOT advance while it has released
    SCL and the line is still low: it may not change SDA or pull SCL low again (the BFM's
    `protocol_errors`), the transfer completes value-exact, and every SCL-high interval is at least
    one full tick (the high interval starts only once SCL is really high).
    MUTATION TARGET: bit engine advancing regardless of the synchronised scl_i."""
    apb, slave = await _setup(dut)
    stretch_falls = [3, 8, _bit_idx(1, 4), _bit_idx(1, 8), _bit_idx(2, 0)]
    for f in stretch_falls:
        slave.stretch_at_fall(f, 60)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x6D)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))

    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0x6D, True),
        ("STOP",),
    ], slave.events
    assert stat & IRQ_STICKY == IRQ_DONE
    slave.assert_clean()
    long_lows = [c for c in slave.scl_low_cycles if c >= 60]
    assert len(long_lows) == len(stretch_falls), (
        f"expected {len(stretch_falls)} stretched SCL-low intervals, saw {slave.scl_low_cycles}"
    )
    assert min(slave.scl_high_cycles) >= TICK, (
        f"an SCL-high interval shorter than one tick: {slave.scl_high_cycles}"
    )


@cocotb.test()
async def test_i2c_clock_stretch_every_bit(dut):
    """A slave that stretches EVERY SCL fall by 25 clk, through a 2-byte write and a 2-byte read
    (so the slave also presents read data while stretching). Data is value-exact both ways, nothing
    is mis-sampled, the master never advances early."""
    apb, slave = await _setup(dut)
    slave.stretch_every_fall(25)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, [0x08, 0x0F, 0x1E])  # pointer, 2 payload bytes
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=3))
    assert slave.received == [0x08, 0x0F, 0x1E]
    await apb.write(I2C_TX_DATA, 0x08)  # pointer, then read back
    await _run(dut, apb, cmd(start=1, write=1, count=1))
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=2))

    assert bytes(slave.mem[0x08:0x0A]) == bytes([0x0F, 0x1E]), "write under stretching did not land"
    assert await _drain_rx(apb) == [0x0F, 0x1E]
    rds = [e for e in slave.events if e[0] == "RD"]
    assert [e[2] for e in rds] == [True, False]
    assert len([c for c in slave.scl_low_cycles if c >= 25]) >= 60, slave.scl_low_cycles
    slave.assert_clean()


@cocotb.test()
async def test_i2c_clock_stretch_repeated_start_wait(dut):
    """The slave holds SCL low (manual hold) across the repeated-START setup. The master releases
    SCL, sees it low and must WAIT in the repeated-START wait state: no RSTART on the bus, busy
    stays set, SDA frozen, until the slave lets go; then the register read completes."""
    apb, slave = await _setup(dut)
    slave.mem[0x44] = 0xE7
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x44)
    await _run(dut, apb, cmd(start=1, write=1, count=1))

    slave.hold_scl_low(True)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await apb.write(I2C_CMD, cmd(start=1, read=1, stop=1, nack_last=1, count=1))
    await ClockCycles(dut.clk, 150)
    assert await _rd(apb, I2C_STATUS) & ST_BUSY, "engine must still be waiting"
    assert ("RSTART",) not in slave.events, (
        f"repeated START issued while SCL stretched: {slave.events}"
    )
    assert int(dut.i2c_scl_oe_o.value) == 0, "master must have released SCL and be waiting"
    slave.hold_scl_low(False)
    await _wait_idle(dut)
    assert slave.events[3:5] == [("RSTART",), ("ADDR", SLAVE_ADDR, 1, True)], slave.events
    assert await _drain_rx(apb) == [0xE7]
    slave.assert_clean()


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_timeout_stuck_scl(dut):
    """A dead slave holds SCL low mid-address (5000 clk, far past the 10-tick timeout). The
    sticky `timeout` bit sets INSTEAD of `done`; both lines are released, the engine goes idle and
    txn_active clears; the queued TX byte is untouched. After W1C and the slave coming back the
    controller recovers and completes a normal transfer."""
    apb, slave = await _setup(dut, timeout=10)
    slave.stretch_at_fall(3, 5000)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0xAB)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=3000)

    assert stat & IRQ_STICKY == IRQ_TOUT, f"IRQ_STAT=0x{stat:x}: only timeout may set"
    st = await _rd(apb, I2C_STATUS)
    assert st & ST_TOUT and not st & (ST_BUSY | ST_TXN | ST_NACK | ST_ARB), f"STATUS=0x{st:x}"
    assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0, (
        "timeout must release both lines"
    )
    assert slave.events == [("START",)], slave.events
    assert (await _rd(apb, I2C_FIFO_STAT)) & 0xF == 1, "TX byte must be untouched"
    assert slave.stretching, "precondition: the slave is still holding SCL"

    # Recovery.
    slave.reset_state()
    slave.reset_log()
    await apb.write(I2C_IRQ_CLR, IRQ_TOUT)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == 0
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    assert stat & IRQ_STICKY == IRQ_DONE
    assert slave.events == [
        ("START",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0xAB, True),
        ("STOP",),
    ], slave.events


async def _timeout_latency(dut, apb, slave, tmo: int, div: int) -> int:
    """Clocks from the commit of a START command until IRQ_STAT.timeout is visible, with SDA held
    low by 'another device' so the engine sits in the pre-START bus-free wait."""
    await apb.write(I2C_CLKDIV, div)
    await apb.write(I2C_TIMEOUT, tmo)
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    slave.hold_sda_low(True)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    n = 0
    for n in range(1, 4000):
        await _settled_edge(dut)
        if await _peek(dut, I2C_IRQ_STAT) & IRQ_TOUT:
            break
    else:
        raise AssertionError(f"no timeout within 4000 clk (tmo={tmo}, div={div})")
    slave.hold_sda_low(False)
    await ClockCycles(dut.clk, 6)
    return n


@cocotb.test()
async def test_i2c_timeout_scales_with_clkdiv_and_value(dut):
    """I2C_TIMEOUT is in engine TICKS and a tick is CLKDIV+1 clk, so the expiry latency is exactly
    TIMEOUT * (CLKDIV + 1) + K for one constant K. Measured at four (TIMEOUT, CLKDIV) points."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    points = [(8, 3), (24, 3), (8, 7), (1, 3)]
    ks = {}
    for tmo, div in points:
        lat = await _timeout_latency(dut, apb, slave, tmo, div)
        ks[(tmo, div)] = lat - tmo * (div + 1)
        await apb.write(I2C_CTRL, 0)  # drop the aborted command's leftovers
        await apb.write(I2C_CTRL, CTRL_EN)
        await ClockCycles(dut.clk, 8)
    assert len(set(ks.values())) == 1, (
        f"timeout latency is not TIMEOUT*(CLKDIV+1)+K for a constant K: residuals {ks}"
    )
    assert 0 <= next(iter(ks.values())) <= 8, f"implausible constant offset: {ks}"


@cocotb.test()
async def test_i2c_timeout_bus_busy_wait(dut):
    """The pre-START bus-free wait is bounded too. (a) SDA held low and a short timeout: the engine
    waits with BOTH lines undriven (it must not START into a busy bus), then times out. (b) SDA
    released well inside a long timeout: the START proceeds only after the release and the
    transfer completes without a timeout."""
    apb, slave = await _setup(dut, timeout=10)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x3E)
    slave.hold_sda_low(True)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    for _ in range(25):
        await _settled_edge(dut)
        assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0, (
            "engine drove the bus while it was busy"
        )
    stat = await _wait_idle(dut, 2000)
    assert stat & IRQ_STICKY == IRQ_TOUT, f"IRQ_STAT=0x{stat:x}"
    assert slave.events == [], "a START reached a busy bus"

    # (b)
    slave.reset_log()
    slave.hold_sda_low(False)
    await ClockCycles(dut.clk, 6)
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_TIMEOUT, 200)
    slave.hold_sda_low(True)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    await ClockCycles(dut.clk, 120)
    assert slave.events == []
    release_cycle = slave.cycle
    slave.hold_sda_low(False)
    stat = await _wait_idle(dut)
    assert stat & IRQ_STICKY == IRQ_DONE, f"IRQ_STAT=0x{stat:x}"
    assert slave.events[0] == ("START",) and slave.event_cycles[0] > release_cycle
    assert slave.received == [0x3E]


@cocotb.test()
async def test_i2c_timeout_fifo_starvation(dut):
    """A WRITE command with an EMPTY TX FIFO makes the master hold SCL low and wait (a legal
    pause); the wait is bounded by I2C_TIMEOUT. (a) short timeout: sticky timeout, lines released.
    (b) a byte pushed inside a long timeout: SCL was held low throughout the wait, the transfer
    then completes."""
    apb, slave = await _setup(dut, timeout=10)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=3000)
    assert stat & IRQ_STICKY == IRQ_TOUT, f"IRQ_STAT=0x{stat:x}"
    assert slave.events == [("START",), ("ADDR", SLAVE_ADDR, 0, True)], slave.events
    assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0
    assert not await _rd(apb, I2C_STATUS) & (ST_NACK | ST_TXN)

    # (b)
    slave.reset_state()
    slave.reset_log()
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_TIMEOUT, 400)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    for _ in range(3000):
        await _settled_edge(dut)
        if len(slave.events) >= 2:
            break
    await ClockCycles(dut.clk, 120)
    assert int(dut.i2c_scl_oe_o.value) == 1, "SCL must be held low while waiting for TX data"
    assert await _rd(apb, I2C_STATUS) & ST_BUSY
    await apb.write(I2C_TX_DATA, 0x2B)
    stat = await _wait_idle(dut)
    assert stat & IRQ_STICKY == IRQ_DONE, f"IRQ_STAT=0x{stat:x}"
    assert slave.received == [0x2B]
    slave.assert_clean()


@cocotb.test()
async def test_i2c_timeout_zero_disables(dut):
    """I2C_TIMEOUT = 0 DISABLES the watchdog (it must not mean 'expire immediately'): a slave
    stretching SCL for 2000 clk is waited out and the transfer completes with no timeout bit."""
    apb, slave = await _setup(dut, timeout=0)
    assert await _rd(apb, I2C_TIMEOUT) == 0
    slave.stretch_at_fall(3, 2000)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x4C)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=6000)
    assert stat & IRQ_STICKY == IRQ_DONE, f"IRQ_STAT=0x{stat:x}"
    assert slave.received == [0x4C]
    slave.assert_clean()


# ---------------------------------------------------------------------------
# Arbitration loss
# ---------------------------------------------------------------------------


async def _assert_arb_lost(dut, apb, label: str) -> None:
    """Common arbitration-loss postconditions: ONLY `arb_lost` is flagged (never `done`), both lines
    released, engine idle, txn_active cleared, and the master goes silent on SCL."""
    stat = await _peek(dut, I2C_IRQ_STAT)
    assert stat & IRQ_STICKY == IRQ_ARB, f"[{label}] IRQ_STAT=0x{stat:x}, expected only arb_lost"
    st = await _rd(apb, I2C_STATUS)
    assert st & ST_ARB and not st & (ST_BUSY | ST_TXN | ST_NACK | ST_TOUT), (
        f"[{label}] STATUS=0x{st:x}"
    )
    assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0, (
        f"[{label}] master must release both lines on arbitration loss"
    )


@cocotb.test()
async def test_i2c_arbitration_loss_address_bit(dut):
    """Another master drives SDA low during an address bit this master sends as a 1 (bit 2 of
    0xA0). The master must detect it: sticky `arb_lost` INSTEAD of `done`, lines released at once,
    no further SCL clocks, no address completed. Afterwards (W1C, contention over) a fresh transfer
    succeeds and the slave logs the half-seen byte as abandoned.
    MUTATION TARGET: arbitration compare disabled."""
    apb, slave = await _setup(dut)
    slave.contend_at_fall(2, 400)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x11)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=3000)
    await _assert_arb_lost(dut, apb, "address bit")
    assert slave.events == [("START",)], slave.events
    assert (await _rd(apb, I2C_FIFO_STAT)) & 0xF == 1, "address phase must not consume TX data"
    falls = len(slave.scl_fall_cycles)
    await ClockCycles(dut.clk, 200)
    assert len(slave.scl_fall_cycles) == falls and len(slave.scl_rise_cycles) <= falls + 1, (
        "master kept clocking after losing arbitration"
    )

    await ClockCycles(dut.clk, 300)  # contention over, bus idle high
    await apb.write(I2C_IRQ_CLR, IRQ_ARB)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == 0
    slave.reset_log()
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    assert stat & IRQ_STICKY == IRQ_DONE
    # The abandoned transfer never produced a STOP, so to the slave the new START is a repeated
    # START -- exactly what a real slave would conclude -- and it arrives mid-byte (2 bits seen).
    assert slave.events == [
        ("RSTART",),
        ("ADDR", SLAVE_ADDR, 0, True),
        ("WR", 0x11, True),
        ("STOP",),
    ], slave.events
    assert slave.abandoned == [("START", 2)], (
        f"the lost byte must show as abandoned: {slave.abandoned}"
    )


@cocotb.test()
async def test_i2c_arbitration_loss_data_bit(dut):
    """Same, in a DATA byte: bit 2 of 0xA0 is sent as a 1 while another master holds SDA low."""
    apb, slave = await _setup(dut)
    slave.contend_at_fall(_bit_idx(1, 2), 400)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0xA0)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=3000)
    await _assert_arb_lost(dut, apb, "data bit")
    assert slave.events == [("START",), ("ADDR", SLAVE_ADDR, 0, True)], slave.events
    assert ("STOP",) not in slave.events


@cocotb.test()
async def test_i2c_arbitration_loss_read_nack_slot(dut):
    """The ACK slot of a READ is where THIS master drives SDA: sending a NACK (releasing SDA) while
    another master holds it low is an arbitration loss too (the second half of the compare). The
    received byte is discarded (not pushed to the RX FIFO)."""
    apb, slave = await _setup(dut)
    slave.read_queue = [0x8B]
    slave.contend_at_fall(_bit_idx(1, 8), 400)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1), limit=3000)
    await _assert_arb_lost(dut, apb, "read NACK slot")
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x800, f"FIFO_STAT=0x{fs:x}: a byte whose ACK slot lost arbitration must be dropped"
    assert ("STOP",) not in slave.events


@cocotb.test()
async def test_i2c_arbitration_no_false_loss_when_sending_zero(dut):
    """NEGATIVE CONTROL for arbitration: another device driving SDA low must NOT be flagged when
    this
    master is itself sending a 0, nor in a write's ACK slot (the slave pulls it low by design), nor
    in
    a read's ACK slot when this master ACKs (drives 0). A compare that fired unconditionally would
    fail here. Contention lasts exactly one bit (until the next SCL fall)."""
    apb, slave = await _setup(dut)
    slave.contend_at_fall(1, -1)  # address bit 1 is 0
    slave.contend_at_fall(8, -1)  # address ACK slot
    slave.contend_at_fall(_bit_idx(1, 0), -1)  # data 0x5A bit 0 is 0
    slave.contend_at_fall(_bit_idx(1, 8), -1)  # data ACK slot
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x5A)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    assert stat & IRQ_STICKY == IRQ_DONE, f"false arbitration loss: IRQ_STAT=0x{stat:x}"
    assert slave.received == [0x5A]

    slave.reset_log()
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    slave.read_queue = [0x12, 0x34]
    slave.contend_at_fall(_bit_idx(1, 8), -1)  # master ACKs byte 1 (drives 0)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    stat = await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=2))
    assert stat & IRQ_STICKY == IRQ_DONE, f"false arbitration loss on a read ACK: 0x{stat:x}"
    assert await _drain_rx(apb) == [0x12, 0x34]
    slave.assert_clean()


@cocotb.test()
async def test_i2c_arbitration_loss_repeated_start_setup(dut):
    """During the repeated-START setup the master releases SDA and expects it high before pulling it
    low for the START. Another device holding SDA low there is an arbitration loss: no RSTART
    appears, lines are released, `arb_lost` (not `done`) is flagged, and the master goes SILENT: it
    must abort at the setup check, before it pulls SCL low again for the START.
    MUTATION TARGET (found by the campaign, not by inspection): removing the S_RS_HI check. The
    master then falls through to the data-bit compare and still raises arb_lost on the first 1 bit,
    so the flag alone cannot tell the two apart; and with SDA already held low the BFM cannot see a
    START either. The observable difference is the extra SCL fall, so the test asserts there is
    none."""
    apb, slave = await _setup(dut)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x44)
    await _run(dut, apb, cmd(start=1, write=1, count=1))  # bus held
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)  # drop that command's done
    slave.hold_sda_low(True)
    falls_before = len(slave.scl_fall_cycles)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1), limit=3000)
    await _assert_arb_lost(dut, apb, "repeated START setup")
    assert ("RSTART",) not in slave.events, slave.events
    assert len(slave.scl_fall_cycles) == falls_before, (
        "the master pulled SCL low again after losing arbitration at the repeated-START setup: "
        "it must abort before the START, not carry on and fail later"
    )
    slave.hold_sda_low(False)


# ---------------------------------------------------------------------------
# FIFOs
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_tx_fifo_fill_drain_and_stat(dut):
    """TX FIFO: level and full/empty track every push 0..8, pushes into a FULL FIFO are DROPPED (the
    dropped values never reach the bus), TX_DATA reads 0, and the FIFO order is the bus order."""
    apb, slave = await _setup(dut)
    assert await _rd(apb, I2C_TX_DATA) == 0
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x200 and not fs & 0x100 and fs & 0xF == 0
    vals = [0x60 + i for i in range(FIFO_DEPTH)]
    for n, v in enumerate(vals, start=1):
        await apb.write(I2C_TX_DATA, v)
        fs = await _rd(apb, I2C_FIFO_STAT)
        assert fs & 0xF == n, f"tx_level after {n} pushes = {fs & 0xF}"
        assert bool(fs & 0x100) == (n == FIFO_DEPTH), f"tx_full wrong at level {n} (0x{fs:x})"
        assert not fs & 0x200, f"tx_empty set at level {n}"
    await apb.write(I2C_TX_DATA, 0xEE)  # dropped
    await apb.write(I2C_TX_DATA, 0xEF)  # dropped
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0xF == FIFO_DEPTH and fs & 0x100, f"push into a full FIFO changed it: 0x{fs:x}"

    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=FIFO_DEPTH))
    assert slave.received == vals, (
        f"bus order/value mismatch (or dropped push leaked): {slave.received}"
    )
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x200 and fs & 0xF == 0 and not fs & 0x100, f"FIFO_STAT=0x{fs:x}"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_tx_fifo_refill_during_transfer(dut):
    """COUNT may exceed the 8-byte FIFO: the engine holds SCL low when the FIFO runs dry, and
    software
    refills it while the transfer is running. 12 bytes arrive in order with nothing lost or
    duplicated at the refill boundary."""
    apb, slave = await _setup(dut)
    vals = [0x80 + i for i in range(12)]
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _push(apb, vals[:FIFO_DEPTH])
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=12))
    nxt = FIFO_DEPTH
    for _ in range(20000):
        await _settled_edge(dut)
        if nxt < len(vals) and (await _peek(dut, I2C_FIFO_STAT)) & 0xF <= 5:
            await apb.write(I2C_TX_DATA, vals[nxt])
            nxt += 1
        if nxt == len(vals) and not (await _peek(dut, I2C_STATUS)) & ST_BUSY:
            break
    assert nxt == len(vals), "refill never found space"
    await _wait_idle(dut)
    assert slave.received == vals, f"refill boundary corrupted the stream: {slave.received}"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_rx_fifo_fill_drain_and_stat(dut):
    """RX FIFO: eight received bytes fill it exactly (level 8, rx_full), APB reads pop in order and
    the level/flags track every pop down to empty."""
    apb, slave = await _setup(dut)
    vals = [0x30 + i for i in range(FIFO_DEPTH)]
    slave.read_queue = list(vals)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=FIFO_DEPTH))
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert (fs >> 4) & 0xF == FIFO_DEPTH and fs & 0x400 and not fs & 0x800, f"0x{fs:x}"
    for n, v in enumerate(vals):
        assert await _rd(apb, I2C_RX_DATA) == v, f"pop {n} out of order / wrong value"
        fs = await _rd(apb, I2C_FIFO_STAT)
        left = FIFO_DEPTH - 1 - n
        assert (fs >> 4) & 0xF == left, f"rx_level after pop {n}: {(fs >> 4) & 0xF}, want {left}"
        assert not fs & 0x400, "rx_full must clear after the first pop"
        assert bool(fs & 0x800) == (left == 0), f"rx_empty wrong at level {left}"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_rx_empty_read_is_zero(dut):
    """Reading RX_DATA on an EMPTY FIFO returns 0, sets no status, raises no error and does not
    underflow: the next real receive still delivers exactly its bytes (a phantom pop would corrupt
    the level)."""
    apb, slave = await _setup(dut)
    for _ in range(3):
        v, ok = await apb.read(I2C_RX_DATA)
        assert ok and v == 0, f"empty RX read returned 0x{v:x} ok={ok}"
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0x800 and (fs >> 4) & 0xF == 0 and not fs & 0x400, f"FIFO_STAT=0x{fs:x}"
    assert await _rd(apb, I2C_IRQ_STAT) == 0 and await _rd(apb, I2C_STATUS) & 0x1F == 0

    slave.read_queue = [0xC1, 0xC2]
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=2))
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert (fs >> 4) & 0xF == 2, f"rx_level=0x{fs:x}: an earlier empty pop corrupted the FIFO"
    assert await _drain_rx(apb) == [0xC1, 0xC2]


@cocotb.test()
async def test_i2c_rx_full_holds_scl_low(dut):
    """A READ of 10 bytes into the 8-byte RX FIFO: when the FIFO is full the engine holds SCL LOW
    and waits (no clocks, no timeout at the default limit) until software pops; the transfer then
    continues and all 10 bytes come out in order."""
    apb, slave = await _setup(dut)
    pattern = [0x10 + i for i in range(10)]
    slave.read_queue = list(pattern)
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await apb.write(I2C_CMD, cmd(start=1, read=1, stop=1, nack_last=1, count=10))
    for _ in range(6000):
        await _settled_edge(dut)
        if (await _peek(dut, I2C_FIFO_STAT) >> 4) & 0xF == FIFO_DEPTH:
            break
    else:
        raise AssertionError("RX FIFO never filled")
    await ClockCycles(dut.clk, 60)
    rises = len(slave.scl_rise_cycles)
    await ClockCycles(dut.clk, 300)
    assert len(slave.scl_rise_cycles) == rises, "master kept clocking into a full RX FIFO"
    assert int(dut.i2c_scl_oe_o.value) == 1, "SCL must be held low while the RX FIFO is full"
    st = await _rd(apb, I2C_STATUS)
    assert st & ST_BUSY and not st & ST_TOUT, f"STATUS=0x{st:x}"

    got: list = []
    for _ in range(40000):
        fs = await _rd(apb, I2C_FIFO_STAT)
        if (fs >> 4) & 0xF:
            got.append(await _rd(apb, I2C_RX_DATA))
        elif not await _rd(apb, I2C_STATUS) & ST_BUSY:
            break
        await ClockCycles(dut.clk, 3)
    await _wait_idle(dut)
    got += await _drain_rx(apb)
    assert got == pattern, f"RX stream corrupted across the full/resume boundary: {got}"
    rds = [e for e in slave.events if e[0] == "RD"]
    assert len(rds) == 10 and rds[-1][2] is False
    slave.assert_clean()


# ---------------------------------------------------------------------------
# Register file
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_reset_defaults(dut):
    """After reset (controller still disabled, bus released): CTRL 0, STATUS == 0x60 exactly (only
    the
    two sensed bus levels), CLKDIV 0xFF, ADDR 0, TIMEOUT 0xFFFF, IRQ_EN 0, IRQ_STAT 0, FIFO_STAT ==
    0xA00 (tx_empty | rx_empty), the write-only registers and the unused words read 0, both oe pins
    and both dead `*_o` pins 0, irq_o 0, and the bus stays silent."""
    apb, slave = await _setup(dut, enable=False)
    await apb.write(I2C_CLKDIV, 0xFF)  # _setup wrote FAST_DIV; restore for the check
    # re-reset to see the true defaults
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 6)
    want = {
        I2C_CTRL: 0,
        I2C_STATUS: ST_SCL | ST_SDA,
        I2C_CLKDIV: 0xFF,
        I2C_ADDR: 0,
        I2C_TX_DATA: 0,
        I2C_RX_DATA: 0,
        I2C_CMD: 0,
        I2C_FIFO_STAT: 0xA00,
        I2C_TIMEOUT: 0xFFFF,
        I2C_IRQ_EN: 0,
        I2C_IRQ_STAT: 0,
        I2C_IRQ_CLR: 0,
    }
    for addr, exp in want.items():
        v, ok = await apb.read(addr)
        assert ok and v == exp, f"reg 0x{addr:03x} reset value 0x{v:x}, expected 0x{exp:x}"
    for _ in range(200):
        await RisingEdge(dut.clk)
        assert int(dut.i2c_scl_oe_o.value) == 0 and int(dut.i2c_sda_oe_o.value) == 0
        assert int(dut.i2c_scl_o.value) == 0 and int(dut.i2c_sda_o.value) == 0
        assert int(dut.irq_o.value) == 0
    assert slave.events == []
    slave.assert_clean()


@cocotb.test()
async def test_i2c_rw_roundtrip_and_masks(dut):
    """RW registers keep exactly their documented bits (CTRL 0xF03, CLKDIV 16, ADDR 8, TIMEOUT 16,
    IRQ_EN 5 bits) and drop the rest; read-only registers ignore writes; write-only registers read
    0; pslverr is never raised."""
    apb, _slave = await _setup(dut, enable=False)
    for addr, full in (
        (I2C_CTRL, 0x0F03),
        (I2C_CLKDIV, 0xFFFF),
        (I2C_ADDR, 0xFF),
        (I2C_TIMEOUT, 0xFFFF),
        (I2C_IRQ_EN, 0x1F),
    ):
        for pat in (0xFFFF_FFFF, 0x0000_0000, 0xAAAA_AAAA, 0x5555_5555, 0xFFFF_FFFF):
            ok = await apb.write(addr, pat)
            assert ok, f"pslverr on write 0x{addr:03x}"
            v = await _rd(apb, addr)
            assert v == pat & full, (
                f"reg 0x{addr:03x}: wrote 0x{pat:08x}, read 0x{v:08x}, expected 0x{pat & full:08x}"
            )
    await apb.write(I2C_CTRL, 0)
    await apb.write(I2C_CLKDIV, FAST_DIV)

    # read-only registers ignore writes
    before = {a: await _rd(apb, a) for a in (I2C_STATUS, I2C_RX_DATA, I2C_FIFO_STAT, I2C_IRQ_STAT)}
    for a in before:
        assert await apb.write(a, 0xFFFF_FFFF)
    after = {a: await _rd(apb, a) for a in before}
    assert before == after, f"a read-only register changed on write: {before} -> {after}"
    # write-only registers read 0
    for a in (I2C_TX_DATA, I2C_CMD, I2C_IRQ_CLR):
        await apb.write(a, 0)
        assert await _rd(apb, a) == 0, f"WO register 0x{a:03x} must read 0"


@cocotb.test()
async def test_i2c_pstrb_partial_word(dut):
    """Byte strobes: only strobed lanes of an RW register change; lanes above a register's mask are
    dropped; strb = 0 is a no-op; TX_DATA pushes only on lane 0 and only pwdata[7:0]."""
    apb, _slave = await _setup(dut, enable=False)
    await apb.write(I2C_CLKDIV, 0x1234)
    await apb.write(I2C_CLKDIV, 0xAABBCCDD, strb=0b0010)
    assert await _rd(apb, I2C_CLKDIV) == 0xCC34
    await apb.write(I2C_CLKDIV, 0xAABBCCDD, strb=0b0001)
    assert await _rd(apb, I2C_CLKDIV) == 0xCCDD
    await apb.write(I2C_CLKDIV, 0xFFFFFFFF, strb=0b1100)  # lanes above the mask
    assert await _rd(apb, I2C_CLKDIV) == 0xCCDD
    await apb.write(I2C_CLKDIV, 0xFFFFFFFF, strb=0b0000)
    assert await _rd(apb, I2C_CLKDIV) == 0xCCDD

    await apb.write(I2C_CTRL, 0x0F00, strb=0b0010)  # RX_THR lane only
    assert await _rd(apb, I2C_CTRL) == 0x0F00
    await apb.write(I2C_CTRL, 0x0001, strb=0b0001)  # EN lane only
    assert await _rd(apb, I2C_CTRL) == 0x0F01
    await apb.write(I2C_CTRL, 0x0000, strb=0b0001)
    assert await _rd(apb, I2C_CTRL) == 0x0F00
    await apb.write(I2C_CTRL, 0)

    await apb.write(I2C_TX_DATA, 0x0000AB00, strb=0b0010)  # lane 1 only: no push
    assert (await _rd(apb, I2C_FIFO_STAT)) & 0xF == 0
    await apb.write(I2C_TX_DATA, 0x123456CD, strb=0b0001)  # lane 0: pushes 0xCD only
    fs = await _rd(apb, I2C_FIFO_STAT)
    assert fs & 0xF == 1


@cocotb.test()
async def test_i2c_out_of_range_access(dut):
    """Word index >= 12 (0x030..0xFFC): writes are dropped (no aliasing back onto the 12 real
    registers, including the power-of-two wrap at 0x040), reads return 0, pslverr stays 0."""
    apb, _slave = await _setup(dut, enable=False)
    marks = {
        I2C_CTRL: 0x0301,
        I2C_CLKDIV: 0x1357,
        I2C_ADDR: 0x6A,
        I2C_TIMEOUT: 0x2468,
        I2C_IRQ_EN: 0x15,
    }
    await apb.write(I2C_CTRL, 0x0300)  # EN stays 0
    marks[I2C_CTRL] = 0x0300
    for a, v in marks.items():
        if a != I2C_CTRL:
            await apb.write(a, v)
    for oor in (I2C_OUT_OF_RANGE, 0x034, 0x03C, 0x040, 0x080, 0x800, 0xFFC):
        assert await apb.write(oor, 0xFFFF_FFFF), f"pslverr on write 0x{oor:03x}"
        v, ok = await apb.read(oor)
        assert ok and v == 0, f"out-of-range read 0x{oor:03x} returned 0x{v:x} ok={ok}"
    for a, v in marks.items():
        assert await _rd(apb, a) == v, f"write to an out-of-range address aliased onto 0x{a:03x}"
    assert (await _rd(apb, I2C_FIFO_STAT)) == 0xA00, "an out-of-range write must not push/pop"


@cocotb.test()
async def test_i2c_clkdiv_clamp_to_min(dut):
    """CLKDIV values below CLKDIV_MIN (3) read back AS WRITTEN but run at the minimum: the SCL-low
    interval for CLKDIV 0, 1 and 2 equals the one for 3, and CLKDIV 4 is strictly (exactly one tick
    per low-half) slower, so the measurement is sensitive."""
    low = {}
    for div in (0, 1, 2, 3, 4):
        apb, slave = await _setup(dut, clkdiv=div)
        assert await _rd(apb, I2C_CLKDIV) == div, "CLKDIV must read back as written"
        await apb.write(I2C_ADDR, SLAVE_ADDR)
        await apb.write(I2C_TX_DATA, 0x42)
        stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
        assert stat & IRQ_STICKY == IRQ_DONE and slave.received == [0x42], (
            f"CLKDIV={div}: transfer failed (events {slave.events})"
        )
        lows = sorted(slave.scl_low_cycles)
        low[div] = lows[len(lows) // 2]
    assert low[0] == low[1] == low[2] == low[3], f"clamp not applied: {low}"
    assert low[4] == low[3] + 2, f"CLKDIV=4 must add exactly one tick per SCL-low half: {low}"


@cocotb.test()
async def test_i2c_clkdiv_min_guard_rejects_elaboration(dut):
    """The DUT's g_clkdiv_min_check $fatal must REFUSE to elaborate an unsafe prescaler minimum
    (CLKDIV_MIN < SYNC_STAGES+1 = 3), and the same lint command must pass at the default -- the
    negative control that proves the command line itself is sound."""
    srcs = [
        str(_PROJ_ROOT / "rtl/soc/apb4_register_bank.sv"),
        str(_PROJ_ROOT / "rtl/soc/cdc/cdc_2ff_sync.sv"),
        str(_PROJ_ROOT / "rtl/periph/i2c_bit_engine.sv"),
        str(_PROJ_ROOT / "rtl/periph/i2c_controller.sv"),
        str(Path(__file__).resolve().parent / "tb_i2c.sv"),
    ]
    base = [
        "verilator",
        "--lint-only",
        "-Wall",
        "-Wno-IMPORTSTAR",
        "-Wno-SYNCASYNCNET",
        "--top-module",
        "tb_i2c",
    ]
    ok = subprocess.run(base + srcs, capture_output=True, text=True, check=False)
    assert ok.returncode == 0, f"default elaboration must pass:\n{ok.stdout}{ok.stderr}"
    for bad in (2, 0):
        r = subprocess.run(
            base + [f"-GCLKDIV_MIN={bad}"] + srcs, capture_output=True, text=True, check=False
        )
        assert r.returncode != 0, f"CLKDIV_MIN={bad} elaborated; the guard is not firing"
        assert "CLKDIV_MIN" in r.stdout + r.stderr, (
            f"CLKDIV_MIN={bad} failed, but not via the guard:\n{r.stdout}{r.stderr}"
        )
    good = subprocess.run(
        base + ["-GCLKDIV_MIN=5"] + srcs, capture_output=True, text=True, check=False
    )
    assert good.returncode == 0, "a larger legal CLKDIV_MIN must still elaborate"


# ---------------------------------------------------------------------------
# Interrupts
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_i2c_rx_threshold_irq(dut):
    """IRQ_STAT[4] is a LIVE level: set iff rx_level >= RX_THR (0 behaves as 1; 9..15 can never fire
    for an 8-deep FIFO), not sticky, no W1C. Swept over every threshold at level 8 and level 7;
    irq_o follows IRQ_STAT[4] & IRQ_EN[4]; draining the FIFO drops it with no clear."""
    apb, slave = await _setup(dut)
    slave.read_queue = [0x20 + i for i in range(FIFO_DEPTH)]
    await apb.write(I2C_ADDR, SLAVE_ADDR | 0x80)
    await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=FIFO_DEPTH))
    await apb.write(I2C_IRQ_EN, IRQ_RXTHR)

    async def check(level: int) -> None:
        for thr in range(16):
            await apb.write(I2C_CTRL, CTRL_EN | (thr << 8))
            await ClockCycles(dut.clk, 2)
            want = level >= max(thr, 1)
            stat = await _rd(apb, I2C_IRQ_STAT)
            assert bool(stat & IRQ_RXTHR) == want, (
                f"level {level} thr {thr}: IRQ_STAT[4]={bool(stat & IRQ_RXTHR)} want {want}"
            )
            assert int(dut.irq_o.value) == int(want), f"level {level} thr {thr}: irq_o wrong"

    await check(FIFO_DEPTH)
    assert await _rd(apb, I2C_RX_DATA) == 0x20
    await check(FIFO_DEPTH - 1)

    # W1C of bit 4 does nothing to a live level.
    await apb.write(I2C_CTRL, CTRL_EN | (3 << 8))
    await apb.write(I2C_IRQ_CLR, IRQ_RXTHR)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_RXTHR, (
        "rx_threshold has no clear; W1C must not drop it"
    )
    # Drain exactly down to the threshold boundary: still set at 3, clear at 2.
    for expect_after in (6, 5, 4, 3):
        await apb.read(I2C_RX_DATA)
        fs = await _rd(apb, I2C_FIFO_STAT)
        assert (fs >> 4) & 0xF == expect_after
        assert await _rd(apb, I2C_IRQ_STAT) & IRQ_RXTHR, f"must stay set at level {expect_after}"
    assert int(dut.irq_o.value) == 1
    await apb.read(I2C_RX_DATA)  # level 2 < 3
    assert not await _rd(apb, I2C_IRQ_STAT) & IRQ_RXTHR, "must drop below the threshold"
    assert int(dut.irq_o.value) == 0
    await _drain_rx(apb)
    assert not await _rd(apb, I2C_IRQ_STAT) & IRQ_RXTHR


async def _ev_done(dut, apb, slave) -> int:
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x01)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    return IRQ_DONE


async def _ev_nack(dut, apb, slave) -> int:
    slave.ack_address = False
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    slave.ack_address = True
    return IRQ_DONE | IRQ_NACK  # a NACK is a normal completion: done sets with it


async def _ev_arb(dut, apb, slave) -> int:
    slave.contend_at_fall(2, 300)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x01)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=3000)
    return IRQ_ARB


async def _ev_tout(dut, apb, slave) -> int:
    await apb.write(I2C_TIMEOUT, 10)
    slave.stretch_at_fall(3, 5000)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x01)
    await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=3000)
    return IRQ_TOUT


@cocotb.test()
async def test_i2c_irq_sources_and_w1c(dut):
    """Every sticky IRQ source (done, nack, arb_lost, timeout): it sets IRQ_STAT and its STATUS
    mirror
    (STATUS[4:2] are the SAME flops as IRQ_STAT[3:1]); IRQ_EN masks irq_o ONLY (IRQ_STAT stays set);
    an enable for a DIFFERENT bit does not raise irq_o; irq_o is LEVEL-held; a W1C of other bits or
    with the byte lane strobed away does not clear it; IRQ_STAT ignores writes; the right W1C clears
    exactly that bit and drops irq_o; IRQ_CLR reads 0."""
    apb, slave = await _setup(dut)
    for name, maker, bit, mirror in (
        ("done", _ev_done, IRQ_DONE, None),
        ("nack", _ev_nack, IRQ_NACK, ST_NACK),
        ("arb_lost", _ev_arb, IRQ_ARB, ST_ARB),
        ("timeout", _ev_tout, IRQ_TOUT, ST_TOUT),
    ):
        await apb.write(I2C_IRQ_EN, 0)
        await apb.write(I2C_TIMEOUT, 0xFFFF)
        slave.reset_state()
        await ClockCycles(dut.clk, 4)
        await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
        await apb.write(I2C_CTRL, 0)  # clean engine + FIFOs between sources
        await apb.write(I2C_CTRL, CTRL_EN)
        pending = await maker(dut, apb, slave)
        await ClockCycles(dut.clk, 2)

        stat = await _rd(apb, I2C_IRQ_STAT)
        assert stat & IRQ_STICKY == pending, f"[{name}] IRQ_STAT=0x{stat:x}, expected 0x{pending:x}"
        if mirror:
            assert await _rd(apb, I2C_STATUS) & mirror, f"[{name}] STATUS mirror bit not set"
        assert int(dut.irq_o.value) == 0, (
            f"[{name}] irq_o high with IRQ_EN == 0 (mask is output-only)"
        )

        other = IRQ_STICKY & ~pending
        await apb.write(I2C_IRQ_EN, other)
        await ClockCycles(dut.clk, 3)
        assert int(dut.irq_o.value) == 0, (
            f"[{name}] irq_o raised by an enable for a non-pending bit"
        )
        assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == pending, (
            "IRQ_EN must not touch IRQ_STAT"
        )

        await apb.write(I2C_IRQ_EN, bit)
        for _ in range(100):  # level-held, never a pulse
            await RisingEdge(dut.clk)
            assert int(dut.irq_o.value) == 1, f"[{name}] irq_o dropped while pending"

        await apb.write(I2C_IRQ_STAT, 0)  # RO
        assert await _rd(apb, I2C_IRQ_STAT) & bit, f"[{name}] IRQ_STAT must ignore writes"
        await apb.write(I2C_IRQ_CLR, IRQ_STICKY & ~bit)  # W1C of other bits only
        assert await _rd(apb, I2C_IRQ_STAT) & bit, f"[{name}] cleared by a W1C of OTHER bits"
        assert int(dut.irq_o.value) == 1
        await apb.write(I2C_IRQ_CLR, bit, strb=0b1110)  # right bit, lane 0 not strobed
        assert await _rd(apb, I2C_IRQ_STAT) & bit, f"[{name}] cleared with pstrb[0] = 0"
        await apb.write(I2C_IRQ_CLR, bit)
        stat = await _rd(apb, I2C_IRQ_STAT)
        assert not stat & bit, f"[{name}] W1C did not clear the bit"
        assert int(dut.irq_o.value) == 0, f"[{name}] irq_o still high after the clear"
        if mirror:
            assert not await _rd(apb, I2C_STATUS) & mirror, f"[{name}] STATUS mirror not cleared"
        assert await _rd(apb, I2C_IRQ_CLR) == 0


async def _clear_coincident(dut, pred, clr_value: int, set_sig, label: str) -> None:
    """Land an IRQ_CLR write whose ACCESS-phase commit edge is EXACTLY the edge that sets an event
    bit.
    `pred(dut)` is evaluated on the settled state of cycle k and must be true iff cycle k+1 is the
    cycle in which `set_sig` is high (derived from the FSM's tick arithmetic); the write's SETUP is
    driven in cycle k, its ACCESS in cycle k+1, so the commit edge is the one that ends cycle k+1.
    The coincidence itself is then VERIFIED from the DUT's own combinational set/clear nets, so a
    mis-timed prediction fails loudly instead of silently testing nothing."""
    for _ in range(20000):
        await _settled_edge(dut)
        if pred(dut):
            break
    else:
        raise AssertionError(f"[{label}] the predicted event cycle never arrived")
    _raw_write_setup(dut, I2C_IRQ_CLR, clr_value)
    await RisingEdge(dut.clk)  # SETUP edge
    _raw_write_access(dut)
    await Timer(1, units="step")
    sets, clrs = int(set_sig.value), int(dut.u_dut.clr_w.value)
    assert sets == 1 and clrs & clr_value == clr_value, (
        f"[{label}] clear did not coincide with the set (set_w={sets}, clr_w=0x{clrs:x}) -- "
        f"the alignment prediction is wrong, the test would be vacuous"
    )
    await RisingEdge(dut.clk)  # commit edge
    _raw_write_idle(dut)
    await _settled_edge(dut)


S_BUSWAIT, S_BIT_HI, S_STP_FREE = 1, 9, 15
S_WAITS = (1, 3, 8, 10, 13)


@cocotb.test()
async def test_i2c_sticky_set_wins_over_clear(dut):
    """The sticky event bits are `(q & ~clear) | set`: a SET WINS over a same-cycle W1C, so an
    event is
    never lost to a racing clear (GPIO_IRQ_STAT / trng health_fail precedent). Each of done, nack,
    arb_lost and timeout is hit by an IRQ_CLR write that commits on EXACTLY the edge that sets it
    (coincidence verified from the DUT's own set/clear nets) and must stay set.
    MUTATION TARGET: a same-cycle W1C beating the set."""
    u = dut.u_dut
    e = u.u_bit_engine  # protocol core (i2c_bit_engine.sv): state_q/tick_q/bitcnt_q/to_q
    apb, slave = await _setup(dut, timeout=0xFFFF)
    await apb.write(I2C_ADDR, SLAVE_ADDR)

    # done: the STOP path sets it in the S_STP_FREE tick (tick_q == 1 one cycle earlier).
    await apb.write(I2C_TX_DATA, 0x99)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    await _clear_coincident(
        dut,
        lambda d: int(e.state_q.value) == S_STP_FREE and int(e.tick_q.value) == 1,
        IRQ_DONE,
        u.done_set_w,
        "done",
    )
    await _wait_idle(dut)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == IRQ_DONE, (
        "a W1C on the very edge of the done event must not swallow it"
    )
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)

    # nack (+done): address NACK without STOP -> both set in the same S_BIT_HI tick; clear both.
    slave.ack_address = False
    await apb.write(I2C_CMD, cmd(start=1, write=1, count=1))
    await _clear_coincident(
        dut,
        lambda d: (
            int(e.state_q.value) == S_BIT_HI
            and int(e.bitcnt_q.value) == 8
            and int(e.tick_q.value) == 1
        ),
        IRQ_DONE | IRQ_NACK,
        u.nack_set_w,
        "nack",
    )
    await _wait_idle(dut)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == IRQ_DONE | IRQ_NACK, (
        "a W1C on the very edge of the nack event must not swallow it"
    )
    slave.ack_address = True
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_CTRL, 0)
    await apb.write(I2C_CTRL, CTRL_EN)

    # arb_lost: contention on address bit 2 -> set in the S_BIT_HI tick of bit 2.
    slave.contend_at_fall(2, 300)
    await apb.write(I2C_TX_DATA, 0x99)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    await _clear_coincident(
        dut,
        lambda d: (
            int(e.state_q.value) == S_BIT_HI
            and int(e.bitcnt_q.value) == 2
            and int(e.tick_q.value) == 1
        ),
        IRQ_ARB,
        u.arb_set_w,
        "arb_lost",
    )
    await _wait_idle(dut)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == IRQ_ARB, (
        "a W1C on the very edge of the arbitration loss must not swallow it"
    )
    slave.reset_state()
    await ClockCycles(dut.clk, 4)
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_CTRL, 0)
    await apb.write(I2C_CTRL, CTRL_EN)

    # timeout: stuck-low SDA before START; the counter reaches TIMEOUT on a tick, the set follows.
    tmo = 5
    await apb.write(I2C_TIMEOUT, tmo)
    slave.hold_sda_low(True)
    await apb.write(I2C_CMD, cmd(start=1, write=1, stop=1, count=1))
    await _clear_coincident(
        dut,
        lambda d: (
            int(e.state_q.value) in S_WAITS
            and int(e.to_q.value) == tmo - 1
            and int(e.tick_q.value) == 0
        ),
        IRQ_TOUT,
        u.tout_set_w,
        "timeout",
    )
    await _wait_idle(dut)
    assert await _rd(apb, I2C_IRQ_STAT) & IRQ_STICKY == IRQ_TOUT, (
        "a W1C on the very edge of the timeout must not swallow it"
    )
    slave.hold_sda_low(False)


# ---------------------------------------------------------------------------
# Bus rate, loopback, sensed levels
# ---------------------------------------------------------------------------


async def _measure_scl(dut, div: int) -> dict:
    """Run one 1-byte write at CLKDIV=`div` and return the median measured SCL timing (clk
    cycles)."""
    apb, slave = await _setup(dut, clkdiv=div)
    await apb.write(I2C_ADDR, SLAVE_ADDR)
    await apb.write(I2C_TX_DATA, 0x3C)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1), limit=40000)
    assert stat & IRQ_STICKY == IRQ_DONE and slave.received == [0x3C]
    slave.assert_clean()

    def med(xs: list) -> int:
        xs = sorted(xs)
        return xs[len(xs) // 2]

    return {
        "period": med(slave.scl_periods),
        "low": med(slave.scl_low_cycles),
        "high": med(slave.scl_high_cycles),
    }


@cocotb.test()
async def test_i2c_clkdiv_scl_period_linear(dut):
    """Contract-independent rate sanity: the SCL period is EXACTLY linear in (CLKDIV + 1) with a
    small
    constant offset (the synchroniser wait), at CLKDIV 3, 62 and 249. This pins the scaling of the
    prescaler without asserting the per-bit tick count -- that is test_i2c_clkdiv_100k_400k."""
    m = {d: await _measure_scl(dut, d) for d in (3, 62, 249)}
    dut._log.info("measured SCL timing (clk cycles @ 100 MHz): %s", m)
    slope_num = m[249]["period"] - m[62]["period"]
    assert slope_num % (249 - 62) == 0, f"period is not linear in CLKDIV+1: {m}"
    slope = slope_num // (249 - 62)
    assert m[62]["period"] - m[3]["period"] == slope * (62 - 3), f"period is not linear: {m}"
    offset = m[3]["period"] - slope * 4
    assert 0 <= offset <= 8, f"implausible constant offset {offset} (slope {slope} clk/tick): {m}"
    assert m[3]["low"] < m[62]["low"] < m[249]["low"]


@cocotb.test()
async def test_i2c_clkdiv_100k_400k(dut):
    """Standard-mode and Fast-mode rates from CLKDIV at the 100 MHz test clock, against the DUT
    header's contract: "One bit = 4 ticks ... f_scl = f_clk / (4*(CLKDIV+1))" and the bead's
    "Standard 100 kHz and Fast 400 kHz via a 16-bit I2C_CLKDIV". CLKDIV = 249 is the 100 kHz divisor
    (1000-clk period) and CLKDIV = 62 the largest-rate Fast-mode divisor not over 400 kHz (252 clk;
    61 would be 403 kHz). Checked against the I2C specification limits, not against the RTL:
      * f_scl never exceeds the mode's maximum and is within 2 % below it;
      * Standard mode: tLOW >= 4.7 us, tHIGH >= 4.0 us;  Fast mode: tLOW >= 1.3 us, tHIGH >= 0.6 us.

    Permanent regression gate for fix_request fr_609b42790e0f_20261003_015343_00: the bit engine
    used to spend three timed states per bit (132.8 kHz at CLKDIV=249, tHIGH 2.53 us; 520.8 kHz at
    CLKDIV=62, tLOW 1.26 us). It now has the fourth phase (S_BIT_HI1), with the synchroniser wait
    counted inside the high phase, so the period is exactly 4*(CLKDIV+1) clk."""
    # (CLKDIV, max kHz, tLOW_min us, tHIGH_min us)
    for div, max_khz, t_low_us, t_high_us in ((249, 100.0, 4.7, 4.0), (62, 400.0, 1.3, 0.6)):
        t = await _measure_scl(dut, div)
        f_khz = 1e5 / t["period"]
        low_us, high_us = t["low"] / 100.0, t["high"] / 100.0
        dut._log.info(
            "CLKDIV=%d: %.1f kHz, tLOW %.2f us, tHIGH %.2f us (period %d clk)",
            div,
            f_khz,
            low_us,
            high_us,
            t["period"],
        )
        assert 0.98 * max_khz <= f_khz <= max_khz, (
            f"CLKDIV={div}: SCL = {f_khz:.1f} kHz, must be within 2 % below {max_khz} kHz"
        )
        assert low_us >= t_low_us, f"CLKDIV={div}: tLOW {low_us:.2f} us < {t_low_us} us"
        assert high_us >= t_high_us, f"CLKDIV={div}: tHIGH {high_us:.2f} us < {t_high_us} us"


@cocotb.test()
async def test_i2c_loopback_write_then_read(dut):
    """Internal loopback (CTRL[1], the SPI_CTRL[4] precedent, used by the SoC fabric test): the
    master
    talks to a tiny internal slave that ACKs ANY address and every write byte, a read returns the
    LAST
    BYTE WRITTEN (reset value 0xA5), and the real pads are NOT disturbed (oe_o forced 0, no bus
    events) at any point."""
    apb, slave = await _setup(dut, enable=False)
    await apb.write(I2C_CTRL, CTRL_EN | CTRL_LOOP)
    bad: list = []

    async def pad_monitor() -> None:
        while True:
            await RisingEdge(dut.clk)
            if int(dut.i2c_scl_oe_o.value) or int(dut.i2c_sda_oe_o.value):
                bad.append(slave.cycle)

    _active_tasks.append(cocotb.start_soon(pad_monitor()))

    await apb.write(I2C_ADDR, 0x7F | 0x80)  # any address, read
    stat = await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1))
    assert stat & IRQ_STICKY == IRQ_DONE, f"IRQ_STAT=0x{stat:x}"
    assert await _drain_rx(apb) == [0xA5], "read before any write returns the reset byte 0xA5"

    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_ADDR, 0x2A)
    await apb.write(I2C_TX_DATA, 0x6B)
    stat = await _run(dut, apb, cmd(start=1, write=1, stop=1, count=1))
    assert stat & IRQ_STICKY == IRQ_DONE, f"loopback write: IRQ_STAT=0x{stat:x} (no NACK expected)"
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    await apb.write(I2C_ADDR, 0x2A | 0x80)
    stat = await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=1))
    assert stat & IRQ_STICKY == IRQ_DONE
    assert await _drain_rx(apb) == [0x6B], "loopback read must return the last byte written"
    # A multi-byte loopback read: the internal slave presents the next byte after each master ACK.
    await apb.write(I2C_IRQ_CLR, IRQ_STICKY)
    stat = await _run(dut, apb, cmd(start=1, read=1, stop=1, nack_last=1, count=3))
    assert stat & IRQ_STICKY == IRQ_DONE
    assert await _drain_rx(apb) == [0x6B, 0x6B, 0x6B], "multi-byte loopback read"
    assert not bad, f"loopback drove the real pads at BFM ticks {bad[:5]}"
    assert slave.events == [], f"real bus saw loopback traffic: {slave.events}"
    slave.assert_clean()


@cocotb.test()
async def test_i2c_status_reflects_bus_levels(dut):
    """STATUS[5] / STATUS[6] are the SYNCHRONISED sensed SCL / SDA levels: both 1 on an idle bus,
    each drops when (and only when) its own line is held low externally, within the synchroniser
    latency, and returns when released."""
    apb, slave = await _setup(dut, enable=False)
    assert await _rd(apb, I2C_STATUS) & (ST_SCL | ST_SDA) == ST_SCL | ST_SDA

    for name, hold, bit, other in (
        ("SDA", slave.hold_sda_low, ST_SDA, ST_SCL),
        ("SCL", slave.hold_scl_low, ST_SCL, ST_SDA),
    ):
        hold(True)
        for n in range(1, 8):
            await _settled_edge(dut)
            if not await _peek(dut, I2C_STATUS) & bit:
                break
        else:
            raise AssertionError(f"STATUS never showed {name} low")
        dut._log.info("%s low reached STATUS after %d clk", name, n)
        # The DUT header: the engine samples the SYNCHRONISED lines, which lag the pins by
        # SYNC_STAGES (2) clk. A pad level that shows up sooner than that has bypassed the 2-FF
        # synchroniser -- functionally invisible to a glitch-free BFM, so latency is the only
        # observable (MUTATION TARGET: synchroniser bypass; found by the campaign, M32).
        assert n >= SYNC_STAGES, (
            f"{name} low reached STATUS after {n} clk, faster than the {SYNC_STAGES}-stage "
            f"synchroniser the header promises -- is the pad being sampled unsynchronised?"
        )
        assert n <= 5, f"{name} low took {n} clk to reach STATUS (2-FF synchroniser + mirror)"
        st = await _peek(dut, I2C_STATUS)
        assert st & other, f"holding {name} low must not pull the other line's bit"
        hold(False)
        await ClockCycles(dut.clk, 6)
        assert await _peek(dut, I2C_STATUS) & (ST_SCL | ST_SDA) == ST_SCL | ST_SDA
