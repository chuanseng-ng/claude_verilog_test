#!/usr/bin/env python3
"""mk_cell_netlist.py <out.sp> <cell> [<cell> ...] -- extract the named hd/ef std-cell subckts from the open_pdks spice libraries into one HSPICE-readable file.

Only change to the netlist text: numbers written with a `u` suffix (e.g. `w=870000u`, `l=1e+06u`) are rewritten as plain numbers.  Those cell files rely on ngspice
reading `870000u` as 0.87 and `1e+06u` as 1.0 (units: um, through `.option scale=1u`).  HSPICE ignores the letters after an exponent (`1e+06u` -> 1e6), so the
suffix is resolved here to a plain micrometre number; mk_hspice_models.py then applies the um -> m scaling inside the model wrapper.
"""
import os, re, sys
out, cells = sys.argv[1], sys.argv[2:]
pdk = os.environ.get("SKY130A", os.path.expanduser("~/pdk/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A"))
src = [pdk + "/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"] + [pdk + "/libs.ref/sky130_fd_sc_hd/spice/sky130_ef_sc_hd__decap_12.spice"]
blocks = {}
for p in src:
    cur = None
    for line in open(p):
        m = re.match(r"^\.subckt\s+(\S+)", line, re.I)
        if m: cur = m.group(1); blocks[cur] = []
        if cur is not None: blocks[cur].append(line)
        if re.match(r"^\.ends", line, re.I): cur = None
num = re.compile(r"(?<![A-Za-z_])([A-Za-z]+)=([0-9.]+(?:[eE][+-]?[0-9]+)?)u\b")
def fix(line):
    return num.sub(lambda m: "%s=%.10g" % (m.group(1), float(m.group(2)) * 1e-6), line)
with open(out, "w") as f:
    f.write("* extracted from open_pdks sky130A sc_hd spice; `u`-suffixed numbers resolved to plain um numbers (see mk_cell_netlist.py)\n")
    for c in cells:
        if c not in blocks: raise SystemExit("cell %s not found" % c)
        f.write("".join(fix(l) for l in blocks[c]) + "\n")
print("wrote %s (%d cells)" % (out, len(cells)))
