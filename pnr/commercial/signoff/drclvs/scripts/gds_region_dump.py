import pya
ly = pya.Layout(); ly.read(gds)
top = ly.top_cell()
x1,y1,x2,y2 = [float(v) for v in box.split(',')]
ln, dt = [int(v) for v in layer.split('/')]
li = ly.layer(ln, dt)
reg = pya.Region(top.begin_shapes_rec_touching(li, pya.Box(int(x1*1000),int(y1*1000),int(x2*1000),int(y2*1000))))
reg.merge()
for p in reg.each():
    b = p.bbox()
    print("poly bbox um: %.3f %.3f %.3f %.3f  w=%.3f h=%.3f npts=%d" % (b.left/1000,b.bottom/1000,b.right/1000,b.top/1000,b.width()/1000,b.height()/1000,p.num_points()))
