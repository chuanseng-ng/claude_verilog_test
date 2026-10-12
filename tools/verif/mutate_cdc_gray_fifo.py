#!/usr/bin/env python3
"""Mutation campaign for the cdc_gray_fifo unit suite (bead 3snb).

Each mutant is a textual edit of rtl/soc/cdc/cdc_gray_fifo.sv written to OUT_DIR and fed to the
very same suite through `make CDC_GRAY_FIFO_RTL=<mutant> cdc_gray_fifo_sim`. A mutant is KILLED when
the run fails (Verilator build/elaboration error, or any cocotb test FAIL) and SURVIVED when all tests pass.
A mutant that did not apply (pattern not found) is an error, not a survivor.

Usage (inside the nix sim devshell):
    python3 tools/verif/mutate_cdc_gray_fifo.py [--out DIR] [--only NAME[,NAME...]]
"""

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "rtl/soc/cdc/cdc_gray_fifo.sv"

# (name, requirement it targets, [(old, new), ...]) -- every old must occur exactly once.
D2_FULL = "assign full_cmp_w = ~rd_gray_sync_w;"
MUTANTS = [
    ("a1_general_expr_at_depth2", "(a) DEPTH>=4 full expression used at depth 2 (literal)",
     [(D2_FULL, "assign full_cmp_w = {~rd_gray_sync_w[PTR_W-1:PTR_W-2], rd_gray_sync_w[PTR_W-3:0]};")]),
    ("a2_msb_only_inversion_d2", "(a) naive narrowing of the general form: invert only the MSB",
     [(D2_FULL, "assign full_cmp_w = {~rd_gray_sync_w[PTR_W-1], rd_gray_sync_w[PTR_W-2:0]};")]),
    ("a3_lsb_only_inversion_d2", "full flag: invert only the LSB",
     [(D2_FULL, "assign full_cmp_w = {rd_gray_sync_w[PTR_W-1], ~rd_gray_sync_w[PTR_W-2:0]};")]),
    ("a4_no_inversion_d2", "full flag: compare equal (empty-style) at depth 2",
     [(D2_FULL, "assign full_cmp_w = rd_gray_sync_w;")]),
    ("a5_never_full", "full flag never asserted (any depth)",
     [("full_q <= (wr_gray_d == full_cmp_w);", "full_q <= 1'b0;")]),
    ("a6_dge4_msb_not_inverted", "DEPTH>=4 branch: top bit not inverted (control depth)",
     [("{~rd_gray_sync_w[PTR_W-1:PTR_W-2], rd_gray_sync_w[PTR_W-3:0]}",
       "{rd_gray_sync_w[PTR_W-1], ~rd_gray_sync_w[PTR_W-2], rd_gray_sync_w[PTR_W-3:0]}")]),
    ("b1_ungated_wr_ready", "(b) wr_ready_o not gated by own-domain reset",
     [("assign wr_ready_o = wr_rst_n_i && !full_q;", "assign wr_ready_o = !full_q;")]),
    ("c1_binary_wr_to_rd_raw", "(c) binary write pointer crosses (and is compared as if gray)",
     [(".d_i     (wr_gray_q),", ".d_i     (wr_bin_q),")]),
    ("c2_binary_wr_to_rd_gray_after", "(c) binary write pointer crosses, gray-converted after the sync",
     [(".d_i     (wr_gray_q),\n        .q_o     (wr_gray_sync_r)",
       ".d_i     (wr_bin_q),\n        .q_o     (wr_bin_sync_r)"),
      ("    logic [PTR_W-1:0] rd_gray_sync_w;",
       "    logic [PTR_W-1:0] rd_gray_sync_w;\n    logic [PTR_W-1:0] wr_bin_sync_r;\n"
       "    assign wr_gray_sync_r = (wr_bin_sync_r >> 1) ^ wr_bin_sync_r;"),
      ("    logic [PTR_W-1:0] wr_gray_sync_r;   // wr_gray_q synchronised into the READ domain",
       "    logic [PTR_W-1:0] wr_gray_sync_r;")]),
    ("c3_binary_rd_to_wr_gray_after", "(c) binary read pointer crosses, gray-converted after the sync",
     [(".d_i     (rd_gray_q),\n        .q_o     (rd_gray_sync_w)",
       ".d_i     (rd_bin_q),\n        .q_o     (rd_bin_sync_w)"),
      ("    logic [PTR_W-1:0] rd_gray_sync_w;   // rd_gray_q synchronised into the WRITE domain",
       "    logic [PTR_W-1:0] rd_gray_sync_w;\n    logic [PTR_W-1:0] rd_bin_sync_w;\n"
       "    assign rd_gray_sync_w = (rd_bin_sync_w >> 1) ^ rd_bin_sync_w;")]),
    ("d1_empty_resets_to_valid", "rd_valid_o advertises data in reset (empty_q resets to 0)",
     [("            empty_q <= 1'b1;", "            empty_q <= 1'b0;")]),
    ("d2_write_ignores_ready", "storage written on wr_valid_i alone (ignores full)",
     [("        if (wr_en) begin\n            mem_q", "        if (wr_valid_i) begin\n            mem_q")]),
    ("d3_read_ignores_valid", "read pointer advances on rd_ready_i alone (underflow)",
     [("assign rd_en     = rd_valid_o && rd_ready_i;", "assign rd_en     = rd_ready_i;")]),
    ("d4_empty_compares_next_vs_cur", "empty flag compares against the unsynchronised write gray pointer",
     [("empty_q <= (rd_gray_d == wr_gray_sync_r);", "empty_q <= (rd_gray_d == wr_gray_q);")]),
    ("d5_full_resets_to_one", "full_q resets to 1 (wr_ready already gated by reset)",
     [("            full_q <= 1'b0;", "            full_q <= 1'b1;")]),
]


def build(name, edits, out):
    s = SRC.read_text()
    for old, new in edits:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"mutant {name}: pattern occurs {n}x (need 1): {old[:60]!r}")
        s = s.replace(old, new)
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "cdc_gray_fifo.sv"  # same basename as the original (lint DECLFILENAME)
    p.write_text(s)
    return p


def run(mut_path, build_root):
    cmd = ["make", "-C", str(ROOT / "tb/cocotb/soc"), "cdc_gray_fifo_sim",
           f"CDC_GRAY_FIFO_RTL={mut_path}", f"SIM_BUILD_ROOT={build_root}",
           "SIM_BUILD_MIN_FREE_MB=500"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    log = r.stdout + r.stderr
    m = re.search(r"TESTS=(\d+) PASS=(\d+) FAIL=(\d+)", log)
    failing = sorted(set(re.findall(r"FAIL (test_\S+?):", log)))
    return r.returncode, m.groups() if m else None, failing, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/mut_cdc_gray_fifo")
    ap.add_argument("--build-root", default="/nobackup/claude_sim_build/soc3snb_mut")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    survivors = []
    for name, why, edits in MUTANTS:
        if only and name not in only:
            continue
        path = build(name, edits, out)
        rc, counts, failing, log = run(path, a.build_root)
        (out / name / "run.log").write_text(log)
        if rc == 0 and counts and counts[2] == "0":
            verdict = "SURVIVED"
            survivors.append(name)
        elif counts is None:
            verdict = "KILLED (compile/lint/elaboration failure)"
        else:
            verdict = f"KILLED ({counts[2]}/{counts[0]} tests fail)"
        print(f"{name:34s} {verdict:44s} {why}", flush=True)
        if failing:
            print(f"    failing: {', '.join(failing[:6])}{' ...' if len(failing) > 6 else ''}", flush=True)
    print("SURVIVORS:", survivors if survivors else "none")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
