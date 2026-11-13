#!/usr/bin/env python3
"""collect_runs.py -- write reports/quantus_runs.json: Quantus run cost (wall, RSS), Techgen cost, and the optional PrimeTime sensitivity
(nom_tt, base SDC) of the Quantus SPEF against the StarRC SPEF.  Committed so compare.py can cite it."""
import json, os, re, hashlib, glob, sys

Q = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ROOT = os.path.abspath(os.path.join(Q, "../../../.."))
PT = os.path.join(ROOT, "pnr/commercial/signoff/pt")
SK = os.path.join(ROOT, "pnr/commercial/pdk/sky130/build/qrc")

def hms(s):
    p = [float(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]

def tv(path):
    t = open(path).read()
    e = re.search(r"Elapsed \(wall clock\) time.*?: ([\d:.]+)", t)
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t)
    s = re.search(r"session_peak_rss_kb=(\d+)", t)
    return {"wall_s": round(hms(e.group(1)), 1) if e else None, "max_single_process_rss_kb": int(m.group(1)) if m else None,
            "session_peak_rss_kb": int(s.group(1)) if s else None, "rc": (re.search(r"^rc=(\d+)", t, re.M) or [None, None])[1]}

def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()

out = {"quantus_runs": {}, "techgen": {}, "pt_sensitivity_nom_tt": {}}
for d in sorted(glob.glob(os.path.join(Q, "runs/*_*/"))):
    tag = os.path.basename(d.rstrip("/"))
    c = tag.rsplit("_", 1)[1]
    spef = os.path.join(d, "rv32i_cpu_top.%s.spef" % c)
    if not os.path.isfile(spef) or not os.path.isfile(os.path.join(d, "time.txt")):
        continue
    log = open(os.path.join(d, "quantus.log"), errors="replace").read()
    r = tv(os.path.join(d, "time.txt"))
    r.update({"nets_extracted": int((re.search(r"Nets:\s+(\d+)", log) or [0, 0])[1]),
              "warnings": int((re.search(r"Warning messages:\s+(\d+)", log) or [0, 0])[1]),
              "errors": int((re.search(r"Error messages:\s+(\d+)", log) or [0, 0])[1]),
              "spef_bytes": os.path.getsize(spef), "spef_md5": md5(spef)})
    out["quantus_runs"][tag] = r
for c in ("nom", "min", "max"):
    tm = os.path.join(SK, c, "techgen_cell.timing")
    if os.path.isfile(tm):
        out["techgen"][c] = {"timing_lines": open(tm).read().strip().split("\n"), "qrcTechFile_bytes": os.path.getsize(os.path.join(SK, c, "qrcTechFile")) if os.path.isfile(os.path.join(SK, c, "qrcTechFile")) else None,
                             "provenance": open(os.path.join(SK, c, "PROVENANCE.txt")).read().strip() if os.path.isfile(os.path.join(SK, c, "PROVENANCE.txt")) else None}

def metrics(d):
    m = {}
    for l in open(os.path.join(d, "metrics.tsv")):
        k, _, v = l.rstrip("\n").partition("\t"); m[k] = v
    pw = re.search(r"Total Power\s+=\s+([\d.eE+-]+)", open(os.path.join(d, "power_B.txt")).read())
    a = open(os.path.join(d, "annot.txt")).read()
    p2p_un = sum(int(x) for x in re.findall(r"Pin to pin nets\s+\|\s+\d+ \|\s+\d+ \|\s+\d+ \|\s+\d+ \|\s+(\d+)", a))
    return {"setup_wns_ns": float(m["setup_wns"]), "setup_tns_ns": float(m["setup_tns"]), "setup_viol": int(m["setup_viol"]),
            "hold_wns_ns": float(m["hold_wns"]), "hold_tns_ns": float(m["hold_tns"]), "hold_viol": int(m["hold_viol"]),
            "total_power_mW": float(pw.group(1)) * 1e3, "p2p_unannotated_nets": p2p_un}

for arm in ("icc2b6", "innovusb6", "openroad", "icc2b9", "innovusb11"):
    dq = os.path.join(PT, "runs_quantus/%s_nom_tt" % arm); ds = os.path.join(PT, "runs/%s_nom_tt" % arm)
    if os.path.isfile(os.path.join(dq, "metrics.tsv")) and os.path.isfile(os.path.join(ds, "metrics.tsv")):
        mq, ms = metrics(dq), metrics(ds)
        out["pt_sensitivity_nom_tt"][arm] = {"starrc": ms, "quantus": mq,
            "delta": {k: round(mq[k] - ms[k], 6) for k in mq if isinstance(mq[k], float)}}
os.makedirs(os.path.join(Q, "reports"), exist_ok=True)
json.dump(out, open(os.path.join(Q, "reports/quantus_runs.json"), "w"), indent=1)
print(json.dumps(out["pt_sensitivity_nom_tt"], indent=1)[:2500])
