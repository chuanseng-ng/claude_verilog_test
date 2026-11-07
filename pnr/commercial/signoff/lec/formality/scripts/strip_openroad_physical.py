#!/usr/bin/env python3
"""strip_openroad_physical.py <in.nl.v> <out.nl.v> [--diodes]
Make a LEC-readable copy of the OpenROAD/LibreLane `final/nl/rv32i_cpu_top.nl.v`.
That netlist is the *logical* export but still carries every physical-only instance:
  * sky130_fd_sc_hd__{decap_N,fill_N,tapvpwrvgnd_N} and sky130_ef_sc_hd__decap_12 -- each with an EMPTY port list `()`; they have no signal pin at all.
    (sky130_ef_sc_hd__decap_12 has no .db model, so Formality could not link the netlist otherwise.)
  * --diodes: sky130_fd_sc_hd__diode_2 antenna / port diodes -- one INPUT pin (.DIODE), no output.
Removing an instance with no output pin and no signal connection cannot change any other cell's behaviour.
The script ASSERTS the form of every instance it removes (empty `()` for physical-only, exactly one `.DIODE(net)` for diodes), that the removed count equals
the number of textual occurrences of those master names (nothing is left behind or half-matched), and prints per-master counts.
Nothing else is touched (no logic cell, buffer, tie cell, SRAM or assign is removed or edited)."""
import re, sys, collections
src, dst = sys.argv[1:3]
diodes = "--diodes" in sys.argv[3:]
t = open(src).read()
phys = re.compile(r"^ (sky130_(?:fd|ef)_sc_hd__(?:decap|fill|tapvpwrvgnd)_\d+) (\S+) \(\);\n", re.M)
found = phys.findall(t)
n_txt = len(re.findall(r"^ sky130_(?:fd|ef)_sc_hd__(?:decap|fill|tapvpwrvgnd)_\d+ ", t, re.M))
assert len(found) == n_txt, ("physical-only instance with a non-empty or unusual port list", len(found), n_txt)
cnt = collections.Counter(m for m, _ in found)
t = phys.sub("", t)
print("removed %d physical-only instances:" % len(found), dict(sorted(cnt.items())))
if diodes:
    dio = re.compile(r"^ sky130_fd_sc_hd__diode_2 (\S+)\s+\(\s*\.DIODE\(((?:[^()\n]|\n)+?)\s*\)\s*\);\n", re.M)   # may be wrapped over two lines (long escaped net names)
    f2 = dio.findall(t)
    n2 = len(re.findall(r"^ sky130_fd_sc_hd__diode_2 ", t, re.M))
    assert len(f2) == n2, ("diode with unusual form", len(f2), n2)
    inputs = set(re.findall(r"^ input\s+(?:\[[^\]]*\]\s+)?(\S+)\s*;", t, re.M))
    onprim = sum(1 for _, n in f2 if n.split("[")[0].strip() in inputs)
    t = dio.sub("", t)
    print("removed %d diode_2 instances (%d on primary-input nets, %d on internal nets)" % (len(f2), onprim, len(f2) - onprim))
left = re.findall(r"sky130_(?:fd|ef)_sc_hd__(?:decap|fill|tapvpwrvgnd%s)_\d+" % ("|diode" if diodes else ""), t)
assert not left, left[:3]
open(dst, "w").write(t)
print("written", dst)
