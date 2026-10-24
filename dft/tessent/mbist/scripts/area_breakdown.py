#!/usr/bin/env python3
"""area_breakdown.py <yosys stat report> ... -- group the per-module own areas of a Tessent-inserted design.

Every Tessent module is instantiated once except the small RTL cells (and2/mux2/clk_gate_and ... , counted once
here, a few tens of um2 in total), so the grouped sums are the inserted-hardware area.  Latches ($_DLATCH_*, ten
in the clock-gate cells) are not mapped by the dfflibmap/abc flow and are not counted (about 150 um2 estimated).
"""
import re
import sys

for f in sys.argv[1:]:
    t = open(f).read().split("=== design hierarchy ===")[0]
    d = {m.group(1): float(m.group(2)) for m in re.finditer(r"Chip area for module '\\?(\S+?)':\s+([\d.]+)", t)}
    g = {"controller": 0.0, "memory interfaces + comparators/status": 0.0, "BAP (TDR + SIBs)": 0.0,
         "IJTAG SIB network": 0.0, "Tessent TAP": 0.0, "generic cells": 0.0}
    for k, v in d.items():
        if "mbist_c1_controller" in k:
            g["controller"] += v
        elif "c1_interface" in k:
            g["memory interfaces + comparators/status"] += v
        elif "mbist_bap" in k:
            g["BAP (TDR + SIBs)"] += v
        elif "tessent_sib" in k:
            g["IJTAG SIB network"] += v
        elif "tap_main" in k:
            g["Tessent TAP"] += v
        elif "tessent_" in k:
            g["generic cells"] += v
    print(f)
    for k, v in g.items():
        print(f"  {k:42s} {v:9.0f}")
    print(f"  {'TOTAL inserted':42s} {sum(g.values()):9.0f}")
