# clip_gds.py -- KLayout: clip a window out of a layout GDS into a small GDS (hierarchy kept), for Magic nwell.4 mode A/B tests.
#   klayout -b -r clip_gds.py -rd gds=in.gds -rd top=rv32i_cpu_top -rd box=x0,y0,x1,y1 (um) -rd name=clip_top -rd out=out.gds
import pya
ly = pya.Layout(); ly.read(gds)
x0, y0, x1, y1 = [float(v) for v in box.split(',')]
c = ly.clip(ly.cell(top).cell_index(), pya.DBox(x0, y0, x1, y1).to_itype(ly.dbu))
ly.cell(c).name = name
o = pya.SaveLayoutOptions(); o.format = 'GDS2'; o.select_all_cells(); o.clear_cells(); o.add_cell(c)
ly.write(out, o)
print('clipped', box, '->', out)
