#!/usr/bin/env python3
"""summarize.py <arm> <drclvs dir>: condensed one-page facts from the run products (no big file is loaded)."""
import sys, os, re, json
arm, here = sys.argv[1], sys.argv[2]
run = f"{here}/runs/{arm}"; rep = f"{here}/reports"
def tail(p, n=40):
    try:
        with open(p, errors="replace") as f: return f.readlines()[-n:]
    except OSError: return None
print(f"== drclvs summary: arm={arm}")
for tag, d in (("LVS (Magic DEF+LEF, LibreLane mode)", "lvs"), ("LVS (Magic from GDS, cells as LEF abstracts)", "lvsgds")):
    p = f"{run}/{d}/netgen/reports/lvs.netgen.rpt"
    t = tail(p, 400)
    print(f"-- {tag}")
    if t is None: print("   NOT RUN / no report"); continue
    txt = "".join(t)
    fin = [l.strip() for l in t if l.startswith("Final result") or "do not match" in l or "Circuits match" in l or "equivalent" in l and "Cell pin lists" in l]
    print("   " + " | ".join(dict.fromkeys(fin)) if fin else "   (no verdict line)")
    js = f"{run}/{d}/netgen/reports/lvs.netgen.json"
    for l in open(p, errors="replace"):
        if re.match(r"^\s*Number of (devices|nets):", l) or "Circuit 1 contains" in l or "Circuit 2 contains" in l: print("   " + l.rstrip())
for f, lab in (("kdrc/../../../reports/%s_klayout_drc_by_rule.txt" % arm, "KLayout DRC"), ):
    pass
for p, lab in ((f"{rep}/{arm}_klayout_drc_by_rule.txt", "KLayout DRC"), (f"{rep}/{arm}_magic_drc_by_rule.tsv", "Magic DRC by rule (inside/straddle/outside SRAM)"), (f"{rep}/{arm}_antenna.rpt", "Antenna (OpenROAD check_antennas)")):
    print(f"-- {lab}")
    t = tail(p, 400) if os.path.exists(p) else None
    if t is None: print("   NOT RUN / no report"); continue
    for l in (t[:25] if "klayout" in p or "magic" in p else [x for x in t if re.search(r"violat|ANT|Found|nets|pins", x)][-8:]): print("   " + l.rstrip())
