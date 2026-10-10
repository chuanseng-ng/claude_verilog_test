"""
Kernel test: how many warps does gpu_top run for a given BLOCK_X? (bead a5ze)

Every warp executes the same tiny kernel and writes a marker (warp_id + 1) to its own word:

  vmov_bid_x r2           r2[l] = warp_id
  vaddi r7, r2, 1         r7[l] = warp_id + 1          (marker, never 0)
  vaddi r3, r0, 2
  vsll  r4, r2, r3        r4[l] = warp_id * 4
  vaddi r9, r4, OUT-7     r9[l] = OUT + warp_id*4 - 7
  vst   r7 -> r9 + 7      mem[OUT + warp_id*4] = warp_id + 1
  vret

The architecture (CLAUDE.md "8 warps max; 64 total threads", PHASE4 spec "Warp size: 8 lanes")
means BLOCK_X in 1..64 must run ceil(BLOCK_X / 8) warps.  The check is the exact set of warps
that ran, not a count: a missing warp is a missing marker.

  test_block_sizes_below_cap       BLOCK_X = 1, 8, 9, 16, 17, 55, 56: ceil(BLOCK_X/8) warps
  test_block_sizes_57_to_64        BLOCK_X = 57 and 64 must run all 8 warps.  rtl/gpu/gpu_top.sv:251
                                   caps the 3-bit warp count at N_WARPS-1 = 7, so warp 7 never
                                   runs: expect_fail until the RTL is fixed (see the strict limits
                                   below -- they must NOT be loosened to make this pass)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_bid_x, vaddi, vsll, vst, vret,
)
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

OUT = 0x300
N_WARPS = 8


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


async def warps_that_ran(dut, block_x: int) -> list[int]:
    """Launch one block of ``block_x`` threads; return the sorted warp ids that stored a marker."""
    await gpu_reset(dut)
    data_mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, build_kernel()))
    data_task = cocotb.start_soon(data_responder(dut, data_mem))
    await gpu_launch(dut, kernel_pc=0, block_x=block_x)
    done = await gpu_wait_done(dut, timeout=20_000)
    instr_task.kill()
    data_task.kill()
    assert done, f"GPU did not complete for BLOCK_X={block_x}"
    ran = []
    for w in range(N_WARPS):
        marker = data_mem.get(OUT + 4 * w)
        if marker is not None:
            assert marker & 0xFFFF_FFFF == w + 1, (
                f"warp {w} stored {marker:#x}, expected marker {w + 1}"
            )
            ran.append(w)
    return ran


@cocotb.test()
async def test_block_sizes_below_cap(dut):
    """ceil(BLOCK_X/8) warps run, and exactly warps 0..n-1."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for block_x in (1, 8, 9, 16, 17, 55, 56):
        want = list(range(-(-block_x // 8)))
        got = await warps_that_ran(dut, block_x)
        assert got == want, f"BLOCK_X={block_x}: warps that ran {got}, expected {want}"


# Strict by construction: the full 8-warp set is required, not "at least 7".  When the RTL is
# fixed this test XPASSes, which cocotb reports as a failure -- the cue to delete expect_fail.
@cocotb.test(expect_fail=True)
async def test_block_sizes_57_to_64(dut):
    """BLOCK_X 57..64 is 8 warps (64 threads is the architectural maximum)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for block_x in (57, 64):
        got = await warps_that_ran(dut, block_x)
        assert got == list(range(N_WARPS)), (
            f"BLOCK_X={block_x}: warps that ran {got}, expected all of {list(range(N_WARPS))}"
        )
