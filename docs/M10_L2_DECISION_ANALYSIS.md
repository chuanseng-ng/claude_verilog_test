# Phase 5 M10 — L2 Cache Decision Analysis

**Status:** DECIDED 2026-06-21 — **L2 deferred; evaluate a 2-way set-associative D$ first** (human architectural call). L2 GO/NO-GO is re-decided after the 2-way re-benchmark. M11 floorplan stays L2-free pending that result.
**Date:** 2026-06-21
**Gate criterion** (`docs/PHASE5_SOC_INTEGRATION_PLAN.md` M10; `CLAUDE.md` locked-decision #4):
> Add `rtl/mem/l2_cache.sv` **only if** Phase 5 benchmarking shows L1 miss rates are a bottleneck. Document the decision either way.

## 1. What was measured

M9 recorded cycle counts but not miss rates. M10 built a real RISC-V bare-metal
benchmark path (`sw/bench/`, riscv32-none-elf-gcc) and a SoC cocotb harness
(`tb/cocotb/soc/test_l2_bench.py`) that runs C on the full `soc_top`, dumps the
M7 hardware perf counters (`mhpmcounter3`=I$ miss, `mhpmcounter4`=D$ miss,
`mcycle`, `minstret`) through a flushed scratch block, and computes miss rates.

The decision workload is `sweep.c`: a working-set sweep (512 B → 32 KB) in two
access patterns — **SEQ** (sequential) and **STRIDE** (256 B stride, defeats
spatial locality) — each warmed by a prime pass then measured at steady state.
L1 D$ = 4 KB, direct-mapped, 16 B lines.

Raw data: [`tb/cocotb/soc/l2_bench_results.md`](../tb/cocotb/soc/l2_bench_results.md).

## 2. Result — a hard capacity cliff at the 4 KB L1 boundary

| working set | SEQ D$miss/1k-instr | STRIDE D$miss/1k-instr |
| ----------: | ------------------: | ---------------------: |
| ≤ 4 KB      | **0.00**            | **0.00**               |
| 8 KB        | **49.96**           | **189.35**             |
| 16 KB       | 49.98               | 194.53                 |
| 32 KB       | 49.99               | 197.23                 |

- **Below/at 4 KB:** zero D$ misses — the working set fits entirely in L1.
- **First size above L1 (8 KB):** miss rate snaps to ~50/1k-instr (SEQ) and
  ~190/1k-instr (STRIDE) and then **plateaus** — a textbook capacity wall, not a
  gradual roll-off.
- **STRIDE ≈ 3.8× worse than SEQ** above the cliff — classic direct-mapped
  conflict/eviction behavior.
- **I$ misses ≈ 0** for all sizes ≥ 1 KB — the hot loops fit the 4 KB I$; the
  512 B/SEQ I$ figure is just cold first-touch. **I$ is not a concern.**
- Corroboration: a 48×48 int `matmul` (27 KB working set, 6.75× L1) showed
  ~50 D$miss/1k-instr before its software-multiply runtime made the sim
  intractable — consistent with the SEQ plateau.

## 3. Interpretation

**What the data proves:** the L1 D$ has a sharp 4 KB capacity boundary, and any
data working set above it sustains a high miss rate to SRAM (full AXI4 burst
penalty per miss). A 16–32 KB L2 would absorb the 8 KB / 16 KB cases entirely and
roughly halve the 32 KB SEQ miss stream.

**What the data does NOT prove:** that *representative* SoC CPU workloads actually
operate above 4 KB with reuse. `sweep` is a synthetic adversary built to defeat the
cache — it measures the cache's limit, not that real firmware reaches it. The
representative integer workloads (Dhrystone/CoreMark) were not run to completion
(no hardware multiply → software `__mulsi3` makes them very slow in RTL sim).

**Architectural context** weighs against a reflexive "yes":
- This CPU is the **control/orchestration core** of a GPU-governed SoC (SoC fmax
  ≈ 571 MHz, GPU-bound). Bulk data-parallel work runs on the **GPU**, which has its
  own 16 KB shared memory + memory coalescer — it does not lean on the CPU L1.
- An L2 adds latency, area, and an **extra hard macro to the M11 floorplan**
  (changing area/PDN/timing scope), against the conservative Phase 5 locked posture
  (decisions #1/#4/#5: add capacity only when a real bottleneck is proven).
- The STRIDE ≈ 4× penalty is a **conflict-miss** signature. If a cheaper lever is
  wanted first, a **2-way set-associative D$** (CLAUDE.md decision #2) attacks the
  conflict component directly and is far smaller than an L2.

## 4. Recommendation

**Decision (2026-06-21): defer L2; evaluate a 2-way set-associative D$ first.**

L2 is not added in the Phase 5 base scope on this evidence alone. Instead, attack
the cheaper, more-targeted lever first: the STRIDE ≈ 4× penalty is a **conflict-miss**
signature (CLAUDE.md decision #2's trigger — "measurable conflict-miss impact" — is
now met). A 2-way set-associative D$ is far smaller than an L2 and addresses the
conflict component directly.

**Experiment plan (M10b):**
1. Prototype a 2-way set-associative D$ (`rv32i_dcache.sv`), parameterized ways,
   **same 4 KB total capacity** (128 sets × 2 ways × 16 B) so the change isolates
   *conflict*-miss reduction from capacity (capacity is held constant).
2. Re-run the same `sweep` benchmark and compare against the direct-mapped baseline
   in §2. Expected: SEQ plateau (~50/kI ≥8 KB) is **capacity** — associativity will
   NOT move it; STRIDE (~190/kI) should drop toward SEQ if conflicts dominate it.
3. Re-decide L2 with that data: if 2-way collapses STRIDE and the residual SEQ
   capacity miss is deemed acceptable for control-plane firmware → no L2. If the SEQ
   capacity wall is judged a real bottleneck for on-core workloads → escalate to L2.

This keeps the M11 floorplan L2-free for now; the 2-way D$ (if adopted) is a
modification of the existing L1, not a new macro.

> Direct-mapped remains the committed default until the 2-way experiment justifies a
> change (Phase 3 locked decision #2). The prototype runs on an experiment branch.

## 5. 2-Way D$ Re-benchmark (M10b-2, 2026-06-21)

**Correctness gate (Step 1):** RTL fix `fr_null_20260621_125041_00` confirmed on
branch `experiment/dcache-2way` (commit `aba0c18` — writeback buffer now reads
`cand_vw`, not stale `victim_way_q`).
- `make -C sim dcache`: TESTS=8 PASS=8 FAIL=0 (including `test_dirty_eviction_writeback`)
- `make -C sim soc_coherency`: TESTS=3 PASS=3 FAIL=0

**Benchmark (Step 2):** same `sweep` firmware, same `test_l2_bench.py` harness,
same `SRAM_MEM_WORDS=65536`.  Cache: `DCACHE_WAYS=2`, 128 sets × 2 ways × 16 B = 4 KB.

Raw data: [`tb/cocotb/soc/l2_bench_results_2way.md`](../tb/cocotb/soc/l2_bench_results_2way.md).

### 5.1 Comparison table — direct-mapped vs 2-way (same 4 KB capacity)

| size (B) | 1-way SEQ /kI | 2-way SEQ /kI | 1-way STR /kI | 2-way STR /kI | STRIDE change |
| -------: | ------------: | ------------: | ------------: | ------------: | :------------ |
| 512      | 0.00          | 0.00          | 0.00          | 0.00          | no change     |
| 1024     | 0.00          | 0.00          | 0.00          | 0.00          | no change     |
| 2048     | 0.00          | 0.00          | 0.00          | 0.00          | no change     |
| 4096     | 0.00          | 0.00          | 0.00          | 0.00          | no change     |
| 8192     | 49.96         | 49.96         | 189.35        | 189.35        | 0% reduction  |
| 16384    | 49.98         | 49.98         | 194.53        | 194.53        | 0% reduction  |
| 32768    | 49.99         | 49.99         | 197.23        | 197.23        | 0% reduction  |

### 5.2 Capacity vs conflict decomposition

The two benchmarks are **bit-identical**.  This outcome is physically expected once
the STRIDE access geometry is analyzed:

- The `sweep` firmware uses `STRIDE_STEP = 64 words = 256 bytes`.
- The D$ line size is 16 bytes, and the cache has 256 sets (WAYS=1) or 128 sets (WAYS=2).
- A 256 B stride increments the cache-set index by 256/16 = 16 sets (WAYS=1) or
  8 sets (WAYS=2).  Each consecutive STRIDE access maps to a *different set* in
  both configurations.
- Because no two STRIDE accesses map to the same set, **there is no set aliasing**,
  and therefore **no conflict misses** — only capacity misses (the working set
  exceeds 4 KB total cache space).
- 2-way associativity prevents evictions when two addresses map to the *same set*
  with different tags.  When no two live accesses share a set (as here), extra
  ways provide no benefit.

**Conclusion:** the STRIDE ≈ 3.8× penalty over SEQ measured in the direct-mapped
baseline is a **capacity miss phenomenon, not a conflict-miss phenomenon**.  The
STRIDE pattern in this benchmark always evicts by capacity; reducing the effective
number of sets from 256 to 128 (the price of adding a second way at constant
capacity) does not change the miss rate because no aliasing was occurring in the
first place.

### 5.3 Residual capacity wall

Both WAYS=1 and WAYS=2 sustain ~50 D$miss/kI (SEQ) for working sets ≥ 8 KB.
This is a pure capacity wall: once the working set exceeds 4 KB, every line
brought in evicts a line that will be needed again.  The only remedy is more
cache capacity (a larger L1 or an L2), not more associativity.

The STRIDE ceiling (~190–197/kI) is similarly capacity-driven.  With a 256 B
stride and a 16 B line, each access is guaranteed cold regardless of cache size
below the full working-set footprint.  Neither associativity nor an L2 would
help STRIDE unless the L2 were large enough to hold the entire working set.

### 5.4 Implication for L2

- **2-way D$ at same 4 KB capacity: no measurable miss-rate benefit** for the
  `sweep` workload (which uses non-aliasing large strides).
- **Residual capacity wall above 4 KB is entirely a capacity problem**, addressable
  only by a larger cache (a bigger L1 or an L2).
- **An L2 of 16–32 KB would absorb the 8–16 KB working-set cases** (SEQ ~50/kI
  would drop to ~0; STRIDE would drop only if the L2 is large enough to hold the
  strided footprint — typically not for STRIDE_STEP << working_set).
- Whether the capacity wall represents a *real bottleneck* for the SoC's actual
  control-plane firmware remains unproven (see §3 architectural context).

> **L2 GO/NO-GO decision left to the human** on this data.  The 2-way experiment
> confirms: conflict misses are not the driver for this workload; any remaining
> miss-rate concern is purely capacity, and only an L2 (or larger L1) would address it.

## 6. Reproduce

```bash
# Direct-mapped baseline (DCACHE_WAYS=1 in rv32i_cache_pkg.sv)
nix develop .#bench --command make -C sw/bench clean all   # build benchmarks
cd sim && make l2_bench                                      # writes l2_bench_results.md

# 2-way re-benchmark (branch experiment/dcache-2way, DCACHE_WAYS=2)
git checkout experiment/dcache-2way
cd sim && make l2_bench                                      # writes l2_bench_results_2way.md
```

## 7. Conflict-stress benchmark (M10c, 2026-06-21)

**Purpose:** M10b's `sweep` benchmark used a 256 B stride which never aliases the same
cache set — so it tested *capacity* misses only.  To determine whether **conflict misses**
can be relevant for real SoC workloads, M10c (`conflict.c`) forces true set-aliasing:
all K probe addresses are at 4096 B intervals (same D$ set for both WAYS=1 and WAYS=2).
K ∈ {1, 2, 4, 8, 16}.  K=2 is the key discriminator.

### 7.1 Results — D$miss/kI by K-value

Branch `experiment/dcache-2way`.  Same firmware binary (`conflict.hex`) for both WAYS.
ROUNDS=256 measured-pass accesses per K-value.

| K | WAYS=1 D$miss/kI | WAYS=2 D$miss/kI | WAYS=1 miss/access | WAYS=2 miss/access | verdict |
| -: | ---------------: | ---------------: | -----------------: | -----------------: | ------- |
| 1  | **0.00**          | **0.00**          | 0.0000              | 0.0000              | fits both (no conflict) |
| 2  | **153.48**        | **0.00**          | **1.0000**          | **0.0000**          | **KEY: 1-way thrashes, 2-way holds** |
| 4  | 173.68            | 173.68            | 1.0000              | 1.0000              | both thrash (K > 2 ways) |
| 8  | 185.91            | 185.91            | 1.0000              | 1.0000              | both thrash |
| 16 | 192.70            | 192.70            | 1.0000              | 1.0000              | both thrash |

Raw data: [`tb/cocotb/soc/conflict_results_1way.md`](../tb/cocotb/soc/conflict_results_1way.md),
[`conflict_results_2way.md`](../tb/cocotb/soc/conflict_results_2way.md).

### 7.2 K=2 headline numbers

| config | ΔD$miss | D$miss/access | D$miss/kI | cycles (measured pass) |
| ------ | ------: | ------------: | --------: | ---------------------: |
| WAYS=1 | 512     | **1.0000**    | 153.48    | 20 749                 |
| WAYS=2 | 0       | **0.0000**    | 0.00      | 16 141                 |

**K=2 WAYS=1:** every access evicts the other line → 1.0000 miss/access. The measured
pass counts exactly 512 = 2 × ROUNDS misses — one miss for each of the 512 accesses.
**K=2 WAYS=2:** both lines reside simultaneously in the 2-way LRU set → 0 misses.
Cycle counts: 20 749 (1-way, stall-heavy) vs 16 141 (2-way, no stalls) — a 22% speedup
for the K=2 conflict-heavy access pattern.

The 2-way LRU implementation (cand_vw / lru_array fix from `fr_null_20260621_125041_00`)
is **confirmed functionally correct**.

### 7.3 Interpretation

**What the conflict-stress benchmark proves:**

1. **2-way D$ eliminates conflict misses completely when K=2** — the LRU policy works
   as designed; the cand_vw RTL fix is confirmed.
2. **For K>2, both configs thrash equally** — a 2-way cache cannot hold K>2 aliased
   lines any more than a 1-way cache can hold K>1.  Adding associativity beyond 2 would
   help K=3 but not K≥4.
3. **The discriminating question** is whether real SoC firmware has hot data structures
   that map exactly 2 or more congruent lines to the same cache set.  For this CPU
   (RV32I control core, not the data-parallel GPU):
   - Small scalar kernels (boot, peripheral drivers, interrupt handlers): working set
     typically < 512 B → all in L1, zero misses regardless of WAYS.
   - `matmul`-class loops with two large arrays: both arrays may alias the same sets,
     making this a real concern.  But the GPU handles bulk data-parallel work.
   - Memory-scanning loops (boot ROM copy, DMA setup): stride-based, not aliasing.

4. **The conflict-miss problem is real but workload-conditional.** The experiment
   proves 2-way works; it does not prove the workload reaches K=2 aliasing in practice.

### 7.4 Final architecture observation

| axis | finding |
| ---- | ------- |
| 2-way eliminates conflict misses (K=2) | CONFIRMED — 1.0000 → 0.0000 miss/access |
| Capacity wall (working set > 4 KB) | UNCHANGED — requires L2 or larger L1 |
| K≥4 conflict (>2 aliased hot lines) | UNSOLVED by 2-way; needs ≥4-way or L2 |
| Real workload set aliasing | UNPROVEN — sweep/conflict are synthetic |

> **GO/NO-GO for 2-way promotion and/or L2 is left to the human.**
> The conflict-stress result closes the open measurement question: **2-way does
> eliminate true conflict misses when they exist**.  Whether the SoC CPU firmware
> encounters them is an architectural-judgement call, not a simulation question.

## 8. Reproduce (M10c)

```bash
# On branch experiment/dcache-2way (DCACHE_WAYS=2 active):
# conflict.hex is already built (sw/bench/build/conflict.hex, commit 87c16d1).
# Do NOT need to rebuild firmware — same binary for both WAYS.

# WAYS=1 run: edit rv32i_cache_pkg.sv to DCACHE_WAYS=1 then:
cd sim && make conflict_bench_1way     # → tb/cocotb/soc/conflict_results_1way.md

# WAYS=2 run: edit rv32i_cache_pkg.sv to DCACHE_WAYS=2 then:
cd sim && make conflict_bench_2way     # → tb/cocotb/soc/conflict_results_2way.md
```
