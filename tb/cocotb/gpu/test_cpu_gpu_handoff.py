"""
CPU-GPU handoff integration test — Phase 4 sign-off step 4.

Exercises the full CPU-side control-plane handshake against gpu_top, acting as a
proxy for the CPU driver:

  1. CPU writes the kernel descriptor over AXI4-Lite (PC, grid, block).
  2. CPU launches the kernel AND enables the completion IRQ in one CTRL write
     (CTRL[0]=launch W1S, CTRL[2]=irq_enable).
  3. GPU runs the kernel; the in-test AXI responders serve instruction fetch and
     global load/store traffic.
  4. CPU polls STATUS[done] and observes gpu_irq_o assert on completion.
  5. CPU reads back the results the kernel wrote to global memory.
  6. CPU clears the IRQ (IRQ_CLR W1C) and confirms gpu_irq_o deasserts.

This is the control-plane proxy — there is no instantiated CPU; the testbench
drives the same AXI4-Lite register sequence the CPU firmware would.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vaddi, vsll, vadd, vst, vret, N_LANES,
)
from gpu_test_utils import (
    gpu_reset, axil_write, axil_read, gpu_wait_done,
    GPU_CTRL, GPU_STATUS, GPU_KERNEL_PC, GPU_GRID_X, GPU_GRID_Y, GPU_GRID_Z,
    GPU_BLOCK_X, GPU_BLOCK_Y, GPU_BLOCK_Z, GPU_IRQ_CLR,
)

OUT_BASE = 0x300

CTRL_LAUNCH     = 0x1
CTRL_IRQ_ENABLE = 0x4


def build_kernel() -> dict:
    """Each lane stores its tid.x to OUT_BASE + l*4 (observable handoff result)."""
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))               # r1[l] = l
    k.emit(vaddi(2, 0, 2))              # r2[l] = 2
    k.emit(vsll(3, 1, 2))               # r3[l] = l*4 (byte offset)
    k.emit(vaddi(10, 0, OUT_BASE - 1))  # r10[l] = OUT_BASE-1
    k.emit(vadd(10, 10, 3))             # r10[l] = OUT_BASE-1 + l*4
    k.emit(vst(1, 10, 0))               # mem[OUT_BASE + l*4] = r1[l] = l
    k.emit(vret())
    return k.instructions()


async def _launch_with_irq(dut, *, kernel_pc, block_x):
    """Write descriptor, then launch + enable IRQ in a single CTRL write."""
    await axil_write(dut, GPU_KERNEL_PC, kernel_pc)
    await axil_write(dut, GPU_GRID_X,  1)
    await axil_write(dut, GPU_GRID_Y,  1)
    await axil_write(dut, GPU_GRID_Z,  1)
    await axil_write(dut, GPU_BLOCK_X, block_x)
    await axil_write(dut, GPU_BLOCK_Y, 1)
    await axil_write(dut, GPU_BLOCK_Z, 1)
    await axil_write(dut, GPU_CTRL, CTRL_LAUNCH | CTRL_IRQ_ENABLE)


@cocotb.test()
async def test_cpu_gpu_handoff(dut):
    """Full launch → run → IRQ → result-readback → IRQ-clear handshake."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    data_mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task  = cocotb.start_soon(data_responder(dut, data_mem))

    # Before launch the GPU must be idle and IRQ low.
    assert int(dut.gpu_irq_o.value) == 0, "IRQ should be low before launch"

    await _launch_with_irq(dut, kernel_pc=0, block_x=8)

    done = await gpu_wait_done(dut, timeout=15_000)
    assert done, "GPU never asserted STATUS[done] after launch"

    # Completion IRQ must be asserted now (irq_enable was set at launch).
    await Timer(1, units="ns")
    assert int(dut.gpu_irq_o.value) == 1, \
        "gpu_irq_o should assert on kernel completion with IRQ enabled"

    # CPU reads back the per-lane results the kernel wrote to global memory.
    instr_task.kill()
    data_task.kill()
    for l in range(N_LANES):
        addr = OUT_BASE + l * 4
        got  = data_mem.get(addr)
        assert got is not None, f"lane {l}: no result write @ 0x{addr:x}"
        assert got & 0xFFFF_FFFF == l, \
            f"lane {l}: expected {l}, got {got & 0xFFFF_FFFF}"

    # CPU acknowledges the interrupt (W1C) and confirms it deasserts.
    await axil_write(dut, GPU_IRQ_CLR, 0x1)
    await Timer(1, units="ns")
    assert int(dut.gpu_irq_o.value) == 0, "gpu_irq_o should deassert after IRQ_CLR"
