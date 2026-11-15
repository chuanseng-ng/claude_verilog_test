#!/usr/bin/env python3 -I
"""summarize_windows.py <outdir> <windows.tsv> <sram_boxes.txt> <margin> -> window_summary.tsv + window_by_rule.tsv.
Per window: Magic drc(full) items by rule, split into: INSIDE an SRAM footprint, STRADDLING one, OUTSIDE all SRAMs, and CLIP-EDGE (touches the clip boundary: excluded).
Items are read from <outdir>/m_<name>/reports/drc_violations.magic.rpt (um coordinates, die frame)."""
import sys, os, re, collections, glob
out, wf, sf, mg = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
srams = []
for l in open(sf):
    p = l.split(); srams.append(tuple(float(v) for v in p[-4:]))
wins = {}
for l in open(wf):
    n, *v = l.split(); wins[n] = tuple(float(x) for x in v)
rows = []; byrule = collections.defaultdict(collections.Counter)
for n, (x0, y0, x1, y1) in wins.items():
    f = f"{out}/m_{n}/reports/drc_violations.magic.rpt"
    if not os.path.isfile(f):
        rows.append((n, "NOT RUN", "", "", "", "")); continue
    cx0, cy0, cx1, cy1 = max(x0 - mg, 0.0), max(y0 - mg, 0.0), x1 + mg, y1 + mg
    cnt = collections.Counter(); rule = None
    for l in open(f):
        l = l.rstrip("\n")
        if l.startswith("-") or l.startswith("[INFO]") or not l.strip() or l == "clip_top": continue
        if l.startswith(" "):
            v = [float(t.replace("um", "")) for t in l.split()]
            cut = (cx0 > 0 and v[0] <= cx0 + .05) or (cy0 > 0 and v[1] <= cy0 + .05) or (cx1 < 3600 and v[2] >= cx1 - .05) or (cy1 < 1800 and v[3] >= cy1 - .05)
            if cut:
                cnt["edge"] += 1; continue
            ins = any(v[0] >= a - .01 and v[1] >= b - .01 and v[2] <= c + .01 and v[3] <= d + .01 for a, b, c, d in srams)
            ov = any(v[0] < c and v[2] > a and v[1] < d and v[3] > b for a, b, c, d in srams)
            k = "inside" if ins else ("straddle" if ov else "outside")
            cnt[k] += 1; byrule[rule][k] += 1
        else:
            rule = l
    rows.append((n, "ok", cnt["inside"], cnt["straddle"], cnt["outside"], cnt["edge"]))
with open(f"{out}/window_summary.tsv", "w") as fo:
    fo.write("window\tstatus\tinside_sram\tstraddle_sram\toutside_sram\tclip_edge_excluded\n")
    for r in rows: fo.write("\t".join(map(str, r)) + "\n")
with open(f"{out}/window_by_rule.tsv", "w") as fo:
    fo.write("rule\tinside\tstraddle\toutside\n")
    for r, c in sorted(byrule.items()): fo.write(f"{r}\t{c['inside']}\t{c['straddle']}\t{c['outside']}\n")
print(open(f"{out}/window_summary.tsv").read())
