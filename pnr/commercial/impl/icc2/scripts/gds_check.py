#!/usr/bin/env python3
"""gds_check.py <gds> <top> [sram_cell] -- minimal GDSII stream reader (no external lib), integrity checks for Step B5e:
  1. structures, top cells (structures never referenced) -> must be exactly one
  2. every SREF/AREF target defined, and non-empty (an empty referenced structure = truncated/missing name)
  3. instances of the SRAM cell and whether that structure has its own geometry
  4. pin geometry: BOUNDARY count per layer:datatype in the top structure, TEXT per layer:texttype with labels
Streams the file once; keeps only per-structure counters."""
import struct, sys, collections
f = open(sys.argv[1], 'rb'); top = sys.argv[2]; sram = sys.argv[3] if len(sys.argv) > 3 else 'sky130_sram_1kbyte_1rw1r_32x256_8'
cur = None; elem = None
nelem = collections.Counter()          # structure -> own boundary/path/text count (not srefs)
nref = collections.Counter()           # structure -> number of sref/aref
refs = collections.defaultdict(collections.Counter)  # parent -> child -> n
bnd = collections.defaultdict(collections.Counter)   # structure -> (layer,dt) -> n   (only kept for top)
txt = collections.defaultdict(collections.Counter)   # structure -> (layer,tt) -> n
labels = collections.defaultdict(list)
etype = None; lay = dt = None; sname = None; strn = None; xy = None
rects = collections.defaultdict(list); tpos = []
RT = {0x0502: 'BGNSTR', 0x0606: 'STRNAME', 0x0700: 'ENDSTR', 0x0800: 'BOUNDARY', 0x0900: 'PATH', 0x0A00: 'SREF', 0x0B00: 'AREF', 0x0C00: 'TEXT',
      0x0D02: 'LAYER', 0x0E02: 'DATATYPE', 0x1206: 'SNAME', 0x1602: 'TEXTTYPE', 0x1906: 'STRING', 0x1003: 'XY', 0x1100: 'ENDEL'}
while True:
    h = f.read(4)
    if len(h) < 4: break
    n, rt = struct.unpack(">HH", h)
    if n < 4: break
    body = f.read(n - 4)
    k = RT.get(rt)
    if k == 'STRNAME': cur = body.rstrip(b'\0').decode(); nelem[cur] += 0
    elif k in ('BOUNDARY', 'PATH', 'TEXT', 'SREF', 'AREF'): etype = k; lay = dt = None; sname = None; strn = None
    elif k == 'LAYER': lay = struct.unpack('>h', body)[0]
    elif k == 'DATATYPE': dt = struct.unpack('>h', body)[0]
    elif k == 'TEXTTYPE': dt = struct.unpack('>h', body)[0]
    elif k == 'SNAME': sname = body.rstrip(b'\0').decode()
    elif k == 'STRING': strn = body.rstrip(b'\0').decode()
    elif k == 'XY': xy = struct.unpack('>%di' % (len(body) // 4), body)
    elif k == 'ENDEL':
        if etype in ('SREF', 'AREF'): nref[cur] += 1; refs[cur][sname] += 1
        elif etype == 'TEXT':
            nelem[cur] += 1; txt[cur][(lay, dt)] += 1
            if cur == top: tpos.append((lay, strn, xy[0], xy[1]))
            if cur == top and len(labels[(lay, dt)]) < 3: labels[(lay, dt)].append(strn)
        elif etype in ('BOUNDARY', 'PATH'):
            nelem[cur] += 1
            if cur == top:
                bnd[cur][(lay, dt)] += 1
                if lay in (69, 70) and etype == 'BOUNDARY' and xy and len(xy) == 10:
                    xs = xy[0::2]; ys = xy[1::2]; rects[lay].append((min(xs), min(ys), max(xs), max(ys)))
        etype = None
defined = set(nelem)
referenced = set(c for p in refs for c in refs[p])
tops = sorted(defined - referenced)
print(f"structures: {len(defined)}; top cells (never referenced): {len(tops)} {tops[:5]}")
undefined = sorted(referenced - defined)
print(f"referenced but undefined structures: {len(undefined)} {undefined[:5]}")
def own(s): return nelem[s] + nref[s]
empty = sorted(c for c in referenced if c in defined and own(c) == 0)
print(f"referenced structures that are EMPTY: {len(empty)} {empty[:5]}")
srams = [(p, n) for p in refs for c, n in refs[p].items() if c == sram]
print(f"SRAM '{sram}': defined={sram in defined} own shapes={nelem[sram]} refs={nref[sram]}; instances placed: {sum(n for _, n in srams)} (parents {[p for p,_ in srams]})")
near = sorted(c for c in referenced if c.startswith(sram[:28]) and c != sram and not c.startswith(sram + '_'))
print(f"other referenced names with the SRAM stem: {near}")
print(f"top '{top}': defined={top in defined} boundaries={sum(bnd[top].values())} texts={sum(txt[top].values())} srefs={nref[top]}")
print("top BOUNDARY by layer:datatype (only layers of interest): " + ", ".join(f"{l}:{d}={n}" for (l, d), n in sorted(bnd[top].items()) if l in (68, 69, 70, 71, 72, 67, 64)))
print("top TEXT by layer:texttype: " + ", ".join(f"{l}:{d}={n}" for (l, d), n in sorted(txt[top].items())))
for k2, v in sorted(labels.items()): print(f"  sample labels {k2}: {v}")

# pin geometry: a label sits inside a pin-size rectangle on its layer (met2 280x4000 or met3 4000x600 nm at -units 1000)
PIN = {69: (280, 4000), 70: (4000, 600)}
pinr = {l: [r for r in rects[l] if (r[2] - r[0], r[3] - r[1]) == PIN[l]] for l in PIN}
print(f"pin-size rectangles in top: met2 {len(pinr[69])}, met3 {len(pinr[70])}")
import bisect
ok = bad = 0; badl = []
for lay, name, x, y in tpos:
    if lay not in PIN: continue
    hit = any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in pinr[lay])
    if hit: ok += 1
    else: bad += 1; badl.append(name)
print(f"pin labels inside a pin rectangle: {ok}; NOT inside: {bad} {badl[:5]}")
