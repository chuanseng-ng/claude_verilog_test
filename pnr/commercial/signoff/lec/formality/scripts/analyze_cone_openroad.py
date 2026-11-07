import re,sys,collections
run=sys.argv[1]; nl=sys.argv[2]
OUT={"X","Y","Q","Q_N","COUT","SUM","HI","LO"}
syn=open(nl).read()
drv={}   # net -> (cell, [input nets])
cells={}
for m in re.finditer(r"^\s*(sky130_\w+)\s+(\S+)\s*\((.*?)\);",syn,re.S|re.M):
    typ,name,body=m.groups()
    pins=[(a,b.strip()) for a,b in re.findall(r"\.(\w+)\(([^()]*?)\)",body)]
    if typ.startswith("sky130_sram"):
        outs=[n for p,n in pins if p.startswith("dout")]; ins=[n for p,n in pins if not p.startswith("dout")]
        for o in outs: drv[o]=("SRAM",name,[])
        cells[name]=(typ,[(p,n) for p,n in pins if not p.startswith("dout")],outs); continue
    outs=[n for p,n in pins if p in OUT]; ins=[(p,n) for p,n in pins if p not in OUT]
    isff=typ.startswith("sky130_fd_sc_hd__df")
    cells[name]=(typ,ins,outs)
    for o in outs: drv[o]=("FF" if isff else "C",name,[n for p,n in ins if not (isff and p=="CLK")])
for m in re.finditer(r"^\s*assign\s+(\S+)\s*=\s*(\S+);",syn,re.M): drv[m.group(1)]=("A","",[m.group(2)])
def cone(net,memo={}):
    seen=set(); st=[net]; ffs=set()
    while st:
        n=st.pop()
        if n in seen: continue
        seen.add(n)
        d=drv.get(n)
        if not d: continue
        if d[0]=="FF": ffs.add(d[1]); continue
        if d[0]=="SRAM": continue
        st.extend(d[2])
    return ffs
un=open(run+"/unmatched_points.txt").read()
U=set(m.group(1) for m in re.finditer(r"Impl\s+DFF\s+i:/WORK/rv32i_cpu_top/(\S+)",un))
ft=open(run+"/failing_points.txt").read()
pairs=re.findall(r"Ref\s+(\w+)\s+r:/WORK/rv32i_cpu_top/(\S+)\n\s+Impl\s+(\w+)\s+i:/WORK/rv32i_cpu_top/(\S+)",ft)
exp=0; unexp=[]
for kind,rn,ik,iname in pairs:
    if ik=="DFF":
        c=cells.get(iname)
        if not c: continue
        dn=[n for p,n in c[1] if p=="D"][0]; ffs=cone(dn)
    elif ik=="Port":
        ffs=cone(iname.replace("\\","")) if iname in drv else cone(iname)
    else:
        ffs=None
    if ffs is None: unexp.append((kind,rn,iname,"bbpin")); continue
    if ffs & U: exp+=1
    else: unexp.append((kind,rn,iname,len(ffs)))
print("failing",len(pairs),"explained by unmatched impl flop in impl cone",exp,"not explained",len(unexp))
c=collections.Counter(k for k,_,_,_ in unexp); print(c)
for u in unexp[:15]: print(u)
