#!/usr/bin/env python3
"""Generate the hierarchical-probe include files used by tb_sky130_cpu_check.sv
(-DPROBE_FILE="<file>") so each arm exposes, under the SAME names:

  p_idex  [216:0]   ID/EX pipeline register (rs1_data = [152:121], rs2_data = [120:89],
                    rs1_addr = [56:52], rs2_addr = [51:47], valid = [0],
                    instruction = [184:153], pc = [216:185]; layout from
                    rv32i_pipeline_pkg::id_ex_reg_t)
  p_regs  [1023:0]  register-file STORAGE, word k = bits [32k +: 32], architectural xk

RTL arm : dut.u_core.id_ex_reg / dut.u_core.u_regfile.regs[k]
gate arm: flattened per-bit nets  \\u_core.id_ex_reg[N]  /  \\u_core.u_regfile.regs[W][B]
          (W = memory word; --gate-word-offset maps W -> architectural index k = W+offset;
           decided empirically by comparing the two arms' STATE dumps)

  gen_probes.py rtl  <out.vh>
  gen_probes.py gate <out.vh> [--gate-word-offset N]
"""
import sys


def rtl(out):
    with open(out, "w") as f:
        # forwarding-select registers feeding the EX operand mux (A side)
        f.write("wire [4:0] p_fwd = {dut.u_core.fwd_a_ex1b2_r, dut.u_core.fwd_a_ex1c_r, 1'b0, dut.u_core.fwd_a_sel_r};\n")
        f.write("wire [216:0] p_idex = dut.u_core.id_ex_reg;\n")
        parts = []
        for k in range(31, -1, -1):
            parts.append("32'h0" if k == 0 else f"dut.u_core.u_regfile.regs[{k}]")
        f.write("wire [1023:0] p_regs = {" + ", ".join(parts) + "};\n")


def gate(out, off):
    import re

    # Synthesis keeps only some id_ex_reg bits as named nets (the rest are merged /
    # renamed); probe only those that exist, tie the rest to 0. All of rs1_data
    # [152:121] and rs2_data [120:89] survive; the address/valid bits do not.
    have = set()
    import os

    with open(os.environ.get("NETLIST", "/nobackup/claude_sim_build/dud4/rv32i_cpu_top.nl.v")) as nl:
        for ln in nl:
            m = re.match(r"\s*wire \\u_core\.id_ex_reg\[(\d+)\] ;", ln)
            if m:
                have.add(int(m.group(1)))
    with open(out, "w") as f:
        # gate keeps fwd_a_sel_r as bits [1],[2],[3] (renamed by synthesis); raw dump
        f.write("wire [4:0] p_fwd = {dut.\\u_core.fwd_a_ex1b2_r , dut.\\u_core.fwd_a_ex1c_r , "
                "dut.\\u_core.fwd_a_sel_r[3] , dut.\\u_core.fwd_a_sel_r[2] , dut.\\u_core.fwd_a_sel_r[1] };\n")
        bits = [f"dut.\\u_core.id_ex_reg[{n}] " if n in have else "1'b0" for n in range(216, -1, -1)]
        f.write("wire [216:0] p_idex = {" + ",\n  ".join(bits) + "};\n")
        words = []
        for k in range(31, -1, -1):
            w = k - off
            if w < 0 or w > 31:
                words.append("32'h0")
            else:
                words.append("{" + ", ".join(f"dut.\\u_core.u_regfile.regs[{w}][{b}] " for b in range(31, -1, -1)) + "}")
        f.write("wire [1023:0] p_regs = {" + ",\n  ".join(words) + "};\n")


if __name__ == "__main__":
    arm, out = sys.argv[1], sys.argv[2]
    off = 0
    if "--gate-word-offset" in sys.argv:
        off = int(sys.argv[sys.argv.index("--gate-word-offset") + 1])
    rtl(out) if arm == "rtl" else gate(out, off)
