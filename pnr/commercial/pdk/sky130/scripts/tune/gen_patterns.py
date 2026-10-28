#!/usr/bin/env python3
"""gen_patterns.py <out.def> -- synthetic routed DEF of canonical interconnect patterns for tuning the Sky130 ITF.

Used with BOTH OpenRCX (reference) and StarRC (candidate) on the same file.  No cells; every net has one
bterm at each end on the wire's own layer.  Patterns are 100 um straight wires, >= 40 um apart:
  S_<layer>_<k>   7 parallel wires on <layer>, spacing = k x min spacing  (k = 1, 2, 4, 16)
  T_<layer>_<a>_<b> probe with neighbours a / b routing tracks away (N = none), real routing pitch
  V_<upper>_<lower> 3 aligned wires on <upper> over 3 on <lower>, both at min pitch (parallel stack)
Net names encode the pattern; the middle wire (index 3 of S, index 1 of V) is the probe.
"""
import sys
W = {"li1": (0.17, 0.17), "met1": (0.14, 0.14), "met2": (0.14, 0.14), "met3": (0.30, 0.30), "met4": (0.30, 0.30), "met5": (1.6, 1.6)}
ORDER = ["li1", "met1", "met2", "met3", "met4", "met5"]
L = 100.0
def build():
    nets = []   # (name, layer, x0, x1, y)
    y = 100.0
    for lay in ORDER:
        w, s = W[lay]
        for k in (1, 2, 4, 16):
            pitch = w + k * s
            for i in range(7):
                nets.append((f"S_{lay}_{k}_{i}", lay, 100.0, 100.0 + L, y + i * pitch))
            y += 7 * pitch + 60.0
    pairs = [("met1", "li1"), ("met2", "met1"), ("met3", "met2"), ("met4", "met3"), ("met5", "met4"), ("met2", "li1"), ("met3", "met1"), ("met4", "met2"), ("met5", "met3")]
    for up, lo in pairs:
        w, s = W[up]; w2, s2 = W[lo]; pitch = max(w + s, w2 + s2)
        for i in range(3):
            nets.append((f"V_{up}_{lo}_u{i}", up, 100.0, 100.0 + L, y + i * pitch))
            nets.append((f"V_{up}_{lo}_l{i}", lo, 100.0, 100.0 + L, y + i * pitch))
        y += 3 * pitch + 60.0
    # routing-pitch patterns (what the router really produces): probe with neighbours a, b tracks away (N = none)
    RP = {"li1": 0.46, "met1": 0.34, "met2": 0.46, "met3": 0.68, "met4": 0.92, "met5": 3.4}
    for lay in ("met1", "met2", "met3", "met4", "li1", "met5"):
        for a, b in ((1, 1), (1, 2), (1, "N"), (2, 2), (2, "N"), ("N", "N")):
            nets.append((f"T_{lay}_{a}_{b}_p", lay, 100.0, 100.0 + L, y))
            if a != "N": nets.append((f"T_{lay}_{a}_{b}_l", lay, 100.0, 100.0 + L, y - a * RP[lay]))
            if b != "N": nets.append((f"T_{lay}_{a}_{b}_r", lay, 100.0, 100.0 + L, y + b * RP[lay]))
            y += 60.0 + 2 * max(a if a != "N" else 0, b if b != "N" else 0) * RP[lay]
    return nets, y + 100.0
def write(path):
    nets, ymax = build()
    d = lambda v: int(round(v * 1000))
    o = ["VERSION 5.8 ;", 'DIVIDERCHAR "/" ;', 'BUSBITCHARS "[]" ;', "DESIGN pat ;", "UNITS DISTANCE MICRONS 1000 ;",
         f"DIEAREA ( 0 0 ) ( {d(400)} {d(ymax)} ) ;", ""]
    o.append(f"PINS {2*len(nets)} ;")
    for (n, lay, x0, x1, y) in nets:
        w = W[lay][0]
        for tag, x in (("a", x0), ("b", x1)):
            o.append(f" - {n}_{tag} + NET {n} + DIRECTION INOUT + USE SIGNAL + LAYER {lay} ( {-d(w/2)} {-d(w/2)} ) ( {d(w/2)} {d(w/2)} ) + FIXED ( {d(x)} {d(y)} ) N ;")
    o.append("END PINS"); o.append("")
    o.append(f"NETS {len(nets)} ;")
    for (n, lay, x0, x1, y) in nets:
        o.append(f" - {n} ( PIN {n}_a ) ( PIN {n}_b )")
        o.append(f"   + ROUTED {lay} ( {d(x0)} {d(y)} ) ( {d(x1)} * ) ;")
    o.append("END NETS"); o.append("END DESIGN")
    open(path, "w").write("\n".join(o) + "\n")
if __name__ == "__main__":
    write(sys.argv[1]); print("wrote", sys.argv[1], len(build()[0]), "nets")
