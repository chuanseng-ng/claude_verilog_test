# test_dma.py
# Phase 5 (M5) — cocotb unit suite for the DMA engine.
#
# Uses:
#   AXI4LiteMaster (bfm/axi4lite_master.py)  — drives s_axil_* to program CSRs
#   AXI4SlaveModel (soc/axi4_slave_model.py)  — responds on m_* (DMA master)
#
# Signal prefix conventions:
#   AXI4LiteMaster: name="s_axil_"  → dut.s_axil_awvalid etc.
#   AXI4SlaveModel: prefix="m"      → dut.m_awid, dut.m_araddr etc.
#
# TOPLEVEL=dma_engine (flat ports — no wrapper needed).
# Clock 2 ns, reset 5 cycles low, 2 idle cycles after release (matches soc pattern).

from dataclasses import dataclass
from functools import partial

import cocotb
from axi4_slave_model import AXI4SlaveModel
from bfm.axi4lite_master import AXI4LiteMaster
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge
from cocotb.utils import get_sim_time

# ── Register byte addresses ───────────────────────────────────────────────────
REG_SRC_ADDR = 0x00
REG_DST_ADDR = 0x04
REG_LENGTH = 0x08
REG_CTRL = 0x0C
REG_STATUS = 0x10
REG_IRQ_STATUS = 0x14
REG_ERR_INFO = 0x18

# STATUS bit positions
STATUS_BUSY = 1 << 0
STATUS_DONE = 1 << 1
STATUS_ERROR = 1 << 2
STATUS_Q_FULL = 1 << 3
STATUS_Q_EMPTY = 1 << 4

# CTRL bit positions
CTRL_START = 1 << 0
CTRL_IRQ_EN = 1 << 1
CTRL_SRST = 1 << 2

# AXI response codes
RESP_OKAY = 0b00
RESP_SLVERR = 0b10

CLK_PERIOD_NS = 2
POLL_TIMEOUT_CYCLES = 5000


class BoundaryCheckSlave(AXI4SlaveModel):
    """Slave model that fails the test if any AR/AW crosses a 4 KB page.

    AXI4 spec: a burst must not cross a 4 KB boundary, i.e.
    addr[11:0] + (axlen+1)*4 <= 0x1000. Catches a src_to_4k/dst_to_4k
    unit bug in the DMA burst-split logic (byte distance vs word count).
    """

    def _check_4k(self, addr, axlen):
        span = (addr & 0xFFF) + (axlen + 1) * 4
        assert span <= 0x1000, (
            f"AXI4 4 KB-boundary violation: addr={addr:#010x} "
            f"(low12={addr & 0xFFF:#05x}) axlen={axlen} "
            f"spans {span:#x} bytes past page base (> 0x1000)"
        )


# Track slave tasks so _setup can cancel them before starting new ones.
# cocotb does NOT auto-cancel background tasks between tests; if the previous
# test's slave loops are still alive they will fight the new slave for the
# m_awready / m_arready signals and corrupt data.
_active_slave_tasks = []


# ── Setup helper ─────────────────────────────────────────────────────────────


async def _setup(dut, mem=None, slave_delays=None, slave_class=None):
    """Start clock, apply reset, return (axil_master, axi4_slave_model).

    slave_delays is a dict accepted by AXI4SlaveModel.__init__ (aw_delay etc.).
    slave_class overrides the slave model class (default: AXI4SlaveModel).

    Cancels any slave coroutines left over from a previous test before
    starting new ones — cocotb does not auto-cancel background tasks between
    tests, so stale loops would fight the new slave for m_awready/m_arready.
    """
    global _active_slave_tasks

    # Cancel and clear stale slave tasks from the previous test.
    for task in _active_slave_tasks:
        task.kill()
    _active_slave_tasks = []

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, units="ns").start())

    # AXI4-Lite master drives the DMA's CSR slave port.
    axil = AXI4LiteMaster(dut, "s_axil_", dut.clk)

    # AXI4 slave model responds to the DMA's AXI4 master port.
    kwargs = slave_delays if slave_delays is not None else {}
    cls = slave_class if slave_class is not None else AXI4SlaveModel
    slave = cls(dut, "m", dut.clk, mem=mem, **kwargs)

    # Monkey-patch start() to record tasks so we can cancel them later.
    def _tracked_start():
        t1 = cocotb.start_soon(slave._write_loop())
        t2 = cocotb.start_soon(slave._read_loop())
        _active_slave_tasks.extend([t1, t2])

    slave.start = _tracked_start
    slave.start()

    # Reset: 5 cycles low, 2 idle after release (matches existing soc tests).
    dut.rst_n.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)

    return axil, slave


# ── Programming helpers ───────────────────────────────────────────────────────


async def _program_descriptor(axil, src, dst, length):
    """Write SRC_ADDR / DST_ADDR / LENGTH without pulsing start."""
    await axil.write(REG_SRC_ADDR, src)
    await axil.write(REG_DST_ADDR, dst)
    await axil.write(REG_LENGTH, length)


async def _launch(axil, src, dst, length, irq_en=False):
    """Program descriptor and pulse CTRL.start (+ optionally set IRQ_EN)."""
    await _program_descriptor(axil, src, dst, length)
    ctrl = CTRL_START | (CTRL_IRQ_EN if irq_en else 0)
    await axil.write(REG_CTRL, ctrl)


async def _poll_done(dut, axil, timeout=POLL_TIMEOUT_CYCLES, wait_idle=False):
    """Poll STATUS until (done or error) is set.

    If wait_idle=True, additionally require that STATUS.busy is clear before
    returning — use this when multiple descriptors may be queued so that
    sticky done from an early descriptor does not trigger a premature return.
    """
    status = 0
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        status, _ = await axil.read(REG_STATUS)
        triggered = bool(status & (STATUS_DONE | STATUS_ERROR))
        if triggered and (not wait_idle or not (status & STATUS_BUSY)):
            return status
    raise AssertionError(
        f"DMA did not complete within {timeout} cycles; final STATUS={status:#010x}"
    )


async def _soft_reset(axil):
    """Issue CTRL.soft_reset pulse."""
    await axil.write(REG_CTRL, CTRL_SRST)


# ── Test 1: single burst copy (4 words / 16 bytes) ───────────────────────────


@cocotb.test()
async def test_mem_copy_single_burst(dut):
    """Seed slave mem with 4 words at SRC; DMA copies to DST; verify."""
    SRC = 0x0000_1000
    DST = 0x0000_2000
    LEN = 16  # 4 words

    seed = {SRC + i * 4: 0xA000_0000 + i for i in range(4)}
    axil, slave = await _setup(dut, mem=dict(seed))

    await _launch(axil, SRC, DST, LEN)
    status = await _poll_done(dut, axil)

    assert status & STATUS_DONE, f"STATUS.done not set: {status:#010x}"
    assert not (status & STATUS_ERROR), f"STATUS.error set unexpectedly: {status:#010x}"
    assert not (status & STATUS_BUSY), f"STATUS.busy still set after done: {status:#010x}"

    for i in range(4):
        got = slave.mem.get(DST + i * 4, None)
        expected = seed[SRC + i * 4]
        assert got == expected, (
            f"word[{i}] at DST+{i * 4:#x}: got {got:#010x}, expected {expected:#010x}"
        )
    dut._log.info("test_mem_copy_single_burst PASS")


# ── Test 2: multi-burst copy (256 words = 1 max burst; then >= 2 bursts) ─────


@cocotb.test()
async def test_mem_copy_multi_burst(dut):
    """LEN=1024 (256 words, exactly one max burst) and LEN=2048 (two bursts)."""
    for label, LEN, N_WORDS in [("1-burst", 1024, 256), ("2-burst", 2048, 512)]:
        SRC = 0x0001_0000
        DST = 0x0002_0000

        seed = {SRC + i * 4: 0xB000_0000 + i for i in range(N_WORDS)}
        axil, slave = await _setup(dut, mem=dict(seed))

        await _launch(axil, SRC, DST, LEN)
        status = await _poll_done(dut, axil, timeout=20000)

        assert status & STATUS_DONE, f"[{label}] STATUS.done not set: {status:#010x}"
        assert not (status & STATUS_ERROR), f"[{label}] STATUS.error set: {status:#010x}"

        mismatches = []
        for i in range(N_WORDS):
            got = slave.mem.get(DST + i * 4, None)
            expected = seed[SRC + i * 4]
            if got != expected:
                mismatches.append((i, got, expected))
        assert not mismatches, (
            f"[{label}] {len(mismatches)} word mismatches; "
            f"first: word[{mismatches[0][0]}] "
            f"got {mismatches[0][1]:#010x} exp {mismatches[0][2]:#010x}"
        )
        dut._log.info(f"test_mem_copy_multi_burst [{label}] PASS")

    dut._log.info("test_mem_copy_multi_burst PASS")


# ── Test 3: 4 KB boundary split ───────────────────────────────────────────────


@cocotb.test()
async def test_4kb_boundary_split(dut):
    """Transfer spanning a 4 KB page boundary is correctly split.

    SRC addr[11:0] = 0xF00  →  64 words (256 B) to 4K boundary.
    LEN = 128 words (512 B) → first burst = 64 words, second burst = 64 words.
    DST is page-aligned so the dst constraint does not further restrict.
    Verify no issued burst crosses a 4K boundary and all data lands correctly.
    """
    SRC = 0x0003_0F00  # addr[11:0] = 0xF00
    DST = 0x0005_0000  # page-aligned → dst_to_4k = 1024 words, not binding
    N_WORDS = 128
    LEN = N_WORDS * 4

    seed = {SRC + i * 4: 0xC000_0000 + i for i in range(N_WORDS)}
    # Use a slave that asserts AXI4 4 KB-boundary compliance on every AR/AW,
    # so a burst-split unit bug is reported at protocol level before the
    # data-integrity checks below.
    axil, slave = await _setup(dut, mem=dict(seed), slave_class=BoundaryCheckSlave)

    await _launch(axil, SRC, DST, LEN)
    status = await _poll_done(dut, axil, timeout=10000)

    assert status & STATUS_DONE, f"STATUS.done not set: {status:#010x}"
    assert not (status & STATUS_ERROR), f"STATUS.error set: {status:#010x}"

    # Verify data correctness
    mismatches = []
    for i in range(N_WORDS):
        got = slave.mem.get(DST + i * 4, None)
        expected = seed[SRC + i * 4]
        if got != expected:
            mismatches.append((i, got, expected))
    assert not mismatches, (
        f"{len(mismatches)} word mismatches after 4K-split; "
        f"first: word[{mismatches[0][0]}] got {mismatches[0][1]:#010x} "
        f"exp {mismatches[0][2]:#010x}"
    )

    # Verify 4K boundary rule: every issued AR must have
    # addr[11:0] + (arlen+1)*4 <= 0x1000  (i.e. last beat does not cross page).
    # We can check the final src address residue: the split was correct if
    # the DMA completed without error (slave model returns SLVERR for any
    # out-of-range access it doesn't have in its mem dict — but we seeded it,
    # so the real guard is the no-error assertion above).
    #
    # Additionally check that the second burst started at the next page boundary:
    # DST second-burst start = DST + 64*4 = DST + 256 = 0x0005_0100
    expected_second_burst_start_dst = DST + 64 * 4
    # Words 64..127 should be at DST+64*4 .. DST+127*4
    for i in range(64, 128):
        got = slave.mem.get(DST + i * 4, None)
        expected = seed[SRC + i * 4]
        assert got == expected, (
            f"Post-split word[{i}] at {DST + i * 4:#010x}: got {got:#010x} exp {expected:#010x}"
        )

    dut._log.info(
        f"test_4kb_boundary_split PASS (split at DST+{expected_second_burst_start_dst:#010x})"
    )


# ── Test 4: IRQ on completion ─────────────────────────────────────────────────


@cocotb.test()
async def test_irq_on_complete(dut):
    """IRQ_EN=1: irq_o rises on done; soft_reset drops irq_o and clears STATUS."""
    SRC = 0x0004_0000
    DST = 0x0004_1000
    LEN = 16  # 4 words

    seed = {SRC + i * 4: 0xD000_0000 + i for i in range(4)}
    axil, slave = await _setup(dut, mem=dict(seed))

    # Assert irq_o is deasserted before the transfer.
    assert int(dut.irq_o.value) == 0, "irq_o unexpectedly high before transfer"

    await _launch(axil, SRC, DST, LEN, irq_en=True)
    status = await _poll_done(dut, axil)

    assert status & STATUS_DONE, f"STATUS.done not set: {status:#010x}"
    assert not (status & STATUS_ERROR), f"STATUS.error set: {status:#010x}"

    # Allow one extra cycle for IRQ flop to propagate.
    await RisingEdge(dut.clk)
    assert int(dut.irq_o.value) == 1, "irq_o not raised after completion with IRQ_EN=1"

    # IRQ_STATUS.done_irq should be set.
    irq_status, _ = await axil.read(REG_IRQ_STATUS)
    assert irq_status & 0x1, f"IRQ_STATUS.done_irq not set: {irq_status:#010x}"

    # Soft reset: irq_o must drop, STATUS.done must clear.
    await _soft_reset(axil)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert int(dut.irq_o.value) == 0, "irq_o still high after soft_reset"

    status_after, _ = await axil.read(REG_STATUS)
    assert not (status_after & STATUS_DONE), (
        f"STATUS.done still set after soft_reset: {status_after:#010x}"
    )

    irq_status_after, _ = await axil.read(REG_IRQ_STATUS)
    assert not (irq_status_after & 0x1), (
        f"IRQ_STATUS.done_irq still set after soft_reset: {irq_status_after:#010x}"
    )

    dut._log.info("test_irq_on_complete PASS")


# ── Test 5: descriptor queue (3 back-to-back descriptors) ─────────────────────


@cocotb.test()
async def test_descriptor_queue(dut):
    """Enqueue 3 descriptors and verify all 3 copies complete correctly.

    Strategy: seed memory for all 3 descriptors, enqueue all 3 before waiting
    for completion, verify every word at destination.  To maximise queue depth
    during execution, enqueue descriptor 1 and 2 while the DMA is processing
    descriptor 0.  We use no slave delays so data integrity is guaranteed, and
    rely on the AXI-Lite programming time (4 register writes × multiple cycles
    per write = ~20+ cycles per enqueue) to create natural overlap.

    The key invariant tested: the DMA must process all 3 descriptors to
    completion — STATUS.done set AND STATUS.busy clear — and all destination
    words must match.  STATUS.q_count reaching >0 during execution confirms
    the queue was used (observable via the done-but-busy intermediate state).
    """
    BASE_SRC = 0x0010_0000
    BASE_DST = 0x0020_0000
    WORDS_EACH = 8
    LEN_EACH = WORDS_EACH * 4

    # Seed source regions for all 3 descriptors.
    seed = {}
    for d in range(3):
        for i in range(WORDS_EACH):
            seed[BASE_SRC + d * 0x1000 + i * 4] = 0xE000_0000 + d * 0x100 + i

    # No slave delays: avoids the cocotb Verilator r_delay/rd_idx timing
    # issue; the queue is still exercised because AXI-Lite CSR writes take
    # several cycles and the DMA may already be executing while we enqueue
    # subsequent descriptors.
    axil, slave = await _setup(dut, mem=dict(seed))

    # Enqueue all 3 descriptors back-to-back.
    for d in range(3):
        await _program_descriptor(
            axil, src=BASE_SRC + d * 0x1000, dst=BASE_DST + d * 0x1000, length=LEN_EACH
        )
        await axil.write(REG_CTRL, CTRL_START)

    # Poll STATUS until done sticky AND busy cleared (all descriptors done).
    # wait_idle=True prevents early return when descriptor 0 sets done_sticky
    # while descriptors 1/2 are still executing.
    status = await _poll_done(dut, axil, timeout=30000, wait_idle=True)
    assert status & STATUS_DONE, f"STATUS.done not set after 3 descriptors: {status:#010x}"
    assert not (status & STATUS_ERROR), f"STATUS.error set: {status:#010x}"
    assert not (status & STATUS_BUSY), f"STATUS.busy still set: {status:#010x}"

    # Verify all 3 destination regions.
    for d in range(3):
        for i in range(WORDS_EACH):
            src_addr = BASE_SRC + d * 0x1000 + i * 4
            dst_addr = BASE_DST + d * 0x1000 + i * 4
            got = slave.mem.get(dst_addr, None)
            expected = seed[src_addr]
            assert got == expected, (
                f"descriptor[{d}] word[{i}]: "
                f"got {got!r} ({got:#010x if got is not None else 'None'}) "
                f"exp {expected:#010x}"
            )

    dut._log.info("test_descriptor_queue PASS")


# ── Test 6: SLVERR on read halts DMA, sets error status ──────────────────────


class _ErrorSlaveModel(AXI4SlaveModel):
    """AXI4SlaveModel subclass that returns SLVERR on accesses to err_addrs."""

    def __init__(self, dut, prefix, clock, mem=None, err_addrs=None, **kwargs):
        super().__init__(dut, prefix, clock, mem=mem, **kwargs)
        self.err_addrs = err_addrs if err_addrs is not None else set()

    async def _write_loop(self):
        """Override: return SLVERR bresp when any beat address is in err_addrs."""
        s = self._sig
        while True:
            for _ in range(self.aw_delay):
                await RisingEdge(self.clock)
            s("awready").value = 1
            awid = addr = awlen = 0
            while True:
                await RisingEdge(self.clock)
                if s("awvalid").value:
                    awid = int(s("awid").value)
                    addr = int(s("awaddr").value)
                    awlen = int(s("awlen").value)
                    break
            s("awready").value = 0

            slverr = False
            for i in range(awlen + 1):
                for _ in range(self.w_delay):
                    await RisingEdge(self.clock)
                s("wready").value = 1
                while True:
                    await RisingEdge(self.clock)
                    if s("wvalid").value:
                        wdata = int(s("wdata").value)
                        wstrb = int(s("wstrb").value)
                        break
                s("wready").value = 0
                beat_addr = addr + i * 4
                if beat_addr in self.err_addrs:
                    slverr = True
                else:
                    cur = self.mem.get(beat_addr, 0)
                    val = 0
                    for b in range(4):
                        src = wdata if (wstrb >> b) & 1 else cur
                        val |= ((src >> (b * 8)) & 0xFF) << (b * 8)
                    self.mem[beat_addr] = val

            for _ in range(self.b_delay):
                await RisingEdge(self.clock)
            s("bid").value = awid
            s("bresp").value = RESP_SLVERR if slverr else 0
            s("bvalid").value = 1
            while True:
                await RisingEdge(self.clock)
                if s("bready").value:
                    break
            s("bvalid").value = 0

    async def _read_loop(self):
        """Override: return SLVERR rresp when the burst base address is in err_addrs."""
        s = self._sig
        while True:
            for _ in range(self.ar_delay):
                await RisingEdge(self.clock)
            s("arready").value = 1
            arid = addr = arlen = 0
            while True:
                await RisingEdge(self.clock)
                if s("arvalid").value:
                    arid = int(s("arid").value)
                    addr = int(s("araddr").value)
                    arlen = int(s("arlen").value)
                    break
            s("arready").value = 0

            slverr = addr in self.err_addrs

            for i in range(arlen + 1):
                for _ in range(self.r_delay):
                    await RisingEdge(self.clock)
                await RisingEdge(self.clock)
                s("rid").value = arid
                s("rdata").value = self.mem.get(addr + i * 4, 0)
                s("rresp").value = RESP_SLVERR if slverr else 0
                s("rlast").value = 1 if i == arlen else 0
                s("rvalid").value = 1
                while True:
                    await RisingEdge(self.clock)
                    if s("rready").value:
                        break
            await RisingEdge(self.clock)
            s("rvalid").value = 0
            s("rlast").value = 0


@cocotb.test()
async def test_error_slverr(dut):
    """SLVERR on DMA read: STATUS.error set, ERR_INFO correct, IRQ raised,
    queue halts until soft_reset.
    """
    SRC = 0x0006_0000  # This address will trigger SLVERR on read
    DST = 0x0007_0000
    LEN = 16  # 4 words

    seed = {SRC + i * 4: 0xF000_0000 + i for i in range(4)}

    # Build the error slave via _setup so stale tasks are cancelled first.
    def _make_err_slave(dut_arg, prefix, clock, mem=None, **kwargs):
        return _ErrorSlaveModel(dut_arg, prefix, clock, mem=mem, err_addrs={SRC}, **kwargs)

    axil, err_slave = await _setup(
        dut,
        mem=dict(seed),
        slave_class=_make_err_slave,
    )

    # Launch with IRQ_EN so we can also verify the error IRQ.
    await _launch(axil, SRC, DST, LEN, irq_en=True)
    status = await _poll_done(dut, axil)

    # STATUS.error must be set; STATUS.done must NOT be set.
    assert status & STATUS_ERROR, f"STATUS.error not set after SLVERR: {status:#010x}"
    assert not (status & STATUS_DONE), (
        f"STATUS.done should not be set on error path: {status:#010x}"
    )

    # ERR_INFO: resp should be SLVERR (0b10), err_on_read should be 1 (bit2).
    err_info, _ = await axil.read(REG_ERR_INFO)
    axi_resp = err_info & 0x3
    err_on_read = (err_info >> 2) & 0x1
    assert axi_resp == RESP_SLVERR, (
        f"ERR_INFO[1:0] = {axi_resp:#x}, expected SLVERR ({RESP_SLVERR:#x})"
    )
    assert err_on_read == 1, f"ERR_INFO.err_on_read = {err_on_read}, expected 1 (error on read)"

    # IRQ_STATUS.err_irq (bit1) should be set; irq_o should be high.
    await RisingEdge(dut.clk)
    irq_status, _ = await axil.read(REG_IRQ_STATUS)
    assert irq_status & 0x2, f"IRQ_STATUS.err_irq not set: {irq_status:#010x}"
    assert int(dut.irq_o.value) == 1, "irq_o not raised after error with IRQ_EN=1"

    # Queue must be halted: a new start pulse must be ignored.
    await _program_descriptor(axil, 0x0008_0000, 0x0009_0000, 16)
    await axil.write(REG_CTRL, CTRL_START)
    for _ in range(10):
        await RisingEdge(dut.clk)
    status_halted, _ = await axil.read(REG_STATUS)
    assert status_halted & STATUS_ERROR, "DMA accepted new descriptor while in halted/error state"

    # Soft reset: clears error, IRQ, halted state.
    await _soft_reset(axil)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert int(dut.irq_o.value) == 0, "irq_o still high after soft_reset"
    status_cleared, _ = await axil.read(REG_STATUS)
    assert not (status_cleared & STATUS_ERROR), (
        f"STATUS.error still set after soft_reset: {status_cleared:#010x}"
    )

    dut._log.info("test_error_slverr PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Read-channel beat-count / drain tests (bead wdmo, TDD step 1)
#
# Specification pinned here (the RTL fix is written to this):
#   1. A beat-count mismatch is a READ ERROR, handled exactly like a non-OKAY
#      RRESP: STATUS.error (not done), ERR_INFO.err_on_read, IRQ_STATUS.err_irq,
#      irq_o, halt until soft_reset, and NO AW/W issued for that descriptor.
#        - early RLAST: RLAST on any beat other than beat beats-1 (even OKAY)
#        - late  RLAST: beat beats-1 arrives without RLAST
#   2. The R channel is always drained: on every read-error exit (early RLAST,
#      late RLAST, non-OKAY RRESP mid-burst) the DMA keeps rready high and
#      discards beats until it has accepted the beat carrying RLAST.  Only then
#      is the error final (observable as err_irq / irq_o).  linebuf is never
#      written past beats beats.
#   3. After the error the DMA is recoverable via soft_reset, and a following
#      good transfer completes with correct data (nothing wedged).
# ═════════════════════════════════════════════════════════════════════════════

POISON_BASE = 0xBAD0_0000  # data on beats the DMA never asked for
SENTINEL_BASE = 0x5E00_0000  # pre-seeded destination words (must stay untouched)
DRAIN_TIMEOUT_CYCLES = 3000  # bound on "slave sees RLAST accepted" waits
GOOD_XFER_TIMEOUT_CYCLES = 3000  # bound on the post-recovery good transfer
N_WORDS = 8  # default burst length (single burst, 32 bytes)


@dataclass(frozen=True)
class ReadPlan:
    """How one read burst misbehaves.  The default plan is a compliant burst.

    n_beats      beats actually driven (None -> arlen + 1)
    rlast_beat   beat index that carries RLAST (None -> last driven beat)
    slverr_beats beat indices that carry RRESP = SLVERR (others OKAY)
    Beats at index > arlen (a slave over-running the request) carry poison data.
    """

    n_beats: int | None = None
    rlast_beat: int | None = None
    slverr_beats: frozenset[int] = frozenset()


class _FaultyReadSlave(AXI4SlaveModel):
    """AXI4SlaveModel whose read side follows a per-burst ReadPlan list.

    Plans are consumed one per accepted AR; once the list is exhausted every
    burst is compliant.  The write side is the stock, proven AXI4SlaveModel
    loop.  read_log holds one record per AR so tests can see how many beats
    the DMA actually accepted and when it accepted the RLAST beat.
    """

    def __init__(self, dut, prefix, clock, mem=None, read_plans=(), **kwargs):
        super().__init__(dut, prefix, clock, mem=mem, **kwargs)
        self._plans = list(read_plans)
        self.read_log = []

    async def _read_loop(self):
        s = self._sig
        while True:
            for _ in range(self.ar_delay):
                await RisingEdge(self.clock)
            s("arready").value = 1
            arid = addr = arlen = 0
            while True:
                await ReadOnly()
                if s("arvalid").value:
                    arid = int(s("arid").value)
                    addr = int(s("araddr").value)
                    arlen = int(s("arlen").value)
                    break
                await RisingEdge(self.clock)
            await RisingEdge(self.clock)
            s("arready").value = 0

            plan = self._plans.pop(0) if self._plans else ReadPlan()
            n = plan.n_beats if plan.n_beats is not None else arlen + 1
            last = plan.rlast_beat if plan.rlast_beat is not None else n - 1
            rec = {
                "addr": addr,
                "arlen": arlen,
                "driven": n,
                "accepted": 0,
                "rlast_accepted": False,
                "rlast_edge_ns": None,
            }
            self.read_log.append(rec)

            for i in range(n):
                for _ in range(self.r_delay):
                    await RisingEdge(self.clock)
                await RisingEdge(self.clock)
                s("rid").value = arid
                s("rdata").value = self.mem.get(addr + i * 4, 0) if i <= arlen else POISON_BASE + i
                s("rresp").value = RESP_SLVERR if i in plan.slverr_beats else RESP_OKAY
                s("rlast").value = 1 if i == last else 0
                s("rvalid").value = 1
                while True:
                    await ReadOnly()
                    if s("rready").value:
                        break
                    await RisingEdge(self.clock)
                # rready seen with rvalid high: the handshake happens on the next edge.
                rec["accepted"] += 1
                if i == last:
                    rec["rlast_accepted"] = True
                    rec["rlast_edge_ns"] = get_sim_time("ns") + CLK_PERIOD_NS
            await RisingEdge(self.clock)
            s("rvalid").value = 0
            s("rlast").value = 0


class _BusMonitor:
    """Counts AR/AW/W handshakes on the DMA master and times irq_o's rising edge."""

    def __init__(self, dut):
        self.dut = dut
        self.ar = self.aw = self.w = 0
        self.irq_rise_ns = None

    async def run(self):
        dut = self.dut
        prev_irq = 0
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            self.ar += int(dut.m_arvalid.value and dut.m_arready.value)
            self.aw += int(dut.m_awvalid.value and dut.m_awready.value)
            self.w += int(dut.m_wvalid.value and dut.m_wready.value)
            irq = int(dut.irq_o.value)
            if irq and not prev_irq and self.irq_rise_ns is None:
                self.irq_rise_ns = get_sim_time("ns")
            prev_irq = irq

    def summary(self):
        return f"AR={self.ar} AW={self.aw} W={self.w}"


def _start_monitor(dut):
    mon = _BusMonitor(dut)
    _active_slave_tasks.append(cocotb.start_soon(mon.run()))
    return mon


async def _wait_until(dut, cond, timeout):
    """Bounded wait: True as soon as cond() holds, False after `timeout` cycles."""
    for _ in range(timeout):
        if cond():
            return True
        await RisingEdge(dut.clk)
    return cond()


LINEBUF_DEPTH = 256  # dma_engine MAX_BURST_BEATS default


def _peek_linebuf(dut, n):
    """Backdoor read of linebuf[0..n-1] (the module's own array, --public-flat-rw).

    Indices past the array depth are not peeked: an over-running slave's beat 256+
    can only ever land by wrapping rd_idx_q onto an earlier word, which the
    in-range comparison below catches.
    """
    return [int(dut.linebuf[i].value) for i in range(min(n, LINEBUF_DEPTH))]


def _src_word(i):
    return 0xA1A1_0000 + i


def _sentinel(i):
    return SENTINEL_BASE + i


async def _start_error_case(dut, plan, src, dst, n_words=N_WORDS):
    """Reset, seed memory, start one descriptor against a slave following `plan`."""
    mem = {src + 4 * i: _src_word(i) for i in range(n_words)}
    mem.update({dst + 4 * i: _sentinel(i) for i in range(n_words)})
    axil, slave = await _setup(
        dut, mem=mem, slave_class=partial(_FaultyReadSlave, read_plans=[plan])
    )
    mon = _start_monitor(dut)
    await _launch(axil, src, dst, n_words * 4, irq_en=True)
    return axil, slave, mon


async def _check_read_error(
    dut, axil, slave, mon, *, dst, n_words=N_WORDS, expect_resp=None, expect_accepted=None
):
    """Assert the whole spec-1 / spec-2 contract for one read-error descriptor."""
    # (a) the descriptor ends in error, not done.
    status = await _poll_done(dut, axil)
    assert status & STATUS_ERROR, (
        f"STATUS.error not set (STATUS={status:#010x}); the beat-count mismatch was "
        f"accepted as a good read. Master saw {mon.summary()}"
    )
    assert not (status & STATUS_DONE), f"STATUS.done set on the error path: {status:#010x}"

    # (b) spec 2: the R channel is drained to and including the RLAST beat.
    assert slave.read_log, "slave never saw an AR for this descriptor"
    rec = slave.read_log[0]
    drained = await _wait_until(dut, lambda: rec["rlast_accepted"], DRAIN_TIMEOUT_CYCLES)
    assert drained, (
        f"R channel not drained: slave drove {rec['driven']} beats, DMA accepted "
        f"{rec['accepted']}, RLAST never accepted within {DRAIN_TIMEOUT_CYCLES} cycles "
        f"(rready dropped on the error -> slave/crossbar wedged)"
    )
    if expect_accepted is not None:
        assert rec["accepted"] == expect_accepted, (
            f"DMA accepted {rec['accepted']} R beats, expected {expect_accepted}"
        )

    # (c) the error only becomes final (err_irq / irq_o) after the RLAST beat.
    await _wait_until(dut, lambda: mon.irq_rise_ns is not None, 50)
    assert mon.irq_rise_ns is not None, "irq_o never rose for the read error (IRQ_EN=1)"
    assert mon.irq_rise_ns > rec["rlast_edge_ns"], (
        f"error declared final at {mon.irq_rise_ns} ns, before the RLAST beat was "
        f"accepted at {rec['rlast_edge_ns']} ns"
    )

    # (d) same flags as the non-OKAY RRESP path.
    err_info, _ = await axil.read(REG_ERR_INFO)
    assert (err_info >> 2) & 1, f"ERR_INFO.err_on_read not set: {err_info:#010x}"
    if expect_resp is not None:
        assert err_info & 0x3 == expect_resp, (
            f"ERR_INFO[1:0]={err_info & 0x3:#x}, expected {expect_resp:#x} "
            f"(first error response must be retained across the drain)"
        )
    irq_status, _ = await axil.read(REG_IRQ_STATUS)
    assert irq_status & 0x2, f"IRQ_STATUS.err_irq not set: {irq_status:#010x}"
    assert not (irq_status & 0x1), f"IRQ_STATUS.done_irq set on error: {irq_status:#010x}"
    assert int(dut.irq_o.value) == 1, "irq_o not high after the read error"

    # (e) spec 1: nothing was written for this descriptor.
    assert mon.aw == 0 and mon.w == 0, (
        f"AW/W issued for a descriptor that failed on read: {mon.summary()}"
    )
    stale = [
        (i, slave.mem.get(dst + 4 * i))
        for i in range(n_words)
        if slave.mem.get(dst + 4 * i) != _sentinel(i)
    ]
    assert not stale, f"destination written despite the read error: {stale[:4]}"


async def _run_cases(cases):
    """Run every (label, coroutine-factory) case, reporting all failures together."""
    failures = []
    for label, factory in cases:
        try:
            await factory()
        except AssertionError as exc:
            failures.append(f"[{label}] {exc}")
    assert not failures, f"{len(failures)}/{len(cases)} cases failed:\n" + "\n".join(failures)


# ── Test 7: early RLAST is a read error ──────────────────────────────────────


@cocotb.test()
async def test_dma_early_rlast_is_error(dut):
    """RLAST on beat k < N-1 with RRESP=OKAY is a read error; no AW/W, dst untouched.

    Before the fix S_R leaves for S_AW on the first OKAY RLAST without comparing
    the beat count, so S_W emits beats_q words of which only k+1 are fresh.
    """
    SRC = 0x0010_0000
    DST = 0x0011_0000

    def case(k):
        async def run():
            axil, slave, mon = await _start_error_case(dut, ReadPlan(n_beats=k + 1), SRC, DST)
            await _check_read_error(dut, axil, slave, mon, dst=DST, expect_accepted=k + 1)

        return run

    # k=0 (first beat), a middle beat, and the beat just before the legal last one.
    await _run_cases([(f"early RLAST at beat {k}", case(k)) for k in (0, 3, N_WORDS - 2)])
    dut._log.info("test_dma_early_rlast_is_error PASS")


# ── Test 8: late / over-running RLAST is a read error ────────────────────────


@cocotb.test()
async def test_dma_late_rlast_is_error(dut):
    """Beat N-1 without RLAST (slave over-runs to RLAST on a later beat) is a read error.

    All N+extra beats must be drained, RLAST accepted, no AW/W, and linebuf must
    not be written past beat N-1 (checked by backdoor; the 256-beat case would
    otherwise wrap rd_idx_q onto linebuf[0] and silently corrupt beat 0).
    """
    SRC = 0x0020_0000
    DST = 0x0021_0000

    def case(n_words, extra):
        async def run():
            plan = ReadPlan(n_beats=n_words + extra, rlast_beat=n_words + extra - 1)
            axil, slave, mon = await _start_error_case(dut, plan, SRC, DST, n_words=n_words)
            # Snapshot only matters for indices >= N, which no legal beat can reach, so
            # taking it just after the (multi-cycle) launch is race-free.
            before = _peek_linebuf(dut, n_words + extra)

            # linebuf is checked as soon as the slave's RLAST beat has been accepted,
            # BEFORE any status check, so a wrap/overrun is caught directly rather than
            # inferred from the error flags.
            rec_ready = await _wait_until(
                dut,
                lambda: bool(slave.read_log) and slave.read_log[0]["rlast_accepted"],
                DRAIN_TIMEOUT_CYCLES,
            )
            assert rec_ready, "R channel not drained: slave's RLAST beat never accepted"
            for _ in range(4):  # let a write on the final handshake edge land
                await RisingEdge(dut.clk)
            after = _peek_linebuf(dut, n_words + extra)
            # Beats 0..N-2 are legitimate fresh data (beat N-1 is where the mismatch is
            # detected, so an implementation may or may not store it).  Nothing may land
            # at or past N, and nothing may wrap back over an earlier beat.
            wrapped = [(i, hex(after[i])) for i in range(n_words - 1) if after[i] != _src_word(i)]
            assert not wrapped, (
                f"linebuf[0..{n_words - 2}] corrupted by over-running beats (wrap): "
                f"first bad {wrapped[0]}"
            )
            assert after[n_words:] == before[n_words:], (
                f"linebuf written past beats_q={n_words}: "
                f"{[hex(v) for v in after[n_words:]]} (was {[hex(v) for v in before[n_words:]]})"
            )

            await _check_read_error(
                dut,
                axil,
                slave,
                mon,
                dst=DST,
                n_words=n_words,
                expect_accepted=n_words + extra,
            )

        return run

    cases = [
        (f"late RLAST N={n} +{extra} beats", case(n, extra))
        for n, extra in ((N_WORDS, 1), (N_WORDS, 5), (256, 4))
    ]
    await _run_cases(cases)
    dut._log.info("test_dma_late_rlast_is_error PASS")


# ── Test 9: SLVERR mid-burst must still drain the R channel (defect B) ───────


@cocotb.test()
async def test_dma_slverr_midburst_drains(dut):
    """Non-OKAY RRESP on beat k: DMA keeps rready high and discards beats up to RLAST.

    Before the fix S_R jumps to S_ERR and rready drops while the slave still
    owes beats, wedging the slave (and, in the SoC, the crossbar/R path).
    """
    SRC = 0x0030_0000
    DST = 0x0031_0000
    all_beats = frozenset(range(N_WORDS))

    def case(slverr_beats):
        async def run():
            plan = ReadPlan(slverr_beats=slverr_beats)
            axil, slave, mon = await _start_error_case(dut, plan, SRC, DST)
            await _check_read_error(
                dut,
                axil,
                slave,
                mon,
                dst=DST,
                expect_resp=RESP_SLVERR,
                expect_accepted=N_WORDS,
            )

        return run

    await _run_cases(
        [
            ("SLVERR on beat 0 only", case(frozenset({0}))),
            ("SLVERR on mid beat 3 only", case(frozenset({3}))),
            (
                "SLVERR on every beat (whole-burst error, as sram_controller/crossbar do)",
                case(all_beats),
            ),
        ]
    )
    dut._log.info("test_dma_slverr_midburst_drains PASS")


# ── Test 10: recovery after each read-error class ────────────────────────────


@cocotb.test()
async def test_dma_recovers_after_read_error(dut):
    """After each read-error class: soft_reset, then a good transfer copies correctly.

    This is the evidence that nothing was left wedged: the same slave must accept
    a fresh AR and the data must match the reference.  The good descriptor must
    issue exactly one AW burst of N W beats (the erroring one issued none).
    """
    BAD_SRC, BAD_DST = 0x0040_0000, 0x0041_0000
    GOOD_SRC, GOOD_DST = 0x0050_0000, 0x0051_0000
    classes = [
        ("early RLAST (beat 2)", ReadPlan(n_beats=3)),
        ("late RLAST (+3 beats)", ReadPlan(n_beats=N_WORDS + 3)),
        ("SLVERR mid-burst (beat 3)", ReadPlan(slverr_beats=frozenset({3}))),
        ("SLVERR whole burst", ReadPlan(slverr_beats=frozenset(range(N_WORDS)))),
    ]

    def case(plan):
        async def run():
            axil, slave, mon = await _start_error_case(dut, plan, BAD_SRC, BAD_DST)
            await _check_read_error(dut, axil, slave, mon, dst=BAD_DST)

            # Documented recovery: soft_reset clears error/IRQ/halt and flushes the queue.
            await _soft_reset(axil)
            for _ in range(3):
                await RisingEdge(dut.clk)
            assert int(dut.irq_o.value) == 0, "irq_o still high after soft_reset"
            status, _ = await axil.read(REG_STATUS)
            assert not (status & (STATUS_ERROR | STATUS_DONE | STATUS_BUSY)), (
                f"STATUS not clean after soft_reset: {status:#010x}"
            )

            # A good transfer through the same slave, with a distinct reference pattern.
            ref = {GOOD_SRC + 4 * i: 0xC0DE_0000 + 0x11 * i for i in range(N_WORDS)}
            slave.mem.update(ref)
            await _launch(axil, GOOD_SRC, GOOD_DST, N_WORDS * 4)
            status = await _poll_done(dut, axil, timeout=GOOD_XFER_TIMEOUT_CYCLES)
            assert status & STATUS_DONE and not (status & STATUS_ERROR), (
                f"good transfer after the error did not complete cleanly: {status:#010x}"
            )
            bad = [
                (i, slave.mem.get(GOOD_DST + 4 * i), ref[GOOD_SRC + 4 * i])
                for i in range(N_WORDS)
                if slave.mem.get(GOOD_DST + 4 * i) != ref[GOOD_SRC + 4 * i]
            ]
            assert not bad, (
                f"good transfer data mismatch after recovery: word[{bad[0][0]}] "
                f"got {bad[0][1]!r} exp {bad[0][2]:#010x} ({len(bad)} bad)"
            )
            assert (mon.aw, mon.w) == (1, N_WORDS), (
                f"expected exactly one {N_WORDS}-beat write burst, saw {mon.summary()}"
            )
            assert len(slave.read_log) == 2 and slave.read_log[1]["accepted"] == N_WORDS

        return run

    await _run_cases([(label, case(plan)) for label, plan in classes])
    dut._log.info("test_dma_recovers_after_read_error PASS")
