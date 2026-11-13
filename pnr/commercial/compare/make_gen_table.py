#!/usr/bin/env python3 -I
"""make_gen_table.py [arm_b6 arm_b7 arm_b8 ...] -- markdown table of the key metrics of the b6 / b7 / b8 / b9 generations of one commercial arm, from comparison.json (never from run dirs).
    python3 -I pnr/commercial/compare/make_gen_table.py icc2     |  ... innovus
Rows are produced from the JSON only, so the doc section 4.9 can be regenerated after every compare.py run."""
import json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "comparison.json")))
tool = sys.argv[1] if len(sys.argv) > 1 else "icc2"
arms = [f"{tool}_b6", f"{tool}_b7", f"{tool}_b8", f"{tool}_b9", f"{tool}_b10", f"{tool}_b11"]
arms = [a for a in arms if a in d["arms"] and "base" in (d["judge"].get(a) or {})]
def S(a, var, k):
    try: return d["judge"][a][var]["summary"]["values"][k]
    except Exception: return None
def M(a, k):
    try: return d["arms"][a]["metrics"][k]["value"]
    except Exception: return None
def DRV(a, kind, corners=None):
    try: v = d["judge"][a]["drv_all_corners_base"]["values"]
    except Exception: return None
    return [v[c][kind] for c in (corners or v)]
def fmt(x, nd=3):
    if x is None: return "-"
    if isinstance(x, float): return f"{x:.{nd}f}"
    return str(x)
rows = []
def row(name, f): rows.append((name, [f(a) for a in arms]))
for var, lab in (("base", "shared SDC"), ("iolat_pv", "per-view iolat SDC"), ("own", "own SDC")):
    row(f"judge {lab}: worst setup WNS (ns) / setup violators, 9 corners", lambda a, v=var: f"{fmt(S(a, v, 'setup_wns_worst'))} / {fmt(S(a, v, 'setup_viol_sum'))}")
    row(f"judge {lab}: worst hold WNS (ns) / hold violators, 9 corners", lambda a, v=var: f"{fmt(S(a, v, 'hold_wns_worst'))} / {fmt(S(a, v, 'hold_viol_sum'))}")
row("judge reg-to-reg setup / hold violators, 9 corners (shared SDC)", lambda a: f"{fmt(S(a, 'base', 'r2r_setup_viol_sum'))} / {fmt(S(a, 'base', 'r2r_hold_viol_sum'))}")
row("judge SRAM dout0 max-cap pins, nom_tt / worst corner", lambda a: (lambda l: f"{l[0]} / {max(l)}" if l else "-")(DRV(a, "max_cap_dout0")))
row("judge max-cap pins other than dout0, worst corner", lambda a: (lambda l: str(max(l)) if l else "-")(DRV(a, "max_cap_other")))
row("judge max-tran pins, nom_tt / worst corner", lambda a: (lambda l: f"{l[0]} / {max(l)}" if l else "-")(DRV(a, "max_tran")))
row("judge PrimePower nom_tt (mW)", lambda a: fmt((d["judge"][a]["base"].get("power") or {}).get("values", {}).get("total_mW"), 2))
row("native routed DRC / native antenna (tool rule)", lambda a: f"{fmt(M(a, 'native_route_drc'))} / {fmt(M(a, 'native_antenna'))}")
row("signoff KLayout DRC items", lambda a: fmt(M(a, "klayout_drc")))
row("signoff deck antenna nets", lambda a: fmt(M(a, "antenna_deck_nets")))
row("signoff Netgen LVS (GDS, as delivered)", lambda a: fmt(M(a, "lvs_as_delivered")))
row("signoff LEC (positive / negative controls)", lambda a: fmt(M(a, "lec")))
row("signoff Magic (std cells from GDS): inside SRAM / straddle / outside", lambda a: f"{fmt(M(a, 'magic_drc_inside_sram'))} / {fmt(M(a, 'magic_drc_straddle_sram'))} / {fmt(M(a, 'magic_drc_outside_sram'))}")
row("derived logical cells", lambda a: fmt((d['arms'][a]['metrics'].get('census') or {}).get('values', {}).get('logical_cells')))
print("| metric | " + " | ".join(d["arms"][a]["name"] for a in arms) + " |")
print("|---|" + "---|" * len(arms))
for n, v in rows:
    print(f"| {n} | " + " | ".join(v) + " |")
