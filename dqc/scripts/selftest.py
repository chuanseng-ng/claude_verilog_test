#!/usr/bin/env python3
"""DQC negative control: prove the flow flags a known-bad design and spares the known-good part.

Runs SpyGlass cdc/cdc_verify_struct and rdc/rdc_verify_struct on dqc/selftest/bad_cdc.sv (no
waivers, own SGDC) through the SAME sg_run.tcl + dqc_report.py path the real goals use, then checks
the parsed rows:

  CDC: an unsynchronised-crossing rule (Ac_unsync*) names bad_data_q;   no Ac_unsync names ok_data_q
  RDC: a reset-domain-crossing rule (Ar_*, severity Error/Warning) names bad_rst_q

A selftest that passes is evidence the verdict logic can go red; it says nothing about soc_top.
Exit 0 only when every expectation holds.  Stdlib only (python 3.8).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DQC = os.path.dirname(HERE)
RUN = os.path.join(DQC, "run", "selftest")
SG = os.environ.get("SG", "sg_shell")


def run_goal(goal, tag):
    logdir = os.path.join(RUN, tag)
    os.makedirs(logdir, exist_ok=True)
    env = dict(os.environ, DQC_RUN=RUN, DQC_GOAL=goal, DQC_TOP="bad_cdc",
               DQC_SGDC=os.path.join(DQC, "selftest", "bad_cdc.sgdc"), DQC_AWL="")
    with open(os.path.join(logdir, "sg_shell.out"), "w") as out:
        subprocess.call(["/usr/bin/time", "-f", "%e s wall, %M KB peak RSS", "-o",
                         os.path.join(logdir, "time.txt"), SG, "-tcl",
                         os.path.join(HERE, "sg_run.tcl")], cwd=logdir, env=env,
                        stdout=out, stderr=subprocess.STDOUT)
    subprocess.call([sys.executable, os.path.join(HERE, "dqc_report.py"), "--goal", goal, "--run", RUN,
                     "--tag", tag, "--top", "bad_cdc", "--arm", "selftest", "--awl", ""])
    rows = []
    tsv = os.path.join(RUN, tag + ".unwaived.tsv")
    if os.path.isfile(tsv):
        for ln in open(tsv).read().splitlines()[1:]:
            p = ln.split("\t", 5)
            if len(p) == 6:
                rows.append(dict(cls=p[0], rule=p[1], sev=p[2], file=p[3], line=p[4], msg=p[5]))
    return rows


def main():
    os.makedirs(RUN, exist_ok=True)
    with open(os.path.join(RUN, "sources.sgf"), "w") as fh:
        fh.write(os.path.join(DQC, "selftest", "bad_cdc.sv") + "\n")
    open(os.path.join(RUN, "incdirs.txt"), "w").close()
    open(os.path.join(RUN, "defines.txt"), "w").close()

    fails = []
    cdc = run_goal("cdc/cdc_verify_struct", "cdc_verify")
    rdc = run_goal("rdc/rdc_verify_struct", "rdc")

    unsync = [r for r in cdc if r["rule"].startswith("Ac_unsync")]
    if not any("bad_data_q" in r["msg"] for r in unsync):
        fails.append("CDC: no Ac_unsync* row names bad_data_q (rows: %s)" % sorted({r["rule"] for r in cdc}))
    if any("ok_data_q" in r["msg"] or "s1_q" in r["msg"] for r in unsync):
        fails.append("CDC: the synchronised crossing was wrongly flagged unsynchronised")
    if not any(r["cls"] in ("error", "warning") and "bad_rst_q" in r["msg"] for r in rdc if r["rule"].startswith("Ar_")):
        fails.append("RDC: no Ar_* row names bad_rst_q (rows: %s)" % sorted({r["rule"] for r in rdc}))

    print("-" * 78)
    for f in fails:
        print("SELFTEST FAIL: " + f)
    print("SELFTEST %s (cdc rows=%d, rdc rows=%d)" % ("FAIL" if fails else "PASS", len(cdc), len(rdc)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
