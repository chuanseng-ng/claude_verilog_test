#!/usr/bin/env python3
"""strip_diodes.py <in.nl.v> <out.nl.v> -- B4d: remove every sky130_fd_sc_hd__diode_2 instance from the Innovus netlist (copy; the original is never edited).
A diode has a single input pin (.DIODE) and no output: it cannot influence any compare point.  Conformal may report such cells as unmatched
revised black boxes; the stripped copy lets the 'unmatched = 0' count be literally true with no waiver (same approach as B4c, formality/scripts/strip_diodes.py).
Asserts: every diode instance has exactly the form `diode_2 NAME ( .DIODE(net) );`. The count is derived from the file and printed (b5b: 271 = 115 PORTDIODE_*
+ 156 DIODE_*; b5c: 262); pass it as argv[3] to assert it."""
import re, sys
src, dst = sys.argv[1:3]
expect = int(sys.argv[3]) if len(sys.argv) > 3 else None   # optional: assert the count; default = derive it (B4e: b5c has a different count than b5b)
t = open(src).read()
pat = re.compile(r"[ \t]*sky130_fd_sc_hd__diode_2\s+\S+\s*\(\s*\.DIODE\s*\(\s*\S+?\s*\)\s*\)\s*;\n")
n_all = len(re.findall(r"sky130_fd_sc_hd__diode_2\b", t))
ms = pat.findall(t)
assert n_all == len(ms) and len(ms) > 0, (n_all, len(ms))   # every diode_2 instance matches the exact form
assert expect is None or len(ms) == expect, (len(ms), expect)
nports = sum(1 for m in re.findall(r"diode_2\s+(\S+)", t) if "PORTDIODE" in m)
open(dst, "w").write(pat.sub("", t))
print("stripped %d diode_2 instances (%d PORTDIODE, %d other) -> %s" % (len(ms), nports, len(ms) - nports, dst))
