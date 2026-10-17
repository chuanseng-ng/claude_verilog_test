#!/usr/bin/env python3
"""Mutation campaign for the crypto_accel scan-wipe (bead j41m.6, DFT_ARCHITECTURE.md sec.14.3).

Each mutant is a textual edit of rtl/periph/{crypto_accel,aes128_core,sha256_core}.sv written to a
private copy of the rtl tree under OUT_DIR and fed to the very same `test_crypto` suite through
`make crypto RTL=<tree>`. A mutant is KILLED when the run fails (any cocotb test FAIL) and SURVIVED
when all tests pass. A mutant that does not lint/elaborate is INVALID (reported, counted neither
way): a mutant must be killed by behaviour, not by a build error. A pattern that does not occur
exactly once is an error, not a survivor.

Usage (inside the nix sim devshell):
    python3 tools/verif/mutate_crypto_scan_wipe.py [--out DIR] [--only NAME[,NAME...]]
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = {
    "ca": "rtl/periph/crypto_accel.sv",
    "aes": "rtl/periph/aes128_core.sv",
    "sha": "rtl/periph/sha256_core.sv",
}
BANK = "rtl/soc/apb4_register_bank.sv"

SYNC_BLK = """    always_ff @(posedge clk) begin
        scan_s1_q   <= scan_mode_i;
        scan_s2_q   <= scan_s1_q;
        scan_prev_q <= scan_s2_q;
    end"""
SYNC_RST = """    always_ff @(posedge clk) begin
        if (!rst_n) begin
            scan_s1_q <= 1'b0; scan_s2_q <= 1'b0; scan_prev_q <= 1'b0;
        end else begin
            scan_s1_q   <= scan_mode_i;
            scan_s2_q   <= scan_s1_q;
            scan_prev_q <= scan_s2_q;
        end
    end"""

# (name, what it removes, [(file key, old, new), ...]) -- every old must occur exactly once.
MUTANTS = [
    ("k1_key_q_kept", "key_q survives the wipe",
     [("ca", "            key_q       <= 128'h0;", "            key_q       <= wipe_w ? key_q : 128'h0;")]),
    ("k2_key_valid_kept", "key_seen_q survives: key_valid would stay 1",
     [("ca", "            key_seen_q  <= 4'h0;", "            key_seen_q  <= wipe_w ? key_seen_q : 4'h0;")]),
    ("k3_msg_q_kept", "msg_q survives the wipe",
     [("ca", "        if (!rst_n || wipe_w) msg_q <= '0;", "        if (!rst_n) msg_q <= '0;")]),
    ("k4_ctr_op_kept", "ctr_op_q survives the wipe",
     [("ca", "        if (!rst_n || wipe_w) ctr_op_q <= 1'b0;", "        if (!rst_n) ctr_op_q <= 1'b0;")]),
    ("b1_dout_kept", "bank DOUT0-3 not cleared",
     [("ca", "                hw_wen_i  [REG_DOUT0 + i] = 1'b1;\n                hw_wdata_i[REG_DOUT0 + i] = 32'h0;\n", "")]),
    ("b2_iv_kept", "bank IV0-3 not cleared",
     [("ca", "                hw_wen_i  [REG_IV0 + i]   = 1'b1;\n                hw_wdata_i[REG_IV0 + i]   = 32'h0;\n", "")]),
    ("b3_digest_kept", "bank DIGEST0-7 not cleared",
     [("ca", "                hw_wen_i  [REG_DIGEST0 + i] = 1'b1;\n                hw_wdata_i[REG_DIGEST0 + i] = 32'h0;\n", "")]),
    ("c1_aes_core_ignores_wipe", "AES core wipe_i tied 0",
     [("ca", "            .wipe_i     (wipe_w),\n            .key_i", "            .wipe_i     (1'b0),\n            .key_i")]),
    ("c2_sha_core_ignores_wipe", "SHA core wipe_i tied 0",
     [("ca", "            .wipe_i     (wipe_w),\n            .start_i    (sha_start_w),", "            .wipe_i     (1'b0),\n            .start_i    (sha_start_w),")]),
    ("a1_aes_s_q_kept", "AES s_q survives",
     [("aes", "            s_q     <= 128'h0;", "            s_q     <= wipe_i ? s_q : 128'h0;")]),
    ("a2_aes_rk_q_kept", "AES rk_q survives",
     [("aes", "            rk_q    <= 128'h0;", "            rk_q    <= wipe_i ? rk_q : 128'h0;")]),
    ("a3_aes_state_kept", "AES state_q survives (round counter keeps running)",
     [("aes", "            state_q <= A_IDLE;\n            round_q <= 4'd0;", "            state_q <= wipe_i ? state_q : A_IDLE;\n            round_q <= 4'd0;")]),
    ("s1_sha_hin_kept", "SHA hin_q (previous chaining value) survives",
     [("sha", "            hin_q   <= 256'h0;", "            hin_q   <= wipe_i ? hin_q : 256'h0;")]),
    ("s2_sha_a_kept", "SHA working variable a_q survives",
     [("sha", "            a_q     <= 32'h0;", "            a_q     <= wipe_i ? a_q : 32'h0;")]),
    ("s3_sha_h_kept", "SHA working variable h_q survives",
     [("sha", "            h_q     <= 32'h0;", "            h_q     <= wipe_i ? h_q : 32'h0;")]),
    ("s4_sha_w_kept", "SHA message schedule w_q survives",
     [("sha", "            for (int unsigned j = 0; j < 16; j++) w_q[j] <= 32'h0;",
       "            if (!wipe_i) for (int unsigned j = 0; j < 16; j++) w_q[j] <= 32'h0;")]),
    ("s5_sha_t_kept", "SHA round counter t_q survives",
     [("sha", "            t_q     <= 7'd0;\n            hin_q", "            t_q     <= wipe_i ? t_q : 7'd0;\n            hin_q")]),
    ("e1_exit_not_detected", "rising edge only (exit does not wipe)",
     [("ca", "assign wipe_w = scan_s2_q ^ scan_prev_q;", "assign wipe_w = scan_s2_q & ~scan_prev_q;")]),
    ("e2_entry_not_detected", "falling edge only (entry does not wipe)",
     [("ca", "assign wipe_w = scan_s2_q ^ scan_prev_q;", "assign wipe_w = ~scan_s2_q & scan_prev_q;")]),
    ("e3_wipe_held_as_level", "clear held for the whole of scan mode (reset-like)",
     [("ca", "assign wipe_w = scan_s2_q ^ scan_prev_q;", "assign wipe_w = scan_s2_q ^ scan_prev_q | scan_s2_q;")]),
    ("e4_sync_stage_dropped", "one synchroniser stage short (latency 1)",
     [("ca", "        scan_s2_q   <= scan_s1_q;", "        scan_s2_q   <= scan_mode_i;")]),
    ("e5_edge_flops_reset", "edge detector reset to 0 (reset fabricates / hides an edge)",
     [("ca", SYNC_BLK, SYNC_RST)]),
    ("f1_inflight_not_aborted", "wrapper FSM stays busy when the wipe lands mid-operation",
     [("ca", "            C_BUSY:  if (wipe_w)                               state_d = C_DONE;   // aborted: no data\n"
             "                     else if (aes_done_set_w | sha_done_set_w) state_d = C_IDLE;",
       "            C_BUSY:  if (aes_done_set_w | sha_done_set_w) state_d = C_IDLE;")]),
    ("f2_start_in_wipe_cycle", "a START in the wipe cycle goes busy over a cleared core",
     [("ca", "state_d = (op_legal_w && !wipe_w) ? C_BUSY : C_DONE;", "state_d = op_legal_w ? C_BUSY : C_DONE;")]),
    ("f3_key_write_in_wipe_cycle", "a KEY write in the wipe cycle is accepted (key_valid mirror)",
     [("ca", "key_wr_w[i] & ~busy_q & ~wipe_w;", "key_wr_w[i] & ~busy_q;")]),
    ("f4_status_key_valid_stale", "STATUS.key_valid mirror ignores the wipe",
     [("ca", "assign key_valid_d_w = ~wipe_w & (&(key_seen_q | key_accept_w));",
       "assign key_valid_d_w = &(key_seen_q | key_accept_w);")]),
]


def build(name, edits, out):
    tree = out / name / "rtl"
    if tree.parent.exists():
        shutil.rmtree(tree.parent)
    (tree / "periph").mkdir(parents=True)
    (tree / "soc").mkdir(parents=True)
    shutil.copy(ROOT / BANK, tree / "soc" / pathlib.Path(BANK).name)
    texts = {k: (ROOT / v).read_text() for k, v in FILES.items()}
    for key, old, new in edits:
        n = texts[key].count(old)
        if n != 1:
            raise SystemExit(f"mutant {name}: pattern occurs {n}x in {key} (need 1): {old[:60]!r}")
        texts[key] = texts[key].replace(old, new)
    for key, rel in FILES.items():
        (tree / "periph" / pathlib.Path(rel).name).write_text(texts[key])
    return tree


def run(tree, build_root):
    cmd = ["make", "-C", str(ROOT / "tb/cocotb/soc"), "crypto", f"RTL={tree}",
           f"SIM_BUILD_ROOT={build_root}", "SIM_BUILD_MIN_FREE_MB=500"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    log = r.stdout + r.stderr
    m = re.search(r"TESTS=(\d+) PASS=(\d+) FAIL=(\d+)", log)
    failing = sorted(set(re.findall(r"\*\* test_crypto\.(\S+)\s+FAIL", log)))
    return r.returncode, m.groups() if m else None, failing, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/mut_crypto_scan_wipe")
    ap.add_argument("--build-root", default="/nobackup/claude_sim_build/soc_j41m6_mut")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    survivors, invalid, killed = [], [], 0
    for name, why, edits in MUTANTS:
        if only and name not in only:
            continue
        tree = build(name, edits, out)
        rc, counts, failing, log = run(tree, a.build_root)
        (out / name / "run.log").write_text(log)
        if counts is None:
            verdict = "INVALID (no test result: build/lint/elaboration failure)"
            invalid.append(name)
        elif counts[2] == "0" and rc == 0:
            verdict = "SURVIVED"
            survivors.append(name)
        else:
            verdict = f"KILLED ({counts[2]}/{counts[0]} tests fail)"
            killed += 1
        print(f"{name:30s} {verdict:44s} {why}", flush=True)
        if failing:
            print(f"    failing: {', '.join(failing[:5])}{' ...' if len(failing) > 5 else ''}", flush=True)
    print(f"KILLED {killed}  SURVIVORS: {survivors if survivors else 'none'}  INVALID: {invalid if invalid else 'none'}")
    return 1 if survivors or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
