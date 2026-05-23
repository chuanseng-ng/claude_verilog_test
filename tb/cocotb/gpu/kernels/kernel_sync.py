"""
Kernel test: VSYNC barrier between two warps inside the same block.

Launch with BLOCK_X=16 → 2 warps (warp 0: lanes 0..7, warp 1: lanes 0..7 of second warp).

Kernel:
  0x000: vmov_tid_x r1    r1[l] = lane index (0..7 in each warp)
  0x004: vmov_bid_x r2    r2[l] = warp_id (0 or 1)
  0x008: vsync            barrier — both warps must reach here
  0x00C: vadd r3, r1, r2  r3[l] = tid.x + warp_id
  0x010: vaddi r4, r0, 2
  0x014: vsll  r5, r1, r4  r5[l] = l*4
  -- store r3 to OUT_BASE + warp_id*32 + l*4 (warp-separated output area) --
  -- addr = r6[l] + 3; need r6[l] = base - 3 + l*4                        --
  0x018: vaddi r6, r2, OUT_BASE - 3   r6[l] = OUT_BASE + warp_id - 3
  Actually, the offset formula gets complex with warp_id in a register.
  Simplify: each warp stores to OUT_BASE + warp_id*0x40 + l*4.
  With warp_id in r2: warp_base = OUT_BASE + r2*0x40.

  Use: vaddi r7, r0, 0x40; vmul r7, r2, r7  → warp_offset[l] = warp_id * 64
       vaddi r8, r0, OUT_BASE
       vadd  r8, r8, r7    → r8[l] = OUT_BASE + warp_id*64
       vadd  r9, r8, r5    → r9[l] = OUT_BASE + warp_id*64 + l*4
       vst(r3, r9, offset) ...

  VST: vst(rs2_data=3, rs1_base=r9): imm=3 → addr=r9[l]+3; need r9[l]+3 = target
       So r9[l] = target - 3 = OUT_BASE + warp_id*64 + l*4 - 3
       Do the subtract after building r9.

Simplified kernel (avoiding complex warp_id-indexed stores):
  Each warp stores r3 (= tid.x + warp_id) to a flat array at OUT_BASE + warp_id*32 + l*4.
  warp_id*32 = warp_id << 5 (shift left 5).

  0x000: vmov_tid_x r1      r1[l]=l
  0x004: vmov_bid_x r2      r2[l]=warp_id
  0x008: vsync
  0x00C: vadd r3, r1, r2    r3[l] = l + warp_id  (sum to verify both ran)
  0x010: vaddi r4, r0, 5
  0x014: vsll  r6, r2, r4   r6[l] = warp_id*32
  0x018: vaddi r7, r0, 2
  0x01C: vsll  r5, r1, r7   r5[l] = l*4
  0x020: vadd  r6, r6, r5   r6[l] = warp_id*32 + l*4
  -- vst rs2=r3(idx=3): addr = r9[l]+3; r9[l]=OUT_BASE-3+warp_id*32+l*4 --
  0x024: vaddi r9, r0, OUT_BASE-3
  0x028: vadd  r9, r9, r6   r9[l] = OUT_BASE-3+warp_id*32+l*4
  0x02C: vst(3, r9, 0)      mem[OUT_BASE+warp_id*32+l*4] = l+warp_id
  0x030: vret
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vmov_bid_x, vaddi, vsll, vadd, vst, vsync, vret,
    N_LANES,
)
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

OUT_BASE = 0x500


def build_kernel() -> dict:
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))                   # r1[l] = tid.x (0..7)
    k.emit(vmov_bid_x(2))                   # r2[l] = warp_id
    k.emit(vsync())                          # barrier
    k.emit(vadd(3, 1, 2))                   # r3[l] = tid.x + warp_id
    k.emit(vaddi(4, 0, 5))                  # r4[l] = 5 (shift for *32)
    k.emit(vsll(6, 2, 4))                   # r6[l] = warp_id * 32
    k.emit(vaddi(7, 0, 2))                  # r7[l] = 2 (shift for *4)
    k.emit(vsll(5, 1, 7))                   # r5[l] = l*4
    k.emit(vadd(6, 6, 5))                   # r6[l] = warp_id*32 + l*4
    # vst(rs2_data=3, rs1_base=r9): imm=3 → addr=r9[l]+3 = OUT_BASE+warp_id*32+l*4
    k.emit(vaddi(9, 0, OUT_BASE - 3))
    k.emit(vadd(9, 9, 6))                   # r9[l] = OUT_BASE-3+warp_id*32+l*4
    k.emit(vst(3, 9, 0))
    k.emit(vret())
    return k.instructions()


@cocotb.test()
async def test_sync_two_warps(dut):
    """VSYNC barrier with 2 warps (BLOCK_X=16); both complete and produce correct output."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await gpu_reset(dut)

    data_mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task  = cocotb.start_soon(data_responder(dut, data_mem))

    await gpu_launch(dut, kernel_pc=0, block_x=16)
    done = await gpu_wait_done(dut, timeout=20_000)
    instr_task.kill()
    data_task.kill()
    assert done, "GPU did not complete (sync kernel — possible VSYNC deadlock)"

    # Warp 0 stores tid.x + 0 = l at OUT_BASE + 0*32 + l*4
    # Warp 1 stores tid.x + 1 = l+1 at OUT_BASE + 1*32 + l*4
    for warp_id in range(2):
        for l in range(N_LANES):
            addr     = OUT_BASE + warp_id * 32 + l * 4
            got      = data_mem.get(addr)
            expected = l + warp_id
            assert got is not None, \
                f"warp {warp_id} lane {l}: no write @ 0x{addr:03x}"
            assert got & 0xFFFF_FFFF == expected, \
                f"warp {warp_id} lane {l}: expected {expected}, got {got & 0xFFFF_FFFF}"
