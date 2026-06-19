#!/usr/bin/env python3
"""
gen_boot_hex.py — generate boot.hex for tb_soc_top boot test.

Boot program (runs from ROM @ 0x0000_1000 after RESET_PC fix):

  Offset  Instruction          Encoding              Notes
  ------  -----------          --------              -----
  +0x00   lui  x1, 0x10       0x00010537  load upper SRAM base (0x0000_2000)
  +0x04   addi x1, x1, 0      0x00008093  x1 = 0x0000_2000  (but lui already sets it)
            -- simpler: use lui+addi --
          lui  x2, 0xDEAD     -- doesn't fit neatly; use two-step below --

  Simplified encoding plan (all RV32I, no pseudo-instruction assembler needed):

  Instruction stream (PC offset from ROM base 0x1000):
  [0]  LUI  x1, 0x1      -> x1 = 0x0000_1000  (ROM base — used as reference)
  [1]  LUI  x2, 0x2      -> x2 = 0x0000_2000  (SRAM base for SW destination)
  [2]  LUI  x3, 0xDEADB  -> x3 = 0xDEADB000   (upper sentinel)
  [3]  ADDI x3, x3, 0xEEF->                    BUT ADDI imm is sign-extended 12-bit
       0xEEF = 3823 → sign bit (bit 11) = 1 → sign-extends to 0xFFFFF_EEF → wrong
       Use ORI instead: x3 = 0xDEADB000 | 0xEEF = 0xDEADBEEF (bit 11 of 0xEEF is 1)
       Actually 0xEEF has bit11=1 so upper gets -1 adjusted.
       Strategy: lui loads upper 20 bits (the imm is bits[31:12]).
         Target: 0xDEAD_BEEF
         Upper 20 bits: 0xDEADB (= 0xDEAD_B000 when shifted)
         Lower 12 bits: 0xEEF  (but sign-extended from 12-bit = -273 = 0xFFFFFEEF)
         Compensation:  lui imm must be upper20 + 1 if lower12 has bit11 set.
         0xEEF bit11 = 1, so add 1 to upper: 0xDEADC
         Then addi -273 (0xEEF sign-extended): 0xDEADC000 + (-273) = 0xDEADB_EEF -- close
         0xDEADC000 - 0x111 = 0xDEADBEEF? No: 0xDEADC000 - 0x111 = 0xDEAD_BEEF ?
         0xDEADC000 = 3740893184; -0x111 = -273; 3740893184 - 273 = 3740892911 = 0xDEAD_BEEF?
         0xDEAD_BEEF = 3735928559; 0xDEADC000 - 0x111 = 3735929088 - 273 = 3735928815 ≠ 0xDEADBEEF
         Let me compute properly:
           0xDEAD_BEEF = 1101_1110_1010_1101_1011_1110_1110_1111
           upper 20: 0xDEADB  (bits [31:12])
           lower 12: 0xEEF    (bits [11:0])
           0xEEF sign-extended in 12 bits: bit11=1 → negative → -0x111 = -273
           lui compensation: upper_imm = 0xDEADB + 1 = 0xDEADC
           addi imm = 0xEEF (as 12-bit 2's complement = -273 = 0xFFFFFEEF)
           Result: 0xDEADC000 + sign_ext(0xEEF) = 0xDEADC000 - 0x111 = ?
           0xDEADC000 = 3735932928
           0x111 = 273
           3735932928 - 273 = 3735932655 = 0xDEAD_BEEF?
           0xDEAD_BEEF = 3735928559 (from python: 0xDEADBEEF)
           3735932655 ≠ 3735928559 → difference is 4096 → wrong
         Correct: sign_ext(0xEEF) in 12-bit: 0xEEF = 3823; bit11 = 1 so negative:
           3823 - 4096 = -273. In 32-bit: 0xFFFF_FEEF
         lui imm=0xDEADC → loads 0xDEADC000 into x3
         addi x3, x3, 0xEEF (as signed 12-bit = -273) → 0xDEADC000 - 273 = ?
           0xDEADC000 = 0xDEAD_C000; subtract 273 = 0x111
           0xDEADC000 - 0x111 = 0xDEADBEEF?
           0xDEAD_C000 = D E A D C 0 0 0
           -           0 0 0 0 1 1 1
           = D E A D B E E F  ← YES! 0xDEAD_BEEF ✓

  Revised sequence:
  [0]  LUI  x2, 0x2       -> x2 = 0x0000_2000  (SRAM write addr)
  [1]  LUI  x3, 0xDEADC   -> x3 = 0xDEADC000
  [2]  ADDI x3, x3, -273  -> x3 = 0xDEADBEEF  (sentinel value)
  [3]  SW   x3, 0(x2)     -> mem[0x2000] = 0xDEADBEEF
  [4]  ADDI x2, x2, 4     -> x2 = 0x0000_2004  (second SRAM word)
  [5]  LUI  x4, 0xCAFEB   -> x4 = 0xCAFEB000   (second sentinel upper)
  [6]  ADDI x4, x4, -769  -> x4 = 0xCAFEBABE?
         0xCAFE_BABE: upper=0xCAFEB, lower=0xABE=2750; bit11=1 → -1346
         Compensation: 0xCAFEB+1=0xCAFEC
         0xCAFEC000 - 1346 = 0xCAFEC000 - 0x542 = 0xCAFEBABE?
         0xCAFEC000 = 3405783040; -0x542 = -1346; 3405783040 - 1346 = 3405781694 = 0xCAFEBABE?
         0xCAFEBABE = 3405691582; difference = 3405783040-3405691582 = 91458 ≠ 1346
         Let's use a simpler sentinel instead: 0x12345678
         upper=0x12345 (bit19:0 of upper imm); lower=0x678=1656; bit11=0 → positive
         lui imm=0x12345 → 0x12345000; addi +0x678 = 0x12345678 ✓

  Final clean sequence:
  [0]  LUI  x2, 0x2        -> x2 = 0x0000_2000   (SRAM word-0 addr)
  [1]  LUI  x3, 0xDEADC    -> x3 = 0xDEADC000
  [2]  ADDI x3, x3, -273   -> x3 = 0xDEAD_BEEF   (sentinel 0)
  [3]  SW   x3, 0(x2)      -> store sentinel 0 at SRAM[0x2000]
  [4]  LUI  x4, 0x12345    -> x4 = 0x12345000
  [5]  ADDI x4, x4, 0x678  -> x4 = 0x12345678    (sentinel 1, bit11=0 so no compensation)
  [6]  SW   x4, 4(x2)      -> store sentinel 1 at SRAM[0x2004]
  [7]  EBREAK               -> halt (trap to debug)

Encoding reference (RV32I):
  LUI  rd, imm20   : imm[31:12] | rd[4:0] | 0110111
  ADDI rd,rs1,imm12: imm[11:0]  | rs1[4:0]| 000 | rd[4:0] | 0010011
  SW   rs2,imm(rs1): imm[11:5] | rs2[4:0] | rs1[4:0] | 010 | imm[4:0] | 0100011
  EBREAK           : 000000000001 | 00000 | 000 | 00000 | 1110011
"""

import struct
import os


ROM_BASE   = 0x0000_1000
ROM_WORDS  = 1024          # 4 KB / 4 bytes
SRAM_BASE  = 0x0000_2000


def encode_lui(rd: int, imm20: int) -> int:
    """LUI rd, imm20  (imm20 is bits[31:12] of the loaded value)."""
    assert 0 < rd < 32
    assert 0 <= imm20 < (1 << 20), f"imm20 out of range: {imm20:#x}"
    return (imm20 << 12) | (rd << 7) | 0b0110111


def encode_addi(rd: int, rs1: int, imm12: int) -> int:
    """ADDI rd, rs1, imm12  (imm12 is a signed 12-bit integer)."""
    assert 0 <= rd < 32 and 0 <= rs1 < 32
    assert -2048 <= imm12 <= 2047, f"imm12 out of range: {imm12}"
    uimm = imm12 & 0xFFF
    return (uimm << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0010011


def encode_sw(rs2: int, rs1: int, imm12: int) -> int:
    """SW rs2, imm12(rs1)  (imm12 is a signed 12-bit byte offset)."""
    assert 0 <= rs2 < 32 and 0 <= rs1 < 32
    assert -2048 <= imm12 <= 2047, f"imm12 out of range: {imm12}"
    uimm = imm12 & 0xFFF
    imm_11_5 = (uimm >> 5) & 0x7F
    imm_4_0  = uimm & 0x1F
    return (imm_11_5 << 25) | (rs2 << 20) | (rs1 << 15) | (0b010 << 12) | (imm_4_0 << 7) | 0b0100011


EBREAK = 0x00100073


def encode_csrrw(rd: int, csr: int, rs1: int) -> int:
    """CSRRW rd, csr, rs1  — CSR read/write (funct3=001)."""
    assert 0 <= rd < 32 and 0 <= rs1 < 32
    assert 0 <= csr < 0x1000, f"CSR out of range: {csr:#x}"
    return (csr << 20) | (rs1 << 15) | (0b001 << 12) | (rd << 7) | 0b1110011


# CSR addresses for D-cache maintenance (from rv32i_csr_file.sv)
CSR_DCACHE_FLUSH = 0x7C0   # CSRW 0x7C0 triggers full D-cache flush-all


def build_boot_program() -> list[int]:
    """Return list of 32-bit instruction words for the boot program.

    Assumptions (valid after the RESET_PC RTL fix):
      - CPU starts fetching from ROM_BASE (0x0000_1000)
      - SRAM is accessible at SRAM_BASE (0x0000_2000)

    Program:
      x2 = SRAM_BASE                          (store-address register)
      x3 = 0xDEAD_BEEF                        (sentinel word 0)
      SW  x3, 0(x2)   -> D-cache[0x2000] = 0xDEAD_BEEF (dirty line)
      x4 = 0x1234_5678                        (sentinel word 1)
      SW  x4, 4(x2)   -> D-cache[0x2004] = 0x12345678  (dirty line)
      CSRRW x0, 0x7C0, x0  -> flush D-cache: write dirty lines back to SRAM
      EBREAK                -> halt

    The D-cache flush (CSRRW 0x7C0) is required before EBREAK because the
    D-cache is write-back: SW populates a dirty cache line which is not
    propagated to the physical SRAM until an explicit flush or eviction.
    Without the flush, the SRAM backing store remains all-zero even though
    the software correctly stored the sentinel values.
    """
    insns: list[int] = []

    # x2 = 0x0000_2000
    insns.append(encode_lui(2, 0x2))               # LUI x2, 0x2  -> 0x00002000

    # x3 = 0xDEAD_BEEF
    # lower 12 bits: 0xEEF=3823 → bit11=1 → signed = -273
    # so compensate upper: 0xDEADB+1 = 0xDEADC
    insns.append(encode_lui(3, 0xDEADC))           # LUI x3, 0xDEADC -> 0xDEADC000
    insns.append(encode_addi(3, 3, -0x111))        # ADDI x3,x3,-273 -> 0xDEADBEEF

    # SW x3, 0(x2)  — writes sentinel 0 into D-cache dirty line
    insns.append(encode_sw(3, 2, 0))               # D-cache[0x2000] = 0xDEAD_BEEF

    # x4 = 0x1234_5678
    # lower 12 bits: 0x678=1656 → bit11=0 → no compensation needed
    insns.append(encode_lui(4, 0x12345))           # LUI x4, 0x12345 -> 0x12345000
    insns.append(encode_addi(4, 4, 0x678))         # ADDI x4,x4,0x678 -> 0x12345678

    # SW x4, 4(x2)  — writes sentinel 1 into same D-cache dirty line
    insns.append(encode_sw(4, 2, 4))               # D-cache[0x2004] = 0x12345678

    # CSRRW x0, 0x7C0, x0  — flush D-cache: write-back all dirty lines to SRAM
    # This stalls the pipeline while the flush-all FSM walks all 256 cache lines.
    # After this instruction commits, all dirty lines are in the SRAM backing store.
    insns.append(encode_csrrw(0, CSR_DCACHE_FLUSH, 0))

    # EBREAK — trap to debugger / halt
    insns.append(EBREAK)

    return insns


def verify_encoding(insns: list[int]) -> None:
    """Sanity-check the encoded values against known constants."""
    assert len(insns) == 9, f"Expected 9 instructions, got {len(insns)}"

    # Decode x2 LUI: should give 0x00002000
    lui_x2 = insns[0]
    assert lui_x2 & 0x7F == 0b0110111, "LUI opcode wrong"
    assert (lui_x2 >> 7) & 0x1F == 2, "LUI rd must be x2"
    assert (lui_x2 >> 12) == 0x2, f"LUI imm20 wrong: {(lui_x2>>12):#x}"

    # Verify sentinel 0xDEADBEEF is built correctly by Python arithmetic
    x3 = ((0xDEADC << 12) + ((-0x111) & 0xFFFFFFFF)) & 0xFFFFFFFF
    assert x3 == 0xDEADBEEF, f"sentinel 0 wrong: {x3:#010x}"

    # Verify sentinel 0x12345678
    x4 = ((0x12345 << 12) + 0x678) & 0xFFFFFFFF
    assert x4 == 0x12345678, f"sentinel 1 wrong: {x4:#010x}"

    # Verify CSRRW x0, 0x7C0, x0 encoding
    csrrw = insns[7]
    assert csrrw == (CSR_DCACHE_FLUSH << 20) | (0 << 15) | (0b001 << 12) | (0 << 7) | 0b1110011, \
        f"CSRRW x0,0x7C0,x0 encoding wrong: {csrrw:#010x}"

    print("Encoding verification PASS")
    print(f"  Sentinel 0: 0x{0xDEADBEEF:08X}")
    print(f"  Sentinel 1: 0x{0x12345678:08X}")
    print(f"  SRAM addr 0: 0x{SRAM_BASE:08X}")
    print(f"  SRAM addr 1: 0x{SRAM_BASE+4:08X}")


def write_hex(insns: list[int], path: str) -> None:
    """Write instructions as $readmemh-compatible hex file.

    Format: one 8-hex-digit word per line, starting at word offset 0
    (i.e. byte address ROM_BASE).  The ROM is 1024 words; pad remainder
    with NOP (ADDI x0,x0,0 = 0x00000013) so $readmemh fills the array.
    """
    NOP = 0x00000013
    words = list(insns)
    # Pad to full ROM depth
    words.extend([NOP] * (ROM_WORDS - len(words)))

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        for w in words:
            f.write(f"{w:08x}\n")
    print(f"Wrote {len(words)} words to {path}")
    print(f"  First {len(insns)} words are program instructions:")
    for i, w in enumerate(insns):
        print(f"    [{i}] 0x{w:08x}  (PC=0x{ROM_BASE + i*4:08x})")


if __name__ == "__main__":
    insns = build_boot_program()
    verify_encoding(insns)
    out_path = os.path.join(os.path.dirname(__file__), "boot.hex")
    write_hex(insns, out_path)
    print(f"\nboot.hex ready: {out_path}")
    print("Expected final state after boot program completes:")
    print(f"  SRAM[0x{SRAM_BASE:08X}] = 0xDEADBEEF")
    print(f"  SRAM[0x{SRAM_BASE+4:08X}] = 0x12345678")
