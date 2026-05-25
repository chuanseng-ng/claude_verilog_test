"""
Kernel test: divergent branch — if(tid.x < 4) r5=100 else r5=200; store to mem.

Branch encoding constraint: VBLT rs1=r1, rs2=r4 → rs2_idx=4 → offset[4:0]=4.
Smallest useful offset ≥ 4 with low 5 bits = 4: 36 (= 32+4 = 0x24).

Kernel layout (base_pc=0):
  0x000: vmov_tid_x r1         r1[l]=l
  0x004: vaddi r4, r0, 4       r4[l]=4 (threshold)
  0x008: vaddi r2, r0, 2       r2[l]=2 (shift amount, precomputed before diverge)
  0x00C: vsll  r3, r1, r2      r3[l]=l*4
  0x010: vblt  r1, r4, target=0x034  (offset=36, rs2_idx=4 ✓)
  -- false-path (lanes 4..7, l≥4) starts here --
  0x014: vaddi r5, r0, 200
  0x018: vaddi r10, r0, BASE_OUT-5   (r10[l]=BASE_OUT-5)
  0x01C: vadd  r10, r10, r3          (r10[l]=BASE_OUT-5+l*4)
  0x020: vst   r5(idx=5), r10, 0    (addr=r10[l]+5=BASE_OUT+l*4)
  0x024: vret
  -- padding PCs 0x028, 0x02C, 0x030 are never executed --
  -- true-path (lanes 0..3, l<4) starts here --
  0x034: vaddi r5, r0, 100
  0x038: vaddi r10, r0, BASE_OUT-5
  0x03C: vadd  r10, r10, r3
  0x040: vst   r5(idx=5), r10, 0
  0x044: vret

VST: vst(rs2_data=5, rs1_base=10, base_offset=0)
     imm=5 → addr = r10[l]+5 = BASE_OUT+l*4
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vaddi, vsll, vadd, vst, vret,
    vblt, branch_rs2_for, N_LANES,
)
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

BASE_OUT = 0x200


def build_kernel() -> dict:
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))               # r1[l] = l
    k.emit(vaddi(4, 0, 4))              # r4[l] = 4 (threshold; also rs2 for vblt)
    k.emit(vaddi(2, 0, 2))              # r2[l] = 2 (precomputed)
    k.emit(vsll(3, 1, 2))               # r3[l] = l*4

    branch_pc = k.pc()                  # = 0x010
    # rs2=r4 (idx=4), offset=36 so offset[4:0]=4 ✓
    target_pc = branch_pc + 36          # = 0x034
    assert branch_rs2_for(target_pc - branch_pc) == 4, "rs2/offset mismatch"
    k.emit(vblt(1, 4, branch_pc, target_pc))

    # False-path (fall-through, lanes 4..7):
    k.emit(vaddi(5, 0, 200))
    k.emit(vaddi(10, 0, BASE_OUT - 5))
    k.emit(vadd(10, 10, 3))
    k.emit(vst(5, 10, 0))
    k.emit(vret())

    # Pad to true-path start (0x034)
    while k.pc() < target_pc:
        k.emit(vret())                  # unreachable padding

    # True-path (lanes 0..3):
    assert k.pc() == target_pc, f"true-path PC mismatch: {k.pc():#x} != {target_pc:#x}"
    k.emit(vaddi(5, 0, 100))
    k.emit(vaddi(10, 0, BASE_OUT - 5))
    k.emit(vadd(10, 10, 3))
    k.emit(vst(5, 10, 0))
    k.emit(vret())

    return k.instructions()


@cocotb.test()
async def test_divergence_basic(dut):
    """if(tid.x<4) stores 100, else stores 200 — divergent branch."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    data_mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task  = cocotb.start_soon(data_responder(dut, data_mem))

    await gpu_launch(dut, kernel_pc=0, block_x=8)
    done = await gpu_wait_done(dut, timeout=15_000)
    instr_task.kill()
    data_task.kill()
    assert done, "GPU did not complete (divergence kernel)"

    for l in range(N_LANES):
        addr     = BASE_OUT + l * 4
        got      = data_mem.get(addr)
        expected = 100 if l < 4 else 200
        assert got is not None, f"lane {l}: no write @ 0x{addr:03x}"
        assert got & 0xFFFF_FFFF == expected, \
            f"lane {l}: expected {expected}, got {got & 0xFFFF_FFFF}"
