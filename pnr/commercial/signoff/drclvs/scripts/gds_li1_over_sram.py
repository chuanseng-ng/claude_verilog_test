import pya
ly = pya.Layout(); ly.read(gds); tc = ly.cell(top)
boxes = [l.split() for l in open(boxes) if l.strip()]
li = ly.find_layer(67,20)
for b in boxes:
    bx = pya.DBox(*map(float, b[1:5]))
    for s in tc.shapes(li).each_overlapping(bx.to_itype(ly.dbu)):
        bb = s.dbbox()
        print(b[0][-30:], "rel um", round(bb.left-bx.left,3), round(bb.bottom-bx.bottom,3), round(bb.right-bx.left,3), round(bb.top-bx.bottom,3), "w x h", round(bb.width(),3), round(bb.height(),3))
