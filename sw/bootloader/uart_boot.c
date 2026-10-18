/* uart_boot.c -- 4 KB boot-ROM UART bootloader for the RV32I SoC (bead hlrm.2).
 *
 * Runs from the boot ROM at RESET_PC 0x0000_1000, receives framed, CRC32-protected
 * blocks over the existing uart_controller (APB slot 0, 0x2000_2000) into main SRAM and
 * jumps to the loaded image.  Protocol: uart_boot_proto.h.  Build/usage: README.md.
 *
 * Constraints honoured here:
 *   - RV32I + Zicsr only (no M extension): no multiply/divide, no libgcc.
 *   - No initialised data (nothing copies ROM->RAM): state is zero-init .bss in SRAM.
 *   - The loaded image lives in SRAM [BL_LOAD_LO, BL_LOAD_HI); the bootloader's own
 *     .bss/stack sit above it and are never written by a WRITE command.
 */
#include <stdint.h>

#include "bl_config.h"
#include "uart_boot_proto.h"

/* ---- uart_controller register map (rtl/periph/uart_controller.sv) ------------------- */
#define UART_BASE        0x20002000u
#define UART_TX          (*(volatile uint32_t *)(UART_BASE + 0x00u))
#define UART_RX          (*(volatile uint32_t *)(UART_BASE + 0x04u))
#define UART_STATUS      (*(volatile uint32_t *)(UART_BASE + 0x08u))
#define UART_CTRL        (*(volatile uint32_t *)(UART_BASE + 0x0Cu))
#define UART_BAUD        (*(volatile uint32_t *)(UART_BASE + 0x10u))
#define ST_TX_BUSY       (1u << 0)
#define ST_TX_FULL       (1u << 1)
#define ST_TX_EMPTY      (1u << 2)
#define ST_RX_EMPTY      (1u << 3)
#define CTRL_TX_RX_EN    0x3u

/* ---- CPU cache maintenance CSRs (docs/design/PHASE5_MMIO_UNCACHED_DECISION.md) ------- */
#define CSR_DCACHE_FLUSH 0x7C0   /* write: write back every dirty D$ line */
#define CSR_DCACHE_INVAL 0x7C1   /* write: drop every D$ line (no write-back) */

#define IDLE_CYCLES      ((BL_CPU_HZ / 1000u) * BL_IDLE_MS)
#define AUTOBOOT_CYCLES  ((BL_CPU_HZ / 1000u) * BL_AUTOBOOT_MS)
#define RX_NONE          (-1)

static uint8_t rxbuf[4u + BL_MAX_DATA];

static inline uint32_t cycle_now(void)
{
    uint32_t v;
    __asm__ volatile("csrr %0, 0xB00" : "=r"(v));   /* mcycle */
    return v;
}

/* ---- UART -------------------------------------------------------------------------- */
static void uart_putc(uint8_t c)
{
    while (UART_STATUS & ST_TX_FULL) {
    }
    UART_TX = c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        uart_putc((uint8_t)*s++);
    }
}

static void uart_drain(void)
{
    while ((UART_STATUS & (ST_TX_EMPTY | ST_TX_BUSY)) != ST_TX_EMPTY) {
    }
}

/* Next received byte, or RX_NONE after `limit` cycles of silence (limit 0 = wait forever). */
static int rx_byte(uint32_t limit)
{
    uint32_t t0 = cycle_now();
    while (UART_STATUS & ST_RX_EMPTY) {
        if (limit != 0u && (cycle_now() - t0) >= limit) {
            return RX_NONE;
        }
    }
    return (int)(UART_RX & 0xFFu);   /* the read pops the FIFO */
}

/* ---- CRC32 (IEEE 802.3, reflected, same as zlib.crc32) -------------------------------------- */
/* Nibble-table form: 64 B of ROM and two table steps per byte.  The bitwise form (8 shift/xor
 * steps per byte) is ~3x slower, which mattered: the receive loop must keep up with the line rate
 * between UART_STATUS/UART_RX reads that each cross the CPU->fabric clock-domain bridge. */
static const uint32_t crc_nib[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u,
    0x4DB26158u, 0x5005713Cu, 0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu,
    0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu,
};

static uint32_t crc32_byte(uint32_t crc, uint8_t b)
{
    crc ^= b;
    crc = (crc >> 4) ^ crc_nib[crc & 0xFu];
    crc = (crc >> 4) ^ crc_nib[crc & 0xFu];
    return crc;
}

static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* ---- responses ----------------------------------------------------------------------- */
static void send_nak(uint8_t err)
{
    uart_putc(BL_NAK);
    uart_putc(err);
}

static void send_ack(const uint8_t *p, uint8_t n)
{
    uart_putc(BL_ACK);
    uart_putc(n);
    while (n--) {
        uart_putc(*p++);
    }
}

static void put_le32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

/* ---- cache hand-off ------------------------------------------------------------------- */
/* Write back every dirty D$ line, optionally drop them all, and give the maintenance FSM
 * time to finish.  The pipeline already stalls on the CSR write; the spin matches
 * sw/bench/crt0.S (flush then 2048-iteration drain) and costs ~0.1 ms at 50 MHz.
 *
 * One asm block, register-only spin: after the flush NOTHING may store to memory before the
 * invalidate, because the invalidate discards dirty lines without write-back.  A C `volatile`
 * loop counter would dirty the stack line, and the invalidate would then roll back this frame's
 * (and the callers') saved registers -- the CRC command hung exactly that way. */
static void dcache_sync(int invalidate)
{
    __asm__ volatile(
        "fence\n"
        "csrw 0x7C0, x0\n"      /* dcache_flush */
        "li t0, 2048\n"
        "1: addi t0, t0, -1\n"
        "bnez t0, 1b\n"
        "beqz %0, 3f\n"
        "csrw 0x7C1, x0\n"      /* dcache_inval: every line is clean now */
        "li t0, 512\n"
        "2: addi t0, t0, -1\n"
        "bnez t0, 2b\n"
        "3:\n"
        :
        : "r"(invalidate)
        : "t0", "memory");
}

/* FENCE.I (0x0000100F) as a raw word: the project's -march=rv32i_zicsr has no Zifencei. */
static void icache_invalidate(void)
{
    __asm__ volatile(".word 0x0000100F" ::: "memory");
}

static __attribute__((noreturn)) void run_image(uint32_t entry)
{
    uart_drain();
    dcache_sync(0);        /* image bytes are dirty in the write-back D$: push them to SRAM */
    icache_invalidate();   /* then make the I$ refetch them */
    ((void (*)(void))entry)();
    for (;;) {
    }
}

/* ---- address policy ------------------------------------------------------------------- */
static int region_ok(uint32_t addr, uint32_t n)
{
    return addr >= BL_LOAD_LO && addr <= BL_LOAD_HI && n <= (BL_LOAD_HI - addr);
}

/* ---- command handlers ------------------------------------------------------------------ */
static void do_info(void)
{
    uint8_t r[11];
    r[0] = BL_PROTO_VERSION;
    r[1] = (uint8_t)BL_MAX_DATA;
    r[2] = (uint8_t)(BL_MAX_DATA >> 8);
    put_le32(&r[3], BL_LOAD_LO);
    put_le32(&r[7], BL_LOAD_HI);
    send_ack(r, sizeof r);
}

static void do_write(uint32_t len)
{
    uint32_t addr = le32(rxbuf);
    uint32_t n = len - 4u;
    if (!region_ok(addr, n)) {
        send_nak(BL_ERR_ADDR);
        return;
    }
    volatile uint8_t *dst = (volatile uint8_t *)addr;
    for (uint32_t i = 0; i < n; i++) {
        dst[i] = rxbuf[4u + i];
    }
    send_ack(rxbuf, 0);
}

static void do_crc(void)
{
    uint32_t addr = le32(rxbuf);
    uint32_t n = le32(rxbuf + 4);
    if (!region_ok(addr, n)) {
        send_nak(BL_ERR_ADDR);
        return;
    }
    /* Read the region back from SRAM itself, not from the D$ copy that was just written. */
    dcache_sync(1);
    const volatile uint8_t *src = (const volatile uint8_t *)addr;
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < n; i++) {
        crc = crc32_byte(crc, src[i]);
    }
    crc = ~crc;
    uint8_t r[4];
    put_le32(r, crc);
    send_ack(r, sizeof r);
}

static void do_jump(void)
{
    uint32_t entry = le32(rxbuf);
    if ((entry & 3u) != 0u || !region_ok(entry, 0u) || entry == BL_LOAD_HI) {
        send_nak(BL_ERR_ADDR);
        return;
    }
    send_ack(rxbuf, 0);
    run_image(entry);
}

/* ---- frame receive ---------------------------------------------------------------------- */
/* Receive and dispatch one frame.  Returns 0 if no byte arrived within the auto-boot window. */
static int serve_one(int first)
{
    uint32_t limit = (first && AUTOBOOT_CYCLES != 0u) ? AUTOBOOT_CYCLES : 0u;
    int c;
    do {                                   /* hunt for SOF, ignore line noise */
        c = rx_byte(limit);
        if (c == RX_NONE) {
            return 0;
        }
        limit = 0u;
    } while (c != BL_SOF);

    uint32_t crc = 0xFFFFFFFFu;
    uint8_t hdr[3];
    for (uint32_t i = 0; i < 3u; i++) {
        c = rx_byte(IDLE_CYCLES);
        if (c == RX_NONE) {
            send_nak(BL_ERR_TIMEOUT);
            return 1;
        }
        hdr[i] = (uint8_t)c;
        crc = crc32_byte(crc, hdr[i]);
    }
    uint32_t len = (uint32_t)hdr[1] | ((uint32_t)hdr[2] << 8);
    if (len > sizeof rxbuf) {
        send_nak(BL_ERR_LEN);              /* cannot skip a frame of unknown extent: host resyncs */
        return 1;
    }
    for (uint32_t i = 0; i < len + 4u; i++) {   /* payload then the 4 CRC bytes */
        c = rx_byte(IDLE_CYCLES);
        if (c == RX_NONE) {
            send_nak(BL_ERR_TIMEOUT);
            return 1;
        }
        if (i < len) {
            rxbuf[i] = (uint8_t)c;
        }
        /* The 4 CRC bytes are folded in last: a good frame leaves the raw CRC register at
         * the fixed residue 0xDEBB20E3, so no 4-byte compare buffer is needed. */
        crc = crc32_byte(crc, (uint8_t)c);
    }
    if (crc != 0xDEBB20E3u) {
        send_nak(BL_ERR_CRC);
        return 1;
    }

    switch (hdr[0]) {
    case BL_CMD_INFO:
        if (len != 0u) { send_nak(BL_ERR_LEN); } else { do_info(); }
        break;
    case BL_CMD_WRITE:
        if (len < 5u) { send_nak(BL_ERR_LEN); } else { do_write(len); }
        break;
    case BL_CMD_CRC:
        if (len != 8u) { send_nak(BL_ERR_LEN); } else { do_crc(); }
        break;
    case BL_CMD_JUMP:
        if (len != 4u) { send_nak(BL_ERR_LEN); } else { do_jump(); }
        break;
    default:
        send_nak(BL_ERR_CMD);
        break;
    }
    return 1;
}

int main(void)
{
    UART_BAUD = BL_UART_DIV;
    UART_CTRL = CTRL_TX_RX_EN;
    uart_puts(BL_BANNER);

    int first = 1;
    for (;;) {
        if (!serve_one(first)) {
            /* Auto-boot window expired with a silent host. Only jump to something that
             * looks like code (SRAM is not initialised after an FPGA configuration). */
            uint32_t w = *(volatile uint32_t *)BL_AUTOBOOT_ADDR;
            if (w != 0u && w != 0xFFFFFFFFu) {
                run_image(BL_AUTOBOOT_ADDR);
            }
            first = 0;                     /* nothing to boot: wait for the host forever */
        } else {
            first = 0;
        }
    }
}
