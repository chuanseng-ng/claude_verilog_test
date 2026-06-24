/* matmul.c — Integer matrix-multiply benchmark for Phase 5 M10 L2-cache decision.
 *
 * Computes C = A × B for 48×48 int32 matrices.  This is a representative
 * integer workload with strong reuse: each row of A is reused 48 times, each
 * column of B is reused 48 times.  The working set deliberately spans the L1
 * D-cache so reuse behaviour (cache hit rates on second+ touches) is visible
 * in mhpmcounter4.
 *
 * WORKING SET SIZE
 *   Three 48×48 int32 matrices: 3 × 48 × 48 × 4 B = 27 648 B (~27 KB).
 *   L1 D-cache = 4 KB (256 lines × 16 B).  The matrix set is 6.75× the cache,
 *   producing significant miss pressure — exactly the regime where L2 helps.
 *
 * SELF-CHECK
 *   With A[i][j] = i+j and B[i][j] = i*j+1, C[i][j] has a closed-form
 *   reference value.  The loop computes a running CRC-style checksum over
 *   all C elements; the harness can compare this against the Python reference
 *   to confirm data integrity.
 *   Reference checksum = sum_of_all_C_elements (mod 2^32).
 *
 * BENCH_REPORT ID
 *   id = 0x01  (matmul, single measurement region)
 *
 * MEMORY FOOTPRINT
 *   27 648 B matrices + small stack frames + .text — well inside 256 KB SRAM.
 *
 * DEAD-CODE GUARD
 *   The inner accumulator `acc` is written to C[i][j] and then checksummed,
 *   so the entire triple loop body is live.
 */

#include "bench.h"

#define N    48              /* matrix dimension: N×N */
#define ID   0x01u           /* bench_report id for this benchmark */

/* Place matrices in .bss (zeroed by crt0) so they don't bloat the .hex. */
static int32_t A[N][N];
static int32_t B[N][N];
static int32_t C[N][N];

/* Initialise A and B with simple, non-trivial values.
 * A[i][j] = (int32_t)(i + j)
 * B[i][j] = (int32_t)(i * j + 1)
 * Chosen so the result is deterministic and easy to verify in Python:
 *   C[i][j] = sum_{k=0}^{N-1} (i+k) * (k*j+1)
 *           = sum_k (i*k*j + i + k^2*j + k)
 */
static void init_matrices(void)
{
    for (int i = 0; i < N; i++)
        for (int j = 0; j < N; j++) {
            A[i][j] = (int32_t)(i + j);
            B[i][j] = (int32_t)(i * j + 1);
        }
}

/* Standard ijk matrix multiply — no cache-blocking so the access pattern
 * shows raw L1 pressure (B is accessed column-major, every row of B is a
 * cache miss for large N).  This is intentional: we want to measure misses,
 * not hide them with tiling. */
static uint32_t matmul_and_checksum(void)
{
    uint32_t cs = 0;

    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            int32_t acc = 0;
            for (int k = 0; k < N; k++)
                acc += A[i][k] * B[k][j];
            C[i][j] = acc;
            cs += (uint32_t)acc;   /* accumulate checksum over all results */
        }
    }
    return cs;
}

int main(void)
{
    bench_snap_t a, b;

    bench_init();   /* zero scratch record-count before first bench_report() */

    init_matrices();

    bench_snapshot(&a);
    uint32_t cs = matmul_and_checksum();
    bench_snapshot(&b);

    bench_report(ID, cs, &a, &b);

    /* Return checksum so crt0 parks it in __result — harness can cross-check. */
    return (int)cs;
}
