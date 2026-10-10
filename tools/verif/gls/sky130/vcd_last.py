#!/usr/bin/env python3
"""Print the final value of named signals in a VCD (top-scope copies preferred).
usage: vcd_last.py <vcd> <signal> [signal...]"""
import sys

path, want = sys.argv[1], set(sys.argv[2:])
ids, last = {}, {}
with open(path) as f:
    defs = True
    for ln in f:
        s = ln.strip()
        if defs:
            if s.startswith("$var"):
                p = s.split()
                full = p[4]
                short = next((w for w in want if full == w or full.endswith("." + w)), None)
                if short and short not in ids.values():
                    ids[p[3]] = short
            elif s.startswith("$enddefinitions"):
                defs = False
            continue
        if not s or s[0] == "#":
            continue
        if s[0] == "b":
            sp = s.rfind(" ")
            v, i = s[1:sp], s[sp + 1:]
        else:
            v, i = s[0], s[1:]
        if i in ids:
            last[ids[i]] = v
for n in sorted(want):
    v = last.get(n)
    print(n, "=", hex(int(v, 2)) if v and set(v) <= {"0", "1"} else v)
