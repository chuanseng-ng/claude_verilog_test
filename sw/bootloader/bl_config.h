/* bl_config.h -- build-time configuration of the UART bootloader.
 * Every value can be overridden with -D on the compiler command line (see Makefile).
 */
#ifndef BL_CONFIG_H
#define BL_CONFIG_H

/* UART reference clock (the fabric clock that feeds uart_controller) and line rate.
 * FPGA plan: 50 MHz / 115200.  ASIC (Sky130 SoC, 25 ns period): -DBL_UART_CLK_HZ=40000000 */
#ifndef BL_UART_CLK_HZ
#define BL_UART_CLK_HZ   50000000u
#endif
#ifndef BL_BAUD
#define BL_BAUD          115200u
#endif
/* uart_controller: 1 serial bit = 16*(UART_BAUD+1) clocks.  Rounded to nearest. */
#ifndef BL_UART_DIV
#define BL_UART_DIV      (((BL_UART_CLK_HZ + 8u * BL_BAUD) / (16u * BL_BAUD)) - 1u)
#endif

/* CPU clock, used only to convert the mcycle CSR into timeouts. */
#ifndef BL_CPU_HZ
#define BL_CPU_HZ        50000000u
#endif
/* Silence inside a frame longer than this aborts it (NAK TIMEOUT).  Must be far
 * larger than one byte time (87 us at 115200). */
#ifndef BL_IDLE_MS
#define BL_IDLE_MS       20u
#endif
/* 0 = wait for the host forever.  >0 = if no byte at all arrives within this many ms
 * after reset, jump to BL_AUTOBOOT_ADDR (only if the word there is not 0 / 0xFFFFFFFF). */
#ifndef BL_AUTOBOOT_MS
#define BL_AUTOBOOT_MS   0u
#endif
#ifndef BL_AUTOBOOT_ADDR
#define BL_AUTOBOOT_ADDR 0x00002000u
#endif

/* SRAM geometry.  Main SRAM starts at 0x2000 and is SRAM_MEM_WORDS*4 bytes (4 KB today).
 * The top BL_RAM_BYTES of it hold the bootloader's .bss, receive buffer and stack. */
#ifndef BL_SRAM_BASE
#define BL_SRAM_BASE     0x00002000u
#endif
#ifndef BL_SRAM_BYTES
#define BL_SRAM_BYTES    4096u
#endif
#ifndef BL_RAM_BYTES
#define BL_RAM_BYTES     512u
#endif
/* Largest WRITE data block (payload = 4 address bytes + data). */
#ifndef BL_MAX_DATA
#define BL_MAX_DATA      128u
#endif

#define BL_LOAD_LO       (BL_SRAM_BASE)
#define BL_LOAD_HI       (BL_SRAM_BASE + BL_SRAM_BYTES - BL_RAM_BYTES)

#endif
