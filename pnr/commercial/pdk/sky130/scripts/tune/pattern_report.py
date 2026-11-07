#!/usr/bin/env python3
"""pattern_report.py <out.md> -- OpenRCX vs StarRC vs cap2d on the gen_patterns.py routing-pitch patterns (nom stack)."""
import sys
import pattern_table as pt, patterns2d as p2
B = "../../build"
orr = pt.table(B + "/tune/pat_rcx_nom.spef"); sr = pt.table(B + "/tune/sr_untuned_nom_T/pat.nom.spef")
keys = [k for k in orr if k.startswith("T_")]
me = p2.table(B + "/tech/itf/sky130A_nom.untuned.itf", 0.02, keys)
o = ["# Pattern check, nominal stack (aF/um, middle wire of a 100 um pattern)", "",
     "Reference OpenRCX = `rules.openrcx.sky130A.nom.calibre` (the deck the OpenROAD flow uses). StarRC = authored nominal nxtgrd (unchanged by the tuning).",
     "cap2d = the numpy 2-D surrogate (`scripts/tune/cap2d.py`) on the same ITF.  T_<layer>_<a>_<b>: probe with neighbours a / b routing tracks away (N = none), real routing pitch.",
     "Ctot = total, Ccn = coupling to the two nearest same-layer neighbours.", "",
     "| pattern | OpenRCX Ctot | OpenRCX Ccn | StarRC Ctot | StarRC Ccn | cap2d Ctot | cap2d Ccn | StarRC/OpenRCX Ctot |", "|---|---|---|---|---|---|---|---|"]
for k in keys:
    a, b, c = orr[k], sr[k], me[k]
    o.append("| %s | %.1f | %.1f | %.1f | %.1f | %.1f | %.1f | %.3f |" % (k, a[3], a[1], b[3], b[1] + b[2], c[3], c[1], b[3] / a[3]))
open(sys.argv[1], "w").write("\n".join(o) + "\n")
print("wrote", sys.argv[1])
