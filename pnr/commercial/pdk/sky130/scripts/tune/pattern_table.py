#!/usr/bin/env python3
"""pattern_table.py <spef> [<spef2> ...]  -- per-pattern capacitance of the probe wires of gen_patterns.py, aF/um.

Probe: S_<layer>_<k>_3 (middle of 7) and V_<up>_<lo>_u1 / _l1 (middle of 3 aligned pairs).
Columns: Cg = capacitance to ground (everything that is not a coupling element), Ccn = coupling to the two nearest
same-layer neighbours (sum), Cco = coupling to all other nets (same-layer far neighbours, other layer), Ctot.
For V patterns also Cv = coupling to the aligned wire on the other layer.
"""
import sys, re, collections
L = 100.0
def parse(path):
    nm = {}; cu = 1.0; nets = {}
    cur = None; sub = None
    for line in open(path, errors="replace"):
        if line.startswith("*C_UNIT"):
            p = line.split(); cu = float(p[1]) * {"FF": 1, "PF": 1e3}[p[2]]
        if line.startswith("*") and len(line) > 1 and line[1].isdigit() and cur is None and not line.startswith("*D_NET"):
            p = line.split(None, 1)
            if len(p) == 2 and p[1].strip() and not p[1].startswith("I "):
                nm[p[0]] = p[1].strip()
            continue
        if line.startswith("*D_NET"):
            p = line.split(); cur = nm.get(p[1], p[1]); nets[cur] = {"tot": float(p[2]) * cu, "cc": collections.defaultdict(float), "g": 0.0}; sub = None; continue
        if cur is None: continue
        if line.startswith("*CAP"): sub = "cap"; continue
        if line.startswith("*RES") or line.startswith("*CONN"): sub = None; continue
        if line.startswith("*END"): cur = None; continue
        if sub == "cap":
            p = line.split()
            if len(p) == 3: nets[cur]["g"] += float(p[2]) * cu
            elif len(p) == 4:
                other = p[2] if not p[2].startswith("*" + str(0)) else p[2]
                key = p[2].split(":")[0]
                key = nm.get(key, key)
                if re.search(r"_[ab]$", key): key = key[:-2]
                nets[cur]["cc"][key] += float(p[3]) * cu
    # make coupling symmetric (OpenRCX lists a pair once, StarRC in both nets) and define ground as total - coupling
    pair = {}
    for a, d in nets.items():
        for b, v in d["cc"].items():
            pair[frozenset((a, b))] = v
    for a, d in nets.items():
        d["cc"] = collections.defaultdict(float)
    for k, v in pair.items():
        if len(k) < 2: continue
        a, b = tuple(k)
        if a in nets: nets[a]["cc"][b] = v
        if b in nets: nets[b]["cc"][a] = v
    for a, d in nets.items():
        d["g"] = d["tot"] - sum(d["cc"].values())
    return nets
def row(nets, probe, nb):
    n = nets.get(probe)
    if not n: return None
    cc = n["cc"]; ccn = sum(cc.get(x, 0.0) for x in nb); cco = sum(cc.values()) - ccn
    return n["g"] / L * 1e3, ccn / L * 1e3, cco / L * 1e3, n["tot"] / L * 1e3
LAY = ["li1", "met1", "met2", "met3", "met4", "met5"]
def table(path):
    nets = parse(path); out = {}
    for lay in LAY:
        for k in (1, 2, 4, 16):
            out[f"S_{lay}_{k}"] = row(nets, f"S_{lay}_{k}_3", [f"S_{lay}_{k}_2", f"S_{lay}_{k}_4"])
    for lay in ("met1", "met2", "met3", "met4", "li1", "met5"):
        for a, b in ((1, 1), (1, 2), (1, "N"), (2, 2), (2, "N"), ("N", "N")):
            key = f"T_{lay}_{a}_{b}"
            out[key] = row(nets, key + "_p", [key + "_l", key + "_r"])
    for up, lo in [("met1", "li1"), ("met2", "met1"), ("met3", "met2"), ("met4", "met3"), ("met5", "met4"), ("met2", "li1"), ("met3", "met1"), ("met4", "met2"), ("met5", "met3")]:
        n = nets.get(f"V_{up}_{lo}_u1")
        if not n: continue
        cv = n["cc"].get(f"V_{up}_{lo}_l1", 0.0) / L * 1e3
        g, ccn, cco, tot = row(nets, f"V_{up}_{lo}_u1", [f"V_{up}_{lo}_u0", f"V_{up}_{lo}_u2"])
        out[f"V_{up}_{lo}"] = (g, ccn, cco - cv, tot, cv)
    return out
if __name__ == "__main__":
    tabs = [table(p) for p in sys.argv[1:]]
    print("%-14s" % "pattern" + "".join(" | %-8s %-7s %-7s %-7s %-7s" % ("Cg", "Ccn", "Cco", "Ctot", "Cv") for _ in tabs))
    for key in tabs[0]:
        s = "%-14s" % key
        for t in tabs:
            r = t.get(key)
            s += " | " + (" ".join("%7.1f" % x for x in r) if r else "   -")
        print(s)
