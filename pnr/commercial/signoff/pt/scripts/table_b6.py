#!/usr/bin/env python3
"""table_b6.py -- b6 judge tables: per SDC variant (base / iolat / own) x 9 corners, arms icc2b6 / icc2b5m / innovusb5k / openroad.
Reads runs*/<arm>_<rc>_<lib>/metrics.tsv (+ power_B.txt Total at nom_tt).  Prints markdown."""
import os, re, sys
PT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = {"base": "runs", "iolat": "runs_iolat", "own": "runs_own"}
ARMS = [("icc2b6", "ICC2 b6"), ("icc2b5m", "ICC2 b5m"), ("innovusb5k", "Innovus b5k"), ("openroad", "OpenROAD")]
def rd(p):
    d = {}
    try:
        for l in open(p):
            k, _, v = l.rstrip("\n").partition("\t"); d[k] = v
    except OSError: return None
    return d
def f(x, n=3):
    try: return ("%+." + str(n) + "f") % float(x)
    except Exception: return "-"
for var in sys.argv[1:] or ["base", "iolat", "own"]:
    print("\n### SDC variant `%s`: setup WNS ns (violators) / hold WNS ns (violators)\n" % var)
    print("| corner | " + " | ".join(n for _, n in ARMS) + " |")
    print("|---|" + "---|" * len(ARMS))
    for rc in ("nom", "min", "max"):
        for lib in ("tt", "ss", "ff"):
            row = []
            for a, _ in ARMS:
                m = rd(os.path.join(PT, DIRS[var], "%s_%s_%s" % (a, rc, lib), "metrics.tsv"))
                if not m: row.append("n/a"); continue
                row.append("%s (%s) / %s (%s)" % (f(m.get("setup_wns")), m.get("setup_viol", "?"), f(m.get("hold_wns")), m.get("hold_viol", "?")))
            print("| %s_%s | %s |" % (rc, lib, " | ".join(row)))
    print("\nreg-to-reg (r2rx) worst setup / hold, ns (violators):\n")
    print("| corner | " + " | ".join(n for _, n in ARMS) + " |")
    print("|---|" + "---|" * len(ARMS))
    for rc in ("nom", "min", "max"):
        for lib in ("tt", "ss", "ff"):
            row = []
            for a, _ in ARMS:
                m = rd(os.path.join(PT, DIRS[var], "%s_%s_%s" % (a, rc, lib), "metrics.tsv"))
                if not m: row.append("n/a"); continue
                s = m.get("r2rx_setup_wns", ""); h = m.get("r2rx_hold_wns", "")
                row.append("%s (%s) / %s (%s)" % ("none" if s in ("1e9", "") else f(s), m.get("r2rx_setup_viol", "?"), "none" if h in ("1e9", "") else f(h), m.get("r2rx_hold_viol", "?")))
            print("| %s_%s | %s |" % (rc, lib, " | ".join(row)))
    row = []
    for a, _ in ARMS:
        p = os.path.join(PT, DIRS[var], "%s_nom_tt" % a, "power_B.txt"); t = "-"
        try:
            for l in open(p):
                m = re.match(r"Total Power\s*=\s*([-0-9.e+]+)", l)
                if m: t = "%.1f mW" % (float(m.group(1)) * 1000)
        except OSError: pass
        row.append(str(t))
    print("\nnom_tt PrimePower total (raw `Total` row tail, W): " + "; ".join("%s %s" % (n, r) for (_, n), r in zip(ARMS, row)))
