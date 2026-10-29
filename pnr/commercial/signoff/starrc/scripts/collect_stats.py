#!/usr/bin/env python3
"""collect_stats.py  -- per (arm, corner) table from runs/<arm>_<corner>/: net counts, opens, shorts, C, runtime, RSS."""
import os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spef_stats import parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../.."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DEF = {"openroad": "pnr/commercial/runs/openroad/rv32i_cpu_top.def",
       "icc2": "pnr/commercial/impl/icc2/runs/b5a_icc2/out/rv32i_cpu_top.def",
       "innovus": "pnr/commercial/impl/innovus/runs/b5d_innovus/out/rv32i_cpu_top.def"}

def def_nets(arm):
    with open(os.path.join(ROOT, DEF[arm])) as f:
        for l in f:
            if l.startswith("NETS "):
                return int(l.split()[1])

def grep_count(path, pat):
    n = 0
    try:
        with open(path, errors="replace") as f:
            for l in f:
                if re.search(pat, l): n += 1
    except OSError:
        pass
    return n

rows = []
for arm in ("openroad", "icc2", "innovus"):
    for c in ("nom", "min", "max"):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", "%s_%s" % (arm, c))
        spef = os.path.join(d, "rv32i_cpu_top.%s.spef" % c)
        if not os.path.exists(spef): continue
        nets = parse(spef)
        tot = sum(n[1] for n in nets); gnd = sum(n[2] for n in nets); cc = sum(n[3] for n in nets) / 2
        zero = sum(1 for n in nets if n[1] == 0.0)
        rs = sum(n[4] for n in nets)
        opens = None
        try:
            for l in open(os.path.join(d, "star/summary/.ReportOpens.messages")):
                m = re.search(r"report_opens NETID1 : (\d+)", l)
                if m: opens = int(m.group(1))
        except OSError: pass
        log = os.path.join(d, "starrc.log")
        sx = {}
        for l in open(log, errors="replace"):
            m = re.match(r"(WARNING|ERROR).*\((SX-\d+)\)", l)
            if not m:
                m = re.match(r"\s.*\((SX-\d+)\)\s*$", l)
                if m: sx[m.group(1)] = sx.get(m.group(1), 0) + 1
                continue
            sx[m.group(2)] = sx.get(m.group(2), 0) + 1
        wall = rss = ""
        try:
            for l in open(os.path.join(d, "time.txt")):
                if "Elapsed (wall" in l: wall = l.split()[-1]
                if "Maximum resident" in l: rss = "%.2f" % (int(l.split()[-1]) / 1048576.0)
        except OSError: pass
        rows.append((arm, c, def_nets(arm), len(nets), zero, opens, tot / 1e3, gnd / 1e3, cc / 1e3, rs / 1e6, wall, rss, sx))

print("| arm | corner | DEF nets | SPEF D_NETs | zero-C nets | opens | total C (pF) | gnd C (pF) | coupling C (pF) | sum R (Mohm) | wall | peak RSS (GB) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| %s | %s | %d | %d | %d | %s | %.1f | %.1f | %.1f | %.2f | %s | %s |" % r[:12])
print()
for r in rows:
    print("%s_%s message codes: %s" % (r[0], r[1], ", ".join("%s x%d" % kv for kv in sorted(r[12].items()))))
