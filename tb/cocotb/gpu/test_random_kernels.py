"""
Phase 4 random-kernel regression — golden-plan sign-off step 5.

Generates many randomized GPU kernels, runs each on gpu_top, and compares the
resulting global memory against the GpuRefModel reference interpreter
(gpu_ref_model.py, which matches the RTL/gpu_asm opcode encoding). A per-kernel
watchdog (gpu_wait_done timeout) detects deadlocks.

Kernel shape (straight-line, single 8-lane warp):
  init    : r1=tid.x, r2=2, r3=l*4
  compute : K random R/I-type ALU ops (+ occasional VSYNC) over working regs
  store   : S distinct data registers stored to distinct global regions, so
            lane l writes region_base + l*4
  VRET

Divergent branches / loads / shared memory are out of scope here (covered by the
directed kernel tests); the generator emits only the subset GpuRefModel models,
so any model/RTL mismatch is a real datapath bug, not a generator artifact.

Config (env):
  RANDOM_KERNELS        number of kernels (default 1000)
  RANDOM_KERNELS_SMOKE  if set, use 25 kernels (quick CI/smoke)
  RANDOM_KERNELS_SEED   base seed (default 0xC0DE)
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(__file__))

import cocotb
from cocotb.clock import Clock

from gpu_asm import (
    Kernel, instr_responder, data_responder, N_LANES,
    vmov_tid_x, vaddi, vsll, vadd, vsub, vmul, vand, vor, vxor, vsrl, vsra,
    vandi, vori, vxori, vst, vsync, vret,
)
from gpu_ref_model import GpuRefModel
from gpu_test_utils import gpu_reset, gpu_launch, gpu_wait_done

# Infrastructure registers (not used as random ALU destinations)
R_TID, R_TWO, R_OFF, R_BASE = 1, 2, 3, 4
WORKING = list(range(5, 16))   # r5..r15 random data/working registers

R_OPS = [
    ("vadd", vadd), ("vsub", vsub), ("vmul", vmul),
    ("vand", vand), ("vor", vor), ("vxor", vxor),
    ("vsll", vsll), ("vsrl", vsrl), ("vsra", vsra),
]
I_OPS = [("vaddi", vaddi), ("vandi", vandi), ("vori", vori), ("vxori", vxori)]

STORE_REGIONS = [0x200, 0x240, 0x280]   # 64B apart; lane span (28B) < stride


def gen_random_kernel(seed: int):
    """Return ({pc: word}, expected_global_mem) for a random straight-line kernel."""
    rng = random.Random(seed)
    k = Kernel(base_pc=0)

    # init
    k.emit(vmov_tid_x(R_TID))          # r1[l] = l
    k.emit(vaddi(R_TWO, 0, 2))         # r2 = 2
    k.emit(vsll(R_OFF, R_TID, R_TWO))  # r3[l] = l*4

    # seed working registers with random constants
    for r in WORKING:
        k.emit(vaddi(r, 0, rng.randint(-2048, 2047)))

    # compute phase
    n_ops = rng.randint(10, 24)
    for _ in range(n_ops):
        if rng.random() < 0.08:
            k.emit(vsync())
            continue
        rd = rng.choice(WORKING)
        if rng.random() < 0.5:
            _, fn = rng.choice(R_OPS)
            rs1 = rng.choice([R_TID] + WORKING)
            rs2 = rng.choice([R_TID] + WORKING)
            k.emit(fn(rd, rs1, rs2))
        else:
            _, fn = rng.choice(I_OPS)
            rs1 = rng.choice([R_TID] + WORKING)
            k.emit(fn(rd, rs1, rng.randint(-2048, 2047)))

    # store phase: distinct data regs -> distinct global regions
    data_regs = rng.sample(WORKING, k=len(STORE_REGIONS))
    for base, dD in zip(STORE_REGIONS, data_regs):
        k.emit(vaddi(R_BASE, 0, base - dD))   # r4[l] = base - dD
        k.emit(vadd(R_BASE, R_BASE, R_OFF))   # r4[l] = base - dD + l*4
        k.emit(vst(dD, R_BASE, 0))            # mem[base + l*4] = regs[dD][l]

    k.emit(vret())

    words = k.instructions()
    expected = GpuRefModel(n_lanes=N_LANES).run(words)
    return words, expected


@cocotb.test()
async def test_random_kernels(dut):
    """Run N random kernels; assert 0 deadlocks and 0 RTL-vs-model mismatches."""
    n_kernels = 25 if os.environ.get("RANDOM_KERNELS_SMOKE") \
        else int(os.environ.get("RANDOM_KERNELS", "1000"))
    base_seed = int(os.environ.get("RANDOM_KERNELS_SEED", "0xC0DE"), 0)

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    deadlocks = 0
    mismatches = 0
    first_failures = []

    for i in range(n_kernels):
        seed = base_seed + i
        words, expected = gen_random_kernel(seed)

        await gpu_reset(dut)
        data_mem = {}
        instr_task = cocotb.start_soon(instr_responder(dut, words))
        data_task  = cocotb.start_soon(data_responder(dut, data_mem))

        await gpu_launch(dut, kernel_pc=0, block_x=N_LANES)
        done = await gpu_wait_done(dut, timeout=3000)
        instr_task.kill()
        data_task.kill()

        if not done:
            deadlocks += 1
            if len(first_failures) < 10:
                first_failures.append(f"seed 0x{seed:x}: DEADLOCK (no STATUS[done])")
            continue

        # Compare global memory: every expected write must match, no extras.
        ok = (len(data_mem) == len(expected))
        for addr, val in expected.items():
            got = data_mem.get(addr)
            if got is None or (got & 0xFFFF_FFFF) != (val & 0xFFFF_FFFF):
                ok = False
                if len(first_failures) < 10:
                    first_failures.append(
                        f"seed 0x{seed:x}: @0x{addr:x} exp 0x{val:08x} "
                        f"got {'None' if got is None else f'0x{got & 0xFFFFFFFF:08x}'}")
                break
        if not ok:
            mismatches += 1

    dut._log.info(f"Random-kernel regression: {n_kernels} kernels, "
                  f"{deadlocks} deadlocks, {mismatches} mismatches")
    for f in first_failures:
        dut._log.error(f)

    assert deadlocks == 0, f"{deadlocks}/{n_kernels} kernels deadlocked"
    assert mismatches == 0, f"{mismatches}/{n_kernels} kernels mismatched the reference model"
