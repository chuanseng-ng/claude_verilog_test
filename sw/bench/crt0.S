# crt0.S — minimal RV32I bare-metal startup for SoC cache benchmarks (Phase 5 M10).
#
# Linked at 0x0000_2000 (SRAM) as .text.init so it is the trampoline's jump target.
# Sets the stack, zeroes .bss, calls main(), parks main()'s return value where the
# cocotb harness can backdoor-read it, then halts with EBREAK (the SoC CPU's halt
# convention, same as every other firmware in tb/cocotb/soc/).
#
# Result handoff: main()'s a0 is stored to __result (a word in .data). The harness
# resolves the symbol address from the .elf and reads SRAM[(addr-0x2000)/4].
# Benchmarks that report perf counters write their own scratch words from C via the
# read_csr() helper in bench.h; this __result word is just the top-level exit code.

    .section .text.init, "ax"
    .global _start
_start:
    # Global/stack pointers. .option norelax so gp load isn't relaxed away before
    # gp is actually set.
.option push
.option norelax
    la   gp, __global_pointer$
.option pop
    la   sp, __stack_top

    # Zero .bss [__bss_start, __bss_end)
    la   t0, __bss_start
    la   t1, __bss_end
1:  bgeu t0, t1, 2f
    sw   zero, 0(t0)
    addi t0, t0, 4
    j    1b
2:

    # main()
    li   a0, 0
    li   a1, 0
    call main

    # Park exit code, then halt.
    la   t0, __result
    sw   a0, 0(t0)
    fence
3:  ebreak
    j    3b

    .section .data
    .global __result
    .align 2
__result:
    .word 0xFFFFFFFF
