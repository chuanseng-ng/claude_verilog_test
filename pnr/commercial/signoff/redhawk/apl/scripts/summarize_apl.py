#!/usr/bin/env python3
"""summarize_apl.py -- tabulate the APL cdev results (intrinsic C / ESR / leakage per P/G pin, LOW state) of apl/runs/main into reports/apl_cdev_summary.tsv, with the
HSPICE AC cross-check (1 MHz, C = Im(I)/(2 pi f), VPWR driven, VGND/VNB 0, VPB tied to VPWR) for the three decap cells measured independently (reports/hspice_decap_check.tsv)."""
import os, re, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__)); apl = os.path.join(here, ".."); rep = os.path.join(apl, "reports")
CAP = os.path.join(apl, "runs/main/results/TT_25_1v80/CAP")
env = dict(os.environ)
rows = ["cell\tpin\tesc_fF\tesr_ohm\tleak_A"]
for f in sorted(os.listdir(CAP)):
    if not f.endswith(".cdev") or f.startswith("ef_decap12_bad"): continue
    out = subprocess.run(["aplreader", os.path.join(CAP, f)], capture_output=True, text=True, env=env).stdout
    cell = f[:-5]; state = 0; seen = {}
    for line in out.splitlines():
        if "State = ADS_DEFAULT_STATE_LOW" in line: state = 1
        elif "State = ADS_DEFAULT_STATE_HIGH" in line: state = 2
        m = re.search(r"pin = (\w+), esc = ([\d.eE+-]+) F, esr = ([\d.eE+-]+) ohm", line)
        if m and state == 1: seen.setdefault(m.group(1), {}).update(esc=float(m.group(2)) * 1e15, esr=float(m.group(3)))
        m = re.search(r"pin = (\w+), leak = ([\d.eE+-]+) A", line)
        if m and state == 1: seen.setdefault(m.group(1), {}).update(leak=float(m.group(2)))
    for pin in ("VPWR", "VGND", "VPB", "VNB"):
        d = seen.get(pin)
        if d: rows.append("%s\t%s\t%.2f\t%.1f\t%.3g" % (cell, pin, d["esc"], d["esr"], d.get("leak", float("nan"))))
open(os.path.join(rep, "apl_cdev_summary.tsv"), "w").write("\n".join(rows) + "\n")
print("\n".join(rows))
