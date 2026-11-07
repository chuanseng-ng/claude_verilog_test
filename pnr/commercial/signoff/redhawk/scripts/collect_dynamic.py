#!/usr/bin/env python3
"""collect_dynamic.py <arm> [rundir-name] -- parse RedHawk vectorless dynamic run (adsRpt/Dynamic/*.dvd) into JSON + text.
dvd columns: x y eff_Vdd max_pg_tw min_pg_tw min_pg_sim max_pg_sim min_vdd_tw max_vss_tw domain inst
 eff_Vdd = time-window-average of (VDD-VSS) at the instance; drop_avgTW = 1.8 - eff_Vdd ; drop_minTW = 1.8 - min_pg_tw ; drop_minWC = 1.8 - min_pg_sim
 (min over the whole simulation, any time).  RedHawk's headline dynamic number is the instance-level avgTW/minTW; minWC is the absolute waveform minimum."""
import json, os, re, sys, collections
arm = sys.argv[1]; sub = sys.argv[2] if len(sys.argv) > 2 else "rh-dynamic"
here = os.path.dirname(os.path.abspath(__file__))
d = os.path.join(here, "..", "runs", arm, sub, "adsRpt")
VDD = 1.8
ptl = {}
with open(os.path.join(here, "..", "runs", arm, "pt", "instance_power.txt")) as f:
    for line in f:
        p = line.split(); ptl[p[0]] = p[2]
def cls(n):
    r = ptl.get(n)
    if r is None: return "fill_tap"
    return "sram" if r.startswith("sky130_sram") else "logic"
rows = []
with open(os.path.join(d, "Dynamic/rv32i_cpu_top.dvd")) as f:
    for line in f:
        if line.startswith("#"): continue
        p = line.split()
        if len(p) < 11: continue
        try: v = [float(x) for x in p[:9]]
        except ValueError: continue          # 'n/a' (no timing window)
        rows.append((v, p[10]))
def pop(c): return [r for r in rows if cls(r[1]) == c]
def stats(rs):
    if not rs: return None
    avg = [VDD - r[0][2] for r in rs]; mn = [VDD - r[0][4] for r in rs]; wc = [VDD - r[0][5] for r in rs]
    i = max(range(len(rs)), key=lambda k: avg[k]); j = max(range(len(rs)), key=lambda k: wc[k])
    return {"n": len(rs), "worst_avgTW_mV": avg[i] * 1e3, "worst_avgTW_at": [rs[i][0][0], rs[i][0][1], rs[i][1]],
            "mean_avgTW_mV": sum(avg) / len(avg) * 1e3, "worst_minTW_mV": max(mn) * 1e3, "worst_minWC_mV": wc[j] * 1e3,
            "worst_minWC_at": [rs[j][0][0], rs[j][0][1], rs[j][1]], "mean_minWC_mV": sum(wc) / len(wc) * 1e3,
            "frac_inst_avgTW_gt_5pct": sum(1 for x in avg if x > 0.05 * VDD) / len(avg), "frac_inst_avgTW_gt_10pct": sum(1 for x in avg if x > 0.10 * VDD) / len(avg)}
out = {"arm": arm, "run": sub, "populations": {c: stats(pop(c)) for c in ("logic", "sram", "fill_tap")}}
out["populations"]["logic+sram"] = stats(pop("logic") + pop("sram"))
T = 200.0; tiles = collections.defaultdict(list)
for r in pop("logic") + pop("sram"):
    tiles[(int(r[0][0] // T), int(r[0][1] // T))].append(VDD - r[0][2])
top = sorted(((sum(v) / len(v), len(v), k) for k, v in tiles.items() if len(v) >= 20), reverse=True)[:5]
out["hotspot_tiles_200um"] = [{"x_um": [k[0] * T, (k[0] + 1) * T], "y_um": [k[1] * T, (k[1] + 1) * T], "mean_avgTW_mV": m * 1e3, "n_inst": n} for m, n, k in top]
top_inst = sorted(pop("logic") + pop("sram"), key=lambda r: r[0][2])[:5]
out["top5_inst_avgTW"] = [{"inst": r[1], "x": r[0][0], "y": r[0][1], "drop_mV": (VDD - r[0][2]) * 1e3} for r in top_inst]
# sram per macro
out["sram_macros"] = sorted(({"name": r[1], "avgTW_mV": (VDD - r[0][2]) * 1e3, "minWC_mV": (VDD - r[0][5]) * 1e3} for r in pop("sram")), key=lambda s: -s["avgTW_mV"])
lg = open(os.path.join(d, "redhawk.log")).read()
m = re.search(r"Worst Dynamic Voltage Drop:.*?-+\n(.*?)\n\n", lg, re.S)
out["log_worst_block"] = m.group(1).splitlines()[1:] if m else None
m = re.search(r"Total chip power, ([\d.eE+-]+) Watt", lg) or re.search(r"Total chip power, ([\d.eE+-]+) Watt", open(os.path.join(d, "power_summary.rpt")).read())
out["rh_total_power_mW"] = float(m.group(1)) * 1e3 if m else None
m = re.search(r"Presim is determined to be (\d+) ps", lg); out["presim_ps"] = int(m.group(1)) if m else None
# decap accounted by RedHawk
try:
    dc = collections.Counter()
    with open(os.path.join(d, "Dynamic/decaps.rpt")) as f:
        for line in f:
            if line.startswith("#"): continue
            dc[re.sub(r"!\d+\s.*", "", re.sub(r"^.*!(sky130_\w+)!.*$", r"\1", line.split()[0]))] += 1
    out["decap_instances_in_dynamic"] = sum(dc.values())
except OSError: pass
# dynamic EM: one report per mode (run_dynamic.tcl snapshots em.worst.<MODE>); falls back to the default-mode file
em = {}
for md in ("AVG", "RMS", "PEAK"):
    p = os.path.join(d, "Dynamic", "em.worst." + md)
    if not os.path.exists(p): continue
    n = 0; mx = 0.0; nv = 0; mode = None; byl = collections.Counter()
    for line in open(p):
        if line.startswith("# EM MODE"): mode = line.split()[-1]
        if line.startswith("#"): continue
        mm = re.search(r"([\d.]+)%", line)
        if mm:
            r = float(mm.group(1)); n += 1; mx = max(mx, r)
            if r >= 100: nv += 1; byl[line.split()[0]] += 1
    em[md] = {"file_mode": mode, "entries_ge_50pct": n, "max_ratio_pct": mx, "violations_ge_100pct": nv, "violations_by_layer": dict(byl)}
for md, key in (("PEAK", "PEAK"), ("AVG", "DC"), ("RMS", "RMS")):
    m = re.search(r"Worst %s EM:.*?-+\n(WIRE[^\n]*)\n?(VIA[^\n]*)?" % key, lg, re.S) if False else None
out["em_by_mode"] = em
for md, key in (("PEAK", "PEAK"), ("AVG", "DC"), ("RMS", "RMS")):
    m = re.search(r"Worst %s EM:\s*\n-+\nType[^\n]*\n-+\n(WIRE[^\n]*)" % key, lg)
    if md in em and m: em[md]["worst_wire_ratio_line"] = " ".join(m.group(1).split()[:6])
json.dump(out, open(os.path.join(d, "..", "..", "dynamic_summary.json" if sub == "rh-dynamic" else "dynamic_nodecap_summary.json"), "w"), indent=1)
for k, s in out["populations"].items():
    if s: print("%-10s n=%-7d avgTW worst %.1f mV (%.2f%%) mean %.1f | minTW worst %.1f | minWC worst %.1f mV (%.2f%%) mean %.1f | >5%%: %.3f >10%%: %.3f" % (k, s["n"], s["worst_avgTW_mV"], s["worst_avgTW_mV"]/18, s["mean_avgTW_mV"], s["worst_minTW_mV"], s["worst_minWC_mV"], s["worst_minWC_mV"]/18, s["mean_minWC_mV"], s["frac_inst_avgTW_gt_5pct"], s["frac_inst_avgTW_gt_10pct"]))
print("log worst:", out["log_worst_block"]); print("EM dyn:", em)
