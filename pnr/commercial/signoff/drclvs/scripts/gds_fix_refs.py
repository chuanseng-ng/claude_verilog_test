# gds_fix_refs.py -- derive a *measurement copy* of a GDS whose instances reference EMPTY, name-truncated structures.
#   klayout -b -r gds_fix_refs.py -rd gds=<in.gds> -rd out=<fixed.gds> -rd top=<top> [-rd report=<txt>]
# Defect class (ICC2 write_gds, found on b5a_icc2): a structure name longer than 32 characters is shortened to 32 with a
# "_<n>" uniquifier ("sky130_sram_1kbyte_1rw1r_32x256_8" (33) -> "sky130_sram_1kbyte_1rw1r_32x25_0"); the top cell instantiates
# the shortened (empty) name, while the merged macro GDS keeps its full-length name, unreferenced.
# Repair rule (generic, evidence-based): an empty structure E reachable from top is re-pointed to the unique non-empty structure R
# that is a ROOT structure (no parents; the merged-in macro GDS top) with R.name.startswith(stem), stem = E.name without the trailing _<n>.
# Second step: orphan roots are pruned so the file has exactly one top cell. Instance transformations are untouched. The original GDS file is never modified.
import pya, re
top = globals().get("top", "rv32i_cpu_top")
rep = []
def P(s): rep.append(s); print(s)
ly = pya.Layout(); ly.read(gds)
tc = ly.cell(top)
def empty(c): return c.bbox().empty() and c.child_instances() == 0
reach = set(); stack = [tc.cell_index()]
while stack:
    ci = stack.pop()
    for ch in ly.cell(ci).each_child_cell():
        if ch not in reach: reach.add(ch); stack.append(ch)
empties = [ly.cell(i) for i in reach if empty(ly.cell(i))]
P(f"empty structures reachable from {top}: {[c.name for c in empties]}")
fixed = 0
for e in empties:
    m = re.match(r"^(.*)_[0-9]+$", e.name)
    stem = m.group(1) if m else e.name
    cands = [c for c in ly.each_cell() if c.name != e.name and len(c.name) > len(e.name) and c.name.startswith(stem) and not empty(c) and c.parent_cells() == 0]
    P(f"  {e.name}: stem={stem!r} candidates={[c.name for c in cands]}")
    if len(cands) != 1: P("  -> ambiguous or none, NOT repaired"); continue
    r = cands[0]
    n = 0
    for pc in list(e.each_parent_cell()):
        pcell = ly.cell(pc)
        for inst in list(pcell.each_inst()):
            if inst.cell_index == e.cell_index():
                inst.cell_index = r.cell_index(); n += 1
    P(f"  -> {n} instances re-pointed to {r.name} (bbox um {r.dbbox()})")
    fixed += n
    e.delete()
# prune orphan root structures (ICC2 merges the WHOLE std-cell + SRAM GDS libraries, so ~400 unreferenced cells become extra
# top cells; KLayout's sky130A_mr.drc requires a single top cell). Cells reachable from top are untouched.
orph = [c.cell_index() for c in ly.each_cell() if c.name != top and c.parent_cells() == 0]
P(f"orphan root structures pruned: {len(orph)} (cells in file before: {ly.cells()})")
for ci in orph:
    if ly.is_valid_cell_index(ci): ly.prune_cell(ci, -1)
P(f"cells after prune: {ly.cells()}; top cells: {[c.name for c in ly.top_cells()]}")
empties2 = [c.name for c in ly.each_cell() if c.name != top and empty(c) and c.cell_index() in reach]
opt = pya.SaveLayoutOptions(); opt.format = "GDS2"; opt.gds2_max_cellname_length = 32000; opt.gds2_libname = "LIB"
ly.write(out, opt)
P(f"wrote {out}; instances repaired={fixed}")
if globals().get("report"): open(report, "w").write("\n".join(rep) + "\n")
