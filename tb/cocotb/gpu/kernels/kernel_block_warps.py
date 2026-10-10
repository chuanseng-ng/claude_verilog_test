"""
Kernel test: how many warps does gpu_top run for a given BLOCK_X? (beads a5ze, 47lf)

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
  test_block_sizes_57_to_64        EVERY BLOCK_X in 57..64 (each its own launch) must run all
                                   8 warps.  Regression for bead 47lf / GH #254: the warp COUNT
                                   (0..8) was held in WARP_W = 3 bits and saturated at 7, so
                                   warp 7 (threads 56..63) never ran.  Fixed -- this test was
                                   expect_fail until then; the limits below were never loosened.
  test_lane_results_match_model    a second, per-LANE kernel: every one of the 64 lanes (and the
                                   tail lanes of a partially filled last warp) stores a value that
                                   depends on its (warp, lane); the complete set of stores must
                                   equal the union of GpuRefModel runs, one per warp -- no missing
                                   store, no extra store, no wrong value.
  test_block_sizes_above_cap       BLOCK_X > 64 cannot be honoured (warp storage is 8 deep); the
                                   documented behaviour is truncation to 8 warps.

Not pinned here, deliberately: BLOCK_X = 0 (no warp ever issues, so STATUS[done] never sets --
the launch hangs until CTRL reset) and the masking of tail lanes (a partially filled last warp
runs ALL 8 lanes; init_mask is always 0xFF in RTL and in both reference models).  Both are
out of 47lf's scope; see the bead notes.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cocotb
from cocotb.clock import Clock
from gpu_asm import (
    Kernel, instr_responder, data_responder,
    vmov_tid_x, vmov_bid_x, vaddi, vadd, vmul, vsll, vst, vret,
)
from gpu_ref_model import GpuRefModel
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

OUT = 0x300
N_WARPS = 8
N_LANES = 8


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


def build_lane_kernel() -> dict:
    """Every lane of every warp stores its own value at its own word.

    gid = warp_id*8 + lane;  mem[OUT + gid*4] = gid*gid + 0x11  (distinct for every gid, so
    a store routed to the wrong lane/warp slot or computed with the wrong warp_id shows up).
    """
    k = Kernel(base_pc=0)
    k.emit(vmov_tid_x(1))             # r1[l] = lane
    k.emit(vmov_bid_x(2))             # r2[l] = warp_id
    k.emit(vaddi(3, 0, 3))            # r3[l] = 3
    k.emit(vsll(4, 2, 3))             # r4[l] = warp_id * 8
    k.emit(vadd(5, 4, 1))             # r5[l] = gid
    k.emit(vmul(6, 5, 5))             # r6[l] = gid * gid
    k.emit(vaddi(7, 6, 0x11))         # r7[l] = gid*gid + 0x11  (data)
    k.emit(vaddi(8, 0, 2))            # r8[l] = 2
    k.emit(vsll(8, 5, 8))             # r8[l] = gid * 4
    k.emit(vaddi(9, 8, OUT - 7))      # r9[l] = OUT + gid*4 - 7
    k.emit(vst(7, 9, 0))              # mem[r9 + 7] = r7
    k.emit(vret())
    return k.instructions()


async def run_block(dut, words: dict, block_x: int) -> dict:
    """Launch one block of ``block_x`` threads of ``words``; return the data-memory dict."""
    await gpu_reset(dut)
    data_mem: dict = {}
    instr_task = cocotb.start_soon(instr_responder(dut, words))
    data_task = cocotb.start_soon(data_responder(dut, data_mem))
    await gpu_launch(dut, kernel_pc=0, block_x=block_x)
    done = await gpu_wait_done(dut, timeout=20_000)
    instr_task.kill()
    data_task.kill()
    assert done, f"GPU did not complete for BLOCK_X={block_x}"
    return data_mem


async def warps_that_ran(dut, block_x: int) -> list[int]:
    """Launch one block of ``block_x`` threads; return the sorted warp ids that stored a marker."""
    data_mem = await run_block(dut, build_kernel(), block_x)
    ran = []
    for w in range(N_WARPS):
        marker = data_mem.get(OUT + 4 * w)
        if marker is not None:
            assert marker & 0xFFFF_FFFF == w + 1, (
                f"warp {w} stored {marker:#x}, expected marker {w + 1}"
            )
            ran.append(w)
    dut._log.info(f"BLOCK_X={block_x}: warps that ran {ran}")
    return ran


def expected_warps(block_x: int) -> list[int]:
    """Architectural expectation: ceil(block_x / 8) warps, capped at the 8 that exist."""
    return list(range(min(-(-block_x // N_LANES), N_WARPS)))


def expected_stores(words: dict, warps: list[int]) -> dict:
    """Union of GpuRefModel single-warp runs: the reference for every lane of every warp."""
    stores: dict = {}
    for w in warps:
        stores.update(GpuRefModel(warp_id=w).run(words))
    return stores


@cocotb.test()
async def test_block_sizes_below_cap(dut):
    """ceil(BLOCK_X/8) warps run, and exactly warps 0..n-1."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for block_x in (1, 8, 9, 16, 17, 55, 56):
        want = expected_warps(block_x)
        got = await warps_that_ran(dut, block_x)
        assert got == want, f"BLOCK_X={block_x}: warps that ran {got}, expected {want}"


@cocotb.test()
async def test_block_sizes_57_to_64(dut):
    """BLOCK_X 57..64 is 8 warps (64 threads is the architectural maximum)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    bad = []
    for block_x in range(57, 65):          # every size, individually -- do not stop at the first
        got = await warps_that_ran(dut, block_x)
        if got != list(range(N_WARPS)):
            bad.append(f"BLOCK_X={block_x}: warps that ran {got}")
    assert not bad, f"expected all of {list(range(N_WARPS))}: " + "; ".join(bad)


@cocotb.test()
async def test_lane_results_match_model(dut):
    """All lanes of all warps match GpuRefModel, incl. the 56/57 and 63/64 boundaries."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    words = build_lane_kernel()
    bad = []
    for block_x in (1, 8, 9, 56, 57, 58, 60, 63, 64):
        want = expected_stores(words, expected_warps(block_x))
        got = await run_block(dut, words, block_x)
        got = {a: v & 0xFFFF_FFFF for a, v in got.items()}
        want = {a: v & 0xFFFF_FFFF for a, v in want.items()}
        if got != want:
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            wrong = sorted(a for a in set(got) & set(want) if got[a] != want[a])
            bad.append(
                f"BLOCK_X={block_x}: {len(got)}/{len(want)} stores; missing lanes "
                f"{[(a - OUT) // 4 for a in missing]}, extra {[(a - OUT) // 4 for a in extra]}, "
                f"wrong {[(a - OUT) // 4 for a in wrong]}"
            )
        else:
            dut._log.info(f"BLOCK_X={block_x}: {len(got)} lane stores match the model")
    assert not bad, "; ".join(bad)


@cocotb.test()
async def test_block_sizes_above_cap(dut):
    """BLOCK_X > 64 is truncated to the 8 warps that exist (not wrapped, not zero)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for block_x in (65, 72, 128, 1023):
        got = await warps_that_ran(dut, block_x)
        assert got == list(range(N_WARPS)), (
            f"BLOCK_X={block_x}: warps that ran {got}, expected truncation to all {N_WARPS}"
        )
