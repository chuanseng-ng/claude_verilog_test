#!/usr/bin/env python3
"""fix_netlist_for_netgen.py <in.v> <out.v>: MEASUREMENT COPY of a powered Verilog netlist for Netgen. Connectivity is unchanged.
 1. delete `supply1 X;` / `supply0 X;` declarations (Netgen turns them into phantom devices; X is also an input port)
 2. rename nets whose escaped names collide when case is folded (ICC2 wrote \\u_core/N1435 and \\u_core/n1435 as two nets).
    Netgen reads the PDK SPICE case-insensitively and then treats the Verilog case-insensitively too ("A case-insensitive file has
    been read and so the verilog file must be treated case-insensitive"), merging the pair into ONE net.
Streams the file twice (names, then rewrite)."""
import sys, re, collections
inp, outp = sys.argv[1:3]
names = collections.defaultdict(set)
tok = re.compile(r"\\\S+(?= )")
with open(inp, errors="replace") as f:
    for line in f:
        for m in tok.finditer(line): names[m.group(0).lower()].add(m.group(0))
coll = {}
for k, s in names.items():
    if len(s) > 1:
        for i, n in enumerate(sorted(s)):
            if i: coll[n] = n + "_CASEFIX%d" % i
print(f"renaming {len(coll)} case-colliding escaped names: {coll}")
pat = re.compile("|".join(re.escape(k) + r"(?= )" for k in sorted(coll, key=len, reverse=True))) if coll else None
sup = re.compile(r"^supply[01]\s+\S+\s*;")
nsup = 0
with open(inp, errors="replace") as f, open(outp, "w") as o:
    for line in f:
        if sup.match(line): nsup += 1; continue
        if pat: line = pat.sub(lambda m: coll[m.group(0)], line)
        o.write(line)
print(f"supply declarations removed: {nsup}")
