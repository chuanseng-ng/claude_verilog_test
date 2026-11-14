#!/usr/bin/env python3 -I
"""make_final_tables.py [section ...] -- the tables of sections 4.1 to 4.7 of docs/COMMERCIAL_FLOW_COMPARISON.md for the FINAL arms (OpenROAD B2 plus the arm of each commercial tool whose
`role` is "final" in comparison.json, i.e. compare.py FINAL_GEN_ICC2 / FINAL_GEN_INN), deterministic from comparison.json only (no run directory is read).
Sections: base iolat iolat_pv iolat_pvs own latency power native physical cost.  With no argument all sections are printed, each between `<!-- FINAL-TABLE name -->` markers.
update_doc_tables.py substitutes the marked blocks of the document with the output of this script.  A value the final generation did not re-measure (RedHawk) is printed as the b6 value
and flagged in the cell; a value that does not exist is printed `n/a`."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "comparison.json")))
CORNERS = [f"{rc}_{lib}" for rc in ("nom", "min", "max") for lib in ("tt", "ss", "ff")]


def final_arms():
    out = ["openroad_b2"]
    for tool in ("icc2", "innovus"):
        for k, a in D["arms"].items():
            if k.startswith(tool + "_") and a["role"] == "final":
                out.append(k)
    return out


ARMS = final_arms()


def nm(k):
    return D["arms"][k]["name"].replace("OpenROAD/LibreLane B2", "OpenROAD B2")


def tool_of(k):
    return k.split("_")[0]


def b6_of(k):
    return {"icc2": "icc2_b6", "innovus": "innovus_b6", "openroad": "openroad_b2"}[tool_of(k)]


def z(x):
    return 0.0 if abs(x) < 0.005 else x


def cell(v):
    return f"{v['setup_wns']:+.3f} / {z(v['setup_tns']):.2f} / {int(v['setup_viol'])} ; {v['hold_wns']:+.3f} / {z(v['hold_tns']):.2f} / {int(v['hold_viol'])}"


def judge_table(var, arms=None):
    arms = [a for a in (arms or ARMS) if var in D["judge"].get(a, {})]
    rows = ["| corner | " + " | ".join(nm(a) for a in arms) + " |", "|---|" + "---|" * len(arms)]
    for c in CORNERS:
        rows.append(f"| {c} | " + " | ".join(cell(D["judge"][a][var]["corners"][c]["values"]) for a in arms) + " |")
    return "\n".join(rows)


def latency():
    rows = ["| corner | " + " | ".join(nm(a) for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for c in CORNERS:
        cs = []
        for a in ARMS:
            v = D["clock_latency"]["measured"][a][c]["values"]
            cs.append(f"{v['all_mean']:.3f} ({v['all_min']:.2f}..{v['all_max']:.2f})")
        rows.append(f"| {c} | " + " | ".join(cs) + " |")
    return "\n".join(rows)


def power():
    ks = (("total", "total_mW"), ("clock network", "clock_network_mW"), ("combinational", "combinational_mW"), ("register", "register_mW"), ("memory (10 SRAM)", "memory_mW"))
    rows = ["| | " + " | ".join(nm(a) for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for lab, k in ks:
        rows.append(f"| {lab} | " + " | ".join(f"{D['judge'][a]['base']['power']['values'][k]:.1f}" for a in ARMS) + " |")
    return "\n".join(rows)


def M(a, k, default=None):
    m = D["arms"][a]["metrics"].get(k)
    return default if m is None else m.get("value", default)


def n(x, f="{:,}"):
    return "n/a" if x is None else f.format(x)


def native():
    def orr(a):
        g = lambda k: M(a, k)  # noqa: E731
        return [
            f"nom_tt {g('native_setup_wns_nom_tt'):+.3f}; worst over 9 corners {g('native_setup_ws_all_corners'):.3f} ({g('native_setup_viol_all_corners'):,} viol., {g('native_setup_r2r_viol_all_corners'):,} r2r)",
            f"nom_tt {g('native_hold_wns_nom_tt'):+.3f} ({g('native_hold_viol_nom_tt')}); worst {g('native_hold_ws_all_corners'):.3f} ({g('native_hold_viol_all_corners'):,}, {g('native_hold_r2r_viol_all_corners')} r2r)",
            str(g("native_route_drc")), f"(deck: {g('antenna_deck_nets')} nets)",
            f"nom_tt max_slew {g('native_max_slew_viol_nom_tt'):,} / max_cap {g('native_max_cap_viol_nom_tt'):,} / max_fanout {g('native_max_fanout_viol_nom_tt'):,} pins",
            f"{g('native_power_mW'):.2f} (OpenSTA, default activity)", f"{g('native_stdcell_area_um2'):,.0f} (incl. tap/decap/diode)",
            f"{g('native_util')*100:.1f} % (std + macro) / {g('native_util_stdcell')*100:.1f} % std", f"PSM worst VPWR drop {g('native_ir_drop_worst_V')*1000:.2f} mV",
        ]

    def icc(a):
        g = lambda k: M(a, k)  # noqa: E731
        s, t, h, ht = g("native_setup_func_ss"), g("native_setup_func_tt"), g("native_hold_func_ff"), g("native_hold_func_tt")
        so = g("native_shorts_opens") or ["n/a", "n/a"]
        return [
            f"func_ss {s['wns']:+.2f} ({s['nve']}, TNS {s['tns']:.2f}); func_tt {t['wns']:+.2f}", f"func_ff {h['wns']:.2f} ({h['nve']}); func_tt {ht['wns']:+.2f}",
            f"{g('native_route_drc')} (shorts {so[0]}, opens {so[1]})", f"{g('native_antenna')} (lenient ICC2 rule)",
            f"max_tran {g('native_max_tran_viol')} / max_cap {g('native_max_cap_viol')} nets", f"{g('native_power_mW')} (func_tt)",
            f"{g('native_stdcell_area_um2'):,.0f} (comb + noncomb)", f"{g('native_util')*100:.2f} % site-row", "not run",
        ]

    def inn(a):
        g = lambda k: M(a, k)  # noqa: E731
        s, so, h, ho = g("native_setup"), g("native_setup_sioff"), g("native_hold"), g("native_hold_sioff")
        return [
            f"all views {s['wns_all']:+.3f} ({s['viol_all']}; r2r {s['wns_r2r']:+.3f}, {s['viol_r2r']}); SI off {so['wns_all']:+.3f} ({so['viol_all']}, r2r {so['viol_r2r']})",
            f"all views {h['wns_all']:+.3f} ({h['viol_all']}); SI off {ho['wns_all']:+.3f}", n(g("native_route_drc")) + (" (see 4.9)" if g("native_route_drc") is None else ""),
            f"{g('native_antenna')} (verifyProcessAntenna, no side area)", f"max_cap {g('native_max_cap_viol')} / max_tran {g('native_max_tran_viol')} / max_fanout {g('native_max_fanout_viol')} nets",
            f"{g('native_power_mW'):.2f} (av_ss view, activity 0.1; not comparable)", f"{g('native_total_area_incl_macros_um2'):,.0f} incl. SRAM (report_area)", f"{g('native_util')*100:.1f} % density", "not run",
        ]

    fn = {"openroad": orr, "icc2": icc, "innovus": inn}
    cols = [fn[tool_of(a)](a if tool_of(a) != "openroad" else a) for a in ARMS]
    heads = {"openroad": "OpenROAD B2 (OpenSTA + OpenRCX)", "icc2": "(report_qor, TLU+)", "innovus": "(timeDesign, captbl6, SI on)"}
    hd = [heads["openroad"]] + [f"{nm(a)} {heads[tool_of(a)]}" for a in ARMS[1:]]
    labs = ["setup WNS", "hold WNS", "route DRC", "native antenna", "DRV", "power (mW)", "std-cell area (tool definition, um2)", "util (tool definition)", "IR (native)"]
    rows = ["| native | " + " | ".join(hd) + " |", "|---|" + "---|" * len(ARMS)]
    for i, lab in enumerate(labs):
        rows.append(f"| {lab} | " + " | ".join(c[i] for c in cols) + " |")
    return "\n".join(rows)


def lvs(a):
    m = D["arms"][a]["metrics"]
    if "lvs_errors" in m:
        return f"{m['lvs_errors']['value']} errors (LibreLane, DEF/LEF mode)"
    v = m["lvs_as_delivered"]
    return f"{v['nets'][0]:,} / {v['nets'][1]:,} nets, devices {v['devices'][0]:,} / {v['devices'][1]:,}: {v['value']} (as delivered); clean: {m['lvs_clean']['value']}; merged: {m['lvs_merged']['value']}"


def physical():
    def red(a, k, f):
        v = M(a, k)
        if v is not None:
            return f.format(v)
        v6 = M(b6_of(a), k)
        return "n/a" if v6 is None else f.format(v6) + "*"

    def lecs(a):
        s = D["arms"][a].get("synthesis_metrics", {}).get("synth_lec")
        if not s:
            return "not run"
        return "; ".join(f"{k}: {v['value']}" + (f" ({v['passing']:,} / {v['failing']})" if "passing" in v else f" ({v['compare_points']:,} points)" if "compare_points" in v else "") for k, v in s.items())

    ci = lambda a, k: D["arms"][a]["metrics"]["census"]["values"][k]  # noqa: E731
    rows = [
        ("logical cells / flops / buffers / inverters (derived)", lambda a: f"{ci(a,'logical_cells'):,} / {ci(a,'flops'):,} / {ci(a,'buffers'):,} / {ci(a,'inverters'):,}"),
        ("buffer area (um2, derived)", lambda a: f"{ci(a,'buffer_area_um2'):,.0f}"),
        ("antenna diodes in netlist", lambda a: f"{ci(a,'diodes'):,}"),
        ("KLayout DRC (items)", lambda a: str(M(a, "klayout_drc"))),
        ("Netgen LVS", lvs),
        ("deck antenna nets / pins", lambda a: f"{M(a,'antenna_deck_nets')} / {M(a,'antenna_deck_pins')}"),
        ("Magic total / inside SRAM", lambda a: f"{M(a,'magic_drc_total'):,} / {M(a,'magic_drc_inside_sram'):,}"),
        ("Magic straddle / outside (all `nwell.4`; LEF-abstract artefact, 0 n-well regions without tap contact in the real GDS)", lambda a: f"{M(a,'magic_drc_straddle_sram'):,} / {M(a,'magic_drc_outside_sram'):,}"),
        ("LEC post-route", lambda a: str(M(a, "lec"))),
        ("LEC synthesis netlist vs RTL", lecs),
        ("RedHawk static VPWR / VGND worst (mV)", lambda a: red(a, "ir_static_vpwr_drop_mV", "{}") + " / " + red(a, "ir_static_vgnd_bounce_mV", "{}")),
        ("RedHawk static EM violations", lambda a: red(a, "ir_static_em_violations", "{}")),
        ("RedHawk dynamic worst avgTW / minWC / mean avgTW (mV)", lambda a: " / ".join(red(a, k, "{}") for k in ("ir_dynamic_worst_avgTW_mV", "ir_dynamic_worst_minWC_mV", "ir_dynamic_mean_avgTW_mV"))),
        ("RedHawk dynamic, instances above 5 % VDD", lambda a: red(a, "ir_dynamic_frac_gt5pct", "{:.2%}")),
        ("RedHawk dynamic with no decap, worst avgTW (mV)", lambda a: red(a, "ir_dynamic_nodecap_worst_avgTW_mV", "{}")),
        ("decap instances seen by RedHawk", lambda a: red(a, "ir_dynamic_decap_instances", "{:,}")),
    ]
    t = ["| | " + " | ".join(nm(a) for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for lab, f in rows:
        t.append(f"| {lab} | " + " | ".join(f(a) for a in ARMS) + " |")
    txt = "\n".join(t)
    if "*" in txt:
        txt += "\n\n\\* b6 value of the same tool: RedHawk was not re-run on the final generation (section 7 item 8, pending)."
    return txt


def cost():
    def sy(a, k):
        if a == "openroad_b2":
            return M(a, "synth_runtime_s") if k == "synth_runtime" else None
        s = D["arms"][a].get("synthesis_metrics", {}).get(k)
        return s["value"] if s else None

    rows = [
        ("synthesis wall (s)", lambda a: n(sy(a, "synth_runtime"), "{:,}")),
        ("synthesis peak RSS (GB)", lambda a: n(sy(a, "synth_peak_rss"), "{}")),
        ("P&R wall (s, sum of the stages of the final chain, derived)", lambda a: n(M(a, "runtime_pnr_s"), "{:,}")),
        ("P&R peak RSS (GB, max over stages)", lambda a: n(M(a, "peak_rss"), "{}")),
        ("full LibreLane flow incl. sign-off (s)", lambda a: n(M(a, "runtime_total_flow_s"), "{:,}")),
    ]
    t = ["| | " + " | ".join(nm(a) for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for lab, f in rows:
        t.append(f"| {lab} | " + " | ".join(f(a) for a in ARMS) + " |")
    return "\n".join(t)


def pvsum():
    def sm(a, var):
        return D["judge"][a][var]["summary"]["values"]

    rows = []
    for lab, var in (("fixed iolat", "iolat"), ("**per-view iolat**", "iolat_pv"), ("shared latency per corner (4.2e)", "iolat_pvs"), ("**SoC-context input budgets (4.2f)**", "soc_budget")):
        for kind in ("setup", "hold"):
            def c(a, var=var, kind=kind):
                v = sm(a, var)
                tot, r2r = v[f"{kind}_viol_sum"], v[f"r2r_{kind}_viol_sum"]
                return f"{tot - r2r:,} / {r2r:,}"
            rows.append((f"{kind}, {lab} (I/O / reg-to-reg)", c))
    t = ["| | " + " | ".join(nm(a) for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    for lab, f in rows:
        t.append(f"| {lab} | " + " | ".join(f(a) for a in ARMS) + " |")
    return "\n".join(t)


STARTPOINTS = {
    "awready": "reset synchroniser flop `u_s_rst_sync_sync_q_reg_1_`", "wready": "reset synchroniser flop", "arready": "reset synchroniser flop",
    "bresp": "`u_b_fifo_rd_bin_q` (8:1 read mux)", "bvalid": "`u_b_fifo_empty_q`", "rdata": "`u_r_fifo_rd_bin_q` (8:1 read mux)", "rresp": "`u_r_fifo_rd_bin_q`",
    "rlast": "`u_r_fifo_rd_bin_q`", "rvalid": "`u_r_fifo_empty_q`", "paddr": "`cmd_paddr_cap_q`", "psel": "`d_state_q`", "penable": "`d_state_q`", "pwrite": "`cmd_pwrite_cap_q`", "pwdata": "`cmd_pwdata_cap_q`",
}


def soc_budget_table():
    ev = D["clock_latency"]["tables"]["soc_budget"]["values"]
    rows = ["| group (bits) | startpoint (SoC side) | tt: arrival / budget | ss: arrival / budget | ff: arrival / budget | current SDC delay |", "|---|---|---|---|---|---|"]
    for g, st in STARTPOINTS.items():
        cs = []
        for lib in ("tt", "ss", "ff"):
            e = ev[lib][g]
            cs.append(f"{e['arrival_ns']:.2f} / {e['budget_ns']:.1f}" + (" (capped)" if e["note"].startswith("kept") else ""))
        rows.append(f"| {g} ({ev['tt'][g]['bits']}) | {st} | " + " | ".join(cs) + f" | {ev['tt'][g]['current_ns']:.1f} |")
    return "\n".join(rows)


def soc_delta():
    """per arm and corner: setup WNS / TNS / violators (total; I/O-only) before (per-view iolat, 4.2b) and after (SoC-context budgets)."""
    def c(v):
        io = int(v["setup_viol"]) - int(v["r2rx_setup_viol"])
        return f"{v['setup_wns']:+.3f} / {z(v['setup_tns']):.1f} / {int(v['setup_viol'])} (I/O {io})"

    rows = ["| corner | arm | before: per-view iolat (4.2b) | after: SoC-context budgets (4.2f) |", "|---|---|---|---|"]
    for cn in CORNERS:
        for a in ARMS:
            rows.append(f"| {cn} | {nm(a)} | {c(D['judge'][a]['iolat_pv']['corners'][cn]['values'])} | {c(D['judge'][a]['soc_budget']['corners'][cn]['values'])} |")
    return "\n".join(rows)


def r2r():
    out = []
    for a in ARMS:
        cs = D["judge"][a]["base"]["corners"]
        su = [f"{c} {int(cs[c]['values']['r2rx_setup_viol'])} ({cs[c]['values']['r2rx_setup_wns']:+.3f} ns)" for c in CORNERS if cs[c]["values"]["r2rx_setup_viol"] > 0]
        ho = [f"{c} {int(cs[c]['values']['r2rx_hold_viol'])} ({cs[c]['values']['r2rx_hold_wns']:+.3f} ns)" for c in CORNERS if cs[c]["values"]["r2rx_hold_viol"] > 0]
        out.append(f"- {nm(a)}: reg-to-reg setup violators " + (", ".join(su) if su else "none at any corner") + "; reg-to-reg hold violators " + (", ".join(ho) if ho else "none at any corner") + ".")
    return "\n".join(out)


SECTIONS = {
    "base": lambda: judge_table("base"), "iolat": lambda: judge_table("iolat"), "iolat_pv": lambda: judge_table("iolat_pv"), "iolat_pvs": lambda: judge_table("iolat_pvs"),
    "own": lambda: judge_table("own", [a for a in ARMS if a != "openroad_b2"]), "latency": latency, "power": power, "native": native, "physical": physical, "cost": cost, "pvsum": pvsum, "r2r": r2r, "soc_budget": lambda: judge_table("soc_budget"), "soc_budget_table": soc_budget_table, "soc_delta": soc_delta,
}

if __name__ == "__main__":
    want = sys.argv[1:] or list(SECTIONS)
    for s in want:
        print(f"<!-- FINAL-TABLE {s} -->\n{SECTIONS[s]()}\n<!-- /FINAL-TABLE -->\n")
