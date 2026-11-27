#!/usr/bin/env python3
"""Sample audit of the faults Quaigh proved untestable on the cell-pin fault list.

usage:
  untestable_audit.py sample  --cut-dir DIR --status status.txt --out sample.json [--per-class 50 --tail 50 --neg-per-class 5 --seed N]
  untestable_audit.py analyse --cut-dir DIR --netlist cut_dir/netlist_cellpin.v --sample sample.json --out analysis.json
  untestable_audit.py report  --analysis analysis.json --md

`sample` lists the proven-untestable faults (status U) that are not on the scan-path pins SCD/SCE, groups them by pin class, and
draws a seeded random sample per class (the ten largest classes, plus one pooled stratum for all other classes).  It also draws
a negative-control sample of faults ATPG detected (status D).  `analyse` decodes every sampled fault to a cell instance and pin,
finds the driving net and fanout cone, names the constant that forces it (cell-level simulation of the Verilog netlist), proves
the verdict again with a SAT solver that is not Quaigh's, and classifies the cause.  `report` gives per-class counts, Wilson
intervals and the extrapolation to the whole untestable set.

Doc: tm:ch:dft-architecture
"""

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cellpin_report import SCAN_PATH_PINS, pin_of  # noqa: E402

TAIL = "(tail)"
CF_BUDGET = 150_000  # conflicts for the exclusion counterfactual; unknown is reported, never counted as testable
# group names, in the order of the report
GROUPS = ("tie-off", "constant-from-logic", "redundant", "scan-path", "artifact", "unresolved")
LABEL_GROUP = {
    "TESTABLE": "artifact", "EXCLUSION_INDUCED": "artifact", "CONST_NOT_IN_NETLIST": "artifact", "CLOCK_ONLY": "artifact",
    "NO_OBSERVATION": "artifact", "SCAN_SHIFT_PATH": "scan-path", "TIE_OFF": "tie-off", "CONST_FROM_ROOT": "constant-from-logic",
    "CONST_FROM_EXCLUSION": "constant-from-logic", "BLOCKED_BY_CONST": "constant-from-logic",
    "REDUNDANT_CONSTANT_NET": "redundant", "REDUNDANT_MASKED": "redundant", "UNRESOLVED": "unresolved",
}


# ---- pure functions ----------------------------------------------------------------------------------------------------------


def fault_site(k: int) -> Tuple[int, int]:
    """Fault k is site k // 2 stuck-at (k % 2)."""
    return k // 2, k % 2


def codes_by_index(lines: Sequence[str], n_faults: int) -> List[str]:
    """Status file lines `k S` -> list of codes by fault index; a missing fault is an error."""
    st = [""] * n_faults
    for ln in lines:
        f = ln.split()
        if len(f) == 2:
            st[int(f[0])] = f[1]
    if "" in st:
        raise ValueError(f"{st.count('')} faults missing from the status list")
    return st


def faults_by_class(sites: Sequence[str], st: Sequence[str], code: str, skip_scan: bool = True) -> Dict[str, List[int]]:
    """Fault indices with status `code`, grouped by pin class.  The scan-path pins SCD / SCE are left out."""
    by: Dict[str, List[int]] = {}
    for k, s in enumerate(st):
        if s != code:
            continue
        p = pin_of(sites[k // 2])
        if skip_scan and p in SCAN_PATH_PINS:
            continue
        by.setdefault(p, []).append(k)
    return by


def top_classes(by: Dict[str, List[int]], n: int = 10) -> List[str]:
    """The n largest classes; ties broken by name so the choice is stable."""
    return [c for c, _ in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:n]]


def draw(items: Sequence[int], n: int, seed: int, label: str) -> List[int]:
    """Seeded sample without replacement.  The generator is keyed by seed and label, so one class's draw never moves another's."""
    rng = random.Random(f"{seed}:{label}")
    return sorted(rng.sample(list(items), min(n, len(items))))


def draw_strata(by: Dict[str, List[int]], per_class: int, tail: int, seed: int, n_top: int = 10) -> List[Dict]:
    """One stratum per top class and one pooled stratum for the rest.  Each: {name, N, faults}."""
    top = top_classes(by, n_top)
    strata = [{"name": c, "N": len(by[c]), "faults": draw(by[c], per_class, seed, c)} for c in top]
    rest = sorted(k for c, v in by.items() if c not in top for k in v)
    if rest:
        strata.append({"name": TAIL, "N": len(rest), "faults": draw(rest, tail, seed, TAIL)})
    return strata


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for k successes in n trials."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def stratified(strata: Sequence[Dict], group: str, z: float = 1.96) -> Dict:
    """Population estimate of one group over strata with sample counts: {name, N, n, k}.
    Point estimate sum(N_h * k_h / n_h); the interval is Wilson on the pooled proportion with the effective sample size
    p(1-p)/var, where var is the stratified variance with finite-population correction."""
    big_n = sum(s["N"] for s in strata)
    est = sum(s["N"] * s["k"][group] / s["n"] for s in strata if s["n"])
    p = est / big_n if big_n else 0.0
    var = sum((s["N"] / big_n) ** 2 * (s["k"][group] / s["n"]) * (1 - s["k"][group] / s["n"]) / s["n"] * (1 - s["n"] / s["N"])
              for s in strata if s["n"] and s["N"])
    n_eff = (p * (1 - p) / var) if var > 0 else sum(s["n"] for s in strata)
    lo, hi = wilson(round(p * n_eff), max(1, round(n_eff)), z) if 0 < p < 1 else wilson(0, sum(s["n"] for s in strata), z)
    if p >= 1:
        lo, hi = wilson(sum(s["n"] for s in strata), sum(s["n"] for s in strata), z)
    return {"estimate": est, "lo": lo * big_n, "hi": hi * big_n, "pct": 100 * p, "pct_lo": 100 * lo, "pct_hi": 100 * hi}


def classify(f: Dict) -> Tuple[str, str]:
    """Cause of one proven-untestable fault from its features.  Returns (label, group).

    Features: excitable (the site can take the opposite of the stuck value in the three-valued simulation),
    const_kind ('tie' | 'literal' | 'root-logic' | 'excl-tie' | 'none': what holds the site at the stuck value), cf_testable
    (a detecting vector exists once the nets the cut's exclusions tie constant are made free), exc_sat ('yes' | 'no' | 'unknown'),
    diff_obs (the fault effect can reach an observation net), struct_obs / struct_clk (observation / clock nets in the structural
    fanout, constants ignored), sat ('testable' | 'untestable' | 'unknown'), verified (a detecting vector re-simulated),
    scan_path_only (every load of the fault's fanout, through buffers, is a flop SCD pin: a shift-path fault that the chain test
    credits, like SCD / SCE)."""
    label = _label(f)
    return label, LABEL_GROUP[label]


def _label(f: Dict) -> str:
    if f.get("sat") == "testable" and f.get("verified"):
        return "TESTABLE"
    if f.get("scan_path_only"):
        return "SCAN_SHIFT_PATH"
    if f.get("cf_testable"):
        return "EXCLUSION_INDUCED"
    if not f["excitable"]:
        kind = f.get("const_kind", "none")
        if kind in ("tie", "literal"):
            return "TIE_OFF"
        if kind == "root-logic":
            return "CONST_FROM_ROOT"
        if kind == "excl-tie":
            return "CONST_FROM_EXCLUSION"  # an exclusion holds it, but freeing the excluded nets does not make it testable
        return "CONST_NOT_IN_NETLIST"
    if not f["diff_obs"]:
        if f.get("struct_obs", 0) > 0:
            return "BLOCKED_BY_CONST"
        if f.get("struct_clk", 0) > 0:
            return "CLOCK_ONLY"
        return "NO_OBSERVATION"
    if f.get("exc_sat") == "no":
        return "REDUNDANT_CONSTANT_NET"
    if f.get("sat") == "untestable":
        return "REDUNDANT_MASKED"
    return "UNRESOLVED"


def scan_path_only(cd, rec: Dict) -> bool:
    """True when the fault's effect can only travel along the scan shift path: from the faulted pin, through buffers and
    delay cells only, to flop SCD pins.  `cd` is a CellDesign."""
    import netlist_lib

    def leaf_ok(net: str, seen: set) -> bool:
        loads = cd.loads.get(net, ())
        if not loads or net in seen:
            return False
        seen.add(net)
        for inst, pin in loads:
            c = cd.cells[inst]
            if pin == "SCD":
                continue
            m = cd.models.get(c.typ.replace("__core", ""))
            if m is None or not netlist_lib.BUF_RE.match(c.typ) or len(m.outputs) != 1 or not leaf_ok(c.pins.get(m.outputs[0], ""), seen):
                return False
        return True

    c = cd.cells.get(rec["inst"])
    if c is None or rec.get("net") is None:
        return False
    if rec["dir"] == "in":
        m = cd.models.get(c.typ.replace("__core", ""))
        if m is None or not netlist_lib.BUF_RE.match(c.typ) or len(m.outputs) != 1:
            return False
        return leaf_ok(c.pins.get(m.outputs[0], ""), set())
    return leaf_ok(rec["net"], set())


def corrected_tc(detected: int, total: int, untestable: int, artifact_faults: float) -> float:
    """Test coverage D / (total - U + A), A = untestable faults that are really testable (counted back into the denominator)."""
    return 100.0 * detected / (total - untestable + artifact_faults)


def rtl_hint(net: Optional[str], modmap: Dict[str, Dict], top: str = "soc_top") -> Optional[str]:
    """`u_a.u_b.sig[3]` -> `rtl/.../b.sv::sig` by following instance names through the module map; None if the first part is unknown."""
    if not net:
        return None
    toks = net.replace("u_dut.", "", 1).split(".")
    mod = top
    path: List[str] = []
    while len(toks) > 1:
        inst = toks[0]
        nxt = modmap.get(mod, {}).get("inst", {}).get(inst)
        if nxt is None:
            break
        path.append(inst)
        mod = nxt
        toks = toks[1:]
    if mod == top and not path:
        return None
    f = modmap.get(mod, {}).get("file", "?")
    return f"{f}::{'.'.join(toks)}"


def build_modmap(rtl_root: Path) -> Dict[str, Dict]:
    """module -> {file, inst: {instance name: module type}} for every .sv under rtl_root (best effort, comments stripped)."""
    mm: Dict[str, Dict] = {}
    inst_re = re.compile(r"\b([A-Za-z_]\w*)\s*(?:#\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))?\s*(u_\w+|g_\w+)\s*\(")
    for p in sorted(rtl_root.rglob("*.sv")):
        txt = re.sub(r"//[^\n]*|/\*.*?\*/", "", p.read_text(errors="replace"), flags=re.S)
        for m in re.finditer(r"\bmodule\s+(\w+)", txt):
            mm.setdefault(m.group(1), {"file": str(p), "inst": {}})
        cur = None
        for m in re.finditer(r"\bmodule\s+(\w+)|" + inst_re.pattern, txt):
            if m.group(1):
                cur = m.group(1)
            elif cur and m.group(2) and m.group(3):
                mm[cur]["inst"][m.group(3)] = m.group(2)
    return mm


def summarise(records: Sequence[Dict], strata: Sequence[Dict]) -> Dict:
    """Per-stratum group counts and the population extrapolation, from analysed records (those with a `class`)."""
    out_strata = []
    for s in strata:
        recs = [r for r in records if r["stratum"] == s["name"] and not r.get("control")]
        k = {g: sum(1 for r in recs if LABEL_GROUP[r["label"]] == g) for g in GROUPS}
        labels: Dict[str, int] = {}
        for r in recs:
            labels[r["label"]] = labels.get(r["label"], 0) + 1
        out_strata.append({"name": s["name"], "N": s["N"], "n": len(recs), "k": k, "labels": labels,
                           "ci": {g: wilson(k[g], len(recs)) for g in GROUPS}})
    pop = {g: stratified(out_strata, g) for g in GROUPS}
    all_labels = sorted({lb for s in out_strata for lb in s["labels"]})
    lab_strata = [{"name": s["name"], "N": s["N"], "n": s["n"], "k": {lb: s["labels"].get(lb, 0) for lb in all_labels}}
                  for s in out_strata]
    pop_labels = {lb: stratified(lab_strata, lb) for lb in all_labels}
    return {"strata": out_strata, "population": pop, "population_labels": pop_labels}


# ---- commands ----------------------------------------------------------------------------------------------------------------


def cmd_sample(a) -> int:
    sites = (Path(a.cut_dir) / "cut_sites.txt").read_text().split()
    st = codes_by_index(Path(a.status).read_text().split("\n"), 2 * len(sites))
    u = faults_by_class(sites, st, "U")
    d = faults_by_class(sites, st, "D")
    strata = draw_strata(u, a.per_class, a.tail, a.seed)
    top = [s["name"] for s in strata if s["name"] != TAIL]
    ctrl = [{"name": c, "N": len(d[c]), "faults": draw(d[c], a.neg_per_class, a.seed, "D:" + c)} for c in top if c in d]
    res = {"seed": a.seed, "per_class": a.per_class, "tail": a.tail, "neg_per_class": a.neg_per_class,
           "n_faults": len(st), "untestable_nonscan": sum(len(v) for v in u.values()),
           "untestable_by_class": {c: len(v) for c, v in sorted(u.items(), key=lambda kv: -len(kv[1]))},
           "status_counts": {c: st.count(c) for c in "DURN"},
           "strata": strata, "control": ctrl}
    Path(a.out).write_text(json.dumps(res, indent=1))
    print(json.dumps({"untestable_nonscan": res["untestable_nonscan"], "sampled": sum(len(s["faults"]) for s in strata),
                      "control": sum(len(s["faults"]) for s in ctrl)}))
    return 0


def real_out_pin(cd, inst: str, pin: str) -> str:
    """An output-pin buffer whose core is a plain wire (a buffer or delay cell) reads the input-pin buffer, so its name says
    `cvtpin_<input pin>`.  The faulted pin is then the cell's single output pin."""
    c = cd.cells.get(inst)
    m = cd.models.get(c.typ.replace("__core", "")) if c else None
    return m.outputs[0] if m and pin in m.inputs and len(m.outputs) == 1 else pin


def _site_pin(b, cd, site_name: str) -> Tuple[str, str, str]:
    """(instance, pin, 'in'|'out') of a site net, as Yosys names the instance without the `u_dut.` prefix.
    The output buffer of a tie cell has a constant behind it (no `cvtpin_` name); the cell is then found through the load
    pin the site net is named after (`u_dut.<load inst>.<pin>`)."""
    if ".cvtpin_" in site_name:
        inst, pin = site_name.rsplit(".cvtpin_", 1)
        return inst[len("u_dut."):], pin, "in"
    g = b.gin[b.id[site_name]]
    inner = b.name[g[0]] if g else ""
    if ".cvtpin_" not in inner:
        load_inst, load_pin = site_name[len("u_dut."):].rsplit(".", 1)
        lc = cd.cells.get(load_inst)
        drv = cd.driver.get(lc.pins.get(load_pin)) if lc else None
        if inner not in ("$false", "$true") or drv is None:
            raise SystemExit(f"site {site_name}: no pin buffer behind it")
        return drv[0], drv[1], "out"
    inst, pin = inner.rsplit(".cvtpin_", 1)
    return inst[len("u_dut."):], real_out_pin(cd, inst[len("u_dut."):], pin), "out"


def _features(b, cd, k: int, sites: Sequence[str], cls: str, stratum: str, modmap, control: bool, do_sat: bool) -> Dict:
    import audit_graph as ag

    sidx, v = fault_site(k)
    name = sites[sidx]
    site = b.id[name]
    inst, pin, d = _site_pin(b, cd, name)
    cell = cd.cells.get(inst)
    net = cell.pins.get(pin) if cell else None
    drv = cd.driver.get(net) if net else None
    rec: Dict = {"k": k, "class": cls, "stratum": stratum, "control": control, "site": name, "stuck": v, "inst": inst, "pin": pin,
                 "dir": d, "cell_type": cell.typ if cell else None, "net": net,
                 "driver": ({"inst": drv[0], "type": cd.cells[drv[0]].typ, "pin": drv[1]} if drv else None),
                 "net_loads": len(cd.loads.get(net, ())) if net else None, "blif_value": int(b.val[site])}
    rec["excitable"] = b.val[site] != v
    fv = b.cone(site, v) if rec["excitable"] else {}
    rec["cone_nets"] = len(fv)
    rec["cone_obs"] = sum(1 for n in fv if b.obs[n])
    rec["diff_obs"] = rec["cone_obs"] > 0
    sg, so, sc = b.struct_reach(site)
    rec.update(struct_gates=sg, struct_obs=so, struct_clk=sc)
    if not rec["excitable"] and net is not None:
        rec["const_net_info"] = cd.const_roots([net])[net]
        rec["const_kind"] = rec["const_net_info"]["kind"] if rec["const_net_info"]["value"] == v else "none"
    elif not rec["excitable"]:
        rec["const_kind"] = "none"
    rec["exc_sat"] = "n/a"
    rec["sat"] = "n/a"
    if rec["excitable"] and do_sat:
        rec["exc_sat"] = ag.sat_excitable(b, site, v)
        if rec["exc_sat"] != "no":
            r = ag.sat_testable(b, site, v, fv) if rec["diff_obs"] else {"result": "untestable", "verified": True}
            rec["sat"], rec["verified"], rec["miter_gates"] = r["result"], r["verified"], r.get("gates")
            if r["result"] == "untestable" and fv:
                rec["random_1024_detects"] = ag.random_detect(b, site, v, fv)
    rec["scan_path_only"] = scan_path_only(cd, rec)
    rec["label"], rec["group"] = classify(rec)
    if b.relaxed and rec["group"] != "tie-off" and rec["label"] != "TESTABLE" and do_sat:
        # counterfactual: the same fault with the nets the cut's exclusions tie constant left free
        b.mode(True)
        try:
            exc_f = b.val[site] != v
            fvf = b.cone(site, v) if exc_f else {}
            rec["cf_excitable"], rec["cf_diff_obs"] = exc_f, any(b.obs[n] for n in fvf)
            if rec["cf_diff_obs"]:
                r = ag.sat_testable(b, site, v, fvf, conf_budget=CF_BUDGET)
                rec["cf_sat"] = r["result"]  # testable | untestable | unknown
                rec["cf_testable"] = r["result"] == "testable" and r["verified"]
        finally:
            b.mode(False)
        if rec.get("cf_testable"):
            rec["label"], rec["group"] = classify(rec)
    near = cd.named_near(net) if net else None
    rec["near_net"] = near
    rec["rtl"] = rtl_hint(near, modmap)
    return rec


def cmd_analyse(a) -> int:
    import audit_graph as ag

    cut = Path(a.cut_dir)
    sample = json.loads(Path(a.sample).read_text())
    sites = (cut / "cut_sites.txt").read_text().split()
    b = ag.Blif()
    b.parse((cut / "cut.blif").read_text())
    print(f"blif: {len(b.name)} nets, {len(b.order)} gates, {b.n_latches} latches", flush=True)
    cd = ag.CellDesign(Path(a.netlist), cut / "libcells.v")
    print(f"cells: {len(cd.cells)}, exclusion ties: {len(cd.assign_tie)}", flush=True)
    groups = {b.id[f"u_dut.{i}.cvtpin_{p}"]: n for n in cd.assign_tie for i, p in cd.loads.get(n, ()) if f"u_dut.{i}.cvtpin_{p}" in b.id}
    b.set_relaxed(groups, groups)
    print(f"free mode: {len(b.relaxed)} pin nets of exclusion-tied nets relaxed, "
          f"{sum(1 for o in b.order if b.val_free[o] != b.val_base[o])} constants lost", flush=True)
    modmap = build_modmap(Path(a.rtl))
    recs: List[Dict] = []
    for ctrl, groups in ((False, sample["strata"]), (True, sample["control"])):
        for s in groups:
            for k in s["faults"]:
                recs.append(_features(b, cd, k, sites, pin_of(sites[k // 2]), s["name"], modmap, ctrl, not a.no_sat))
                if len(recs) % 25 == 0:
                    print(len(recs), flush=True)
    Path(a.out).write_text(json.dumps({"sample": {k: sample[k] for k in sample if k not in ("strata", "control")},
                                       "strata": [{k: s[k] for k in ("name", "N")} for s in sample["strata"]],
                                       "records": recs}, indent=1))
    return 0


def cmd_attribute(a) -> int:
    """For each sampled fault that depends on an exclusion tie: which single exclusion group, freed alone, makes the fault
    excitable and its effect able to reach an observation net (three-valued test; `cf_groups` in the records)."""
    import audit_graph as ag

    cut = Path(a.cut_dir)
    b = ag.Blif()
    b.parse((cut / "cut.blif").read_text())
    cd = ag.CellDesign(Path(a.netlist), cut / "libcells.v")
    pins: Dict[str, set] = {}
    for n in cd.assign_tie:
        for i, p in cd.loads.get(n, ()):
            nm = f"u_dut.{i}.cvtpin_{p}"
            if nm in b.id:
                pins.setdefault(ag.excl_group(n), set()).add(b.id[nm])
    an = json.loads(Path(a.analysis).read_text())
    for r in an["records"]:
        if r["dir"] == "out" and r["cell_type"]:
            pin = real_out_pin(cd, r["inst"], r["pin"])
            if pin != r["pin"]:
                r["pin"], r["net"] = pin, cd.cells[r["inst"]].pins.get(pin)
        r["scan_path_only"] = scan_path_only(cd, r)
        r["label"], r["group"] = classify(r)
    targets = [r for r in an["records"] if r["label"] in ("EXCLUSION_INDUCED", "CONST_FROM_EXCLUSION") and not r.get("control")]
    for r in targets:
        r["cf_groups"] = []
    for g, ids in sorted(pins.items()):
        b.set_relaxed(ids)
        b.mode(True)
        for r in targets:
            site, v = b.id[r["site"]], r["stuck"]
            if b.val[site] != v and any(b.obs[n] for n in b.cone(site, v)):
                r["cf_groups"].append(g)
        b.mode(False)
    Path(a.out).write_text(json.dumps(an, indent=1))
    cnt: Dict[str, int] = {}
    for r in targets:
        for g in r["cf_groups"] or ["(no single group)"]:
            cnt[g] = cnt.get(g, 0) + 1
    print(json.dumps({"targets": len(targets), "by_group": dict(sorted(cnt.items(), key=lambda kv: -kv[1]))}, indent=1))
    return 0


def fmt_ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.1f}%, {100 * lo:.1f}-{100 * hi:.1f}%)" if n else "-"


def cmd_report(a) -> int:
    an = json.loads(Path(a.analysis).read_text())
    summ = summarise(an["records"], an["strata"])
    ctrl = [r for r in an["records"] if r.get("control")]
    lines = ["| class | N | n | " + " | ".join(GROUPS) + " |", "|" + "---|" * (3 + len(GROUPS))]
    for s in summ["strata"]:
        lines.append(f"| {s['name']} | {s['N']} | {s['n']} | " + " | ".join(str(s["k"][g]) for g in GROUPS) + " |")
    lines += ["", "population (extrapolated, Wilson on the effective sample size):"]
    for g in GROUPS:
        p = summ["population"][g]
        lines.append(f"- {g}: {p['estimate']:.0f} ({p['pct']:.1f}%, 95% {p['pct_lo']:.1f}-{p['pct_hi']:.1f}%; {p['lo']:.0f}-{p['hi']:.0f} faults)")
    lines += ["", "by label:"]
    for lb, p in summ["population_labels"].items():
        lines.append(f"- {lb}: {p['estimate']:.0f} ({p['pct']:.1f}%, 95% {p['pct_lo']:.1f}-{p['pct_hi']:.1f}%; {p['lo']:.0f}-{p['hi']:.0f} faults)")
    lines += ["", f"negative control: {len(ctrl)} detected faults classified; labels: "
              + json.dumps({lb: sum(1 for r in ctrl if r['label'] == lb) for lb in sorted({r['label'] for r in ctrl})})]
    print("\n".join(lines) if a.md else json.dumps(summ))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--cut-dir", required=True)
    s.add_argument("--status", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--per-class", type=int, default=50)
    s.add_argument("--tail", type=int, default=50)
    s.add_argument("--neg-per-class", type=int, default=5)
    s.add_argument("--seed", type=int, default=244)
    s.set_defaults(fn=cmd_sample)
    n = sub.add_parser("analyse")
    n.add_argument("--cut-dir", required=True)
    n.add_argument("--netlist", required=True)
    n.add_argument("--sample", required=True)
    n.add_argument("--out", required=True)
    n.add_argument("--rtl", default=str(Path(__file__).resolve().parents[3] / "rtl"))
    n.add_argument("--no-sat", action="store_true")
    n.set_defaults(fn=cmd_analyse)
    t = sub.add_parser("attribute")
    t.add_argument("--cut-dir", required=True)
    t.add_argument("--netlist", required=True)
    t.add_argument("--analysis", required=True)
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_attribute)
    r = sub.add_parser("report")
    r.add_argument("--analysis", required=True)
    r.add_argument("--md", action="store_true")
    r.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
