# klayout -b -r gds_top_over_sram.py -rd gds=<f> -rd boxes=<sram_boxes.txt> -rd top=<cell>
# Counts routing shapes that belong to the TOP cell itself (not std-cell/SRAM sub-cells) lying over each SRAM footprint, per layer.
import pya
ly = pya.Layout(); ly.read(gds); tc = ly.cell(top)
boxes = [l.split() for l in open(boxes) if l.strip()]
names = {(67,20):"li1",(68,20):"met1",(69,20):"met2",(70,20):"met3",(71,20):"met4",(72,20):"met5"}
tot = {n:0 for n in names.values()}
per = []
for b in boxes:
    bx = pya.DBox(*map(float, b[1:5]))
    row = {}
    for (l,d), n in names.items():
        li = ly.find_layer(l, d)
        if li is None: continue
        cnt = 0
        for s in tc.shapes(li).each_overlapping(pya.Box.from_dbox(bx * (1.0/ly.dbu) * ly.dbu)) if False else tc.shapes(li).each_overlapping(bx.to_itype(ly.dbu)):
            cnt += 1
        row[n] = cnt; tot[n] += cnt
    per.append((b[0][-34:], row))
for n, r in per: print(n, r)
print("TOTAL top-cell shapes overlapping SRAM footprints:", tot)
