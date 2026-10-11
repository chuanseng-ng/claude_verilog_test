"""
Kernel test: GPU_BLOCK_X launch contract (beads a5ze, 47lf, 6hy6).

The architecture is 8 warps x 8 lanes = 64 threads (CLAUDE.md "8 warps max; 64 total threads",
PHASE4 spec "Warp size: 8 lanes").  Contract, user decision 2026-10-11 (bead 6hy6):

  * BLOCK_X in 1..64 runs ceil(BLOCK_X / 8) warps and EXACTLY BLOCK_X threads take effect:
    the last warp starts with only its valid lanes active (BLOCK_X=9: warp 0 all 8 lanes,
    warp 1 lane 0 only).  An invalid lane never writes a register, shared memory or AXI.
  * BLOCK_X == 0 or BLOCK_X > 64 raises the GPU ERROR condition at launch: no hang, no silent
    truncation, no kernel instruction executes.  It reuses the q6w0 ERROR path: GPU_STATUS
    reads ERROR, the GPU is halted, no done IRQ, and CTRL.reset then a legal launch recovers.

Marker kernel (every warp writes warp_id + 1 to its own word):

  vmov_bid_x r2           r2[l] = warp_id
  vaddi r7, r2, 1         r7[l] = warp_id + 1          (marker, never 0)
  vaddi r3, r0, 2
  vsll  r4, r2, r3        r4[l] = warp_id * 4
  vaddi r9, r4, OUT-7     r9[l] = OUT + warp_id*4 - 7
  vst   r7 -> r9 + 7      mem[OUT + warp_id*4] = warp_id + 1
  vret

Tests:

  test_block_sizes_below_cap       BLOCK_X = 1, 8, 9, 16, 17, 55, 56: ceil(BLOCK_X / 8) warps
  test_block_sizes_57_to_64        EVERY BLOCK_X in 57..64 runs all 8 warps (bead 47lf / GH #254:
                                   the warp COUNT was held in 3 bits and saturated at 7)
  test_lane_results_match_model    a per-LANE kernel; for every legal BLOCK_X the complete set of
                                   stores equals the GpuRefModel union with per-warp lane masks:
                                   no missing store, no extra store (one AXI write per thread,
                                   counted), no wrong value
  test_invalid_lanes_have_no_side_effects   register-file, shared-memory and global-memory write
                                   strobes are checked every cycle against the valid-lane map,
                                   and the surviving register / shared-memory state is read back
                                   by a follow-up 64-thread kernel (partial warp leaves the
                                   previous kernel's values in the invalid lanes)
  test_partial_warp_divergence     a divergent branch counts only valid lanes: BLOCK_X=9 pushes
                                   one divergence entry (warp 0), not two
  test_illegal_block_x_raises_error  BLOCK_X in 0, 65, 72, 128, 1023: STATUS reads ERROR (only)
                                   within a bounded time, nothing is fetched or stored, no IRQ,
                                   then CTRL.reset + a legal launch gives the right results
  test_illegal_block_x_after_done  the same from DONE (launch without reset), and 64 -> OK
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vmov_bid_x, vaddi, vadd, vmul, vsll, vst, vsts, vlds, vblt, vret,
)
from gpu_ref_model import (
    GpuRefModel, launch_is_error, warps_for_block, warp_lane_mask, run_block,
)
from gpu_test_utils import (
    gpu_reset, gpu_launch, gpu_wait_done, axil_read, axil_write, GPU_CTRL, GPU_STATUS,
    GPU_IRQ_CLR, GPU_PERFCNT0, GPU_KERNEL_PC, GPU_GRID_X, GPU_GRID_Y, GPU_GRID_Z, GPU_BLOCK_X,
    GPU_BLOCK_Y, GPU_BLOCK_Z,
)

OUT = 0x300
N_WARPS = 8
N_LANES = 8
CTRL_LAUNCH, CTRL_RESET, CTRL_IRQ_EN = 0x1, 0x2, 0x4
ST_IDLE, ST_DONE, ST_ERROR = 0x1, 0x2, 0x4
PERF_RETIRE, PERF_ISSUE, PERF_DIVPUSH = GPU_PERFCNT0 + 4, GPU_PERFCNT0 + 8, GPU_PERFCNT0 + 12
ERROR_BOUND_POLLS = 60       # STATUS polls (each a few cycles) allowed for the launch error
ILLEGAL_BLOCK_X = (0, 65, 72, 128, 1023)
PARTIAL_BLOCK_X = (1, 7, 9, 15, 17, 63, 64)


def build_kernel() -> dict:
    k = Kernel(base_pc=0)
    k.emit(vmov_bid_x(2))             # r2[l] = warp_id
    k.emit(vaddi(7, 2, 1))            # r7[l] = warp_id + 1  (marker)
    k.emit(vaddi(3, 0, 2))            # r3[l] = 2
    k.emit(vsll(4, 2, 3))             # r4[l] = warp_id * 4
    k.emit(vaddi(9, 4, OUT - 7))      # r9[l] = OUT + warp_id*4 - 7
    k.emit(vst(7, 9, 0))              # mem[r9 + 7] = r7
    k.emit(vret())
    return k.instructions()


def _emit_gid(k: Kernel) -> None:
    """r1 = lane, r2 = warp, r5 = gid = warp*8 + lane, r8 = gid*4."""
    k.emit(vmov_tid_x(1))             # r1[l] = lane
    k.emit(vmov_bid_x(2))             # r2[l] = warp_id
    k.emit(vaddi(3, 0, 3))            # r3[l] = 3
    k.emit(vsll(4, 2, 3))             # r4[l] = warp_id * 8
    k.emit(vadd(5, 4, 1))             # r5[l] = gid
    k.emit(vaddi(8, 0, 2))            # r8[l] = 2
    k.emit(vsll(8, 5, 8))             # r8[l] = gid * 4


def build_lane_kernel() -> dict:
    """Every lane of every warp stores its own value at its own word.

    gid = warp_id*8 + lane;  mem[OUT + gid*4] = gid*gid + 0x11  (distinct for every gid, so
    a store routed to the wrong lane/warp slot or computed with the wrong warp_id shows up).
    """
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))             # r1[l] = lane
    k.emit(vmov_bid_x(2))             # r2[l] = warp_id
    k.emit(vaddi(3, 0, 3))            # r3[l] = 3
    k.emit(vsll(4, 2, 3))             # r4[l] = warp_id * 8
    k.emit(vadd(5, 4, 1))             # r5[l] = gid
    k.emit(vmul(6, 5, 5))             # r6[l] = gid * gid
    k.emit(vaddi(7, 6, 0x11))         # r7[l] = gid*gid + 0x11  (data)
    k.emit(vaddi(8, 0, 2))            # r8[l] = 2
    k.emit(vsll(8, 5, 8))             # r8[l] = gid * 4
    k.emit(vaddi(9, 8, OUT - 7))      # r9[l] = OUT + gid*4 - 7
    k.emit(vst(7, 9, 0))              # mem[r9 + 7] = r7
    k.emit(vret())
    return k.instructions()


# Side-effect kernels (test_invalid_lanes_have_no_side_effects).  Three launches share one DUT
# (registers and shared memory have no reset): A (64 threads) and B (BLOCK_X threads) write
# r7 = gid + tag and shared[gid*4] = r7; C (64 threads) reads both back without writing r7.
TAG_A, TAG_B = 0x100, 0x200
OUT_SHARED, OUT_REG = 0x400, 0x500


def build_effect_kernel(tag: int) -> dict:
    """r7 = gid + tag; shared[gid*4] = r7; global[OUT + gid*4] = r7."""
    k = Kernel(base_pc=0)
    _emit_gid(k)
    k.emit(vaddi(7, 5, tag))          # r7[l] = gid + tag
    k.emit(vaddi(10, 8, -7))          # vsts adds the data-register index (7)
    k.emit(vsts(7, 10, 0))            # shared[gid*4] = r7
    k.emit(vaddi(9, 8, OUT - 7))
    k.emit(vst(7, 9, 0))              # global[OUT + gid*4] = r7
    k.emit(vret())
    return k.instructions()


def build_readback_kernel() -> dict:
    """global[OUT_SHARED + gid*4] = shared[gid*4]; global[OUT_REG + gid*4] = r7 (NOT written)."""
    k = Kernel(base_pc=0)
    _emit_gid(k)
    k.emit(vlds(11, 8, 0))            # r11[l] = shared[gid*4]
    k.emit(vaddi(9, 8, OUT_SHARED - 11))
    k.emit(vst(11, 9, 0))             # global[OUT_SHARED + gid*4] = r11
    k.emit(vaddi(12, 8, OUT_REG - 7))
    k.emit(vst(7, 12, 0))             # global[OUT_REG + gid*4] = r7 left by the previous kernel
    k.emit(vret())
    return k.instructions()


def build_divergence_kernel() -> dict:
    """if (lane < 4) mem[OUT+gid*4] = 100 else mem[OUT+gid*4] = 200.  One divergent branch."""
    k = Kernel(base_pc=0)
    _emit_gid(k)
    k.emit(vaddi(4, 0, 4))            # r4 = 4: threshold, and rs2 index = branch offset[4:0]
    bpc = k.pc()
    target = bpc + 32 + 4
    k.emit(vblt(1, 4, bpc, target))   # lanes 0..3 taken
    for value in (200, 100):          # fall-through (false) path, then the taken path
        k.emit(vaddi(6, 0, value))
        k.emit(vaddi(10, 8, OUT - 6))
        k.emit(vst(6, 10, 0))
        k.emit(vret())
        while k.pc() < target:
            k.emit(vret())
    return k.instructions()


class LaunchMonitor:
    """Falling-edge sampler on gpu_top: AXI handshake counts, plus every register-file,
    shared-memory and global-memory lane strobe checked against the valid-lane map of the warp
    that issues it.  ``violations`` lists any strobe for a lane that is not valid."""

    def __init__(self, dut, block_x: int):
        self.dut = dut
        self.valid = {w: 0 for w in range(N_WARPS)}
        if not launch_is_error(block_x):
            for w in range(warps_for_block(block_x)):
                self.valid[w] = warp_lane_mask(block_x, w)
        self.hs = {"ifar": 0, "ar": 0, "aw": 0, "w": 0}
        self.rf_writes = 0
        self.shmem_writes = 0
        self.mem_requests = 0
        self.violations: list = []
        self.task = None

    def start(self):
        self.task = cocotb.start_soon(self._run())

    def stop(self):
        self.task.kill()

    def counts(self) -> tuple:
        return tuple(self.hs.values())

    async def _run(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            for name, (v, r) in {
                "ifar": ("m_axil_if_arvalid", "m_axil_if_arready"),
                "ar": ("m_axi_arvalid", "m_axi_arready"),
                "aw": ("m_axi_awvalid", "m_axi_awready"),
                "w": ("m_axi_wvalid", "m_axi_wready"),
            }.items():
                if int(getattr(d, v).value) and int(getattr(d, r).value):
                    self.hs[name] += 1
            exec_valid = self.valid[int(d.cu_exec_warp_id.value)]
            if int(d.u_cu.rf_wr_en.value):
                self.rf_writes += 1
                mask = int(d.u_cu.rf_wr_mask.value)
                warp = int(d.u_cu.rf_wr_warp.value)
                if mask & ~self.valid[warp]:
                    self.violations.append(f"register write warp {warp} mask {mask:#04x}")
            sm_we = int(d.sm_we.value)
            if sm_we:
                self.shmem_writes += 1
                if sm_we & ~exec_valid:
                    self.violations.append(f"shared-memory write mask {sm_we:#04x}")
            if int(d.cu_mem_req.value) and not int(d.halt_q.value):
                self.mem_requests += 1
                mask = int(d.cu_mem_lane_mask.value)
                if mask & ~exec_valid:
                    self.violations.append(f"global-memory request mask {mask:#04x}")


async def launch_block(dut, words: dict, block_x: int, mem=None, reset=True,
                       monitor=True, timeout=20_000):
    """Launch one block of ``block_x`` threads of ``words`` and wait for DONE.

    Returns (data_mem, LaunchMonitor).  ``mem`` carries the data memory across launches."""
    if reset:
        await gpu_reset(dut)
    data_mem: dict = {} if mem is None else mem
    mon = LaunchMonitor(dut, block_x)
    if monitor:
        mon.start()
    instr_task = cocotb.start_soon(instr_responder(dut, words))
    data_task = cocotb.start_soon(data_responder(dut, data_mem))
    await gpu_launch(dut, kernel_pc=0, block_x=block_x)
    done = await gpu_wait_done(dut, timeout=timeout)
    for _ in range(40):            # let the last write drain before sampling
        await RisingEdge(dut.clk)
    instr_task.kill()
    data_task.kill()
    if monitor:
        mon.stop()
    assert done, f"GPU did not complete for BLOCK_X={block_x}"
    return data_mem, mon


async def run_block_mem(dut, words: dict, block_x: int) -> dict:
    """Backwards-compatible helper: launch and return the data-memory dict."""
    data_mem, _ = await launch_block(dut, words, block_x, monitor=False)
    return data_mem


async def warps_that_ran(dut, block_x: int) -> list[int]:
    """Launch one block of ``block_x`` threads; return the sorted warp ids that stored a marker."""
    data_mem = await run_block_mem(dut, build_kernel(), block_x)
    ran = []
    for w in range(N_WARPS):
        marker = data_mem.get(OUT + 4 * w)
        if marker is not None:
            assert marker & 0xFFFF_FFFF == w + 1, (
                f"warp {w} stored {marker:#x}, expected marker {w + 1}"
            )
            ran.append(w)
    dut._log.info(f"BLOCK_X={block_x}: warps that ran {ran}")
    return ran


def expected_warps(block_x: int) -> list[int]:
    """Architectural expectation: ceil(block_x / 8) warps (block_x is legal: 1..64)."""
    return list(range(warps_for_block(block_x)))


def masked(d: dict) -> dict:
    return {a: v & 0xFFFF_FFFF for a, v in d.items()}


async def poll_status(dut, want: int, polls: int) -> int:
    """Read GPU_STATUS up to ``polls`` times until ``status & want``; return the last STATUS."""
    st = 0
    for _ in range(polls):
        st = await axil_read(dut, GPU_STATUS)
        if st & want:
            break
    return st


@cocotb.test()
async def test_block_sizes_below_cap(dut):
    """ceil(BLOCK_X/8) warps run, and exactly warps 0..n-1."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for block_x in (1, 8, 9, 16, 17, 55, 56):
        want = expected_warps(block_x)
        got = await warps_that_ran(dut, block_x)
        assert got == want, f"BLOCK_X={block_x}: warps that ran {got}, expected {want}"


@cocotb.test()
async def test_block_sizes_57_to_64(dut):
    """BLOCK_X 57..64 is 8 warps (64 threads is the architectural maximum)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    bad = []
    for block_x in range(57, 65):          # every size, individually -- do not stop at the first
        got = await warps_that_ran(dut, block_x)
        if got != list(range(N_WARPS)):
            bad.append(f"BLOCK_X={block_x}: warps that ran {got}")
    assert not bad, f"expected all of {list(range(N_WARPS))}: " + "; ".join(bad)


@cocotb.test()
async def test_lane_results_match_model(dut):
    """Exactly BLOCK_X threads take effect: stores equal the masked model, one AXI write each."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    words = build_lane_kernel()
    bad = []
    for block_x in (1, 7, 8, 9, 15, 17, 56, 57, 58, 60, 63, 64):
        want = masked(run_block(words, block_x))
        assert len(want) == block_x, "reference must store once per thread"
        got, mon = await launch_block(dut, words, block_x)
        got = masked(got)
        problems = []
        if got != want:
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            wrong = sorted(a for a in set(got) & set(want) if got[a] != want[a])
            problems.append(
                f"{len(got)}/{len(want)} stores; missing lanes {[(a - OUT) // 4 for a in missing]}, "
                f"extra {[(a - OUT) // 4 for a in extra]}, wrong {[(a - OUT) // 4 for a in wrong]}"
            )
        if mon.hs["aw"] != block_x or mon.hs["w"] != block_x:
            problems.append(f"AXI writes AW={mon.hs['aw']} W={mon.hs['w']}, want {block_x}")
        if mon.violations:
            problems.append(f"invalid-lane strobes {mon.violations[:3]}")
        if problems:
            bad.append(f"BLOCK_X={block_x}: " + "; ".join(problems))
        else:
            dut._log.info(f"BLOCK_X={block_x}: {len(got)} lane stores match the model")
    assert not bad, "; ".join(bad)


@cocotb.test()
async def test_invalid_lanes_have_no_side_effects(dut):
    """Invalid lanes of a partial warp write no register, shared word or global word."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    kernel_a, kernel_b = build_effect_kernel(TAG_A), build_effect_kernel(TAG_B)
    readback = build_readback_kernel()

    # Control (non-vacuity): after A (64 threads), C sees A's values in every lane, i.e.
    # registers and shared memory do survive gpu_reset and the readback sees them.
    await launch_block(dut, kernel_a, 64)
    mem_c, mon_c = await launch_block(dut, readback, 64)
    for gid in range(64):
        for base in (OUT_SHARED, OUT_REG):
            assert mem_c.get(base + 4 * gid, 0) & 0xFFFF_FFFF == TAG_A + gid, (
                f"control: readback of gid {gid} at {base:#x} = {mem_c.get(base + 4 * gid)}"
            )
    assert not mon_c.violations

    bad = []
    for block_x in PARTIAL_BLOCK_X:
        await launch_block(dut, kernel_a, 64)
        mem_b, mon_b = await launch_block(dut, kernel_b, block_x)
        mem_c, mon_c = await launch_block(dut, readback, 64)
        problems = []
        if set(mem_b) != {OUT + 4 * g for g in range(block_x)}:
            problems.append(f"global stores {sorted(a - OUT for a in set(mem_b))[:12]}")
        if mon_b.hs["aw"] != block_x:
            problems.append(f"{mon_b.hs['aw']} AXI writes, want {block_x}")
        if mon_b.violations:
            problems.append(f"strobes {mon_b.violations[:3]}")
        if not (mon_b.rf_writes and mon_b.shmem_writes and mon_b.mem_requests):
            problems.append("monitor saw no register/shared/global write: vacuous")
        stale = [
            f"{what}[gid {gid}] = {mem_c.get(base + 4 * gid, 0) & 0xFFFF_FFFF:#x}"
            for what, base in (("shared", OUT_SHARED), ("r7", OUT_REG))
            for gid in range(64)
            if mem_c.get(base + 4 * gid, 0) & 0xFFFF_FFFF
            != (TAG_B if gid < block_x else TAG_A) + gid
        ]
        if stale:
            problems.append(f"{len(stale)} clobbered/missing words, first {stale[:3]}")
        if problems:
            bad.append(f"BLOCK_X={block_x}: " + "; ".join(problems))
        else:
            dut._log.info(f"BLOCK_X={block_x}: invalid lanes left registers/shared/global alone")
    assert not bad, "; ".join(bad)


@cocotb.test()
async def test_partial_warp_divergence(dut):
    """Invalid lanes take no part in a branch: BLOCK_X=9 diverges in warp 0 only."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    words = build_divergence_kernel()
    bad = []
    for block_x in (9, 17, 63):
        pushes = 0
        want: dict = {}
        for w in range(warps_for_block(block_x)):
            model = GpuRefModel(warp_id=w, init_mask=warp_lane_mask(block_x, w))
            want.update(model.run(words))
            pushes += model.div_pushes
        got, mon = await launch_block(dut, words, block_x)
        got_pushes = await axil_read(dut, PERF_DIVPUSH)
        problems = []
        if masked(got) != masked(want):
            problems.append(f"stores differ ({len(got)} vs model {len(want)})")
        if got_pushes != pushes:
            problems.append(f"divergence pushes {got_pushes}, model {pushes}")
        if mon.violations:
            problems.append(f"strobes {mon.violations[:3]}")
        if problems:
            bad.append(f"BLOCK_X={block_x}: " + "; ".join(problems))
    assert not bad, "; ".join(bad)


async def program(dut, block_x: int, ctrl: int = CTRL_LAUNCH | CTRL_IRQ_EN):
    """Write the descriptor and launch with CTRL=ctrl (gpu_launch would clear the irq enable)."""
    for addr, val in ((GPU_KERNEL_PC, 0), (GPU_GRID_X, 1), (GPU_GRID_Y, 1), (GPU_GRID_Z, 1),
                      (GPU_BLOCK_X, block_x), (GPU_BLOCK_Y, 1), (GPU_BLOCK_Z, 1)):
        await axil_write(dut, addr, val)
    await axil_write(dut, GPU_CTRL, ctrl)


async def assert_launch_error(dut, block_x: int, mon: LaunchMonitor, mem: dict, label: str):
    """After a launch with an illegal BLOCK_X: ERROR within a bound, then total silence."""
    st = await poll_status(dut, ST_ERROR, ERROR_BOUND_POLLS)
    assert st == ST_ERROR, (
        f"{label} BLOCK_X={block_x}: STATUS={st:#x} after {ERROR_BOUND_POLLS} polls, "
        f"want ERROR only ({ST_ERROR:#x}) -- no hang, no done, no idle"
    )
    before = mon.counts()
    for _ in range(400):           # ERROR is sticky and quiescent: nothing may start
        await RisingEdge(dut.clk)
    assert mon.counts() == before, f"{label} BLOCK_X={block_x}: bus activity after ERROR"
    assert mon.counts() == (0, 0, 0, 0), f"{label} BLOCK_X={block_x}: traffic {mon.counts()}"
    assert not mem, f"{label} BLOCK_X={block_x}: kernel stored {sorted(mem)[:4]}"
    assert mon.rf_writes == 0, f"{label} BLOCK_X={block_x}: register write while erroring"
    st = await axil_read(dut, GPU_STATUS)
    assert st == ST_ERROR, f"{label} BLOCK_X={block_x}: STATUS decayed to {st:#x}"
    assert await axil_read(dut, GPU_IRQ_CLR) == 0, "an errored launch must not latch a done IRQ"
    assert int(dut.gpu_irq_o.value) == 0, "an errored launch must not raise gpu_irq_o"
    assert await axil_read(dut, GPU_BLOCK_X) == block_x, "BLOCK_X register must be left as written"


async def recover_and_run(dut, mem: dict, block_x: int = 9):
    """CTRL.reset (irq enable kept) -> IDLE within a bound -> a legal launch is correct."""
    await axil_write(dut, GPU_CTRL, CTRL_RESET | CTRL_IRQ_EN)
    st = await poll_status(dut, ST_IDLE, ERROR_BOUND_POLLS)
    assert st == ST_IDLE, f"CTRL.reset did not leave ERROR (STATUS={st:#x})"
    words = build_lane_kernel()
    mem.clear()
    await gpu_launch(dut, kernel_pc=0, block_x=block_x)
    assert await gpu_wait_done(dut, timeout=20_000), "legal launch after reset did not finish"
    assert masked(mem) == masked(run_block(words, block_x)), (
        f"BLOCK_X={block_x} after recovery: stores differ from the model"
    )


async def _illegal_case(dut, block_x: int, words: dict, after_done: bool):
    """One illegal-BLOCK_X case; raises AssertionError on any deviation."""
    await gpu_reset(dut)
    mem: dict = {}
    mon = LaunchMonitor(dut, block_x)
    tasks = [cocotb.start_soon(instr_responder(dut, words)),
             cocotb.start_soon(data_responder(dut, mem))]
    try:
        if after_done:
            await gpu_launch(dut, kernel_pc=0, block_x=9)
            assert await gpu_wait_done(dut, timeout=20_000), "setup kernel did not finish"
            mem.clear()
        nw0 = int(dut.u_sched.n_warps_q.value)     # scheduler state before the illegal launch
        mon.start()
        await program(dut, block_x)
        label = "after-done" if after_done else "fresh"
        await assert_launch_error(dut, block_x, mon, mem, label)
        assert int(dut.cq_desc_valid.value) == 0, "illegal descriptor not consumed (still queued)"
        assert int(dut.u_sched.n_warps_q.value) == nw0, "warp scheduler was launched/loaded"
        assert int(dut.halt_q.value) == 1, "ERROR entered without halting the GPU"
        if not after_done:
            assert await axil_read(dut, PERF_ISSUE) == 0, "a warp was issued"
            assert await axil_read(dut, PERF_RETIRE) == 0, "an instruction retired"
        await recover_and_run(dut, mem, block_x=64 if after_done else 9)
    finally:
        mon.stop() if mon.task else None
        for t in tasks:
            t.kill()


@cocotb.test()
async def test_illegal_block_x_raises_error(dut):
    """BLOCK_X = 0 / 65 / 72 / 128 / 1023: launch ERROR, nothing runs, reset + legal launch ok."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    words = build_lane_kernel()
    bad = []
    for block_x in ILLEGAL_BLOCK_X:
        assert launch_is_error(block_x)
        try:
            await _illegal_case(dut, block_x, words, after_done=False)
        except AssertionError as exc:       # keep going: report every size
            bad.append(f"BLOCK_X={block_x}: {exc}")
    assert not bad, " | ".join(bad)


@cocotb.test()
async def test_illegal_block_x_after_done(dut):
    """A good kernel finishes (DONE); the next launch, with an illegal BLOCK_X and no reset in
    between, raises ERROR instead of re-running the old warps or hanging."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    words = build_lane_kernel()
    bad = []
    for block_x in (0, 65):
        try:
            await _illegal_case(dut, block_x, words, after_done=True)
        except AssertionError as exc:
            bad.append(f"BLOCK_X={block_x}: {exc}")
    assert not bad, " | ".join(bad)
