#!/usr/bin/env python3
"""Generate golden test vectors for vector_alu_hls GLS cross-check (bead egt/gcd/b0t).

Golden semantics are taken EXACTLY from the inline expected-value formulas in
tb/cocotb/gpu/test_vector_alu.py (the "Python reference the cocotb test uses"),
not from any RTL. Only opcodes actually exercised by that suite are modeled:
VADD, VSUB, VMUL, VAND, VOR, VXOR, VSLL, VSRL, VSRA, VADDI, VANDI, VBEQ, VBLT.

Shift amount is masked to 5 bits (rs2 & 0x1F) to avoid the untested >=32 shift
edge (Verilog >>/<</>>> semantics for shift>=width are not exercised by any
directed test, so vectors are kept inside the tested/unambiguous range).
VANDI immediates are kept with bit 11 = 0 so sign-extension and zero-extension
of the 12-bit imm coincide (VADDI's directed test proves sign-extension;
VANDI's does not disambiguate, so that ambiguity is avoided rather than
guessed at).
"""
import ctypes
import json
import random
import sys

N_LANES = 8
REG_WIDTH = 32
MASK32 = 0xFFFF_FFFF

OP = {
    "VADD": 0x01, "VSUB": 0x02, "VMUL": 0x03,
    "VAND": 0x04, "VOR": 0x05, "VXOR": 0x06,
    "VSLL": 0x07, "VSRL": 0x08, "VSRA": 0x09,
    "VADDI": 0x11, "VANDI": 0x12,
    "VBEQ": 0x30, "VBLT": 0x32,
}
NONBRANCH = ["VADD", "VSUB", "VMUL", "VAND", "VOR", "VXOR", "VSLL", "VSRL", "VSRA"]
IMM_OPS = ["VADDI", "VANDI"]
BRANCH = ["VBEQ", "VBLT"]


def m32(v):
    return v & MASK32


def s32(v):
    return ctypes.c_int32(v & MASK32).value


def sext12(imm12):
    imm12 &= 0xFFF
    if imm12 & 0x800:
        imm12 -= 0x1000
    return imm12


def alu(op, a, b):
    a &= MASK32
    b &= MASK32
    if op == "VADD":
        return m32(a + b)
    if op == "VSUB":
        return m32(a - b)
    if op == "VMUL":
        return m32(a * b)
    if op == "VAND":
        return a & b
    if op == "VOR":
        return a | b
    if op == "VXOR":
        return a ^ b
    if op == "VSLL":
        sh = b & 0x1F
        return m32(a << sh)
    if op == "VSRL":
        sh = b & 0x1F
        return a >> sh
    if op == "VSRA":
        sh = b & 0x1F
        sv = s32(a)
        return m32(sv >> sh) if sh else m32(a)
    raise ValueError(op)


def gen_lanes_random(rng, lo=0, hi=MASK32):
    return [rng.randint(lo, hi) for _ in range(N_LANES)]


CORNERS = [0x0000_0000, 0xFFFF_FFFF, 0x8000_0000, 0x7FFF_FFFF,
           0x0000_0001, 0xAAAA_AAAA, 0x5555_5555, 0x0000_00FF]


def expected_nonbranch(op, rs1, rs2, mask):
    res = []
    for lane in range(N_LANES):
        if mask & (1 << lane):
            res.append(alu(op, rs1[lane], rs2[lane]))
        else:
            res.append(0)
    return res


def expected_imm(op, rs1, imm12, mask):
    res = []
    if op == "VADDI":
        add = sext12(imm12)
        for lane in range(N_LANES):
            if mask & (1 << lane):
                res.append(m32(rs1[lane] + add))
            else:
                res.append(0)
    elif op == "VANDI":
        assert (imm12 & 0x800) == 0, "VANDI imm must keep bit11=0 (sign/zero-ext ambiguity avoided)"
        for lane in range(N_LANES):
            if mask & (1 << lane):
                res.append(rs1[lane] & imm12)
            else:
                res.append(0)
    else:
        raise ValueError(op)
    return res


def expected_branch(op, rs1, rs2):
    taken = 0
    for lane in range(N_LANES):
        if op == "VBEQ":
            t = 1 if m32(rs1[lane]) == m32(rs2[lane]) else 0
        elif op == "VBLT":
            t = 1 if s32(rs1[lane]) < s32(rs2[lane]) else 0
        else:
            raise ValueError(op)
        taken |= (t << lane)
    return taken


def main():
    rng = random.Random(0xE6707)
    vectors = []

    # 1. Full-mask (0xFF) coverage per non-branch op: corners + random.
    for op in NONBRANCH:
        # corner pairs
        for i, c in enumerate(CORNERS):
            rs1 = [c] * N_LANES
            rs2 = [CORNERS[(i + 3) % len(CORNERS)]] * N_LANES
            vectors.append({
                "op": op, "rs1": rs1, "rs2": rs2, "imm": 0, "mask": 0xFF,
                "exp_result": expected_nonbranch(op, rs1, rs2, 0xFF),
                "tag": f"{op}_corner{i}",
            })
        # random, distinct per-lane values
        for i in range(4):
            rs1 = gen_lanes_random(rng)
            rs2 = gen_lanes_random(rng)
            vectors.append({
                "op": op, "rs1": rs1, "rs2": rs2, "imm": 0, "mask": 0xFF,
                "exp_result": expected_nonbranch(op, rs1, rs2, 0xFF),
                "tag": f"{op}_rand{i}",
            })

    # 2. Partial-mask coverage (the corruption class this whole investigation
    #    is about) across a representative subset of ops, with garbage data in
    #    inactive lanes to make any leak visible.
    mask_patterns = [0x00, 0xFF, 0x01, 0x80, 0x55, 0xAA, 0x0F, 0xF0,
                      0x11, 0x88, 0x42, 0x24]
    mask_ops = ["VADD", "VSUB", "VMUL", "VAND", "VOR", "VXOR", "VSLL", "VSRA"]
    for op in mask_ops:
        for mi, mask in enumerate(mask_patterns):
            rs1 = gen_lanes_random(rng)
            rs2 = gen_lanes_random(rng)
            # force garbage into inactive lanes specifically
            for lane in range(N_LANES):
                if not (mask & (1 << lane)):
                    rs1[lane] = rng.choice(CORNERS)
                    rs2[lane] = rng.choice(CORNERS)
            vectors.append({
                "op": op, "rs1": rs1, "rs2": rs2, "imm": 0, "mask": mask,
                "exp_result": expected_nonbranch(op, rs1, rs2, mask),
                "tag": f"{op}_mask{mi:02d}_{mask:#04x}",
            })

    # 3. Immediate ops.
    for i in range(10):
        rs1 = gen_lanes_random(rng)
        imm = rng.randint(0, 0xFFF)
        mask = rng.choice([0xFF, 0x55, 0xAA, 0x01, 0x80])
        vectors.append({
            "op": "VADDI", "rs1": rs1, "rs2": rs1, "imm": imm, "mask": mask,
            "exp_result": expected_imm("VADDI", rs1, imm, mask),
            "tag": f"VADDI_{i}",
        })
    for i in range(10):
        rs1 = gen_lanes_random(rng)
        imm = rng.randint(0, 0x7FF)  # bit11=0, avoids sign/zero-ext ambiguity
        mask = rng.choice([0xFF, 0x55, 0xAA, 0x01, 0x80])
        vectors.append({
            "op": "VANDI", "rs1": rs1, "rs2": rs1, "imm": imm, "mask": mask,
            "exp_result": expected_imm("VANDI", rs1, imm, mask),
            "tag": f"VANDI_{i}",
        })

    # 4. Branch ops (full mask only -- result_o/masked-branch semantics for
    #    branch opcodes are not exercised by any directed test, so this stays
    #    consistent with that scope).
    for op in BRANCH:
        for i, c in enumerate(CORNERS):
            rs1 = [c] * N_LANES
            rs2 = [CORNERS[(i + 5) % len(CORNERS)]] * N_LANES
            vectors.append({
                "op": op, "rs1": rs1, "rs2": rs2, "imm": 0, "mask": 0xFF,
                "exp_taken": expected_branch(op, rs1, rs2),
                "tag": f"{op}_corner{i}",
            })
        for i in range(6):
            rs1 = gen_lanes_random(rng)
            rs2 = gen_lanes_random(rng)
            vectors.append({
                "op": op, "rs1": rs1, "rs2": rs2, "imm": 0, "mask": 0xFF,
                "exp_taken": expected_branch(op, rs1, rs2),
                "tag": f"{op}_rand{i}",
            })

    for v in vectors:
        v["opcode"] = OP[v["op"]]

    out_path = sys.argv[1] if len(sys.argv) > 1 else "vectors.json"
    print(f"Generated {len(vectors)} vectors -> {out_path}", flush=True)
    with open(out_path, "w") as f:
        json.dump(vectors, f)


if __name__ == "__main__":
    main()
