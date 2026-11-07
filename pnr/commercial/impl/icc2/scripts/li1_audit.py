#!/usr/bin/env python3
"""li1_audit.py <def> -- routed li1 usage in a DEF NETS/SPECIALNETS section (Step B5e).
Reports (a) li1 wire segments of non-zero length (= signal/clock routing on li1; must be 0),
(b) li1-context items of zero length (a via placed on an li1 landing = cell-pin access mcon; legitimate),
(c) the nets involved, split by clock-ness is not decidable from DEF, so the net names with long segments are listed."""
import re, sys, collections
d = sys.argv[1]
units = 1000
nets = collections.defaultdict(lambda: [0, 0.0, 0.0])   # net -> [nseg, total_len, max_len]
zero = 0; mcon_via_total = 0
sec = None; net = None
isint = re.compile(r'^-?\d+$')
VIA = {'mcon': ('li1', 'met1'), 'via': ('met1', 'met2'), 'via2': ('met2', 'met3'), 'via3': ('met3', 'met4'), 'via4': ('met4', 'met5')}
def vkey(t):
    m = re.match(r'(mcon|via\d?)(_|$)', t)
    return m.group(1) if m else None
def segments(buf):
    """yield (layer, x0, y0, x1, y1) for wires and (layer, x, y) for via landings; layer follows vias through the item"""
    toks = buf.replace('(', ' ( ').replace(')', ' ) ').split()
    i = 0; wires = []; lands = []
    while i < len(toks):
        if toks[i] in ('ROUTED', 'NEW'):
            layer = toks[i + 1]; i += 2; cur = None
            while i < len(toks) and toks[i] not in ('ROUTED', 'NEW', '+', ';'):
                t = toks[i]
                if t == '(':
                    j = i + 1; vals = []
                    while toks[j] != ')': vals.append(toks[j]); j += 1
                    x = cur[0] if vals[0] == '*' else int(vals[0]); y = cur[1] if vals[1] == '*' else int(vals[1])
                    if cur is not None and (x, y) != cur: wires.append((layer, cur[0], cur[1], x, y))
                    cur = (x, y); i = j + 1
                else:
                    k = vkey(t)
                    if k and cur is not None:
                        lo, hi = VIA[k]
                        lands.append((layer, cur[0], cur[1], k))
                        layer = hi if layer == lo else lo if layer == hi else layer
                        lands.append((layer, cur[0], cur[1], k))
                    i += 1
        else:
            i += 1
    return wires, lands
buf = ''
for l in open(d):
    if l.startswith('UNITS'): units = int(l.split()[3])
    if l.startswith(('NETS ', 'SPECIALNETS ')): sec = 1; continue
    if l.startswith(('END NETS', 'END SPECIALNETS')): sec = None; continue
    if not sec: continue
    if l.lstrip().startswith('- ') and not buf: buf = l; 
    else: buf += l
    if ';' in l and buf:
        m = re.match(r'\s*- (\S+)', buf); name = m.group(1) if m else '?'
        wires, lands = segments(buf)
        for layer, x0, y0, x1, y1 in wires:
            if layer == 'li1':
                L = (abs(x1 - x0) + abs(y1 - y0)) / units
                n = nets[name]; n[0] += 1; n[1] += L; n[2] = max(n[2], L)
        for layer, x, y, k in lands:
            if layer == 'li1': zero += 1
            if k == 'mcon': mcon_via_total += 1
        buf = ''
nseg = sum(v[0] for v in nets.values()); tot = sum(v[1] for v in nets.values())
print(f"li1 wire segments (len>0): {nseg} on {len(nets)} nets, total {tot:.1f} um, longest {max([v[2] for v in nets.values()] or [0]):.1f} um")
print(f"li1 via landings (mcon/li1 at cell-pin access; counted once per via end on li1): {zero};  mcon via tokens in DEF: {mcon_via_total // 2}")
for n, v in sorted(nets.items(), key=lambda kv: -kv[1][2])[:20]: print(f"  {n}: {v[0]} seg, {v[1]:.1f} um, max {v[2]:.1f}")
