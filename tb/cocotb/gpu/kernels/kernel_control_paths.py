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
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vaddi, vsll, vst, vret, vblt, N_LANES,
)
from gpu_test_utils import (
    gpu_reset, gpu_launch, gpu_wait_done, axil_write, axil_read,
    GPU_CTRL, GPU_STATUS, GPU_BLOCK_Y, GPU_BLOCK_Z, GPU_IRQ_CLR, GPU_KERNEL_PC,
    GPU_GRID_X, GPU_GRID_Y, GPU_GRID_Z, GPU_BLOCK_X,
)

OUT = 0x300
CTRL_LAUNCH, CTRL_RESET, CTRL_IRQ_EN = 0x1, 0x2, 0x4
ST_IDLE, ST_DONE, ST_ERROR = 0x1, 0x2, 0x4
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
    for _ in range(timeout):
        st = await axil_read(dut, GPU_STATUS)
        if st & mask:
            return st
        await RisingEdge(dut.clk)
    raise TimeoutError(f"STATUS never showed {mask:#x}")


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
