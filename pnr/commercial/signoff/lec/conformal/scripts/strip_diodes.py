#!/usr/bin/env python3
"""strip_diodes.py <in.nl.v> <out.nl.v> -- B4d: remove every sky130_fd_sc_hd__diode_2 instance from the Innovus netlist (copy; the original is never edited).
A diode has a single input pin (.DIODE) and no output: it cannot influence any compare point.  Conformal may report such cells as unmatched
revised black boxes; the stripped copy lets the 'unmatched = 0' count be literally true with no waiver (same approach as B4c, formality/scripts/strip_diodes.py).
Asserts: every diode instance has exactly the form `diode_2 NAME ( .DIODE(net) );` and the count equals EXPECT (default 271 = 115 PORTDIODE_* on primary
inputs + 156 DIODE_* antenna-repair diodes in b5b_innovus)."""
import re, sys
src, dst = sys.argv[1:3]
expect = int(sys.argv[3]) if len(sys.argv) > 3 else 271
t = open(src).read()
pat = re.compile(r"[ \t]*sky130_fd_sc_hd__diode_2\s+\S+\s*\(\s*\.DIODE\s*\(\s*\S+?\s*\)\s*\)\s*;\n")
n_all = len(re.findall(r"sky130_fd_sc_hd__diode_2\b", t))
ms = pat.findall(t)
assert n_all == len(ms) == expect, (n_all, len(ms), expect)
open(dst, "w").write(pat.sub("", t))
print("stripped %d diode_2 instances -> %s" % (len(ms), dst))
