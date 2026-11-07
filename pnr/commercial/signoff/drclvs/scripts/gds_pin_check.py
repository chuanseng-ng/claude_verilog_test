import pya
ly = pya.Layout(); ly.read(gds); tc = ly.cell(top)
lays = {(69,5):(69,20),(70,5):(70,20)}
tot = 0; nometal = 0; ex = []
for (tl, td), (ml, md) in lays.items():
    tli = ly.find_layer(tl, td); mli = ly.find_layer(ml, md)
    if tli is None: continue
    rg = pya.Region(tc.begin_shapes_rec(mli))
    for s in tc.shapes(tli).each():
        if s.is_text():
            tot += 1
            p = pya.Point(s.text.x, s.text.y)
            hit = not (rg & pya.Region(pya.Box(p.x, p.y, p.x, p.y).enlarged(1, 1))).is_empty()
            if not hit:
                nometal += 1
                if len(ex) < 5: ex.append((s.text.string, p.x * ly.dbu, p.y * ly.dbu))
print("pin texts", tot, "with NO same-layer metal at the text point:", nometal, ex)
