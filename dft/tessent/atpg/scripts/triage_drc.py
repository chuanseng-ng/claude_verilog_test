#!/usr/bin/env python3
"""Group Tessent DRC violations by the RTL hierarchy of the offending sequential cell.

The yosys netlist is flat and its instances are anonymous (`_135887_`), but each flop/latch Q net keeps its RTL name
(`\\u_dft_ctrl.u_tap.state_q[0]`).  This script maps every instance named in a Tessent DRC report back to the hierarchical
prefix of its Q net, so a violation class can be attributed to a block (TAP domain, MBIST TCK side, DMA, ...).

Usage: triage_drc.py <gate_netlist.v> <drc_all_fails.rpt> [depth]   (depth = number of dotted components, default 2)
Output: per rule, the count and the top groups.
"""
import collections
import re
import sys

net_file, rpt_file = sys.argv[1], sys.argv[2]
depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2

inst_q = {}
cell_re = re.compile(r"^\s*(sky130_fd_sc_hd__(?:df|edf|dl|sdf|sdl|sedf)\w*)\s+(\S+)\s*\(")
cur = None
with open(net_file) as f:
    for line in f:
        m = cell_re.match(line)
        if m:
            cur = m.group(2)
            continue
        if cur:
            q = re.match(r"\s*\.(Q|Q_N|GCLK|X)\((.*)\)\s*,?\s*$", line)
            if q and cur not in inst_q:
                inst_q[cur] = q.group(2).strip()
            if line.strip().startswith(");"):
                cur = None


def group(net):
    net = net.strip().lstrip("\\")
    net = re.sub(r"\[\d+\]", "", net).split(" ")[0]
    if net.startswith("_") or "$" in net:
        return "(anonymous Q net)"
    parts = net.split(".")
    return ".".join(parts[:depth])


rules = collections.defaultdict(collections.Counter)
totals = collections.Counter()
viol_re = re.compile(r"/(\S+?)(?:/\S+)?\s.*\(([A-Z]+\d+)-\d+\)")
src_re = re.compile(r"\(([A-Z]+\d+)-\d+\)")
for line in open(rpt_file):
    m = re.search(r"(?:cell|flop|input \d+ of|latch|port)\s+/?(_\d+_|\S+?)(?:/\S+)?\s.*\(([A-Z]+\d+)-\d+\)\.?\s*$", line)
    m2 = re.search(r"\((S\d+|C\d+|D\d+|E\d+|A\d+)-\d+\)", line)
    if not m2:
        continue
    rule = m2.group(1)
    totals[rule] += 1
    inst = re.search(r"/(_\d+_)", line)
    if inst:
        rules[rule][group(inst_q.get(inst.group(1), "(not a flop/latch)"))] += 1
    else:
        rules[rule]["(no instance in message)"] += 1

for rule in sorted(totals):
    print("%s: %d violations" % (rule, totals[rule]))
    for g, n in rules[rule].most_common(12):
        print("    %6d  %s" % (n, g))
