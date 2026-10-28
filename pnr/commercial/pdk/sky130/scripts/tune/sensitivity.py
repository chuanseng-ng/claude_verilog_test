#!/usr/bin/env python3
"""sensitivity.py -- cap2d sensitivity of routing-pitch patterns to the allowed ITF knobs (nom stack).  Output: % change of
Ctot for T_<layer>_1_1 (dense, adjacent tracks both sides) and T_<layer>_N_N (isolated), layers met1..met4."""
import copy, sys
import cap2d, patterns2d as p2
ITF = sys.argv[1] if len(sys.argv) > 1 else "../../build/tech/itf/sky130A_nom.untuned.itf"
slabs, conds = cap2d.parse_itf(ITF)
def evaluate(slabs_, conds_, dw=0.0, liner=None):
    st = cap2d.Stack(slabs_, conds_)
    out = {}
    W0 = dict(p2.W)
    for lay in ("met1", "met2", "met3", "met4"):
        w, s = W0[lay]
        p2.W[lay] = (w + dw, s)             # etch: drawn width grows by dw (spacing shrinks via fixed pitch in run_T)
        for ab in ((1, 1), ("N", "N")):
            out[(lay, ab)] = p2.run_T(st, conds_, lay, ab[0], ab[1], 0.02, liner)[3]
        p2.W[lay] = W0[lay]
    return out
base = evaluate(slabs, conds)
def show(name, res):
    print("%-44s" % name + " ".join("%s %s %+5.1f%%" % (l[3:], "dense" if ab[0] == 1 else "iso  ", 100 * (res[(l, ab)] / base[(l, ab)] - 1)) for (l, ab) in base))
print("%-44s" % "baseline Ctot aF/um" + " ".join("%s %s %5.1f " % (l[3:], "dense" if ab[0] == 1 else "iso  ", base[(l, ab)]) for (l, ab) in base))
def scaled(f, which=None):
    return [[a, b, (e * f if (which is None or n in which) else e), n] for a, b, e, n in slabs]
show("all dielectric ER x1.05", evaluate(scaled(1.05), conds))
show("ER of met-level slabs (ILD1..4) x1.10 (lateral)", evaluate(scaled(1.10, {"ILD1", "ILD2", "ILD3", "ILD4"}), conds))
show("ER of ILDLI/ILDPOLY/FOX (below) x1.10", evaluate(scaled(1.10, {"ILDLI", "ILDPOLY", "FOX"}), conds))
c2 = {k: (v[0], v[1] * 1.05, v[2], v[3]) for k, v in conds.items()}
show("metal thickness x1.05", evaluate(slabs, c2))
c3 = {k: (v[0], v[1] * 0.97, v[2], v[3]) for k, v in conds.items()}
show("metal thickness x0.97 (tech-LEF 0.35 vs fig 0.36)", evaluate(slabs, c3))
show("etch bias: wires +10 nm wider (+5 nm/side)", evaluate(slabs, conds, dw=0.010))
show("etch bias: wires +20 nm wider", evaluate(slabs, conds, dw=0.020))
show("conformal liner K=7.3, 25 nm side/top", evaluate(slabs, conds, liner=(7.3, 0.025, 0.025)))
