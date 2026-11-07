# klayout -b -r gds_cell_layers.py -rd gds=<f> -rd cell=<name>: per layer:datatype, shape counts (own shapes summed over the cell's
# unique descendant tree, plus recursive flat count) -> compare the SRAM macro content between GDS files.
import pya
ly = pya.Layout(); ly.read(gds)
c = ly.cell(cell)
print(f"{gds}\n cell {cell}: found={c is not None} bbox={c.dbbox() if c else None}  subcells={len(list(c.called_cells()))}")
tree = [c.cell_index()] + list(c.called_cells())
tot = {}
for li in ly.layer_indexes():
    i = ly.get_info(li); n = sum(ly.cell(ci).shapes(li).size() for ci in tree)
    if n: tot[(i.layer, i.datatype)] = n
print(" own-shape counts per layer:datatype: " + " ".join(f"{l}:{d}={n}" for (l, d), n in sorted(tot.items())))
print(" total own shapes:", sum(tot.values()))
