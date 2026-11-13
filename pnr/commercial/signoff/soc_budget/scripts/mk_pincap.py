#!/usr/bin/env python3
"""mk_pincap.py -- input-pin capacitances (pF) of the SoC's CPU macro Liberty (pnr/sky130/cpu/macro, nom RC), one file per lib corner: runs/pincap_<lib>.tsv"""
import re, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "../../../../.."))
for L, c in {"tt": "nom_tt_025C_1v80", "ss": "nom_ss_100C_1v60", "ff": "nom_ff_n40C_1v95"}.items():
    t = open(f"{ROOT}/pnr/sky130/cpu/macro/rv32i_cpu_top__{c}.lib").read()
    with open(f"{HERE}/../runs/pincap_{L}.tsv", "w") as o:
        for m in re.finditer(r'pin\("([^"]+)"\)\s*\{\s*direction : input;\s*capacitance : ([0-9.eE+-]+);', t):
            o.write(f"{m.group(1)}\t{m.group(2)}\n")
