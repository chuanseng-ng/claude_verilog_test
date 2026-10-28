# klayout -b -r gds_add_pins.py -rd gds=<in.gds> -rd def=<routed.def> -rd out=<out.gds> -rd top=<cell> [-rd report=<txt>]
# MEASUREMENT COPY: add the pin rectangles from the DEF PINS section to the top cell, on the pin's metal layer (met1..met5 drawing).
# Needed because ICC2 write_gds -output_pin text writes the pin NAME only: the text floats 1.7 um above the real metal stub (the pin
# rectangle, 0.28 x 4.0 um on the die edge, is in the DEF but not in the GDS), so no label touches metal and Magic extracts 503
# unconnected port nodes. The original GDS is untouched.
import pya, re
ly = pya.Layout(); ly.read(gds); tc = ly.cell(top)
LAY = {"met1": (68, 20), "met2": (69, 20), "met3": (70, 20), "met4": (71, 20), "met5": (72, 20), "li1": (67, 20)}
units = 1000; pins = []
cur = None
txt = open(globals()["def"], errors="replace")
inpins = False
for line in txt:
    m = re.match(r"^UNITS DISTANCE MICRONS (\d+)", line)
    if m: units = int(m.group(1))
    if line.startswith("PINS "): inpins = True; continue
    if line.startswith("END PINS"): break
    if not inpins: continue
    m = re.match(r"^\s*-\s+(\S+)\s", line)
    if m: cur = {"name": m.group(1), "rect": None, "at": None, "layer": None, "orient": "N"}; pins.append(cur); continue
    m = re.search(r"\+\s+LAYER\s+(\w+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)", line)
    if m and cur: cur["layer"] = m.group(1); cur["rect"] = tuple(int(m.group(i)) for i in (2, 3, 4, 5))
    m = re.search(r"\+\s+(?:FIXED|PLACED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\w+)", line)
    if m and cur: cur["at"] = (int(m.group(1)), int(m.group(2))); cur["orient"] = m.group(3)
n = 0; skipped = []
for p in pins:
    if not (p["rect"] and p["at"] and p["layer"] in LAY and p["orient"] == "N"): skipped.append(p["name"]); continue
    f = 1.0 / units / ly.dbu
    x0, y0, x1, y1 = p["rect"]; ax, ay = p["at"]
    li = ly.layer(*LAY[p["layer"]])
    tc.shapes(li).insert(pya.Box(round((ax + x0) * f), round((ay + y0) * f), round((ax + x1) * f), round((ay + y1) * f)))
    n += 1
opt = pya.SaveLayoutOptions(); opt.format = "GDS2"; opt.gds2_max_cellname_length = 32000
ly.write(out, opt)
msg = f"pin rectangles added: {n}; skipped {len(skipped)} {skipped[:5]}"
print(msg)
if globals().get("report"): open(report, "w").write(msg + "\n")
