"""
gpu_top control-plane and error paths (bead a5ze, slice 2).

DUT = gpu_top.  What each test pins (spec: PHASE4_GPU_ARCHITECTURE_SPEC.md "Control Interface":
GPU_CTRL = start / reset, GPU_STATUS = idle / done / error; "nested branches NOT supported in
Phase 4 (kernel must avoid)" with a 4-deep per-warp divergence stack, gpu_pkg::DIV_STACK_DEPTH):

  test_register_file_paths      BLOCK_Y / BLOCK_Z / IRQ_STATUS read back; writes to unmapped
                                offsets change nothing and unmapped reads return 0
  test_done_returns_to_idle     a finished kernel (STATUS.done) goes back to idle on a second
                                CTRL.launch, and on CTRL.reset; the IRQ latch clears on reset
  test_four_deep_nesting_ok     four nested divergent branches fit the stack and finish
  test_stack_overflow_sets_error   a fifth nested divergence overflows the stack: STATUS.error,
                                not idle, not done, no interrupt, and it stays there
  test_soft_reset_recovers_from_error   CTRL.reset leaves ERROR for idle and a fresh kernel then
                                runs to the correct result
  test_error_halts_then_reset_then_divergent_kernel_matches_model   (bead q6w0) ERROR halts the
                                errored kernel (no fetch, no memory traffic), CTRL.reset from the
                                halted ERROR returns to IDLE, and a divergent kernel then
                                matches gpu_ref_model on every lane
  test_error_halts_issue_and_memory_traffic   (bead q6w0, halt-on-ERROR) 56 error-injection
                                offsets: after ERROR nothing new starts, the in-flight fetch /
                                VST / shared-memory access completes legally, then the GPU is
                                quiescent in ERROR (STATUS stays error, nothing advances)
  test_error_injected_mid_traffic_halts_and_drains   (bead q6w0, halt-on-ERROR) the error flop is
                                forced at 100 offsets into VST/VSTS/VLDS streams, so a burst /
                                shared-memory access / fetch IS in flight at ERROR: it completes
                                legally, nothing new starts, then quiescent; reset recovers
  test_error_reset_while_inflight_drains   (bead q6w0, halt-on-ERROR) CTRL.reset written the
                                moment ERROR is entered, with a burst still in flight, waits for
                                the drain; relaunch is correct
  test_soft_reset_during_running_is_protocol_clean   (bead q6w0) CTRL.reset while RUNNING aborts
                                the kernel only after the in-flight AXI beat completes: no
                                dropped valid, no orphan R/B beat, nothing issued after IDLE
  test_soft_reset_contract_config_irq_perf   (bead q6w0) reset keeps the config registers, the
                                CTRL.irq_en bit it was written with and the perf counters; it
                                clears the IRQ latch; reset from IDLE and DONE is harmless
  test_hardware_reset_clears_error_and_config   (bead q6w0) rst_n still clears everything
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vmov_bid_x, vaddi, vsll, vst, vsts, vlds, vret, vblt, vbne, vjmp,
    N_LANES,
)
from gpu_ref_model import GpuRefModel
from kernel_divergence_basic import build_kernel as divergence_kernel, BASE_OUT as DIV_OUT
from gpu_test_utils import (
    gpu_reset, gpu_launch, gpu_wait_done, axil_write, axil_read,
    GPU_CTRL, GPU_STATUS, GPU_BLOCK_Y, GPU_BLOCK_Z, GPU_IRQ_CLR, GPU_KERNEL_PC,
    GPU_GRID_X, GPU_GRID_Y, GPU_GRID_Z, GPU_BLOCK_X, GPU_ARG_PTR, GPU_PERFCNT0,
)

OUT = 0x300
CTRL_LAUNCH, CTRL_RESET, CTRL_IRQ_EN = 0x1, 0x2, 0x4
ST_IDLE, ST_DONE, ST_ERROR = 0x1, 0x2, 0x4
ST_ERROR_ENC = 3   # gpu_top state_q encoding of GPS_ERROR (internal; STATUS bit is ST_ERROR)
ST_ERROR_ENC = 3   # gpu_top state_q encoding of GPS_ERROR (internal; STATUS bit is ST_ERROR)
IRQ_STATUS = GPU_IRQ_CLR  # 0x028: read = latch, write bit0 = clear


def store_kernel() -> dict:
    """mem[OUT + tid*4] = tid + 0x40 for the 8 lanes of one warp."""
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))
    k.emit(vaddi(7, 1, 0x40))         # r7 = tid + 0x40 (the stored value, register index 7)
    k.emit(vaddi(2, 0, 2))
    k.emit(vsll(3, 1, 2))             # r3 = tid * 4
    k.emit(vaddi(9, 3, OUT - 7))      # vst adds the data-register index (7) to r9
    k.emit(vst(7, 9, 0))
    k.emit(vret())
    return k.instructions()


def nested_kernel(depth: int) -> dict:
    """``depth`` nested divergent VBLTs: lanes tid < 7, then tid < 6, ... so every level splits."""
    thresholds = (7, 6, 5, 4, 3)
    regs = (4, 8, 12, 16, 20)  # branch offset = 32 + rs2 so that offset[4:0] == rs2 index
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))
    for r, t in zip(regs[:depth], thresholds):
        k.emit(vaddi(r, 0, t))
    for r in regs[:depth]:
        bpc = k.pc()
        target = bpc + 32 + r
        k.emit(vblt(1, r, bpc, target))
        while k.pc() < target:
            k.emit(vret())            # fall-through (not-taken) lanes just retire
    k.emit(vret())
    return k.instructions()


async def start(dut, instrs: dict):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    mem: dict = {}
    tasks = [
        cocotb.start_soon(instr_responder(dut, instrs)),
        cocotb.start_soon(data_responder(dut, mem)),
    ]
    return mem, tasks


async def program(dut, kernel_pc: int, block_x: int = 8):
    """Write the whole kernel descriptor without launching (gpu_launch also writes CTRL=1,
    which would clear the irq-enable bit)."""
    for addr, val in ((GPU_KERNEL_PC, kernel_pc), (GPU_GRID_X, 1), (GPU_GRID_Y, 1),
                      (GPU_GRID_Z, 1), (GPU_BLOCK_X, block_x), (GPU_BLOCK_Y, 1),
                      (GPU_BLOCK_Z, 1)):
        await axil_write(dut, addr, val)


async def wait_status(dut, mask: int, timeout: int = 4000) -> int:
    st = 0
    for _ in range(timeout):
        st = await axil_read(dut, GPU_STATUS)
        if st & mask:
            return st
        await RisingEdge(dut.clk)
    raise AssertionError(f"STATUS never showed {mask:#x}; last STATUS={st:#x}")


def check_store(mem: dict):
    for lane in range(N_LANES):
        got = mem.get(OUT + 4 * lane)
        assert got is not None and got & 0xFFFF_FFFF == 0x40 + lane, (
            f"lane {lane}: mem[{OUT + 4 * lane:#x}]={got}, want {0x40 + lane:#x}"
        )


@cocotb.test()
async def test_register_file_paths(dut):
    """Descriptor registers that no other test reads, and the unmapped-offset behaviour."""
    mem, tasks = await start(dut, store_kernel())
    await axil_write(dut, GPU_BLOCK_Y, 0x155)
    await axil_write(dut, GPU_BLOCK_Z, 0x2AA)
    assert await axil_read(dut, GPU_BLOCK_Y) == 0x155
    assert await axil_read(dut, GPU_BLOCK_Z) == 0x2AA
    # Block registers are 10 bits wide: the upper bits of the write are dropped.
    await axil_write(dut, GPU_BLOCK_Y, 0xFFFF_FFFF)
    assert await axil_read(dut, GPU_BLOCK_Y) == 0x3FF

    # Unmapped offsets: reads give 0, writes disturb nothing mapped.
    before = [await axil_read(dut, a) for a in (GPU_CTRL, GPU_STATUS, GPU_BLOCK_Y, GPU_BLOCK_Z)]
    for addr in (0x02C, 0x070, 0x100, 0xFFC):
        assert await axil_read(dut, addr) == 0, f"unmapped read {addr:#x}"
        await axil_write(dut, addr, 0xFFFF_FFFF)
    after = [await axil_read(dut, a) for a in (GPU_CTRL, GPU_STATUS, GPU_BLOCK_Y, GPU_BLOCK_Z)]
    assert after == before, f"an unmapped write disturbed the register file: {before} -> {after}"
    assert after[1] == ST_IDLE, "a write to an unmapped offset must not start or reset anything"
    for t in tasks:
        t.kill()


@cocotb.test()
async def test_done_returns_to_idle(dut):
    """DONE -> IDLE on a new launch and on CTRL.reset; IRQ latch is set by DONE, cleared by reset."""
    mem, tasks = await start(dut, store_kernel())
    await program(dut, kernel_pc=0)
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_EN)
    st = await wait_status(dut, ST_DONE)
    assert st == ST_DONE, f"STATUS={st:#x}: done must be exclusive of idle / error"
    check_store(mem)
    assert await axil_read(dut, IRQ_STATUS) == 1, "IRQ latch not set by a finished kernel"
    assert dut.gpu_irq_o.value == 1, "irq enabled in CTRL but gpu_irq_o is low after done"

    # Clear-by-write, then run again from DONE with a plain launch (DONE -> IDLE -> RUNNING).
    await axil_write(dut, IRQ_STATUS, 1)
    assert await axil_read(dut, IRQ_STATUS) == 0
    mem.clear()
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH)
    await wait_status(dut, ST_DONE)
    check_store(mem)

    # And DONE -> IDLE on CTRL.reset, which also clears a pending IRQ latch.
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_EN)
    await wait_status(dut, ST_DONE)
    assert await axil_read(dut, IRQ_STATUS) == 1
    await axil_write(dut, GPU_CTRL, CTRL_RESET)
    for _ in range(4):
        await RisingEdge(dut.clk)
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE
    assert await axil_read(dut, IRQ_STATUS) == 0, "CTRL.reset must clear the IRQ latch"
    for t in tasks:
        t.kill()


async def run_nested(dut, depth: int):
    mem, tasks = await start(dut, nested_kernel(depth))
    await gpu_launch(dut, kernel_pc=0, block_x=8)
    return mem, tasks


@cocotb.test()
async def test_four_deep_nesting_ok(dut):
    """The stack holds 4 entries: four nested divergences complete normally."""
    mem, tasks = await run_nested(dut, 4)
    assert await gpu_wait_done(dut, timeout=20_000), "4-deep nested divergence did not finish"
    st = await axil_read(dut, GPU_STATUS)
    assert st == ST_DONE, f"STATUS={st:#x}: no error expected at depth 4"
    for t in tasks:
        t.kill()


@cocotb.test()
async def test_stack_overflow_sets_error(dut):
    """A fifth nested divergence overflows the 4-entry stack: STATUS.error and nothing else."""
    mem, tasks = await run_nested(dut, 5)
    await wait_status(dut, ST_ERROR, timeout=6000)
    for _ in range(200):  # ERROR is sticky: it must not decay into done / idle by itself
        await RisingEdge(dut.clk)
    st = await axil_read(dut, GPU_STATUS)
    assert st == ST_ERROR, f"STATUS={st:#x}, want error only ({ST_ERROR:#x})"
    assert await axil_read(dut, IRQ_STATUS) == 0, "an errored kernel must not latch a done IRQ"
    assert dut.gpu_irq_o.value == 0
    for t in tasks:
        t.kill()


# Bead q6w0 / GH #261: gpu_compute_unit's gpu_error_o used to be cleared only by rst_n, so after
# CTRL.reset the next launch went straight back to ERROR.  Fixed by the synchronous soft-reset
# clear (see MEMORY_MAP.md "GPU_CTRL.RESET").
@cocotb.test()
async def test_soft_reset_recovers_from_error(dut):
    """CTRL.reset leaves ERROR for IDLE, after which a fresh kernel gives the right result."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    prog = nested_kernel(5)
    mem: dict = {}
    data_task = cocotb.start_soon(data_responder(dut, mem))
    instr_task = cocotb.start_soon(instr_responder(dut, prog))
    await gpu_launch(dut, kernel_pc=0, block_x=8)
    await wait_status(dut, ST_ERROR, timeout=6000)

    await axil_write(dut, GPU_CTRL, CTRL_RESET)
    for _ in range(4):
        await RisingEdge(dut.clk)
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE, "CTRL.reset did not leave ERROR"

    # New kernel image at a different base so the stale nested program cannot be what runs.
    instr_task.kill()
    base = 0x1000
    k = Kernel(base_pc=base)
    for pc, word in store_kernel().items():
        k.emit(word)
    instr_task = cocotb.start_soon(instr_responder(dut, k.instructions()))
    await gpu_launch(dut, kernel_pc=base, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    check_store(mem)
    instr_task.kill()
    data_task.kill()


@cocotb.test()
async def test_reset_after_done_then_new_kernel_runs(dut):
    """Control for the error-recovery test: DONE -> CTRL.reset -> a kernel at another PC runs.

    If this passes while the error-recovery test fails, the wedge is specific to leaving ERROR.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    mem: dict = {}
    data_task = cocotb.start_soon(data_responder(dut, mem))
    base = 0x1000
    image = dict(store_kernel())
    k = Kernel(base_pc=base)
    for word in store_kernel().values():
        k.emit(word)
    image.update(k.instructions())
    instr_task = cocotb.start_soon(instr_responder(dut, image))
    await gpu_launch(dut, kernel_pc=0, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    await axil_write(dut, GPU_CTRL, CTRL_RESET)
    for _ in range(4):
        await RisingEdge(dut.clk)
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE
    mem.clear()
    await gpu_launch(dut, kernel_pc=base, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    check_store(mem)
    instr_task.kill()
    data_task.kill()


# ---------------------------------------------------------------------------------------------
# Bead q6w0: CTRL.reset contract.  Helpers first.
# ---------------------------------------------------------------------------------------------
LOOP_OUT = 0x500
SPIN_BASE = 0x2000
STORE_BASE = 0x1000


def loop_store_kernel(out: int = LOOP_OUT) -> dict:
    """Never finishes: store tid+0x40 to out+tid*4 forever (VST; VJMP back)."""
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))
    k.emit(vaddi(2, 0, 2))
    k.emit(vsll(3, 1, 2))
    k.emit(vaddi(9, 3, out - 7))
    k.emit(vaddi(7, 1, 0x40))
    k.emit(vaddi(10, 3, -7))           # shared addr = tid*4 (VSTS adds data-reg index 7)
    top = k.pc()
    k.emit(vst(7, 9, 0))
    k.emit(vsts(7, 10, 0))             # shared-memory traffic too, so a reset can land mid-access
    k.emit(vlds(11, 10, 7))
    k.emit(vjmp(top - k.pc()))
    return k.instructions()


def error_then_spin_kernel(base: int) -> dict:
    """nested_kernel(5) relocated to ``base``, with the first fall-through slot after the 5th
    (overflowing) branch replaced by a self-jump.  The overflow sets gpu_error_o with no push, the
    warp falls through into the self-jump and spins forever: the errored kernel is still
    *running* when the host sees STATUS.error."""
    regs = (4, 8, 12, 16, 20)
    thresholds = (7, 6, 5, 4, 3)
    k = Kernel(base_pc=base)
    k.emit(vmov_tid_x(1))
    for r, t in zip(regs, thresholds):
        k.emit(vaddi(r, 0, t))
    spin_pc = None
    for r in regs:
        bpc = k.pc()
        target = bpc + 32 + r
        k.emit(vblt(1, r, bpc, target))
        if r == regs[-1]:
            spin_pc = k.pc()
        while k.pc() < target:
            k.emit(vret())
    k.emit(vret())
    k.patch(spin_pc, vjmp(0))
    return k.instructions()


class BusMonitor:
    """Passive AXI protocol checker on gpu_top's two master ports, sampled at the falling edge
    (every DUT output and every testbench-driven input is settled there).

    Checks: a valid is never withdrawn (or its payload changed) before its ready; every
    response beat the testbench offers is accepted (an unaccepted R/B/IF-R beat is an orphan: the
    master abandoned its transaction); request and response handshake counts agree once idle."""

    REQ = {  # name: (valid, ready, payload)
        "ifar": ("m_axil_if_arvalid", "m_axil_if_arready", "m_axil_if_araddr"),
        "ar":   ("m_axi_arvalid", "m_axi_arready", "m_axi_araddr"),
        "aw":   ("m_axi_awvalid", "m_axi_awready", "m_axi_awaddr"),
        "w":    ("m_axi_wvalid", "m_axi_wready", "m_axi_wdata"),
    }
    RSP = {  # name: (valid, ready)
        "ifr": ("m_axil_if_rvalid", "m_axil_if_rready"),
        "r":   ("m_axi_rvalid", "m_axi_rready"),
        "b":   ("m_axi_bvalid", "m_axi_bready"),
    }

    def __init__(self, dut):
        self.dut = dut
        self.hs = {n: 0 for n in (*self.REQ, *self.RSP)}
        self.offered = {n: 0 for n in self.RSP}
        self.errors = []
        self.cycle = 0
        self._stuck = {}
        self.clears = 0
        self.task = None
        self.retires = 0        # cycles with a warp retire / warp done / issue / kernel-done pulse
        self.dones = 0
        self.issues = 0
        self.kdones = 0
        self.demand = {"mem": 0, "shmem": 0, "fetch": 0}
        self.err_snap = None    # in-flight state sampled in the first cycle state_q == ERROR
        self.retires = 0        # cycles with a warp retire / warp done / issue / kernel-done pulse
        self.dones = 0
        self.issues = 0
        self.kdones = 0
        self.demand = {"mem": 0, "shmem": 0, "fetch": 0}
        self.err_snap = None    # in-flight state sampled in the first cycle state_q == ERROR

    def start(self):
        self.task = cocotb.start_soon(self._run())

    def stop(self):
        self.task.kill()

    def arm(self):
        """Forget the previous ERROR entry so the next one is sampled."""
        self.err_snap = None

    def activity(self) -> tuple:
        """Everything that must stop once the GPU is quiescent in ERROR."""
        return (self.hs["ifar"], self.hs["ar"], self.hs["aw"], self.hs["w"],
                self.retires, self.dones, self.issues, self.kdones)

    def arm(self):
        """Forget the previous ERROR entry so the next one is sampled."""
        self.err_snap = None

    def activity(self) -> tuple:
        """Everything that must stop once the GPU is quiescent in ERROR."""
        return (self.hs["ifar"], self.hs["ar"], self.hs["aw"], self.hs["w"],
                self.retires, self.dones, self.issues, self.kdones)

    async def _run(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            self.cycle += 1
            for n, (v, r, p) in self.REQ.items():
                valid, ready, pay = (int(getattr(d, x).value) for x in (v, r, p))
                prev = self._stuck.pop(n, None)
                if prev is not None and (not valid or prev != pay):
                    self.errors.append(f"cycle {self.cycle}: {n} valid dropped or changed")
                if valid and ready:
                    self.hs[n] += 1
                elif valid:
                    self._stuck[n] = pay
            self._count_pipeline_activity()
            self._count_pipeline_activity()
            self._check_reset_sequencer()
            for n, (v, r) in self.RSP.items():
                valid, ready = int(getattr(d, v).value), int(getattr(d, r).value)
                if valid:
                    self.offered[n] += 1
                    if ready:
                        self.hs[n] += 1
                    else:
                        self.errors.append(f"cycle {self.cycle}: orphan {n} beat (not accepted)")

    def _count_pipeline_activity(self):
        d = self.dut
        self.retires += int(d.cu_retire.value)
        self.dones += int(d.cu_done.value)
        self.issues += int(d.sched_issue.value)
        self.kdones += int(d.sched_kernel_done.value)
        if int(d.state_q.value) == ST_ERROR_ENC:
            # Requests the (halted) GPU WANTED to make in ERROR: proof that each gate is exercised.
            self.demand["mem"] += int(d.cu_mem_req.value)
            self.demand["shmem"] += int(d.cu_shmem_req.value)
            self.demand["fetch"] += int(d.u_sched.found.value)
        if self.err_snap is None and int(d.state_q.value) == ST_ERROR_ENC:
            self.err_snap = {
                "cycle": self.cycle,
                "mu_busy": int(d.u_mu.busy_q.value),
                "if_outst": int(d.if_outst_q.value) if hasattr(d, "if_outst_q") else 0,
                "sm_stall": int(d.sm_stall.value),
                "halt_q": int(d.halt_q.value),
            }

    def _check_reset_sequencer(self):
        """While a soft reset drains, or the GPU sits in ERROR (halt_q): nothing new may start;
        at the soft_clr pulse: nothing may be outstanding on either master or inside the shared
        memory.  A transaction that began before ERROR was visible runs to completion."""
        d = self.dut
        halted = int(d.halt_q.value) or int(d.state_q.value) == ST_ERROR_ENC
        if halted:
            for what, sig in (("coalescer start", d.u_mu.coal_start),
                              ("shared-memory request", d.sm_active)):
                if int(sig.value):
                    self.errors.append(f"cycle {self.cycle}: new {what} while draining/ERROR")
        if int(d.halt_q.value) and int(d.m_axil_if_arvalid.value):
            self.errors.append(f"cycle {self.cycle}: new fetch AR while draining/ERROR")
        if int(d.soft_clr.value):
            self.clears += 1
            out = (self.hs["ifar"] - self.hs["ifr"], self.hs["ar"] - self.hs["r"],
                   self.hs["aw"] - self.hs["b"], int(d.u_mu.busy_q.value), int(d.sm_stall.value))
            if any(out):
                self.errors.append(f"cycle {self.cycle}: soft_clr with work outstanding {out}")

    def check_clean(self, where: str):
        assert not self.errors, f"{where}: AXI protocol errors: {self.errors[:3]}"
        for n in self.RSP:
            assert self.offered[n] == self.hs[n], f"{where}: {n} beat offered but not accepted"
        assert self.hs["ifar"] == self.hs["ifr"], (
            f"{where}: fetch AR {self.hs['ifar']} != R {self.hs['ifr']}")
        assert self.hs["ar"] == self.hs["r"], f"{where}: AR {self.hs['ar']} != R {self.hs['r']}"
        assert self.hs["aw"] == self.hs["w"] == self.hs["b"], (
            f"{where}: AW/W/B {self.hs['aw']}/{self.hs['w']}/{self.hs['b']}")


async def settle(dut, cycles: int = 20):
    for _ in range(cycles):
        await RisingEdge(dut.clk)


def check_model(mem: dict, words: dict, out_base: int):
    """Every lane's store from the RTL run equals the reference model's."""
    ref = GpuRefModel(n_lanes=N_LANES).run(words)
    assert ref, "reference model produced no stores"
    for addr, want in ref.items():
        got = mem.get(addr)
        assert got is not None and got & 0xFFFF_FFFF == want & 0xFFFF_FFFF, (
            f"mem[{addr:#x}]={got}, model says {want:#x}")
    for lane in range(N_LANES):
        assert out_base + 4 * lane in ref


@cocotb.test()
async def test_error_halts_then_reset_then_divergent_kernel_matches_model(dut):
    """ERROR halts the errored kernel (it used to keep fetching): once the in-flight beats drain
    nothing is fetched or stored.  CTRL.reset from the halted ERROR returns to IDLE, and a
    divergent kernel then matches gpu_ref_model on all lanes (a stale divergence stack / warp
    state / error flag would break it)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    div_words = divergence_kernel()
    image = dict(error_then_spin_kernel(SPIN_BASE))
    image.update(div_words)
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    instr_task = cocotb.start_soon(instr_responder(dut, image, latency=1))
    data_task = cocotb.start_soon(data_responder(dut, mem))

    await gpu_launch(dut, kernel_pc=SPIN_BASE, block_x=8)
    await wait_status(dut, ST_ERROR, timeout=6000)
    await settle(dut, 40)                       # in-flight fetch drains
    halted = bus.activity()
    await settle(dut, 200)
    assert bus.activity() == halted, (
        "the errored kernel kept running in ERROR (fetch / retire / issue still advancing)")
    assert await axil_read(dut, GPU_STATUS) == ST_ERROR, "STATUS must keep reporting ERROR"

    await axil_write(dut, GPU_CTRL, CTRL_RESET)
    await wait_status(dut, ST_IDLE, timeout=200)
    await settle(dut, 20)
    n_fetch, n_ar, n_aw = bus.hs["ifar"], bus.hs["ar"], bus.hs["aw"]
    await settle(dut, 200)
    assert (bus.hs["ifar"], bus.hs["ar"], bus.hs["aw"]) == (n_fetch, n_ar, n_aw), (
        "fetch / memory traffic after CTRL.reset returned the GPU to IDLE")
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE
    bus.check_clean("after reset from ERROR")

    mem.clear()
    await gpu_launch(dut, kernel_pc=0, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    check_model(mem, div_words, DIV_OUT)
    bus.check_clean("after the recovery kernel")
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()


@cocotb.test()
async def test_soft_reset_during_running_is_protocol_clean(dut):
    """CTRL.reset while RUNNING aborts the kernel at a clean AXI boundary.  Sweeping the reset
    over 100 consecutive offsets, with slow responders so it lands in fetch, AR/R, AW/W/B,
    shared-memory and ALU phases: the
    bus stays protocol-clean, the GPU reaches IDLE, nothing is issued afterwards, and a fresh
    kernel then runs correctly."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    image = dict(loop_store_kernel())
    for pc, word in store_kernel().items():
        image[STORE_BASE + pc] = word
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    instr_task = cocotb.start_soon(instr_responder(dut, image, latency=2))
    data_task = cocotb.start_soon(data_responder(dut, mem, ar_latency=1, r_latency=1,
                                                 aw_latency=2, w_latency=1))
    stores_seen = 0
    for delay in range(0, 100):
        await gpu_launch(dut, kernel_pc=0, block_x=8)
        await settle(dut, delay)
        st = await axil_read(dut, GPU_STATUS)
        assert st == 0, f"delay {delay}: loop kernel should be RUNNING, STATUS={st:#x}"
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=400)
        await settle(dut, 20)
        bus.check_clean(f"reset at +{delay}")
        snap, n_ifar = dict(mem), bus.hs["ifar"]
        await settle(dut, 60)
        assert mem == snap and bus.hs["ifar"] == n_ifar, f"delay {delay}: activity after IDLE"
        stores_seen += len(snap)
        mem.clear()
        await gpu_launch(dut, kernel_pc=STORE_BASE, block_x=8)
        await wait_status(dut, ST_DONE, timeout=6000)
        check_store(mem)
        bus.check_clean(f"fresh kernel after reset at +{delay}")
        mem.clear()
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=200)
    assert stores_seen > 0, "the sweep never aborted a kernel that had stored anything"
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()


@cocotb.test()
async def test_soft_reset_contract_config_irq_perf(dut):
    """What CTRL.reset keeps and what it clears (MEMORY_MAP.md GPU_CTRL.RESET)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    image = dict(store_kernel())
    image.update(error_then_spin_kernel(SPIN_BASE))
    mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, image))
    data_task = cocotb.start_soon(data_responder(dut, mem))
    cfg = {GPU_KERNEL_PC: 0, GPU_GRID_X: 3, GPU_GRID_Y: 2, GPU_GRID_Z: 5, GPU_BLOCK_X: 8,
           GPU_BLOCK_Y: 0x11, GPU_BLOCK_Z: 0x22, GPU_ARG_PTR: 0xDEAD_BEE0}

    async def regs():
        return {a: await axil_read(dut, a) for a in cfg}

    # Reset from IDLE is harmless: config kept, still IDLE, no spurious DONE.
    for a, v in cfg.items():
        await axil_write(dut, a, v)
    await axil_write(dut, GPU_CTRL, CTRL_RESET | CTRL_IRQ_EN)
    await settle(dut, 10)
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE
    assert await regs() == cfg, "CTRL.reset from IDLE disturbed a configuration register"
    assert await axil_read(dut, GPU_CTRL) == CTRL_IRQ_EN, "irq_en written with the reset is kept"

    # DONE: IRQ latch set, perf counters count; reset clears the latch, keeps config and counters.
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_EN)
    await wait_status(dut, ST_DONE)
    check_store(mem)
    assert await axil_read(dut, IRQ_STATUS) == 1 and dut.gpu_irq_o.value == 1
    perf = [await axil_read(dut, GPU_PERFCNT0 + 4 * i) for i in range(6)]
    assert perf[0] > 0 and perf[1] > 0, f"perf counters did not count: {perf}"
    await axil_write(dut, GPU_CTRL, CTRL_RESET | CTRL_IRQ_EN)
    await wait_status(dut, ST_IDLE, timeout=200)
    assert await axil_read(dut, IRQ_STATUS) == 0 and dut.gpu_irq_o.value == 0, "IRQ latch survived"
    assert await regs() == cfg
    assert [await axil_read(dut, GPU_PERFCNT0 + 4 * i) for i in range(6)] == perf, (
        "perf counters are kept across CTRL.reset (post-mortem), cleared by the next launch")

    # The retained irq_en still raises the IRQ for the next finished kernel.
    mem.clear()
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_EN)
    await wait_status(dut, ST_DONE)
    check_store(mem)
    assert dut.gpu_irq_o.value == 1
    await axil_write(dut, GPU_CTRL, CTRL_RESET | CTRL_IRQ_EN)
    await wait_status(dut, ST_IDLE, timeout=200)

    # ERROR: no IRQ, reset leaves IRQ low and the GPU launchable.
    await axil_write(dut, GPU_KERNEL_PC, SPIN_BASE)
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_EN)
    await wait_status(dut, ST_ERROR, timeout=6000)
    assert dut.gpu_irq_o.value == 0
    await axil_write(dut, GPU_CTRL, CTRL_RESET | CTRL_IRQ_EN)
    await wait_status(dut, ST_IDLE, timeout=200)
    assert dut.gpu_irq_o.value == 0 and await axil_read(dut, IRQ_STATUS) == 0
    assert await axil_read(dut, GPU_KERNEL_PC) == SPIN_BASE, "kernel address is config: kept"
    mem.clear()
    await axil_write(dut, GPU_KERNEL_PC, 0)
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_EN)
    await wait_status(dut, ST_DONE)
    check_store(mem)
    assert dut.gpu_irq_o.value == 1
    for t in (instr_task, data_task):
        t.kill()


@cocotb.test()
async def test_hardware_reset_clears_error_and_config(dut):
    """rst_n still clears everything, including the sticky compute-unit error and the config."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, nested_kernel(5)))
    data_task = cocotb.start_soon(data_responder(dut, mem))
    await gpu_launch(dut, kernel_pc=0, block_x=8)
    await wait_status(dut, ST_ERROR, timeout=6000)
    assert dut.u_cu.gpu_error_o.value == 1
    instr_task.kill()
    data_task.kill()
    await gpu_reset(dut)
    assert dut.u_cu.gpu_error_o.value == 0, "hardware reset must clear the compute-unit error"
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE
    for a in (GPU_KERNEL_PC, GPU_BLOCK_X, GPU_GRID_X, GPU_CTRL):
        assert await axil_read(dut, a) == 0, f"config {a:#x} survived hardware reset"
    assert await axil_read(dut, GPU_PERFCNT0) == 0
    mem.clear()
    instr_task = cocotb.start_soon(instr_responder(dut, store_kernel()))
    data_task = cocotb.start_soon(data_responder(dut, mem))
    await gpu_launch(dut, kernel_pc=0, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    check_store(mem)
    for t in (instr_task, data_task):
        t.kill()


@cocotb.test()
async def test_start_queued_in_error_does_not_survive_reset(dut):
    """A START written while the GPU is in ERROR is queued but not run (ERROR ignores it).
    CTRL.reset must drop the queued descriptor: the GPU stays IDLE instead of launching on its
    own.  START and RESET in the same write: reset wins, nothing runs."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    image = dict(error_then_spin_kernel(SPIN_BASE))
    image.update(store_kernel())
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    instr_task = cocotb.start_soon(instr_responder(dut, image))
    data_task = cocotb.start_soon(data_responder(dut, mem))
    await gpu_launch(dut, kernel_pc=SPIN_BASE, block_x=8)
    await wait_status(dut, ST_ERROR, timeout=6000)
    await axil_write(dut, GPU_KERNEL_PC, 0)
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH)        # queued behind ERROR
    await axil_write(dut, GPU_CTRL, CTRL_RESET)
    await wait_status(dut, ST_IDLE, timeout=200)
    await settle(dut, 100)
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE, "START queued behind ERROR launched"
    assert not mem, f"a kernel stored after the reset: {mem}"

    # START | RESET in one write, from IDLE: reset wins.
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_RESET)
    await settle(dut, 100)
    assert await axil_read(dut, GPU_STATUS) == ST_IDLE and not mem
    bus.check_clean("START|RESET")
    assert bus.clears >= 2
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()


def loop_shmem_kernel(base: int = 0) -> dict:
    """Never finishes: VSTS / VLDS forever, no global-memory traffic (shared memory is busy for
    a large fraction of the loop, the coalescer never is)."""
    k = Kernel(base_pc=base)
    k.emit(vmov_tid_x(1))
    k.emit(vaddi(2, 0, 2))
    k.emit(vsll(3, 1, 2))
    k.emit(vaddi(7, 1, 0x40))
    k.emit(vaddi(10, 3, -7))
    top = k.pc()
    k.emit(vsts(7, 10, 0))
    k.emit(vlds(11, 10, 7))
    k.emit(vjmp(top - k.pc()))
    return k.instructions()


@cocotb.test()
async def test_soft_reset_during_shared_memory_loop(dut):
    """CTRL.reset while the shared memory is mid-access drains it first (soft_clr never fires
    with sm_stall up, nothing new starts while draining) and the GPU is launchable afterwards."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    image = dict(loop_shmem_kernel())
    for pc, word in store_kernel().items():
        image[STORE_BASE + pc] = word
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    instr_task = cocotb.start_soon(instr_responder(dut, image))
    data_task = cocotb.start_soon(data_responder(dut, mem))
    for delay in range(0, 40):
        await gpu_launch(dut, kernel_pc=0, block_x=8)
        await settle(dut, delay)
        assert await axil_read(dut, GPU_STATUS) == 0, f"delay {delay}: loop kernel not RUNNING"
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=400)
        await settle(dut, 20)
        bus.check_clean(f"shmem loop, reset at +{delay}")
    mem.clear()
    await gpu_launch(dut, kernel_pc=STORE_BASE, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    check_store(mem)
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()


# ---------------------------------------------------------------------------------------------
# Bead q6w0, halt-on-ERROR.  ERROR must stop the GPU issuing instructions and memory requests,
# let in-flight bus beats drain, and then sit quiescent until software writes CTRL.reset.
# ---------------------------------------------------------------------------------------------
STORM_OUT = 0x700
STORM_BASE = 0x4000
# Error-injection cases (kind, block_x, pad, instruction-fetch latency):
#   "after":     one kernel image for every warp; the lanes that fall through the overflowing
#                branch run ``pad`` ALU ops and then store forever (the kernel does not stop by
#                itself after ERROR).  8 store positions x 1/2/4 warps, slow fetch.
#   "bystander": warp 0 runs the 5-deep nest (and errors) while the other warps stream VSTs
#                forever.  With a fast instruction fetch (latency 0 / 1) the instruction behind
#                the erroring branch is already decoded, so a coalescer burst starts in the very
#                cycle the error flag rises and is still in flight when ERROR is entered.
#   "bystander_sm": the same with VSTS / VLDS streams, for the shared memory.
#                ``pad`` ALU ops before the nest slide the error across the bystanders' loop.
CASES = ([("after", bx, pad, 2) for bx in (8, 16, 32) for pad in range(8)]
         + [(kind, bx, pad, 0) for kind in ("bystander", "bystander_sm")
            for bx in (16, 64) for pad in range(8)])


def error_storm_kernel(base: int, pad: int) -> dict:
    """nested_kernel(5) relocated to ``base``.  The 5th (overflowing) branch sets gpu_error_o;
    the lanes that fall through run ``pad`` ALU ops and then loop forever over
    VST / VSTS / VLDS / VST, so an ungated GPU keeps hitting the fetch port, the coalescer and the
    shared memory after ERROR.  ``pad`` moves the first store relative to the error."""
    regs = (4, 8, 12, 16, 20)
    thresholds = (7, 6, 5, 4, 3)
    k = Kernel(base_pc=base)
    k.emit(vmov_tid_x(1))
    k.emit(vaddi(2, 0, 2))
    k.emit(vsll(3, 1, 2))
    k.emit(vaddi(9, 3, STORM_OUT - 7))
    k.emit(vaddi(7, 1, 0x40))
    k.emit(vaddi(10, 3, -7))
    for r, t in zip(regs, thresholds):
        k.emit(vaddi(r, 0, t))
    slot = None
    for r in regs:
        bpc = k.pc()
        target = bpc + 32 + r
        k.emit(vblt(1, r, bpc, target))
        if r == regs[-1]:
            slot = k.pc()
        while k.pc() < target:
            k.emit(vret())
    k.emit(vret())
    for i in range(pad):
        k.patch(slot + 4 * i, vaddi(13, 0, 1))
    head = slot + 4 * pad
    k.patch(head, vst(7, 9, 0))
    k.patch(head + 4, vsts(7, 10, 0))
    k.patch(head + 8, vlds(11, 10, 7))
    k.patch(head + 12, vst(7, 9, 0))
    k.patch(head + 16, vjmp(head - (head + 16)))
    return k.instructions()


def error_bystander_kernel(base: int, pad: int, shared: bool) -> dict:
    """Warp 0 runs the 5-deep nested divergence (the 5th branch overflows: ERROR) after ``pad``
    ALU ops; every other warp takes a non-divergent branch (bid != 0) into an endless loop of
    six VSTs (``shared`` False) or three VSTS / VLDS pairs (``shared`` True)."""
    regs = (4, 8, 12, 16, 20)
    thresholds = (7, 6, 5, 4, 3)
    k = Kernel(base_pc=base)
    k.emit(vmov_bid_x(14))
    k.emit(vmov_tid_x(1))
    k.emit(vaddi(2, 0, 2))
    k.emit(vsll(3, 1, 2))
    k.emit(vaddi(9, 3, STORM_OUT - 7))
    k.emit(vaddi(7, 1, 0x40))
    k.emit(vaddi(10, 3, -7))
    for r, t in zip(regs, thresholds):
        k.emit(vaddi(r, 0, t))
    for _ in range(pad):
        k.emit(vaddi(13, 0, 1))
    bpc = k.pc()
    k.emit(vbne(14, 0, bpc, bpc + 32))      # warps != 0 jump to the store loop
    jmp_pc = k.emit(0)                      # warp 0 falls through: hop over the loop (patched)
    while k.pc() < bpc + 32:
        k.emit(vret())
    head = k.pc()
    for _ in range(3):
        if shared:
            k.emit(vsts(7, 10, 0))
            k.emit(vlds(11, 10, 7))
        else:
            k.emit(vst(7, 9, 0))
            k.emit(vst(7, 9, 0))
    k.emit(vjmp(head - k.pc()))
    k.patch(jmp_pc, vjmp(k.pc() - jmp_pc))
    for r in regs:
        npc = k.pc()
        target = npc + 32 + r
        k.emit(vblt(1, r, npc, target))
        while k.pc() < target:
            k.emit(vret())
    k.emit(vret())
    return k.instructions()


def case_base(index: int) -> int:
    return STORM_BASE + 0x400 * (index + 1)


def storm_image() -> dict:
    image = {STORE_BASE + pc: word for pc, word in store_kernel().items()}
    for i, (kind, _bx, pad, _lat) in enumerate(CASES):
        if kind == "after":
            image.update(error_storm_kernel(case_base(i), pad))
        else:
            image.update(error_bystander_kernel(case_base(i), pad, shared=kind == "bystander_sm"))
    return image


async def wait_drained(dut, bus: BusMonitor, timeout: int = 600):
    """Every transaction started so far has completed and the coalescer / shared memory are idle,
    for 4 consecutive cycles."""
    quiet = 0
    pending = None
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        pending = (bus.hs["ifar"] - bus.hs["ifr"], bus.hs["ar"] - bus.hs["r"],
                   bus.hs["aw"] - bus.hs["b"], int(dut.u_mu.busy_q.value), int(dut.sm_stall.value))
        quiet = quiet + 1 if not any(pending) else 0
        if quiet >= 4:
            return
    raise AssertionError(f"bus never drained after ERROR (pending {pending})")


@cocotb.test()
async def test_error_halts_issue_and_memory_traffic(dut):
    """Halt-on-ERROR: after the GPU enters ERROR nothing new starts on the fetch port, the
    coalescer or the shared memory; a transaction already under way completes legally; then the
    GPU is quiescent (no AXI beat, no issue / retire / warp-done / kernel-done) until CTRL.reset,
    while STATUS keeps reporting ERROR with no interrupt.  56 error-injection cases (see CASES)
    with slow responders."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    image = storm_image()
    instr_task = cocotb.start_soon(instr_responder(dut, image, latency=2))
    data_task = cocotb.start_soon(data_responder(dut, mem, ar_latency=1, r_latency=1,
                                                 aw_latency=2, w_latency=1))
    inflight = {"mu_busy": 0, "if_outst": 0, "sm_stall": 0}
    fetch_lat = 2
    for i, (kind, block_x, pad, lat) in enumerate(CASES):
        where = f"{kind} block_x={block_x} pad={pad} fetch_latency={lat}"
        if lat != fetch_lat:        # the GPU is IDLE and drained here: safe to swap the responder
            instr_task.kill()
            instr_task = cocotb.start_soon(instr_responder(dut, image, latency=lat))
            fetch_lat = lat
        bus.arm()
        mem.clear()
        await gpu_launch(dut, kernel_pc=case_base(i), block_x=block_x)
        await wait_status(dut, ST_ERROR, timeout=6000)
        snap = bus.err_snap
        assert snap is not None, f"{where}: ERROR entry not sampled"
        for key in inflight:
            inflight[key] += snap[key]
        await wait_drained(dut, bus)
        await settle(dut, 24)
        quiet, quiet_mem = bus.activity(), dict(mem)
        await settle(dut, 300)
        assert bus.activity() == quiet and mem == quiet_mem, (
            f"{where}: the GPU kept working in ERROR: {quiet} -> {bus.activity()}")
        assert await axil_read(dut, GPU_STATUS) == ST_ERROR, f"{where}: STATUS left ERROR"
        assert dut.gpu_irq_o.value == 0 and await axil_read(dut, IRQ_STATUS) == 0
        bus.check_clean(where)
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=200)
        await settle(dut, 10)
        bus.check_clean(f"{where}, after reset")
    # The sweep must really have asked for each kind of request while in ERROR (so each gate was
    # exercised) and have had a fetch in flight at the moment of ERROR.  A coalescer burst or a
    # shared-memory access can NOT be in flight at ERROR entry in this pipeline (the erroring
    # branch executes only with memory idle and nothing behind it in ID/EX); that case is
    # covered by test_error_injected_mid_traffic_halts_and_drains.
    assert inflight["if_outst"] > 0, f"no fetch was in flight at ERROR: {inflight}"
    for what, n in bus.demand.items():
        assert n > 0, f"the {what} gate was never exercised in ERROR: demand {bus.demand}"
    assert not bus.errors, bus.errors[:3]
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()


@cocotb.test()
async def test_error_reset_while_inflight_drains(dut):
    """CTRL.reset written as early as software can after ERROR (the very cycle state_q enters
    ERROR, so a fetch / burst / shared-memory access may still be in flight) waits for the drain:
    the bus stays protocol-clean, nothing is outstanding at soft_clr, the GPU reaches IDLE and a
    plain kernel then runs correctly."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    image = storm_image()
    instr_task = cocotb.start_soon(instr_responder(dut, image, latency=2))
    data_task = cocotb.start_soon(data_responder(dut, mem, ar_latency=1, r_latency=1,
                                                 aw_latency=2, w_latency=1))
    clears = bus.clears
    fetch_lat = 2
    for i, (kind, block_x, pad, lat) in enumerate(CASES):
        where = f"{kind} block_x={block_x} pad={pad} fetch_latency={lat}"
        if lat != fetch_lat:
            instr_task.kill()
            instr_task = cocotb.start_soon(instr_responder(dut, image, latency=lat))
            fetch_lat = lat
        await gpu_launch(dut, kernel_pc=case_base(i), block_x=block_x)
        for _ in range(6000):
            await RisingEdge(dut.clk)
            if int(dut.state_q.value) == ST_ERROR_ENC:
                break
        else:
            raise AssertionError(f"{where}: never entered ERROR")
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=400)
        await settle(dut, 20)
        bus.check_clean(f"{where}, reset at ERROR entry")
        assert bus.clears > clears, f"{where}: soft_clr never fired"
        clears = bus.clears
        quiet = bus.activity()
        await settle(dut, 60)
        assert bus.activity() == quiet, f"{where}: activity after IDLE"
        mem.clear()
        await gpu_launch(dut, kernel_pc=STORE_BASE, block_x=8)
        await wait_status(dut, ST_DONE, timeout=6000)
        check_store(mem)
        bus.check_clean(f"{where}, fresh kernel")
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=200)
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()


@cocotb.test()
async def test_error_injected_mid_traffic_halts_and_drains(dut):
    """The sticky error flop is forced high at 100 offsets into a kernel that streams VST / VSTS /
    VLDS (60) or VSTS / VLDS only (40), so that a coalescer burst, a shared-memory access or a
    fetch is in flight at the moment of ERROR (a real divergence overflow cannot time it that
    way).  Required: the in-flight
    transaction completes legally (AR/R, AW/W/B balance, no dropped valid, no orphan beat), nothing
    new starts once ERROR is entered, the GPU is then quiescent with STATUS == ERROR, and CTRL.reset
    returns it to IDLE with a correct relaunch."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)
    shmem_base = 0x6000
    image = dict(loop_store_kernel())
    image.update(loop_shmem_kernel(shmem_base))
    for pc, word in store_kernel().items():
        image[STORE_BASE + pc] = word
    mem: dict = {}
    bus = BusMonitor(dut)
    bus.start()
    instr_task = cocotb.start_soon(instr_responder(dut, image, latency=1))
    data_task = cocotb.start_soon(data_responder(dut, mem, ar_latency=1, r_latency=1,
                                                 aw_latency=2, w_latency=1))
    inflight = {"mu_busy": 0, "if_outst": 0, "sm_stall": 0}
    for pc, delay in [(0, d) for d in range(12, 72)] + [(shmem_base, d) for d in range(12, 52)]:
        where = f"error injected at +{delay} into the kernel at {pc:#x}"
        bus.arm()
        mem.clear()
        await gpu_launch(dut, kernel_pc=pc, block_x=16)
        await settle(dut, delay)
        assert await axil_read(dut, GPU_STATUS) == 0, f"{where}: loop kernel should be RUNNING"
        dut.u_cu.gpu_error_o.value = 1
        for _ in range(200):
            await RisingEdge(dut.clk)
            if bus.err_snap is not None:
                break
        snap = bus.err_snap
        assert snap is not None, f"{where}: ERROR never entered"
        for key in inflight:
            inflight[key] += snap[key]
        await wait_drained(dut, bus)
        await settle(dut, 24)
        quiet, quiet_mem = bus.activity(), dict(mem)
        await settle(dut, 200)
        assert bus.activity() == quiet and mem == quiet_mem, (
            f"{where}: the GPU kept working in ERROR: {quiet} -> {bus.activity()}")
        assert await axil_read(dut, GPU_STATUS) == ST_ERROR, f"{where}: STATUS left ERROR"
        bus.check_clean(where)
        await axil_write(dut, GPU_CTRL, CTRL_RESET)
        await wait_status(dut, ST_IDLE, timeout=200)
        await settle(dut, 10)
        bus.check_clean(f"{where}, after reset")
        assert int(dut.u_cu.gpu_error_o.value) == 0, f"{where}: reset did not clear the error"
    assert inflight["mu_busy"] > 0, f"no coalescer burst was in flight at ERROR: {inflight}"
    assert inflight["if_outst"] > 0, f"no fetch was in flight at ERROR: {inflight}"
    assert inflight["sm_stall"] > 0, f"no shared-memory access was in flight at ERROR: {inflight}"
    assert not bus.errors, bus.errors[:3]
    mem.clear()
    await gpu_launch(dut, kernel_pc=STORE_BASE, block_x=8)
    await wait_status(dut, ST_DONE, timeout=6000)
    check_store(mem)
    bus.check_clean("relaunch after the injection sweep")
    for t in (instr_task, data_task):
        t.kill()
    bus.stop()
