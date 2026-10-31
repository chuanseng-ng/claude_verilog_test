#!/usr/bin/env python3 -I
"""mk_ict_li1m1.py <corner> -- derive the Innovus capTable ICT from the tuned authored ICT (pdk/sky130/build/tech/ict/sky130A_<corner>.ict).

Why: generateCapTbl treats the conductor named `li1` as the local-interconnect/POLY-class layer (warning IMPEXT-6091) and emits only met1..met5 as
M1..M5, but the Sky130 tech LEF has SIX routing layers (li1 met1..met5), so Innovus rejects the table (IMPEXT-3548 "layer M6 missing").
Renaming the conductor li1 -> met0 (and the via references) makes it an ordinary interconnect layer: the table then has M1=li1 ... M6=met5, in LEF order.
Geometry, heights, K, resistivities are untouched: the same tuned stack ("calibrated to OpenRCX, not silicon") StarRC uses via the ITF.
"""
import re, sys, os
c = sys.argv[1]
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../pdk/sky130/build/tech/ict/sky130A_%s.ict" % c)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../captbl6/sky130A_%s_li1m1.ict" % c)
t = open(src).read()
t2 = t.replace('conductor "li1"', 'conductor "met0"')
t2 = re.sub(r'(top_layer|bottom_layer) li1\b', r'\1 met0', t2)
assert t2 != t
open(out, "w").write("# DERIVED by scripts/mk_ict_li1m1.py from %s: conductor li1 renamed met0 (Innovus capTable layer order M1=li1..M6=met5)\n" % os.path.basename(src) + t2)
print(out)
