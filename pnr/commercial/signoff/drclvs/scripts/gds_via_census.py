import pya, collections
ly = pya.Layout(); ly.read(gds); tc = ly.cell(top)
cnt = collections.Counter()
for inst in tc.each_inst():
    n = inst.cell.name
    if not n.startswith("sky130_"): cnt[n] += (inst.na * inst.nb if inst.is_regular_array() else 1)
for n, c in sorted(cnt.items(), key=lambda kv: -kv[1])[:30]:
    cl = ly.cell(n); print(f"{c:8d} {n:22s} own shapes by layer: " + " ".join(f"{ly.get_info(li).layer}:{ly.get_info(li).datatype}={cl.shapes(li).size()}" for li in ly.layer_indexes() if cl.shapes(li).size()))
