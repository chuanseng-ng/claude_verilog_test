/* hello.c — A1 toolchain validation program (not a real benchmark).
 *
 * Exercises the full .c -> .elf -> .bin -> .hex path and the perf-counter +
 * scratch-report helpers: sums a small array (touches D-cache), brackets it with
 * snapshots, reports deltas, returns a checksum. Confirms the compile/link/CSR
 * path works before the real Dhrystone/CoreMark/sweep workloads (A3) land.
 */
#include "bench.h"

#define N 64
static volatile uint32_t buf[N];

int main(void) {
    bench_snap_t a, b;

    for (int i = 0; i < N; i++) buf[i] = (uint32_t)(i * 3 + 1);

    bench_snapshot(&a);
    uint32_t sum = 0;
    for (int i = 0; i < N; i++) sum += buf[i];
    bench_snapshot(&b);

    bench_report(/*id=*/0, /*checksum=*/sum, &a, &b);
    return (int)sum;
}
