# klayout -b -r gds_pin_ports.py -rd gds=<f> -rd top=<cell> -rd out=<pin_ports.tcl>
# Writes one `findlabel NAME; port make` per pin text of the top cell: Magic does not flag GDS text as ports by itself, and a top
# subckt with no port-flagged labels has no pins. (`port makeall` silently does nothing for GDS text; findlabel + port make works.)
import pya
ly = pya.Layout(); ly.read(gds); tc = ly.cell(top)
lay = {(69, 5): "m2", (70, 5): "m3", (68, 5): "m1", (71, 5): "m4", (72, 5): "m5", (67, 5): "li"}
n = 0
names = []
with open(out, "w") as o:
    o.write("# pin ports from GDS text (um)\nset ::pin_n 0\nset ::pin_err 0\n")
    for li in ly.layer_indexes():
        i = ly.get_info(li)
        if (i.layer, i.datatype) not in lay: continue
        for s in tc.shapes(li).each():
            if s.is_text():
                x, y = s.text.x * ly.dbu, s.text.y * ly.dbu
                o.write(f"if {{[catch {{findlabel {{{s.text.string}}}; port make}}]}} {{incr ::pin_err}} else {{incr ::pin_n}}\n")
                n += 1; names.append(s.text.string)
    o.write('puts "pin ports made: $::pin_n, errors: $::pin_err"\n')
print("pin texts:", n)

open(out + ".names", "w").write("\n".join(names) + "\n")
