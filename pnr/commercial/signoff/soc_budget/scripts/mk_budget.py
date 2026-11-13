#!/usr/bin/env python3
"""mk_budget.py -- build pt/iolat_pv/iobud_soc.tsv (SoC-context input-delay budgets) from runs/dc/arrival_{tt,ss,ff}.tsv.   python3 -I mk_budget.py
RULE (doc 4.2f):  ARR(lib, group) = worst bit of the group, launch-edge -> macro pin, driver cells + macro-Liberty pin load, zero wire (pt_arrival.tcl).
  budget = min(CURRENT, ceil_to_0.1( MARGIN_K * ARR ))   -- absolute ns after the launching clock edge, NOT a fraction of the period (clk->Q + logic does
  not scale with the clock period, so the SoC's 25 ns and the macro's 13.333 ns map to the same ns value). A derived value above the current SDC delay would tighten the constraint, so the current value is kept and flagged.
  rc corners: StarRC min/nom/max share the lib corner's driver arrival (no SoC SPEF exists, no wire modelled), so the 3 rc rows of a lib are equal.
"""
import math, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "../../../../.."))
RUNS = os.path.join(HERE, "../runs/dc"); OUT = os.path.join(ROOT, "pnr/commercial/signoff/pt/iolat_pv/iobud_soc.tsv")
EVID = os.path.join(HERE, "../runs/budget_evidence.tsv")
K = float(os.environ.get("MARGIN_K", "2.0"))
CUR = {"awready": 2.0, "wready": 2.0, "arready": 2.0, "bresp": 2.0, "bvalid": 2.0, "rdata": 2.0, "rresp": 2.0, "rvalid": 2.0, "rlast": 2.0,
       "paddr": 3.5, "psel": 3.5, "penable": 3.5, "pwrite": 3.5, "pwdata": 3.5}
arr = collections.defaultdict(float); n = collections.Counter()
for lib in ("tt", "ss", "ff"):
    for l in open(os.path.join(RUNS, f"arrival_{lib}.tsv")):
        if l.startswith("#") or not l.strip(): continue
        lb, g, port, cap, amax, amin, sp = l.rstrip("\n").split("\t")
        g = re.sub(r"^(axi|apb)_", "", g); g = re.sub(r"_i$", "", g)
        if amax == "NA": sys.exit(f"no arrival for {lb} {port}")
        arr[(lb, g)] = max(arr[(lb, g)], float(amax)); n[(lb, g)] += 1
rows = []; ev = ["lib\tgroup\tbits\tarrival_ns\tK\tk_arrival_ns\tcurrent_ns\tbudget_ns\tnote"]
for lib in ("tt", "ss", "ff"):
    for g, cur in CUR.items():
        a = arr[(lib, g)]; assert n[(lib, g)] > 0, (lib, g)
        want = math.ceil(K * a * 10 - 1e-9) / 10
        b = min(cur, want); note = "relaxed" if b < cur else "kept current (derived >= current)"
        ev.append(f"{lib}\t{g}\t{n[(lib, g)]}\t{a:.4f}\t{K}\t{want:.1f}\t{cur}\t{b}\t{note}")
        for rc in ("nom", "min", "max"): rows.append((rc, lib, g, b))
with open(OUT, "w") as f:
    f.write(f"# SoC-context input-delay budgets (ns, -max) for sky130_cpu_iolat_pv_soc.sdc: rc, lib, group, value.  Built by soc_budget/scripts/mk_budget.py, K={K}.\n")
    for rc, lib, g, b in rows: f.write(f"{rc}\t{lib}\t{g}\t{b}\n")
open(EVID, "w").write("\n".join(ev) + "\n")
print(open(EVID).read())
