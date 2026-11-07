#!/usr/bin/env python3
"""b5g: list the AXI input-port nets whose routed length in the b5f DEF exceeds a threshold (default 2000 um).
usage: b5g_nets.py <def> <out.txt> [min_um]"""
import re, sys
lines = open(sys.argv[1]).read().split('\n')
thr = float(sys.argv[3]) if len(sys.argv) > 3 else 2000.0
i = next(k for k, l in enumerate(lines) if l.startswith('NETS '))
res = {}; cur = None; L = 0
for l in lines[i:]:
    if l.startswith('- '):
        if cur: res[cur] = L
        cur = l.split()[1]; L = 0; continue
    if cur and re.search(r'\bmet\d|\bli1', l):
        px = py = None
        for x, y in re.findall(r'\(\s*([\-\d\*]+)\s+([\-\d\*]+)(?:\s+\d+)?\s*\)', l):
            x = px if x == '*' else int(x); y = py if y == '*' else int(y)
            if px is not None and (px != x or py != y): L += abs(x - px) + abs(y - py)
            px, py = x, y
res[cur] = L
sel = sorted((n, v / 1000.0) for n, v in res.items() if re.match(r'axi_(rdata_i|rresp_i|rvalid_i)', n) and v / 1000.0 > thr)
open(sys.argv[2], 'w').write(''.join('%s %.1f\n' % s for s in sel))
print(len(sel), 'nets')
