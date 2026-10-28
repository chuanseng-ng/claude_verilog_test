#!/usr/bin/env python3
"""def_stats.py <routed.def> <out.json> -- per-layer wirelength and same-layer neighbour-spacing mix of a routed DEF.

For every straight segment (width = layer min width) the fraction of its length with a same-layer neighbour on the
adjacent track(s): classes by the nearest neighbour on EACH side: 1 = adjacent track (min spacing), 2 = two tracks over,
3 = three or more tracks over / none.  Result is the weight table used to weight the pattern fit by the real design.
"""
import re, sys, json, collections
import numpy as np
LAY = ["li1", "met1", "met2", "met3", "met4", "met5"]
def parse(path):
    segs = {l: [] for l in LAY}
    lay = None
    tok = re.compile(r"\(\s*(-?\d+|\*)\s+(-?\d+|\*)\s*\)|(\w+)")
    in_nets = False
    for line in open(path):
        if line.startswith("NETS "): in_nets = True; continue
        if line.startswith("END NETS"): break
        if not in_nets: continue
        pts = []
        lay = None
        px = py = None
        for m in tok.finditer(line):
            if m.group(3) is not None:
                w = m.group(3)
                if w in segs: lay = w; pts = []
                continue
            x, y = m.group(1), m.group(2)
            x = px if x == "*" else int(x); y = py if y == "*" else int(y)
            px, py = x, y
            pts.append((x, y))
            if len(pts) == 2 and lay:
                (x0, y0), (x1, y1) = pts
                if y0 == y1 and x0 != x1: segs[lay].append(("H", y0, min(x0, x1), max(x0, x1)))
                elif x0 == x1 and y0 != y1: segs[lay].append(("V", x0, min(y0, y1), max(y0, y1)))
                pts = [pts[1]]
        # note: a net continues across lines only via NEW; layer carries over on the same line
    return segs
def mix(segs, lay, pitch_um, res=0.05):
    """returns total length (um), and fractions for left/right classes 1,2,3"""
    dirs = collections.Counter(s[0] for s in segs[lay])
    if not dirs: return 0.0, {}
    d = dirs.most_common(1)[0][0]
    ss = [s for s in segs[lay] if s[0] == d]
    p = int(round(pitch_um * 1000))
    tracks = collections.defaultdict(list)
    for _, c, a, b in ss: tracks[c].append((a, b))
    cs = sorted(tracks)
    # map coordinate -> track index via modular snapping to pitch grid of first coordinate
    off = cs[0] % p
    idx = {c: int(round((c - off) / p)) for c in cs}
    occ = collections.defaultdict(list)
    for c in cs: occ[idx[c]].extend(tracks[c])
    def cover(i):   # merged intervals of track i
        iv = sorted(occ.get(i, []))
        out = []
        for a, b in iv:
            if out and a <= out[-1][1]: out[-1][1] = max(out[-1][1], b)
            else: out.append([a, b])
        return out
    def overlap_len(A, B):
        i = j = 0; tot = 0
        while i < len(A) and j < len(B):
            lo = max(A[i][0], B[j][0]); hi = min(A[i][1], B[j][1])
            if hi > lo: tot += hi - lo
            if A[i][1] < B[j][1]: i += 1
            else: j += 1
        return tot
    cnt = collections.Counter(); total = 0
    for i in sorted(occ):
        A = cover(i); L = sum(b - a for a, b in A)
        if L == 0: continue
        total += L
        # each side: length with neighbour at +-1, else at +-2, else none
        for sgn in (-1, 1):
            n1 = overlap_len(A, cover(i + sgn)); n2 = overlap_len(A, cover(i + 2 * sgn))
            c1 = n1; c2 = max(0, min(L - n1, n2)); c3 = max(0, L - c1 - c2)
            cnt["1"] += c1; cnt["2"] += c2; cnt["3"] += c3
    tot_sides = 2 * total
    return total / 1000.0, {k: cnt[k] / tot_sides for k in ("1", "2", "3")}
if __name__ == "__main__":
    segs = parse(sys.argv[1])
    pitch = {"li1": 0.46, "met1": 0.34, "met2": 0.46, "met3": 0.68, "met4": 0.92, "met5": 3.4}
    out = {}
    for l in LAY:
        L, m = mix(segs, l, pitch[l])
        out[l] = {"length_um": L, "side_mix": m}
        print(l, "length %.0f um" % L, m)
    json.dump(out, open(sys.argv[2], "w"), indent=1)
