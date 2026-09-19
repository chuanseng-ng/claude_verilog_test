#!/usr/bin/env python3
"""Generate rom_cpu_check.hex for the bead claude_verilog_test-ma7 step-1
BRANCH-DEPENDENT regfile read-port check.

u99 proved the Synlig-built rv32i_cpu_top gate netlist mis-elaborates the
regfile's *debug* read port (`dbg_rd_data = regs[dbg_rd_addr]`). It did NOT
establish whether the corruption reaches the two ID-stage read ports
(`rd_data1 = regs[rd_addr1]`, `rd_data2 = regs[rd_addr2]`) that feed the
execute datapath -- the original 6-instruction straight-line program used by
tools/verif/gls/tb_cpu_macro_check.v cannot see that, because a straight-line
PC sequence never depends on a computed register value.

This program makes ID-stage regfile reads OBSERVABLE through commit_pc_o /
commit_insn_o (the channel u99 already showed is reliable and NOT the known-
bad debug port) by making a branch's taken/not-taken outcome a function of
two distinct general-purpose registers (both read ports, rs1 and rs2, used
simultaneously). If either read port returns a wrong value for the exercised
indices, the compare flips and the retire trace diverges to a dead "WRONG"
marker instead of continuing to the "PASS" self-loop.

NOTE ON DESIGN (single branch, not two): a first version of this program
used two back-to-back taken branches (two icache-miss redirects in quick
succession). On the frontend-independent RTL reference (arm 3) that version
retired only as far as the SECOND branch's commit and then hung -- no
further commit_valid_o, no further AXI activity -- for the rest of a 1500-
cycle run. The FIRST redirect (one taken branch, one icache-miss refill)
retired cleanly and correctly (commit trace 0x00,0x04,0x08,0x0c,0x18,
matching the reference model exactly) before the second redirect was
introduced. This looks like a real, separate pipeline issue triggered
specifically by two consecutive taken-branch redirects -- out of scope for
bead ma7 (which is about regfile read-port corruption in a Synlig netlist,
not an RTL functional bug) and NOT investigated further here per the task's
"do not apply any RTL change" constraint; flag for a follow-up bead if
confirmed. This program was redesigned to use exactly ONE taken branch (one
redirect) to stay inside the region already shown to execute correctly on
the RTL reference, while still exercising both regfile read ports (rs1 and
rs2, on register indices distinct from the debug-port index x4 u99 used).

Layout (byte address: instruction):
  0x00: ADDI x1, x0, 5        x1=5
  0x04: ADDI x2, x0, 9        x2=9
  0x08: ADDI x3, x0, 9        x3=9
  0x0c: ADD  x4, x1, x2        x4=14 (pre-branch ALU read-port exercise)   [rs1=x1, rs2=x2]
  0x10: BEQ  x2, x3, +0x10 -> 0x20   (x2==x3 -> TAKEN)                     [rs1=x2, rs2=x3]
  0x14: ADDI x5, x0, 0x111    WRONG marker (only reached if BEQ wrongly not-taken)
  0x18: JAL  x0, 0            WRONG self-loop
  0x1c: (dead filler, never fetched as a real instruction on the correct path)
  0x20: ADD  x6, x1, x2        x6=14 (post-redirect ALU read-port exercise) [rs1=x1, rs2=x2]
  0x24: ADDI x7, x0, 0x222    PASS marker
  0x28: JAL  x0, 0            PASS self-loop (parks here forever if correct)

Verified against tb/models/rv32i_model.py by
tools/verif/gls/check_branch_prog_refmodel.py before use: the reference
model retires pc trace 0x00,0x04,0x08,0x0c,0x10,0x20,0x24,0x28 and never
visits the WRONG marker at 0x14/0x18.

Usage: gen_cpu_check_rom_branch.py <out.hex> [rom_words]
"""
import sys


def addi(rd, rs1, imm):
    imm &= 0xFFF
    return (imm << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0010011


def add(rd, rs1, rs2):
    return (0 << 25) | (rs2 << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0110011


def _branch(funct3, rs1, rs2, imm):
    assert imm % 2 == 0, "branch immediate must be halfword-aligned"
    imm &= 0x1FFF
    imm12 = (imm >> 12) & 0x1
    imm11 = (imm >> 11) & 0x1
    imm10_5 = (imm >> 5) & 0x3F
    imm4_1 = (imm >> 1) & 0xF
    return (
        (imm12 << 31)
        | (imm10_5 << 25)
        | (rs2 << 20)
        | (rs1 << 15)
        | (funct3 << 12)
        | (imm4_1 << 8)
        | (imm11 << 7)
        | 0b1100011
    )


def beq(rs1, rs2, imm):
    return _branch(0b000, rs1, rs2, imm)


def bne(rs1, rs2, imm):
    return _branch(0b001, rs1, rs2, imm)


def jal(rd, imm):
    imm20 = (imm >> 20) & 1
    imm10_1 = (imm >> 1) & 0x3FF
    imm11 = (imm >> 11) & 1
    imm19_12 = (imm >> 12) & 0xFF
    return (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) | (imm19_12 << 12) | (rd << 7) | 0b1101111


PROGRAM = {
    0x00: addi(1, 0, 5),
    0x04: addi(2, 0, 9),
    0x08: addi(3, 0, 9),
    0x0C: add(4, 1, 2),
    0x10: beq(2, 3, 0x20 - 0x10),
    0x14: addi(5, 0, 0x111),
    0x18: jal(0, 0),
    0x20: add(6, 1, 2),
    0x24: addi(7, 0, 0x222),
    0x28: jal(0, 0),
}

# Expected reference-model retire PC sequence (see refmodel check script).
EXPECTED_PC_SEQUENCE = [0x00, 0x04, 0x08, 0x0C, 0x10, 0x20, 0x24, 0x28]


def main():
    if len(sys.argv) < 2:
        print("usage: gen_cpu_check_rom_branch.py <out.hex> [rom_words]", file=sys.stderr)
        sys.exit(1)
    out_path = sys.argv[1]
    rom_words = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    pad = jal(0, 0)  # self-loop, safe filler for speculative/prefetch reads
    with open(out_path, "w") as f:
        for i in range(rom_words):
            addr = i * 4
            v = PROGRAM.get(addr, pad)
            f.write(f"{v:08x}\n")
    print(
        f"wrote {out_path}: {len(PROGRAM)} real instructions "
        f"(incl. 1 dead WRONG-path marker), {rom_words} words total"
    )


if __name__ == "__main__":
    main()
