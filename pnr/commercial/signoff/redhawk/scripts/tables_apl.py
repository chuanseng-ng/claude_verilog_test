#!/usr/bin/env python3
"""tables_apl.py -- STEP 8 markdown tables: RedHawk old (b6 generation, Liberty-default currents + W/L decap estimate + ideal feed) vs new (APL + ASSUMED package model), per arm."""
import json, os
here = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(here, "..", "reports")
def L(n):
    p = os.path.join(R, n); return json.load(open(p)) if os.path.exists(p) else None
cols = [("ICC2 b6 (old)", "icc2b6", ""), ("ICC2 b9 (new)", "icc2b9", ""), ("ICC2 b12 decap-filled (new)", "icc2b12", ""),
        ("Innovus b6 (old)", "innovusb6", ""), ("Innovus b11 (new)", "innovusb11", ""), ("OpenROAD B2 (old)", "openroad_b6model", ""), ("OpenROAD B2 (new)", "openroad", "")]
S = {a: L("%s_static_summary.json" % a) for _, a, _ in cols}
D = {a: L("%s_dynamic_summary.json" % a) for _, a, _ in cols}
N = {a: L("%s_dynamic_nodecap_summary.json" % a) for _, a, _ in cols}
E = {a: L("%s_dynamic_estdecap_summary.json" % a) for _, a, _ in cols}
def row(lbl, f):
    vals = []
    for _, a, _ in cols:
        try: vals.append(f(a))
        except Exception: vals.append("n/a")
    print("| %s | %s |" % (lbl, " | ".join(vals)))
print("| | " + " | ".join(c[0] for c in cols) + " |\n|---|" + "---|" * len(cols))
row("RedHawk total power (mW)", lambda a: "%.2f" % S[a]["rh_total_power_mW"])
row("static VPWR drop / VGND bounce worst (mV)", lambda a: "%.1f / %.1f" % (S[a]["populations"]["all"]["worst_vpwr_drop_mV"], S[a]["populations"]["all"]["worst_vgnd_bounce_mV"]))
row("static VPWR+VGND worst (mV / %)", lambda a: "%.1f / %.2f%%" % (S[a]["populations"]["all"]["worst_total_mV"], S[a]["populations"]["all"]["worst_total_mV"] / 18))
row("static EM violations (metal / via)", lambda a: "%d / %d" % (S[a]["em_static"]["metal_violations"], S[a]["em_static"]["via_violations"]))
g = lambda a, k: D[a]["populations"]["logic+sram"][k]
row("dynamic worst avgTW (mV / %)", lambda a: "%.1f / %.1f%%" % (g(a, "worst_avgTW_mV"), g(a, "worst_avgTW_mV") / 18))
row("dynamic worst minWC (mV)", lambda a: "%.1f" % g(a, "worst_minWC_mV"))
row("dynamic mean avgTW (mV)", lambda a: "%.1f" % g(a, "mean_avgTW_mV"))
row("dynamic instances above 5 % / 10 % of VDD", lambda a: "%.2f%% / %.2f%%" % (100 * g(a, "frac_inst_avgTW_gt_5pct"), 100 * g(a, "frac_inst_avgTW_gt_10pct")))
row("dynamic worst SRAM macro avgTW (mV)", lambda a: "%.1f" % D[a]["populations"]["sram"]["worst_avgTW_mV"])
import re
wr = lambda a, m: re.search(r"([\d.]+)%", D[a]["em_by_mode"][m]["worst_wire_ratio_line"]).group(1)
row("dynamic EM AVG / RMS: worst ratio (%)", lambda a: "%s / %s" % (wr(a, "AVG"), wr(a, "RMS")))
row("dynamic EM PEAK segments >= 100 % (not judged)", lambda a: str(D[a]["em_by_mode"]["PEAK"]["violations_ge_100pct"]))
n = lambda a, d, k: d[a]["populations"]["logic+sram"][k]
row("no decap: worst avgTW / mean (mV)", lambda a: "%.1f / %.1f" % (n(a, N, "worst_avgTW_mV"), n(a, N, "mean_avgTW_mV")))
row("APL std cells + W/L-ESTIMATED decap: worst avgTW / mean (mV)", lambda a: "%.1f / %.1f" % (n(a, E, "worst_avgTW_mV"), n(a, E, "mean_avgTW_mV")))
