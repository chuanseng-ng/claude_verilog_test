#!/usr/bin/env python3
"""Generate rom_cpu_check.hex for tools/verif/gls/tb_cpu_macro_check.v.

Encodes the fixed 6-instruction RV32I program used by the CPU macro GLS
check (bead claude_verilog_test-b0t part B, 2026-09-18):
  0x00: ADDI x1, x0, 5      -> x1 = 5
  0x04: ADDI x2, x0, 7      -> x2 = 7
  0x08: ADD  x3, x1, x2     -> x3 = 12
  0x0c: ADD  x4, x3, x0     -> x4 = 12 (exercises forwarding)
  0x10: SW   x4, 0(x0)      -> mem[0] = 12 (D$ is write-back, so this does
                                NOT itself generate an AXI write -- see the
                                testbench header comment)
  0x14: JAL  x0, 0          -> self-loop, parks PC

Usage: gen_cpu_check_rom.py <out.hex> [rom_words]
"""
import sys


def addi(rd, rs1, imm):
    imm &= 0xFFF
    return (imm << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0010011


def add(rd, rs1, rs2):
    return (0 << 25) | (rs2 << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0110011


def sw(rs1, rs2, imm):
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (0b010 << 12) | ((imm & 0x1F) << 7) | 0b0100011


def jal(rd, imm):
    imm20 = (imm >> 20) & 1
    imm10_1 = (imm >> 1) & 0x3FF
    imm11 = (imm >> 11) & 1
    imm19_12 = (imm >> 12) & 0xFF
    return (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12) | (rd << 7) | 0b1101111


PROGRAM = [
    addi(1, 0, 5),
    addi(2, 0, 7),
    add(3, 1, 2),
    add(4, 3, 0),
    sw(0, 4, 0),
    jal(0, 0),
]


def main():
    out_path = sys.argv[1]
    rom_words = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    pad = jal(0, 0)  # self-loop, safe filler for speculative/prefetch reads
    with open(out_path, "w") as f:
        for i in range(rom_words):
            v = PROGRAM[i] if i < len(PROGRAM) else pad
            f.write(f"{v:08x}\n")
    print(f"wrote {out_path}: {len(PROGRAM)} real instructions, {rom_words} words total")


if __name__ == "__main__":
    main()
