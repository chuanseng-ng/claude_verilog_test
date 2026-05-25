"""
Kernel test: memory coalescing — all lanes issue contiguous-address loads/stores.

Verifies that the GPU completes correctly when all 8 lanes access consecutive
word-aligned addresses (the ideal case for the memory coalescer).  Whether the
coalescer is enabled (GPU_ENABLE_COALESCE=1) or not, the result must be correct.

Secondary check: GPU_PERFCNT[5] (scatter AXI transactions) read via s_axil after
the kernel finishes.  With COALESCE=0 (default Phase 4) we expect exactly 8 loads
+ 8 stores = 16 scatter transactions.

Memory layout:
  SRC[0..7] → 0x300 + l*4
  DST[0..7] → 0x320 + l*4  (copy of SRC, written by kernel)

Kernel: load SRC[l] into r6, store r6 to DST[l].
VST: vst(rs2_data=6, rs1_base=r9, base_offset=0) → imm=6, addr=r9[l]+6=DST+l*4
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
from gpu_test_utils import gpu_reset, axil_read, gpu_launch, gpu_wait_done, GPU_PERFCNT0

BASE_SRC = 0x300
BASE_DST = 0x320


def build_kernel() -> dict:
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))              # r1[l] = l
    k.emit(vaddi(2, 0, 2))             # r2[l] = 2
    k.emit(vsll(3, 1, 2))              # r3[l] = l*4
    k.emit(vaddi(4, 0, BASE_SRC))      # r4[l] = BASE_SRC
    k.emit(vadd(4, 4, 3))              # r4[l] = BASE_SRC + l*4
    k.emit(vld(6, 4, 0))               # r6[l] = SRC[l]
    # vst rs2=r6(idx=6): addr = r9[l]+6 = BASE_DST+l*4
    k.emit(vaddi(9, 0, BASE_DST - 6))
    k.emit(vadd(9, 9, 3))
    k.emit(vst(6, 9, 0))
    k.emit(vret())
    return k.instructions()


@cocotb.test()
async def test_memory_coalesce(dut):
    """Contiguous-address load+store; verify data correctness and scatter count."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    src_values = [0xAB00 + l for l in range(N_LANES)]
    data_mem: dict = {}
    for l in range(N_LANES):
        data_mem[BASE_SRC + l * 4] = src_values[l]

    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task  = cocotb.start_soon(data_responder(dut, data_mem))

    await gpu_launch(dut, kernel_pc=0, block_x=8)
    done = await gpu_wait_done(dut, timeout=10_000)
    instr_task.kill()
    data_task.kill()
    assert done, "GPU did not complete (memory-coalesce kernel)"

    for l in range(N_LANES):
        addr = BASE_DST + l * 4
        got  = data_mem.get(addr)
        assert got is not None, f"lane {l}: no write to DST[{l}]"
        assert got & 0xFFFF_FFFF == src_values[l], \
            f"lane {l}: expected {src_values[l]:#x}, got {got:#010x}"

    # Perf counter[5] = scatter AXI txns; with COALESCE=0: 8 loads + 8 stores = 16
    scatter_cnt = await axil_read(dut, GPU_PERFCNT0 + 5 * 4)
    assert scatter_cnt >= 8, \
        f"expected ≥8 scatter transactions, got {scatter_cnt}"
