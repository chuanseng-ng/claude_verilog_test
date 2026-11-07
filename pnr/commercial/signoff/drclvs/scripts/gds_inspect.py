# gds_inspect.py -- run with `klayout -b -r gds_inspect.py -rd gds=<file> -rd top=<cell> -rd out=<report>`
# Reports: cell census (empty/referenced-only cells), std-cell + SRAM geometry presence, layer:datatype table with
# shape counts in the top cell, and a spot-check of the Sky130 layer map. Pure reading; no layout change.
import pya, sys, re
gds = globals().get("gds"); top = globals().get("top", "rv32i_cpu_top"); out = globals().get("out")
ly = pya.Layout(); ly.read(gds)
lines = []
def P(s=""): lines.append(s); print(s)
P(f"GDS {gds}  dbu={ly.dbu}  cells={ly.cells()}  layers={ly.layers()}")
tc = ly.cell(top)
P(f"top cell {top}: found={tc is not None}  bbox um={tc.dbbox() if tc else None}")
tops = [c.name for c in ly.top_cells()]
P(f"top cells in file: {tops}")
# cell census
empty, std, sram, other = [], [], [], []
for c in ly.each_cell():
    n = c.name
    nsh = sum(c.shapes(li).size() for li in ly.layer_indexes())
    ninst = c.child_instances()
    if re.match(r"sky130_(fd_sc_hd|ef_sc_hd)__", n): std.append((n, nsh, ninst))
    elif "sram" in n.lower(): sram.append((n, nsh, ninst))
    if nsh == 0 and ninst == 0: empty.append(n)
P(f"std-cell structures: {len(std)}; with zero shapes: {sum(1 for n,s,i in std if s==0 and i==0)}")
P(f"sram-related structures: {len(sram)}; with zero shapes+zero instances: {sum(1 for n,s,i in sram if s==0 and i==0)}")
for n, s, i in sorted(sram, key=lambda x: -x[1])[:6]: P(f"   sram struct {n}: own shapes={s} child instances={i}")
P(f"completely empty structures (0 shapes, 0 instances): {len(empty)}  e.g. {empty[:8]}")
used_std = set()
for c in ly.each_cell():
    pass
# which std cells the top actually instantiates (recursively counted by cell name through hierarchy is heavy; use called cells)
called = set()
def walk(c, seen):
    for ci in c.each_child_cell():
        if ci in seen: continue
        seen.add(ci); walk(ly.cell(ci), seen)
seen = set(); walk(tc, seen)
cn = sorted(ly.cell(i).name for i in seen)
P(f"cells reachable from top: {len(cn)}; std {sum(1 for n in cn if n.startswith('sky130_fd_sc_hd__') or n.startswith('sky130_ef'))}; sram {[n for n in cn if 'sram' in n.lower()][:3]}...")
missing = [n for n in cn if (ly.cell(n).bbox().empty() and ly.cell(n).child_instances()==0)]
P(f"reachable cells with EMPTY geometry (would be reference-only): {len(missing)} {missing[:10]}")
# layer table
P("")
P("layer:datatype | top-cell own shapes | all-cells own shapes")
tbl = []
for li in ly.layer_indexes():
    info = ly.get_info(li)
    t = tc.shapes(li).size()
    a = sum(c.shapes(li).size() for c in ly.each_cell())
    tbl.append((info.layer, info.datatype, t, a))
for l, d, t, a in sorted(tbl): P(f"{l:4d}:{d:<3d} | {t:10d} | {a:12d}")
P("")
want = {"nwell":(64,20),"diff":(65,20),"tap":(65,44),"poly":(66,20),"licon1":(66,44),"li1":(67,20),"mcon":(67,44),"met1":(68,20),"via":(68,44),
        "met2":(69,20),"via2":(69,44),"met3":(70,20),"via3":(70,44),"met4":(71,20),"via4":(71,44),"met5":(72,20),"npc":(95,20),"nsdm":(93,44),"psdm":(94,20)}
have = {(l,d):(t,a) for l,d,t,a in tbl}
P("spot-check (Sky130 layer map): name  l:d  top-shapes  all-shapes")
for k,(l,d) in want.items():
    t,a = have.get((l,d),(None,None))
    P(f"   {k:7s} {l}:{d}  top={t}  all={a}")
# text labels (pin names) in top
labs = []
for li in ly.layer_indexes():
    for s in tc.shapes(li).each():
        if s.is_text(): labs.append((ly.get_info(li).to_s(), s.text.string))
P(f"text labels in top cell: {len(labs)}; layers: {sorted(set(l for l,_ in labs))}")
P("sample labels: " + str(labs[:6]))
for pn in ("VPWR","VGND","clk_i","rst_n_i"):
    P(f"  label {pn}: {[l for l,t in labs if t==pn][:6]}")
# macro boxes
srams = []
for inst in tc.each_inst():
    if "sram" in inst.cell.name.lower(): srams.append((inst.cell.name, inst.dbbox()))
P(f"top-level SRAM instances: {len(srams)}")
for n,b in srams[:12]: P(f"   {n} bbox um {b}")
if out: open(out,"w").write("\n".join(lines)+"\n")
