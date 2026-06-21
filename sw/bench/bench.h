/* bench.h — perf-counter access + result-scratch helpers for SoC cache benchmarks.
 *
 * The CPU exposes RISC-V hardware perf counters (Phase 5 M7):
 *   mcycle  (0xB00)  64-bit cycle count        — low half read here
 *   minstret(0xB02)  retired instructions      — low half
 *   mhpmcounter3 (0xB03)  I-cache miss count
 *   mhpmcounter4 (0xB04)  D-cache miss count
 *   mhpmcounter5 (0xB05)  branch mispredictions
 *
 * Benchmarks bracket a region of interest with bench_snapshot() before/after and
 * write the deltas to a multi-slot SRAM scratch region the cocotb harness
 * backdoor-reads after EBREAK.  All slots from a single run are preserved because
 * bench_report() appends to the next slot rather than overwriting slot 0.
 *
 * SCRATCH REGION LAYOUT  (1 KB, 0x41C00..0x41FFF; 256 words)
 *   Word[0]  : record count (written last by bench_report so the harness can
 *              detect a partial run if the program aborts early)
 *   Word[1+] : slots, 8 words each (32 bytes per slot)
 *              slot k starts at word offset 1 + k*8
 *              max 31 slots (fits 256-word region: 1 header + 31*8 = 249 ≤ 256)
 *
 * SLOT LAYOUT (8 words, indices relative to slot base)
 *   [0] BENCH_MAGIC | (id & 0xFF)   — magic tag + benchmark id
 *   [1] checksum                    — caller-supplied dead-code-elimination guard
 *   [2] Δcycles                     — b->cycles      - a->cycles
 *   [3] Δinstret                    — b->instret     - a->instret
 *   [4] ΔI$miss                     — b->icache_miss - a->icache_miss
 *   [5] ΔD$miss                     — b->dcache_miss - a->dcache_miss
 *   [6] Δbranch_miss                — b->branch_miss - a->branch_miss
 *   [7] 0 (pad, reserved)
 *
 * HARNESS CONTRACT
 *   1. Call bench_init() once at the start of main() to zero the count word.
 *   2. Call bench_snapshot() / bench_report() as many times as needed (≤ 31).
 *   3. After EBREAK: harness reads Word[0] to get count N, then reads N slots.
 *      SRAM word index for BENCH_SCRATCH_ADDR = (0x41C00 - 0x2000) / 4 = 0x7F00.
 *
 * MEMORY MAP (mirrored in rv32i.ld and the Python harness)
 *   0x0000_2000 .. 0x0004_1BFF  code + data + stack working set
 *   0x0004_1C00 .. 0x0004_1FFF  bench scratch region (this header)
 *   Stack grows down from 0x0004_1C00.
 *   SRAM window requires MEM_WORDS = 65536 (256 KB: 0x2000..0x42000).
 */
#ifndef BENCH_H
#define BENCH_H

#include <stdint.h>

#define CSR_MCYCLE        0xB00
#define CSR_MINSTRET      0xB02
#define CSR_HPM3_ICMISS   0xB03
#define CSR_HPM4_DCMISS   0xB04
#define CSR_HPM5_BRMISS   0xB05

#define read_csr(csr) ({ uint32_t __v; \
    __asm__ volatile ("csrr %0, " #csr : "=r"(__v)); __v; })

/* Base address of the 1 KB scratch region.  Stack grows down from here.
 * Mirrored in rv32i.ld (__stack_top) and the Python harness.
 * SRAM word index of base = (BENCH_SCRATCH_ADDR - 0x2000) / 4 = 0x7F00. */
#define BENCH_SCRATCH_ADDR   0x00041C00u
#define BENCH_MAGIC          0xB10C0000u   /* | benchmark id in low byte */
#define BENCH_RECORD_WORDS   8u            /* words per slot (32 bytes) */
#define BENCH_MAX_RECORDS    31u           /* 1 header word + 31*8 = 249 ≤ 256 */

typedef struct {
    uint32_t cycles;
    uint32_t instret;
    uint32_t icache_miss;
    uint32_t dcache_miss;
    uint32_t branch_miss;
} bench_snap_t;

/* bench_init() — zero the record-count header word.
 * MUST be called once at the top of main() before any bench_report() call.
 * Without this the harness cannot trust the count if the SRAM is non-zero
 * from a previous load. */
static inline void bench_init(void) {
    volatile uint32_t *base = (volatile uint32_t *)BENCH_SCRATCH_ADDR;
    base[0] = 0u;
}

static inline void bench_snapshot(bench_snap_t *s) {
    s->cycles      = read_csr(0xB00);
    s->instret     = read_csr(0xB02);
    s->icache_miss = read_csr(0xB03);
    s->dcache_miss = read_csr(0xB04);
    s->branch_miss = read_csr(0xB05);
}

/* bench_report() — append one record to the next free slot.
 *
 * Reads the current count from Word[0], writes the 8-word slot at
 * Word[1 + count*8], then increments and writes back Word[0].
 * If count >= BENCH_MAX_RECORDS the call is silently dropped (no overflow). */
static inline void bench_report(uint32_t id, uint32_t checksum,
                                const bench_snap_t *a, const bench_snap_t *b) {
    volatile uint32_t *base = (volatile uint32_t *)BENCH_SCRATCH_ADDR;
    uint32_t count = base[0];
    if (count >= BENCH_MAX_RECORDS)
        return;
    volatile uint32_t *slot = base + 1u + count * BENCH_RECORD_WORDS;
    slot[0] = BENCH_MAGIC | (id & 0xFFu);
    slot[1] = checksum;
    slot[2] = b->cycles      - a->cycles;
    slot[3] = b->instret     - a->instret;
    slot[4] = b->icache_miss - a->icache_miss;
    slot[5] = b->dcache_miss - a->dcache_miss;
    slot[6] = b->branch_miss - a->branch_miss;
    slot[7] = 0u;
    base[0] = count + 1u;
}

#endif /* BENCH_H */
