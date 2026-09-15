#!/usr/bin/env python3
"""Generate a VCD stimulus file (for `yosys sim -r <fst>`) driving
vector_alu_hls's inputs through the standard reset/start handshake for ONE
vector, then holding start_i asserted for up to `max_cycles` clock cycles so
the caller can find done_o's first rising edge in the CAPTURED output VCD
and read result_o/branch_taken_o at that point.

Usage: gen_stimulus_vcd.py <vectors.json> <vector_index> <out.vcd> [max_cycles]

vectors.json is produced by gen_vector_alu_vectors.py.
"""
import json
import sys

N_LANES = 8
REG_WIDTH = 32
MASK32 = 0xFFFF_FFFF
PERIOD = 10  # ns
RESET_CYCLES = 3


def pack_bin(lanes, width_per_lane=REG_WIDTH):
    val = 0
    for lane in range(N_LANES - 1, -1, -1):
        val = (val << width_per_lane) | (lanes[lane] & MASK32)
    return format(val, f"0{N_LANES * width_per_lane}b")


def vbin(val, width):
    return format(val & ((1 << width) - 1), f"0{width}b")


def main():
    vectors_path, idx_s, out_path = sys.argv[1:4]
    max_cycles = int(sys.argv[4]) if len(sys.argv) > 4 else 40
    idx = int(idx_s)
    with open(vectors_path) as f:
        vectors = json.load(f)
    v = vectors[idx]

    opcode = vbin(v["opcode"], 7)
    funct3 = "000"
    funct7 = vbin(0, 7)
    imm = vbin(v.get("imm", 0), 12)
    mask = vbin(v.get("mask", 0xFF), 8)
    rs1 = pack_bin(v["rs1"])
    rs2 = pack_bin(v["rs2"])

    # Build (time, {signal: bitstring}) change events.
    events = []  # list of (time_ns, dict of changes)

    def ev(t, **kw):
        events.append((t, kw))

    # Static/data inputs valid from t=0 (don't matter until start_i=1, but
    # stable throughout keeps the trace simple).
    ev(0, clk="0", rst_n="0", start_i="0",
       opcode_i=opcode, funct3_i=funct3, funct7_i=funct7, imm_i=imm,
       active_mask_i=mask, rs1_i=rs1, rs2_i=rs2)

    t = 0
    half = PERIOD // 2
    total_cycles = RESET_CYCLES + max_cycles
    rst_released_at_cycle = RESET_CYCLES  # rst_n goes high at this rising edge
    start_asserted = False
    for cyc in range(total_cycles):
        # rising edge
        t = cyc * PERIOD + half
        ch = {"clk": "1"}
        if cyc == rst_released_at_cycle:
            ch["rst_n"] = "1"
        if cyc == rst_released_at_cycle and not start_asserted:
            ch["start_i"] = "1"
            start_asserted = True
        ev(t, **ch)
        # falling edge
        t2 = cyc * PERIOD + PERIOD
        ev(t2, clk="0")

    end_time = total_cycles * PERIOD + PERIOD

    # --- write VCD ---
    sig_widths = {
        "clk": 1, "rst_n": 1, "start_i": 1,
        "opcode_i": 7, "funct3_i": 3, "funct7_i": 7, "imm_i": 12,
        "active_mask_i": 8, "rs1_i": 256, "rs2_i": 256,
    }
    ids = {}
    idchars = "!\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, name in enumerate(sig_widths):
        ids[name] = idchars[i]

    with open(out_path, "w") as f:
        f.write("$timescale 1ns $end\n")
        f.write("$scope module vector_alu_hls $end\n")
        for name, width in sig_widths.items():
            kind = "wire"
            f.write(f"$var {kind} {width} {ids[name]} {name} $end\n")
        f.write("$upscope $end\n")
        f.write("$enddefinitions $end\n")
        f.write("$dumpvars\n")
        for name, width in sig_widths.items():
            init_val = "0" * width
            if width == 1:
                f.write(f"{init_val}{ids[name]}\n")
            else:
                f.write(f"b{init_val} {ids[name]}\n")
        f.write("$end\n")

        # Merge events at same timestamp, apply initial values at t=0 via
        # the first event dict (already includes all static signals).
        merged = {}
        for t_, ch in events:
            merged.setdefault(t_, {}).update(ch)
        for t_ in sorted(merged):
            f.write(f"#{t_}\n")
            for name, bits in merged[t_].items():
                width = sig_widths[name]
                if width == 1:
                    f.write(f"{bits}{ids[name]}\n")
                else:
                    f.write(f"b{bits} {ids[name]}\n")
        f.write(f"#{end_time}\n")

    print(f"wrote {out_path}: vector[{idx}]={v['tag']} ({v['op']}), "
          f"reset releases at cycle {rst_released_at_cycle}, "
          f"end_time={end_time}ns ({total_cycles} cycles)")


if __name__ == "__main__":
    main()
