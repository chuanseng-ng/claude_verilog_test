#!/usr/bin/env python3
"""compare_variants.py <base_set> <iolat_set>  -- base-SDC vs iolat-SDC tables + validation, from runs_<set>/ (set 'current' = runs/).
Writes reports/<iolat_set>/base_vs_iolat.txt and validation_nom_tt.txt.  Reads only."""
import difflib, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect as C

base_set, io_set = sys.argv[1], sys.argv[2]
def dirs(setname):
    return os.path.join(C.PT, "runs" if setname == "current" else "runs_" + setname)
res = {}
for tag, sname in (("base", base_set), ("iolat", io_set)):
    C.RUNS = dirs(sname)
    for arm in ("openroad", "icc2"):
        for rc in C.RCS:
            for lib in C.LIBS:
                r = C.load_run(arm, rc, lib)
                if r:
                    res[(tag, arm, rc, lib)] = r
REP = os.path.join(C.PT, "reports", io_set)
os.makedirs(REP, exist_ok=True)
out = [f"# base SDC ({base_set}) vs I/O-latency SDC ({io_set}); same frozen SPEFs, same netlists, PrimeTime. ns.", ""]
out.append("Columns per variant: WNS / TNS / endpoints for the whole design; pure reg->reg (get_timing_paths -from register clock pins -to register data pins, worst path per endpoint; WNS is the worst slack even when positive); I/O = in->reg + reg->out + in->out from report_global_timing (categories re-assign an endpoint when an I/O constraint changes).")
out.append("'met' = no violation in that category.  The pure reg->reg numbers must be IDENTICAL between variants (clk_i is untouched); the last column checks wns/tns/violators/endpoint count to 1e-9.")
out.append("")
def cat(t):
    return f"{'met' if t[2]==0 else format(t[0],'+.4f'):>8}/{t[1]:>9.3f}/{t[2]:>4}"
r2r_diff = []
for arm, title in (("openroad", "OpenROAD (StarRC, untuned)"), ("icc2", "ICC2 (StarRC, untuned)")):
    for kind in ("setup", "hold"):
        out.append(f"## {title} -- {kind.upper()}")
        out.append(f"{'corner':<18}{'variant':<7}{'total WNS/TNS/n':>28} | {'r2r WNS/TNS/n':>28} | {'I/O WNS/TNS/n':>28} | r2r same?")
        for rc in C.RCS:
            for lib in C.LIBS:
                b = res.get(("base", arm, rc, lib)); i = res.get(("iolat", arm, rc, lib))
                if not b or not i:
                    continue
                kx = {"setup": "r2rx_setup", "hold": "r2rx_hold"}[kind]
                fl = lambda r, k: float(r[f"{kx}_{k}"])
                same = all(abs(fl(b, k) - fl(i, k)) < 1e-9 for k in ("wns", "tns", "viol", "endpoints"))
                r2r_diff.append((arm, kind, rc, lib, same))
                for tag, r in (("base", b), ("iolat", i)):
                    tot = (r[f"{kind}_wns"], r[f"{kind}_tns"], r[f"{kind}_viol"])
                    x = f"{float(r[kx+'_wns']):+.4f}/{float(r[kx+'_tns']):>9.3f}/{int(r[kx+'_viol']):>4}"
                    out.append(f"{C.corner_label(rc, lib):<18}{tag:<7}{format(tot[0],'+.4f'):>10}/{tot[1]:>9.3f}/{tot[2]:>5} | {x:>28} | {cat(r[kind+'_io']):>28} | {'yes' if same else 'NO'}")
        out.append("")
bad = [x for x in r2r_diff if not x[4]]
out.append(f"r2r identical between variants: {len(r2r_diff)-len(bad)}/{len(r2r_diff)} (arm,kind,corner) cells" + ("" if not bad else f"; DIFFERENT: {bad}"))
out.append("")
out.append("## Sign-off view: counts of corners that meet (WNS >= 0) per variant")
for arm in ("openroad", "icc2"):
    for kind in ("setup", "hold"):
        for tag in ("base", "iolat"):
            n = sum(1 for rc in C.RCS for lib in C.LIBS if res.get((tag, arm, rc, lib)) and res[(tag, arm, rc, lib)][f"{kind}_viol"] == 0)
            out.append(f"  {arm:<9}{kind:<6}{tag:<6}: {n}/9 corners with 0 violating endpoints")
open(os.path.join(REP, "base_vs_iolat.txt"), "w").write("\n".join(out) + "\n")

# ---- validation at nom_tt
v = ["# Validation at nom_tt (base vs iolat SDC)", ""]
def grab(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return ""
for arm in ("openroad", "icc2"):
    b = res.get(("base", arm, "nom", "tt")); i = res.get(("iolat", arm, "nom", "tt"))
    if not b or not i:
        continue
    v.append(f"## {arm}")
    v.append(f"SDC md5 base {b['sdc_md5']}  iolat {i['sdc_md5']}  variant tags {b.get('sdc_variant','?')}/{i.get('sdc_variant','?')}")
    # 1. check_timing
    cb = [l for l in grab(os.path.join(b['dir'], 'check_timing.txt')).splitlines() if l.strip()]
    ci = [l for l in grab(os.path.join(i['dir'], 'check_timing.txt')).splitlines() if l.strip()]
    # check_timing lists ports/endpoints in hash order: compare as sets
    d = ['+' + l for l in sorted(set(ci) - set(cb))] + ['-' + l for l in sorted(set(cb) - set(ci))]
    def counts(lines):
        t = "\n".join(lines)
        m1 = re.search(r"There are (\d+) endpoints which are not constrained for maximum delay", t)
        m2 = re.search(r"There are (\d+) ports with no clock-relative input delay", t)
        return (int(m1.group(1)) if m1 else 0, int(m2.group(1)) if m2 else 0)
    v.append(f"check_timing: unconstrained endpoints / ports without input delay: base {counts(cb)}  iolat {counts(ci)}  (new warnings in iolat: {sum(1 for l in d if l.startswith('+'))}, removed {sum(1 for l in d if l.startswith('-'))})")
    for l in d[:30]:
        v.append("   " + l)
    # 2. report_clocks
    v.append("report_clocks (iolat):")
    rc_ = grab(os.path.join(i['dir'], 'clocks.txt')).splitlines()
    v += ["   " + l for l in rc_ if l.strip()][:25]
    # 3. spot report: input launch
    for tag, r in (("base", b), ("iolat", i)):
        sp = grab(os.path.join(r['dir'], 'spot_input.txt')).splitlines()
        keep = [l for l in sp if re.search(r"Startpoint|clock (clk_i|clk_io)|clock source latency|clock network delay|input external delay|slack|Endpoint", l)]
        v.append(f"spot input path axi_rdata_i[10] ({tag}): ")
        v += ["   " + l for l in keep][:22]
    v.append("")
open(os.path.join(REP, "validation_nom_tt.txt"), "w").write("\n".join(v) + "\n")
print(f"wrote {REP}/base_vs_iolat.txt, validation_nom_tt.txt  (r2r identical in {len(r2r_diff)-len(bad)}/{len(r2r_diff)} cells)")
