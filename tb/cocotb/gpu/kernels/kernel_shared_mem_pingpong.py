"""
Kernel test: shared-memory ping-pong — lane N writes shared[tid.x*4], reads shared[(7-tid.x)*4].

Uses REAL shared memory (VLDS/VSTS opcodes 0x22/0x23):
  1. Each lane writes its tid.x to shared[l*4] via VSTS.
  2. VSYNC barrier (intra-warp; single CU so it passes immediately).
  3. Each lane reads shared[(7-l)*4] via VLDS into r12.
  4. Each lane stores r12 to global OUT_BASE+0x40+l*4 via VST so the
     Python testbench can observe and self-check the result.

Expected: lane l stores (7-l) at OUT_BASE+0x40+l*4.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vaddi, vsll, vadd, vsub, vld, vst, vlds, vsts, vsync, vret,
    N_LANES,
)
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

OUT_BASE  = 0x400   # global memory output base address


def build_kernel() -> dict:
    """
    Phase 1: each lane writes r1 (= tid.x = l) to shared[l*4] via VSTS.
    Phase 2: vsync barrier.
    Phase 3: each lane reads shared[(7-l)*4] = shared[28-l*4] via VLDS into r12.
    Phase 4: each lane stores r12 to global OUT_BASE+0x40+l*4 via VST.
    """
    k = Kernel(base_pc=0)

    # r1[l] = l  (tid.x)
    k.emit(vmov_tid_x(1))
    # r2[l] = 2  (shift amount for *4)
    k.emit(vaddi(2, 0, 2))
    # r3[l] = l*4  (byte offset within shared)
    k.emit(vsll(3, 1, 2))

    # --- Phase 1: write r1 to shared[l*4] via VSTS ---
    # VSTS encodes rs2 index in imm[4:0]; eff_addr = rs1_base[l] + base_offset + rs2_idx
    # We want addr = 0 + l*4.
    # Choose rs2=r1 (index=1), so imm[4:0]=1; eff_offset = base_offset_hi + 1.
    # We want eff_offset = l*4, but that varies per lane.
    # Solution: put the varying part in rs1_base: rs1_base[l] = l*4 - 1, rs2_idx=1.
    # eff_addr[l] = (l*4 - 1) + 1 = l*4.  base_offset=0 (must be multiple of 32).
    # r4[l] = l*4 - 1
    k.emit(vaddi(4, 3, -1))          # r4[l] = l*4 - 1
    k.emit(vsts(1, 4, 0))             # shared[l*4] = r1[l] = l

    # --- Phase 2: vsync barrier ---
    k.emit(vsync())

    # --- Phase 3: read shared[(7-l)*4] into r12 via VLDS ---
    # addr[l] = (7-l)*4 = 28 - l*4
    # r5[l] = 28 - l*4
    k.emit(vaddi(5, 0, 28))          # r5[l] = 28
    k.emit(vsub(5, 5, 3))            # r5[l] = 28 - l*4
    k.emit(vlds(12, 5, 0))           # r12[l] = shared[(7-l)*4] = 7-l

    # --- Phase 4: store r12 to global OUT_BASE+0x40+l*4 via VST ---
    # VST encoding: rs2=r12 (index=12), eff_addr = rs1_base[l] + 12.
    # We want addr = OUT_BASE+0x40+l*4 = OUT_BASE+64+l*4.
    # rs1_base[l] = OUT_BASE+64+l*4-12 = OUT_BASE+52+l*4.
    # base_offset must be multiple of 32; rs2_idx=12 → imm[4:0]=12; imm[11:5]=0.
    # eff_offset = 0 + 12 = 12.  So rs1_base[l] = OUT_BASE+0x40-12+l*4.
    k.emit(vaddi(13, 0, OUT_BASE + 0x40 - 12))   # r13[l] = OUT_BASE+52
    k.emit(vadd(13, 13, 3))                        # r13[l] = OUT_BASE+52+l*4
    k.emit(vst(12, 13, 0))                         # mem[OUT_BASE+0x40+l*4] = r12[l] = 7-l

    k.emit(vret())
    return k.instructions()


@cocotb.test()
async def test_shared_mem_pingpong(dut):
    """Lane N writes tid.x to shared[N*4]; reads shared[(7-N)*4] = 7-N; stores to global.

    Validates that shared-memory VLDS/VSTS instructions are correctly routed
    through the compute unit EXECUTE stage and shared_memory scratchpad.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    data_mem: dict = {}

    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task  = cocotb.start_soon(data_responder(dut, data_mem))

    await gpu_launch(dut, kernel_pc=0, block_x=8)
    done = await gpu_wait_done(dut, timeout=15_000)
    instr_task.kill()
    data_task.kill()
    assert done, "GPU did not complete (shared-mem pingpong kernel)"

    # Each lane l should have stored 7-l at OUT_BASE+0x40+l*4
    for l in range(N_LANES):
        addr     = OUT_BASE + 0x40 + l * 4
        got      = data_mem.get(addr)
        expected = 7 - l
        assert got is not None, f"lane {l}: no result write @ 0x{addr:03x}"
        assert got & 0xFFFF_FFFF == expected, \
            f"lane {l}: expected {expected}, got {got & 0xFFFF_FFFF}"
