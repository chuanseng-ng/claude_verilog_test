/* gpio.h — driver for rtl/periph/gpio_controller.sv (Phase 6a GPIO, bead
 * claude_verilog_test-8qn4 item 2).
 *
 * There was previously NO driver layer for this block at all: sw/ held only
 * sw/bench/ (cache benchmarks), and no GPIO register header existed anywhere
 * outside the RTL/testbench. This header is that first layer, following
 * sw/bench/bench.h's `volatile uint32_t *` MMIO convention.
 *
 * Placement: sw/drivers/, not sw/bench/. A driver is not a benchmark and has
 * no crt0/main of its own; sw/bench/'s Makefile builds every *.c file in
 * that directory as an independent linked program (PROGS := wildcard *.c),
 * so a driver source file placed there would itself become a spurious
 * "benchmark". This header is instead pulled in via an extra -I onto the
 * *existing* sw/bench/Makefile (no build-rule changes needed) by any
 * any .c program in that directory that wants it — see sw/bench/gpio_demo.c.
 * Header-only (all `static inline`), exactly like bench.h, so no separate
 * translation unit needs linking in.
 *
 * Base address: 0x2000_A000 (APB slave 7, rtl/soc/soc_top.sv). 32 pins
 * (N_PINS=32 in the soc_top instantiation).
 *
 * ============================================================================
 * THREE BEHAVIOURAL TRAPS THIS DRIVER MUST NOT HIDE (see gpio_controller.sv
 * header for the authoritative RTL rationale — restated here because a
 * driver that papers over any of these will mislead its callers):
 *
 *  1. INPUT SYNC LATENCY: gpio_in_i is asynchronous and is synchronised by a
 *     2-stage cdc_2ff_sync per pin, then latched into the register bank on
 *     the following cycle -- a real pin transition takes 3 clk edges before
 *     it is visible in GPIO_DATA_IN. gpio_in_read() below returns whatever
 *     is in the register RIGHT NOW -- it does not wait. Any caller that
 *     needs to observe a specific transition MUST use the bounded
 *     gpio_poll_in() helper (or its own equivalent bounded retry), never a
 *     single immediate read.
 *
 *  2. EDGE-STICKY / LEVEL-LIVE STATUS: GPIO_IRQ_STAT bits behave differently
 *     by GPIO_IRQ_TYPE:
 *       - EDGE pins:  sticky. Latches until a GPIO_IRQ_CLR write for that
 *         bit. A same-cycle CLR racing a fresh edge loses to the edge (the
 *         bit stays set) -- an edge is never silently dropped.
 *       - LEVEL pins: live. The bit simply mirrors the current condition;
 *         GPIO_IRQ_CLR has NO EFFECT on a level pin's status bit, by design.
 *     This driver therefore does NOT offer one generic "clear the
 *     interrupt" call. gpio_irq_clear_edge() below is named for exactly what
 *     it does and is a no-op on any pin configured GPIO_IRQ_LEVEL -- see its
 *     own comment. To silence a level interrupt: remove the source
 *     condition, or mask it out via gpio_irq_disable().
 *
 *  3. RESET-DEFAULT STATUS IS MEANINGLESS UNTIL CONFIGURED: at reset,
 *     GPIO_IRQ_TYPE=level, GPIO_IRQ_POL=active-low, and every unconnected
 *     pin reads low -- so EVERY GPIO_IRQ_STAT bit reads 1 out of reset (the
 *     level condition "pin is low" is true everywhere). gpio_irq_configure()
 *     MUST be called (setting TYPE/POL) before GPIO_IRQ_STAT means anything
 *     for a given pin.
 * ============================================================================
 *
 * Lint/build target: same toolchain as sw/bench (riscv32-none-elf-gcc,
 * -march=rv32i_zicsr -mabi=ilp32, -Wall -Wextra clean).
 */
#ifndef GPIO_H
#define GPIO_H

#include <stdint.h>

/* ---------------------------------------------------------------------
 * Register map (word offsets), mirrored verbatim from
 * rtl/periph/gpio_controller.sv's header comment.
 * --------------------------------------------------------------------- */
#define GPIO_BASE_ADDR   0x2000A000u

typedef enum {
    GPIO_REG_DATA_IN  = 0,   /* RO  -- live synchronised pin levels        */
    GPIO_REG_DATA_OUT = 1,   /* RW  -- output-drive value per pin          */
    GPIO_REG_DIR      = 2,   /* RW  -- 1 = pin driven as output            */
    GPIO_REG_IRQ_EN   = 3,   /* RW  -- 1 = pin's IRQ event masked into irq_o */
    GPIO_REG_IRQ_TYPE = 4,   /* RW  -- 0 = level, 1 = edge                 */
    GPIO_REG_IRQ_POL  = 5,   /* RW  -- 0 = low/falling, 1 = high/rising    */
    GPIO_REG_IRQ_STAT = 6,   /* RO  -- edge-sticky / level-live (see above) */
    GPIO_REG_IRQ_CLR  = 7    /* WO  -- write 1 to clear (edge pins only)   */
} gpio_reg_t;

#define GPIO_N_REGS 8u

typedef enum {
    GPIO_IRQ_LEVEL = 0,
    GPIO_IRQ_EDGE  = 1
} gpio_irq_type_t;

typedef enum {
    GPIO_IRQ_POL_LOW_OR_FALLING  = 0,
    GPIO_IRQ_POL_HIGH_OR_RISING  = 1
} gpio_irq_pol_t;

/* ---------------------------------------------------------------------
 * Raw word accessors.
 * --------------------------------------------------------------------- */
static inline volatile uint32_t *gpio_regs(void) {
    return (volatile uint32_t *)GPIO_BASE_ADDR;
}

static inline uint32_t gpio_reg_read(gpio_reg_t reg) {
    return gpio_regs()[reg];
}

static inline void gpio_reg_write(gpio_reg_t reg, uint32_t val) {
    gpio_regs()[reg] = val;
}

/* ---------------------------------------------------------------------
 * Direction (GPIO_DIR: 1 = output).
 * --------------------------------------------------------------------- */
static inline uint32_t gpio_dir_read(void) {
    return gpio_reg_read(GPIO_REG_DIR);
}

/* Whole-register write -- caller supplies the full 32-bit direction mask. */
static inline void gpio_dir_write(uint32_t dir_mask) {
    gpio_reg_write(GPIO_REG_DIR, dir_mask);
}

/* Per-pin read-modify-write direction config. */
static inline void gpio_set_dir(uint32_t pin_mask, int as_output) {
    uint32_t dir = gpio_dir_read();
    if (as_output)
        dir |= pin_mask;
    else
        dir &= ~pin_mask;
    gpio_dir_write(dir);
}

/* ---------------------------------------------------------------------
 * Output drive (GPIO_DATA_OUT).
 * --------------------------------------------------------------------- */
static inline uint32_t gpio_out_read(void) {
    return gpio_reg_read(GPIO_REG_DATA_OUT);
}

static inline void gpio_out_write(uint32_t val) {
    gpio_reg_write(GPIO_REG_DATA_OUT, val);
}

static inline void gpio_out_set(uint32_t pin_mask) {
    gpio_out_write(gpio_out_read() | pin_mask);
}

static inline void gpio_out_clear(uint32_t pin_mask) {
    gpio_out_write(gpio_out_read() & ~pin_mask);
}

static inline void gpio_out_toggle(uint32_t pin_mask) {
    gpio_out_write(gpio_out_read() ^ pin_mask);
}

/* ---------------------------------------------------------------------
 * Input read (GPIO_DATA_IN) -- see trap #1 in the file header.
 * --------------------------------------------------------------------- */

/* gpio_in_read() -- returns GPIO_DATA_IN's CURRENT value. Does NOT wait for
 * a specific transition to become visible; see the header note on the
 * 3-clock-edge synchroniser latency. A caller polling for a pin change must
 * use gpio_poll_in() (or an equivalent bounded loop of its own), never a
 * single immediate call after driving/expecting an external event. */
static inline uint32_t gpio_in_read(void) {
    return gpio_reg_read(GPIO_REG_DATA_IN);
}

static inline uint32_t gpio_in_read_pin(unsigned pin) {
    return (gpio_in_read() >> pin) & 0x1u;
}

/* gpio_poll_in() -- bounded retry for (gpio_in_read() & mask) == (expected & mask).
 * Returns 1 if the condition was observed within max_iters loop iterations,
 * 0 on timeout. This is the one intended way to wait on an input pin: it
 * makes the mandatory bound explicit at every call site instead of letting
 * callers write their own unbounded `while (gpio_in_read() != x);` which
 * would hang forever on a stuck pin or a synchroniser that never latches
 * the expected value (e.g. mis-wired testbench driver). max_iters must be
 * large enough to cover the pin's 3-clock-edge synchroniser latency AND
 * this loop's own per-iteration MMIO round-trip cost (multiple cycles
 * through the full AXI/APB fabric on the SoC, not a flat register read). */
static inline int gpio_poll_in(uint32_t mask, uint32_t expected, uint32_t max_iters) {
    uint32_t i;
    for (i = 0; i < max_iters; i++) {
        if ((gpio_in_read() & mask) == (expected & mask))
            return 1;
    }
    return 0;
}

/* ---------------------------------------------------------------------
 * Interrupt configuration.
 * --------------------------------------------------------------------- */

/* gpio_irq_configure() -- per-pin read-modify-write of GPIO_IRQ_TYPE and
 * GPIO_IRQ_POL. Does NOT touch GPIO_IRQ_EN (call gpio_irq_enable()
 * separately) and does NOT clear stale GPIO_IRQ_STAT (see trap #3 above --
 * call gpio_irq_clear_edge() yourself first if the pin was previously an
 * edge pin, or simply expect a level pin's status to already be live/correct
 * once TYPE/POL are set). */
static inline void gpio_irq_configure(unsigned pin, gpio_irq_type_t type, gpio_irq_pol_t pol) {
    uint32_t mask = 1u << pin;
    uint32_t t = gpio_reg_read(GPIO_REG_IRQ_TYPE);
    uint32_t p = gpio_reg_read(GPIO_REG_IRQ_POL);

    if (type == GPIO_IRQ_EDGE)
        t |= mask;
    else
        t &= ~mask;

    if (pol == GPIO_IRQ_POL_HIGH_OR_RISING)
        p |= mask;
    else
        p &= ~mask;

    gpio_reg_write(GPIO_REG_IRQ_TYPE, t);
    gpio_reg_write(GPIO_REG_IRQ_POL, p);
}

static inline void gpio_irq_enable(uint32_t pin_mask) {
    gpio_reg_write(GPIO_REG_IRQ_EN, gpio_reg_read(GPIO_REG_IRQ_EN) | pin_mask);
}

static inline void gpio_irq_disable(uint32_t pin_mask) {
    gpio_reg_write(GPIO_REG_IRQ_EN, gpio_reg_read(GPIO_REG_IRQ_EN) & ~pin_mask);
}

static inline uint32_t gpio_irq_status(void) {
    return gpio_reg_read(GPIO_REG_IRQ_STAT);
}

static inline uint32_t gpio_irq_status_pin(unsigned pin) {
    return (gpio_irq_status() >> pin) & 0x1u;
}

/* gpio_irq_clear_edge() -- write GPIO_IRQ_CLR for the given pin mask.
 *
 * NAMED FOR WHAT IT ACTUALLY DOES: this clears sticky status ONLY for pins
 * currently configured GPIO_IRQ_EDGE. Per gpio_controller.sv, a bit here
 * has NO EFFECT WHATSOEVER on a pin configured GPIO_IRQ_LEVEL -- that pin's
 * status bit simply keeps following its live condition. This is a hardware
 * property, not a driver limitation, and this function does not pretend
 * otherwise by silently no-op'ing under a generic "clear interrupt" name.
 * To silence a level-type interrupt: remove the external condition, or call
 * gpio_irq_disable() on that pin (masks it out of irq_o without touching
 * GPIO_IRQ_STAT). Calling this function on a level pin is a silent,
 * by-design no-op -- if you find yourself doing that, you almost certainly
 * want gpio_irq_disable() instead. */
static inline void gpio_irq_clear_edge(uint32_t edge_pin_mask) {
    gpio_reg_write(GPIO_REG_IRQ_CLR, edge_pin_mask);
}

#endif /* GPIO_H */
