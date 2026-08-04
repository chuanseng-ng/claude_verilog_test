"""
test_async_axi_fifo.py — GH #91 cocotb verification for the dual-clock AXI4
CDC bridge (rtl/soc/async_axi_fifo.sv), via the standalone wrapper
tb_async_axi_fifo.sv.

DUT: tb_async_axi_fifo (re-exports async_axi_fifo's s_*/m_* faces as flat
top-level ports, BFM naming convention, no _i/_o suffix).

s_* face = CPU domain, AXI SLAVE port -> AXI4Master(dut, "s", dut.s_clk).
m_* face = fabric domain, AXI MASTER port -> AXI4SlaveModel(dut, "m", dut.m_clk).
Both faces are ID-LESS on the RTL; m_awid/m_arid/m_bid/m_rid are wrapper-only
shim nets (see tb_async_axi_fifo.sv header) so axi4_slave_model.py's
unconditional id touches have somewhere to land.

**Two-Clock() mechanic** (a first for this repo, see the GH #91 plan): both
s_clk and m_clk are true top-level input ports written via VPI, so two
independent `Clock()` coroutines free-run with no HDL-internal timing
involved (`--no-timing` in the Makefile disables only HDL specify/intra-
assignment delays, not testbench-side Clock()/Timer()/RisingEdge()). cocotb
+ Verilator has no ReadWrite() — every driving loop below follows the same
RisingEdge-then-ReadOnly discipline as axi4_slave_model.py (never write a
signal from a ReadOnly context).

Every test is wrapped in `with_timeout(..., 50, "us")` (extended for the
one intentionally long stress test) so a real CDC deadlock fails the test
instead of hanging the whole `soc_all` regression.

Clock pairs exercised across this suite (ns): 4/9 and 9/4 (~2.25 ratio,
closest proxy for the real CPU:fabric ~1282:571 MHz split), 4/20 and 20/4
(wide ratio), 10/10 (the PLL_IMPL="STUB" equal-clock case), 10/11 (coprime —
edges slide continuously, the closest sim proxy for a violation-window
sweep).
"""

from types import SimpleNamespace

import cocotb
from axi4_slave_model import AXI4SlaveModel
from bfm.axi4_master import AXI4Master, RESP_OKAY
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Combine, ReadOnly, RisingEdge, Timer, with_timeout
from cocotb.utils import get_sim_time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESET_HOLD_NS = 300  # generous vs. SYNC_STAGES(2)+1 periods of any clock used here

AW_SIZE_4B = 0b010
BURST_INCR = 0b01

# ---------------------------------------------------------------------------
# Module-level task handle list (guard against cross-test coroutine leakage,
# same pattern as test_pmu.py's _active_tasks / _kill_active_tasks).
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------

async def _setup(dut, s_ns, m_ns, m_mem=None, start_slave_loops=True,
                  monitors=True, **slave_kwargs) -> SimpleNamespace:
    """Start both clocks, build the s-side master + m-side slave model,
    drive a common-root reset, and (optionally) launch the slave model's
    background loops and the no-VALID-withdrawal monitors. Returns a
    SimpleNamespace with everything a test might need to reach in and kill
    selectively (e.g. test 20 freezes only s_clk_task)."""
    _kill_active_tasks()

    s_clk_task = cocotb.start_soon(Clock(dut.s_clk, s_ns, units="ns").start())
    m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
    _active_tasks.append(s_clk_task)
    _active_tasks.append(m_clk_task)

    s_master = AXI4Master(dut, "s", dut.s_clk)
    m_slave = AXI4SlaveModel(dut, "m", dut.m_clk, mem=m_mem, **slave_kwargs)
    # Wrapper-only ID shim (async_axi_fifo is id-less on both faces) — tie
    # to 0 so axi4_slave_model.py's unconditional awid/arid reads land on
    # something.  See tb_async_axi_fifo.sv header.
    dut.m_awid.value = 0
    dut.m_arid.value = 0

    dut.s_rst_n.value = 0
    dut.m_rst_n.value = 0
    # A real-time hold (not clock-edge-counted) so it is correct regardless
    # of the s/m period ratio under test — always >> SYNC_STAGES(2)+1
    # periods of the slower clock in this suite's matrix (max period 20 ns).
    await Timer(RESET_HOLD_NS, units="ns")
    dut.s_rst_n.value = 1
    dut.m_rst_n.value = 1
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)

    slave_tasks = []
    if start_slave_loops:
        wt = cocotb.start_soon(m_slave._write_loop())
        rt = cocotb.start_soon(m_slave._read_loop())
        _active_tasks.extend([wt, rt])
        slave_tasks = [wt, rt]

    monitor_tasks = []
    if monitors:
        monitor_tasks = _start_no_withdrawal_monitors(dut)
        _active_tasks.extend(monitor_tasks)

    return SimpleNamespace(
        s_master=s_master,
        m_slave=m_slave,
        s_clk_task=s_clk_task,
        m_clk_task=m_clk_task,
        slave_tasks=slave_tasks,
        monitor_tasks=monitor_tasks,
    )


def _idle_s_side(dut) -> None:
    """Force all s-side stimulus signals idle. Used after killing a
    mid-flight AXI4Master coroutine (reset-while-busy tests) so a leaked
    valid/ready state does not confuse the next transaction."""
    dut.s_awvalid.value = 0
    dut.s_wvalid.value = 0
    dut.s_wlast.value = 0
    dut.s_arvalid.value = 0
    dut.s_bready.value = 0
    dut.s_rready.value = 0


# ---------------------------------------------------------------------------
# No-VALID-withdrawal monitors (test 16; started by every test per the plan)
# ---------------------------------------------------------------------------

async def _valid_no_withdrawal_monitor(dut, prefix, clock, vfield, rfield, rst_attr) -> None:
    """Once VALID is seen high without READY, it must still be high (or the
    handshake must have completed) on the very next edge — i.e. VALID is
    never withdrawn except by reset (checked via rst_attr on this same
    domain's synchronised reset)."""
    prev_bad = False
    while True:
        await RisingEdge(clock)
        await ReadOnly()
        rst_n = int(getattr(dut, rst_attr).value)
        v = int(getattr(dut, f"{prefix}_{vfield}").value)
        r = int(getattr(dut, f"{prefix}_{rfield}").value)
        if prev_bad and rst_n:
            assert v, (
                f"{prefix}_{vfield} withdrawn without a completed handshake "
                "(no reset in effect on this domain)"
            )
        prev_bad = bool(v and not r and rst_n)


def _start_no_withdrawal_monitors(dut) -> list:
    # Only the DUT-DRIVEN valid signals matter here (bridge protocol
    # compliance) — not the BFM-driven inputs (s_awvalid/m_bvalid/...),
    # which are stimulus, not something the bridge could violate.
    specs = [
        ("m", "awvalid", "awready", "m_rst_n", dut.m_clk),
        ("m", "wvalid", "wready", "m_rst_n", dut.m_clk),
        ("m", "arvalid", "arready", "m_rst_n", dut.m_clk),
        ("s", "bvalid", "bready", "s_rst_n", dut.s_clk),
        ("s", "rvalid", "rready", "s_rst_n", dut.s_clk),
    ]
    return [
        cocotb.start_soon(_valid_no_withdrawal_monitor(dut, p, clk, v, r, rst))
        for (p, v, r, rst, clk) in specs
    ]


# ---------------------------------------------------------------------------
# Raw single-channel drivers (bypass AXI4Master for scenarios where the test
# needs to control one channel's VALID/READY independent of the others —
# exact-depth fill, cross-flush buffering, B/R-fill backpressure).
# ---------------------------------------------------------------------------

async def _raw_aw_beat(dut, addr, awlen=0) -> None:
    await RisingEdge(dut.s_clk)
    dut.s_awaddr.value = addr
    dut.s_awlen.value = awlen
    dut.s_awsize.value = AW_SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_awready.value:
            break
        await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)
    dut.s_awvalid.value = 0


async def _raw_w_beat(dut, data, strb=0xF, last=True) -> None:
    await RisingEdge(dut.s_clk)
    dut.s_wdata.value = data
    dut.s_wstrb.value = strb
    dut.s_wlast.value = 1 if last else 0
    dut.s_wvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_wready.value:
            break
        await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)
    dut.s_wvalid.value = 0
    dut.s_wlast.value = 0


async def _raw_ar_beat(dut, addr, arlen=0) -> None:
    await RisingEdge(dut.s_clk)
    dut.s_araddr.value = addr
    dut.s_arlen.value = arlen
    dut.s_arsize.value = AW_SIZE_4B
    dut.s_arburst.value = BURST_INCR
    dut.s_arvalid.value = 1
    while True:
        await ReadOnly()
        if dut.s_arready.value:
            break
        await RisingEdge(dut.s_clk)
    await RisingEdge(dut.s_clk)
    dut.s_arvalid.value = 0


async def _raw_write_no_bready(dut, addr, data) -> None:
    """Push one single-beat write (AW+W) into the bridge WITHOUT touching
    s_bready — the caller controls B acceptance independently. AW and W are
    driven by two concurrent coroutines (independent AXI channels)."""
    t_aw = cocotb.start_soon(_raw_aw_beat(dut, addr))
    t_w = cocotb.start_soon(_raw_w_beat(dut, data))
    await Combine(t_aw, t_w)


async def _poll_until(clock, predicate, max_cycles=300, msg="condition"):
    """Poll `predicate()` (evaluated at ReadOnly) once per `clock` rising
    edge, up to max_cycles. Raises AssertionError with `msg` if it never
    becomes true — a real CDC latency (several SYNC_STAGES crossings +
    sequential slave-model processing) can take many cycles, so this is
    used instead of a fixed guessed wait everywhere the RTL's own state
    (not a fixed cycle count) is the thing that determines when to stop
    waiting."""
    for _ in range(max_cycles):
        await RisingEdge(clock)
        await ReadOnly()
        if predicate():
            await RisingEdge(clock)  # leave the caller in the active phase, safe to write signals
            return
    assert False, f"{msg}: not observed within {max_cycles} cycles"


async def _count_beats_until_full(dut, ready_attr, clock, max_iters):
    """Count successful VALID&&READY handshakes on one channel while VALID
    is held high throughout the call. READY is sampled in the ReadOnly
    phase that PRECEDES the RisingEdge which would consume it -- sampling
    it in the ReadOnly AFTER that edge (as a naive loop might) would
    already reflect the fifo's post-push state and undercount by exactly
    one the push that fills the very last slot."""
    count = 0
    for _ in range(max_iters):
        await ReadOnly()
        if not getattr(dut, ready_attr).value:
            break
        count += 1
        await RisingEdge(clock)
    await RisingEdge(clock)  # guarantee active phase regardless of which branch above ran
    return count


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# --- 1. reset defaults ------------------------------------------------------

async def _reset_defaults_body(dut):
    await _setup(dut, 10, 10)
    await ClockCycles(dut.s_clk, 2)
    await ClockCycles(dut.m_clk, 2)

    assert int(dut.s_awready.value) == 1, "AW fifo must be ready (empty) at reset"
    assert int(dut.s_wready.value) == 1, "W fifo must be ready (empty) at reset"
    assert int(dut.s_arready.value) == 1, "AR fifo must be ready (empty) at reset"
    assert int(dut.m_bready.value) == 1, "B fifo write-side must be ready (empty) at reset"
    assert int(dut.m_rready.value) == 1, "R fifo write-side must be ready (empty) at reset"

    assert int(dut.m_awvalid.value) == 0, "AW fifo read-side must be empty at reset"
    assert int(dut.m_wvalid.value) == 0, "W fifo read-side must be empty at reset"
    assert int(dut.m_arvalid.value) == 0, "AR fifo read-side must be empty at reset"
    assert int(dut.s_bvalid.value) == 0, "B fifo read-side must be empty at reset"
    assert int(dut.s_rvalid.value) == 0, "R fifo read-side must be empty at reset"
    dut._log.info("reset defaults OK: all write-sides ready, all read-sides empty")


@cocotb.test()
async def test_reset_defaults(dut):
    await with_timeout(_reset_defaults_body(dut), 50, "us")


# --- 2. single 4-beat write+read (GATE test) --------------------------------

async def _single_write_read_4beat_body(dut):
    # 4/9 ns: the real ~2.25 CPU:fabric ratio — the gate test proves the
    # two-Clock() mechanic on a genuine non-trivial ratio, not just 1:1.
    ctx = await _setup(dut, 4, 9)
    data_words = [0xAAAA0000, 0xBBBB1111, 0xCCCC2222, 0xDDDD3333]

    resp = await ctx.s_master.write(0x1000, data_words)
    assert resp == RESP_OKAY, f"write bresp={resp}"
    for i, w in enumerate(data_words):
        assert ctx.m_slave.mem[0x1000 + i * 4] == w, f"beat {i} mismatch in fabric mem"

    data, rresp = await ctx.s_master.read(0x1000, length=4)
    assert rresp == RESP_OKAY, f"read rresp={rresp}"
    assert data == data_words, f"read data {data} != {data_words}"
    dut._log.info("single 4-beat write+read OK (s_clk=4ns/m_clk=9ns) — two-Clock() mechanic confirmed")


@cocotb.test()
async def test_single_write_read_4beat(dut):
    await with_timeout(_single_write_read_4beat_body(dut), 50, "us")


# --- 3. full-throttle 64 write bursts ---------------------------------------

async def _full_throttle_write_bursts_body(dut):
    ctx = await _setup(dut, 10, 10)
    n = 64
    for i in range(n):
        resp = await ctx.s_master.write(0x20000 + i * 16, [0x30000000 + i])
        assert resp == RESP_OKAY, f"burst {i}: bresp={resp}"
    for i in range(n):
        assert ctx.m_slave.mem[0x20000 + i * 16] == 0x30000000 + i
    dut._log.info(f"full-throttle write OK: {n} back-to-back single-beat bursts, no delays")


@cocotb.test()
async def test_full_throttle_write_bursts(dut):
    await with_timeout(_full_throttle_write_bursts_body(dut), 50, "us")


# --- 4. full-throttle 64 read bursts -----------------------------------------

async def _full_throttle_read_bursts_body(dut):
    ctx = await _setup(dut, 10, 10)
    n = 64
    for i in range(n):
        ctx.m_slave.mem[0x21000 + i * 16] = 0x40000000 + i
    for i in range(n):
        data, rresp = await ctx.s_master.read(0x21000 + i * 16)
        assert rresp == RESP_OKAY
        assert data[0] == 0x40000000 + i, f"burst {i}: data={data[0]:#x}"
    dut._log.info(f"full-throttle read OK: {n} back-to-back single-beat bursts, no delays")


@cocotb.test()
async def test_full_throttle_read_bursts(dut):
    await with_timeout(_full_throttle_read_bursts_body(dut), 50, "us")


# --- 5. backpressure fabric side (slave-model delays) -----------------------

async def _backpressure_fabric_side_body(dut):
    ctx = await _setup(dut, 10, 10, aw_delay=3, w_delay=2, b_delay=3, ar_delay=3, r_delay=2)
    n = 8
    for i in range(n):
        resp = await ctx.s_master.write(0x22000 + i * 4, [0x50000000 + i])
        assert resp == RESP_OKAY
    for i in range(n):
        data, rresp = await ctx.s_master.read(0x22000 + i * 4)
        assert rresp == RESP_OKAY, f"read {i}: rresp={rresp}"
        assert data[0] == 0x50000000 + i
    dut._log.info("fabric-side backpressure OK: slave-model AW/W/B/AR/R delays absorbed cleanly")


@cocotb.test()
async def test_backpressure_fabric_side(dut):
    await with_timeout(_backpressure_fabric_side_body(dut), 50, "us")


# --- 6. backpressure CPU side (B/R fill) ------------------------------------

async def _drain_n_beats(dut, valid_attr, clock, n, check=None):
    """Pop exactly n beats off a channel whose READY the caller already set
    (and holds) to 1. Uses the same ReadOnly-before-commit-edge discipline
    as _count_beats_until_full: sampling READY/VALID in the ReadOnly phase
    that PRECEDES the commit edge, then exactly ONE RisingEdge per beat.
    (A naive "RisingEdge; check; RisingEdge-again" loop is wrong here: with
    READY held high throughout, that trailing edge can itself commit a
    SECOND, unintended pop whenever VALID is still high going into it.)"""
    for _ in range(n):
        await ReadOnly()
        while not getattr(dut, valid_attr).value:
            await RisingEdge(clock)
            await ReadOnly()
        if check is not None:
            check()
        await RisingEdge(clock)  # commits exactly this one beat


async def _backpressure_cpu_side_body(dut):
    ctx = await _setup(dut, 10, 10)
    dut.s_bready.value = 0
    dut.s_rready.value = 0

    b_depth = int(dut.b_depth_o.value)
    r_depth = int(dut.r_depth_o.value)

    # Push b_depth single-beat writes (AW+W only — B is never accepted) so
    # the fabric-domain responses accumulate and the B fifo fills. Each
    # push only waits for its OWN AW+W acceptance (not for the slave to
    # finish processing it), so wait for m_bready to actually drop --
    # sequential slave-model processing + CDC crossing latency (several
    # SYNC_STAGES hops) easily exceeds a fixed small cycle count.
    for i in range(b_depth):
        await _raw_write_no_bready(dut, 0x23000 + i * 4, 0xB0000000 + i)
    await _poll_until(dut.m_clk, lambda: not dut.m_bready.value, max_cycles=300,
                       msg="B fifo never reported FULL (m_bready low)")

    def _check_bresp():
        assert int(dut.s_bresp.value) == RESP_OKAY, f"bresp={int(dut.s_bresp.value)}"

    dut.s_bready.value = 1
    await _drain_n_beats(dut, "s_bvalid", dut.s_clk, b_depth, check=_check_bresp)
    dut.s_bready.value = 0

    # Same story on the read side: fill R by not accepting on s_rready.
    for i in range(r_depth):
        await _raw_ar_beat(dut, 0x24000 + i * 4)
    await _poll_until(dut.m_clk, lambda: not dut.m_rready.value, max_cycles=300,
                       msg="R fifo never reported FULL (m_rready low)")

    dut.s_rready.value = 1
    await _drain_n_beats(dut, "s_rvalid", dut.s_clk, r_depth)
    dut.s_rready.value = 0
    dut._log.info(f"CPU-side backpressure OK: B fifo ({b_depth}) and R fifo ({r_depth}) filled + drained")


@cocotb.test()
async def test_backpressure_cpu_side(dut):
    await with_timeout(_backpressure_cpu_side_body(dut), 50, "us")


# --- 7. exact-depth-full -----------------------------------------------------

async def _exact_depth_full_body(dut):
    await _setup(dut, 10, 10, start_slave_loops=False)

    aw_depth = int(dut.aw_depth_o.value)
    dut.s_awaddr.value = 0x60000
    dut.s_awlen.value = 0
    dut.s_awsize.value = AW_SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    count_aw = await _count_beats_until_full(dut, "s_awready", dut.s_clk, aw_depth + 4)
    dut.s_awvalid.value = 0
    assert count_aw == aw_depth, f"AW fifo accepted {count_aw}, expected EXACTLY {aw_depth}"

    w_depth = int(dut.w_depth_o.value)
    dut.s_wdata.value = 0x1
    dut.s_wstrb.value = 0xF
    dut.s_wlast.value = 1
    dut.s_wvalid.value = 1
    count_w = await _count_beats_until_full(dut, "s_wready", dut.s_clk, w_depth + 4)
    dut.s_wvalid.value = 0
    dut.s_wlast.value = 0
    assert count_w == w_depth, f"W fifo accepted {count_w}, expected EXACTLY {w_depth}"

    dut._log.info(f"exact-depth-full OK: AW accepted {count_aw}/{aw_depth}, W accepted {count_w}/{w_depth}")


@cocotb.test()
async def test_exact_depth_full(dut):
    await with_timeout(_exact_depth_full_body(dut), 50, "us")


# --- 8. pointer wrap + near-empty ping-pong ----------------------------------

async def _pointer_wrap_ping_pong_body(dut):
    ctx = await _setup(dut, 10, 10)
    n = 3 * int(dut.w_depth_o.value)  # wraps AW/W/B (and AR/R below) several times

    for i in range(n):
        resp = await ctx.s_master.write(0x25000 + (i % 16) * 4, [0x70000000 + i])
        assert resp == RESP_OKAY, f"write {i}: bresp={resp}"

    for i in range(n):
        data, rresp = await ctx.s_master.read(0x25000 + ((n - 1) % 16) * 4)
        assert rresp == RESP_OKAY

    # Near-empty ping-pong: single push, single pop, repeated across the
    # full pointer range so every pointer value is visited at depth 0/1.
    depth = int(dut.aw_depth_o.value)
    for i in range(2 * depth + 2):
        resp = await ctx.s_master.write(0x26000, [0x80000000 + i])
        assert resp == RESP_OKAY
        data, rresp = await ctx.s_master.read(0x26000)
        assert rresp == RESP_OKAY, f"ping-pong {i}: rresp={rresp}"
        assert data[0] == 0x80000000 + i, f"ping-pong {i}: {data[0]:#x}"
    dut._log.info(f"pointer wrap OK: {n} fill/drain writes+reads, {2 * depth + 2} near-empty ping-pongs")


@cocotb.test()
async def test_pointer_wrap_ping_pong(dut):
    await with_timeout(_pointer_wrap_ping_pong_body(dut), 50, "us")


# --- 9. reset-while-busy, s side ---------------------------------------------

async def _reset_while_busy_s_side_body(dut):
    """Mid-burst reset on the s side must be a hard flush: whatever the
    master had in flight is discarded, and the bridge recovers cleanly for
    genuinely NEW transactions afterward.

    Kill-timing note (fixed 2026-08-01, alongside the cdc_gray_fifo
    wr_ready_o reset-gating fix, commit 7a9f9d4): the interrupted master
    task is killed AT reset assertion, not after release+settling. A real
    AXI master is itself part of the domain this reset covers, so its own
    issuing FSM would be wiped by the very same reset edge -- it would never
    "resume" a half-issued burst afterward without re-establishing AW, since
    the bridge's hard flush (rst_both_n) drops the AW entry it already
    latched right along with the W data. Killing after settling (the
    original ordering) let this un-reset Python coroutine do exactly the
    invalid thing a real master never would: with the wr_ready_o fix's
    correct backpressure, the still-alive task would block through reset,
    then resume pushing its remaining W-beats (with no matching AW, since
    that entry was flushed) the moment s_wready recovered -- silently
    queuing orphaned W data ahead of the deliberately-fresh 0x50100
    transaction below and corrupting its read-back. That failure
    (`test_reset_while_busy_s_side` reading back 0x2222, one of the
    orphaned beats, instead of 0xCAFEBABE) was a testbench modeling gap
    exposed BY the RTL fix, not a new RTL defect -- pre-fix, wr_ready_o
    read 1 throughout the reset pulse, so the burst completed falsely-
    instantly before the old, later kill() ever ran, hiding the gap.
    """
    ctx = await _setup(dut, 10, 10)

    async def _wr():
        return await ctx.s_master.write(0x50000, [0x1111, 0x2222, 0x3333, 0x4444])

    t = cocotb.start_soon(_wr())
    await ClockCycles(dut.s_clk, 3)
    dut.s_rst_n.value = 0
    # Kill + idle immediately -- models the master's own reset, not a
    # surviving driver resuming mid-burst across the DUT's reset boundary.
    t.kill()
    _idle_s_side(dut)
    await ClockCycles(dut.s_clk, 5)
    dut.s_rst_n.value = 1
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)

    await ClockCycles(dut.s_clk, 2)
    assert int(dut.s_awready.value) == 1
    assert int(dut.s_wready.value) == 1
    assert int(dut.s_arready.value) == 1

    resp = await ctx.s_master.write(0x50100, [0xCAFEBABE])
    assert resp == RESP_OKAY
    data, rresp = await ctx.s_master.read(0x50100)
    assert rresp == RESP_OKAY, f"post-reset read rresp={rresp}"
    assert data[0] == 0xCAFEBABE
    dut._log.info("reset-while-busy (s side) OK: interrupted write recovered cleanly")


@cocotb.test()
async def test_reset_while_busy_s_side(dut):
    await with_timeout(_reset_while_busy_s_side_body(dut), 50, "us")


# --- 10. reset-while-busy, m side ---------------------------------------------

async def _reset_while_busy_m_side_body(dut):
    ctx = await _setup(dut, 10, 10)
    ctx.m_slave.mem[0x40000] = 0xBEEF0001

    async def _rd():
        return await ctx.s_master.read(0x40000, length=4)

    t = cocotb.start_soon(_rd())
    await ClockCycles(dut.m_clk, 3)
    dut.m_rst_n.value = 0
    await ClockCycles(dut.m_clk, 5)
    dut.m_rst_n.value = 1
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)
    t.kill()
    _idle_s_side(dut)

    await ClockCycles(dut.s_clk, 2)
    assert int(dut.s_arready.value) == 1, "AR channel must recover ready after m-side reset"
    assert int(dut.s_awready.value) == 1
    assert int(dut.s_wready.value) == 1

    resp = await ctx.s_master.write(0x40100, [0x1234ABCD])
    assert resp == RESP_OKAY
    data, rresp = await ctx.s_master.read(0x40100)
    assert rresp == RESP_OKAY, f"post-reset read rresp={rresp}"
    assert data[0] == 0x1234ABCD
    dut._log.info("reset-while-busy (m side) OK: interrupted read recovered cleanly")


@cocotb.test()
async def test_reset_while_busy_m_side(dut):
    await with_timeout(_reset_while_busy_m_side_body(dut), 50, "us")


# --- 11. cross-flush ----------------------------------------------------------

async def _cross_flush_body(dut):
    await _setup(dut, 10, 10, start_slave_loops=False)
    depth = int(dut.aw_depth_o.value)

    # Buffer 2 (not full) AW entries — m_awready never asserted since the
    # slave loop was never started, so nothing drains them.
    for i in range(2):
        await _raw_aw_beat(dut, 0x27000 + i * 4)
    await ClockCycles(dut.s_clk, 2)
    assert int(dut.s_awready.value) == 1, "AW fifo should not be full with only 2 entries buffered"

    # Assert ONLY m_rst_n. s_rst_n is held high throughout — the point of
    # this test is that a single-side reset still flushes BOTH domains via
    # rst_both_n = s_rst_n_i & m_rst_n_i.
    dut.m_rst_n.value = 0
    await ClockCycles(dut.m_clk, 6)
    dut.m_rst_n.value = 1
    await ClockCycles(dut.s_clk, 4)
    await ClockCycles(dut.m_clk, 4)

    assert int(dut.s_awready.value) == 1, "far face (s) did not quiesce after m-only reset pulse"

    # Prove the buffered entries were actually FLUSHED (not merely stalled):
    # a fresh push must accept the FULL depth again, not depth-2.
    dut.s_awaddr.value = 0x28000
    dut.s_awlen.value = 0
    dut.s_awsize.value = AW_SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    count = await _count_beats_until_full(dut, "s_awready", dut.s_clk, depth + 4)
    dut.s_awvalid.value = 0
    assert count == depth, (
        f"post-cross-flush AW fifo accepted {count}, expected full depth={depth} "
        "-- old entries were not flushed by the far-side-only reset"
    )
    dut._log.info(f"cross-flush OK: m-only reset pulse quiesced s face and flushed all {depth} slots")


@cocotb.test()
async def test_cross_flush(dut):
    await with_timeout(_cross_flush_body(dut), 50, "us")


# --- 12-15. clock ratio sweeps -------------------------------------------------

async def _ratio_sweep_workload(dut, s_ns, m_ns, n=8):
    ctx = await _setup(dut, s_ns, m_ns)
    for i in range(n):
        resp = await ctx.s_master.write(0x30000 + i * 4, [0x60000000 + i])
        assert resp == RESP_OKAY
    for i in range(n):
        data, rresp = await ctx.s_master.read(0x30000 + i * 4)
        assert rresp == RESP_OKAY, f"txn {i}: rresp={rresp}"
        assert data[0] == 0x60000000 + i, f"txn {i}: {data[0]:#x}"
    dut._log.info(f"clock ratio {s_ns}/{m_ns} ns OK: {n} write+read round trips")


@cocotb.test()
async def test_clock_ratio_slow_to_fast(dut):
    await with_timeout(_ratio_sweep_workload(dut, 20, 4), 50, "us")


@cocotb.test()
async def test_clock_ratio_fast_to_slow(dut):
    await with_timeout(_ratio_sweep_workload(dut, 4, 20), 50, "us")


@cocotb.test()
async def test_clock_ratio_equal(dut):
    await with_timeout(_ratio_sweep_workload(dut, 10, 10), 50, "us")


@cocotb.test()
async def test_clock_ratio_coprime_phase_drift(dut):
    # >= 200 total AXI transactions (100 write + 100 read) at a coprime
    # 10/11 ns pair -- edges slide continuously across the entire run,
    # the closest sim proxy for a real metastability-window sweep.
    await with_timeout(_ratio_sweep_workload(dut, 10, 11, n=100), 50, "us")


# --- 16. no-VALID-withdrawal stress -------------------------------------------

async def _no_valid_withdrawal_stress_body(dut):
    ctx = await _setup(dut, 9, 4, aw_delay=1, w_delay=1, b_delay=2, ar_delay=1, r_delay=2)
    n = 20
    for i in range(n):
        resp = await ctx.s_master.write(0x13000 + i * 4, [0x20000000 + i], ready_delay=(i % 3))
        assert resp == RESP_OKAY
    for i in range(n):
        data, rresp = await ctx.s_master.read(0x13000 + i * 4, ready_delay=(i % 3))
        assert rresp == RESP_OKAY, f"txn {i}: rresp={rresp}"
        assert data[0] == 0x20000000 + i
    # Pass condition is implicit: the background _valid_no_withdrawal_monitor
    # tasks (started by _setup) would have raised AssertionError by now if
    # any DUT-driven VALID was withdrawn without a completed handshake.
    dut._log.info(f"no-VALID-withdrawal stress OK: {2 * n} delayed transactions, monitors clean")


@cocotb.test()
async def test_no_valid_withdrawal_stress(dut):
    await with_timeout(_no_valid_withdrawal_stress_body(dut), 50, "us")


# --- 17. burst integrity -------------------------------------------------------

async def _burst_integrity_body(dut):
    ctx = await _setup(dut, 10, 10)
    length = 6
    data_words = [0x10000000 + i for i in range(length)]

    w_beats = 0
    w_lasts = 0

    async def _monitor_w():
        nonlocal w_beats, w_lasts
        while True:
            await RisingEdge(dut.m_clk)
            await ReadOnly()
            if dut.m_wvalid.value and dut.m_wready.value:
                w_beats += 1
                if dut.m_wlast.value:
                    w_lasts += 1

    mon_w = cocotb.start_soon(_monitor_w())
    resp = await ctx.s_master.write(0x11000, data_words)
    mon_w.kill()
    assert resp == RESP_OKAY
    assert w_beats == length, f"m_wvalid&&m_wready beats={w_beats}, expected {length} (= awlen+1)"
    assert w_lasts == 1, f"m_wlast asserted {w_lasts} times, expected exactly 1"

    r_beats = 0
    r_lasts = 0

    async def _monitor_r():
        nonlocal r_beats, r_lasts
        while True:
            await RisingEdge(dut.s_clk)
            await ReadOnly()
            if dut.s_rvalid.value and dut.s_rready.value:
                r_beats += 1
                if dut.s_rlast.value:
                    r_lasts += 1

    mon_r = cocotb.start_soon(_monitor_r())
    data, rresp = await ctx.s_master.read(0x11000, length=length)
    mon_r.kill()
    assert rresp == RESP_OKAY, f"burst read rresp={rresp}"
    assert data == data_words
    assert r_beats == length, f"s_rvalid&&s_rready beats={r_beats}, expected {length}"
    assert r_lasts == 1, f"s_rlast asserted {r_lasts} times, expected exactly 1"
    dut._log.info(f"burst integrity OK: {length}-beat burst, exactly one wlast/rlast, beat count matches awlen+1")


@cocotb.test()
async def test_burst_integrity(dut):
    await with_timeout(_burst_integrity_body(dut), 50, "us")


# --- 18. concurrent read+write -------------------------------------------------

async def _concurrent_read_write_body(dut):
    ctx = await _setup(dut, 9, 4)
    ctx.m_slave.mem[0x12100] = 0xCAFEF00D

    async def _do_write():
        return await ctx.s_master.write(0x12000, [0xABCD1234])

    async def _do_read():
        return await ctx.s_master.read(0x12100)

    # AW/W/B and AR/R are 5 fully independent FIFOs (no shared signal
    # between the write side and the read side), so running write() and
    # read() concurrently is safe and is exactly what this test verifies.
    t_w = cocotb.start_soon(_do_write())
    t_r = cocotb.start_soon(_do_read())
    await Combine(t_w, t_r)

    assert t_w.result() == RESP_OKAY
    data, rresp = t_r.result()
    assert rresp == RESP_OKAY, f"concurrent read rresp={rresp}"
    assert data[0] == 0xCAFEF00D
    assert ctx.m_slave.mem[0x12000] == 0xABCD1234
    dut._log.info("concurrent read+write OK: independent AW/W/B vs AR/R channels did not interfere")


@cocotb.test()
async def test_concurrent_read_write(dut):
    await with_timeout(_concurrent_read_write_body(dut), 50, "us")


# --- 19. no deadlock with all five FIFOs full ----------------------------------

async def _no_deadlock_all_fifos_full_body(dut):
    ctx = await _setup(dut, 10, 10)
    dut.s_bready.value = 0
    dut.s_rready.value = 0

    aw_depth = int(dut.aw_depth_o.value)
    b_depth = int(dut.b_depth_o.value)
    ar_depth = int(dut.ar_depth_o.value)
    r_depth = int(dut.r_depth_o.value)

    # The slave model is STRICTLY SEQUENTIAL (one AW/W/B transaction fully
    # in flight at a time) and its AW-capture readiness is gated on
    # completing the PREVIOUS transaction's B phase. With s_bready held
    # low, B fills after b_depth transactions, the slave then captures ONE
    # more AW+W (queued ahead of it) and wedges trying to post ITS B, and
    # after that m_awready is permanently 0 until s_bready frees B again.
    # So b_depth + 1 + aw_depth is the maximum number of write pushes that
    # can EVER be absorbed before B is released -- pushing more would be a
    # self-inflicted deadlock in the TEST (not the DUT). Same reasoning for
    # the read side with r_depth/ar_depth (independent coroutine, unaffected
    # by the write side's stall).
    n_wr = b_depth + 1 + aw_depth
    n_rd = r_depth + 1 + ar_depth

    for i in range(n_wr):
        await _raw_write_no_bready(dut, 0x2A000 + i * 4, 0xD0000000 + i)
    for i in range(n_rd):
        await _raw_ar_beat(dut, 0x2B000 + i * 4)

    # Confirm genuine saturation (not just "we stopped pushing"): AW must
    # now be refusing further beats (m_awready permanently 0 from the
    # slave's wedge, so the AW fifo itself is at or approaching full).
    await _poll_until(dut.m_clk, lambda: not dut.m_bready.value, max_cycles=300,
                       msg="B fifo never reported FULL")
    await _poll_until(dut.m_clk, lambda: not dut.m_rready.value, max_cycles=300,
                       msg="R fifo never reported FULL")

    # Release everything and confirm a full, clean drain -- THIS is the
    # actual "no deadlock" claim: saturation is normal backpressure, a
    # permanent wedge after release would be a real deadlock, and the
    # outer with_timeout(50us) is the ultimate detector for that.
    dut.s_bready.value = 1
    dut.s_rready.value = 1
    await _poll_until(
        dut.s_clk,
        lambda: (dut.s_awready.value and dut.s_wready.value and dut.m_bready.value
                  and dut.m_rready.value and not dut.s_bvalid.value and not dut.s_rvalid.value),
        max_cycles=500, msg="bridge never fully drained after releasing s_bready/s_rready",
    )
    dut._log.info(
        f"no-deadlock-all-full OK: saturated (wr pushes={n_wr}, rd pushes={n_rd}) then fully drained with no wedge"
    )


@cocotb.test()
async def test_no_deadlock_all_fifos_full(dut):
    await with_timeout(_no_deadlock_all_fifos_full_body(dut), 50, "us")


# --- 20. no combinational crossing ---------------------------------------------

async def _no_combinational_crossing_body(dut):
    ctx = await _setup(dut, 10, 10)
    dut.s_bready.value = 0
    dut.s_rready.value = 0

    # Leave ONE valid, UNCONSUMED entry sitting in both B and R (s_bready/
    # s_rready held low) before freezing -- with the fifo EMPTY, s_rdata_o/
    # s_bresp_o are documented don't-cares that legitimately advance
    # speculatively for the next (not-yet-valid) write (see cdc_gray_fifo.sv
    # header: "cannot become VISIBLE... until the gray pointer has
    # propagated"); the actual contract under test is that an ALREADY-VALID
    # entry's data must not move, so there must be a real rd_valid_o=1
    # entry present when the snapshot is taken.
    await _raw_write_no_bready(dut, 0xC000, 0x5A5A5A5A)
    await _raw_ar_beat(dut, 0xC100)
    await _poll_until(dut.s_clk, lambda: dut.s_bvalid.value and dut.s_rvalid.value,
                       max_cycles=300, msg="setup: B/R never became valid before freeze")

    # Stop the slave-model background loops so ONLY this test's direct
    # pokes drive the m-side inputs from here on (no fighting coroutines).
    for t in ctx.slave_tasks:
        t.kill()
    await ClockCycles(dut.s_clk, 2)

    snapshot = (
        int(dut.s_awready.value), int(dut.s_wready.value), int(dut.s_arready.value),
        int(dut.s_bvalid.value), int(dut.s_bresp.value),
        int(dut.s_rvalid.value), int(dut.s_rdata.value), int(dut.s_rresp.value), int(dut.s_rlast.value),
    )

    # Freeze s_clk permanently for the rest of this test.
    ctx.s_clk_task.kill()

    for i in range(30):
        await RisingEdge(dut.m_clk)
        dut.m_awready.value = i & 1
        dut.m_wready.value = (i >> 1) & 1
        dut.m_bvalid.value = (i >> 2) & 1
        dut.m_bresp.value = i & 0x3
        dut.m_arready.value = (i >> 3) & 1
        dut.m_rvalid.value = (i >> 4) & 1
        dut.m_rdata.value = 0xDEAD0000 + i
        dut.m_rresp.value = i & 0x3
        dut.m_rlast.value = i & 1

    after = (
        int(dut.s_awready.value), int(dut.s_wready.value), int(dut.s_arready.value),
        int(dut.s_bvalid.value), int(dut.s_bresp.value),
        int(dut.s_rvalid.value), int(dut.s_rdata.value), int(dut.s_rresp.value), int(dut.s_rlast.value),
    )
    assert after == snapshot, (
        f"s-side outputs moved while s_clk was frozen: before={snapshot} after={after} "
        "-- possible combinational s<-m crossing"
    )
    dut._log.info("no-combinational-crossing OK: s-side outputs static across 30 frozen-s_clk m_clk edges")


@cocotb.test()
async def test_no_combinational_crossing(dut):
    await with_timeout(_no_combinational_crossing_body(dut), 50, "us")


# --- 21. latency budget ---------------------------------------------------------

async def _latency_budget_body(dut):
    # s_clk=4ns / m_clk=9ns: the real ~2.25 CPU:fabric ratio (GH #93's
    # eventual integration case), so this number is a usable budget input.
    ctx = await _setup(dut, 4, 9)

    t0 = get_sim_time(units="ns")
    resp = await ctx.s_master.write(0x10000, [0x11223344])
    t1 = get_sim_time(units="ns")
    assert resp == RESP_OKAY
    write_latency_ns = t1 - t0

    t2 = get_sim_time(units="ns")
    data, rresp = await ctx.s_master.read(0x10000)
    t3 = get_sim_time(units="ns")
    assert rresp == RESP_OKAY, f"latency-budget read rresp={rresp}"
    assert data[0] == 0x11223344
    read_latency_ns = t3 - t2

    dut._log.info(
        "GH #93 CDC round-trip latency budget (s_clk=4ns/m_clk=9ns): "
        f"single-beat write={write_latency_ns:.1f} ns, single-beat read={read_latency_ns:.1f} ns"
    )

    # Loose sanity bound only (NOT a spec number): a single-beat round trip
    # should not take more than ~50 slow-domain (9 ns) periods even with
    # SYNC_STAGES=2 crossings on both legs of each of the 2 channels
    # involved (AW+W+B for the write, AR+R for the read).
    loose_bound_ns = 50 * 9
    assert write_latency_ns < loose_bound_ns, f"write latency {write_latency_ns} ns exceeds loose bound {loose_bound_ns} ns"
    assert read_latency_ns < loose_bound_ns, f"read latency {read_latency_ns} ns exceeds loose bound {loose_bound_ns} ns"


@cocotb.test()
async def test_latency_budget(dut):
    await with_timeout(_latency_budget_body(dut), 50, "us")


# --- 22. white-box: gray pointer single-bit change (best-effort) ---------------

async def _white_box_gray_pointer_body(dut):
    ctx = await _setup(dut, 10, 10)
    try:
        node = dut.u_dut.u_w_fifo.wr_gray_q
    except AttributeError:
        dut._log.warning(
            "white-box wr_gray_q not visible under this sim/build -- skipping (best-effort per the GH #91 plan)"
        )
        return

    prev = int(node.value)
    changes = 0
    for i in range(40):
        resp = await ctx.s_master.write(0xF000 + (i % 16) * 4, [0xF0000000 + i])
        assert resp == RESP_OKAY
        curr = int(node.value)
        if curr != prev:
            popcount = bin(curr ^ prev).count("1")
            assert popcount <= 1, (
                f"wr_gray_q changed by {popcount} bits in one step "
                f"(prev={prev:#x} curr={curr:#x}) -- not a valid single-bit gray transition"
            )
            changes += 1
        prev = curr
    assert changes > 0, "wr_gray_q never changed value -- test did not exercise the pointer"
    dut._log.info(f"white-box gray-pointer OK: {changes} valid <=1-bit transitions observed over 40 writes")


@cocotb.test()
async def test_white_box_gray_pointer_single_bit_change(dut):
    await with_timeout(_white_box_gray_pointer_body(dut), 50, "us")


# =============================================================================
# GH #95 (Group A): reset-asymmetry test class.
#
# design_state.json's gh93_cdc_verification record documents that BOTH RTL
# bugs GH #93 found (commit 4398c2e -- soc_top.sv's cpu_gated_clk stopped
# during the CPU's own reset window; commit 7a9f9d4 -- this module's
# cdc_gray_fifo.sv wr_ready_o not gated by wr_rst_n_i) shared one root
# signature: a reset value that advertises availability while cross-domain
# readiness has not actually been established -- invisible whenever both
# domains release reset together, which was every scenario before GH #93's
# genuinely divergent-ratio SoC boot ever ran.
#
# async_axi_fifo.sv's reset strategy is "hard flush, common root": BOTH
# s_rst_n_i and m_rst_n_i feed rst_both_n = s_rst_n_i & m_rst_n_i, which
# feeds BOTH per-domain cdc_reset_sync instances (see async_axi_fifo.sv
# header -- this is NOT decoupled the way apb_cdc_bridge's post-#93 fix is;
# see that file's tests below for the asymmetric case). Consequence: holding
# EITHER physical reset input low holds BOTH domains' internal synchronised
# resets (s_rst_sync_n AND m_rst_sync_n) low, regardless of which physical
# clock is still ticking. These tests exploit exactly that: hold one
# physical input low (or release it on a staggered delay after the other),
# keep BOTH clocks free-running throughout (Clock() coroutines here are
# never reset-gated -- only the RTL's internal state is), and offer
# full-throttle traffic on all 5 channels simultaneously. The essential
# property under test: while EITHER physical reset input is low, every
# *_ready output must read 0 (zero acceptance) and every read-side *_valid
# output must read 0 (zero silent pass-through) -- exactly what 7a9f9d4
# fixed (`wr_ready_o = wr_rst_n_i && !full_q`, not just `!full_q`). After
# both inputs release, one real transaction must complete cleanly, exactly
# once, proving nothing offered during the rejected window was silently
# latched.
#
# Metastability injection is not modelable in Verilator/cocotb -- these
# tests characterise the synchronised, deterministic RTL behaviour only.
# =============================================================================

RESP_OKAY_LOCAL = 0b00  # RESP_OKAY re-derived locally for the m_bresp/m_rresp raw drives below


def _drive_offer_all_channels(dut) -> None:
    """Assert VALID with a legal-looking payload on all 5 channels
    simultaneously (s-side AW/W/AR *and* m-side B/R), and hold the m-side
    *ready inputs high (downstream always-ready) so any false accept on the
    bridge's read-side outputs would be immediately observable. Does NOT
    wait for READY -- the caller samples readiness itself via
    _assert_zero_accept_window."""
    dut.s_awaddr.value = 0x50000
    dut.s_awlen.value = 0
    dut.s_awsize.value = AW_SIZE_4B
    dut.s_awburst.value = BURST_INCR
    dut.s_awvalid.value = 1
    dut.s_wdata.value = 0xA5A5A5A5
    dut.s_wstrb.value = 0xF
    dut.s_wlast.value = 1
    dut.s_wvalid.value = 1
    dut.s_araddr.value = 0x50000
    dut.s_arlen.value = 0
    dut.s_arsize.value = AW_SIZE_4B
    dut.s_arburst.value = BURST_INCR
    dut.s_arvalid.value = 1
    dut.s_bready.value = 1
    dut.s_rready.value = 1
    dut.m_bvalid.value = 1
    dut.m_bresp.value = RESP_OKAY_LOCAL
    dut.m_rvalid.value = 1
    dut.m_rdata.value = 0x5A5A5A5A
    dut.m_rresp.value = RESP_OKAY_LOCAL
    dut.m_rlast.value = 1
    dut.m_awready.value = 1
    dut.m_wready.value = 1
    dut.m_arready.value = 1


def _quiesce_offer(dut) -> None:
    _idle_s_side(dut)
    dut.m_bvalid.value = 0
    dut.m_rvalid.value = 0
    dut.m_awready.value = 0
    dut.m_wready.value = 0
    dut.m_arready.value = 0


async def _assert_zero_accept_window(dut, clock, n_cycles, ctx_label) -> None:
    """Sample every *_ready and read-side *_valid output once per `clock`
    edge for n_cycles; every one must read 0 throughout -- zero acceptance,
    zero silent pass-through, while either physical reset is asserted."""
    for i in range(n_cycles):
        await RisingEdge(clock)
        await ReadOnly()
        assert int(dut.s_awready.value) == 0, f"{ctx_label}: s_awready asserted (cycle {i})"
        assert int(dut.s_wready.value) == 0, f"{ctx_label}: s_wready asserted (cycle {i})"
        assert int(dut.s_arready.value) == 0, f"{ctx_label}: s_arready asserted (cycle {i})"
        assert int(dut.m_bready.value) == 0, f"{ctx_label}: m_bready asserted (cycle {i})"
        assert int(dut.m_rready.value) == 0, f"{ctx_label}: m_rready asserted (cycle {i})"
        assert int(dut.m_awvalid.value) == 0, f"{ctx_label}: m_awvalid (accepted!) (cycle {i})"
        assert int(dut.m_wvalid.value) == 0, f"{ctx_label}: m_wvalid (accepted!) (cycle {i})"
        assert int(dut.m_arvalid.value) == 0, f"{ctx_label}: m_arvalid (accepted!) (cycle {i})"
        assert int(dut.s_bvalid.value) == 0, f"{ctx_label}: s_bvalid (accepted!) (cycle {i})"
        assert int(dut.s_rvalid.value) == 0, f"{ctx_label}: s_rvalid (accepted!) (cycle {i})"
    # Leave the caller in a writable (post-RisingEdge, pre-ReadOnly) phase --
    # the loop above always exits from a ReadOnly context, and cocotb+
    # Verilator has no ReadWrite(); writing a signal immediately after a bare
    # ReadOnly() raises "scheduled during a read-only sync phase" (same
    # discipline as _poll_until above).
    await RisingEdge(clock)


async def _recover_and_verify_once(dut, addr, wdata) -> None:
    """After both resets have released and offered signals were quiesced,
    build a fresh AXI4Master/AXI4SlaveModel pair, start the slave loops, and
    prove exactly one clean write+read round trip -- confirms nothing from
    the rejected offer window was silently latched or duplicated."""
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)
    s_master = AXI4Master(dut, "s", dut.s_clk)
    m_slave = AXI4SlaveModel(dut, "m", dut.m_clk)
    dut.m_awid.value = 0
    dut.m_arid.value = 0
    wt = cocotb.start_soon(m_slave._write_loop())
    rt = cocotb.start_soon(m_slave._read_loop())
    _active_tasks.extend([wt, rt])
    resp = await s_master.write(addr, [wdata])
    assert resp == RESP_OKAY, f"post-recovery write at {addr:#x} failed (resp={resp})"
    data, rresp = await s_master.read(addr)
    assert rresp == RESP_OKAY, f"post-recovery read at {addr:#x} failed (rresp={rresp})"
    assert data[0] == wdata, f"post-recovery readback mismatch at {addr:#x}: {data[0]:#x} != {wdata:#x}"


# --- 23-24. held-reset, free-running far side, wide clock ratio ---------------

async def _reset_asym_held_body(dut, s_ns, m_ns, held) -> None:
    assert held in ("s", "m")
    _kill_active_tasks()
    s_clk_task = cocotb.start_soon(Clock(dut.s_clk, s_ns, units="ns").start())
    m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
    _active_tasks.extend([s_clk_task, m_clk_task])

    dut.s_rst_n.value = 0
    dut.m_rst_n.value = 0
    _quiesce_offer(dut)
    dut.m_awid.value = 0
    dut.m_arid.value = 0
    await Timer(RESET_HOLD_NS, units="ns")

    free = "m" if held == "s" else "s"
    getattr(dut, f"{free}_rst_n").value = 1
    free_clock = dut.m_clk if free == "m" else dut.s_clk

    # Let the free domain's own external input settle a couple of its own
    # cycles before offering -- the point of this test is the STEADY-STATE
    # held window, not the immediate release edge.
    await ClockCycles(free_clock, 2)
    _drive_offer_all_channels(dut)
    await _assert_zero_accept_window(
        dut, free_clock, 20, f"held={held},free={free},{s_ns}/{m_ns}ns"
    )
    _quiesce_offer(dut)

    getattr(dut, f"{held}_rst_n").value = 1
    await _recover_and_verify_once(dut, 0x51000, 0x1357_9BDF)
    dut._log.info(
        f"reset-asym held={held} ({s_ns}/{m_ns} ns) OK: zero acceptance for 20 "
        f"{free}_clk cycles while {held}_rst_n was held low, clean recovery after release"
    )


@cocotb.test()
async def test_reset_asym_m_held_s_free_wide_ratio(dut):
    # m held low, s released and free-running (mirrors the CPU-releases-
    # first scenario that exposed fr_280f3ac18c66 at the SoC level) -- 5x
    # wide ratio (4ns/20ns).
    await with_timeout(_reset_asym_held_body(dut, 4, 20, held="m"), 50, "us")


@cocotb.test()
async def test_reset_asym_s_held_m_free_wide_ratio(dut):
    # Mirror: s held low, m released and free-running -- 5x wide ratio
    # (20ns/4ns).
    await with_timeout(_reset_asym_held_body(dut, 20, 4, held="s"), 50, "us")


# --- 25-26. staggered release-order sweep, coprime ratio -----------------------

async def _reset_asym_staggered_body(dut, s_ns, m_ns, order) -> None:
    assert order in ("s_first", "m_first")
    first, second = ("s", "m") if order == "s_first" else ("m", "s")
    slower_period = max(s_ns, m_ns)
    stagger_windows_ns = [1 * slower_period, 3 * slower_period, 8 * slower_period]

    for idx, stagger_ns in enumerate(stagger_windows_ns):
        _kill_active_tasks()
        s_clk_task = cocotb.start_soon(Clock(dut.s_clk, s_ns, units="ns").start())
        m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
        _active_tasks.extend([s_clk_task, m_clk_task])

        dut.s_rst_n.value = 0
        dut.m_rst_n.value = 0
        _quiesce_offer(dut)
        dut.m_awid.value = 0
        dut.m_arid.value = 0
        await Timer(RESET_HOLD_NS, units="ns")

        getattr(dut, f"{first}_rst_n").value = 1
        first_clock = dut.m_clk if first == "m" else dut.s_clk
        first_period = m_ns if first == "m" else s_ns
        await ClockCycles(first_clock, 2)

        _drive_offer_all_channels(dut)
        window_cycles = max(2, int(stagger_ns / first_period))
        await _assert_zero_accept_window(
            dut, first_clock, window_cycles,
            f"staggered order={order} stagger={stagger_ns}ns ({s_ns}/{m_ns} ns)"
        )
        _quiesce_offer(dut)

        getattr(dut, f"{second}_rst_n").value = 1
        await _recover_and_verify_once(dut, 0x52000 + idx * 0x100, 0x2468_ACE0 + idx)
        dut._log.info(
            f"staggered reset-asym OK: order={order} stagger={stagger_ns}ns "
            f"window_cycles={window_cycles} ({s_ns}/{m_ns} ns), iteration {idx}"
        )


@cocotb.test()
async def test_reset_asym_staggered_s_then_m_coprime(dut):
    # s (CPU domain proxy) releases first, m held -- the exact ordering that
    # exposed fr_280f3ac18c66 at the SoC level -- swept over 3 stagger
    # windows at a coprime 10ns/11ns ratio.
    await with_timeout(_reset_asym_staggered_body(dut, 10, 11, order="s_first"), 100, "us")


@cocotb.test()
async def test_reset_asym_staggered_m_then_s_coprime(dut):
    # Mirror ordering: m releases first, s held.
    await with_timeout(_reset_asym_staggered_body(dut, 10, 11, order="m_first"), 100, "us")
