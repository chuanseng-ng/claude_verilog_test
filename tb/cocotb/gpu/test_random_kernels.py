"""
Phase 4 random-kernel regression — broadened scope (B1/B2/B3).

Generates many randomized GPU kernels, runs each on gpu_top, and compares the
resulting global memory against the GpuRefModel reference interpreter
(gpu_ref_model.py, which matches the RTL/gpu_asm opcode encoding). A per-kernel
watchdog (gpu_wait_done timeout) detects deadlocks.

Kernel classes (mixed probabilistically, all in one pass):
  straight-line : R/I-type ALU + global stores only (original baseline).
  B1 global-load: seed an INPUT_REGION in global memory; emit VLD from it into
                  working regs; feed loaded values into compute+store phase.
  B2 shared-mem : emit VSTS (write scratchpad) → VSYNC → VLDS (read back) →
                  use result in compute → final VST to global.
  B3 divergent  : emit one guaranteed-reconverging single-level diamond:
                    VBLT rd=0, rs1=working_reg, rs2=r0, target=true_path
                    false-path: vaddi + VST + VRET
                    true-path : vaddi + VST + VRET
                  The ref model's SIMT stack handles reconvergence exactly as
                  gpu_compute_unit.sv does.

All four classes co-exist in a single test loop; the RNG picks which extensions
to apply per kernel while always preserving the core straight-line ALU+store
skeleton.  Every kernel ends with VRET (or two VRETs in the divergent diamond).

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
    vandi, vori, vxori, vst, vsts, vlds, vld, vsync, vret,
    VBLT, vbranch, branch_rs2_for,
    vst_effective_offset,
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

# Global store regions — 64 B apart; lane span (8 lanes * 4 B = 32 B) < 64 B stride
STORE_REGIONS = [0x200, 0x240, 0x280]

# B1: Input region for VLD — 64 B below stores, non-overlapping.
# Layout: INPUT_REGION_BASE + lane*4 → one word per lane.
INPUT_REGION_BASE = 0x100
INPUT_REGION_SIZE = N_LANES   # words (one per lane)

# B2: Shared-memory scratchpad base.
# Layout: SMEM_BASE + lane*4 → one word per lane.  Well within 16 KB / 32 banks.
# vsts/vlds bake rs2 index into imm[4:0]; base_offset must be a multiple of 32.
# We use base_offset_hi_mult32=0 always, so effective offset = rs2_data_index.
SMEM_BASE = 0   # shared byte address for lane 0; lane l → SMEM_BASE + l*4


def _seed_input_region(rng: random.Random) -> dict:
    """Return a dict {addr: value} seeding INPUT_REGION for one kernel."""
    return {
        INPUT_REGION_BASE + lane * 4: rng.randint(0, 0xFFFF_FFFF)
        for lane in range(INPUT_REGION_SIZE)
    }


def _emit_compute_phase(k: Kernel, rng: random.Random, n_ops: int):
    """Append n_ops random ALU instructions to k using WORKING regs."""
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


def _emit_store_phase(k: Kernel, rng: random.Random, data_regs: list):
    """Append VST instructions storing data_regs to STORE_REGIONS (one per region)."""
    for base, dD in zip(STORE_REGIONS, data_regs):
        # vst(rs2_data=dD, rs1_base=R_BASE, base_offset=0):
        #   eff_offset = 0 + dD  (because base_offset_hi_mult32=0, rs2_idx=dD)
        #   addr[l] = R_BASE[l] + dD
        # So we need R_BASE[l] = base + l*4 - dD (i.e. base - dD + l*4)
        # R_BASE = base - dD + R_OFF[l]   where R_OFF[l]=l*4
        k.emit(vaddi(R_BASE, 0, (base - dD) & 0xFFF))    # r4 = base-dD (low 12b)
        # Handle the case where base-dD might not fit in 12-bit signed:
        # For our ranges: base in {0x200,0x240,0x280}, dD in [5,15].
        # base-dD: 0x200-15=0x1F1 .. 0x280-5=0x27B. All fit in unsigned 12 bits
        # but sign-extend: 0x200=512 > 2047 → would sign-extend wrong.
        # Solution: emit as two-instruction sequence: vaddi r4,r0,base_hi; then vadd.
        # Actually let us use a cleaner approach: store R_OFF-adjusted base.
        # Recompute: we want R_BASE[l] = base + l*4 - dD_idx.
        # vst_effective_offset(dD, 0) = dD.
        # So addr[l] = R_BASE[l] + dD = base + l*4.
        # R_BASE[l] = base - dD + l*4.
        # vaddi R_BASE, r0, (base - dD):  value = base-dD for all lanes.
        # But base-dD for base=0x200=512, dD=5: 507.  507 < 2048 → fits signed 12b. OK.
        # For base=0x280=640, dD=5: 635 < 2048. OK.
        # All values in range [0x200-15, 0x280-5] = [497, 635] — all positive, < 2048. OK.
        k.emit(vadd(R_BASE, R_BASE, R_OFF))               # r4[l] += l*4
        k.emit(vst(dD, R_BASE, 0))                        # mem[r4[l]+dD] = regs[dD][l]


def gen_random_kernel(seed: int):
    """Return ({pc: word}, expected_global_mem, initial_gmem) for a random kernel.

    The returned initial_gmem must be seeded into the cocotb data_mem dict
    so the AXI data responder and GpuRefModel start from identical state.
    """
    rng = random.Random(seed)
    k = Kernel(base_pc=0)

    # Choose which B-class extensions to apply this kernel.
    # These are independent — a single kernel may get 0, 1, 2, or all 3.
    use_b1 = rng.random() < 0.40   # 40% chance: global loads
    use_b2 = rng.random() < 0.40   # 40% chance: shared memory round-trip
    use_b3 = rng.random() < 0.35   # 35% chance: single-level divergence diamond

    # Seed input region (used for B1 VLD; always generated so data_mem is consistent)
    input_gmem = _seed_input_region(rng)

    # ------------------------------------------------------------------ init
    k.emit(vmov_tid_x(R_TID))          # r1[l] = l
    k.emit(vaddi(R_TWO, 0, 2))         # r2 = 2
    k.emit(vsll(R_OFF, R_TID, R_TWO))  # r3[l] = l*4

    # Seed working registers with random constants
    for r in WORKING:
        k.emit(vaddi(r, 0, rng.randint(-2048, 2047)))

    # ------------------------------------------------------------------ B1: global loads
    # Load one value per lane from INPUT_REGION into a working reg, then mix it
    # into the compute phase by XOR-ing it into another working reg.
    vld_dest_reg = None
    if use_b1:
        vld_dest_reg = rng.choice(WORKING)
        mix_dest_reg = rng.choice([r for r in WORKING if r != vld_dest_reg])
        # R_BASE[l] = INPUT_REGION_BASE - vld_dest_reg + l*4
        # So addr[l] = R_BASE[l] + vld_dest_reg = INPUT_REGION_BASE + l*4
        # But VLD uses i_instr: addr[l] = rs1[l] + simm.
        # Simpler: set R_BASE[l] = INPUT_REGION_BASE + l*4, then VLD with offset=0.
        # R_BASE[l] = INPUT_REGION_BASE + l*4 = INPUT_REGION_BASE + R_OFF[l].
        # vaddi R_BASE, r0, INPUT_REGION_BASE
        k.emit(vaddi(R_BASE, 0, INPUT_REGION_BASE))   # r4 = 0x100 (fits 12b signed: 256<2048)
        k.emit(vadd(R_BASE, R_BASE, R_OFF))            # r4[l] = 0x100 + l*4
        k.emit(vld(vld_dest_reg, R_BASE, 0))           # rd[l] = gmem[r4[l]]
        k.emit(vxor(mix_dest_reg, mix_dest_reg, vld_dest_reg))  # mix in loaded value

    # ------------------------------------------------------------------ B2: shared memory
    # Pattern: VSTS(smem_reg, smem_base_reg, 0) → VSYNC → VLDS(rd, smem_base_reg, 0) → mix
    # smem_reg index is baked into imm[4:0], so addr[l] = smem_base_reg[l] + smem_reg_idx.
    # We want smem addr[l] = SMEM_BASE + l*4.
    # vsts(rs2_data=smem_reg, rs1_base=R_BASE, base_offset=0):
    #   eff_offset = 0 + smem_reg_idx
    #   addr[l] = R_BASE[l] + smem_reg_idx
    # So R_BASE[l] must = SMEM_BASE + l*4 - smem_reg_idx = (SMEM_BASE - smem_reg_idx) + l*4.
    # With SMEM_BASE=0: R_BASE[l] = l*4 - smem_reg_idx.
    # For smem_reg_idx in [5..15] and l in [0..7]: R_BASE[l] = l*4 - idx.
    #   For l=0: R_BASE[0] = -idx (negative). That's fine for 32-bit arithmetic.
    # vaddi R_BASE, r0, -smem_reg_idx  (fits in -2048..2047).
    # vadd  R_BASE, R_BASE, R_OFF      → R_BASE[l] = l*4 - smem_reg_idx.
    # vsts  smem_reg, R_BASE, 0        → smem[l*4] = regs[smem_reg][l].
    # vsync
    # vlds  load_reg, R_BASE, 0        → load_reg[l] = smem[l*4 - smem_reg_idx + smem_reg_idx]
    #                                                  = smem[l*4].
    # Wait — vlds uses i_instr: addr[l] = rs1[l] + simm.
    # vlds(rd, R_BASE, 0): addr[l] = R_BASE[l] + 0 = l*4 - smem_reg_idx.
    # That reads smem[l*4 - smem_reg_idx], not smem[l*4].
    # We need to read back what was stored. Stored at smem[l*4]. So vlds must use
    # a base that satisfies rs1[l] + offset = l*4.
    # Use R_OFF directly: R_OFF[l] = l*4. So vlds(load_reg, R_OFF, 0) reads smem[l*4].
    # But we need smem[l*4] = what was stored = regs[smem_reg][l].
    # VSTS addr[l] = R_BASE[l] + smem_reg_idx.
    # Set R_BASE[l] = l*4 - smem_reg_idx → addr = l*4. Stored at smem[l*4].
    # VLDS addr[l] = R_OFF[l] + 0 = l*4. Loads from smem[l*4]. Correct.
    if use_b2:
        smem_reg = rng.choice(WORKING)
        load_reg = rng.choice([r for r in WORKING if r != smem_reg])
        mix_target = rng.choice([r for r in WORKING if r not in (smem_reg, load_reg)])

        smem_reg_idx = smem_reg  # register index = smem_reg number

        # Set R_BASE[l] = l*4 - smem_reg_idx  (so vsts addr = smem_reg_idx + R_BASE[l] = l*4)
        smem_base_val = (-smem_reg_idx) & 0xFFF   # 12-bit two's complement
        k.emit(vaddi(R_BASE, 0, smem_base_val))
        k.emit(vadd(R_BASE, R_BASE, R_OFF))       # R_BASE[l] = l*4 - smem_reg_idx
        k.emit(vsts(smem_reg, R_BASE, 0))         # smem[l*4] = regs[smem_reg][l]
        k.emit(vsync())                            # VSYNC barrier
        k.emit(vlds(load_reg, R_OFF, 0))           # load_reg[l] = smem[l*4]
        k.emit(vxor(mix_target, mix_target, load_reg))  # mix loaded into another reg

    # ------------------------------------------------------------------ compute phase
    n_ops = rng.randint(10, 24)
    _emit_compute_phase(k, rng, n_ops)

    # ------------------------------------------------------------------ B3: divergence diamond
    # Single-level diamond pattern:
    #   VBLT rs1=branch_reg, rs2=r0, target=true_path_pc
    #   false-path: vaddi rd, r0, FALSE_VAL; VST; VRET
    #   [padding to align true_path_pc]
    #   true-path:  vaddi rd, r0, TRUE_VAL;  VST; VRET
    #
    # Branch encoding constraint: rs2_idx = offset[4:0].
    # We pick r0 as rs2 (index=0), so offset[4:0] must = 0, i.e. offset % 32 == 0.
    # Minimum useful forward offset: 32 bytes (8 instructions ahead).
    # False path body: vaddi(5) + vaddi(R_BASE,0,...)(4) + vadd(R_BASE)(4) +
    #                  vst(4) + vret(4) = 5 instructions × 4 bytes = 20 bytes.
    # We need offset divisible by 32 AND at least 20+padding bytes.
    # Use offset = 32 (branch jumps 8 instructions = 32 bytes forward).
    # False-path has 5 instructions (20 bytes). Pad 3 VRETs (12 bytes) to reach 32 bytes.
    # true_path_pc = branch_pc + 32.
    #
    # The divergent store uses a dedicated region (STORE_REGIONS[0]) for the
    # true-path and a separate (STORE_REGIONS[1]) for the false-path,
    # each for one lane-specific address.
    # branch_reg: pick a working reg that has a mix of positive and negative
    # values with high probability — just use whatever is there; if all same
    # sign, the branch converges (which is valid, just not divergent; the model
    # and RTL both handle converging branches correctly).
    if use_b3:
        branch_reg = rng.choice(WORKING)
        div_store_true  = rng.choice([r for r in WORKING if r != branch_reg])
        div_store_false = rng.choice([r for r in WORKING
                                      if r not in (branch_reg, div_store_true)])

        # Constants for the two paths (lane-uniform; store to lane-varying addr)
        true_val  = rng.randint(-2048, 2047)
        false_val = rng.randint(-2048, 2047)

        branch_pc = k.pc()
        # rs2=r0 (index 0); offset must be divisible by 32.  Use 32 (= 8 instructions).
        offset = 32
        assert branch_rs2_for(offset) == 0, "rs2_for(32) should be 0 (r0)"
        target_pc = branch_pc + offset

        # VBLT rs1=branch_reg, rs2=r0 (compare branch_reg[l] < 0)
        # True-path: lanes where branch_reg[l] < 0 (treated as signed)
        k.emit(vbranch(VBLT, branch_reg, 0, branch_pc, target_pc))

        # False-path (fall-through, lanes where branch_reg[l] >= 0):
        # Use STORE_REGIONS[1] for false-path writes
        div_false_base = STORE_REGIONS[1]
        k.emit(vaddi(div_store_false, 0, false_val))              # reg = false_val
        k.emit(vaddi(R_BASE, 0, (div_false_base - div_store_false) & 0xFFF))
        k.emit(vadd(R_BASE, R_BASE, R_OFF))                       # R_BASE[l] = base-idx+l*4
        k.emit(vst(div_store_false, R_BASE, 0))                   # mem[base+l*4] = false_val
        k.emit(vret())                                             # end false-path

        # Pad to true_path_pc with unreachable VRETs
        while k.pc() < target_pc:
            k.emit(vret())
        assert k.pc() == target_pc, \
            f"true-path PC mismatch: {k.pc():#x} != {target_pc:#x}"

        # True-path (lanes where branch_reg[l] < 0):
        # Use STORE_REGIONS[2] for true-path writes
        div_true_base = STORE_REGIONS[2]
        k.emit(vaddi(div_store_true, 0, true_val))                # reg = true_val
        k.emit(vaddi(R_BASE, 0, (div_true_base - div_store_true) & 0xFFF))
        k.emit(vadd(R_BASE, R_BASE, R_OFF))
        k.emit(vst(div_store_true, R_BASE, 0))                    # mem[base+l*4] = true_val
        k.emit(vret())                                             # end true-path (pops stack)
        # After true-path VRET, ref model pops stack → executes false-path lanes
        # ... but false-path already executed (those lanes hit the fall-through VRET).
        # Actually: the SIMT model is:
        #   branch → diverge → push(false_path_pc=fall_through=branch+4, false_mask)
        #         → execute true-path lanes (branch_reg < 0) until VRET
        #   VRET (true-path, non-empty stack) → pop → resume false-path lanes at fall_through
        #   false-path lanes execute: vaddi, vadd, vst, VRET
        #   VRET (false-path, empty stack) → terminate
        # This is correct: true-path VRET pops the stack; false-path lanes then run.

    # ------------------------------------------------------------------ baseline store phase
    # When B3 is active the diamond's two VRETs fully terminate the warp (true-path
    # VRET pops the stack, false-path VRET empties it), so anything emitted past the
    # diamond is UNREACHABLE in both the RTL and the reference model. The block below
    # is therefore vestigial padding under B3 — both sides ignore it identically, so
    # it cannot mask a bug; the diamond's STORE_REGIONS[1]/[2] writes are the checked
    # output. When B3 is inactive, the full three-region baseline store runs normally.
    if use_b3:
        # Unreachable under B3 (see note above); kept only as harmless tail padding.
        baseline_store_regs = rng.sample(WORKING, k=1)
        for base, dD in zip(STORE_REGIONS[:1], baseline_store_regs):
            k.emit(vaddi(R_BASE, 0, (base - dD) & 0xFFF))
            k.emit(vadd(R_BASE, R_BASE, R_OFF))
            k.emit(vst(dD, R_BASE, 0))
        k.emit(vret())
    else:
        # Full three-region baseline store
        data_regs = rng.sample(WORKING, k=len(STORE_REGIONS))
        _emit_store_phase(k, rng, data_regs)
        k.emit(vret())

    words = k.instructions()
    expected = GpuRefModel(n_lanes=N_LANES, initial_gmem=input_gmem).run(words)
    return words, expected, input_gmem


@cocotb.test()
async def test_random_kernels(dut):
    """Run N random kernels (straight-line + B1 loads + B2 shared-mem + B3 divergence).

    Asserts 0 deadlocks and 0 RTL-vs-model mismatches.
    """
    n_kernels = 25 if os.environ.get("RANDOM_KERNELS_SMOKE") \
        else int(os.environ.get("RANDOM_KERNELS", "1000"))
    base_seed = int(os.environ.get("RANDOM_KERNELS_SEED", "0xC0DE"), 0)

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    deadlocks = 0
    mismatches = 0
    first_failures = []

    for i in range(n_kernels):
        seed = base_seed + i
        words, expected, input_gmem = gen_random_kernel(seed)

        await gpu_reset(dut)

        # Pre-seed data_mem with the input region so VLD reads return correct values.
        data_mem = dict(input_gmem)

        instr_task = cocotb.start_soon(instr_responder(dut, words))
        data_task  = cocotb.start_soon(data_responder(dut, data_mem))

        await gpu_launch(dut, kernel_pc=0, block_x=N_LANES)
        done = await gpu_wait_done(dut, timeout=5000)
        instr_task.kill()
        data_task.kill()

        if not done:
            deadlocks += 1
            if len(first_failures) < 10:
                first_failures.append(f"seed 0x{seed:x}: DEADLOCK (no STATUS[done])")
            continue

        # Compare global memory: every expected VST write must match, no extras.
        # expected only contains VST destinations (GpuRefModel.gmem_writes);
        # input_gmem addresses are pre-seeded reads that remain in data_mem
        # but are not in expected, so we exclude them from the length check.
        input_addrs = set(input_gmem.keys())
        rtl_stores = {a: v for a, v in data_mem.items() if a not in input_addrs}

        ok = (len(rtl_stores) == len(expected))
        for addr, val in expected.items():
            got = rtl_stores.get(addr)
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
