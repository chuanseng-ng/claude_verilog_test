#!/usr/bin/env python3
"""
gen_boot_hex.py -- generate boot.hex for the tb_soc_top boot test.

The program runs from ROM at 0x0000_1000. It uses RV32I only; the generator encodes it by hand.

  [0]  LUI   x2, 0x2        -> x2 = 0x0000_2000   (SRAM word-0 address)
  [1]  LUI   x3, 0xDEADC    -> x3 = 0xDEADC000
  [2]  ADDI  x3, x3, -273   -> x3 = 0xDEAD_BEEF   (sentinel 0)
  [3]  SW    x3, 0(x2)      -> sentinel 0 in a dirty D-cache line for SRAM[0x2000]
  [4]  LUI   x4, 0x12345    -> x4 = 0x12345000
  [5]  ADDI  x4, x4, 0x678  -> x4 = 0x12345678    (sentinel 1, bit 11 clear, no compensation)
  [6]  SW    x4, 4(x2)      -> sentinel 1 for SRAM[0x2004]
  [7]  CSRRW x0, 0x7C0, x0  -> flush the D-cache; it is write-back, so without this SRAM stays zero
  [8]  EBREAK               -> halt

ADDI sign-extends its 12-bit immediate. When bit 11 of the low 12 bits is set (0xEEF = -273), LUI
must load upper20 + 1: 0xDEADB + 1 = 0xDEADC.
Run: python tb/cocotb/soc/boot_fw/gen_boot_hex.py
Doc: tm:suite:soc-boot-fw-gen-boot-hex
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
