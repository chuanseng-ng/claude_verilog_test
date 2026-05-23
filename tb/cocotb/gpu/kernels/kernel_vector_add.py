"""
Kernel test: C[l] = A[l] + B[l] for all 8 lanes.

Memory layout (byte addresses):
  A[0..7] → 0x100 + l*4
  B[0..7] → 0x120 + l*4
  C[0..7] → 0x140 + l*4  (results written here)

VST encoding note: vst(rs2_data=8, rs1_base=r9) with base_offset=0 produces
  imm=8, effective addr = r9[l] + 8.  We set r9[l] = BASE_C - 8 + l*4.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vaddi, vsll, vadd, vld, vst, vret,
    N_LANES,
)
from gpu_test_utils import gpu_reset, axil_write, axil_read, gpu_launch, gpu_wait_done

BASE_A = 0x100
BASE_B = 0x120
BASE_C = 0x140


def build_kernel() -> dict:
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))             # r1[l] = l
    k.emit(vaddi(2, 0, 2))            # r2[l] = 2
    k.emit(vsll(3, 1, 2))             # r3[l] = l*4
    k.emit(vaddi(4, 0, BASE_A))       # r4[l] = BASE_A
    k.emit(vadd(4, 4, 3))             # r4[l] = BASE_A + l*4
    k.emit(vld(6, 4, 0))              # r6[l] = A[l]
    k.emit(vaddi(5, 0, BASE_B))       # r5[l] = BASE_B
    k.emit(vadd(5, 5, 3))             # r5[l] = BASE_B + l*4
    k.emit(vld(7, 5, 0))              # r7[l] = B[l]
    k.emit(vadd(8, 6, 7))             # r8[l] = A[l] + B[l]
    # vst rs2=r8(idx=8): imm=8 → addr = r9[l] + 8 = BASE_C + l*4
    k.emit(vaddi(9, 0, BASE_C - 8))   # r9[l] = BASE_C - 8
    k.emit(vadd(9, 9, 3))             # r9[l] = BASE_C - 8 + l*4
    k.emit(vst(8, 9, 0))              # mem[r9[l]+8] = r8[l]
    k.emit(vret())
    return k.instructions()


@cocotb.test()
async def test_vector_add(dut):
    """C[l] = A[l] + B[l] for 8 lanes."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    A = [10 + l for l in range(N_LANES)]
    B = [100 + l * 3 for l in range(N_LANES)]
    expected = [(A[l] + B[l]) & 0xFFFF_FFFF for l in range(N_LANES)]

    data_mem: dict = {}
    for l in range(N_LANES):
        data_mem[BASE_A + l * 4] = A[l]
        data_mem[BASE_B + l * 4] = B[l]

    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task  = cocotb.start_soon(data_responder(dut, data_mem))

    await gpu_launch(dut, kernel_pc=0, block_x=8)

    done = await gpu_wait_done(dut, timeout=10_000)
    instr_task.kill()
    data_task.kill()
    assert done, "GPU did not complete within watchdog limit"

    for l in range(N_LANES):
        addr = BASE_C + l * 4
        got  = data_mem.get(addr)
        assert got is not None, f"lane {l}: no write to C[{l}] @ 0x{addr:03x}"
        assert got & 0xFFFF_FFFF == expected[l], \
            f"lane {l}: expected {expected[l]}, got {got & 0xFFFF_FFFF}"
