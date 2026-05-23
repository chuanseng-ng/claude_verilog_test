"""
Kernel test: partial[l] = A[l] * B[l] for 8 lanes; CPU sums warp results.

Verifies VMUL (lower-32 product) and that storing partial products works.
The CPU (Python) sums the 8 partial products and checks against the reference.

Memory layout:
  A[0..7] → 0x180 + l*4
  B[0..7] → 0x1A0 + l*4
  P[0..7] → 0x1C0 + l*4  (partial products; CPU reads and sums)

VST encoding: vst(rs2_data=8, rs1_base=r9, base_offset=0)
  imm=8 → addr = r9[l]+8; need r9[l] = BASE_P - 8 + l*4
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vaddi, vsll, vadd, vmul, vld, vst, vret,
    N_LANES,
)
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

BASE_A = 0x180
BASE_B = 0x1A0
BASE_P = 0x1C0


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
    k.emit(vmul(8, 6, 7))             # r8[l] = A[l] * B[l] (lower 32)
    # vst rs2=r8(idx=8): addr = r9[l]+8 = BASE_P+l*4
    k.emit(vaddi(9, 0, BASE_P - 8))
    k.emit(vadd(9, 9, 3))
    k.emit(vst(8, 9, 0))
    k.emit(vret())
    return k.instructions()


@cocotb.test()
async def test_dot_product(dut):
    """partial[l]=A[l]*B[l] stored; CPU sums → dot product."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    A = [l + 1 for l in range(N_LANES)]       # 1, 2, ..., 8
    B = [2 * (l + 1) for l in range(N_LANES)] # 2, 4, ..., 16

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
    assert done, "GPU did not complete (dot-product kernel)"

    expected_partial = [(A[l] * B[l]) & 0xFFFF_FFFF for l in range(N_LANES)]
    expected_dot     = sum(A[l] * B[l] for l in range(N_LANES))

    for l in range(N_LANES):
        addr = BASE_P + l * 4
        got  = data_mem.get(addr)
        assert got is not None, f"lane {l}: no partial product written"
        assert got & 0xFFFF_FFFF == expected_partial[l], \
            f"lane {l}: partial product mismatch: expected {expected_partial[l]}, got {got}"

    # CPU reduction
    got_dot = sum(data_mem.get(BASE_P + l * 4, 0) & 0xFFFF_FFFF for l in range(N_LANES))
    assert got_dot == expected_dot, f"dot product: expected {expected_dot}, got {got_dot}"
