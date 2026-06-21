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

    # Park exit code, flush D-cache to SRAM, then halt.
    #
    # The D-cache is write-back: bench_report() scratch writes (0x41C00 region)
    # and __result may still be dirty in the cache at this point.  The cocotb
    # harness backdoor-reads u_sram.mem[] after EBREAK, so we must write back
    # all dirty lines before halting.
    #
    # Flush sequence (mirrors _emit_dcache_flush in gen_stress_hex.py):
    #   1. sw a0 → __result  (the only pending store; must complete before flush
    #      so CSRRW is not in EX while a cache-stall is in MEM — see obs 4867)
    #   2. csrw 0x7C0, x0   → fires dc_flush_pulse; FSM begins scanning 256 lines
    #   3. drain spin ~2048 iterations ≥ 256-line scan + AXI write-back bursts
    #   4. fence             → memory ordering barrier
    #   5. ebreak            → halt (loop on it)
    #
    # Registers: t0/t1 were used for .bss zeroing and are free here.  a0 holds
    # the return value and must not be clobbered before the sw.
    la   t0, __result
    sw   a0, 0(t0)

    # D-cache flush: CSRW 0x7C0, x0  (encodes to 7c001073)
    # CSR 0x7C0 = dcache_flush (go9/M9 maintenance CSR, rv32i_csr_file.sv).
    # rs1=x0 triggers an unconditional flush (do_fire=1 for CSRRW regardless
    # of rs1 value; FSM scans all 256 lines and write-backs dirty ones).
    csrw 0x7C0, x0

    # Drain spin: 2048 countdown iterations — gives the flush FSM time to
    # scan all 256 D-cache lines and drain the resulting AXI4 write-back
    # bursts to the SRAM before we halt.  Matches gen_stress_hex.py spin=2048.
    li   t0, 2048
4:  addi t0, t0, -1
    bnez t0, 4b

    fence
3:  ebreak
    j    3b

    .section .data
    .global __result
    .align 2
__result:
    .word 0xFFFFFFFF
