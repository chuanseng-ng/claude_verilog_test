#!/usr/bin/env python3
"""collect.py -- parse runs/<arm>_<rc>_<lib>/ into compact text tables under reports/.
Run from pnr/commercial/signoff/pt (make tables).  Reads only; never touches runs/."""
import json, os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
PT = os.path.dirname(HERE)
SET = os.environ.get("PT_SET", "")
RUNS = os.path.join(PT, "runs" + ("_" + SET if SET else ""))
REP = os.path.join(PT, "reports", SET if SET else "current")
ROOT = os.path.abspath(os.path.join(PT, "../../../.."))
os.makedirs(REP, exist_ok=True)
SETNOTE = "SPEF set: " + ("UNTUNED ITF (frozen starrc/runs/_superseded_untuned copies)" if SET == "untuned" else "current starrc/runs (whatever the extraction agent last wrote)")

RCS = ["nom", "min", "max"]
LIBS = ["tt", "ss", "ff"]
LIBLONG = {"tt": "tt_025C_1v80", "ss": "ss_100C_1v60", "ff": "ff_n40C_1v95"}
ARMS = [("openroad", "OpenROAD (StarRC)"), ("icc2", "ICC2 (StarRC)"),
        ("innovus", "Innovus b5c (StarRC)"), ("openroad_rcx", "OpenROAD (OpenRCX SPEF)")]
INDICATIVE = {"nom": "INDICATIVE", "max": "INDICATIVE", "min": "indicative*"}


def rd(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def load_run(arm, rc, lib):
    d = os.path.join(RUNS, f"{arm}_{rc}_{lib}")
    if not os.path.isfile(os.path.join(d, ".done")):
        return None
    r = {"dir": d}
    for line in rd(os.path.join(d, "metrics.tsv")).splitlines():
        k, _, v = line.partition("\t")
        r[k] = v
    for line in rd(os.path.join(d, "inputs.txt")).splitlines():
        k, _, v = line.partition("=")
        r["in_" + k] = v
    for k in ("setup_wns", "setup_tns", "hold_wns", "hold_tns"):
        r[k] = float(r[k])
    for k in ("setup_viol", "hold_viol"):
        r[k] = int(r[k])
    # report_global_timing categories
    gt = rd(os.path.join(d, "global_timing.txt"))
    for kind in ("Setup", "Hold"):
        m = re.search(kind + r" violations\s*-+\s*Total.*?-+\s*WNS\s+(.*?)\n\s*TNS\s+(.*?)\n\s*NUM\s+(.*?)\n", gt, re.S)
        if not m:
            if re.search(r"No " + kind.lower() + r" violations found", gt):
                k = kind.lower()
                r[k + "_r2r"] = (None, 0.0, 0)
                r[k + "_io"] = (None, 0.0, 0)
                r[k + "_gt_total"] = (None, 0.0, 0)
                continue
            raise SystemExit(f"cannot parse global_timing {d} {kind}")
        wns = [float(x) for x in m.group(1).split()]
        tns = [float(x) for x in m.group(2).split()]
        num = [int(x) for x in m.group(3).split()]
        # Total, reg->reg, in->reg, reg->out, in->out
        k = kind.lower()
        r[k + "_r2r"] = (wns[1], tns[1], num[1])
        r[k + "_io"] = (min(wns[2:]), sum(tns[2:]), sum(num[2:]))
        r[k + "_gt_total"] = (wns[0], tns[0], num[0])
    # DRV
    drv = rd(os.path.join(d, "constraint_drv.txt"))
    cnt = {"max_transition": 0, "max_capacitance": 0, "max_fanout": 0}
    worst = {}
    cur = None
    for line in drv.splitlines():
        s = line.strip()
        if s in cnt:
            cur = s
            continue
        if cur and "(VIOLATED)" in line:
            cnt[cur] += 1
            worst.setdefault(cur, s.split()[0])
    r["drv"] = cnt
    # annotation
    def annot(path):
        txt = rd(path)
        rows = {"p2p": [0, 0], "driverless": [0, 0], "loadless": [0, 0]}
        for line in txt.splitlines():
            m = re.match(r"\s*- (Pin to pin|Driverless|Loadless) nets\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", line)
            if m:
                key = {"Pin to pin": "p2p", "Driverless": "driverless", "Loadless": "loadless"}[m.group(1)]
                rows[key][0] += int(m.group(2))
                rows[key][1] += int(m.group(6))
        return rows
    a = annot(os.path.join(d, "annot.txt"))
    c = annot(os.path.join(d, "annot_clock.txt"))
    r["annot"] = a
    r["annot_clock_unann"] = sum(v[1] for v in c.values())
    r["annot_clock_total"] = sum(v[0] for v in c.values())
    p2p_t, p2p_u = a["p2p"]
    r["gate_pct"] = 100.0 * p2p_u / p2p_t if p2p_t else 100.0
    r["gate"] = "PASS" if (p2p_t > 0 and r["gate_pct"] <= 1.0 and r["annot_clock_unann"] == 0) else "FAIL"
    pl = rd(os.path.join(d, "parasitics_command.log"))
    r["spef_nets_missing"] = len(re.findall(r"Cannot find net '", pl))
    m = re.search(r"Annotated nets\s*:\s*(\d+)", pl)
    r["spef_annotated_nets"] = int(m.group(1)) if m else -1
    # wall / rss
    t = rd(os.path.join(d, "time.txt"))
    m = re.search(r"Elapsed \(wall clock\) time.*?: ([\d:.]+)", t)
    r["wall"] = m.group(1) if m else "?"
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t)
    r["rss_gb"] = int(m.group(1)) / 1048576 if m else 0.0
    # power (A = PT defaults, B = matched to OpenSTA register-output assumption)
    for tag in ("A", "B"):
        pw = rd(os.path.join(d, f"power_{tag}.txt"))
        if not pw:
            continue
        pr = {}
        for g in ("clock_network", "register", "combinational", "sequential", "memory", "io_pad", "black_box"):
            m = re.search(r"^" + g + r"\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", pw, re.M)
            if m:
                pr[g] = [float(x) for x in m.groups()]
        tot = [sum(v[i] for v in pr.values()) for i in range(4)]   # internal, switching, leakage, total (W)
        m = re.search(r"Total Power\s*=\s*(\S+)", pw)
        r["power_" + tag] = {"internal": tot[0], "switching": tot[1], "leakage": tot[2], "total": tot[3],
                             "reported_total": float(m.group(1)), "groups": pr}
    return r


def f(x, n=4):
    return "met" if x is None else f"{x:+.{n}f}"


def corner_label(rc, lib):
    return f"{rc}_{LIBLONG[lib]}"


def arm_tables(arm, title, res):
    out = []
    n_have = sum(1 for k in res if k[0] == arm)
    if n_have == 0:
        return [f"## {title}", "", "PENDING: no completed runs (inputs absent). One command once they exist: `make -C pnr/commercial/signoff/pt innovus`", ""]
    any_run = next(v for k, v in res.items() if k[0] == arm)
    out.append(f"## {title}  ({n_have}/9 corners)")
    out.append(f"netlist md5 {any_run['in_netlist_md5']}  sdc md5 {any_run['in_sdc_md5']}  PT {any_run['pt_version']}")
    out.append("SPEF md5 per rc corner: " + ", ".join(
        f"{rc}={next((v['in_spef_md5'] for k,v in res.items() if k[0]==arm and k[1]==rc), '-')}" for rc in RCS))
    out.append("")
    out.append("SETUP (ns).  Total = unique violating endpoints;  r2r = reg->reg;  I/O = in->reg + reg->out + in->out (PT report_global_timing categories; I/O NUM may double-count an endpoint)")
    out.append(f"{'corner':<18}{'WNS':>9}{'TNS':>10}{'viol':>6} | {'r2r WNS':>9}{'TNS':>10}{'n':>6} | {'I/O WNS':>9}{'TNS':>10}{'n':>6} | worst setup path (start -> end)")
    for rc in RCS:
        for lib in LIBS:
            r = res.get((arm, rc, lib))
            if not r:
                out.append(f"{corner_label(rc, lib):<18}  not run")
                continue
            a, b = r["setup_r2r"], r["setup_io"]
            a = (None if a[2] == 0 else a[0],) + tuple(a[1:])
            b = (None if b[2] == 0 else b[0],) + tuple(b[1:])
            out.append(f"{corner_label(rc, lib):<18}{f(r['setup_wns']):>9}{r['setup_tns']:>10.3f}{r['setup_viol']:>6} | "
                       f"{f(a[0]):>9}{a[1]:>10.3f}{a[2]:>6} | {f(b[0]):>9}{b[1]:>10.3f}{b[2]:>6} | {r['setup_worst_start']} -> {r['setup_worst_end']}")
    out.append("")
    out.append("HOLD (ns)")
    out.append(f"{'corner':<18}{'WNS':>9}{'TNS':>10}{'viol':>6} | {'r2r WNS':>9}{'TNS':>10}{'n':>6} | {'I/O WNS':>9}{'TNS':>10}{'n':>6} | worst hold path (start -> end)")
    for rc in RCS:
        for lib in LIBS:
            r = res.get((arm, rc, lib))
            if not r:
                continue
            a, b = r["hold_r2r"], r["hold_io"]
            a = (None if a[2] == 0 else a[0],) + tuple(a[1:])
            b = (None if b[2] == 0 else b[0],) + tuple(b[1:])
            out.append(f"{corner_label(rc, lib):<18}{f(r['hold_wns']):>9}{r['hold_tns']:>10.3f}{r['hold_viol']:>6} | "
                       f"{f(a[0]):>9}{a[1]:>10.3f}{a[2]:>6} | {f(b[0]):>9}{b[1]:>10.3f}{b[2]:>6} | {r['hold_worst_start']} -> {r['hold_worst_end']}")
    out.append("")
    out.append("DRV (violating pins) and ANNOTATION GATE (p2p = nets with a driver and load; gate: >1 % p2p unannotated or any clock net unannotated = FAIL)")
    out.append(f"{'corner':<18}{'max_tran':>9}{'max_cap':>9}{'max_fan':>9} | {'p2p nets':>9}{'p2p unann':>10}{'clk nets':>9}{'clk unann':>10}{'loadless':>9}{'driverless':>11} | gate  | SPEF nets not in netlist | wall   rss")
    for rc in RCS:
        for lib in LIBS:
            r = res.get((arm, rc, lib))
            if not r:
                continue
            a = r["annot"]
            out.append(f"{corner_label(rc, lib):<18}{r['drv']['max_transition']:>9}{r['drv']['max_capacitance']:>9}{r['drv']['max_fanout']:>9} | "
                       f"{a['p2p'][0]:>9}{a['p2p'][1]:>10}{r['annot_clock_total']:>9}{r['annot_clock_unann']:>10}{a['loadless'][0]:>9}{a['driverless'][0]:>11} | {r['gate']:<5} | {r['spef_nets_missing']:>24} | {r['wall']} {r['rss_gb']:.1f}G")
    out.append("")
    return out


def load_native_or():
    p = os.path.join(ROOT, "pnr/commercial/runs/openroad/metrics.json")
    try:
        return json.load(open(p))
    except OSError:
        return {}


def native_or(m, rc, lib, key):
    return m.get(f"timing__{key}__corner:{rc}_{LIBLONG[lib]}")


def main():
    res = {}
    for arm, _ in ARMS:
        for rc in RCS:
            for lib in LIBS:
                r = load_run(arm, rc, lib)
                if r:
                    res[(arm, rc, lib)] = r
    # ---- per-arm 9-corner tables
    allout = ["# PrimeTime judge, 9-corner tables (auto-generated by scripts/collect.py)", SETNOTE, "",
              "Corner label = <RC corner>_<lib corner>; lib corners tt/ss/ff = sky130_fd_sc_hd 025C_1v80 / 100C_1v60 / n40C_1v95; SRAM macro = TT 1p8V 25C at EVERY corner (bead o1i).",
              "SPEFs: StarRC with the AUTHORED, UNTUNED ITF. Correlation gate vs OpenRCX: nom and max INDICATIVE, min median-only pass (see starrc_extraction_summary.md).",
              "Same SDC (md5 3c69635042a9d65cb87e71a9db713e4e), propagated clocks, no derate/OCV, SI off, CRPR on, coupling lumped to ground (factor 1.0), PrimeTime X-2025.06.", ""]
    for arm, title in ARMS:
        t = arm_tables(arm, title, res)
        allout += t
        with open(os.path.join(REP, f"{arm}_9corner.txt"), "w") as fh:
            fh.write("\n".join(t) + "\n")
    with open(os.path.join(REP, "judge_tables.md"), "w") as fh:
        fh.write("```\n" + "\n".join(allout) + "\n```\n")
    # ---- power
    pw = ["# PrimePower, vectorless, nom_tt (tt lib + nom SPEF), mW", ""]
    pw.append("Both variants: power_default_toggle_rate 0.1 (reference clock: related), power_default_static_probability 0.5, averaged mode, no SAIF/VCD,")
    pw.append("clock activity from the SDC clock (clk_i, 13.333 ns).  A = PT defaults (register-output activity propagated from D).  B = A plus 0.1/0.5 asserted on every")
    pw.append("register output pin (matches OpenSTA's behaviour; headline).  Totals are sums of the group rows (4 significant digits).")
    pw.append("")
    for tag, label in (("B", "B  matched to OpenSTA default (headline)"), ("A", "A  PrimePower defaults")):
        pw.append(label)
        pw.append(f"{'arm':<26}{'total':>9}{'internal':>10}{'switching':>10}{'leakage':>9} | {'clock_nw':>9}{'register':>9}{'comb':>8}{'memory':>8}")
        for arm, title in ARMS:
            r = res.get((arm, "nom", "tt"))
            if not r or "power_" + tag not in r:
                pw.append(f"{title:<26}  PENDING / not run")
                continue
            p = r["power_" + tag]
            g = p["groups"]
            gt = lambda k: g.get(k, [0, 0, 0, 0])[3] * 1e3
            pw.append(f"{title:<26}{p['total']*1e3:>9.3f}{p['internal']*1e3:>10.3f}{p['switching']*1e3:>10.3f}{p['leakage']*1e3:>9.4f} | "
                      f"{gt('clock_network'):>9.3f}{gt('register'):>9.3f}{gt('combinational'):>8.3f}{gt('memory'):>8.3f}")
        pw.append("")
    with open(os.path.join(REP, "power_nom_tt.txt"), "w") as fh:
        fh.write("\n".join(pw) + "\n")
    # ---- OpenROAD three-way: native OpenSTA/OpenRCX vs PT/OpenRCX vs PT/StarRC
    nm = load_native_or()
    tw = ["# OpenROAD arm, three views per corner (ns)", "",
          "native = OpenSTA + OpenRCX SPEF (LibreLane, metrics.json); PT/RCX = PrimeTime + the same OpenRCX SPEF (engine effect = PT/RCX - native);",
          "PT/StarRC = PrimeTime + StarRC SPEF (extractor effect = PT/StarRC - PT/RCX).  Native r2r WNS is OpenSTA's `timing__*_r2r__ws`.", ""]
    tw.append(f"{'corner':<18}| SETUP WNS: {'native':>8}{'PT/RCX':>9}{'PT/StarRC':>10} | SETUP viol: {'native':>6}{'PT/RCX':>7}{'PT/Star':>8} | HOLD WNS: {'native':>8}{'PT/RCX':>9}{'PT/StarRC':>10} | HOLD viol: {'native':>6}{'PT/RCX':>7}{'PT/Star':>8} | HOLD r2r viol: {'native':>6}{'PT/RCX':>7}{'PT/Star':>8}")
    def fx(v):
        return "-" if v is None else (f"{v:+.4f}" if isinstance(v, float) else str(v))
    def g(r, k):
        return "-" if r is None else (f(r[k]) if isinstance(r[k], float) else str(r[k]))
    for rc in RCS:
        for lib in LIBS:
            x = res.get(("openroad_rcx", rc, lib)); s_ = res.get(("openroad", rc, lib))
            nsw = native_or(nm, rc, lib, "setup__ws"); nhw = native_or(nm, rc, lib, "hold__ws")
            nsv = native_or(nm, rc, lib, "setup_vio__count"); nhv = native_or(nm, rc, lib, "hold_vio__count")
            nhr = native_or(nm, rc, lib, "hold_r2r_vio__count")
            hr = lambda r: "-" if r is None else str(r["hold_r2r"][2])
            tw.append(f"{corner_label(rc, lib):<18}|           {fx(nsw):>8}{g(x,'setup_wns'):>9}{g(s_,'setup_wns'):>10} |             {fx(nsv):>6}{g(x,'setup_viol'):>7}{g(s_,'setup_viol'):>8} |           {fx(nhw):>8}{g(x,'hold_wns'):>9}{g(s_,'hold_wns'):>10} |            {fx(nhv):>6}{g(x,'hold_viol'):>7}{g(s_,'hold_viol'):>8} |                {fx(nhr):>6}{hr(x):>7}{hr(s_):>8}")
    tw.append("")
    tw.append("DRV violating pins: native (OpenSTA: lib + SDC limits; slew=max_slew count) vs PT (report_constraint, lib + SDC limits)")
    tw.append(f"{'corner':<18}| max_tran: {'native':>7}{'PT/RCX':>8}{'PT/Star':>8} | max_cap: {'native':>7}{'PT/RCX':>8}{'PT/Star':>8}")
    for rc in RCS:
        for lib in LIBS:
            x = res.get(("openroad_rcx", rc, lib)); s_ = res.get(("openroad", rc, lib))
            c = f"{rc}_{LIBLONG[lib]}"
            tw.append(f"{corner_label(rc, lib):<18}|           {nm.get('design__max_slew_violation__count__corner:'+c,'-'):>7}{x['drv']['max_transition'] if x else '-':>8}{s_['drv']['max_transition'] if s_ else '-':>8} |          {nm.get('design__max_cap_violation__count__corner:'+c,'-'):>7}{x['drv']['max_capacitance'] if x else '-':>8}{s_['drv']['max_capacitance'] if s_ else '-':>8}")
    with open(os.path.join(REP, "openroad_three_way.txt"), "w") as fh:
        fh.write("\n".join(tw) + "\n")
    # ---- worst setup path text for nom_tt of every arm (compact)
    for arm, _ in ARMS:
        r = res.get((arm, "nom", "tt"))
        if r:
            for kind in ("setup", "hold"):
                src = os.path.join(r["dir"], f"worst_{kind}.txt")
                lines = rd(src).splitlines()
                with open(os.path.join(REP, f"{arm}_nom_tt_worst_{kind}.txt"), "w") as fh:
                    fh.write("\n".join(l.rstrip() for l in lines if l.strip()) + "\n")
            with open(os.path.join(REP, f"{arm}_nom_tt_power_full.txt"), "w") as fh:
                fh.write("## variant B (matched)\n" + rd(os.path.join(r["dir"], "power_B.txt")) + "\n## variant A (PT defaults)\n" + rd(os.path.join(r["dir"], "power_A.txt")))
    # ---- markdown compact tables (pasted into pnr/commercial/reports/pt_judge_summary.md)
    md = []
    for arm, title in ARMS:
        if not any(k[0] == arm for k in res):
            md += [f"#### {title}", "", "PENDING: inputs absent (one command once they exist: `make -C pnr/commercial/signoff/pt innovus`).", ""]
            continue
        md += [f"#### {title}", "",
               "| corner | setup WNS | TNS | viol (r2r / I/O) | hold WNS | TNS | viol (r2r / I/O) | max_tran | max_cap | worst setup path (start -> end) |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for rc in RCS:
            for lib in LIBS:
                r = res.get((arm, rc, lib))
                if not r:
                    md.append(f"| {corner_label(rc, lib)} | not run | | | | | | | | |")
                    continue
                md.append(f"| {corner_label(rc, lib)} | {r['setup_wns']:+.4f} | {r['setup_tns']:.3f} | {r['setup_viol']} ({r['setup_r2r'][2]} / {r['setup_io'][2]}) | "
                          f"{r['hold_wns']:+.4f} | {r['hold_tns']:.3f} | {r['hold_viol']} ({r['hold_r2r'][2]} / {r['hold_io'][2]}) | "
                          f"{r['drv']['max_transition']} | {r['drv']['max_capacitance']} | `{r['setup_worst_start']}` -> `{r['setup_worst_end']}` |")
        md.append("")
    with open(os.path.join(REP, "compact_tables.md"), "w") as fh:
        fh.write("\n".join(md) + "\n")
    # ---- json (compact) for downstream tooling
    js = {}
    for (arm, rc, lib), r in res.items():
        js[f"{arm}_{rc}_{lib}"] = {k: v for k, v in r.items() if k not in ("dir",)}
    with open(os.path.join(REP, "judge_results.json"), "w") as fh:
        json.dump(js, fh, indent=1, sort_keys=True)
    print(f"collected {len(res)} runs -> {REP}")


if __name__ == "__main__":
    main()
