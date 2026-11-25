"""
GPU instruction-fetch handshake under back-pressure, on gpu_top.

gpu_asm.instr_responder keeps m_axil_if_arready high, so the other GPU suites never see a fetch AR
that waits. This suite serves the fetch port with a slave whose arready and AR-to-R latency vary,
and checks the AXI4-Lite master rules and the fetch bookkeeping of gpu_compute_unit:
  * an AR that is valid and not accepted stays valid with the same address until arready;
  * every recorded fetch (fetch_go) has exactly one AR handshake and exactly one R beat;
  * straight-line kernels fetch consecutive addresses from 0, no gap and no repeat, once per warp;
  * the kernel results equal the reference model (gpu_ref_model.py) in every case.
The slave drives and samples at the falling edge, so every sample sees a settled cycle and a
handshake is the (arvalid, arready) pair of that cycle.
Tests:
  test_fetch_ar_held_through_long_stall        arready low for 200 cycles, then low after every R
  test_fetch_periodic_arready_and_latency      arready high one cycle in N, AR-to-R latency 0, 1, 5
  test_fetch_random_arready_random_kernels     random arready and latency, random kernels
  test_fetch_multi_warp_under_back_pressure    eight warps contend for the one fetch port
  test_fetch_soft_reset_with_ar_pending        GPU_CTRL.reset while the AR waits, then a relaunch
Run: cd sim && make gpu_fetch
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))

import cocotb
import test_random_kernels as rk
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from gpu_asm import (
    N_LANES,
    VBEQ,
    VBGE,
    VBLT,
    VBNE,
    VJMP,
    Kernel,
    data_responder,
    vadd,
    vaddi,
    vld,
    vmov_tid_x,
    vret,
    vsll,
    vst,
)
from gpu_ref_model import GpuRefModel, run_block
from gpu_test_utils import (
    GPU_CTRL,
    GPU_STATUS,
    axil_read,
    axil_write,
    gpu_launch,
    gpu_reset,
    gpu_wait_done,
)
from kernels.kernel_block_warps import build_lane_kernel

BASE_A, BASE_B, BASE_C = 0x100, 0x120, 0x140
CTRL_RESET = 0x2
ST_IDLE, ST_DONE = 0x1, 0x2
BRANCH_OPS = (VBEQ, VBNE, VBLT, VBGE, VJMP)
VRET_WORD = 0x0000003F


def build_vector_add() -> dict:
    """C[l] = A[l] + B[l]: fifteen straight-line instructions with two global loads and a store."""
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))
    k.emit(vaddi(2, 0, 2))
    k.emit(vsll(3, 1, 2))
    k.emit(vaddi(4, 0, BASE_A))
    k.emit(vadd(4, 4, 3))
    k.emit(vld(6, 4, 0))
    k.emit(vaddi(5, 0, BASE_B))
    k.emit(vadd(5, 5, 3))
    k.emit(vld(7, 5, 0))
    k.emit(vadd(8, 6, 7))
    k.emit(vaddi(9, 0, BASE_C - 8))
    k.emit(vadd(9, 9, 3))
    k.emit(vst(8, 9, 0))
    k.emit(vret())
    return k.instructions()


def vector_add_inputs() -> dict:
    mem = {BASE_A + 4 * lane: 10 + lane for lane in range(N_LANES)}
    mem.update({BASE_B + 4 * lane: 100 + 3 * lane for lane in range(N_LANES)})
    return mem


class FetchSlave:
    """AXI4-Lite read slave for m_axil_if_*, one outstanding read.

    ready(cycle) decides arready of a cycle, independent of arvalid. latency() gives the number of
    idle cycles between the AR handshake and the R beat. Violations of the master rules and the
    handshake log are kept for the checks after the kernel."""

    def __init__(self, dut, words: dict, ready, latency) -> None:
        self.dut = dut
        self.words = words
        self.ready = ready
        self.latency = latency
        self.cycle = 0
        self.stall_cycles = 0        # cycles with arvalid high and arready low
        self.handshakes: list = []   # AR addresses, in order
        self.r_beats = 0
        self.fetch_go = 0            # cycles in which the compute unit recorded an issue
        self.violations: list = []
        self._pending = None         # (addr, cycles before the R beat)
        self._held = None            # address of an AR that was valid and not accepted

    async def run(self) -> None:
        dut = self.dut
        cu = dut.u_cu
        dut.m_axil_if_rvalid.value = 0
        dut.m_axil_if_rresp.value = 0
        while True:
            await FallingEdge(dut.clk)
            beat = self._pending is not None and self._pending[1] == 0
            if beat:
                dut.m_axil_if_rvalid.value = 1
                dut.m_axil_if_rdata.value = self.words.get(self._pending[0], VRET_WORD)
                self.r_beats += 1
                self._pending = None
            else:
                dut.m_axil_if_rvalid.value = 0
                if self._pending is not None:
                    self._pending = (self._pending[0], self._pending[1] - 1)
            ready = int(self.ready(self.cycle)) and self._pending is None and not beat
            dut.m_axil_if_arready.value = ready
            await Timer(1, units="ns")
            arvalid = int(dut.m_axil_if_arvalid.value)
            addr = int(dut.m_axil_if_araddr.value)
            self.fetch_go += int(cu.fetch_go.value)
            if self._held is not None:
                if not arvalid:
                    self.violations.append(
                        f"cycle {self.cycle}: ARVALID dropped before ARREADY (was {self._held:#x})"
                    )
                elif addr != self._held:
                    self.violations.append(
                        f"cycle {self.cycle}: ARADDR {addr:#x} changed while waiting, "
                        f"was {self._held:#x}"
                    )
            self._held = None
            if arvalid and ready:
                self.handshakes.append(addr)
                self._pending = (addr, self.latency())
            elif arvalid:
                self.stall_cycles += 1
                self._held = addr
            self.cycle += 1


def check_fetch_log(
    slave: FetchSlave, words: dict, *, expect_stall: bool = True, warps: int = 1
) -> None:
    assert not slave.violations, "AXI4-Lite rule broken: " + "; ".join(slave.violations[:4])
    if expect_stall and slave.stall_cycles == 0:
        raise RuntimeError("harness: no fetch AR ever waited for arready")
    n = len(slave.handshakes)
    assert n == slave.fetch_go, f"{n} AR handshakes for {slave.fetch_go} recorded fetches"
    assert n == slave.r_beats, f"{n} AR handshakes but {slave.r_beats} R beats"
    straight = not any((w & 0x7F) in BRANCH_OPS for w in words.values())
    if straight:
        got = slave.handshakes[: n]
        want = [4 * (i // warps) for i in range(n)]
        assert got == want, f"fetch addresses {[hex(a) for a in got]} are not consecutive from 0"
        assert n >= warps * len(words), f"only {n} of {warps * len(words)} fetches were taken"


def finished(slave: FetchSlave, done: bool, message: str) -> None:
    """A broken AXI4-Lite rule is the cause of a hang, so it is reported first."""
    assert not slave.violations, "AXI4-Lite rule broken: " + "; ".join(slave.violations[:4])
    assert done, message


def stores_of(data_mem: dict, inputs: dict) -> dict:
    return {a: v & 0xFFFF_FFFF for a, v in data_mem.items() if a not in inputs}


async def run_kernel(dut, words, inputs, *, ready, latency, block_x=N_LANES, r_latency=0,
                     timeout=2_000):
    """Reset, serve the fetch port with the slave and the data port with data_responder, launch
    and wait for done. Returns (slave, stores, done)."""
    await gpu_reset(dut)
    data_mem = dict(inputs)
    slave = FetchSlave(dut, words, ready, latency)
    tasks = [cocotb.start_soon(slave.run()),
             cocotb.start_soon(data_responder(dut, data_mem, r_latency=r_latency))]
    try:
        await gpu_launch(dut, kernel_pc=0, block_x=block_x)
        done = await gpu_wait_done(dut, timeout=timeout)
    finally:
        for t in tasks:
            t.kill()
    return slave, stores_of(data_mem, inputs), done


def start_clock(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())


def vector_add_want() -> dict:
    return GpuRefModel(n_lanes=N_LANES, initial_gmem=vector_add_inputs()).run(build_vector_add())


@cocotb.test()
async def test_fetch_ar_held_through_long_stall(dut):
    """The AR of the first fetch waits 200 cycles, and after every R beat arready stays low for
    nine cycles. The AR stays valid with its address, each fetch is taken once, in order, and the
    kernel result equals the model."""
    start_clock(dut)
    words, inputs, want = build_vector_add(), vector_add_inputs(), vector_add_want()

    def ready(cycle: int) -> bool:
        if cycle < 200:
            return False
        return cycle % 10 == 0

    slave, got, done = await run_kernel(dut, words, inputs, ready=ready, latency=lambda: 1)
    finished(slave, done, "the kernel did not finish: a fetch was lost behind a waiting AR")
    check_fetch_log(slave, words)
    assert slave.stall_cycles >= 200
    want = {a: v & 0xFFFF_FFFF for a, v in want.items()}
    assert got == want, "kernel result differs from the model"


@cocotb.test()
async def test_fetch_periodic_arready_and_latency(dut):
    """arready high one cycle in N (N = 2, 3, 5, 8) with AR-to-R latency 0, 1 and 5: every
    combination runs the kernel to the model result with one AR handshake and one R beat per
    recorded fetch."""
    start_clock(dut)
    words, inputs, want = build_vector_add(), vector_add_inputs(), vector_add_want()
    want = {a: v & 0xFFFF_FFFF for a, v in want.items()}
    bad = []
    for period in (2, 3, 5, 8):
        for lat in (0, 1, 5):
            slave, got, done = await run_kernel(
                dut, words, inputs, ready=lambda c, p=period: c % p == 0, latency=lambda n=lat: n
            )
            try:
                finished(slave, done, "kernel did not finish")
                check_fetch_log(slave, words)
                assert got == want, "result differs from the model"
            except AssertionError as err:
                bad.append(f"period {period} latency {lat}: {err}")
    assert not bad, "; ".join(bad)


@cocotb.test()
async def test_fetch_random_arready_random_kernels(dut):
    """Random kernels (straight-line, global load, shared memory, divergence) with a random arready
    density (10 to 90 percent), random AR-to-R latency (0 to 6) and random data-port latency:
    each kernel finishes with the model result and the fetch log is clean."""
    start_clock(dut)
    n_kernels = 12 if os.environ.get("RANDOM_KERNELS_SMOKE") else 40
    base_seed = int(os.environ.get("RANDOM_KERNELS_SEED", "0xC0DE"), 0)
    bad = []
    stalled = 0
    for i in range(n_kernels):
        seed = base_seed + 0x1000 + i
        words, expected, inputs = rk.gen_random_kernel(seed)
        rng = random.Random(seed)
        density = rng.choice((0.1, 0.3, 0.5, 0.9))
        ready_bits = random.Random(seed ^ 0x5A5A)
        slave, got, done = await run_kernel(
            dut, words, inputs,
            ready=lambda c, d=density, r=ready_bits: r.random() < d,
            latency=lambda r=rng: r.randint(0, 6),
            r_latency=rng.randint(0, 3),
        )
        stalled += slave.stall_cycles > 0
        try:
            finished(slave, done, "DEADLOCK")
            check_fetch_log(slave, words, expect_stall=False)
            want = {a: v & 0xFFFF_FFFF for a, v in expected.items()}
            assert got == want, "result differs from the model"
        except AssertionError as err:
            bad.append(f"seed {seed:#x} (density {density}): {err}")
            if len(bad) >= 3:
                break
    assert not bad, f"{len(bad)} kernels failed: " + "; ".join(bad)
    assert stalled >= n_kernels // 2, f"harness: {stalled} of {n_kernels} kernels saw a waiting AR"


@cocotb.test()
async def test_fetch_multi_warp_under_back_pressure(dut):
    """Eight warps share the fetch port. With a random arready and a random latency every warp
    fetches each instruction once and the stores equal the union of the per-warp model runs."""
    start_clock(dut)
    words = build_lane_kernel()
    want = {a: v & 0xFFFF_FFFF for a, v in run_block(words, 64).items()}
    bad = []
    for seed in (1, 2, 3):
        rng = random.Random(seed)
        slave, got, done = await run_kernel(
            dut, words, {}, block_x=64,
            ready=lambda c, r=rng: r.random() < 0.3,
            latency=lambda r=rng: r.randint(0, 4),
        )
        try:
            finished(slave, done, "kernel did not finish")
            check_fetch_log(slave, words, warps=8)
            assert got == want, f"{len(got)}/{len(want)} stores, result differs from the model"
        except AssertionError as err:
            bad.append(f"seed {seed}: {err}")
    assert not bad, "; ".join(bad)


@cocotb.test()
async def test_fetch_soft_reset_with_ar_pending(dut):
    """GPU_CTRL.reset while a fetch AR waits for arready: the AR is not withdrawn, the reset
    completes only after the AR is accepted and its R beat is back, the GPU returns to idle with
    done clear and no further fetch, and the next launch gives the model result."""
    start_clock(dut)
    words, inputs, want = build_vector_add(), vector_add_inputs(), vector_add_want()
    want = {a: v & 0xFFFF_FFFF for a, v in want.items()}
    gate = {"open": False}

    await gpu_reset(dut)
    data_mem = dict(inputs)
    slave = FetchSlave(dut, words, lambda c: gate["open"], lambda: 2)
    tasks = [cocotb.start_soon(slave.run()),
             cocotb.start_soon(data_responder(dut, data_mem))]
    try:
        await gpu_launch(dut, kernel_pc=0, block_x=N_LANES)
        for _ in range(200):
            await FallingEdge(dut.clk)
            if slave.stall_cycles >= 3:
                break
        else:
            raise AssertionError("the fetch AR did not stay valid for three cycles")
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        stalled_at_request = slave.stall_cycles
        for _ in range(30):
            await FallingEdge(dut.clk)
        assert slave.stall_cycles >= stalled_at_request + 28, (
            "the waiting AR was withdrawn by the reset"
        )
        assert not slave.violations, "; ".join(slave.violations[:4])
        assert not slave.handshakes
        gate["open"] = True
        for _ in range(200):
            await FallingEdge(dut.clk)
            if int(await axil_read(dut, GPU_STATUS)) & ST_IDLE:
                break
        status = await axil_read(dut, GPU_STATUS)
        assert status & ST_IDLE and not status & ST_DONE, (
            f"GPU not idle after reset, status {status:#x}"
        )
        for _ in range(40):
            await FallingEdge(dut.clk)
        assert not slave.violations, "; ".join(slave.violations[:4])
        assert len(slave.handshakes) == 1 == slave.r_beats == slave.fetch_go, (
            f"{len(slave.handshakes)} AR, {slave.r_beats} R, {slave.fetch_go} fetches "
            "around the reset"
        )
    finally:
        for t in tasks:
            t.kill()

    slave, got, done = await run_kernel(dut, words, inputs, ready=lambda c: c % 3 == 0,
                                        latency=lambda: 1)
    finished(slave, done, "the kernel after the reset did not finish")
    check_fetch_log(slave, words)
    assert got == want, "kernel result after the reset differs from the model"
