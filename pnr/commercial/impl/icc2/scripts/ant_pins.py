#!/usr/bin/env python3
"""ant_pins.py <openroad check_antennas -verbose report> <out ant_pins.txt> -- violating (net, sink pin) pairs, one "{net} {pin}" line each.
A pin block is 'Pin:  inst/pin (cell)' under a 'Net:' header; it violates if any line in the block carries '(VIOLATED)'."""
import re, sys
net = pin = None; viol = set(); order = []
for ln in open(sys.argv[1]):
    m = re.match(r"Net:\s+(\S+)", ln)
    if m: net = m.group(1); pin = None; continue
    m = re.match(r"\s+Pin:\s+(\S+)", ln)
    if m: pin = m.group(1); continue
    if "(VIOLATED)" in ln and net and pin and (net, pin) not in viol:
        viol.add((net, pin)); order.append((net, pin))
with open(sys.argv[2], "w") as f:
    for n, p in order: f.write("{%s} {%s}\n" % (n.replace("\\/", "/"), p.replace("\\/", "/")))
print("violating nets", len({n for n, _ in order}), "pins", len(order))
