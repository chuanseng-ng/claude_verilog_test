#!/usr/bin/env python3
"""Quantify what excluding the crypto key flops from scan costs, on a synthesised netlist.

usage: crypto_cone.py soc_top.nl.v [--emit-instances out.txt]

Excluded set E = flops whose Q net name matches EXCL (key shadow register and AES round key).
Reports (all on the pre-scan netlist, graph analysis, no ATPG):
  * |E| flops and their share of all flops
  * fan-in cone: combinational cells that drive ONLY excluded flops' D pins (observable nowhere else)
  * fan-out cone: combinational cells in the transitive fan-out of E up to the next sequential element
  * dead cone: fan-out cells whose entire input support is E plus constants (no scan-controllable input at all)
Fault counts are the uncollapsed pin count x 2, an upper-bound proxy, not an ATPG number.
"""
import re
import sys
from collections import defaultdict

EXCL = re.compile(r'u_crypto\.g_aes\.u_aes\.(rk_q|key_i)\b')
OUTS = {'X', 'Y', 'Q', 'Q_N', 'COUT', 'SUM', 'HI', 'LO', 'GCLK'}

text = open(sys.argv[1]).read()
cells = {}
for typ, name, body in re.findall(
        r'\n\s*(sky130_fd_sc_hd__\w+|rv32i_cpu_top|sky130_sram_\w+)\s+(\\?\S+)\s*\((.*?)\);', text, re.S):
    pins = {p: n.strip() for p, n in re.findall(r'\.(\w+)\(([^()]*)\)', body)}
    cells[name] = (typ, pins)

is_seq = lambda t: '__df' in t or '__dlx' in t or '__sdf' in t or t.startswith('rv32i') or 'sram' in t
driver = {}
fanout = defaultdict(list)
for n, (t, pins) in cells.items():
    for p, net in pins.items():
        if p in OUTS and not t.startswith(('rv32i', 'sky130_sram')):
            driver[net] = n
        else:
            fanout[net].append((n, p))

flops = [n for n, (t, _) in cells.items() if '__df' in t]
excl = [n for n in flops if EXCL.search(cells[n][1].get('Q', ''))]
print('flops total', len(flops), '| excluded', len(excl), '(%.2f %%)' % (100.0 * len(excl) / len(flops)))
exclset = set(excl)

# fan-out cone from E
seen = set()
stack = [cells[f][1]['Q'] for f in excl]
while stack:
    net = stack.pop()
    for c, p in fanout.get(net, []):
        t, pins = cells[c]
        if is_seq(t) or c in seen:
            continue
        seen.add(c)
        for op, onet in pins.items():
            if op in OUTS:
                stack.append(onet)
fo = seen

# dead cone: all inputs (transitively) from E or constants
const_nets = {'1\'h0', '1\'h1'}
memo = {}


def dead(c):
    if c in memo:
        return memo[c]
    memo[c] = False  # cycle guard
    t, pins = cells[c]
    ok = True
    for p, net in pins.items():
        if p in OUTS:
            continue
        d = driver.get(net)
        if d is None:
            ok = ok and (net in const_nets)
        elif d in exclset:
            continue
        elif t.startswith('sky130_fd_sc_hd__conb'):
            continue
        elif cells[d][0].startswith('sky130_fd_sc_hd__conb'):
            continue
        elif is_seq(cells[d][0]):
            ok = False
        else:
            ok = ok and dead(d)
    memo[c] = ok
    return ok


dc = {c for c in fo if dead(c)}

# fan-in cone: cells whose every fan-out lands (transitively through comb cells) only on excluded D pins
only = {}


def only_to_excl(c):
    if c in only:
        return only[c]
    only[c] = False
    t, pins = cells[c]
    ok = True
    any_sink = False
    for op, onet in pins.items():
        if op not in OUTS:
            continue
        for sc, sp in fanout.get(onet, []):
            any_sink = True
            if sc in exclset and sp == 'D':
                continue
            if is_seq(cells[sc][0]):
                ok = False
            else:
                ok = ok and only_to_excl(sc)
    only[c] = ok and any_sink
    return only[c]


fi = set()
stack = [cells[f][1]['D'] for f in excl]
visited = set()
while stack:
    net = stack.pop()
    d = driver.get(net)
    if d is None or d in visited or is_seq(cells[d][0]):
        continue
    visited.add(d)
    for p, n in cells[d][1].items():
        if p not in OUTS:
            stack.append(n)
fi = {c for c in visited if only_to_excl(c)}

allpins = sum(len(p) for _, p in cells.values())
cell_total = len(cells)


def faults(cs):
    return 2 * sum(len(cells[c][1]) for c in cs)


print('cells total', cell_total, '| pin-based fault proxy total', 2 * allpins)
for name, cs in (('fan-in exclusive (observable only via E)', fi),
                 ('fan-out cone of E (affected, upper bound)', fo),
                 ('dead cone (support = E + consts)', dc)):
    print('%-45s cells %6d  fault proxy %7d  (%.3f %% of total)' % (
        name, len(cs), faults(cs), 100.0 * faults(cs) / (2 * allpins)))
direct = 2 * (len(excl) * 3)  # D, CLK, Q pins of each excluded flop (CLK/Q/D faults, not collapsed)
print('excluded flops own pins fault proxy', direct, '(%.3f %%)' % (100.0 * direct / (2 * allpins)))
if len(sys.argv) > 3 and sys.argv[2] == '--emit-instances':
    open(sys.argv[3], 'w').write('\n'.join(excl) + '\n')
