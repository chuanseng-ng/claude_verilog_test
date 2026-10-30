#!/usr/bin/env python3
"""summ_compare.py -- side-by-side 9-corner table of several judged arms/vintages, both SDC variants.
usage: summ_compare.py label=<reports dir base>:<reports dir iolat>:<arm> [...]   (dirs relative to pt/reports/)
Reads judge_results.json of each reports dir.  Output markdown on stdout.  Reads only."""
import json, os, sys
PT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RCS, LIBS = ["nom", "min", "max"], ["tt", "ss", "ff"]
sets = []
for a in sys.argv[1:]:
    lab, rest = a.split("=", 1)
    b, i, arm = rest.split(":")
    L = lambda d: json.load(open(os.path.join(PT, "reports", d, "judge_results.json")))
    sets.append((lab, arm, L(b), L(i)))
def cell(r, k):
    if r is None: return "n/a"
    return f"{r[k+'_wns']:+.3f} / {r[k+'_tns']:.1f} / {r[k+'_viol']}"
for sdc, idx in (("base SDC (sky130_cpu.sdc, md5 3c69635042a9d65cb87e71a9db713e4e)", 2), ("iolat SDC (comparison-only, md5 e90bdba8b93f8f4e985c5fbaa6d4ab90)", 3)):
    for kind in ("setup", "hold"):
        print(f"\n#### {kind.upper()} WNS / TNS / violators (ns), {sdc}\n")
        print("| corner | " + " | ".join(l for l, *_ in sets) + " |")
        print("|---|" + "---:|" * len(sets))
        for rc in RCS:
            for lib in LIBS:
                row = []
                for lab, arm, *d in sets:
                    row.append(cell(d[idx-2].get(f"{arm}_{rc}_{lib}"), kind))
                print(f"| {rc}_{lib} | " + " | ".join(row) + " |")
print("\n#### Power, PrimePower nom_tt (mW), variant B (headline) / variant A, base SDC\n")
print("| set | B total | B internal | B switching | B clock_nw | B comb | B memory | A total |")
print("|---|---:|---:|---:|---:|---:|---:|---:|")
for lab, arm, b, i in sets:
    r = b.get(f"{arm}_nom_tt")
    if not r or "power_B" not in r: print(f"| {lab} | n/a |||||||"); continue
    B, A = r["power_B"], r["power_A"]; g = B["groups"]
    print(f"| {lab} | {B['total']*1e3:.2f} | {B['internal']*1e3:.2f} | {B['switching']*1e3:.2f} | {g['clock_network'][3]*1e3:.1f} | {g['combinational'][3]*1e3:.1f} | {g['memory'][3]*1e3:.1f} | {A['total']*1e3:.2f} |")
print("\n#### Annotation gate and DRV (violating pins), base SDC\n")
print("| set | gate PASS corners | max_tran nom_tt / max_ss | max_cap nom_tt / max_ss |")
print("|---|---:|---|---|")
for lab, arm, b, i in sets:
    rs = [b.get(f"{arm}_{rc}_{lib}") for rc in RCS for lib in LIBS]
    n = sum(1 for r in rs if r and r["gate"] == "PASS")
    t, s = b.get(f"{arm}_nom_tt"), b.get(f"{arm}_max_ss")
    print(f"| {lab} | {n}/9 | {t['drv']['max_transition']} / {s['drv']['max_transition']} | {t['drv']['max_capacitance']} / {s['drv']['max_capacitance']} |")
