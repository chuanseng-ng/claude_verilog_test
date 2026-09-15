#!/usr/bin/env python3
"""Emit a batched yosys eval script for all vectors in vectors.json against one
design (gate netlist w/ liberty, or plain RTL)."""
import json
import sys

N_LANES = 8
REG_WIDTH = 32
MASK32 = 0xFFFF_FFFF

LIBS = [
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib",
]


def pack_hex(lanes):
    val = 0
    for lane in range(N_LANES - 1, -1, -1):
        val = (val << REG_WIDTH) | (lanes[lane] & MASK32)
    return f"256'h{val:064x}"


def main():
    vectors_path, netlist, top, out_ys, mode = sys.argv[1:6]
    with open(vectors_path) as f:
        vectors = json.load(f)

    lines = []
    if mode == "gate":
        for lib in LIBS:
            lines.append(f"read_liberty -ignore_miss_func {lib}")
        lines.append(f"read_verilog {netlist}")
    elif mode == "rtl":
        lines.append(f"read_verilog -sv {netlist}")
    elif mode == "rtl3":
        # netlist is a comma-separated list of files (pkg, core, shim)
        files = netlist.split(",")
        lines.append("read_verilog -sv " + " ".join(files))
    else:
        raise SystemExit(f"unknown mode {mode}")

    lines.append(f"hierarchy -top {top} -nokeep_prints -nokeep_asserts")
    lines.append("proc")
    lines.append("flatten")
    lines.append("opt -full")

    for idx, v in enumerate(vectors):
        rs1_hex = pack_hex(v["rs1"])
        rs2_hex = pack_hex(v["rs2"])
        imm = v.get("imm", 0) & 0xFFF
        mask = v.get("mask", 0xFF) & 0xFF
        opcode = v["opcode"] & 0x7F
        lines.append(
            f"eval -set rst_n 1'b1 -set start_i 1'b1 -set clk 1'b0 "
            f"-set opcode_i 7'd{opcode} -set funct3_i 3'd0 -set funct7_i 7'd0 "
            f"-set imm_i 12'd{imm} -set active_mask_i 8'b{mask:08b} "
            f"-set rs1_i {rs1_hex} -set rs2_i {rs2_hex} "
            f"-show done_o -show result_o -show branch_taken_o {top}"
        )
        lines.append(f"log VECTOR_MARKER {idx} {v['tag']}")

    with open(out_ys, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out_ys} with {len(vectors)} eval calls")


if __name__ == "__main__":
    main()
