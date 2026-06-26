# trampoline.S — ROM boot stub at RESET_PC (0x0000_1000).
#
# The boot ROM is only 4 KB (1024 words) — far too small for Dhrystone/CoreMark.
# So the ROM holds just this 2-instruction jump to the benchmark entry in SRAM
# at 0x0000_2000, where crt0 (_start) lives. Assembled standalone and emitted as
# its own ROM hex image (loaded into u_boot_rom.mem); the benchmark image is
# loaded separately into u_sram.mem.

    .section .text.init, "ax"
    .global _start
_start:
    lui  t0, 0x2          # t0 = 0x00002000  (SRAM benchmark entry)
    jr   t0               # jalr x0, 0(t0)
