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
 * write the deltas to a fixed SRAM scratch block the cocotb harness backdoor-reads.
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

/* Scratch block in SRAM the harness reads after EBREAK. Sits in the top 256 B of
 * the 256 KB bench SRAM window (0x41F00..0x41FFF), just above the stack; mirrored
 * in rv32i.ld and the Python harness. SRAM word index = (addr-0x2000)/4. */
#define BENCH_SCRATCH_ADDR  0x00041F00u
#define BENCH_MAGIC         0xB10C0000u   /* | benchmark id in low byte */

typedef struct {
    uint32_t cycles;
    uint32_t instret;
    uint32_t icache_miss;
    uint32_t dcache_miss;
    uint32_t branch_miss;
} bench_snap_t;

static inline void bench_snapshot(bench_snap_t *s) {
    s->cycles      = read_csr(0xB00);
    s->instret     = read_csr(0xB02);
    s->icache_miss = read_csr(0xB03);
    s->dcache_miss = read_csr(0xB04);
    s->branch_miss = read_csr(0xB05);
}

/* Store {magic, checksum, cycles, instret, ic_miss, dc_miss, br_miss} deltas to
 * the scratch block. id tags which benchmark produced the record. */
static inline void bench_report(uint32_t id, uint32_t checksum,
                                const bench_snap_t *a, const bench_snap_t *b) {
    volatile uint32_t *p = (volatile uint32_t *)BENCH_SCRATCH_ADDR;
    p[0] = BENCH_MAGIC | (id & 0xFF);
    p[1] = checksum;
    p[2] = b->cycles      - a->cycles;
    p[3] = b->instret     - a->instret;
    p[4] = b->icache_miss - a->icache_miss;
    p[5] = b->dcache_miss - a->dcache_miss;
    p[6] = b->branch_miss - a->branch_miss;
}

#endif /* BENCH_H */
