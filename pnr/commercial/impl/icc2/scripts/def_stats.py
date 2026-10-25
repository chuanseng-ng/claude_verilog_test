#!/usr/bin/env python3
"""def_stats.py <def> -- component class counts, routed wirelength per layer and via counts from a DEF (tool-neutral)."""
import re, sys, collections
f = sys.argv[1]
comp = collections.Counter(); vias = collections.Counter(); wl = collections.Counter()
sec = None; units = 1000
isnum = re.compile(r'^-?\d+$')
with open(f) as fh:
    for l in fh:
        if l.startswith('UNITS'): units = int(l.split()[3])
        if l.startswith('COMPONENTS'): sec = 'C'; continue
        if l.startswith('END COMPONENTS'): sec = None
        if l.startswith('NETS'): sec = 'N'; continue
        if l.startswith('END NETS'): sec = None
        if sec == 'C' and l.lstrip().startswith('- '):
            comp[l.split()[2]] += 1
        if sec == 'N':
            toks = l.replace('(', ' ( ').replace(')', ' ) ').split()
            layer = None; last = None; i = 0
            while i < len(toks):
                t = toks[i]
                if t in ('ROUTED', 'NEW') and i + 1 < len(toks):
                    layer = toks[i + 1]; last = None; i += 2; continue
                if t == '(' and i + 2 < len(toks) and (isnum.match(toks[i+1]) or toks[i+1] == '*') and (isnum.match(toks[i+2]) or toks[i+2] == '*'):
                    x = last[0] if toks[i+1] == '*' else int(toks[i+1]); y = last[1] if toks[i+2] == '*' else int(toks[i+2])
                    if last is not None and layer: wl[layer] += abs(x - last[0]) + abs(y - last[1])
                    last = (x, y); i += 1
                    # skip optional extension number
                    continue
                if last is not None and layer and t not in ('(', ')', '+', ';', '-', 'ROUTED', 'NEW') and not isnum.match(t) and t != '*' and not t.startswith('MASK'):
                    if t.lower().startswith(('via', 'mcon', 'li1', 'm1m', 'm2m', 'm3m', 'm4m', 'm5m')) and t != layer: vias[t] += 1
                i += 1
print('components', sum(comp.values()))
for k, v in sorted(comp.items(), key=lambda kv: -kv[1])[:14]: print('  ', k, v)
print('routed wirelength um', round(sum(wl.values()) / units))
for k, v in sorted(wl.items()): print('   ', k, round(v / units))
print('vias', sum(vias.values()))
for k, v in vias.most_common(12): print('   ', k, v)
