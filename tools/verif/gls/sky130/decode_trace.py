#!/usr/bin/env python3
"""Decode two per-cycle boundary traces (tb_sky130_cpu_check.sv +trace=) and
print, for a cycle window, the reference arm's key fields and every field that
differs in the other arm.

  decode_trace.py <ref.trc> <dut.trc> <first_cyc> <last_cyc>
"""
import sys

WIDTHS = [1] * 14 + [3, 3, 2, 2, 4, 4, 8, 8, 4] + [32] * 7
NAMES = (
    "arvalid rready awvalid wvalid wlast bready cvalid trap bt eb pcsrc tbj pready pslverr "
    "arsize awsize arburst awburst tcause dstate arlen awlen wstrb "
    "araddr awaddr wdata cpc cinsn rs1 rs2 prdata"
).split()
SHOW = ("cvalid", "trap", "tcause", "cpc", "rs1", "rs2", "awvalid", "awaddr", "wdata", "dstate")


def dec(line):
    cyc, h = line.split()
    v = int(h, 16)
    sh = sum(WIDTHS)
    out = {}
    for n, w in zip(NAMES, WIDTHS):
        sh -= w
        out[n] = (v >> sh) & ((1 << w) - 1)
    return int(cyc), out


def main():
    ref, dut, lo, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    with open(ref) as fa, open(dut) as fb:
        for la, lb in zip(fa, fb):
            c, x = dec(la)
            if not lo <= c <= hi:
                continue
            _, y = dec(lb)
            diff = {k: (hex(x[k]), hex(y[k])) for k in x if x[k] != y[k]}
            print(c, "ref:", {k: hex(x[k]) for k in SHOW}, " DIFF(ref,dut):", diff)


if __name__ == "__main__":
    main()
