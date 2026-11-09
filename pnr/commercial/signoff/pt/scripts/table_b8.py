#!/usr/bin/env python3 -I
"""table_b8.py [variant ...] -- b6 / b7 / b8 judge tables per SDC variant (base own iolat iolat_pv iolat_pvs) x 9 corners, both commercial arms.
Cells: setup WNS ns (violating endpoints) / hold WNS ns (violating endpoints) / r2r setup viol / r2r hold viol.   Reads signoff/pt/runs*/<arm>_<corner>/metrics.tsv."""
import os, sys
PT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
D = {"base": "runs", "own": "runs_own", "iolat": "runs_iolat", "iolat_pv": "runs_iolat_pv", "iolat_pvs": "runs_iolat_pvs"}
CORN = [f"{rc}_{lib}" for rc in ("nom", "min", "max") for lib in ("tt", "ss", "ff")]
GROUPS = {"ICC2": ["icc2b6", "icc2b7", "icc2b8"], "Innovus": ["innovusb6", "innovusb7", "innovusb8"]}
def m(var, arm, c):
    f = os.path.join(PT, D[var], f"{arm}_{c}", "metrics.tsv")
    if not os.path.isfile(f): return None
    d = dict(l.rstrip("\n").split("\t", 1) for l in open(f) if "\t" in l)
    return d
for var in (sys.argv[1:] or ["base", "own", "iolat", "iolat_pv", "iolat_pvs"]):
    for g, arms in GROUPS.items():
        print(f"\n### {g}, SDC variant `{var}`  (setup WNS ns (viol) / hold WNS ns (viol) / r2r setup viol / r2r hold viol)\n")
        print("| corner | " + " | ".join(arms) + " |"); print("|---|" + "---|" * len(arms))
        for c in CORN:
            row = []
            for a in arms:
                d = m(var, a, c)
                if not d: row.append("-"); continue
                row.append("%.3f (%s) / %.3f (%s) / %s / %s" % (float(d["setup_wns"]), d["setup_viol"], float(d["hold_wns"]), d["hold_viol"], d["r2rx_setup_viol"], d["r2rx_hold_viol"]))
            print(f"| {c} | " + " | ".join(row) + " |")
        pw = []
        for a in arms:
            f = os.path.join(PT, D[var], f"{a}_nom_tt", "power_B.txt")
            t = [l for l in open(f) if l.startswith("Total")] if os.path.isfile(f) else []
            pw.append(t[-1].split()[-2] + " " + t[-1].split()[-1] if t else "-")
        print("\nnom_tt PrimePower B total (W): " + "; ".join(f"{a} {p}" for a, p in zip(arms, pw)))
