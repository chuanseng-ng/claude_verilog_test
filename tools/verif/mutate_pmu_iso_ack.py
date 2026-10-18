#!/usr/bin/env python3
"""Mutation campaign for the PMU iso-ack handshake (bead 3ogd).

Each mutant is a textual edit of rtl/soc/pmu.sv or rtl/soc/soc_top.sv applied to a private copy of
the rtl tree under OUT_DIR and fed to the very same suites CI runs through `make <suite> RTL=<tree>`:

  * `pmu` (standalone tb_pmu, ~30 s) for pmu.sv mutants;
  * `soc_pmu_iso_ack` (full tb_soc_top build, minutes) for soc_top.sv mutants and for the pmu.sv
    mutants that only the SoC-level ack plumbing can expose.

A mutant is KILLED when the run reports a FAIL, SURVIVED when everything passes, and INVALID when it
does not elaborate / produces no result (reported, counted neither way: a mutant must be killed by
behaviour, not by a build error). A pattern that does not occur exactly once is an error, not a
survivor. A SURVIVED entry marked `expect_survive` carries the reason it cannot be killed by a
zero-delay cocotb run; anything else surviving is a gap in the tests.

Usage (inside the nix sim devshell):
    python3 tools/verif/mutate_pmu_iso_ack.py [--out DIR] [--build-root DIR] [--only NAME[,NAME...]]
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PMU = "rtl/soc/pmu.sv"
TOP = "rtl/soc/soc_top.sv"

# (name, suite, file, why, [(old, new), ...], expect_survive_reason or None)
MUTANTS = [
    # ---- pmu.sv: the wait states -------------------------------------------------------------
    ("p01_pd_iso_ignores_ack", "pmu", PMU, "DOM_PD_ISO advances without waiting for the ack",
     [("(iso_ack_w[d] || wait_hit[d]) ? DOM_PD_GATE", "1'b1 ? DOM_PD_GATE")], None),
    ("p02_pd_iso_waits_on_low_ack", "pmu", PMU, "DOM_PD_ISO waits for the ack to be LOW",
     [("(iso_ack_w[d] || wait_hit[d]) ? DOM_PD_GATE", "(!iso_ack_w[d] || wait_hit[d]) ? DOM_PD_GATE")], None),
    ("p03_pd_iso_reverses_without_ack", "pmu", PMU, "no ack -> the power-down reverses to ON",
     [("                                                                                   : DOM_PD_ISO;",
       "                                                                                   : DOM_ON;")], None),
    ("p04_pu_iso_no_release_wait", "pmu", PMU, "DOM_PU_ISO settles at ON without waiting for the ack to fall (stale ack)",
     [("(!iso_ack_w[d] || wait_hit[d]) ? DOM_ON", "1'b1 ? DOM_ON")], None),
    ("p05_pu_iso_waits_on_high_ack", "pmu", PMU, "DOM_PU_ISO waits for the ack to be HIGH",
     [("(!iso_ack_w[d] || wait_hit[d]) ? DOM_ON", "(iso_ack_w[d] || wait_hit[d]) ? DOM_ON")], None),
    # ---- pmu.sv: the timeout -----------------------------------------------------------------
    ("t01_no_timeout_pd", "pmu", PMU, "the power-down wait can never time out (PMU hangs)",
     [("((dom_state_q[d] == DOM_PD_ISO) && !iso_ack_w[d]) ||", "1'b0 ||")], None),
    ("t02_no_timeout_pu", "pmu", PMU, "the power-up wait can never time out",
     [("((dom_state_q[d] == DOM_PU_ISO) &&  iso_ack_w[d]);", "1'b0;")], None),
    ("t03_timeout_one_short", "pmu", PMU, "timeout expires one cycle early",
     [("(wait_cnt_q == CW'(ISO_ACK_TIMEOUT - 1))", "(wait_cnt_q == CW'(ISO_ACK_TIMEOUT - 2))")], None),
    ("t04_timeout_one_long", "pmu", PMU, "timeout expires one cycle late",
     [("(wait_cnt_q == CW'(ISO_ACK_TIMEOUT - 1))", "(wait_cnt_q == CW'(ISO_ACK_TIMEOUT))")], None),
    ("t05_counter_carries_over", "pmu", PMU, "the counter holds (not cleared) between waits",
     [("else                             wait_cnt_q <= '0;", "else                             wait_cnt_q <= wait_cnt_q;")], None),
    ("t06_counter_not_reset", "pmu", PMU, "the counter has no reset",
     [("                        wait_cnt_q       <= '0;\n                        cpu_iso_ack_to_q <= 1'b0;\n                    end else begin",
       "                        cpu_iso_ack_to_q <= 1'b0;\n                    end else begin")],
     "equivalent: dom_state_q is reset to DOM_ON, so wait_active is 0 from the first cycle of reset and "
     "the counter's own 'else' branch clears it on the first edge after release; nothing reads the counter "
     "outside a wait"),
    ("t07_flag_never_set", "pmu", PMU, "STATUS[3] is never set on a timeout",
     [("else if (wait_hit[d])                              cpu_iso_ack_to_q <= 1'b1;", "else if (1'b0)                                     cpu_iso_ack_to_q <= 1'b1;")], None),
    ("t08_flag_set_on_any_wait", "pmu", PMU, "STATUS[3] is set whenever a wait starts, not only on timeout",
     [("else if (wait_hit[d])                              cpu_iso_ack_to_q <= 1'b1;", "else if (wait_active)                               cpu_iso_ack_to_q <= 1'b1;")], None),
    ("t09_flag_not_cleared_by_power_down", "pmu", PMU, "STATUS[3] is sticky forever (only reset clears it)",
     [("if (dom_state_q[d] == DOM_ON && !dom_target_on[d]) cpu_iso_ack_to_q <= 1'b0;\n                        else if",
       "if (1'b0) cpu_iso_ack_to_q <= 1'b0;\n                        else if")], None),
    ("t10_flag_not_reset", "pmu", PMU, "STATUS[3] has no reset",
     [("                        wait_cnt_q       <= '0;\n                        cpu_iso_ack_to_q <= 1'b0;\n                    end else begin",
       "                        wait_cnt_q       <= '0;\n                    end else begin")], None),
    ("t11_flag_wrong_bit", "pmu", PMU, "the flag is reported at STATUS[4]",
     [("{28'b0, cpu_iso_ack_to_q, pmu_busy, gpu_domain_on, cpu_domain_on}", "{27'b0, cpu_iso_ack_to_q, 1'b0, pmu_busy, gpu_domain_on, cpu_domain_on}")], None),
    ("t12_timeout_and_not_or", "pmu", PMU, "timeout and ack must BOTH hold to advance PD_ISO",
     [("(iso_ack_w[d] || wait_hit[d]) ? DOM_PD_GATE", "(iso_ack_w[d] && wait_hit[d]) ? DOM_PD_GATE")], None),
    # ---- pmu.sv: GPU independence ------------------------------------------------------------
    ("g01_gpu_uses_cpu_ack", "pmu", PMU, "the GPU domain waits on the CPU ack",
     [("assign iso_ack_w[d] = iso_en_q[d];", "assign iso_ack_w[d] = cpu_iso_ack_i;")], None),
    ("g02_gpu_never_acks", "pmu", PMU, "the GPU's internal ack is tied low",
     [("assign iso_ack_w[d] = iso_en_q[d];", "assign iso_ack_w[d] = 1'b0;")], None),
    # ---- soc_top.sv: the return crossing ------------------------------------------------------
    ("s01_ack_from_unsynced_iso", "soc_pmu_iso_ack", TOP, "ack is a sync of the RAW pmu_cpu_iso_en (never waits for the CPU domain)",
     [(".d_i     (pmu_cpu_iso_en_sync),\n        .q_o     (pmu_cpu_iso_ack)", ".d_i     (pmu_cpu_iso_en),\n        .q_o     (pmu_cpu_iso_ack)")], None),
    ("s02_ack_tied_high", "soc_pmu_iso_ack", TOP, "cpu_iso_ack_i tied 1 (the pre-3ogd behaviour, plus 0-cycle wait)",
     [(".cpu_iso_ack_i       (pmu_cpu_iso_ack),", ".cpu_iso_ack_i       (1'b1),")], None),
    ("s03_ack_tied_low", "soc_pmu_iso_ack", TOP, "cpu_iso_ack_i tied 0 (every power-down times out)",
     [(".cpu_iso_ack_i       (pmu_cpu_iso_ack),", ".cpu_iso_ack_i       (1'b0),")], None),
    ("s04_ack_not_synchronised", "soc_pmu_iso_ack", TOP, "the return crossing is a bare wire (no cdc_sync into core_clk)",
     [("    ) u_cpu_iso_ack_sync (\n        .clk_i   (core_clk),", "    ) u_cpu_iso_ack_sync (\n        .clk_i   (cpu_core_clk),")], None),
    ("s05_ack_after_cpu_gating", "soc_pmu_iso_ack", TOP, "ack sync reset by cpu_core_rst_n instead of core_rst_n",
     [(".rst_n_i (core_rst_n),\n        .d_i     (pmu_cpu_iso_en_sync),", ".rst_n_i (cpu_core_rst_n),\n        .d_i     (pmu_cpu_iso_en_sync),")],
     "equivalent for the property: both resets are released long before the first power cycle and the ack path only matters with both domains alive; the dead-CPU-clock test exercises cpu_core_rst_n low, where the sync is already held at 0 by its own chain"),
    # ---- part 2: ISO_GPU clamp on m_axil_if_rready -------------------------------------------
    ("c01_gif_rready_unclamped", "soc_pmu_iso_ack", TOP, "m_axil_if_rready clamp removed (PR #301)",
     [("assign gif_axil_rready    = pmu_gpu_iso_en ? 1'b0 : gpu_gif_rready_raw;", "assign gif_axil_rready    = gpu_gif_rready_raw;")], None),
    ("c02_gif_rready_inverted", "soc_pmu_iso_ack", TOP, "m_axil_if_rready clamp polarity inverted",
     [("assign gif_axil_rready    = pmu_gpu_iso_en ? 1'b0 : gpu_gif_rready_raw;", "assign gif_axil_rready    = pmu_gpu_iso_en ? gpu_gif_rready_raw : 1'b0;")], None),
]


def build(name, fkey, edits, out):
    base = out / name
    if base.exists():
        shutil.rmtree(base)
    shutil.copytree(ROOT / "rtl", base / "rtl")
    path = base / fkey
    text = (ROOT / fkey).read_text()
    for old, new in edits:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"mutant {name}: pattern occurs {n}x in {fkey} (need 1): {old[:70]!r}")
        text = text.replace(old, new)
    path.write_text(text)
    return base / "rtl"


def run(suite, tree, build_root):
    cmd = ["make", "-C", str(ROOT / "tb/cocotb/soc"), suite, f"RTL={tree}",
           f"SIM_BUILD_ROOT={build_root}", "SIM_BUILD_MIN_FREE_MB=500"]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log = r.stdout + r.stderr
    m = re.search(r"TESTS=(\d+) PASS=(\d+) FAIL=(\d+)", log)
    failing = sorted(set(re.findall(r"\*\* test_\w+\.(\S+)\s+FAIL", log)))
    return r.returncode, m.groups() if m else None, failing, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/mut_pmu_iso_ack")
    ap.add_argument("--build-root", default="/tmp/mut_pmu_iso_ack_build")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    survivors, invalid, expected, killed = [], [], [], 0
    for name, suite, fkey, why, edits, reason in MUTANTS:
        if only and name not in only:
            continue
        tree = build(name, fkey, edits, out)
        rc, counts, failing, log = run(suite, tree, a.build_root)
        (out / name / "run.log").write_text(log)
        if counts is None:
            verdict = "INVALID (no test result: build/lint/elaboration failure)"
            invalid.append(name)
        elif counts[2] == "0" and rc == 0:
            if reason:
                verdict = "SURVIVED (expected)"
                expected.append(name)
            else:
                verdict = "SURVIVED"
                survivors.append(name)
        else:
            verdict = f"KILLED ({counts[2]}/{counts[0]} tests fail)"
            killed += 1
        print(f"{name:36s} {suite:16s} {verdict:34s} {why}", flush=True)
        if failing:
            print(f"    failing: {', '.join(failing[:6])}{' ...' if len(failing) > 6 else ''}", flush=True)
        if verdict.startswith("SURVIVED (expected)"):
            print(f"    reason: {reason}", flush=True)
    print(f"KILLED {killed}  SURVIVORS: {survivors or 'none'}  EXPECTED-SURVIVORS: {expected or 'none'}  "
          f"INVALID: {invalid or 'none'}")
    return 1 if survivors or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
