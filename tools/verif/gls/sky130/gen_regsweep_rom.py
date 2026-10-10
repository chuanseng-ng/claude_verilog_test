#!/usr/bin/env python3
"""Generate the dud4 register-sweep programs.

ma7 only exercised x2/x3 through one BEQ. This program writes a distinct,
random-looking 32-bit value into every register x1..x31 and then pushes each
register under test through BOTH ID-stage regfile read ports, observing the
result at the macro boundary (AXI write address/data of MMIO stores -- the
D-cache bypasses addresses >= 0x2000_0000 so every SW is visible as a single
AW+W beat). It never relies on the APB debug port for the ID-stage ports; the
debug port is read separately by the testbench for all 32 registers.

Per tested register N (B = MMIO base register, D = scratch register):

  ADDI D, xN, 0      ; xN via ID read port 1 (rs1)         -> SW D, 16N+0 (B)
  ADD  D, x0, xN     ; xN via ID read port 2 (rs2)         -> SW D, 16N+4 (B)
  SW   xN, 16N+8 (B) ; xN via port 2 as store data         (direct)
  ADD  D, xN, xN     ; xN via BOTH ports at once (2*xN)    -> SW D, 16N+12(B)

So the store ADDRESS identifies (register, form) and the store DATA is the
value that came out of the regfile read. A corrupted read of xN (either port)
changes the data of at least one of the four stores.

Registers B and D are exercised in the other run (different B/D) so that
across runs every register is a tested register on both ports.

The generator also writes <out>.expect.json (expected AXI write stream and
expected final GPR file) computed by construction, independent of any
simulator. Usage:

  gen_regsweep_rom.py --base 31 --dest 30 --seed 1 --out /path/name
"""
import argparse
import json
import random

MMIO_BASE = 0x2000_0100
M32 = 0xFFFF_FFFF


def lui(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0b0110111


def addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0010011


def add(rd, rs1, rs2):
    return (rs2 << 20) | (rs1 << 15) | (0b000 << 12) | (rd << 7) | 0b0110011


def sw(rs2, rs1, imm):
    imm &= 0xFFF
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (0b010 << 12) | ((imm & 0x1F) << 7) | 0b0100011


def jal0():
    return 0x0000006F


def load_const(rd, val):
    """LUI+ADDI building a 32-bit constant (hi adjusted for ADDI sign)."""
    hi = ((val + 0x800) >> 12) & 0xFFFFF
    lo = val & 0xFFF
    if lo >= 0x800:
        lo -= 0x1000
    return [lui(rd, hi), addi(rd, rd, lo)]


def build(base, dest, seed):
    assert 1 <= base <= 31 and 1 <= dest <= 31 and base != dest
    rng = random.Random(seed)
    vals = {}
    used = set()
    for r in range(1, 32):
        while True:
            v = rng.getrandbits(32)
            # keep values well away from 0/all-ones/small and from each other
            if v in used or v < 0x1000 or v > 0xFFFF_F000:
                continue
            if v >= 0x2000_0000 and v < 0x3000_0000:
                continue
            used.add(v)
            vals[r] = v
            break
    vals[base] = MMIO_BASE

    prog = []
    for r in range(1, 32):
        prog += load_const(r, vals[r])
    prog += [addi(0, 0, 0)] * 6  # let every init write retire before any read

    writes = []
    final = dict(vals)
    tested = [r for r in range(1, 32) if r not in (base, dest)]
    for n in tested:
        v = vals[n]
        prog += [addi(dest, n, 0), sw(dest, base, 16 * n + 0)]
        writes.append((MMIO_BASE + 16 * n + 0, v))
        prog += [add(dest, 0, n), sw(dest, base, 16 * n + 4)]
        writes.append((MMIO_BASE + 16 * n + 4, v))
        prog += [sw(n, base, 16 * n + 8)]
        writes.append((MMIO_BASE + 16 * n + 8, v))
        prog += [add(dest, n, n), sw(dest, base, 16 * n + 12)]
        writes.append((MMIO_BASE + 16 * n + 12, (2 * v) & M32))
        final[dest] = (2 * v) & M32
    prog += [jal0()]
    final[0] = 0
    return prog, writes, final, vals, tested


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, required=True)
    ap.add_argument("--dest", type=int, required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    prog, writes, final, vals, tested = build(a.base, a.dest, a.seed)
    assert len(prog) < 1000
    with open(a.out + ".hex", "w") as f:
        for w in prog:
            f.write(f"{w:08x}\n")
    with open(a.out + ".expect.json", "w") as f:
        json.dump(
            {
                "base": a.base,
                "dest": a.dest,
                "seed": a.seed,
                "tested": tested,
                "n_instr": len(prog),
                "writes": [[f"{ad:08x}", f"{d:08x}"] for ad, d in writes],
                "final_gpr": {str(k): f"{v:08x}" for k, v in sorted(final.items())},
            },
            f,
            indent=1,
        )
    print(f"{a.out}.hex: {len(prog)} instr, {len(writes)} stores, tested {len(tested)} regs")


if __name__ == "__main__":
    main()
