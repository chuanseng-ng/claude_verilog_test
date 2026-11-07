#!/usr/bin/env python3
"""collect_static.py <arm> [rundir-name]  -- parse a RedHawk static run (adsRpt/Static/*) into a JSON + short text summary.
Per-instance numbers come from adsRpt/Static/rv32i_cpu_top.inst:  eff(vdd-vss)  vdd_drop  gnd_bounce  ideal  net  (x,y)  name
Three populations: ALL (includes fill/tap, which sit on the same rails), LOGIC (std cells with power: not xofiller/tapfiller/decap), SRAM (10 macros)."""
import json, math, os, re, sys, collections
arm = sys.argv[1]; sub = sys.argv[2] if len(sys.argv) > 2 else "rh-static"
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", arm, sub, "adsRpt")
open(os.path.join(d, "redhawk.log")).close()
VDD = 1.8
rows = []
rx = re.compile(r"^\s*([\d.]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.]+)\s+(\S+)\s+\(\s*([\d.]+),\s*([\d.]+)\)\s+(.*\S)\s*$")
with open(os.path.join(d, "Static/rv32i_cpu_top.inst")) as f:
    for line in f:
        if line.startswith("#"): continue
        m = rx.match(line)
        if not m: continue
        eff, dv, gb, ideal, net, x, y, name = m.groups()
        rows.append((float(dv), float(gb), float(x), float(y), name))
# population by PrimePower instance list (real cells with power) -- names are the escape-free names RedHawk prints
ptl = {}
with open(os.path.join(d, "..", "..", "pt", "instance_power.txt")) as f:
    for line in f:
        p = line.split(); ptl[p[0]] = p[2]
def cls(n):
    r = ptl.get(n)
    if r is None: return "fill_tap"        # physical-only: fill, decap, tap, endcap (not in the netlist)
    return "sram" if r.startswith("sky130_sram") else "logic"
pop = collections.defaultdict(list)
for r in rows:
    pop["all"].append(r); pop[cls(r[4])].append(r)
def stats(rs):
    if not rs: return None
    tot = [r[0] + r[1] for r in rs]
    wv = max(rs, key=lambda r: r[0]); wg = max(rs, key=lambda r: r[1]); wt = max(rs, key=lambda r: r[0] + r[1])
    return {"n": len(rs),
            "worst_vpwr_drop_mV": wv[0] * 1e3, "worst_vpwr_at": [wv[2], wv[3], wv[4]],
            "worst_vgnd_bounce_mV": wg[1] * 1e3, "worst_vgnd_at": [wg[2], wg[3], wg[4]],
            "worst_total_mV": (wt[0] + wt[1]) * 1e3, "worst_total_at": [wt[2], wt[3], wt[4]],
            "avg_vpwr_drop_mV": sum(r[0] for r in rs) / len(rs) * 1e3, "avg_vgnd_bounce_mV": sum(r[1] for r in rs) / len(rs) * 1e3,
            "avg_total_mV": sum(tot) / len(tot) * 1e3}
out = {"arm": arm, "run": sub, "vdd_V": VDD, "populations": {k: stats(v) for k, v in pop.items()}}
# hotspots: 200 um tiles by mean total drop over LOGIC+SRAM instances (fill/tap excluded so a tile is judged by real loads)
T = 200.0; tiles = collections.defaultdict(list)
for r in pop["logic"] + pop["sram"]:
    tiles[(int(r[2] // T), int(r[3] // T))].append(r[0] + r[1])
top = sorted(((sum(v) / len(v), len(v), k) for k, v in tiles.items() if len(v) >= 20), reverse=True)[:5]
out["hotspot_tiles_200um"] = [{"x_um": [k[0] * T, (k[0] + 1) * T], "y_um": [k[1] * T, (k[1] + 1) * T], "mean_total_mV": m * 1e3, "n_inst": n} for m, n, k in top]
# SRAM per macro
out["sram_macros"] = sorted(({"name": r[4], "vdd_drop_mV": r[0] * 1e3, "gnd_bounce_mV": r[1] * 1e3, "x": r[2], "y": r[3]} for r in pop["sram"]), key=lambda s: -(s["vdd_drop_mV"] + s["gnd_bounce_mV"]))
# pad currents
pads = []
try:
    with open(os.path.join(d, "Static/pad.current")) as f:
        for line in f:
            m = re.match(r"^\s*([-\d.eE+]+)\s+\(\s*([\d.]+),\s*([\d.]+)\)\s+(\S+)", line)
            if m: pads.append((float(m.group(1)), m.group(4)))
except OSError: pass
out["pad_current_mA"] = {"vdd_sum": sum(p[0] for p in pads if "_vdd_" in p[1]), "vss_sum": sum(p[0] for p in pads if "_vss_" in p[1]), "n": len(pads),
                         "max": max((p[0] for p in pads), default=None)}
# power as RedHawk saw it
try:
    t = open(os.path.join(d, "power_summary.rpt")).read()
    m = re.search(r"Total chip power, ([\d.eE+-]+) Watt", t); out["rh_total_power_mW"] = float(m.group(1)) * 1e3 if m else None
except OSError: pass
# EM
em = os.path.join(d, "Static")
emf = [f for f in os.listdir(em) if f.endswith(".em.worst")]
if emf:
    nviol = 0; worst = None; bylayer = collections.Counter(); nrep = 0
    with open(os.path.join(em, emf[0])) as f:
        for line in f:
            if line.startswith("#"): continue
            m = re.search(r"([\d.]+)%", line)
            if not m: continue
            nrep += 1; ratio = float(m.group(1))
            if ratio >= 100.0: nviol += 1; bylayer[line.split()[0]] += 1
            if worst is None or ratio > worst[0]: worst = (ratio, line.strip())
    lg = open(os.path.join(d, "redhawk.log")).read()
    mm = re.search(r"Total number of metal EM violations: (\d+)\s+Total number of via\s+EM violations: (\d+)", lg)
    ww = re.search(r"Worst Static EM:.*?-+\n(WIRE.*)\n(VIA.*)\n", lg, re.S)
    out["em_static"] = {"file": emf[0], "entries_ge_50pct": nrep, "metal_violations": int(mm.group(1)) if mm else None, "via_violations": int(mm.group(2)) if mm else None,
                        "worst_wire": ww.group(1).split()[:6] if ww else None, "worst_via": ww.group(2).split()[:6] if ww else None}
else:
    out["em_static"] = None
json.dump(out, open(os.path.join(d, "..", "..", "static_summary.json"), "w"), indent=1)
for k in ("all", "logic", "sram", "fill_tap"):
    s = out["populations"].get(k)
    if s: print("%-9s n=%-7d VPWR drop worst %.2f mV avg %.2f | VGND bounce worst %.2f avg %.2f | total worst %.2f mV (%.2f%%) avg %.2f mV" % (
        k, s["n"], s["worst_vpwr_drop_mV"], s["avg_vpwr_drop_mV"], s["worst_vgnd_bounce_mV"], s["avg_vgnd_bounce_mV"], s["worst_total_mV"], s["worst_total_mV"] / VDD / 10, s["avg_total_mV"]))
print("RedHawk total power %.3f mW; pad current VDD %.2f mA VSS %.2f mA (%d pads)" % (out.get("rh_total_power_mW", float("nan")), out["pad_current_mA"]["vdd_sum"], out["pad_current_mA"]["vss_sum"], out["pad_current_mA"]["n"]))
print("EM:", out["em_static"])
