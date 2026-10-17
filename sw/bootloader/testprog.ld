/* testprog.ld -- test payload linked into SRAM at 0x2000 (bootloader load region). */
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x00002000, LENGTH = 0x1000 }
__stack_top = ORIGIN(RAM) + LENGTH(RAM);   /* bootloader RAM is free once we are running */
SECTIONS
{
  .text : { KEEP(*(.text.init)) *(.text .text.*) *(.rodata .rodata.*) *(.srodata .srodata.*) . = ALIGN(4); } > RAM
  .data : { *(.data .data.* .sdata .sdata.*) } > RAM
  .bss (NOLOAD) : { __bss_start = .; *(.sbss .sbss.*) *(.bss .bss.*) *(COMMON) . = ALIGN(4); __bss_end = .; } > RAM
  /DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame) }
}
