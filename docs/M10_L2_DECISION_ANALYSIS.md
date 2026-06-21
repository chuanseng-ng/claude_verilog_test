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

## 5. Reproduce

```bash
nix develop .#bench --command make -C sw/bench clean all   # build benchmarks
cd sim && make l2_bench                                      # run hello+sweep, writes l2_bench_results.md
```
