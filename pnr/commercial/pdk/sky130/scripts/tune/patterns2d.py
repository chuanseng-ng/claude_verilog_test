#!/usr/bin/env python3
"""patterns2d.py <itf> [hmin] -- evaluate the gen_patterns.py patterns with cap2d on an ITF (aF/um); same columns as pattern_table.py"""
import sys, time
import cap2d
W = {"li1": (0.17, 0.17), "met1": (0.14, 0.14), "met2": (0.14, 0.14), "met3": (0.30, 0.30), "met4": (0.30, 0.30), "met5": (1.6, 1.6)}
LAY = ["li1", "met1", "met2", "met3", "met4", "met5"]
PAIRS = [("met1", "li1"), ("met2", "met1"), ("met3", "met2"), ("met4", "met3"), ("met5", "met4"), ("met2", "li1"), ("met3", "met1"), ("met4", "met2"), ("met5", "met3")]

def run_S(stack, conds, lay, k, hmin, liner=None):
    w, s = W[lay]; pitch = w + k * s; zb, t = conds[lay][0], conds[lay][1]
    rects = [("w%d" % i, i * pitch, i * pitch + w, zb, zb + t) for i in range(7)]
    Q, it = cap2d.solve(stack, rects, "w3", hmin=hmin, liner=liner)
    tot = Q["w3"]; ccn = -(Q["w2"] + Q["w4"]); cco = -sum(v for n, v in Q.items() if n not in ("w2", "w3", "w4"))
    return (tot - ccn - cco, ccn, cco, tot)

RP = {"li1": 0.46, "met1": 0.34, "met2": 0.46, "met3": 0.68, "met4": 0.92, "met5": 3.4}
def run_T(stack, conds, lay, a, b, hmin, liner=None):
    w = W[lay][0]; zb, t = conds[lay][0], conds[lay][1]; rects = [("p", 0.0, w, zb, zb + t)]
    if a != "N": rects.append(("l", -a * RP[lay], -a * RP[lay] + w, zb, zb + t))
    if b != "N": rects.append(("r", b * RP[lay], b * RP[lay] + w, zb, zb + t))
    Q, it = cap2d.solve(stack, rects, "p", hmin=hmin, liner=liner, xmargin=3.0)
    tot = Q["p"]; ccn = -(Q.get("l", 0.0) + Q.get("r", 0.0))
    return (tot - ccn, ccn, 0.0, tot)

def run_V(stack, conds, up, lo, hmin, liner=None):
    w, s = W[up]; w2, s2 = W[lo]; pitch = max(w + s, w2 + s2)
    rects = []
    for i in range(3):
        rects.append(("u%d" % i, i * pitch, i * pitch + w, conds[up][0], conds[up][0] + conds[up][1]))
        rects.append(("l%d" % i, i * pitch, i * pitch + w2, conds[lo][0], conds[lo][0] + conds[lo][1]))
    Q, it = cap2d.solve(stack, rects, "u1", hmin=hmin, liner=liner)
    tot = Q["u1"]; ccn = -(Q["u0"] + Q["u2"]); cv = -Q["l1"]; cco = -(Q["l0"] + Q["l2"])
    return (tot - ccn - cco - cv, ccn, cco, tot, cv)

def table(itf, hmin=0.02, which=None, liner=None):
    slabs, conds = cap2d.parse_itf(itf)
    stack = cap2d.Stack(slabs, conds)
    out = {}
    for lay in LAY:
        for k in (1, 2, 4, 16):
            key = "S_%s_%d" % (lay, k)
            if which and key not in which: continue
            out[key] = run_S(stack, conds, lay, k, hmin, liner)
    for lay in ("met1", "met2", "met3", "met4", "li1", "met5"):
        for a, b in ((1, 1), (1, 2), (1, "N"), (2, 2), (2, "N"), ("N", "N")):
            key = "T_%s_%s_%s" % (lay, a, b)
            if which and key not in which: continue
            out[key] = run_T(stack, conds, lay, a, b, hmin, liner)
    for up, lo in PAIRS:
        key = "V_%s_%s" % (up, lo)
        if which and key not in which: continue
        out[key] = run_V(stack, conds, up, lo, hmin, liner)
    return out
if __name__ == "__main__":
    t0 = time.time()
    hmin = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
    sel = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    for k, v in table(sys.argv[1], hmin, sel).items():
        print("%-14s" % k, " ".join("%7.1f" % x for x in v), flush=True)
    print("time %.1fs" % (time.time() - t0))
