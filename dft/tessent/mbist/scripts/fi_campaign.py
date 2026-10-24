#!/usr/bin/env python3
"""fi_campaign.py -- fault-injection campaign for the Tessent-generated MBIST (VCS), plus the in-house golden prediction
for the SAME fault universe.

Reuses the in-house fault catalogue (tb/cocotb/soc/mbist_golden.py::catalogue, 105 faults at AW=10) and the in-house
fault-injecting SRAM core (tb/cocotb/soc/sram_fi_core.sv, wrapped by tb/sky130_sram_fi_tess.sv so plusargs set the
fault).  Each Tessent pattern (one algorithm, full address count) is run once per fault with the compiled simv from
`make mbist-sim MBIST_MODEL=fi`; a fault is DETECTED when the testbench reports > 0 miscompares (the fault-free run of
the same simv reports 0, checked first).

Usage:  fi_campaign.py [--mem sr|wm|both] [--jobs 2] [--faults N]
Output: build/fi/results.json and build/fi/summary.md
"""
import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tb" / "cocotb" / "soc"))
import mbist_golden as g  # noqa: E402

SIMDIR = HERE / "build/run/simulation_outdir/mbist_eval_top_rtl1.simulation_full"
PATTERNS = {  # pattern -> Tessent algorithm
    "P_MARCHCM": "LVMARCHCMINUS", "P_SMARCH": "SMARCH", "P_CHKB": "SMARCHCHKB", "P_CHKBCI": "SMARCHCHKBCI",
    "P_CHKBCIL": "SMARCHCHKBCIL", "P_CKBD1X1": "LVCHECKERBOARD1X1",
}
RET_PATTERN = "P_RETENTION"
INHOUSE = {"MARCH_CM": 0, "CKBD": 3, "LANE": 4, "FULL": 5}  # alg numbers of mbist_ctrl


def lab(f):
    return f"P1STUCK(bit={f.v_bit} val={f.val})" if f.kind == 11 else f.label()


def plusargs(tag, f):
    return [f"+{tag}_kind={f.kind}", f"+{tag}_va={f.v_addr}", f"+{tag}_vb={f.v_bit}", f"+{tag}_aa={f.a_addr}",
            f"+{tag}_ab={f.a_bit}", f"+{tag}_val={f.val}", f"+{tag}_dir={f.dir}", f"+{tag}_ret={f.ret_t}"]


def run_one(pattern, args):
    d = next(SIMDIR.glob(f"{pattern}.simulation_fi"))
    p = subprocess.run(["./simv", "+nowarnTFMPC", "+NEWPATH=./patterns_directory", *args], cwd=d,
                       capture_output=True, text=True, timeout=900)
    m = re.search(r"Number of miscompares\s*=\s*(\d+)", p.stdout)
    if not m:
        raise RuntimeError(f"{pattern} {args}: no miscompare line\n{p.stdout[-800:]}")
    return int(m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mem", default="both", choices=["sr", "wm", "both"])
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--faults", type=int, default=0, help="limit catalogue size (debug)")
    a = ap.parse_args()
    out = HERE / "build/fi"
    out.mkdir(parents=True, exist_ok=True)

    cat = g.catalogue(10)
    if a.faults:
        cat = cat[: a.faults]
    # extra kinds not in the in-house catalogue: port-1 stuck (sr only; Tessent compares port B)
    cat = cat + [("P1STUCK", g.Fault(11, v_bit=9, val=1)), ("P1STUCK", g.Fault(11, v_bit=22, val=0))]
    mems = ["sr", "wm"] if a.mem == "both" else [a.mem]

    # fault-free control
    ctl = {p: run_one(p, []) for p in list(PATTERNS) + [RET_PATTERN]}
    assert all(v == 0 for v in ctl.values()), f"fault-free control not clean: {ctl}"
    print("fault-free control (miscompares per pattern):", ctl, flush=True)

    jobs = []
    for mem in mems:
        for cls, f in cat:
            if f.kind == 11 and mem == "wm":
                continue  # NPU weight memory ties port 1 off inside npu_weight_mem
            for p in PATTERNS:
                jobs.append((mem, cls, f, p))
    res = []

    def work(j):
        mem, cls, f, p = j
        return j, run_one(p, plusargs(mem, f))

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for n, (j, mis) in enumerate(ex.map(work, jobs)):
            mem, cls, f, p = j
            res.append({"mem": mem, "class": cls, "fault": lab(f), "kind": f.kind, "pattern": p,
                        "miscompares": mis, "detected": mis > 0})
            if n % 100 == 0:
                print(f"{n}/{len(jobs)}", flush=True)

    # retention: decay faults on cell (300,5) -> 0; ret_t in negedge counts.  Pause = 200 us / 25 ns = 8000 clocks (the longest write-to-read gap of a pause-free March is ~2100 clocks).
    ret_cases = [("RET decay 5000 clk (> back-to-back March gap, < 8000-clk pause)", g.Fault(9, v_addr=300, v_bit=5, val=0, ret_t=5000)),
                 ("RET decay 200000 clk (> pause)", g.Fault(9, v_addr=300, v_bit=5, val=0, ret_t=200000))]
    for mem in mems:
        for name, f in ret_cases:
            mis = run_one(RET_PATTERN, plusargs(mem, f))
            res.append({"mem": mem, "class": "RET", "fault": name, "kind": 9, "pattern": RET_PATTERN,
                        "miscompares": mis, "detected": mis > 0})
            # and the algorithms WITHOUT a pause must not see a retention fault
            mis2 = run_one("P_MARCHCM", plusargs(mem, f))
            res.append({"mem": mem, "class": "RET", "fault": name, "kind": 9, "pattern": "P_MARCHCM",
                        "miscompares": mis2, "detected": mis2 > 0})

    # in-house golden prediction, same faults (port 0 + port 1 of memory 0 as in soc_top: has_p1 = True)
    inh = {}
    for cls, f in cat:
        if f.kind == 11:
            continue  # golden model has no kind 11; covered by the in-house suite's P1STUCK test
        key = f.label()
        inh[key] = {name: g.golden_first_fail(alg, 10, True, f, bg_sweep=(name == "FULL")) is not None
                    for name, alg in INHOUSE.items()}
    json.dump({"control": ctl, "tessent": res, "inhouse_golden": inh}, (out / "results.json").open("w"), indent=1)

    # ---- summary table: detected / injected per fault class and algorithm -----------------------
    per = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in res:
        if r["class"] == "RET":
            continue
        c = r["class"].replace("_intra", " (intra-word)")
        per[c][r["pattern"]][1] += 1
        per[c][r["pattern"]][0] += r["detected"]
    cols = list(PATTERNS)
    lines = ["| Fault class | " + " | ".join(PATTERNS[c] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for c in sorted(per):
        lines.append(f"| {c} | " + " | ".join(f"{per[c][p][0]}/{per[c][p][1]}" for p in cols) + " |")
    tot = {p: [sum(per[c][p][0] for c in per), sum(per[c][p][1] for c in per)] for p in cols}
    lines.append("| **all** | " + " | ".join(f"**{tot[p][0]}/{tot[p][1]}**" for p in cols) + " |")

    # in-house golden, per class
    ih = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for cls, f in cat:
        if f.kind == 11:
            continue
        c = cls.replace("_intra", " (intra-word)")
        for name in INHOUSE:
            ih[c][name][1] += 1
            ih[c][name][0] += inh[f.label()][name]
    lines += ["", "| Fault class | " + " | ".join(INHOUSE) + " |", "|---|" + "---|" * len(INHOUSE)]
    for c in sorted(ih):
        lines.append(f"| {c} | " + " | ".join(f"{ih[c][n][0]}/{ih[c][n][1]}" for n in INHOUSE) + " |")
    itot = {n: [sum(ih[c][n][0] for c in ih), sum(ih[c][n][1] for c in ih)] for n in INHOUSE}
    lines.append("| **all** | " + " | ".join(f"**{itot[n][0]}/{itot[n][1]}**" for n in INHOUSE) + " |")
    lines += ["", "Retention (Tessent, 200 us pause):"]
    for r in res:
        if r["class"] == "RET":
            lines.append(f"- mem {r['mem']}, {r['fault']}, {r['pattern']}: {r['miscompares']} miscompares "
                         f"({'DETECTED' if r['detected'] else 'not detected'})")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
