/* sweep.c — Working-set sweep benchmark for Phase 5 M10 L2-cache decision.
 *
 * Traverses a single 64 KB buffer with access regions of increasing size to
 * expose the 4 KB L1 D-cache capacity cliff.  For each (size, pattern) pair
 * the code brackets the hot loop with bench_snapshot() / bench_report() so the
 * cocotb harness can plot D$-miss-rate vs working-set size.
 *
 * ACCESS PATTERNS
 *   SEQ  — sequential word-by-word scan: every word in [0, N) in address order.
 *           Favours the cache (spatial locality).  Miss rate rises sharply once
 *           the working set exceeds the 4 KB L1 (256 lines × 16 B).
 *
 *   STRIDE — large-stride scan: every 64th word (256-byte stride >> cache line).
 *           Each access is a guaranteed cold miss regardless of working-set size.
 *           Provides a "maximum miss" baseline for comparison.
 *
 * ID ENCODING  (passed as `id` to bench_report)
 *   bits [7:5]  — size bucket index 0-7 (see SIZE_STEPS[] below)
 *   bit  [4]    — 0 = SEQ, 1 = STRIDE
 *   bits [3:0]  — reserved / zero
 *
 *   Example:  size bucket 3 (4 KB), SEQ   → id = (3<<5)|(0<<4) = 0x60
 *             size bucket 3 (4 KB), STRIDE → id = (3<<5)|(1<<4) = 0x70
 *
 *   The harness reconstructs: size_bytes = SIZE_STEPS[id >> 5],
 *                              pattern    = (id >> 4) & 1.
 *
 * SIZE_STEPS (8 buckets, indices 0-7)
 *   0 →   512 B   (< L1, warm baseline)
 *   1 →  1024 B   (< L1)
 *   2 →  2048 B   (< L1)
 *   3 →  4096 B   (= L1 capacity, boundary)
 *   4 →  8192 B   (2× L1)
 *   5 → 16384 B   (4× L1)
 *   6 → 32768 B   (8× L1)
 *   7 → 65536 B   (16× L1, maximum)
 *
 * MEMORY FOOTPRINT
 *   BUF_WORDS = 16384 (64 KB) as a static global.
 *   Total image well within the 256 KB SRAM window (0x2000..0x41F00).
 *
 * DEAD-CODE ELIMINATION GUARD
 *   Every loop accumulates into `acc` (volatile-written via bench_report's
 *   checksum field) so the compiler cannot delete the loop body.
 *
 * HOW TO READ RESULTS
 *   Plot ΔD$-miss (p[5] - p[5]_prev) vs size for SEQ pattern.
 *   The cliff between bucket 3 (4 KB) and bucket 4 (8 KB) shows L1 saturation.
 *   If the cliff is shallow, L2 adds little; if steep, L2 is worthwhile.
 */

#include "bench.h"

/* 64 KB buffer — single allocation, all runs reuse it. */
#define BUF_WORDS   16384u          /* 16384 × 4 B = 65 536 B = 64 KB */
#define STRIDE_STEP 64u             /* 64-word (256 B) stride for STRIDE pattern */

/* Size steps in bytes.  Must match the id encoding comment above. */
static const uint32_t SIZE_STEPS[8] = {
    512, 1024, 2048, 4096, 8192, 16384, 32768, 65536
};

/* The buffer lives in .bss (zero-init at startup by crt0). */
static uint32_t buf[BUF_WORDS];

/* ------------------------------------------------------------------------ */
/* Initialise the buffer with a simple pattern so we are reading real data. */
/* Done once before the sweep so the init traffic is not part of any region. */
static void init_buf(void)
{
    for (uint32_t i = 0; i < BUF_WORDS; i++)
        buf[i] = i * 0x9E3779B9u;  /* gold-ratio hash, avoids trivial zeros */
}

/* Return the number of words for a given byte size (clamped to BUF_WORDS). */
static inline uint32_t words_for(uint32_t bytes)
{
    uint32_t w = bytes >> 2;   /* / 4 */
    return (w < BUF_WORDS) ? w : BUF_WORDS;
}

/* SEQ pattern: scan words [0, n) sequentially, PASSES times.
 * Multiple passes amortise snapshot overhead for small working sets and
 * ensure the D$ is well-exercised (avoids single-pass cold-miss skew on
 * small sizes).  Four passes is enough for steady-state at all sizes. */
#define PASSES 4u

static uint32_t run_seq(uint32_t n)
{
    uint32_t acc = 0;
    for (uint32_t p = 0; p < PASSES; p++)
        for (uint32_t i = 0; i < n; i++)
            acc += buf[i];
    return acc;
}

/* STRIDE pattern: access every STRIDE_STEP-th word within [0, n) words.
 * Each access touches a new cache line, producing one D$ miss per access.
 * Returns checksum so compiler keeps the load. */
static uint32_t run_stride(uint32_t n)
{
    uint32_t acc = 0;
    for (uint32_t p = 0; p < PASSES; p++)
        for (uint32_t i = 0; i < n; i += STRIDE_STEP)
            acc += buf[i];
    return acc;
}

/* ------------------------------------------------------------------------ */
int main(void)
{
    bench_snap_t a, b;

    bench_init();   /* zero scratch record-count before first bench_report() */

    init_buf();

    /* Iterate over all size buckets, then both patterns. */
    for (uint32_t si = 0; si < 8u; si++) {
        uint32_t n = words_for(SIZE_STEPS[si]);

        /* --- SEQ --- */
        uint32_t id_seq = (si << 5u) | (0u << 4u);
        bench_snapshot(&a);
        uint32_t cs_seq = run_seq(n);
        bench_snapshot(&b);
        bench_report(id_seq, cs_seq, &a, &b);

        /* --- STRIDE --- */
        uint32_t id_str = (si << 5u) | (1u << 4u);
        bench_snapshot(&a);
        uint32_t cs_str = run_stride(n);
        bench_snapshot(&b);
        bench_report(id_str, cs_str, &a, &b);
    }

    /* Return the last stride checksum — non-zero proves we ran. */
    return 0;
}
