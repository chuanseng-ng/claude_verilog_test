#!/usr/bin/env python3
"""correlate_all.py [--arms a,b,c] [--corners nom,min,max] -- Quantus vs StarRC, per net, per arm and corner.

Test = Quantus SPEF (runs/<arm>_<corner>/rv32i_cpu_top.<corner>.spef), reference = StarRC SPEF (../starrc/runs/<arm>_<corner>/...), the SPEF
the PrimeTime judge read.  Per-net values come from starrc/scripts/spef_stats.py (total C = D_NET value, ground C, coupling C, sum of *RES).
Percent error = (Quantus / StarRC - 1) * 100.  Population: nets in both SPEFs with StarRC total C > 1 fF (the calibration-gate population of
reports/starrc_extraction_summary.md); R: the subset with R > 0 in both.  Reported: median signed error, median |error|, p95 |error|, share of nets
outside +-10 %, Pearson r (log-log), design totals.  Gate label: INDICATIVE when median |error| > 10 % (plan calibration gate), and a TAIL flag
when p95 |error| > 10 %.  Writes reports/quantus_vs_starrc.json (+ .md table).  Needs numpy: run with Calibre's bundled python3.
"""
import sys, os, json, importlib.util
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
Q = os.path.abspath(os.path.join(HERE, ".."))
S = os.path.abspath(os.path.join(HERE, "../../starrc"))
spec = importlib.util.spec_from_file_location("spef_stats", os.path.join(S, "scripts/spef_stats.py"))
ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)

def load(path):
    d = {}
    for n, c, g, cc, r, k in ss.parse(path):
        d[n] = (c, g, cc, r, k)
    return d

def err_stats(a, b):
    e = (b / a - 1.0) * 100.0
    ae = np.abs(e)
    r_log = float(np.corrcoef(np.log(a), np.log(b))[0, 1]) if len(a) > 2 else float("nan")
    return {"n": int(len(a)), "median_err_pct": float(np.median(e)), "median_abs_err_pct": float(np.median(ae)),
            "p95_abs_err_pct": float(np.percentile(ae, 95)), "p5_err_pct": float(np.percentile(e, 5)), "p95_err_pct": float(np.percentile(e, 95)),
            "outside_10pct_share": float(np.mean(ae > 10.0)), "r_loglog": r_log}

def main():
    arms = ["icc2b6", "innovusb6", "openroad"]; corners = ["nom", "min", "max"]
    a = sys.argv[1:]
    while a:
        k = a.pop(0)
        if k == "--arms": arms = a.pop(0).split(",")
        elif k == "--corners": corners = a.pop(0).split(",")
    out = {"definition": __doc__.strip().split("\n")[0:1], "results": {}}
    rows = []
    for arm in arms:
        for c in corners:
            qp = os.path.join(Q, "runs/%s_%s/rv32i_cpu_top.%s.spef" % (arm, c, c))
            sp = os.path.join(S, "runs/%s_%s/rv32i_cpu_top.%s.spef" % (arm, c, c))
            if not (os.path.isfile(qp) and os.path.isfile(sp)):
                continue
            q = load(qp); s = load(sp)
            common = [n for n in s if n in q]
            sel = [n for n in common if s[n][0] > 1.0]
            C0 = np.array([s[n][0] for n in sel]); C1 = np.array([q[n][0] for n in sel])
            G0 = np.array([s[n][1] for n in sel]); G1 = np.array([q[n][1] for n in sel])
            R0 = np.array([s[n][3] for n in sel]); R1 = np.array([q[n][3] for n in sel])
            m = (R0 > 0) & (R1 > 0)
            gm = (G0 > 0) & (G1 > 0)
            tc0 = sum(v[0] for v in s.values()); tc1 = sum(v[0] for v in q.values())
            tg0 = sum(v[1] for v in s.values()); tg1 = sum(v[1] for v in q.values())
            cc0 = sum(v[2] for v in s.values()) / 2; cc1 = sum(v[2] for v in q.values()) / 2
            tr0 = sum(v[3] for v in s.values()); tr1 = sum(v[3] for v in q.values())
            res = {"nets_starrc": len(s), "nets_quantus": len(q), "nets_common": len(common),
                   "nets_only_starrc": len(s) - len(common), "nets_only_quantus": len(q) - len(common),
                   "gate_population_nets": len(sel),
                   "total_C": err_stats(C0, C1), "ground_C": err_stats(G0[gm], G1[gm]), "total_R": err_stats(R0[m], R1[m]),
                   "design": {"C_starrc_pF": tc0 / 1e3, "C_quantus_pF": tc1 / 1e3, "C_ratio": tc1 / tc0,
                              "Cgnd_ratio": tg1 / tg0, "Ccoupling_ratio": cc1 / cc0 if cc0 else None, "R_ratio": tr1 / tr0},
                   "starrc_spef": os.path.relpath(sp, Q + "/../../../.."), "quantus_spef": os.path.relpath(qp, Q + "/../../../..")}
            res["label"] = "INDICATIVE" if res["total_C"]["median_abs_err_pct"] > 10.0 or res["total_R"]["median_abs_err_pct"] > 10.0 else "within gate (median)"
            res["tail_flag"] = {"total_C": res["total_C"]["p95_abs_err_pct"] > 10.0, "total_R": res["total_R"]["p95_abs_err_pct"] > 10.0}
            out["results"]["%s_%s" % (arm, c)] = res
            for qty, key in (("total C", "total_C"), ("ground C", "ground_C"), ("total R", "total_R")):
                st = res[key]
                rows.append("| %s | %s | %s | %d | %+.2f | %.2f | %.2f | %.1f | %.4f |" % (arm, c, qty, st["n"], st["median_err_pct"], st["median_abs_err_pct"],
                            st["p95_abs_err_pct"], 100 * st["outside_10pct_share"], st["r_loglog"]))
            rows.append("| %s | %s | design totals | %d / %d nets | C %.3f, Cgnd %.3f, Ccc %.3f, R %.3f | | | | %s |" % (
                arm, c, len(q), len(s), res["design"]["C_ratio"], res["design"]["Cgnd_ratio"], res["design"]["Ccoupling_ratio"] or 0, res["design"]["R_ratio"], res["label"]))
            print(arm, c, res["label"], "C med %+.2f%% p95|e| %.2f%%  R med %+.2f%% p95|e| %.2f%%" % (
                  res["total_C"]["median_err_pct"], res["total_C"]["p95_abs_err_pct"], res["total_R"]["median_err_pct"], res["total_R"]["p95_abs_err_pct"]), flush=True)
    os.makedirs(os.path.join(Q, "reports"), exist_ok=True)
    tag = os.environ.get("CORR_TAG", "")
    with open(os.path.join(Q, "reports/quantus_vs_starrc%s.json" % tag), "w") as f:
        json.dump(out, f, indent=1)
    with open(os.path.join(Q, "reports/quantus_vs_starrc%s.md" % tag), "w") as f:
        f.write("| arm | corner | quantity | nets | median err % | median abs err % | p95 abs err % | outside +-10 % | r (log-log) |\n|---|---|---|---:|---:|---:|---:|---:|---:|\n")
        f.write("\n".join(rows) + "\n")

main()
