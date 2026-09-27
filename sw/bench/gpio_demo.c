/* gpio_demo.c — GPIO driver self-test / demo (bead claude_verilog_test-8qn4 item 2).
 *
 * Proves sw/drivers/gpio.h by RUNNING it on the real SoC (via cocotb test
 * tb/cocotb/soc/test_gpio_driver.py), not merely by compiling it. Builds
 * through the existing sw/bench/Makefile (PROGS := wildcard *.c) exactly
 * like hello.c/sweep.c/matmul.c -- crt0.S + rv32i.ld link it into SRAM at
 * 0x2000, same as every other sw/bench program.
 *
 * This is deliberately NOT test_soc_gpio.py's hand-assembled-firmware test
 * (tb/cocotb/soc/gpio_fw/) -- that suite already proves the gpio_controller
 * RTL works through the fabric. This program instead exercises the DRIVER
 * API in sw/drivers/gpio.h end to end: direction config, output write,
 * input read-back (respecting the 3-clock-edge sync latency via
 * gpio_poll_in()), and a real GPIO interrupt taken by the CPU (mtvec ->
 * gpio_isr -> gpio_irq_clear_edge() -> MRET), using an
 * __attribute__((interrupt)) C ISR (GCC's RISC-V "interrupt" attribute:
 * verified by hand to save/restore every register it touches, including
 * across calls, and to emit `mret` -- see the build-verification note in
 * the accompanying PR).
 *
 * Phases, each ended by a distinct marker function whose address (from
 * build/gpio_demo.sym) the cocotb test watches via commit_pc_o -- mirrors
 * test_soc_gpio.py's OUTPUT_DONE_PC/INPUT_READY_PC/IRQ_READY_PC technique,
 * but the PCs come from compiled-C symbol addresses instead of a hand-fixed
 * hex assembler layout:
 *
 *   1. OUTPUT: gpio_dir_write(TEST_DIR_VAL); gpio_out_write(TEST_DATA_VAL);
 *      marker_output_done(). cocotb samples gpio_oe_o/gpio_out_o at that PC.
 *   2. INPUT: marker_input_ready(); then gpio_poll_in(INPUT_MASK, ...).
 *      cocotb, on seeing that PC, drives gpio_in_i = INPUT_MASK.
 *   3. INTERRUPT: configure pin IRQ_PIN_IDX rising-edge, unmask it locally
 *      and at interrupt_controller (bit 5 = GPIO), install gpio_isr at
 *      mtvec, enable mie.MEIE + mstatus.MIE, marker_irq_ready(), then a
 *      bounded poll on g_isr_flag (set by the ISR). cocotb, on seeing
 *      IRQ_READY, raises gpio_in_i bit IRQ_PIN_IDX; independently watches
 *      commit_pc_o for gpio_isr's own entry address and samples
 *      dut.u_soc.gpio_irq/ext_irq at trap entry and after the ISR runs.
 *
 * Result reporting (dual, cross-checked by the harness):
 *   - __result (crt0.S convention): 0 = PASS, else one of the FAIL_* codes
 *     below, identifying which phase failed.
 *   - g_isr_count (backdoor SRAM word, resolved via build/gpio_demo.sym):
 *     independent proof the ISR ran exactly once -- cocotb cross-checks this
 *     against its own commit_pc_o observation of gpio_isr's entry, the same
 *     pattern test_soc_gpio.py uses for its ISR_COUNT_WI backdoor read.
 *     crt0.S flushes the D-cache (CSRW 0x7C0) before EBREAK, so this global
 *     (below MMIO_BASE, normally D$-cached) is guaranteed coherent in main
 *     SRAM by the time the harness backdoor-reads it -- no special D$-aware
 *     read path is needed here (contrast test_l2_bench.py's _dcache_read_word,
 *     which reads WHILE the program is still mid-run and dirty lines have
 *     not yet been flushed).
 */

#include <stdint.h>
#include "gpio.h"
#include "riscv_csr.h"

/* ---------------------------------------------------------------------
 * Test constants.
 * --------------------------------------------------------------------- */
#define TEST_DIR_VAL    0x000000F0u          /* pins 4-7 driven as outputs */
#define TEST_DATA_VAL   0x00000050u          /* pins 4 and 6 driven high   */

#define INPUT_PIN_A     16u
#define INPUT_PIN_B     18u
#define INPUT_MASK      ((1u << INPUT_PIN_A) | (1u << INPUT_PIN_B))

#define IRQ_PIN_IDX     24u

#define POLL_LIMIT      4000u   /* generous vs. full-fabric MMIO round trips */

/* interrupt_controller (base 0x2000_6000): word 1 = IRQ_MASK. GPIO is
 * source bit 5 (rtl/soc/soc_top.sv irq_src_i concat / interrupt_controller.sv
 * header comment). */
#define INTC_IRQ_MASK_ADDR   0x20006004u
#define INTC_GPIO_BIT        5u

/* Fail codes returned via __result (a0). 0 == PASS. */
#define FAIL_OUTPUT_DIR      1
#define FAIL_OUTPUT_DATA     2
#define FAIL_INPUT_TIMEOUT   3
#define FAIL_IRQ_TIMEOUT     4
#define FAIL_IRQ_COUNT       5
#define FAIL_IRQ_STAT_STUCK  6

/* ---------------------------------------------------------------------
 * ISR-visible state. volatile: written by gpio_isr (an interrupt context),
 * read by main()'s poll loop and by the cocotb harness's backdoor read.
 * --------------------------------------------------------------------- */
volatile uint32_t g_isr_count = 0;
volatile uint32_t g_isr_flag  = 0;

/* ---------------------------------------------------------------------
 * Marker functions. Each has a distinct body (a distinct immediate stored
 * to a volatile local) so -O2 cannot identical-code-fold them into one
 * symbol/address -- that would collapse the marker PCs the cocotb test
 * relies on being distinct. noinline keeps the call (and therefore the
 * marker's own entry PC) from disappearing.
 * --------------------------------------------------------------------- */
__attribute__((noinline)) void marker_output_done(void) {
    volatile uint32_t tag = 0xA1u; (void)tag;
}
__attribute__((noinline)) void marker_input_ready(void) {
    volatile uint32_t tag = 0xA2u; (void)tag;
}
__attribute__((noinline)) void marker_irq_ready(void) {
    volatile uint32_t tag = 0xA3u; (void)tag;
}

/* ---------------------------------------------------------------------
 * GPIO ISR. GCC's RISC-V "interrupt" attribute generates full save/restore
 * of every register this function (and anything it calls) touches, plus a
 * trailing `mret` -- confirmed by inspecting the generated .dis for this
 * exact pattern (a leaf `interrupt` function calling ordinary helpers)
 * before relying on it here.
 *
 * Clears the EDGE-configured IRQ_PIN_IDX bit via gpio_irq_clear_edge() --
 * NOT a generic "clear" call, because that call is a silent no-op on a
 * level-type pin (see gpio.h). IRQ_PIN_IDX is configured GPIO_IRQ_EDGE in
 * main() below, so this is the correct call for it.
 * --------------------------------------------------------------------- */
__attribute__((interrupt)) void gpio_isr(void) {
    gpio_irq_clear_edge(1u << IRQ_PIN_IDX);
    g_isr_count++;
    g_isr_flag = 1;
}

int main(void) {
    uint32_t i;

    /* ---------------- Phase 1: OUTPUT ---------------- */
    gpio_dir_write(TEST_DIR_VAL);
    gpio_out_write(TEST_DATA_VAL);
    marker_output_done();

    /* Driver-level self-check of the RW shadow registers (the cocotb test
     * independently checks the actual gpio_oe_o/gpio_out_o pads at the
     * marker_output_done PC -- this check is the firmware's own half of
     * the cross-check, not a substitute for it). */
    if (gpio_dir_read() != TEST_DIR_VAL)
        return FAIL_OUTPUT_DIR;
    if (gpio_out_read() != TEST_DATA_VAL)
        return FAIL_OUTPUT_DATA;

    /* ---------------- Phase 2: INPUT ---------------- */
    marker_input_ready();   /* cocotb drives gpio_in_i = INPUT_MASK on seeing this PC */

    if (!gpio_poll_in(INPUT_MASK, INPUT_MASK, POLL_LIMIT))
        return FAIL_INPUT_TIMEOUT;

    /* ---------------- Phase 3: INTERRUPT ---------------- */
    gpio_irq_configure(IRQ_PIN_IDX, GPIO_IRQ_EDGE, GPIO_IRQ_POL_HIGH_OR_RISING);
    /* Clear any stale sticky status left over from reset defaults (trap #3
     * in gpio.h -- IRQ_PIN_IDX was level/active-low at reset, so its status
     * bit may have latched once already when reconfigured; harmless to
     * clear unconditionally before enabling). */
    gpio_irq_clear_edge(1u << IRQ_PIN_IDX);
    gpio_irq_enable(1u << IRQ_PIN_IDX);

    /* Unmask GPIO (bit 5) at interrupt_controller so its irq_o can assert
     * ext_irq_i (MEIP) -- gpio_controller's own IRQ_EN above only feeds
     * gpio_controller's local irq_o; interrupt_controller's own IRQ_MASK
     * gates that further before it reaches the CPU. */
    {
        volatile uint32_t *intc_mask = (volatile uint32_t *)INTC_IRQ_MASK_ADDR;
        *intc_mask |= (1u << INTC_GPIO_BIT);
    }

    write_csr(0x305, (uint32_t)&gpio_isr);   /* mtvec (Direct mode only, per RTL) */
    set_csr_bits(0x304, (1u << MIE_MEIE_BIT));    /* mie.MEIE */
    set_csr_bits(0x300, (1u << MSTATUS_MIE_BIT)); /* mstatus.MIE */

    marker_irq_ready();   /* cocotb raises gpio_in_i bit IRQ_PIN_IDX on seeing this PC */

    {
        int ok = 0;
        for (i = 0; i < POLL_LIMIT; i++) {
            if (g_isr_flag) { ok = 1; break; }
        }
        if (!ok)
            return FAIL_IRQ_TIMEOUT;
    }

    /* Settle window: MRET re-enables mstatus.MIE. If GPIO_IRQ_CLR had failed
     * to deassert the source, irq_o/ext_irq would still be high and the CPU
     * would immediately re-vector -- g_isr_count would become 2. This spin
     * gives that a chance to happen before we check. */
    for (i = 0; i < 64; i++) {
        __asm__ volatile ("nop");
    }

    if (g_isr_count != 1)
        return FAIL_IRQ_COUNT;
    if (gpio_irq_status_pin(IRQ_PIN_IDX) != 0)
        return FAIL_IRQ_STAT_STUCK;

    return 0;   /* PASS */
}
