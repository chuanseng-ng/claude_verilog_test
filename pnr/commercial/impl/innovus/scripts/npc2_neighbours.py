#!/usr/bin/env python3 -I
"""npc2_neighbours.py <def> -- statistics of the right-hand neighbour of every and2_0 (by orientation) vs the six KLayout npc.2 hits of b5j (cell right edge x, row y)."""
import re,os,collections,sys
W={};cur=None
for l in open(os.path.expanduser('~/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef')):
    m=re.match(r'\s*MACRO (\S+)',l)
    if m: cur=m.group(1)
    m=re.match(r'\s*SIZE ([\d.]+) BY',l)
    if m and cur: W[cur]=float(m.group(1))
rows=collections.defaultdict(list); sec=0
for l in open(sys.argv[1]):
    if l.startswith('COMPONENTS'): sec=1; continue
    if l.startswith('END COMPONENTS'): break
    if not sec: continue
    m=re.match(r'\s*- (\S+) (\S+) .*?\( (-?\d+) (-?\d+) \) (\S+)',l)
    if m and m.group(2) in W: rows[int(m.group(4))].append((int(m.group(3)),m.group(2).replace('sky130_fd_sc_hd__',''),m.group(5)))
bad={(1454520,1126080),(1524440,1395360),(1197840,1194080),(1781580,1093440),(1203360,1188640),(1499140,1286560)}
st=collections.Counter(); w=round(W['sky130_fd_sc_hd__and2_0']*1000)
for y,L in rows.items():
    L.sort()
    for i,(x,c,o) in enumerate(L[:-1]):
        if c=='and2_0' and abs(x+w-L[i+1][0])<2:
            n=L[i+1][1]; n=n.split('_')[0]+'_*' if n.startswith('decap') else n
            st[(o,n,'BAD' if (x+w,y) in bad else 'ok')]+=1
for k,v in sorted(st.items()): print(k,v)
