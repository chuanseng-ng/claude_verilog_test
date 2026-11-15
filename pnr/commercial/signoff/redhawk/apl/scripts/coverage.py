#!/usr/bin/env python3
"""coverage.py -- share of the standard-cell instances and of the PrimePower power (instance_power.txt, variant B) that sit in the 12 APL-characterised cells, per arm.
Writes apl/reports/apl_coverage.tsv.  Cells outside the set keep the RedHawk defaults derived from the Liberty."""
import os
here = os.path.dirname(os.path.abspath(__file__)); apl = os.path.join(here, ".."); rh = os.path.join(apl, "..")
cells = set(open(os.path.join(apl, "reports/cell_list")).read().split())
rows = ["arm\tleaf_cells\tin_set_cells\tinstance_share_pct\ttotal_mW\tin_set_mW\tpower_share_pct"]
for a in ("icc2b9", "icc2b12", "innovusb11", "openroad"):
    p = os.path.join(rh, "runs", a, "pt/instance_power.txt")
    if not os.path.exists(p): continue
    n = k = 0; t = s = 0.0
    for line in open(p):
        f = line.split()
        if len(f) < 3 or any(x in f[2] for x in ("fill", "tap", "decap", "diode", "sram")): continue
        n += 1; t += float(f[1])
        if f[2] in cells: k += 1; s += float(f[1])
    rows.append("%s\t%d\t%d\t%.1f\t%.3f\t%.3f\t%.1f" % (a, n, k, 100.0 * k / n, t * 1e3, s * 1e3, 100.0 * s / t))
open(os.path.join(apl, "reports/apl_coverage.tsv"), "w").write("\n".join(rows) + "\n"); print("\n".join(rows))
