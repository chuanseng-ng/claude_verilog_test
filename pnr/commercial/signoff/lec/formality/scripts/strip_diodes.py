#!/usr/bin/env python3
"""strip_diodes.py <in.nl.v> <out.nl.v>  -- remove the ICC2 port-diode instances (sky130_fd_sc_hd__diode_2) for the 'no unmatched points' variant of the LEC.
A diode has ONE pin (DIODE, an input) and no function/output, so removing it cannot change any other cell's behaviour.  The script asserts that
every removed instance has exactly the form `diode_2 NAME ( .DIODE ( net ) ) ;` and (unless --allow-internal-nets) that the net is a primary input; it prints the count.
Not an edit of the ICC2 file in place: the stripped copy lives in the run dir."""
import sys, re
src, dst = sys.argv[1:3]
allow_internal = "--allow-internal-nets" in sys.argv[3:]   # b5e: ICC2 route-opt left 4 port diodes on buffered (internal) copies of input nets
t = open(src).read()
pat = re.compile(r"^sky130_fd_sc_hd__diode_2 (\S+) \( \.DIODE \( (\S+) \) \) ;\n", re.M)
found = pat.findall(t)
nd = t.count("sky130_fd_sc_hd__diode_2 ")
assert len(found) == nd, (len(found), nd)
inputs = set(re.findall(r"^input\s+(?:\[[^\]]*\]\s+)?(\S+)\s*;", t, re.M))
bad = [n for _, n in found if n.split("[")[0].strip() not in inputs]
assert allow_internal or not bad, bad[:5]
if bad: print("NOTE: %d diode(s) sit on internal (buffered) nets, not primary inputs directly: %s" % (len(bad), sorted(set(bad))))
open(dst, "w").write(pat.sub("", t))
print("stripped %d diode_2 instances (%d on primary inputs, %d on internal nets)" % (len(found), len(found)-len(bad), len(bad)))
