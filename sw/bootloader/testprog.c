/* testprog.c -- tiny payload for the bootloader tests: proves that a loaded image runs and
 * that its read-only data survived the load.  Linked at 0x2000 (testprog.ld), prints
 * "PAYLOAD OK <sum32 of table>\n" on the UART, then halts with EBREAK. */
#include <stdint.h>

#define UART_TX      (*(volatile uint32_t *)0x20002000u)
#define UART_STATUS  (*(volatile uint32_t *)0x20002008u)

static const uint32_t table[32] = {
#include "testprog_table.inc"
};

static void putc_(char c)
{
    while (UART_STATUS & 2u) {
    }
    UART_TX = (uint32_t)(uint8_t)c;
}

int main(void)
{
    uint32_t sum = 0;
    for (uint32_t i = 0; i < 32u; i++) {
        sum += table[i];
    }
    for (const char *s = "PAYLOAD OK "; *s; s++) {
        putc_(*s);
    }
    for (int sh = 28; sh >= 0; sh -= 4) {
        uint32_t d = (sum >> sh) & 0xFu;
        putc_((char)(d < 10u ? '0' + d : 'A' + d - 10u));
    }
    putc_('\n');
    for (;;) {
        __asm__ volatile("ebreak");
    }
}
