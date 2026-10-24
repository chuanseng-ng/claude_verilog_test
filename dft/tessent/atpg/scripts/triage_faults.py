#!/usr/bin/env python3
# ruff: noqa: E501
"""Attribute Tessent untestable/undetected faults to RTL blocks.

The netlist is flat with anonymous instances; each cell is attributed to the hierarchy prefix of its output net (or of its own
name when yosys kept a hierarchical name).  Input: gate netlist, one or more `report_faults` files, depth.
Usage: triage_faults.py <netlist.v> <depth> <faults.rpt>...
Prints, per input file and fault code, the top groups.
"""
import collections
import re
import sys

net_file, depth, files = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
OUT_PINS = {"X", "Y", "Q", "Q_N", "GCLK", "SUM", "COUT", "LO", "HI", "Z"}
inst_group = {}


def grp(name):
    name = name.strip().lstrip("\\")
    name = re.sub(r"\[\d+\]", "", name)
    if name.startswith("_") or "$" in name or "." not in name:
        return None
    return ".".join(name.split(".")[:depth])


cell_re = re.compile(r"^\s*(sky130_\w+|\S+)\s+(\\?\S+)\s*\($")
cur, name = None, None
outs, ins = [], []
with open(net_file) as f:
    for line in f:
        m = cell_re.match(line)
        if m and not line.lstrip().startswith(("module", "input", "output", "wire", "assign")):
            name = m.group(2)
            cur = grp(name)
            outs, ins = [], []
            continue
        if name:
            p = re.match(r"\s*\.(\w+)\((.*?)\)\s*,?\s*$", line)
            if p and cur is None:
                g = grp(p.group(2))
                if g:
                    (outs if p.group(1) in OUT_PINS else ins).append(g)
            if line.strip().startswith(");"):
                if cur is None and outs:
                    cur = outs[0]
                elif cur is None and ins:
                    cur = collections.Counter(ins).most_common(1)[0][0]
                inst_group[name.lstrip("\\")] = cur or "(top-level glue / anonymous nets)"
                name, cur = None, None

for fn in files:
    cnt = collections.defaultdict(collections.Counter)
    for line in open(fn):
        m = re.match(r"\s*\d+\s+(\S+)\s+\"?/?(\\?[^\"]+?)(?:\s*/\w+)?\"?\s*$", line)
        if not m or m.group(1) == "EQ":
            continue
        code, pin = m.group(1), m.group(2)
        inst = re.sub(r"/\w+$", "", pin).strip().lstrip("/\\").strip()
        cnt[code][inst_group.get(inst, "(port / unknown)")] += 1
    print("== %s" % fn)
    for code in sorted(cnt):
        print(" %s: %d" % (code, sum(cnt[code].values())))
        for g, n in cnt[code].most_common(10):
            print("    %6d  %s" % (n, g))
