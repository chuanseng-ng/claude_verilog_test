/* riscv_csr.h — minimal RV32I+Zicsr CSR access helpers, shared across sw/drivers
 * and sw/bench.
 *
 * `read_csr` already existed (duplicated) in sw/bench/bench.h; this header is
 * the first *driver-level* need for csrw/csrs/csrc (setting mtvec/mie/mstatus
 * for the GPIO interrupt path — see sw/drivers/gpio.h), so it lives here
 * rather than growing bench.h with non-benchmark concerns. bench.h is left
 * untouched (its own read_csr keeps working; do not delete it — sw/bench's
 * existing programs still use it and this header does not replace bench.h).
 *
 * All macros take a numeric CSR address (e.g. 0x300), matching bench.h's own
 * `read_csr(0xB00)` convention — NOT a symbolic name — because the value is
 * substituted textually into the asm string via the # (stringise) operator,
 * which does not macro-expand its argument.  Named CSR_* constants below are
 * for documentation/readability at call sites; pass the numeric literal
 * itself to the accessor macros.
 */
#ifndef RISCV_CSR_H
#define RISCV_CSR_H

#include <stdint.h>

/* Relevant Machine-mode CSR addresses (rtl/cpu/core/rv32i_csr_file.sv). */
#define CSR_MSTATUS   0x300u
#define CSR_MIE       0x304u
#define CSR_MTVEC     0x305u
#define CSR_MEPC      0x341u
#define CSR_MCAUSE    0x342u

/* mstatus / mie bit positions actually implemented by rv32i_csr_file.sv. */
#define MSTATUS_MIE_BIT   3u    /* mstatus.MIE  — global interrupt enable   */
#define MSTATUS_MPIE_BIT  7u    /* mstatus.MPIE — previous MIE (trap entry) */
#define MIE_MEIE_BIT      11u   /* mie.MEIE     — machine external enable   */
#define MIE_MTIE_BIT      7u    /* mie.MTIE     — machine timer enable      */

#ifndef read_csr
#define read_csr(csr) ({ uint32_t __v; \
    __asm__ volatile ("csrr %0, " #csr : "=r"(__v)); __v; })
#endif

/* write_csr(csr, val) — csrw csr, val (unconditional overwrite). */
#define write_csr(csr, val) do { \
    uint32_t __v = (uint32_t)(val); \
    __asm__ volatile ("csrw " #csr ", %0" :: "r"(__v)); \
} while (0)

/* set_csr_bits(csr, bits)   — csrs csr, bits  (read-modify-write OR).   */
#define set_csr_bits(csr, bits) do { \
    uint32_t __v = (uint32_t)(bits); \
    __asm__ volatile ("csrs " #csr ", %0" :: "r"(__v)); \
} while (0)

/* clear_csr_bits(csr, bits) — csrc csr, bits  (read-modify-write AND-NOT). */
#define clear_csr_bits(csr, bits) do { \
    uint32_t __v = (uint32_t)(bits); \
    __asm__ volatile ("csrc " #csr ", %0" :: "r"(__v)); \
} while (0)

#endif /* RISCV_CSR_H */
