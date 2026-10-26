#!/usr/bin/env python3
"""spef_stats.py <spef> <out.tsv>  -- per-net totals from a SPEF (any tool), streamed.

Columns: net, total_c_fF (D_NET header value: ground + coupling), gnd_c_fF, cc_fF (coupling, counted once
per net it touches), r_ohm (sum of all *RES elements), n_res.  Units honour *C_UNIT / *R_UNIT.
Names are de-escaped (backslashes removed) so that tools that escape [] or / compare equal.
"""
import sys, re

UNIT_C = {"FF": 1.0, "PF": 1e3, "NF": 1e6, "F": 1e15}
UNIT_R = {"OHM": 1.0, "KOHM": 1e3, "MOHM": 1e6}

def parse(path):
    cu = ru = 1.0
    nm = {}
    out = []
    sec = None
    cur = None
    with open(path, errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            if sec is None or sec == "hdr":
                if line.startswith("*C_UNIT"):
                    p = line.split(); cu = float(p[1]) * UNIT_C[p[2].upper()]
                elif line.startswith("*R_UNIT"):
                    p = line.split(); ru = float(p[1]) * UNIT_R[p[2].upper()]
                elif line.startswith("*NAME_MAP"):
                    sec = "map"
                continue
            if sec == "map":
                if line[0] == "*" and line[1].isdigit():
                    p = line.split(None, 1)
                    nm[p[0]] = p[1].strip().replace("\\", "")
                    continue
                sec = "body"
            if line.startswith("*D_NET"):
                p = line.split()
                name = nm.get(p[1], p[1].replace("\\", ""))
                cur = [name, float(p[2]) * cu, 0.0, 0.0, 0.0, 0]
                sub = None
            elif cur is not None:
                c0 = line[0]
                if c0 == "*":
                    if line.startswith("*CAP"): sub = "cap"
                    elif line.startswith("*RES"): sub = "res"
                    elif line.startswith("*CONN"): sub = "conn"
                    elif line.startswith("*END"):
                        out.append(cur); cur = None
                    continue
                if sub == "cap":
                    p = line.split()
                    if len(p) == 3: cur[2] += float(p[2]) * cu
                    elif len(p) == 4: cur[3] += float(p[3]) * cu
                elif sub == "res":
                    p = line.split()
                    cur[4] += float(p[3]) * ru; cur[5] += 1
    return out

if __name__ == "__main__":
    rows = parse(sys.argv[1])
    with open(sys.argv[2], "w") as o:
        o.write("net\ttotal_c_fF\tgnd_c_fF\tcc_fF\tr_ohm\tn_res\n")
        for r in rows:
            o.write("%s\t%.6g\t%.6g\t%.6g\t%.6g\t%d\n" % tuple(r))
    print("%s: %d nets" % (sys.argv[1], len(rows)))
