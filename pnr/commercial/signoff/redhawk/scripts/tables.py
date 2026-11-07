#!/usr/bin/env python3
"""tables.py -- print the markdown tables for reports/redhawk_ir_summary.md from runs/<arm>/{static,dynamic}_summary.json."""
import json, os
here = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(here, "..", "runs")
arms = [("ICC2 b6", "icc2b6"), ("Innovus b6", "innovusb6"), ("OpenROAD", "openroad")]
def L(a, n):
    p = os.path.join(R, a, n)
    return json.load(open(p)) if os.path.exists(p) else None
S = {a: L(a, "static_summary.json") for _, a in arms}
D = {a: L(a, "dynamic_summary.json") for _, a in arms}
N = {a: L(a, "dynamic_nodecap_summary.json") for _, a in arms}
def row(lbl, f): print("| %s | %s |" % (lbl, " | ".join(f(a) for _, a in arms)))
print("| | " + " | ".join(n for n, _ in arms) + " |\n|---|" + "---|" * len(arms))
row("RedHawk total power (mW)", lambda a: "%.2f" % S[a]["rh_total_power_mW"])
row("pad current, sum VDD (mA)", lambda a: "%.2f" % S[a]["pad_current_mA"]["vdd_sum"])
for pk, pl in (("logic", "logic cells"), ("sram", "SRAM macros"), ("all", "all instances")):
    row("static VPWR drop worst, %s (mV / %%)" % pl, lambda a: "%.1f / %.2f%%" % (S[a]["populations"][pk]["worst_vpwr_drop_mV"], S[a]["populations"][pk]["worst_vpwr_drop_mV"] / 18))
    row("static VGND bounce worst, %s (mV / %%)" % pl, lambda a: "%.1f / %.2f%%" % (S[a]["populations"][pk]["worst_vgnd_bounce_mV"], S[a]["populations"][pk]["worst_vgnd_bounce_mV"] / 18))
    row("static VPWR+VGND worst, %s (mV / %%)" % pl, lambda a: "%.1f / %.2f%%" % (S[a]["populations"][pk]["worst_total_mV"], S[a]["populations"][pk]["worst_total_mV"] / 18))
row("static VPWR+VGND mean, logic cells (mV)", lambda a: "%.1f" % S[a]["populations"]["logic"]["avg_total_mV"])
row("static EM (metal/via violations, worst ratio)", lambda a: "%s/%s, %s %s" % (S[a]["em_static"]["metal_violations"], S[a]["em_static"]["via_violations"], S[a]["em_static"]["worst_wire"][1], S[a]["em_static"]["worst_wire"][5]))
print()
if all(D.values()):
    print("| dynamic | " + " | ".join(n for n, _ in arms) + " |\n|---|" + "---|" * len(arms))
    for pk, pl in (("logic+sram", "logic+SRAM"),):
        row("worst avgTW drop, %s (mV / %%)" % pl, lambda a: "%.1f / %.1f%%" % (D[a]["populations"][pk]["worst_avgTW_mV"], D[a]["populations"][pk]["worst_avgTW_mV"] / 18))
        row("worst minWC drop, %s (mV / %%)" % pl, lambda a: "%.1f / %.1f%%" % (D[a]["populations"][pk]["worst_minWC_mV"], D[a]["populations"][pk]["worst_minWC_mV"] / 18))
        row("mean avgTW drop, %s (mV / %%)" % pl, lambda a: "%.1f / %.1f%%" % (D[a]["populations"][pk]["mean_avgTW_mV"], D[a]["populations"][pk]["mean_avgTW_mV"] / 18))
        row("instances with avgTW > 5% / > 10% of VDD", lambda a: "%.1f%% / %.1f%%" % (100 * D[a]["populations"][pk]["frac_inst_avgTW_gt_5pct"], 100 * D[a]["populations"][pk]["frac_inst_avgTW_gt_10pct"]))
    row("worst SRAM macro avgTW / minWC (mV)", lambda a: "%.1f / %.1f" % (D[a]["populations"]["sram"]["worst_avgTW_mV"], D[a]["populations"]["sram"]["worst_minWC_mV"]))
    row("worst wire drop VPWR / VGND (mV, log)", lambda a: " / ".join(x.split()[1].replace("mV", "") for x in D[a]["log_worst_block"][1:3]))
    for md in ("AVG", "RMS", "PEAK"):
        row("dynamic EM %s: entries >=50%% / segments >=100%% / worst" % md, lambda a: "%d / %d / %s" % (D[a]["em_by_mode"][md]["entries_ge_50pct"], D[a]["em_by_mode"][md]["violations_ge_100pct"], D[a]["em_by_mode"][md].get("worst_wire_ratio_line", "-")))
if any(N.values()) and all(N.values()):
    print()
    row("NO-DECAP sensitivity: worst avgTW (mV / %)", lambda a: "%.1f / %.1f%%" % (N[a]["populations"]["logic+sram"]["worst_avgTW_mV"], N[a]["populations"]["logic+sram"]["worst_avgTW_mV"] / 18))
    row("NO-DECAP sensitivity: mean avgTW (mV)", lambda a: "%.1f" % N[a]["populations"]["logic+sram"]["mean_avgTW_mV"])
print()
for n, a in arms:
    print("**%s** static hotspot tiles (200 um, mean total drop): " % n + "; ".join("x %d-%d y %d-%d: %.1f mV" % (t["x_um"][0], t["x_um"][1], t["y_um"][0], t["y_um"][1], t["mean_total_mV"]) for t in S[a]["hotspot_tiles_200um"][:3]))
    if D[a]: print("   dynamic hotspot tiles (mean avgTW): " + "; ".join("x %d-%d y %d-%d: %.1f mV" % (t["x_um"][0], t["x_um"][1], t["y_um"][0], t["y_um"][1], t["mean_avgTW_mV"]) for t in D[a]["hotspot_tiles_200um"][:3]) + "; worst: " + "; ".join("%s (%.0f,%.0f) %.0f mV" % (t["inst"], t["x"], t["y"], t["drop_mV"]) for t in D[a]["top5_inst_avgTW"][:2]))
