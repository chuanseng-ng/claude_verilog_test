# Phase 4 Random-Kernel Regression

Sign-off step 5 of `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` §9.

## Result (2026-05-23)

| Metric | Value |
| :----- | :---- |
| Kernels run | **1000** |
| Deadlocks | **0** |
| RTL-vs-reference mismatches | **0** |
| Status | ✅ PASS (`TESTS=1 PASS=1 FAIL=0`) |
| Sim time | 2,944,681 ns |
| Wall time | ~88 s (Verilator, tracing disabled) |

Smoke configuration (25 kernels) also passes: 0 deadlocks, 0 mismatches.

## How to run

```bash
# from repo root, inside the LibreLane nix-shell
make -C sim gpu_random                    # 1000 kernels (default)
RANDOM_KERNELS=5000 make -C sim gpu_random # custom count
RANDOM_KERNELS_SMOKE=1 make -C sim gpu_random  # 25-kernel smoke
RANDOM_KERNELS_SEED=0x1234 make -C sim gpu_random  # change base seed
```

The `gpu_random` target sets `EXTRA_ARGS=""` to disable Verilator `--trace`, so
the run does not produce a multi-GB `dump.vcd`.

## Methodology

- **DUT:** `gpu_top` (full GPU: command queue, scheduler, compute unit, regfile,
  ALU, memory unit + coalescer, shared memory).
- **Reference:** `tb/cocotb/gpu/gpu_ref_model.py` (`GpuRefModel`), a Python
  interpreter that matches the actual RTL/`gpu_asm` opcode encoding
  (`gpu_pkg.sv`) and `vector_alu.sv` semantics exactly (VMUL lower-32, VSRL
  logical, VSRA arithmetic, sign-extended 12-bit immediates, r0 hardwired).
  - **Note:** the older `tb/models/gpu_kernel_model.py` uses a *different*,
    RISC-V-style opcode encoding and has no shared-memory ops, so it is **not**
    the scoreboard here. `GpuRefModel` was written specifically to match the
    Phase 4 RTL encoding.
- **Generator** (`test_random_kernels.py`, seeded per kernel for
  reproducibility): each kernel is a single 8-lane warp, straight-line:
  - init: `r1 = tid.x`, `r2 = 2`, `r3 = l*4`; working regs r5..r15 seeded with
    random immediates;
  - compute: 10–24 random R-type / I-type ALU ops (VADD/VSUB/VMUL/VAND/VOR/
    VXOR/VSLL/VSRL/VSRA/VADDI/VANDI/VORI/VXORI) plus occasional VSYNC;
  - store: 3 distinct data registers stored to 3 distinct global regions
    (64 B apart) so lane `l` writes `region_base + l*4`;
  - `VRET`.
- **Check:** after each kernel, the global memory recorded by the AXI4 data
  responder must equal `GpuRefModel`'s predicted global memory exactly (every
  address, no extra writes). A per-kernel watchdog (`gpu_wait_done` timeout)
  flags any kernel that never asserts `STATUS[done]` as a deadlock.

## Scope and rationale

The random generator emits straight-line kernels exercising the ALU, register
file, VMOV special registers, the global-store path (memory unit + coalescer +
AXI), and the VSYNC barrier (single-warp no-op). **Divergent branches, global
loads, and shared memory are intentionally out of scope** for the random
generator — they are covered by the directed kernel tests
(`kernel_divergence_basic`, `kernel_memory_coalesce`, `kernel_dot_product`,
`kernel_shared_mem_pingpong`, `kernel_sync`). Restricting the random space to
the exactly-modeled subset keeps every mismatch a genuine datapath bug rather
than a generator/model artifact, while still validating broad ALU/regfile/store
behavior across 1000 independent random programs.
