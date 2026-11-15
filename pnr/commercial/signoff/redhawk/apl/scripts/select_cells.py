#!/usr/bin/env python3
"""select_cells.py -- pick the APL cell set (user decision 2026-11-08, option "Partial + justify rest"): the DECAP cells present in the final-arm DEFs plus the TOP-12
functional std cells by instance count, pooled over the three final arms (ICC2 b9, Innovus b11, OpenROAD B2).  Input: reports/cell_counts_<arm>.txt (`<cell> <count>`
from the DEF COMPONENTS section of each final DEF).  Functional = not fill/tap/decap/diode/conb.  Writes reports/cell_selection.tsv, cell_list, decap_list (stdout summary)."""
import collections, os, re, sys
here = os.path.dirname(os.path.abspath(__file__)); rep = os.path.join(here, "..", "reports")
arms = ["icc2b9", "innovusb11", "openroad"]
C = {}
for a in arms:
    C[a] = {l.split()[0]: int(l.split()[1]) for l in open(os.path.join(rep, "cell_counts_%s.txt" % a))}
nonfun = re.compile(r"(fill|tap|decap|diode|endcap|conb)")
fun = lambda c: not nonfun.search(c)
tot = collections.Counter()
for a in arms:
    for c, n in C[a].items():
        if fun(c): tot[c] += n
top = [c for c, _ in tot.most_common(12)]
decap = sorted({c for a in arms for c in C[a] if "decap" in c})
S = sum(tot.values())
out = ["cell\tclass\ticc2b9\tinnovusb11\topenroad\tpooled\tpooled_share_pct"]
for c in top: out.append("%s\tstd\t%s\t%d" % (c, "\t".join(str(C[a].get(c, 0)) for a in arms), tot[c]) + "\t%.2f" % (100.0 * tot[c] / S))
for c in decap: out.append("%s\tdecap\t%s\t%d\t-" % (c, "\t".join(str(C[a].get(c, 0)) for a in arms), sum(C[a].get(c, 0) for a in arms)))
open(os.path.join(rep, "cell_selection.tsv"), "w").write("\n".join(out) + "\n")
open(os.path.join(rep, "cell_list"), "w").write("\n".join(top) + "\n")
open(os.path.join(rep, "decap_list"), "w").write("\n".join(decap) + "\n")
print("functional instances pooled: %d; top-12 cover %d (%.1f %%)" % (S, sum(tot[c] for c in top), 100.0 * sum(tot[c] for c in top) / S))
for a in arms:
    fa = sum(n for c, n in C[a].items() if fun(c)); ca = sum(C[a].get(c, 0) for c in top)
    print("  %-10s functional %6d  top-12 covered %6d (%.1f %%)" % (a, fa, ca, 100.0 * ca / fa))
print("decap cells:", decap)
