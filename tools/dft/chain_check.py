#!/usr/bin/env python3
"""Walk the scan chain of a gate-level netlist produced by OpenROAD insert_dft.
usage: chain_check.py netlist.v scan_in_net scan_out_net
Reports chain length, tail, scan-enable nets, clock nets, SCD/SCE fanout.
Measured structural check only (no simulation)."""
import re
import sys

t = open(sys.argv[1]).read()
si, so = sys.argv[2], sys.argv[3]
cells = re.findall(r'\n\s*(sky130_fd_sc_hd__\w+)\s+(\S+)\s*\((.*?)\);', t, re.S)
flops = {}
for typ, name, body in cells:
    if '__sdf' in typ or '__sedf' in typ:
        pins = dict(re.findall(r'\.(\w+)\(([^)]*)\)', body))
        flops[name] = {k: v.strip() for k, v in pins.items()}
        flops[name]['_t'] = typ
plain = [n for typ, n, b in cells if re.search(r'__(df|edf)', typ)]
print('scan flops', len(flops), '| remaining non-scan flops', len(plain))
by_scd = {}
for n, f in flops.items():
    by_scd.setdefault(f['SCD'], []).append(n)
heads = by_scd.get(si, [])
print('flops on scan_in:', heads)
cur = heads[0]
seen = []
guard = set()
while cur and cur not in guard:
    guard.add(cur)
    seen.append(cur)
    nxt = by_scd.get(flops[cur]['Q'], [])
    cur = nxt[0] if nxt else None
print('chain length walked', len(seen), '| unreached flops', len(set(flops) - set(seen)))
print('tail Q net', flops[seen[-1]]['Q'], '| scan_out net', so)
print('SCE nets', sorted(set(f['SCE'] for f in flops.values())))
print('CLK nets', sorted(set(f['CLK'] for f in flops.values())))
print('cell types', sorted(set(f['_t'] for f in flops.values())))
