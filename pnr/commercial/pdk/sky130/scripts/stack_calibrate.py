#!/usr/bin/env python3 -I
"""stack_calibrate.py -- sanity-fit the dielectric K assignment of the authored Sky130 ITF/ICT
against the PEX-cap-model-derived area capacitances shipped in Magic's sky130A.tech
(`defaultareacap`/`defaultoverlap`, aF/um^2, "taken from the document PEX/xRC/cap_models").

Model: 1-D parallel-plate series stack.  z geometry (bottoms/thicknesses) from the SkyWater
metal-stack figure (skywater-pdk docs/_images/metal_stack.svg) == Magic `height` lines.
K candidates are ONLY values printed in that figure.  Prints the residual of the chosen set
and (with --search) the best assignment found by coordinate-descent search.  Not a field solver:
fringing is ignored, so residuals of a few % are expected.  Indicative only.
"""
import itertools, sys
E0 = 8.8541878128e-12  # F/m
# (name, bottom z, thickness)  um   -- Magic 'height' == figure labels
Z = {"poly": (0.3262, 0.18), "li1": (0.9361, 0.10), "met1": (1.3761, 0.36), "met2": (2.0061, 0.36),
     "met3": (2.7861, 0.845), "met4": (4.0211, 0.845), "met5": (5.3711, 1.26)}
KSET = [3.5, 3.9, 4.0, 4.05, 4.1, 4.2, 4.5]
LINT_T, LINT_K = 0.075, 7.3            # nitride on li1 top (figure: LINT K=7.3, 0.075 um)
# Magic nominal caps (aF/um^2): to substrate, and layer-over-layer overlaps
SUB = {"li1": 36.99, "met1": 25.78, "met2": 17.5, "met3": 12.37, "met4": 8.42, "met5": 6.32}
OVL = {("met1", "li1"): 114.20, ("met2", "met1"): 133.86, ("met3", "met2"): 86.19, ("met4", "met3"): 84.03,
       ("met5", "met4"): 68.33, ("met2", "li1"): 37.56, ("met3", "li1"): 20.79, ("met3", "met1"): 34.54,
       ("met4", "met2"): 20.33, ("met5", "met3"): 19.63}
# slabs bottom-up: (name, z0, z1, key).  K chosen per key.
def slabs():
    z = Z
    s = [("FOX", 0.0, z["poly"][0], "FOX"), ("PSG", z["poly"][0], z["li1"][0], "PSG"),
         ("LIfill", z["li1"][0], z["li1"][0] + 0.10, "PSG"),
         ("LINT", z["li1"][0] + 0.10, z["li1"][0] + 0.10 + LINT_T, "LINT"),
         ("MCON", z["li1"][0] + 0.10 + LINT_T, z["met1"][0], "NILD_mcon")]
    prev = "met1"
    for lo, hi in (("met1", "met2"), ("met2", "met3"), ("met3", "met4"), ("met4", "met5")):
        s.append((lo + "_lvl", z[lo][0], z[lo][0] + z[lo][1], lo + "_lvl"))
        s.append((lo + "_via", z[lo][0] + z[lo][1], z[hi][0], lo + "_via"))
    s.append(("met5_lvl", z["met5"][0], z["met5"][0] + z["met5"][1], "met5_lvl"))
    return s
KEYS = ["FOX", "PSG", "NILD_mcon", "met1_lvl", "met1_via", "met2_lvl", "met2_via", "met3_lvl", "met3_via",
        "met4_lvl", "met4_via", "met5_lvl"]
def cap(zlo, zhi, K):
    """series plate cap aF/um^2 between zlo and zhi using slab K map"""
    acc = 0.0
    for (_, a, b, key) in slabs():
        lo, hi = max(a, zlo), min(b, zhi)
        if hi > lo:
            k = LINT_K if key == "LINT" else K[key] if key in K else 3.9
            acc += (hi - lo) / k
    return E0 / (acc * 1e-6) * 1e18 / 1e12 if acc > 0 else float("nan")   # F/m^2 -> aF/um^2
def resid(K, verbose=False):
    err = []
    for l, c in SUB.items():
        m = cap(0.0, Z[l][0], K); err.append((m - c) / c)
        if verbose: print(f"  {l:5s}->sub  model {m:7.2f}  Magic {c:7.2f}  {100*(m-c)/c:+5.1f}%")
    for (u, l), c in OVL.items():
        m = cap(Z[l][0] + Z[l][1], Z[u][0], K); err.append((m - c) / c)
        if verbose: print(f"  {u:5s}->{l:5s} model {m:7.2f}  Magic {c:7.2f}  {100*(m-c)/c:+5.1f}%")
    return (sum(e * e for e in err) / len(err)) ** 0.5
def parse(argv):
    K = {k: 3.9 for k in KEYS}
    # the set actually used by gen_stack.py (result of --search)
    K.update({"met1_via": 4.1, "met2_via": 4.1, "met3_via": 3.5, "met4_via": 3.9, "met4_lvl": 4.0})
    for a in argv:
        if "=" in a:
            k, v = a.split("="); K[k] = float(v)
    return K
if __name__ == "__main__":
    K = parse(sys.argv[1:])
    if "--search" in sys.argv:
        free = ["NILD_mcon", "met1_via", "met2_via", "met3_via", "met4_via", "met1_lvl", "met2_lvl", "met3_lvl", "met4_lvl", "met5_lvl"]
        best = (resid(K), dict(K))          # coordinate descent over the published-K set (exhaustive is 7^10)
        improved = True
        while improved:
            improved = False
            for f in free:
                for kv in KSET:
                    K2 = dict(best[1]); K2[f] = kv; r = resid(K2)
                    if r < best[0] - 1e-9: best = (r, K2); improved = True
        K = best[1]; print("BEST", {k: K[k] for k in free})
    print("K =", {k: K[k] for k in KEYS}); print(f"RMS residual vs Magic PEX-model area caps: {100*resid(K, True):.2f}%")
