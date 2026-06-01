# Phase 4 Random-Kernel Regression

Sign-off step 5 of `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` §9.

## Results

### Original run (2026-05-23) — straight-line only

| Metric | Value |
| :----- | :---- |
| Kernels run | **1000** |
| Deadlocks | **0** |
| RTL-vs-reference mismatches | **0** |
| Status | PASS |
| Scope | Straight-line ALU + global stores only |

### Broadened run (2026-06-01) — B1 loads + B2 shared-mem + B3 divergence

| Metric | Value |
| :----- | :---- |
| Kernels run (smoke) | **25** |
| Kernels run (full) | **1000** |
| Deadlocks | **0** |
| RTL-vs-reference mismatches | **0** |
| Status | PASS (`TESTS=1 PASS=1 FAIL=0 SKIP=0`) |
| Sim time | ~3 355 321 ns |
| Wall time | ~99 s (Verilator, tracing disabled) |
| New scope | + global loads (VLD), shared-memory round-trip (VSTS/VSYNC/VLDS), single-level divergence diamond (VBLT) |

`gpu_random_smoke` (25 kernels): also PASS, now included in `gpu_all` rollup.

## How to run

```bash
# From repo root, inside the LibreLane nix-shell:
make -C sim gpu_random                         # 1000 kernels (default)
make -C sim gpu_random_smoke                   # 25-kernel smoke (also runs inside gpu_all)
RANDOM_KERNELS=5000 make -C sim gpu_random     # custom count
RANDOM_KERNELS_SEED=0x1234 make -C sim gpu_random  # different base seed
RANDOM_KERNELS_SEED=0xBAD0 RANDOM_KERNELS=1 make -C sim gpu_random  # reproduce a failing seed

# Full rollup (unit + kernels + handoff + random smoke):
make -C sim gpu_all

# Nightly regression (CPU + cache + GPU + CPU/GPU random):
make -C sim regression_full
```

`gpu_random` sets `EXTRA_ARGS=""` to disable Verilator `--trace`, so no multi-GB `dump.vcd`.

## Rollup integration

| Target | Contains gpu_random? | Count |
| :----- | :------------------- | :---- |
| `gpu_random_smoke` | yes (25 kernels) | smoke |
| `gpu_all` | yes (via `gpu_random_smoke`) | 25 |
| `regression_full` | yes (via `gpu_all` + explicit 1000) | 25 + 1000 |

`regression_full` runs `gpu_all` (which includes the 25-kernel smoke) and then
`gpu_random` (1000 kernels) separately with its own `results.xml` failure guard.

## Methodology

- **DUT:** `gpu_top` (full GPU: command queue, scheduler, compute unit, regfile,
  ALU, memory unit + coalescer, shared memory).
- **Reference model:** `tb/cocotb/gpu/gpu_ref_model.py` (`GpuRefModel`), a Python
  interpreter that matches the actual RTL/`gpu_asm` opcode encoding (`gpu_pkg.sv`)
  and `vector_alu.sv` semantics exactly (VMUL lower-32, VSRL logical, VSRA
  arithmetic, sign-extended 12-bit immediates, r0 hardwired).
  As of 2026-06-01 the model also implements:
  - Single-level SIMT divergence stack (`VBEQ/VBNE/VBLT/VBGE`, `VJMP`): per-lane
    active mask, taken/not-taken split, reconvergence via stack pop on VRET.
    Semantics validated against `test_divergence.py` and the `gpu_compute_unit.sv`
    divergence stack contract.
  - `initial_gmem` parameter: pre-seeds global memory before execution so VLD
    reads return deterministic values. The model returns `gmem_writes` (VST
    destinations only), not the pre-seeded read-only input entries.
- **Generator** (`test_random_kernels.py`, seeded per kernel for reproducibility):
  each kernel is a single 8-lane warp with these building blocks applied
  probabilistically:

### Kernel building blocks

| Block | Probability | What it exercises |
| :---- | :---------- | :---------------- |
| Straight-line ALU + global stores | always | ALU R/I ops, regfile, global store (memory unit + coalescer + AXI), VSYNC (NOP) |
| **B1 global loads** | 40% | VLD from `INPUT_REGION` (0x100), address calculation, feed loaded values into compute |
| **B2 shared memory** | 40% | VSTS → VSYNC barrier → VLDS round-trip; smem bank addressing; feed back into compute + VST |
| **B3 divergence diamond** | 35% | VBLT with per-lane signed compare, single-level SIMT push/pop, masked VST on each path |

A single kernel may receive 0, 1, 2, or all 3 extensions simultaneously.

### Address layout

```text
Global address space:
0x000–0x0FF : (unused — VRET fallback returns 0x3F from instr_responder)
0x100–0x11F : INPUT_REGION — 8 words (one per lane); pre-seeded; read-only VLD source
0x200–0x23F : STORE_REGIONS[0] — baseline store region (also B3 unreachable-tail store)
0x240–0x27F : STORE_REGIONS[1] — baseline store, or B3 false-path diamond store
0x280–0x2BF : STORE_REGIONS[2] — baseline store, or B3 true-path diamond store

Shared address space (separate from global):
0x000–0x1FF : SMEM (shared scratchpad) — 512 B window used (physical 16 KB / 32
              banks); lane writes smem[lane*4]
```

Regions are non-overlapping. Store lane stride is 4 bytes; 8 lanes = 32 bytes per
region, well within the 64-byte region spacing.

### Scoreboard

After each kernel:
1. `gpu_wait_done` (timeout=5000 cycles) detects deadlocks.
2. `data_mem` (AXI responder dict) is compared against `expected = GpuRefModel(...).run(words)`:
   - `expected` = `gmem_writes` only (VST destinations; no pre-seeded read entries).
   - `rtl_stores` = `data_mem` minus `input_gmem` addresses (pre-seeded reads
     are not RTL writes).
   - Both sets must have equal cardinality and matching values at every address.

### Divergence diamond shape

The B3 generator always emits a provably-reconverging, provably-terminating,
single-level diamond:

```text
VBLT rs1=working_reg, rs2=r0, target=true_path   ; push(false_path_pc, not_taken_mask)
; fall-through (false-path, lanes where working_reg[l] >= 0):
  VADDI  div_reg, r0, false_val
  VADDI  R_BASE, r0, (STORE_REGIONS[1] - div_reg_idx)
  VADD   R_BASE, R_BASE, R_OFF
  VST    div_reg, R_BASE, 0                        ; mem[STORE_REGIONS[1] + l*4] = false_val
  VRET                                              ; end false-path
; [pad VRETs to align true_path_pc to branch_pc+32]
true_path:
  VADDI  div_reg, r0, true_val
  VADDI  R_BASE, r0, (STORE_REGIONS[2] - div_reg_idx)
  VADD   R_BASE, R_BASE, R_OFF
  VST    div_reg, R_BASE, 0                        ; mem[STORE_REGIONS[2] + l*4] = true_val
  VRET                                              ; pop → execute false-path lanes → VRET
```

Branch offset = 32 bytes (multiple of 32, so `rs2=r0` index=0 satisfies the
branch encoding constraint `offset[4:0] == rs2_index`). Branch condition
`VBLT rs1, rs2=r0, ...` compares signed `rs1[l] < 0`, which splits the 8 lanes
based on the sign of whatever accumulated value is in `rs1`. If all lanes happen
to agree (all same sign after the compute phase), the branch converges — the model
and RTL both handle converging branches correctly.

## Scope rationale

| Feature | Covered by |
| :------ | :--------- |
| ALU R-type (VADD/VSUB/VMUL/VAND/VOR/VXOR/VSLL/VSRL/VSRA) | random kernel (always) |
| ALU I-type (VADDI/VANDI/VORI/VXORI) | random kernel (always) |
| VMOV_TID_X | random kernel (always, init) |
| Global store (VST) via AXI4 + coalescer | random kernel (always) |
| VSYNC (single-warp NOP) | random kernel (always, low probability) |
| Global load (VLD) | B1 (40% probability per kernel) |
| Shared-memory round-trip (VSTS/VLDS) | B2 (40% probability per kernel) |
| Single-level divergence (VBLT, SIMT stack) | B3 (35% probability per kernel) |
| Multi-level divergence, loops, backward branches | directed tests only (`kernel_divergence_basic`, `test_divergence.py`) — intentionally excluded from random generator |
| Multi-warp scheduling | directed tests (`test_warp_scheduler.py`, `kernel_sync`) |

Restricting the random space to the exactly-modeled subset keeps every mismatch a
genuine RTL datapath bug rather than a generator/model artifact, while the 1000-seed
campaign exercises broad ALU/regfile/load/store/smem/divergence combinations.

## Reproducing a specific seed

```bash
RANDOM_KERNELS_SEED=0xBAD0 RANDOM_KERNELS=1 make -C sim gpu_random
```

The first 10 failing seeds are also logged as `ERROR` lines in the cocotb output,
so reproduction does not require external tracking.
