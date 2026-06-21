/* conflict.c — Set-conflict (way-pressure) benchmark for Phase 5 M10c-1.
 *
 * PURPOSE
 *   sweep.c used a 256 B stride which advances the set index by 16 sets per
 *   access — consecutive addresses never alias the same cache set, so zero
 *   conflict misses occurred and the 2-way D$ showed no benefit.  This
 *   benchmark deliberately creates set conflicts: all K accessed cache lines
 *   map to EXACTLY the same cache set, varying K from 1 to 16.
 *
 * CACHE GEOMETRY (rtl/mem/rv32i_cache_pkg.sv)
 *   Line  = 16 B (4 words)
 *   WAYS=1 (direct-mapped): 256 sets; set_index = addr[11:4]
 *   WAYS=2 (2-way):         128 sets; set_index = addr[10:4]
 *   Address stride for same-set aliasing:
 *     WAYS=1: 256 sets × 16 B = 4096 B (= 0x1000)
 *     WAYS=2: 128 sets × 16 B = 2048 B; 4096 B is also congruent (mod 2048 = 0)
 *   => 4096 B stride keeps every access in the SAME set for BOTH configurations.
 *      This lets one binary stress both WAYS=1 and WAYS=2 without recompiling.
 *
 * BENCHMARK DESIGN
 *   K distinct cache lines at addresses  base + k*4096  (k = 0 .. K-1).
 *   For each K, the inner loop visits all K lines ROUNDS times, reading
 *   one word from each (the first word of its 16-byte cache line).
 *   Structure:
 *     1. Prime pass (untimed) — one full K×ROUNDS traversal to reach
 *        steady state (or confirm thrash).
 *     2. Measured pass (timed) — another K×ROUNDS traversal bracketed
 *        by bench_snapshot() before/after.
 *   Checksum: accumulate every read into acc; pass as bench_report()
 *   checksum to defeat -O2 dead-code elimination.
 *
 * EXPECTED BEHAVIOUR
 *   K=1 : single line, never evicted → 0 D$-misses in measured pass (both ways)
 *   K=2 : WAYS=1 thrashes (evict-reload every access) → ~2×ROUNDS misses
 *          WAYS=2 holds both lines  → ~0 misses (clean discriminator)
 *   K=4 : WAYS=1 thrashes; WAYS=2 thrashes (only 2 slots per set) → both high
 *   K≥4 : both configurations saturate at ~K×ROUNDS misses (1/access)
 *
 * ID ENCODING  (passed as `id` to bench_report)
 *   id = K   (K in {1, 2, 4, 8, 16})
 *   The harness reads bench_report slot[0] low-byte = id & 0xFF = K directly.
 *   Example: id=2 → K=2 (the clean 1-way vs 2-way discriminator point).
 *
 * MEMORY FOOTPRINT
 *   Base address: CONFLICT_BASE = 0x0000_3100 (well above .bss / .data)
 *   K=16 uses lines at offsets 0×4096 .. 15×4096 = 0x0 .. 0xF000
 *   Highest address accessed: 0x3100 + 0xF000 = 0x12100 < 0x41C00 (stack top)
 *   No collision with code, .bss, stack, or bench scratch region.
 *   (Exact placement is verified post-build by checking build/<p>.sym.)
 *
 * TOTAL ACCESSES (estimate for sim-time sanity)
 *   ROUNDS = 256; K values: 1, 2, 4, 8, 16
 *   Prime + measured per K:  2 × K × ROUNDS
 *   Sum: 2 × (1+2+4+8+16) × 256 = 2 × 31 × 256 = 15 872 word loads
 *   At ~5 instructions/load (load + add + branch + loop overhead):
 *     ≈ 79 000 instructions total
 *   At 2–4 CPI (conflict-miss heavy cases):
 *     ≈ 160 000 – 320 000 cycles — well inside 2 M-cycle budget.
 *   5 bench_report() calls → 5 scratch slots used (max 31, no overflow).
 *
 * HARNESS DECODE
 *   count = scratch[0]  (should be 5)
 *   slot[i].id & 0xFF   = K for that record
 *   slot[i].dcache_miss = D$-miss delta across the measured pass
 *   D$-miss rate per access = dcache_miss / (K * ROUNDS)
 */

#include "bench.h"

/* 4096 B stride: same set in both WAYS=1 (256 sets) and WAYS=2 (128 sets).
 * WAYS=1: stride mod (256×16)=4096 → same set index bits[11:4].
 * WAYS=2: stride mod (128×16)=2048; 4096 mod 2048 = 0 → same set index bits[10:4]. */
#define CONFLICT_STRIDE_B   4096u           /* bytes between congruent lines */
#define CONFLICT_STRIDE_W   (CONFLICT_STRIDE_B / 4u)   /* words (1024) */

/* Base must be 16-byte aligned and safely above .bss.
 * sweep's BUF_WORDS=8192 (32 KB) puts __bss_end at ~0xA320 on this branch.
 * CONFLICT_BASE = 0x3100 is safely above all code+data symbols — confirmed
 * post-build by checking build/conflict.sym that no symbol maps to 0x3100..0x12100. */
#define CONFLICT_BASE       0x00003100u     /* start of conflict probe region */

/* Number of full K-line cycles per pass (prime + measured each).
 * ROUNDS=256: at K=16 → 16×256=4096 accesses per pass; total ≈ 16k accesses. */
#define ROUNDS              256u

/* K values to test: 1, 2, 4, 8, 16.
 * K=2 is the KEY discriminator: direct-mapped thrashes, 2-way holds. */
static const uint32_t K_VALS[] = { 1u, 2u, 4u, 8u, 16u };
#define N_K_VALS            (sizeof(K_VALS) / sizeof(K_VALS[0]))

/* Pointers to the K probe words (first word of each 4096-B-aligned line).
 * Built once in init_probes(); reused across all K sweeps. */
static volatile uint32_t *probes[16];

/* -----------------------------------------------------------------------
 * init_probes — initialise probe pointers and write a non-zero sentinel
 * into each line so loads return real data (defeat zero-page shortcuts).
 * This runs outside any timed region; the stores are not measured.
 * ----------------------------------------------------------------------- */
static void init_probes(void)
{
    uint32_t k;
    for (k = 0u; k < 16u; k++) {
        probes[k] = (volatile uint32_t *)(CONFLICT_BASE + k * CONFLICT_STRIDE_B);
        /* Write a distinct non-zero value so every load reads real data.
         * The write itself is uncached (or primed by crt0 .bss zero-init);
         * after this loop the cache line for each probe may or may not be
         * present — the prime pass will resolve that. */
        *probes[k] = 0xC0FF1E00u + k;
    }
}

/* -----------------------------------------------------------------------
 * do_pass — run one pass of K lines × ROUNDS cycles.
 * Returns accumulated checksum (passed to bench_report to guard vs DCE).
 * ----------------------------------------------------------------------- */
static uint32_t do_pass(uint32_t k_max)
{
    uint32_t acc = 0u;
    uint32_t r, k;
    for (r = 0u; r < ROUNDS; r++) {
        for (k = 0u; k < k_max; k++) {
            acc += *probes[k];
        }
    }
    return acc;
}

/* -----------------------------------------------------------------------
 * main
 * ----------------------------------------------------------------------- */
int main(void)
{
    bench_snap_t a, b;
    uint32_t ki;

    bench_init();       /* zero scratch count-word before first bench_report() */
    init_probes();      /* set up probe addresses + write sentinel values */

    for (ki = 0u; ki < N_K_VALS; ki++) {
        uint32_t K = K_VALS[ki];
        uint32_t cs;
        uint32_t prime_acc;

        /* Prime pass (untimed): warm the cache to steady state. */
        prime_acc = do_pass(K);

        /* Measured pass: bracketed by bench_snapshot(). */
        bench_snapshot(&a);
        cs = do_pass(K);
        bench_snapshot(&b);

        /* Fold prime_acc into checksum so compiler cannot delete the prime loop. */
        bench_report((uint32_t)K, cs ^ prime_acc, &a, &b);
    }

    /* Return 0; __result written by crt0 halt sequence from a0. */
    return 0;
}
