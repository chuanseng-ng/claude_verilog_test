# crt0.S -- ROM start-up for the UART bootloader (RESET_PC = 0x0000_1000).
# Code and rodata live in ROM; .bss and the stack live in the top of SRAM.
    .section .text.init, "ax"
    .global _start
_start:
    la   sp, __stack_top
    la   t0, __bss_start
    la   t1, __bss_end
1:  bgeu t0, t1, 2f
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    1b
2:  call main
3:  ebreak
    j    3b
