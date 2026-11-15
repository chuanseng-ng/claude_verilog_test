# clip_multi.py -- KLayout: many windows out of one GDS (load once).  klayout -b -r clip_multi.py -rd gds=in.gds -rd top=rv32i_cpu_top -rd wins=windows.tsv -rd outdir=dir -rd margin=8
import pya, os
ly = pya.Layout(); ly.read(gds)
top_ci = ly.cell(top).cell_index()
m = float(margin)
for line in open(wins):
    n, x0, y0, x1, y1 = line.split()
    x0, y0, x1, y1 = float(x0) - m, float(y0) - m, float(x1) + m, float(y1) + m
    x0 = max(x0, 0.0); y0 = max(y0, 0.0)
    c = ly.clip(top_ci, pya.DBox(x0, y0, x1, y1).to_itype(ly.dbu))
    ly.cell(c).name = "clip_top"
    o = pya.SaveLayoutOptions(); o.format = 'GDS2'; o.select_all_cells(); o.clear_cells(); o.add_cell(c)
    ly.write(os.path.join(outdir, f"clip_{n}.gds"), o)
    ly.delete_cell(c)
    print("clipped", n, x0, y0, x1, y1)
