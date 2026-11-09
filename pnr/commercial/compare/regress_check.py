#!/usr/bin/env python3 -I
"""regress_check.py <tool: icc2|innovus> <gen: b7|b8> [baseline b6] -- every judge / sign-off / native metric in comparison.json that is WORSE in <gen> than in the baseline, grouped, plus the count of improved ones.
Worse = a violator / item count that rose, or a WNS that fell by more than 2 ps (0.002 ns).  Reads comparison.json only (never run directories).
The shared-SDC and own-SDC hold rows are the I/O-latency artefact of caveat 4 (the SDC has no per-view I/O latency): they are listed but flagged."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "comparison.json")))
tool, gen = sys.argv[1], sys.argv[2]; base = sys.argv[3] if len(sys.argv) > 3 else "b6"
A, B = f"{tool}_{base}", f"{tool}_{gen}"
worse, better, same = [], 0, 0
def cmp(name, a, b, kind, note=""):
    global better, same
    if a is None or b is None: return
    if kind == "wns":
        if b < a - 0.002: worse.append((name, a, b, note))
        elif b > a + 0.002: better += 1
        else: same += 1
    else:
        if b > a: worse.append((name, a, b, note))
        elif b < a: better += 1
        else: same += 1
for var in ("base", "own", "iolat", "iolat_pv", "iolat_pvs"):
    ja, jb = d["judge"].get(A, {}).get(var), d["judge"].get(B, {}).get(var)
    if not ja or not jb: continue
    art = " (fixed / missing I/O latency, caveat 4: not a layout measure)" if var in ("base", "own", "iolat") else ""
    for c, ra in ja["corners"].items():
        rb = jb["corners"].get(c)
        if not ra or not rb: continue
        va, vb = ra["values"], rb["values"]
        for k, kind in (("setup_wns", "wns"), ("hold_wns", "wns"), ("setup_viol", "n"), ("hold_viol", "n"), ("r2rx_setup_viol", "n"), ("r2rx_hold_viol", "n")):
            note = art if k.startswith("hold") else ""
            cmp(f"judge {var} {c} {k}", va.get(k), vb.get(k), kind, note)
da, db = (d["judge"].get(A, {}).get("drv_all_corners_base") or {}).get("values"), (d["judge"].get(B, {}).get("drv_all_corners_base") or {}).get("values")
if da and db:
    for c in da:
        for k in ("max_cap_dout0", "max_cap_other", "max_tran", "max_fanout"):
            cmp(f"judge DRV base {c} {k}", da[c][k], db[c][k], "n")
ma, mb = d["arms"][A]["metrics"], d["arms"][B]["metrics"]
for k in ("klayout_drc", "antenna_deck_nets", "antenna_deck_pins", "native_route_drc", "native_antenna", "magic_drc_outside_sram", "magic_drc_straddle_sram", "native_max_tran_viol", "native_max_cap_viol"):
    if k in ma and k in mb: cmp(f"signoff/native {k}", ma[k]["value"], mb[k]["value"], "n")
for k in ("lvs_as_delivered", "lvs_clean", "lvs_merged", "lec"):
    if k in ma and k in mb and ma[k]["value"] != mb[k]["value"]: worse.append((f"signoff {k} CHANGED", ma[k]["value"], mb[k]["value"], ""))
pa = d["judge"][A]["base"]["power"]["values"]["total_mW"]; pb = d["judge"][B]["base"]["power"]["values"]["total_mW"]
cmp("judge PrimePower nom_tt (mW)", pa, pb, "n")
print(f"### {B} vs {A}: {len(worse)} worse, {better} better, {same} equal (WNS tolerance 2 ps)\n")
grp = {}
for n, a, b, note in worse:
    key = " ".join(n.split()[:3]) if n.startswith("judge") and not n.startswith("judge DRV") and not n.startswith("judge Prime") else n
    k2 = n.split()[-1] if n.startswith("judge") else ""
    grp.setdefault((n.split()[0] + " " + (n.split()[1] if n.startswith("judge") else ""), k2, note), []).append((n, a, b))
for (g, k, note), rows in sorted(grp.items()):
    print(f"- {g} {k}{note}: {len(rows)} item(s); " + "; ".join(f"{n.replace('judge ','').replace(g,'').replace(k,'').strip() or n}: {a} -> {b}" for n, a, b in rows[:12]) + (" ..." if len(rows) > 12 else ""))
