#!/usr/bin/env python3
"""validate.py <itf> <starrc pat spef> [hmin] -- cap2d vs StarRC per pattern (ratio of Ctot, coupling-to-nearest, Cg)"""
import sys
import pattern_table as pt, patterns2d as p2
itf, spef = sys.argv[1], sys.argv[2]
hmin = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02
sr = pt.table(spef); me = p2.table(itf, hmin)
print("%-14s | %-30s | %-30s | ratio" % ("pattern", "StarRC Cg/Ccn/Cco/Ctot", "cap2d Cg/Ccn/Cco/Ctot"))
for k in sr:
    a, b = sr[k], me[k]
    print("%-14s | %6.1f %6.1f %6.1f %6.1f | %6.1f %6.1f %6.1f %6.1f | tot %.3f  cc(n+o) %.3f" % (k, *a[:4], *b[:4], b[3] / a[3], (b[1] + b[2]) / max(1e-9, a[1] + a[2])))
