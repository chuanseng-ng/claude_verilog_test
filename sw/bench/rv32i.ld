/* rv32i.ld — bare-metal link map for SoC cache benchmarks (Phase 5 M10).
 *
 * The whole image (.text/.rodata/.data/.bss) is linked into main SRAM at
 * 0x0000_2000 and backdoor-loaded there by the cocotb harness, so LMA == VMA
 * (no ROM->RAM .data copy needed). A 2-instruction ROM trampoline at 0x0000_1000
 * (RESET_PC) jumps here. Running from SRAM (cacheable region, vs uncached MMIO
 * at 0x2000_0000+) is deliberate: it routes all I-fetch and data traffic through
 * the L1 caches so mhpmcounter3/4 measure real miss behaviour.
 *
 * SRAM spans 0x0000_2000 .. 0x0FFF_FFFF. We give code+data the low region and
 * put the stack top at just below the bench scratch region, leaving generous room
 * for working-set sweeps that deliberately exceed the 4 KB direct-mapped L1.
 */

ENTRY(_start)

/* The behavioral SRAM (rtl/soc/sram_controller.sv) realises only its low MEM_WORDS
 * words and ALIASES higher addresses (index masked to IDX_W). So every linked
 * address — code, data, stack, the bench scratch block — must stay within the
 * realised window. The bench testbench instantiates SRAM with MEM_WORDS=65536
 * (256 KB: 0x0000_2000 .. 0x0004_2000); keep this map and that override in sync.
 *
 * Scratch region (1 KB, 256 words): 0x41C00..0x41FFF — reserved for bench.h
 * multi-slot append protocol (up to 31 records, 8 words each + 1 header word).
 * Stack grows down from 0x41C00. 64 KB of working-set sweep still fits
 * comfortably below the stack (sweep .bss buffer ends ~0x122A8). */
MEMORY
{
  RAM (rwxai) : ORIGIN = 0x00002000, LENGTH = 0x0003EC00  /* 0x2000 .. 0x41C00 */
}

__stack_top = 0x00041C00;   /* grows down; bench scratch occupies 0x41C00..0x41FFF */

SECTIONS
{
  . = ORIGIN(RAM);

  .text : {
    KEEP(*(.text.init))     /* crt0 _start MUST be first => lands at 0x2000 */
    *(.text .text.*)
    *(.rodata .rodata.*)
    *(.srodata .srodata.*)
  } > RAM

  . = ALIGN(4);
  .data : {
    __data_start = .;
    /* gp points 0x800 into the small-data window so [gp-0x800, gp+0x7FF]
     * reaches .sdata/.sbss with signed 12-bit offsets. */
    PROVIDE(__global_pointer$ = . + 0x800);
    *(.data .data.*)
    *(.sdata .sdata.*)
    __data_end = .;
  } > RAM

  . = ALIGN(4);
  .bss (NOLOAD) : {
    __bss_start = .;
    *(.sbss .sbss.*)
    *(.bss .bss.*)
    *(COMMON)
    __bss_end = .;
  } > RAM

  . = ALIGN(16);
  __heap_start = .;

  /DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame) }
}
