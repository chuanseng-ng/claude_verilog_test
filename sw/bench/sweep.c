/* sweep.c — Working-set sweep benchmark for Phase 5 M10 L2-cache decision.
 *
 * Traverses a single 32 KB buffer with access regions of increasing size to
 * expose the 4 KB L1 D-cache capacity cliff.  For each (size, pattern) pair
 * the code runs one untimed prime pass (warms the cache) followed by one
 * timed measured pass (bench_snapshot before/after) that the cocotb harness
 * back-door-reads to plot steady-state D$-miss-rate vs working-set size.
 *
 * TUNING RATIONALE (Phase 5 M10 sim-time reduction)
 *   The original 4-pass / 64 KB design took too many Verilator cycles to finish.
 *   Key changes:
 *     1. Passes: 4 → 1 prime + 1 measured.  Cold misses land in the prime pass;
 *        the measured pass reflects steady-state (hit-heavy below 4 KB, miss-heavy
 *        above).
 *     2. Max size: 64 KB → 32 KB (still 8× the 4 KB L1; cliff is fully visible).
 *     3. STRIDE budget: capped at STRIDE_MAX_ACCESSES (1024) accesses per run.
 *        Rather than touching every stride slot in large arrays, we advance in
 *        STRIDE_STEP-word jumps but stop after 1024 accesses.  Miss rate remains
 *        1 miss / access (every STRIDE_STEP = 64 words = 256 B >> 16 B line)
 *        while the access count is bounded.
 *
 * ACCESS PATTERNS
 *   SEQ    — sequential word-by-word scan of the working-set once (prime once,
 *             measure once).  Below 4 KB: most accesses hit after priming.
 *             Above 4 KB: steady-state miss rate climbs — L1 cliff visible.
 *
 *   STRIDE — large-stride scan: every STRIDE_STEP-th word within the working set,
 *             capped at STRIDE_MAX_ACCESSES.  Each access is a guaranteed cold miss
 *             (256 B stride >> 16 B line) regardless of working-set size.
 *             Provides a near-100%-miss baseline for comparison.
 *
 * ID ENCODING  (passed as `id` to bench_report)
 *   bits [7:5]  — size bucket index 0-6 (see SIZE_STEPS[] below)
 *   bit  [4]    — 0 = SEQ, 1 = STRIDE
 *   bits [3:0]  — reserved / zero
 *
 *   Example:  size bucket 3 (4 KB), SEQ    → id = (3<<5)|(0<<4) = 0x60
 *             size bucket 3 (4 KB), STRIDE → id = (3<<5)|(1<<4) = 0x70
 *
 *   The harness reconstructs: size_bytes = SIZE_STEPS[id >> 5],
 *                              pattern    = (id >> 4) & 1.
 *
 * SIZE_STEPS (7 buckets, indices 0-6)
 *   0 →   512 B   (< L1, warm baseline)
 *   1 →  1024 B   (< L1)
 *   2 →  2048 B   (< L1)
 *   3 →  4096 B   (= L1 capacity, boundary)
 *   4 →  8192 B   (2× L1)
 *   5 → 16384 B   (4× L1)
 *   6 → 32768 B   (8× L1, maximum)
 *
 *   Total output records: 7 sizes × 2 patterns = 14 records.
 *
 * ESTIMATED TOTAL ACCESSES (measured pass only)
 *   SEQ:    128 + 256 + 512 + 1024 + 2048 + 4096 + 8192 = 16 256 word loads
 *   STRIDE: 7 × 1024 (capped)                             =  7 168 word loads
 *   Prime:  same as SEQ for SEQ runs; 7 × min(n/STRIDE_STEP,1024) for STRIDE
 *   Grand total ≈ 47 000 word accesses × ~5 instructions each ≈ 235 000 instrs
 *   At 2–3 CPI (cache-miss heavy) ≈ 500 000–700 000 cycles — well inside 2–3 M
 *   cycle budget.  (init_buf adds ~8192 stores over the 32 KB buffer once.)
 *
 * MEMORY FOOTPRINT
 *   BUF_WORDS = 8192 (32 KB) as a static global.
 *   .bss buffer ends ~0x82A8 — far below stack top at 0x41C00.
 *
 * DEAD-CODE ELIMINATION GUARD
 *   Every loop accumulates into `acc` which is passed as the checksum argument
 *   to bench_report() (written to the scratch slot), preventing the compiler
 *   from deleting the loop body as dead code.
 */

#include "bench.h"

/* 32 KB buffer — single allocation, all runs reuse it. */
#define BUF_WORDS           8192u   /* 8192 × 4 B = 32 768 B = 32 KB */
#define STRIDE_STEP         64u     /* 64-word (256 B) stride >> 16 B line → 1 miss/access */
#define STRIDE_MAX_ACCESSES 1024u   /* cap measured (and prime) stride accesses per run */
#define N_SIZES             7u      /* size_idx 0..6; keep contiguous for harness decode */

/* Size steps in bytes.  Must match the id-encoding comment above.
 * Index 0..6 (7 entries).  The harness decodes: size_bytes = SIZE_STEPS[id >> 5]. */
static const uint32_t SIZE_STEPS[N_SIZES] = {
    512, 1024, 2048, 4096, 8192, 16384, 32768
};

/* The buffer lives in .bss (zero-init at startup by crt0). */
static uint32_t buf[BUF_WORDS];

/* ------------------------------------------------------------------------ */
/* Initialise the buffer with a simple pattern so we are reading real data. */
/* Done once before the sweep; init traffic is not part of any measured run. */
static void init_buf(void)
{
    uint32_t i;
    for (i = 0; i < BUF_WORDS; i++)
        buf[i] = i * 0x9E3779B9u;  /* gold-ratio hash, avoids trivial zeros */
}

/* Return the number of words for a given byte size (clamped to BUF_WORDS). */
static inline uint32_t words_for(uint32_t bytes)
{
    uint32_t w = bytes >> 2;   /* / 4 */
    return (w < BUF_WORDS) ? w : BUF_WORDS;
}

/* run_seq_prime — one untimed warm-up pass over words [0, n).
 * Returns accumulated checksum so the compiler cannot delete the loop body. */
static uint32_t run_seq_prime(uint32_t n)
{
    uint32_t acc = 0;
    uint32_t i;
    for (i = 0; i < n; i++)
        acc += buf[i];
    return acc;
}

/* run_seq_measured — one timed pass over words [0, n).
 * Caller brackets with bench_snapshot() before/after this call. */
static uint32_t run_seq_measured(uint32_t n)
{
    uint32_t acc = 0;
    uint32_t i;
    for (i = 0; i < n; i++)
        acc += buf[i];
    return acc;
}

/* run_stride_prime — one untimed warm-up stride pass capped at STRIDE_MAX_ACCESSES.
 * Advances by STRIDE_STEP words; stops at n or cap, whichever is first. */
static uint32_t run_stride_prime(uint32_t n)
{
    uint32_t acc = 0;
    uint32_t count = 0;
    uint32_t i;
    for (i = 0; i < n && count < STRIDE_MAX_ACCESSES; i += STRIDE_STEP, count++)
        acc += buf[i];
    return acc;
}

/* run_stride_measured — one timed stride pass capped at STRIDE_MAX_ACCESSES.
 * Same pattern as prime; caller brackets with bench_snapshot(). */
static uint32_t run_stride_measured(uint32_t n)
{
    uint32_t acc = 0;
    uint32_t count = 0;
    uint32_t i;
    for (i = 0; i < n && count < STRIDE_MAX_ACCESSES; i += STRIDE_STEP, count++)
        acc += buf[i];
    return acc;
}

/* ------------------------------------------------------------------------ */
int main(void)
{
    bench_snap_t a, b;
    uint32_t si;

    bench_init();   /* zero scratch record-count before first bench_report() */

    init_buf();     /* fill buffer once; not included in any timed measurement */

    /* Iterate over all size buckets, then both patterns.
     * Structure per (size, pattern):
     *   1. Prime pass  — warms the cache; untimed; result discarded after use
     *      as dead-code-elim guard (not reported).
     *   2. Measured pass — steady-state; bracketed by bench_snapshot(). */
    for (si = 0; si < N_SIZES; si++) {
        uint32_t n = words_for(SIZE_STEPS[si]);
        uint32_t prime_acc;  /* used only as dead-code-elim guard */

        /* --- SEQ --- */
        {
            uint32_t id_seq = (si << 5u) | (0u << 4u);
            uint32_t cs;

            /* Prime: warm the cache; suppress unused-variable warning via bench_snap_t
             * trick — we do not call bench_snapshot here so there is no overhead. */
            prime_acc = run_seq_prime(n);

            bench_snapshot(&a);
            cs = run_seq_measured(n);
            bench_snapshot(&b);

            /* Fold prime_acc into checksum so compiler cannot delete the prime loop. */
            bench_report(id_seq, cs ^ prime_acc, &a, &b);
        }

        /* --- STRIDE --- */
        {
            uint32_t id_str = (si << 5u) | (1u << 4u);
            uint32_t cs;

            prime_acc = run_stride_prime(n);

            bench_snapshot(&a);
            cs = run_stride_measured(n);
            bench_snapshot(&b);

            bench_report(id_str, cs ^ prime_acc, &a, &b);
        }
    }

    /* Return 0; __result is written by crt0 halt sequence from a0. */
    return 0;
}
