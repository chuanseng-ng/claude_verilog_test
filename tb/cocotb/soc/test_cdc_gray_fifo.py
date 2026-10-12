"""
test_cdc_gray_fifo.py -- bead claude_verilog_test-3snb cocotb verification of
rtl/soc/cdc/cdc_gray_fifo.sv's DEPTH=2 variant (DEPTH=4 as the control), via the
standalone wrapper tb_cdc_gray_fifo.sv.

Every behavioural test below is registered twice, once per DUT instance:
  *_d2   DEPTH=2   the minimal multi-bit pointer synchroniser (new)
  *_d4   DEPTH=4   control (smallest depth supported before 3snb)

Method
------
All stimulus is driven at the FALLING edge of the owning domain's clock and
sampled 100 ps later, i.e. mid-cycle and well away from the active edge. The DUT
outputs that matter (wr_ready_o, rd_valid_o, rd_data_o) are functions of
registered state and of the domain's own reset only -- never combinationally of
the testbench's own valid/ready -- so a (valid, ready) pair sampled at that point
is exactly the pair the next rising edge sees. That makes the handshake
bookkeeping race-free without relying on RisingEdge/ReadOnly ordering.

Scoreboard: the producer logs every accepted word with the time of the rising edge
that accepts it; the consumer compares every word it takes against that log in
order (no loss, no duplication, no reorder, no phantom word). The occupancy
(accepted minus consumed, replayed in real edge-time order) must stay inside
[0, DEPTH] at all times -- this is what proves the full flag, the thing the
depth-2 variant changes.

Gray-crossing monitors (tb_cdc_gray_fifo.sv) latch a sticky flag if the bus handed
to either pointer synchroniser ever changes by more than one bit per source-clock
edge. Every stream test asserts they stayed clear.

Not covered here, and not coverable in Verilator: metastability and per-bit skew.
The monitor proves the invariant that makes skew harmless, not that skew is
harmless.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer, with_timeout
from cocotb.utils import get_sim_time

SETTLE_PS = 100
WIDTH_MASK = 0xFFFF
SYNC_STAGES = 2


# ---------------------------------------------------------------------------
# Per-instance handle
# ---------------------------------------------------------------------------
class Fifo:
    def __init__(self, dut, tag, depth):
        self.dut = dut
        self.tag = tag
        self.depth = depth

    def _s(self, name):
        return getattr(self.dut, f"{self.tag}_{name}")

    @property
    def wr_data(self):
        return self._s("wr_data_i")

    @property
    def wr_valid(self):
        return self._s("wr_valid_i")

    @property
    def wr_ready(self):
        return self._s("wr_ready_o")

    @property
    def rd_data(self):
        return self._s("rd_data_o")

    @property
    def rd_valid(self):
        return self._s("rd_valid_o")

    @property
    def rd_ready(self):
        return self._s("rd_ready_i")

    def gray_violations(self):
        return (
            int(self._s("wr2rd_gray_viol_o").value),
            int(self._s("rd2wr_gray_viol_o").value),
        )


async def settle():
    await Timer(SETTLE_PS, units="ps")


def idle(f):
    f.wr_valid.value = 0
    f.wr_data.value = 0
    f.rd_ready.value = 0


async def start(dut, f, wr_ns, rd_ns, rd_offset_ns=0, hold_reset=True):
    """Start both clocks, hold both resets, idle the stimulus."""
    dut.wr_rst_n_i.value = 0
    dut.rd_rst_n_i.value = 0
    dut.mon_rst_n_i.value = 0
    for tag in ("d2", "d4"):
        getattr(dut, f"{tag}_wr_valid_i").value = 0
        getattr(dut, f"{tag}_wr_data_i").value = 0
        getattr(dut, f"{tag}_rd_ready_i").value = 0
    cocotb.start_soon(Clock(dut.wr_clk_i, wr_ns, units="ns").start())

    async def _late_rd():
        if rd_offset_ns:
            await Timer(rd_offset_ns, units="ns")
        await Clock(dut.rd_clk_i, rd_ns, units="ns").start()

    cocotb.start_soon(_late_rd())
    # Real-time hold, far longer than SYNC_STAGES+1 periods of the slower clock.
    await Timer(8 * max(wr_ns, rd_ns) + 50, units="ns")
    dut.mon_rst_n_i.value = 1
    if hold_reset:
        return
    await release_wr(dut)
    await release_rd(dut)
    await settle_cycles(dut, 4)


async def release_wr(dut):
    await FallingEdge(dut.wr_clk_i)
    dut.wr_rst_n_i.value = 1


async def release_rd(dut):
    await FallingEdge(dut.rd_clk_i)
    dut.rd_rst_n_i.value = 1


async def settle_cycles(dut, n):
    for _ in range(n):
        await FallingEdge(dut.wr_clk_i)
    for _ in range(n):
        await FallingEdge(dut.rd_clk_i)


async def reset_both(dut, hold_ns):
    """Assert both resets asynchronously (arbitrary phase), release at each domain's own
    falling edge."""
    dut.wr_rst_n_i.value = 0
    dut.rd_rst_n_i.value = 0
    await Timer(hold_ns, units="ns")
    await release_wr(dut)
    await release_rd(dut)
    await settle_cycles(dut, 4)


async def bring_up(dut, f, wr_ns, rd_ns, **kw):
    await start(dut, f, wr_ns, rd_ns, hold_reset=False, **kw)


# ---------------------------------------------------------------------------
# Scoreboard + producer/consumer coroutines
# ---------------------------------------------------------------------------
class Board:
    def __init__(self, f, wr_ns, rd_ns):
        self.f = f
        self.wr_half_ps = int(wr_ns * 1000) // 2
        self.rd_half_ps = int(rd_ns * 1000) // 2
        self.accepted = []  # words accepted by the FIFO, in order
        self.received = []  # words taken from the FIFO, in order
        self.events = []  # (edge_time_ps, +1 write / -1 read)
        self.wr_idle_cycles_full = 0


async def producer(dut, board, words, p_valid, rng):
    """Offer `words` in order (valid held until accepted); return once all are accepted."""
    f = board.f
    queue = list(words)
    idx = 0
    cur = None
    while True:
        await FallingEdge(dut.wr_clk_i)
        if cur is None and idx < len(queue) and rng.random() < p_valid:
            cur = queue[idx]
            idx += 1
        if cur is None:
            f.wr_valid.value = 0
            if idx >= len(queue):
                return
        else:
            f.wr_valid.value = 1
            f.wr_data.value = cur
        await settle()
        if cur is not None and int(f.wr_ready.value) == 1:
            board.accepted.append(cur)
            board.events.append((get_sim_time("ps") - SETTLE_PS + board.wr_half_ps, +1))
            cur = None


async def consumer(dut, board, p_ready, rng):
    f = board.f
    while True:
        await FallingEdge(dut.rd_clk_i)
        rdy = 1 if rng.random() < p_ready else 0
        f.rd_ready.value = rdy
        await settle()
        if rdy and int(f.rd_valid.value) == 1:
            word = int(f.rd_data.value)
            idx = len(board.received)
            assert idx < len(board.accepted), (
                f"{f.tag}: read #{idx} (0x{word:04x}) with only {len(board.accepted)} words "
                "accepted -- phantom word"
            )
            assert word == board.accepted[idx], (
                f"{f.tag}: word #{idx} 0x{word:04x} != written 0x{board.accepted[idx]:04x} "
                "(loss, duplication or reorder)"
            )
            board.received.append(word)
            board.events.append((get_sim_time("ps") - SETTLE_PS + board.rd_half_ps, -1))


def check_occupancy(board):
    occ = 0
    peak = 0
    for t, kind in sorted(board.events, key=lambda e: (e[0], e[1])):
        occ += kind
        peak = max(peak, occ)
        assert occ >= 0, f"{board.f.tag}: occupancy went negative at {t} ps (read of an empty FIFO)"
        assert occ <= board.f.depth, (
            f"{board.f.tag}: occupancy {occ} > DEPTH {board.f.depth} at {t} ps (overflow)"
        )
    return peak


def assert_no_gray_violation(f):
    w2r, r2w = f.gray_violations()
    assert (w2r, r2w) == (0, 0), (
        f"{f.tag}: pointer crossing changed by more than one bit per edge "
        f"(wr->rd {w2r}, rd->wr {r2w})"
    )


async def stream(dut, f, wr_ns, rd_ns, p_valid, p_ready, n, seed, rd_offset_ns=0):
    await bring_up(dut, f, wr_ns, rd_ns, rd_offset_ns=rd_offset_ns)
    rng = random.Random(seed)
    words = [(0x1000 + i * 7 + rng.randrange(0, 5)) & WIDTH_MASK for i in range(n)]
    board = Board(f, wr_ns, rd_ns)
    ptask = cocotb.start_soon(producer(dut, board, words, p_valid, rng))
    ctask = cocotb.start_soon(consumer(dut, board, p_ready, rng))
    slow = max(wr_ns, rd_ns)
    # liveness: generous per-word budget, scaled by the slower clock
    budget_ns = int(n * (60 + 12 / max(min(p_valid, p_ready), 0.05)) * slow) + 2000
    waited = 0
    step = 50 * slow
    while len(board.received) < n:
        await Timer(step, units="ns")
        waited += step
        assert waited < budget_ns, (
            f"{f.tag}: only {len(board.received)}/{n} words after {waited} ns -- "
            "stalled (deadlock or livelock)"
        )
    # quiet period: nothing extra may appear (no duplicate / phantom word)
    await Timer(30 * slow, units="ns")
    ptask.kill()
    ctask.kill()
    assert board.accepted == words, f"{f.tag}: accepted log != source"
    assert board.received == words, f"{f.tag}: received != written"
    peak = check_occupancy(board)
    assert_no_gray_violation(f)
    return peak


# ---------------------------------------------------------------------------
# Behavioural tests (registered per depth below)
# ---------------------------------------------------------------------------
async def run_reset_state(dut, f):
    await start(dut, f, 7, 3)
    for _ in range(6):
        await FallingEdge(dut.wr_clk_i)
        await settle()
        assert int(f.wr_ready.value) == 0, f"{f.tag}: wr_ready_o high while wr domain in reset"
        assert int(f.rd_valid.value) == 0, f"{f.tag}: rd_valid_o high while rd domain in reset"
    await release_wr(dut)
    await release_rd(dut)
    await settle_cycles(dut, 4)
    await settle()
    assert int(f.wr_ready.value) == 1, f"{f.tag}: not ready after reset release"
    assert int(f.rd_valid.value) == 0, f"{f.tag}: not empty after reset release"


async def run_stream_7_3_full(dut, f):
    await stream(dut, f, 7, 3, 1.0, 1.0, 200, seed=11)


async def run_stream_7_3_random(dut, f):
    await stream(dut, f, 7, 3, 0.5, 0.5, 200, seed=12)


async def run_stream_3_7_full(dut, f):
    await stream(dut, f, 3, 7, 1.0, 1.0, 200, seed=13)


async def run_stream_3_7_random(dut, f):
    await stream(dut, f, 3, 7, 0.5, 0.5, 200, seed=14)


async def run_stream_1_1_full(dut, f):
    await stream(dut, f, 10, 10, 1.0, 1.0, 200, seed=15)


async def run_stream_1_1_random(dut, f):
    await stream(dut, f, 10, 10, 0.3, 0.9, 200, seed=16)


async def run_stream_1_1_skewed_phase(dut, f):
    await stream(dut, f, 10, 10, 0.6, 0.6, 200, seed=17, rd_offset_ns=3)


async def run_stream_very_slow_reader(dut, f):
    peak = await stream(dut, f, 5, 97, 1.0, 1.0, 80, seed=18)
    assert peak == f.depth, f"{f.tag}: slow reader never filled the FIFO (peak {peak})"


async def run_stream_very_slow_writer(dut, f):
    await stream(dut, f, 97, 5, 1.0, 1.0, 80, seed=19)


async def _push(dut, f, words, limit_cycles):
    """Offer `words` (valid held until accepted) for up to `limit_cycles` wr cycles. Returns
    the words accepted."""
    acc = []
    i = 0
    for _ in range(limit_cycles):
        await FallingEdge(dut.wr_clk_i)
        if i < len(words):
            f.wr_valid.value = 1
            f.wr_data.value = words[i]
        else:
            f.wr_valid.value = 0
        await settle()
        if i < len(words) and int(f.wr_ready.value) == 1:
            acc.append(words[i])
            i += 1
    await FallingEdge(dut.wr_clk_i)
    f.wr_valid.value = 0
    return acc


async def _pop(dut, f, limit_cycles, want=None):
    """Take words one per rd cycle while valid, for up to `limit_cycles` rd cycles."""
    got = []
    for _ in range(limit_cycles):
        await FallingEdge(dut.rd_clk_i)
        f.rd_ready.value = 1
        await settle()
        if int(f.rd_valid.value) == 1:
            got.append(int(f.rd_data.value))
            if want is not None and len(got) == want:
                break
    await FallingEdge(dut.rd_clk_i)
    f.rd_ready.value = 0
    return got


async def run_full_boundary(dut, f):
    """Reader stalled: exactly DEPTH words are accepted, ready then stays low and the extra
    offered words are NOT accepted; draining returns exactly those words, in order, and ready
    comes back. Repeated at every pointer phase (2*DEPTH rotations of both pointers) so every
    (wr_ptr, rd_ptr) combination at which the full flag is evaluated is exercised."""
    await bring_up(dut, f, 7, 3)
    d = f.depth
    tag = f.tag
    base = 0x2000
    for rot in range(2 * d):
        # one round trip per iteration advances both pointers (phase step 1+DEPTH mod 2*DEPTH)
        rt = await _push(dut, f, [0x4000 + rot], 8)
        assert rt == [0x4000 + rot], f"{tag}: rot {rot}: round-trip word not accepted"
        got = await _pop(dut, f, 24, want=1)
        assert got == [0x4000 + rot], f"{tag}: rot {rot}: round-trip word lost: {got}"
        words = [base + 16 * rot + k for k in range(d + 3)]
        acc = await _push(dut, f, words, 24)  # reader stalled
        assert acc == words[:d], (
            f"{tag}: rot {rot}: accepted {len(acc)} words with reader stalled, expected {d}"
        )
        await settle()
        assert int(f.wr_ready.value) == 0, f"{tag}: rot {rot}: wr_ready_o high while full"
        got = await _pop(dut, f, 24 + 4 * d)
        assert got == words[:d], f"{tag}: rot {rot}: drained {got}, expected {words[:d]}"
        await settle()
        assert int(f.rd_valid.value) == 0, f"{tag}: rot {rot}: rd_valid_o high after drain"
        # ready must return once the read pointer has crossed back
        for _ in range(12):
            await FallingEdge(dut.wr_clk_i)
        await settle()
        assert int(f.wr_ready.value) == 1, f"{tag}: rot {rot}: wr_ready_o never returned"
    assert_no_gray_violation(f)


async def run_empty_boundary(dut, f):
    """Empty after reset; a written word becomes visible only after the pointer has crossed
    the synchroniser (>= SYNC_STAGES+1 read edges) and within a bounded time; reading the last
    word returns to empty with no phantom."""
    await bring_up(dut, f, 20, 3)
    tag = f.tag
    for _ in range(10):
        await FallingEdge(dut.rd_clk_i)
        await settle()
        assert int(f.rd_valid.value) == 0, f"{tag}: rd_valid_o high on an empty FIFO"
    # one write; count rd edges until visible
    await FallingEdge(dut.wr_clk_i)
    f.wr_valid.value = 1
    f.wr_data.value = 0xBEEF
    await settle()
    assert int(f.wr_ready.value) == 1
    await FallingEdge(dut.wr_clk_i)  # the accepting rising edge has passed
    f.wr_valid.value = 0
    edges = 0
    seen = None
    for _ in range(40):
        await FallingEdge(dut.rd_clk_i)
        edges += 1
        await settle()
        if int(f.rd_valid.value) == 1:
            seen = edges
            break
    assert seen is not None, f"{tag}: written word never became visible"
    # wr edge was < one wr half period before the first of these falling edges; with the rd
    # clock far faster than the wr clock, SYNC_STAGES+1 rd rising edges are the floor.
    assert seen >= SYNC_STAGES, f"{tag}: word visible after only {seen} rd edges -- bypasses the synchroniser?"
    assert int(f.rd_data.value) == 0xBEEF
    got = await _pop(dut, f, 6, want=1)
    assert got == [0xBEEF]
    for _ in range(10):
        await FallingEdge(dut.rd_clk_i)
        await settle()
        assert int(f.rd_valid.value) == 0, f"{tag}: phantom word after the last read"


async def run_ready_low_in_reset(dut, f):
    """wr_ready_o is gated by the write domain's own reset (CLAUDE.md item 12: a reset value
    that advertises availability). Checked (1) asynchronously with no clock edge, (2) for a
    held reset with wr_valid asserted -- nothing may be accepted, (3) first post-release word
    is not dropped."""
    await bring_up(dut, f, 7, 3)
    tag = f.tag
    await FallingEdge(dut.wr_clk_i)
    await settle()
    assert int(f.wr_ready.value) == 1, f"{tag}: precondition: ready"
    # (1) asynchronous assertion mid-cycle: no clock edge before the check
    dut.wr_rst_n_i.value = 0
    await settle()
    assert int(f.wr_ready.value) == 0, f"{tag}: wr_ready_o not gated asynchronously by wr_rst_n_i"
    # (2) hold the reset with a word offered every cycle
    accepted_in_reset = 0
    for _ in range(8):
        await FallingEdge(dut.wr_clk_i)
        f.wr_valid.value = 1
        f.wr_data.value = 0xDEAD
        await settle()
        if int(f.wr_ready.value) == 1:
            accepted_in_reset += 1
    assert accepted_in_reset == 0, f"{tag}: {accepted_in_reset} handshake(s) completed in reset"
    f.wr_valid.value = 0
    # (3) release, then send a short run: every word arrives, in order, none dropped
    await release_wr(dut)
    await release_rd(dut)
    words = [0xA000 + i for i in range(5)]
    board = Board(f, 7, 3)
    rng = random.Random(23)
    ptask = cocotb.start_soon(producer(dut, board, words, 1.0, rng))
    ctask = cocotb.start_soon(consumer(dut, board, 1.0, rng))
    waited = 0
    while len(board.received) < len(words):
        await Timer(500, units="ns")
        waited += 500
        assert waited < 50_000, f"{tag}: post-reset traffic stalled"
    await Timer(300, units="ns")
    ptask.kill()
    ctask.kill()
    assert board.received == words, f"{tag}: post-reset words {board.received} != {words}"
    # read-side mirror: rd_valid_o low while rd domain in reset even if wr side holds data
    dut.rd_rst_n_i.value = 0
    await settle()
    assert int(f.rd_valid.value) == 0
    await release_rd(dut)


async def run_reset_while_full(dut, f, order):
    """Fill to full, then reset both domains from a common root and release them staggered
    (order 'wr_first' or 'rd_first', 6 cycles apart). Afterwards no stale word may survive,
    and a fresh stream must arrive intact -- including words written while the read domain is
    still in reset."""
    await bring_up(dut, f, 7, 3)
    tag = f.tag
    d = f.depth
    acc = await _push(dut, f, [0x7000 + k for k in range(d + 2)], 24)
    assert len(acc) == d, f"{tag}: precondition fill: {len(acc)}"
    # common-root reset, asserted asynchronously
    dut.wr_rst_n_i.value = 0
    dut.rd_rst_n_i.value = 0
    await settle()
    assert int(f.wr_ready.value) == 0 and int(f.rd_valid.value) == 0
    await Timer(8 * 7 + 20, units="ns")
    assert int(f.wr_ready.value) == 0 and int(f.rd_valid.value) == 0

    fresh = [0x9000 + k for k in range(24)]
    board = Board(f, 7, 3)
    rng = random.Random(21)
    if order == "wr_first":
        await release_wr(dut)
        ptask = cocotb.start_soon(producer(dut, board, fresh, 1.0, rng))
        for _ in range(6):
            await FallingEdge(dut.wr_clk_i)
        await release_rd(dut)
        ctask = cocotb.start_soon(consumer(dut, board, 1.0, rng))
    else:
        await release_rd(dut)
        ctask = cocotb.start_soon(consumer(dut, board, 1.0, rng))
        for _ in range(6):
            await FallingEdge(dut.rd_clk_i)
        await release_wr(dut)
        ptask = cocotb.start_soon(producer(dut, board, fresh, 1.0, rng))
    waited = 0
    while len(board.received) < len(fresh):
        await Timer(500, units="ns")
        waited += 500
        assert waited < 200_000, f"{tag}: {order}: only {len(board.received)} fresh words arrived"
    await Timer(300, units="ns")
    ptask.kill()
    ctask.kill()
    assert board.received == fresh, f"{tag}: {order}: stale/lost words: {board.received}"
    check_occupancy(board)
    assert_no_gray_violation(f)


async def run_reset_while_full_wr_first(dut, f):
    await run_reset_while_full(dut, f, "wr_first")


async def run_reset_while_full_rd_first(dut, f):
    await run_reset_while_full(dut, f, "rd_first")


async def run_one_sided_reset(dut, f):
    """A reset of only one domain is a documented hard flush (the pointers disagree afterwards,
    see the cdc_gray_fifo.sv header), so no data contract is asserted across it. What must hold:
    (a) wr_ready_o is low for the whole write-domain reset, (b) rd_valid_o is low for the whole
    read-domain reset, (c) neither side hangs or glitches the other's reset state, and (d) a
    subsequent common reset restores an exactly-correct FIFO."""
    await bring_up(dut, f, 7, 3)
    tag = f.tag
    await _push(dut, f, [0x5000 + k for k in range(f.depth)], 24)
    # (a) write domain only
    dut.wr_rst_n_i.value = 0
    for _ in range(8):
        await FallingEdge(dut.wr_clk_i)
        await settle()
        assert int(f.wr_ready.value) == 0, f"{tag}: wr_ready_o high in one-sided wr reset"
    await release_wr(dut)
    await settle_cycles(dut, 4)
    # (b) read domain only
    await _push(dut, f, [0x5100 + k for k in range(1)], 24)
    dut.rd_rst_n_i.value = 0
    for _ in range(8):
        await FallingEdge(dut.rd_clk_i)
        await settle()
        assert int(f.rd_valid.value) == 0, f"{tag}: rd_valid_o high in one-sided rd reset"
    await release_rd(dut)
    await settle_cycles(dut, 4)
    # (d) recover with a common reset; fresh traffic must be exact
    await reset_both(dut, 8 * 7 + 20)
    for _ in range(6):
        await FallingEdge(dut.rd_clk_i)
        await settle()
        assert int(f.rd_valid.value) == 0, f"{tag}: stale word after the recovery reset"
    words = [0xC000 + k for k in range(3 * f.depth)]
    board = Board(f, 7, 3)
    rng = random.Random(22)
    ptask = cocotb.start_soon(producer(dut, board, words, 1.0, rng))
    ctask = cocotb.start_soon(consumer(dut, board, 1.0, rng))
    waited = 0
    while len(board.received) < len(words):
        await Timer(500, units="ns")
        waited += 500
        assert waited < 100_000, f"{tag}: recovery traffic stalled"
    await Timer(300, units="ns")
    ptask.kill()
    ctask.kill()
    assert board.received == words
    assert_no_gray_violation(f)


# ---------------------------------------------------------------------------
# Registration: one cocotb test per behaviour per depth
# ---------------------------------------------------------------------------
_BEHAVIOURS = [
    run_reset_state,
    run_stream_7_3_full,
    run_stream_7_3_random,
    run_stream_3_7_full,
    run_stream_3_7_random,
    run_stream_1_1_full,
    run_stream_1_1_random,
    run_stream_1_1_skewed_phase,
    run_stream_very_slow_reader,
    run_stream_very_slow_writer,
    run_full_boundary,
    run_empty_boundary,
    run_ready_low_in_reset,
    run_reset_while_full_wr_first,
    run_reset_while_full_rd_first,
    run_one_sided_reset,
]


def _register(fn, tag, depth):
    async def _t(dut):
        await with_timeout(fn(dut, Fifo(dut, tag, depth)), 20, "ms")

    name = f"test_{fn.__name__[len('run_'):]}_{tag}"
    _t.__name__ = name
    _t.__qualname__ = name
    _t.__doc__ = fn.__doc__
    globals()[name] = cocotb.test()(_t)


for _fn in _BEHAVIOURS:
    _register(_fn, "d2", 2)
    _register(_fn, "d4", 4)
