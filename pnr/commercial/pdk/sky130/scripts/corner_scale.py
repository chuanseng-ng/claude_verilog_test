#!/usr/bin/env python3 -I
"""corner_scale.py -- min/max capacitance corner multipliers for the Sky130 ITF/ICT.

No ITF/ICT/nxtgrd ships with Sky130, and the tech-LEF corners (nom/min/max.tlef) vary RESISTANCE only.
Capacitance corners therefore come from the OpenRCX rule decks that ship in the PDK
(libs.tech/openlane/rules.openrcx.sky130A.{nom,min,max}.spef_extractor): in them the per-layer
ground ("OVER 0", 4th column) area capacitance scales by

    layer  li1    met1   met2   met3   met4   met5     (min/nom , max/nom)
    ...as printed below; the fringe column (3rd) is identical in all three decks.

The ITF/ICT corner is a uniform multiplier on every dielectric constant = geometric mean of the six
per-layer area-cap ratios (a plate capacitance is linear in ER).  Magic's sky130A.tech carries a
second, independent set (substrate area caps: min 0.78..0.88, max 1.23..1.39 of nom) printed for
comparison; OpenRCX is used because the OpenROAD run this PDK enablement is compared against uses it.
Prints ER_SCALE_MIN / ER_SCALE_MAX (consumed by gen_itf.py / gen_ict.py).
"""
import math, os, re, sys
d = os.path.join(os.environ.get("PDK_ROOT", os.path.expanduser("~/pdk")), "sky130A/libs.tech/openlane")
names = {1: "li1", 2: "met1", 3: "met2", 4: "met3", 5: "met4", 6: "met5"}
def load(c):
    out, cur = {}, None
    for l in open(os.path.join(d, f"rules.openrcx.sky130A.{c}.spef_extractor")):
        m = re.match(r"Metal (\d+) OVER 0\s*$", l.strip())
        if m: cur = int(m.group(1)); out[cur] = []; continue
        if l.startswith("END"): cur = None; continue
        if cur and re.match(r"^[\d.]", l): out[cur].append(float(l.split()[3]))
    return {k: sum(v) / len(v) for k, v in out.items()}
n, mn, mx = load("nom"), load("min"), load("max")
res = {}
for c, dd in (("min", mn), ("max", mx)):
    r = [dd[k] / n[k] for k in range(1, 7)]
    res[c] = math.exp(sum(math.log(x) for x in r) / 6)
    print(c, " ".join(f"{names[k]}={dd[k]/n[k]:.3f}" for k in range(1, 7)), f" geomean={res[c]:.4f}")
print("ER_SCALE_MIN=%.4f" % res["min"]); print("ER_SCALE_MAX=%.4f" % res["max"])
