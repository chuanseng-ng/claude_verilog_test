#!/usr/bin/env python3
"""pinfit.py <ref.tsv> <test.tsv> <openrcx.spef> -- least squares  C_test = a*C_ref + b*n_pins + c   (nets with C_ref < 50 fF)"""
import sys, numpy as np
def pins(path):
    nm = {}; out = {}; cur = None; sec = None; sub = None
    for l in open(path, errors="replace"):
        if l.startswith("*NAME_MAP"): sec = "map"; continue
        if sec == "map":
            if l[0] == "*" and l[1].isdigit():
                p = l.split(None, 1); nm[p[0]] = p[1].strip().replace("\\", ""); continue
            sec = None
        if l.startswith("*D_NET"):
            p = l.split(); cur = nm.get(p[1], p[1]); out[cur] = 0; sub = None; continue
        if cur is None: continue
        if l.startswith("*CONN"): sub = "c"; continue
        if l.startswith("*CAP") or l.startswith("*RES"): sub = None; continue
        if l.startswith("*END"): cur = None; continue
        if sub == "c" and (l.startswith("*I") or l.startswith("*P")): out[cur] += 1
    return out
def load(p):
    d = {}
    for l in list(open(p))[1:]:
        t = l.rstrip().split("\t"); d[t[0]] = [float(x) for x in t[1:]]
    return d
r = load(sys.argv[1]); s = load(sys.argv[2]); pn = pins(sys.argv[3])
ks = [k for k in r if k in s and k in pn and r[k][0] < 50]
C0 = np.array([r[k][0] for k in ks]); C1 = np.array([s[k][0] for k in ks]); P = np.array([pn[k] for k in ks])
G0 = np.array([r[k][1] for k in ks]); G1 = np.array([s[k][1] for k in ks]); X0 = np.array([r[k][2] for k in ks]); X1 = np.array([s[k][2] for k in ks])
for name, a, b in (("total", C0, C1), ("ground", G0, G1), ("coupling", X0, X1)):
    A = np.vstack([a, P, np.ones(len(ks))]).T
    co = np.linalg.lstsq(A, b, rcond=None)[0]
    print("%-8s C_test = %.4f * C_ref + %.4f fF/pin %+.4f" % (name, *co))
