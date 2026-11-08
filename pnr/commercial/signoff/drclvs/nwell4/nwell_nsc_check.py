# nwell_nsc_check.py -- independent geometric check of Magic's nwell.4 on the REAL std-cell GDS geometry (KLayout, run with
#   klayout -b -r nwell_nsc_check.py -rd gds=<gds> -rd boxes=<sram_boxes.txt> -rd top=rv32i_cpu_top -rd out=<report>).
# Magic nwell.4 (sky130A.tech, 'variants (full)'): nwell_missing_tap = nwell AND-NOT bloat-all(nsc, nwell), i.e. an nwell region with no
# n-substrate contact (licon1 on a tap/diff that is inside nsdm). This script applies the same definition to the flattened GDS:
#   nsc = licon1 & (tap & nsdm);  report every merged nwell region that does not interact with any nsc.
import pya, sys
gds = globals().get('gds'); boxes = globals().get('boxes'); top = globals().get('top', 'rv32i_cpu_top'); out = globals().get('out')
ly = pya.Layout(); ly.read(gds)
tc = ly.cell(top)
def L(l, d): return ly.find_layer(l, d)
def reg(l, d):
    i = L(l, d)
    return pya.Region(tc.begin_shapes_rec(i)) if i is not None else pya.Region()
nwell = reg(64, 20); tap = reg(65, 44); nsdm = reg(93, 44); licon = reg(66, 44)
nsc = licon & (tap & nsdm)
nw = nwell.merged()
bad = nw.not_interacting(nsc)
bx = []
for l in open(boxes):
    v = l.split(); bx.append(tuple(float(t) for t in v[-4:]))
def in_sram(p):
    b = p.bbox(); x0, y0, x1, y1 = b.left / 1000., b.bottom / 1000., b.right / 1000., b.top / 1000.
    for (a0, b0, a1, b1) in bx:
        if x0 >= a0 - .01 and y0 >= b0 - .01 and x1 <= a1 + .01 and y1 <= b1 + .01: return 'inside'
    for (a0, b0, a1, b1) in bx:
        if x1 > a0 and x0 < a1 and y1 > b0 and y0 < b1: return 'straddle'
    return 'outside'
cnt = {'inside': 0, 'straddle': 0, 'outside': 0}; samples = []
for p in bad.each():
    c = in_sram(p); cnt[c] += 1
    if c != 'inside' and len(samples) < 50:
        b = p.bbox(); samples.append((c, b.left / 1000., b.bottom / 1000., b.right / 1000., b.top / 1000.))
f = open(out, 'w')
f.write('gds=%s\nnwell_shapes_merged_regions=%d\nnsc_polygons=%d\nnwell_regions_without_nsc: total=%d inside_sram=%d straddle=%d outside=%d\n' %
        (gds, nw.count(), nsc.merged().count(), bad.count(), cnt['inside'], cnt['straddle'], cnt['outside']))
for s in samples: f.write('sample %s %.3f %.3f %.3f %.3f\n' % s)
# also: total merged nwell regions that are NOT in an SRAM box (for scale)
tot = {'inside': 0, 'straddle': 0, 'outside': 0}
for p in nw.each(): tot[in_sram(p)] += 1
f.write('all_merged_nwell_regions: inside=%d straddle=%d outside=%d\n' % (tot['inside'], tot['straddle'], tot['outside']))
f.close(); print(open(out).read())
