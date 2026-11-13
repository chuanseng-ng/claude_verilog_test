#!/usr/bin/env python3
"""Normalise the committed results of the Sky130 ``rv32i_cpu_top`` flow comparison
(OpenROAD/LibreLane, Synopsys DC -> ICC2, Cadence Genus -> Innovus) into one JSON.

    python3 -I pnr/commercial/compare/compare.py            # writes comparison.json
    python3 -I pnr/commercial/compare/compare.py --check    # exit 1 if comparison.json is stale

Reads committed files only (``pnr/commercial/...`` reports, ``compare/snapshot/``
written once by ``snapshot_sources.py``).  Starts no EDA tool.

Every leaf is an *entry*: ``{"value", "unit", "label", "source", ...}`` where
``label`` is one of

* ``judge``   StarRC (tuned ITF) -> PrimeTime / PrimePower, the same for every arm;
* ``native``  the implementation tool's own report (own RC, own SDC, own engine);
* ``signoff`` an open sign-off deck run identically on every arm (KLayout, Magic,
              Netgen, OpenROAD ``check_antennas``) or the LEC / RedHawk run;
* ``derived`` computed here from committed files by one uniform rule (``rule``);

and ``source`` is a repo-relative path (or list of paths).  ``kind: "prose"`` marks a
figure that exists only in a committed markdown report (``locator`` says where).
Judge corner records use ``values`` (a dict) with one ``source``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COM = "pnr/commercial"
SNAP = f"{COM}/compare/snapshot"
OUT = f"{COM}/compare/comparison.json"
CORNERS = [f"{rc}_{lib}" for rc in ("nom", "min", "max") for lib in ("tt", "ss", "ff")]
VARIANTS = ("own", "base", "iolat", "iolat_pv", "iolat_pvs")

# b7 = b6 + one combined ECO pass (ff hold buffers, deck-antenna sink buffers, dcache dout0 buffers; docs/COMMERCIAL_FLOW_COMPARISON.md section 7 items 4-6).
# ADOPT_B7 decides which generation is the FINAL arm of the comparison (the other becomes a history arm); set by the sign-off decision, never silently.
# b8 = b6 flow on the FLIPPED I-cache floorplan (pnr/sky130/cpu/macro_placement_flipic.cfg) + the b7 ECO set with dout0 buffers on every max-cap pin (user decision 2026-11-08).
# b9 = b8 + ICC2 ECO round 3 (ICC2 only): the two input-port diodes moved next to their loads, one antenna diode moved off an abutting li1 pin pair (docs section 4.9, items 12-14).  Innovus b9 (2026-11-12) = Innovus b8 + one post-route optDesign re-time of the APB read path (section 4.9); judged against Innovus b6 by regress_check.py and NOT adopted (FINAL_GEN_INN stays b6).
# FINAL_GEN is the generation that is the FINAL arm of the comparison ("b6" .. "b11"); the others are history arms.  Set by the sign-off decision, never silently.
ADOPT_B7 = False
# 2026-11-09 user decision: the FINAL generation is set per tool.  ICC2 -> b9 (user sign-off: the ss setup margin shift of the I-cache SRAM flip is accepted).
# Innovus -> set by the Innovus adoption rule (no check worse than Innovus b6 apart from measured buffer cost and the user-accepted MET setup/hold shifts of the I-cache flip; no check worse than the previous generation).
# 2026-11-13: Innovus b9 and b10 did not meet it (max-transition at ss); Innovus b11 (b10 + the three repeaters resized buf_6 -> buf_12) does: regress_check.py innovus b11 = 25 worse (all the accepted 7 setup + 18 hold shifts), innovus b11 b10 = 0 worse.
FINAL_GEN_ICC2 = "b9"
FINAL_GEN_INN = "b11"
FINAL_GEN = FINAL_GEN_ICC2  # legacy name: the ICC2 generation


def _role(tool, gen):
    return "final" if (FINAL_GEN_ICC2 if tool == "icc2" else FINAL_GEN_INN) == gen else "history"


_R6 = _role("icc2", "b6")
_R7 = _role("icc2", "b7")
_R8 = _role("icc2", "b8")
_R9 = _role("icc2", "b9")
_R6_INN = _role("innovus", "b6")
_R7_INN = _role("innovus", "b7")
_R8_INN = _role("innovus", "b8")
_R9_INN = _role("innovus", "b9")
_R10_INN = _role("innovus", "b10")
_R11_INN = _role("innovus", "b11")

# arm id -> PT arm name, display name, role, synthesis, notes
ARMS = {
    "openroad_b2": dict(
        pt="openroad",
        name="OpenROAD/LibreLane B2",
        role="final",
        synthesis="Yosys/ABC (LibreLane, SYNTH_STRATEGY DELAY 3)",
        pnr="LibreLane 2.4.13 + OpenROAD edf00dff (container)",
    ),
    "icc2_b6": dict(
        pt="icc2b6",
        name="ICC2 b6",
        role=_R6,
        synthesis="DC-NXT v2 (MCMM ss/tt/ff, compile_ultra -spg)",
        pnr="ICC2 X-2025.06-SP1, MCMM func_ss/tt/ff, 3-pane NDM",
    ),
    "innovus_b6": dict(
        pt="innovusb6",
        name="Innovus b6",
        role=_R6_INN,
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus 23.14, full MMMC av_ss/av_tt/av_ff, captbl6",
    ),
    "icc2_b7": dict(
        pt="icc2b7",
        name="ICC2 b7",
        role=_R7,
        synthesis="DC-NXT v2 (MCMM ss/tt/ff, compile_ultra -spg)",
        pnr="ICC2 X-2025.06-SP1, b6 + ECO: 21 ff-hold buf_1, 1 antenna-sink buf_6, 4 dcache dout0 buffers",
    ),
    "innovus_b7": dict(
        pt="innovusb7",
        name="Innovus b7",
        role=_R7_INN,
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus 23.14, b6 + ECO: 2 antenna-sink buf_6, 1 dcache dout0 buffer",
    ),
    "icc2_b8": dict(
        pt="icc2b8",
        name="ICC2 b8",
        role=_R8,
        synthesis="DC-NXT v2 (MCMM ss/tt/ff, compile_ultra -spg)",
        pnr="ICC2 X-2025.06-SP1, flipped I-cache floorplan (FS), b7 ECO set, dout0 buffers on every max-cap pin",
    ),
    "icc2_b9": dict(
        pt="icc2b9",
        name="ICC2 b9",
        role=_R9,
        synthesis="DC-NXT v2 (MCMM ss/tt/ff, compile_ultra -spg)",
        pnr="ICC2 X-2025.06-SP1, b8 + ECO round 3: 2 port diodes moved next to the loads, 1 antenna diode moved (no cells added)",
    ),
    "innovus_b8": dict(
        pt="innovusb8",
        name="Innovus b8",
        role=_R8_INN,
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus 23.14, flipped I-cache floorplan (MX), b7 ECO set, dout0 buffers on every max-cap pin",
    ),
    "innovus_b9": dict(
        pt="innovusb9",
        name="Innovus b9",
        role=_R9_INN,
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus 23.14, b8 + ECO round 3 (post-route optDesign setup/DRV re-time of the apb_paddr_i -> apb_prdata_o_reg paths and the max-transition violators)",
    ),
    "innovus_b10": dict(
        pt="innovusb10",
        name="Innovus b10",
        role=_R10_INN,
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus 23.14, b9 + max-transition root-cause ECO (3 buf_6 repeaters in the SRAM gap columns on the three scattered-load nets; the apb_prdata_o port nets are left as in b9)",
    ),
    "innovus_b11": dict(
        pt="innovusb11",
        name="Innovus b11",
        role=_R11_INN,
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus 23.14, b10 + slew fix (the three b10 repeaters B10N1, u_core/B10N2, u_core/B10N3 resized buf_6 -> buf_12 in place; nothing else changes)",
    ),
    "icc2_b5e": dict(
        pt="icc2",
        name="ICC2 b5e",
        role="history",
        synthesis="DC-NXT v1 (tt only)",
        pnr="ICC2, single tt scenario",
    ),
    "icc2_b5i": dict(
        pt="icc2b5i",
        name="ICC2 b5i",
        role="history",
        synthesis="DC-NXT v1 (tt only)",
        pnr="ICC2, b5e + routing ECO",
    ),
    "icc2_b5m": dict(
        pt="icc2b5m",
        name="ICC2 b5m",
        role="history",
        synthesis="DC-NXT v1 (tt only)",
        pnr="ICC2, b5i + PDN trim + 556 diodes",
    ),
    "innovus_b5h": dict(
        pt="innovusb5h",
        name="Innovus b5h",
        role="history",
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus, tt, captbl nom",
    ),
    "innovus_b5j": dict(
        pt="innovusb5j",
        name="Innovus b5j",
        role="history",
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus, b5h + 146 taps",
    ),
    "innovus_b5k": dict(
        pt="innovusb5k",
        name="Innovus b5k",
        role="history",
        synthesis="Genus 23.14 v1 (tt only)",
        pnr="Innovus, b5j + ECO round 2",
    ),
}

SDC_FILES = {
    "base": "pnr/sky130/cpu/constraints/sky130_cpu.sdc",
    "iolat": f"{COM}/constraints/sky130_cpu_iolat.sdc",
    "iolat_pv": f"{COM}/constraints/sky130_cpu_iolat_pv.sdc",
    "iolat_pvs": f"{COM}/constraints/sky130_cpu_iolat_pv.sdc",
    "own:icc2_b6": f"{COM}/constraints/sky130_cpu_icc2_b6_own_pt.sdc",
    "own:icc2_b7": f"{COM}/constraints/sky130_cpu_icc2_b7_own_pt.sdc",
    "own:icc2_b8": f"{COM}/constraints/sky130_cpu_icc2_b8_own_pt.sdc",
    "own:icc2_b9": f"{COM}/constraints/sky130_cpu_icc2_b9_own_pt.sdc",
    "own:innovus_b8": f"{COM}/constraints/sky130_cpu_innovus_b8_own_pt.sdc",
    "own:innovus_b9": f"{COM}/constraints/sky130_cpu_innovus_b9_own_pt.sdc",
    "own:innovus_b10": f"{COM}/constraints/sky130_cpu_innovus_b10_own_pt.sdc",
    "own:innovus_b11": f"{COM}/constraints/sky130_cpu_innovus_b11_own_pt.sdc",
    "own:innovus_b7": f"{COM}/constraints/sky130_cpu_innovus_b7_own_pt.sdc",
    "own:innovus_b6": f"{COM}/constraints/sky130_cpu_innovus_b6_own_pt.sdc",
    "own:innovus_b5k": f"{COM}/constraints/sky130_cpu_innovus_b5k_own_pt.sdc",
    "own:innovus_b5h": f"{COM}/constraints/sky130_cpu_innovus_b5h_own_pt.sdc",
    "own:innovus_b5j": f"{COM}/constraints/sky130_cpu_innovus_b5h_own_pt.sdc",
}

warnings: list[str] = []
_TRACKED: set[str] | None = None


def tracked(path: str) -> bool:
    """True if the path is in the git index (committed or staged): untracked scratch is never a source."""
    global _TRACKED
    if _TRACKED is None:
        import subprocess

        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, check=True
        ).stdout
        _TRACKED = set(out.decode().split("\0"))
    return path in _TRACKED


# ----------------------------------------------------------------------------- helpers
def p(path: str) -> Path:
    return REPO / path


def text(path: str) -> str:
    return p(path).read_text(errors="replace")


def E(value, unit, label, source, **kw):
    e = {"value": value, "unit": unit, "label": label, "source": source}
    e.update({k: v for k, v in kw.items() if v is not None})
    return e


def prose(value, unit, label, source, locator, **kw):
    return E(value, unit, label, source, kind="prose", locator=locator, **kw)


def grab(path: str, pattern: str, cast=float, group=1, flags=re.M):
    m = re.search(pattern, text(path), flags)
    if not m:
        warnings.append(f"pattern not found in {path}: {pattern}")
        return None
    return cast(m.group(group).replace(",", ""))


def tsv(path: str) -> dict:
    d = {}
    for line in text(path).splitlines():
        k, _, v = line.partition("\t")
        d[k] = v
    return d


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f == 1e9:  # PT collector sentinel: no path in the group
        return None
    return int(f) if re.fullmatch(r"-?\d+", str(v)) else f


def hms(s: str) -> float:
    parts = [float(x) for x in s.strip().split(":")]
    t = 0.0
    for x in parts:
        t = t * 60 + x
    return t


def time_v(path: str):
    t = text(path)
    wall = re.search(r"Elapsed \(wall clock\) time.*?:\s*([\d:.]+)\s*$", t, re.M)
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", t)
    return (hms(wall.group(1)) if wall else None, int(rss.group(1)) if rss else None)


# ----------------------------------------------------------------------------- judge
def judge_record(var: str, ptarm: str, corner: str):
    base = f"{SNAP}/pt/{var}/{ptarm}_{corner}"
    if not p(f"{base}/metrics.tsv").is_file():
        return None
    m = tsv(f"{base}/metrics.tsv")
    keys = [
        "setup_wns",
        "setup_tns",
        "setup_viol",
        "hold_wns",
        "hold_tns",
        "hold_viol",
        "r2rx_setup_wns",
        "r2rx_setup_tns",
        "r2rx_setup_viol",
        "r2rx_hold_wns",
        "r2rx_hold_tns",
        "r2rx_hold_viol",
        "setup_worst_start",
        "setup_worst_end",
        "hold_worst_start",
        "hold_worst_end",
        "sdc_md5",
        "sdc_variant",
        "leaf_cells",
        "lib_corner",
        "rc_corner",
    ]
    rec = {
        "label": "judge",
        "source": f"{base}/metrics.tsv",
        "unit": "ns / count",
        "values": {k: num(m.get(k)) for k in keys if k in m},
    }
    # reg-to-reg vs I/O split from report_global_timing (Total, reg->reg, in->reg, reg->out, in->out)
    gt = f"{base}/global_timing.txt"
    if p(gt).is_file():
        split = {}
        for kind, blk in re.findall(
            r"^(Setup|Hold) violations\n-+\n.*?\n-+\n(.*?)\n-+", text(gt), re.M | re.S
        ):
            rows = {r.split()[0]: r.split()[1:] for r in blk.splitlines() if r.strip()}
            k = kind.lower()
            n = [int(x) for x in rows["NUM"]]
            w = [float(x) for x in rows["WNS"]]
            split[k] = {
                "viol_total": n[0],
                "viol_r2r": n[1],
                "viol_io": sum(n[2:]),
                "wns_r2r": w[1],
                "wns_io": min(w[2:]),
            }
        rec["io_split"] = {
            "label": "judge",
            "source": gt,
            "unit": "ns / count",
            "values": split or {"setup": None, "hold": None},
            "note": "report_global_timing: missing kind = no violations",
        }
    return rec


def power_b(var: str, ptarm: str):
    path = f"{SNAP}/pt/{var}/{ptarm}_nom_tt/power_B.txt"
    if not p(path).is_file():
        return None
    t = text(path)
    out = {"total_mW": float(re.search(r"^Total Power\s*=\s*([-\d.e+]+)", t, re.M).group(1)) * 1e3}
    for g in ("clock_network", "register", "combinational", "memory"):
        m = re.search(rf"^{g}\s+\S+\s+\S+\s+\S+\s+([-\d.e+]+)", t, re.M)
        if m:
            out[f"{g}_mW"] = float(m.group(1)) * 1e3
    return {
        "label": "judge",
        "unit": "mW",
        "source": path,
        "values": out,
        "note": "PrimePower vectorless variant B (0.1 toggle / 0.5 static prob on inputs and register outputs), nom_tt",
    }


def judge_drv(ptarm: str):
    path = f"{SNAP}/pt/base/{ptarm}_nom_tt/constraint_drv.txt"
    if not p(path).is_file():
        return None
    cnt = {"max_transition": 0, "max_capacitance": 0, "max_fanout": 0}
    cur = None
    for line in text(path).splitlines():
        s = line.strip()
        if s in cnt:
            cur = s
        elif cur and "(VIOLATED)" in line:
            cnt[cur] += 1
    return {
        "label": "judge",
        "unit": "violating pins",
        "source": path,
        "values": cnt,
        "note": "PrimeTime report_constraint -all_violators, nom_tt, base SDC",
    }


def judge_drv_all(ptarm: str):
    """DRV violators of the base-SDC judge at all 9 corners (snapshot/drv_counts.tsv, derived from PrimeTime report_constraint)."""
    f = f"{SNAP}/drv_counts.tsv"
    if not p(f).is_file():
        return None
    vals = {}
    for line in text(f).splitlines()[1:]:
        a, c, d0, co, tr, fo = line.split("\t")
        if a == ptarm:
            vals[c] = {"max_cap_dout0": int(d0), "max_cap_other": int(co), "max_tran": int(tr), "max_fanout": int(fo)}
    if len(vals) != 9:
        return None
    return {
        "label": "judge",
        "unit": "pins",
        "source": f,
        "values": vals,
        "note": "PrimeTime report_constraint -all_violators on the base SDC; dout0 = the SRAM dout0 pins (max_capacitance 0.02756 pF, the top of the characterised load table)",
    }


def judge_summary(arm: str, rec_by_corner: dict, var: str):
    """Aggregates over the 9 corners of one SDC variant (derived from the judge records)."""
    recs = [r for r in rec_by_corner.values() if r]
    if len(recs) != 9:
        return None
    v = [r["values"] for r in recs]
    srcs = [r["source"] for r in recs]

    def worst(k):
        xs = [x[k] for x in v if x.get(k) is not None]
        return min(xs) if xs else None

    out = {
        "setup_wns_worst": worst("setup_wns"),
        "hold_wns_worst": worst("hold_wns"),
        "setup_tns_sum": round(sum(x["setup_tns"] for x in v), 3),
        "hold_tns_sum": round(sum(x["hold_tns"] for x in v), 3),
        "setup_viol_sum": sum(x["setup_viol"] for x in v),
        "hold_viol_sum": sum(x["hold_viol"] for x in v),
        "r2r_setup_viol_sum": sum(x["r2rx_setup_viol"] for x in v),
        "r2r_hold_viol_sum": sum(x["r2rx_hold_viol"] for x in v),
        "corners_setup_clean": sum(1 for x in v if x["setup_viol"] == 0),
        "corners_hold_clean": sum(1 for x in v if x["hold_viol"] == 0),
        "corners_r2r_clean": sum(
            1 for x in v if x["r2rx_setup_viol"] == 0 and x["r2rx_hold_viol"] == 0
        ),
    }
    return {
        "label": "derived",
        "unit": "ns / count",
        "source": srcs,
        "values": out,
        "rule": f"min / sum / count over the 9 judge corners, SDC variant {var}; viol = violating endpoints",
    }


# ----------------------------------------------------------------------------- census
FLOP = re.compile(r"__(s?df|edf|sedf|dl[xr])")
BUF = re.compile(r"__(buf|bufbuf|clkbuf|clkdlybuf\w*|dlygate\w*|dlymetal\w*|probec?_p)_")
INV = re.compile(r"__(inv|clkinv|clkinvlp|bufinv)_")
PHYS = re.compile(r"__(tapvpwrvgnd|fill|decap|fakediode|lpflow_\w*tap)")


def census(path: str):
    area = {}
    for line in text(f"{SNAP}/cell_area.tsv").splitlines()[1:]:
        c, _, _, a = line.split("\t")
        area[c] = float(a)
    c = {
        "logical_cells": 0,
        "flops": 0,
        "buffers": 0,
        "inverters": 0,
        "diodes": 0,
        "physical_cells": 0,
        "sram_macros": 0,
        "logical_area_um2": 0.0,
        "buffer_area_um2": 0.0,
        "unknown_area_cells": 0,
    }
    for line in text(path).splitlines():
        if not line.strip():
            continue
        name, n = line.split()[0], int(line.split()[1])
        if name.startswith("sky130_sram"):
            c["sram_macros"] += n
            continue
        if PHYS.search(name):
            c["physical_cells"] += n
            continue
        if name.endswith("diode_2"):
            c["diodes"] += n
            continue
        c["logical_cells"] += n
        if name not in area:
            c["unknown_area_cells"] += n
        a = area.get(name, 0.0) * n
        c["logical_area_um2"] += a
        if FLOP.search(name):
            c["flops"] += n
        elif BUF.search(name):
            c["buffers"] += n
            c["buffer_area_um2"] += a
        elif INV.search(name):
            c["inverters"] += n
    c["logical_area_um2"] = round(c["logical_area_um2"], 1)
    c["buffer_area_um2"] = round(c["buffer_area_um2"], 1)
    return {
        "label": "derived",
        "unit": "count / um2",
        "source": [path, f"{SNAP}/cell_area.tsv"],
        "values": c,
        "rule": (
            "one rule for every arm: logical = all std cells except tap/fill/decap/diode/SRAM; "
            "flops = df*/edf*/sdf*/dl[xr]*; buffers = buf/bufbuf/clkbuf/clkdlybuf/dlygate/dlymetal; "
            "inverters = inv/clkinv/bufinv; area = count x LEF SIZE (diodes excluded)"
        ),
    }


# ----------------------------------------------------------------------------- per-arm native/sign-off
def drclvs(tag: str):
    d = f"{COM}/signoff/drclvs/reports"
    out = {}
    k = f"{d}/{tag}_klayout_drc_by_rule.txt"
    if tracked(k):
        out["klayout_drc"] = E(
            grab(k, r"TOTAL_VIOLATION_ITEMS\s+(\d+)", int),
            "items",
            "signoff",
            k,
            note="sky130A_mr.drc, LibreLane options",
        )
    for var, suf in (
        ("as_delivered", "lvsgds_netgen"),
        ("clean", "lvsgds_clean_netgen"),
        ("merged", "lvsgds_merged_netgen"),
    ):
        f = f"{d}/{tag}_{suf}.rpt.full"
        if tracked(f):
            t = text(f)
            res = re.search(r"Final result:\s*(.*?)\.?\s*$", t, re.M).group(1)
            nets = re.search(r"Number of nets:\s*(\d+).*?\|\s*Number of nets:\s*(\d+)", t)
            devs = re.search(r"Number of devices:\s*(\d+).*?\|\s*Number of devices:\s*(\d+)", t)
            out[f"lvs_{var}"] = E(
                res,
                "verdict",
                "signoff",
                f,
                nets=[int(nets.group(1)), int(nets.group(2))] if nets else None,
                devices=[int(devs.group(1)), int(devs.group(2))] if devs else None,
                note="Netgen, GDS-mode Magic extraction; [layout, schematic]",
            )
    for f in (f"{d}/{tag}_antenna.rpt", f"{d}/{tag}_summary.txt"):
        if tracked(f) and "ANT-0002" in text(f) and "antenna_deck_nets" not in out:
            out["antenna_deck_nets"] = E(
                grab(f, r"ANT-0002\] Found (\d+) net", int),
                "nets",
                "signoff",
                f,
                note="OpenROAD check_antennas (the deck rule) on the final DEF",
            )
            out["antenna_deck_pins"] = E(
                grab(f, r"ANT-0001\] Found (\d+) pin", int), "pins", "signoff", f
            )
    fg, fl = f"{d}/{tag}_magic_drc_real_stdgds_by_rule.tsv", f"{d}/{tag}_magic_drc_real_by_rule.tsv"
    if tracked(fg):
        out.update(magic(fg))
        if tracked(fl):
            out.update(magic(fl, "magic_lef_"))
    elif tracked(fl):
        out.update(magic(fl))
    out.update(nwell4_nsc(tag))
    return out


def magic(f: str, pre: str = "magic_"):
    """Per-rule Magic DRC classification (inside / straddling / outside the SRAM footprints) of one run.
    pre='magic_' is the sign-off figure (std cells from the GDS since 2026-11-08); pre='magic_lef_' the LEF-abstract history mode."""
    ins = st = outs = 0
    nw = [0, 0, 0]
    rules = {}
    for line in text(f).splitlines()[1:]:
        r = line.split("\t")
        if line.startswith("#") or len(r) < 4:
            continue
        a, b, c = int(r[1]), int(r[2]), int(r[3])
        ins, st, outs = ins + a, st + b, outs + c
        rules[r[0]] = [a, b, c]
        if "nwell.4" in r[0]:
            nw = [a, b, c]
    mode = "std cells from the layout GDS" if pre == "magic_" else "std cells as PDK LEF abstracts (history; abstracts carry no tap contact)"
    return {
        pre + "drc_total": E(ins + st + outs, "items", "signoff", f, note=mode),
        pre + "drc_inside_sram": E(
            ins, "items", "signoff", f, note="bead 45a SRAM-abstract artefact"
        ),
        pre + "drc_straddle_sram": E(st, "items", "signoff", f),
        pre + "drc_outside_sram": E(outs, "items", "signoff", f),
        pre + "nwell4_straddle_outside": E(
            nw[1:],
            "items",
            "signoff",
            f,
            note="[straddling, outside] nwell.4 items (reports/magic_nwell4_rootcause.md; waivers W1-W4 withdrawn by the user 2026-11-08)",
        ),
        pre + "drc_by_rule": E(
            rules, "[inside, straddle, outside] per rule", "signoff", f, note=mode
        ),
    }


def nwell4_nsc(tag: str):
    """KLayout geometric re-check of Magic's nwell.4 definition on the real std-cell GDS."""
    f = f"{COM}/signoff/drclvs/reports/{tag}_nwell4_nsc_check.txt"
    if not tracked(f):
        return {}
    return {
        "nwell_regions_without_nsc": E(
            grab(f, r"nwell_regions_without_nsc: total=(\d+)", int),
            "regions",
            "signoff",
            f,
            note=(
                "KLayout, flattened real GDS: merged nwell regions with no n-tap contact "
                "(nsc = licon1 & tap & nsdm), all of the die incl. SRAMs; the nwell.4 definition"
            ),
        )
    }


def lec_conformal(tag_prefix: str):
    base = f"{COM}/signoff/lec/conformal/reports"
    res = {}
    for d in sorted(p(base).glob(f"{tag_prefix}_*")):
        f = f"{base}/{d.name}/lec_log.txt"
        if not p(f).is_file():
            continue
        t = text(f)
        v = re.findall(r"^B4D_\w+_VERDICT: (\w+)", t, re.M)
        if not v:  # hierarchical (fv_map) flow prints its own result line
            v = [x.upper() for x in re.findall(r"Hierarchical Compare Result\s*:\s*(\w+)", t)]
        cp = re.findall(r"^No of compare points = (\d+)", t, re.M)
        dp = re.findall(r"^No of diff points\s*= (\d+)", t, re.M)
        res[d.name] = E(
            v[-1] if v else None,
            "verdict",
            "signoff",
            f,
            compare_points=int(cp[-1]) if cp else None,
            diff_points=int(dp[-1]) if dp else None,
        )
    return res


def lec_formality(tag_prefix: str):
    base = f"{COM}/signoff/lec/formality/reports"
    res = {}
    for d in sorted(p(base).glob(f"{tag_prefix}_*")):
        f = f"{base}/{d.name}/fm_log.txt"
        if not p(f).is_file():
            continue
        t = text(f)
        v = re.findall(r"^Verification (SUCCEEDED|FAILED|INCONCLUSIVE)", t, re.M)
        pas = re.findall(r"^\s*(\d+) Passing compare points", t, re.M)
        fail = re.findall(r"^\s*(\d+) Failing compare points", t, re.M)
        res[d.name] = E(
            v[-1] if v else None,
            "verdict",
            "signoff",
            f,
            passing=int(pas[-1]) if pas else None,
            failing=int(fail[-1]) if fail else 0,
        )
    return res


def lec_summary(runs: dict, positive: list[str], negative: list[str], src_kind: str):
    ok_word = "EQUIVALENT" if src_kind == "conformal" else "SUCCEEDED"
    bad_word = "NOT_EQUIVALENT" if src_kind == "conformal" else "FAILED"
    pos = [k for k in runs if any(s in k for s in positive)]
    neg = [k for k in runs if any(s in k for s in negative)]
    return E(
        f"{sum(runs[k]['value'] == ok_word for k in pos)}/{len(pos)} equivalent; "
        f"{sum(runs[k]['value'] == bad_word for k in neg)}/{len(neg)} negative controls caught",
        "verdict",
        "derived",
        sorted(runs[k]["source"] for k in pos + neg),
        rule="count of per-run verdicts",
    )


def redhawk(arm: str):
    d = f"{COM}/signoff/redhawk/reports"
    s, dy, nd = (
        f"{d}/{arm}_static_summary.json",
        f"{d}/{arm}_dynamic_summary.json",
        f"{d}/{arm}_dynamic_nodecap_summary.json",
    )
    if not tracked(s):  # b7: not re-run (no PG / decap / clock change; see the doc), so no RedHawk figures are claimed for it
        return {}
    S, D, N = (json.loads(text(x)) for x in (s, dy, nd))
    al = S["populations"]["all"]
    ls = D["populations"]["logic+sram"]
    note = "indicative: default currents, estimated decap, ideal met5 edge feed, uncorrelated tech"
    return {
        "ir_static_vpwr_drop_mV": E(al["worst_vpwr_drop_mV"], "mV", "signoff", s, note=note),
        "ir_static_vgnd_bounce_mV": E(round(al["worst_vgnd_bounce_mV"], 1), "mV", "signoff", s),
        "ir_static_worst_total_mV": E(al["worst_total_mV"], "mV", "signoff", s),
        "ir_static_em_violations": E(
            S["em_static"]["metal_violations"] + S["em_static"]["via_violations"],
            "count",
            "signoff",
            s,
        ),
        "ir_dynamic_worst_avgTW_mV": E(
            round(ls["worst_avgTW_mV"], 1), "mV", "signoff", dy, note=note
        ),
        "ir_dynamic_worst_minWC_mV": E(round(ls["worst_minWC_mV"], 1), "mV", "signoff", dy),
        "ir_dynamic_mean_avgTW_mV": E(round(ls["mean_avgTW_mV"], 1), "mV", "signoff", dy),
        "ir_dynamic_frac_gt5pct": E(
            round(ls["frac_inst_avgTW_gt_5pct"], 4), "fraction", "signoff", dy
        ),
        "ir_dynamic_decap_instances": E(D["decap_instances_in_dynamic"], "count", "signoff", dy),
        "ir_dynamic_nodecap_worst_avgTW_mV": E(
            round(N["populations"]["logic+sram"]["worst_avgTW_mV"], 1), "mV", "signoff", nd
        ),
        "ir_power_fed_mW": E(S["rh_total_power_mW"], "mW", "signoff", s),
    }


# ----------------------------------------------------------------------------- arms
def openroad():
    mj = f"{SNAP}/openroad/metrics.json"
    m = json.loads(text(mj))
    c = "__corner:nom_tt_025C_1v80"
    n = lambda k, u, **kw: E(m[k], u, "native", mj, key=k, **kw)  # noqa: E731
    out = {
        "native_setup_wns_nom_tt": n("timing__setup__ws" + c, "ns"),
        "native_hold_wns_nom_tt": n("timing__hold__ws" + c, "ns"),
        "native_hold_viol_nom_tt": n("timing__hold_vio__count" + c, "count"),
        "native_setup_ws_all_corners": n(
            "timing__setup__ws", "ns", note="OpenSTA + OpenRCX, 9 corners"
        ),
        "native_setup_viol_all_corners": n("timing__setup_vio__count", "count"),
        "native_setup_r2r_viol_all_corners": n("timing__setup_r2r_vio__count", "count"),
        "native_hold_ws_all_corners": n("timing__hold__ws", "ns"),
        "native_hold_viol_all_corners": n("timing__hold_vio__count", "count"),
        "native_hold_r2r_viol_all_corners": n("timing__hold_r2r_vio__count", "count"),
        "native_max_slew_viol_nom_tt": n("design__max_slew_violation__count" + c, "count"),
        "native_max_cap_viol_nom_tt": n("design__max_cap_violation__count" + c, "count"),
        "native_max_fanout_viol_nom_tt": n("design__max_fanout_violation__count" + c, "count"),
        "native_power_mW": E(
            round(m["power__total"] * 1e3, 2), "mW", "native", mj, key="power__total"
        ),
        "native_route_drc": n("route__drc_errors", "count"),
        "native_wirelength_um": n("route__wirelength", "um"),
        "native_vias": n("route__vias", "count"),
        "native_stdcell_area_um2": n(
            "design__instance__area__stdcell",
            "um2",
            note="OpenROAD definition (includes tap/decap/diode cells, not fill)",
        ),
        "native_util": n(
            "design__instance__utilization", "fraction", note="(stdcell + macro) / core"
        ),
        "native_util_stdcell": n("design__instance__utilization__stdcell", "fraction"),
        "native_ir_drop_worst_V": n("ir__drop__worst", "V", note="OpenROAD PSM, nom_tt"),
        "antenna_deck_nets": E(
            m["antenna__violating__nets"],
            "nets",
            "signoff",
            mj,
            key="antenna__violating__nets",
            note="OpenROAD check_antennas",
        ),
        "antenna_deck_pins": E(m["antenna__violating__pins"], "pins", "signoff", mj),
        "klayout_drc": E(
            m["klayout__drc_error__count"], "items", "signoff", mj, key="klayout__drc_error__count"
        ),
        "lvs_errors": E(
            m["design__lvs_error__count"],
            "count",
            "signoff",
            mj,
            key="design__lvs_error__count",
            note="Netgen LVS inside LibreLane (DEF/LEF-mode Magic extraction)",
        ),
    }
    fg = f"{COM}/signoff/drclvs/reports/openroad_magic_drc_real_stdgds_by_rule.tsv"
    fl = f"{COM}/signoff/drclvs/reports/openroad_magic_drc_by_rule.tsv"
    if tracked(fg):
        out.update(magic(fg))
        out.update(magic(fl, "magic_lef_"))
    else:
        out.update(magic(fl))
    out.update(nwell4_nsc("openroad"))
    out["census"] = census(f"{SNAP}/openroad/cellcount.txt")
    rt = f"{SNAP}/openroad/step_runtime.tsv"
    rows = [line.split("\t") for line in text(rt).splitlines()[1:]]
    pnr_steps = [r for r in rows if int(r[0].split("-")[0]) >= 13]
    out["runtime_pnr_s"] = E(
        round(
            sum(
                hms(r[1])
                for r in pnr_steps
                if not r[0].endswith(
                    ("magic-drc", "klayout-drc", "netgen-lvs", "magic-spiceextraction")
                )
            )
        ),
        "s",
        "derived",
        rt,
        rule="sum of LibreLane step runtimes 13-floorplan .. 74, excluding Magic/KLayout DRC, "
        "Magic extraction and Netgen LVS",
    )
    out["runtime_total_flow_s"] = E(
        round(sum(hms(r[1]) for r in rows)),
        "s",
        "derived",
        rt,
        rule="sum of all LibreLane step runtimes (incl. synthesis and sign-off)",
    )
    out["peak_rss"] = E(None, "GB", "native", rt, note="not recorded by LibreLane for this run")
    out["synth_runtime_s"] = E(
        round(sum(hms(r[1]) for r in rows if r[0].endswith("yosys-synthesis"))),
        "s",
        "derived",
        rt,
        rule="06-yosys-synthesis runtime.txt",
    )
    fm = lec_formality("or")
    cf = lec_conformal("or_cf")
    ye = {}
    yb = f"{COM}/signoff/lec/yosys/reports"
    for d in sorted(p(yb).glob("e[0-9]*")):
        f = f"{yb}/{d.name}/equiv_after_induct.txt"
        if not p(f).is_file():
            continue
        t = text(f)
        m = re.search(r"Of those cells (\d+) are proven and (\d+) are unproven", t)
        tot = re.search(r"Found (\d+) \$equiv cells", t)
        ye[d.name] = E(
            ("EQUIVALENT" if m and m.group(2) == "0" else "NOT_PROVEN") if m else None,
            "verdict",
            "signoff",
            f,
            proven=int(m.group(1)) if m else None,
            unproven=int(m.group(2)) if m else None,
            equiv_cells=int(tot.group(1)) if tot else None,
        )
    out["lec_yosys_runs"] = ye
    out["lec_runs"] = {**fm, **cf}

    def v(k):
        return (fm.get(k) or cf.get(k) or {}).get("value")

    ctl = [k for k in fm if "negctl" in k]
    caught = [k for k in ctl if fm[k]["value"] == "FAILED"]
    yneg = [k for k in ye if k.startswith("e") and "_neg_" in k]
    ycaught = [k for k in yneg if ye[k]["value"] == "NOT_PROVEN"]
    yfinal = (ye.get("e5_final") or {}).get("value")
    ysyn = (ye.get("e4") or {}).get("value")
    closed = (
        v("or_fe_rtl_vs_sv2v") == "SUCCEEDED"
        and v("or_nodiode_vs_syn") == "SUCCEEDED"
        and yfinal == "EQUIVALENT"
        and len(yneg) >= 4
        and len(ycaught) == len(yneg)
    )
    out["lec"] = E(
        ("EQUIVALENT (RTL==sv2v by Formality; sv2v==final netlist by Yosys equiv_induct)" if closed else "NOT CLOSED")
        + f": Formality RTL==sv2v {v('or_fe_rtl_vs_sv2v')}; Formality final==Yosys netlist {v('or_nodiode_vs_syn')};"
        f" Yosys equiv_induct sv2v vs Yosys netlist {ysyn}, sv2v vs final netlist {yfinal};"
        f" Formality sv2v/Yosys-netlist compare {v('or_syn_vs_sv2v')}; Conformal RTL vs Yosys netlist {v('or_cf_synnamed_vs_rtl')};"
        f" negative controls caught: Formality {len(caught)}/{len(ctl)}, Yosys {len(ycaught)}/{len(yneg)}",
        "verdict",
        "derived",
        sorted(
            {x["source"] for x in {**fm, **cf, **ye}.values() if isinstance(x["source"], str)}
        ),
        rule="derived from lec_runs and lec_yosys_runs; closed only if RTL==sv2v, final==Yosys, Yosys end-to-end EQUIVALENT and >=4 Yosys mutants all NOT_PROVEN",
    )
    out.update(redhawk("openroad"))
    return out


def icc2_arm(b="b6"):
    d = f"{SNAP}/icc2_{b}"
    q = f"{d}/final_qor.txt"
    out = {}
    for scen, kind in (
        ("func_ss", "Setup"),
        ("func_tt", "Setup"),
        ("func_ff", "Hold"),
        ("func_tt", "Hold"),
    ):
        m = re.search(rf"^{scen}\s+\({kind}\)\s+(\S+)\s+(\S+)\s+(\d+)", text(q), re.M)
        out[f"native_{kind.lower()}_{scen}"] = E(
            {"wns": float(m.group(1)), "tns": float(m.group(2)), "nve": int(m.group(3))},
            "ns / count",
            "native",
            q,
            note="ICC2 report_qor -summary, own TLU+ RC",
        )
    for key, pat, u in (
        ("native_max_tran_viol", r"Max Trans Violations:\s+(\d+)", "nets"),
        ("native_max_cap_viol", r"Max Cap Violations:\s+(\d+)", "nets"),
        ("native_leaf_cells", r"Leaf Cell Count:\s+(\d+)", "count"),
        ("native_buf_cells", r"Buf Cell Count:\s+(\d+)", "count"),
        ("native_seq_cells", r"Sequential Cell Count:\s+(\d+)", "count"),
        ("native_stdcell_area_um2", None, "um2"),
    ):
        if pat:
            out[key] = E(grab(q, pat, int), u, "native", q)
    comb = grab(q, r"Combinational Area:\s+([\d.]+)")
    seq = grab(q, r"Noncombinational Area:\s+([\d.]+)")
    out["native_stdcell_area_um2"] = E(
        round(comb + seq, 2),
        "um2",
        "native",
        q,
        note="Combinational + Noncombinational area (logical cells)",
    )
    u = f"{d}/final_utilization.txt"
    out["native_util"] = E(
        grab(u, r"^Utilization Ratio:\s+([\d.]+)"),
        "fraction",
        "native",
        u,
        note="site-row utilisation, macros excluded from both terms",
    )
    r = f"{d}/final_check_routes.txt"
    out["native_route_drc"] = E(grab(r, r"Total number of DRCs = (\d+)", int), "count", "native", r)
    out["native_antenna"] = E(
        grab(r, r"Total number of antenna violations = (\d+)", int),
        "count",
        "native",
        r,
        note="ICC2 rule (diode_mode 1), lenient vs the deck",
    )
    out["native_wirelength_um"] = E(
        grab(r, r"Total Routed Wire Length =\s+(\d+)", int), "um", "native", r
    )
    out["native_vias"] = E(
        grab(r, r"Total double via conversion rate\s*=.*?/\s*(\d+) vias\)", int),
        "count",
        "native",
        r,
    )
    lv = f"{d}/final_check_lvs.txt"
    out["native_shorts_opens"] = E(
        [grab(lv, r"short violations is (\d+)", int), grab(lv, r"open nets is (\d+)", int)],
        "[shorts, opens]",
        "native",
        lv,
    )
    pw = f"{d}/final_power.txt"
    out["native_power_mW"] = E(
        round(grab(pw, r"^Total\s+\S+ nW\s+\S+ nW\s+\S+ nW\s+([\d.e+]+) nW") / 1e6, 2),
        "mW",
        "native",
        pw,
        note="ICC2 vectorless, func_tt",
    )
    tot, peak, srcs = 0.0, 0, []
    # stage-time sources per generation (dir, glob, skip-prefixes).  b6 = its own stages 01..08; b7 = b6 01..06 + b7 ECO/finish/write; b8 = a full re-run on the flipped floorplan: ITS OWN b8_0* stages
    # (before 2026-11-10 the glob b[67]_0* silently re-used the b6 stage times for b8 = a bug, corrected here); b9 = b8 stages 01..06b + the b9 ECO (06c, 06d, 06e) / finish / write stages.
    if b == "b6":
        stage_srcs = [(f"{SNAP}/icc2_b6", "b6_0*.time", ())]
    elif b == "b7":
        stage_srcs = [(f"{SNAP}/icc2_b6", "b6_0*.time", ("b6_07", "b6_08")), (d, "b7_0*.time", ())]
    elif b == "b8":
        stage_srcs = [(d, "b8_0*.time", ())]
    else:
        stage_srcs = [(f"{SNAP}/icc2_b8", "b8_0*.time", ("b8_07", "b8_08")), (d, f"{b}_0*.time", ())]
    for sd, pat, skip in stage_srcs:
        for t in sorted(p(f"{sd}/stage_time").glob(pat)):
            if "mcmmtest" in t.name or t.name.startswith(skip):
                continue
            rel = f"{sd}/stage_time/{t.name}"
            w, rss = time_v(rel)
            tot += w
            peak = max(peak, rss)
            srcs.append(rel)
    out["runtime_pnr_s"] = E(
        round(tot),
        "s",
        "derived",
        srcs,
        rule="sum of /usr/bin/time wall over stages 01..08 (excl. MCMM probe); b7: b6 stages 01..06 + b7 ECO / finish / write stages; b8: its own stages; b9: b8 stages 01..06b + b9 ECO / finish / write stages",
    )
    out["peak_rss"] = E(round(peak / 1048576, 2), "GB", "derived", srcs, rule="max over stages")
    out["census"] = census(f"{d}/final_cellcount.txt")
    out.update(drclvs(f"icc2_{b}"))
    runs = lec_formality(b)
    out["lec_runs"] = runs
    out["lec"] = lec_summary(runs, ["_vs_"], ["negctl"], "formality")
    out.update(redhawk(f"icc2{b}"))
    return out


def icc2_b6():
    return icc2_arm("b6")


def icc2_b7():
    return icc2_arm("b7")


def icc2_b8():
    return icc2_arm("b8")


def icc2_b9():
    return icc2_arm("b9")


def innovus_arm(b="b6"):
    d = f"{SNAP}/innovus_{b}"
    r6 = f"{COM}/impl/innovus/reports/{b}"
    out = {}
    for kind, f in (
        ("setup", f"{r6}/final_setup.summary.txt"),
        ("hold", f"{r6}/final_hold.summary.txt"),
        ("setup_sioff", f"{r6}/final_setup_sioff.summary.txt"),
        ("hold_sioff", f"{r6}/final_hold_sioff.summary.txt"),
    ):
        t = text(f)
        w = re.search(r"WNS \(ns\):\|\s*(\S+)\s*\|\s*(\S+)", t)
        tn = re.search(r"TNS \(ns\):\|\s*(\S+)\s*\|\s*(\S+)", t)
        v = re.search(r"Violating Paths:\|\s*(\S+)\s*\|\s*(\S+)", t)
        out[f"native_{kind}"] = E(
            {
                "wns_all": float(w.group(1)),
                "wns_r2r": float(w.group(2)),
                "tns_all": float(tn.group(1)),
                "viol_all": int(v.group(1)),
                "viol_r2r": int(v.group(2)),
            },
            "ns / count",
            "native",
            f,
            note="timeDesign -postRoute, all active views (av_ss + av_tt setup, av_ff + av_tt hold)",
        )
    f = f"{r6}/final_setup.summary.txt"
    for drv in ("max_cap", "max_tran", "max_fanout"):
        out[f"native_{drv}_viol"] = E(
            grab(f, rf"\|\s+{drv}\s+\|[^|]*\|[^|]*\|\s*(\d+)", int),
            "nets",
            "native",
            f,
            note="Total column",
        )
    out["native_util"] = E(
        grab(f, r"Density:\s*([\d.]+)%") / 100, "fraction", "native", f, note="Innovus density"
    )
    dr = f"{r6}/final_drc.txt"
    m_drc = re.search(r"Total Violations\s*:\s*(\d+)", text(dr))
    out["native_route_drc"] = E(
        0 if "No DRC violations were found" in text(dr) else (int(m_drc.group(1)) if m_drc else None), "count", "native", dr,
        note="Innovus verify_drc; the 24 items of the flipped I-cache generations (b8..b11) are ParallelRunLength Spacing markers against the SRAM LEF met3 OBS: LEF-abstract pessimism, 24 of 24 evidenced against the SRAM GDS (docs section 7 item 13; written justification, not a waiver)",
    )
    an = f"{d}/final_antenna.txt"
    out["native_antenna"] = E(
        0 if "No Violations Found" in text(an) else None,
        "count",
        "native",
        an,
        note="verifyProcessAntenna (no side-area rule)",
    )
    ar = f"{d}/final_area.txt"
    tot_area = grab(ar, r"^rv32i_cpu_top\s+(\d+)\s+([\d.]+)", float, group=2)
    out["native_total_area_incl_macros_um2"] = E(
        tot_area, "um2", "native", ar, note="report_area, logical instances incl. the 10 SRAMs"
    )
    out["native_logical_instances"] = E(
        grab(ar, r"^rv32i_cpu_top\s+(\d+)", int), "count", "native", ar
    )
    rs = f"{d}/final_route_summary.txt"
    out["native_wirelength_um"] = E(grab(rs, r"\|\s+Total\s+\|\s*([\d.]+) um"), "um", "native", rs)
    out["native_vias"] = E(
        grab(rs, r"Via Count Statistics.*?\|\s+Total\s+\|\s*(\d+)", int, flags=re.S),
        "count",
        "native",
        rs,
    )
    pw = f"{r6}/final_power_act01.txt"
    out["native_power_mW"] = E(
        grab(pw, r"^Total Power:\s+([\d.]+)"),
        "mW",
        "native",
        pw,
        note="power view av_ss (ss leakage), activity 0.1: not comparable with tt figures",
    )
    tot, peak, srcs = 0.0, 0, []
    stage_dirs = ([f"{SNAP}/innovus_b6"] if b in ("b6", "b7") else []) + ([f"{SNAP}/innovus_b8"] if b in ("b9", "b10", "b11") else []) + ([f"{SNAP}/innovus_b9"] if b in ("b10", "b11") else []) + ([f"{SNAP}/innovus_b10"] if b == "b11" else []) + ([d] if b != "b6" else [])  # b7 = the b6 flow + the b7 ECO / finish / restream stages; b8 has its own full chain
    for sd in stage_dirs:
        for t in sorted(p(f"{sd}/stage_time").glob("[01]*.time")):
            if b != "b6" and (sd.endswith(("innovus_b6", "innovus_b8")) or (b in ("b10", "b11") and sd.endswith("innovus_b9")) or (b == "b11" and sd.endswith("innovus_b10"))) and t.name.startswith(("06m_finish", "07_restream")):
                continue  # superseded by the b7 finish / restream (b10: also by the b10 ones)
            rel = f"{sd}/stage_time/{t.name}"
            w, rss = time_v(rel)
            tot += w
            peak = max(peak, rss)
            srcs.append(rel)
    out["runtime_pnr_s"] = E(
        round(tot),
        "s",
        "derived",
        srcs,
        rule="sum of /usr/bin/time wall over stages 01..07 (final chain; excl. probe); b7: b6 stages up to 05m_eco + b7 ECO / finish / restream stages",
    )
    out["peak_rss"] = E(round(peak / 1048576, 2), "GB", "derived", srcs, rule="max over stages")
    out["census"] = census(f"{r6}/final_cellcount.txt")
    out.update(drclvs(f"innovus_{b}"))
    runs = lec_conformal({"b6": "b4m", "b7": "b7m", "b8": "b8m", "b9": "b9m", "b10": "b10m", "b11": "b11m"}[b])
    out["lec_runs"] = runs
    out["lec"] = lec_summary(runs, ["innovus_"], ["negctl"], "conformal")
    out.update(redhawk(f"innovus{b}"))
    return out


def innovus_b6():
    return innovus_arm("b6")


def innovus_b7():
    return innovus_arm("b7")


def innovus_b8():
    return innovus_arm("b8")


def innovus_b9():
    return innovus_arm("b9")


def innovus_b10():
    return innovus_arm("b10")


def innovus_b11():
    return innovus_arm("b11")


def history():
    icc = f"{COM}/reports/icc2_pnr_summary.md"
    inn_k = f"{COM}/reports/innovus_b5k_report.md"
    inn_j = f"{COM}/reports/innovus_b5j_report.md"
    inn_h = f"{COM}/reports/innovus_b5h_report.md"
    h = {
        "icc2_b5e": {
            "native_setup_wns_tt": prose(
                0.0725, "ns", "native", icc, "B5e result table, Setup WNS"
            ),
            "native_hold_wns_tt": prose(0.0037, "ns", "native", icc, "B5e result table, Hold WNS"),
            "native_route_drc": prose(1, "count", "native", icc, "B5e result table, Routing DRC"),
            "native_wirelength_um": prose(
                4499456, "um", "native", icc, "B5e result table, Routed wirelength"
            ),
            "native_vias": prose(
                390255, "count", "native", icc, "B5e result table, Vias / contacts"
            ),
            "native_power_mW": prose(55.8, "mW", "native", icc, "B5e result table, Power"),
            "native_max_tran_cap_viol": prose(
                [121, 170], "[tran, cap]", "native", icc, "B5e result table"
            ),
            "runtime_pnr_s": prose(
                3660, "s", "native", icc, "B5e result table, ICC2 wall (host load 10-14)"
            ),
            "peak_rss": prose(3.9, "GB", "native", icc, "B5e result table, Peak RSS"),
            "antenna_deck_nets": prose(
                488, "nets", "signoff", icc, "B5m verification table, signoff antenna b5e"
            ),
            "lec": prose(
                "EQUIVALENT",
                "verdict",
                "signoff",
                f"{COM}/reports/lec_icc2_formality.md",
                "B5m verification table in icc2_pnr_summary.md cites the b5e Formality run",
            ),
        },
        "icc2_b5i": {
            "native_setup_wns_tt": prose(
                0.0746, "ns", "native", icc, "B5m verification table, b5i column"
            ),
            "native_hold_wns_tt": prose(
                -0.0016, "ns", "native", icc, "B5m verification table, b5i column"
            ),
            "native_route_drc": prose(
                0, "count", "native", icc, "B5m verification table, b5i column"
            ),
        },
        "icc2_b5m": {
            "native_setup_wns_tt": prose(
                0.0746, "ns", "native", icc, "B5m section, Native b5m line"
            ),
            "native_hold_wns_tt": prose(
                -0.0032, "ns", "native", icc, "B5m section, Native b5m line"
            ),
            "native_route_drc": prose(0, "count", "native", icc, "B5m section, Native b5m line"),
            "native_power_mW": prose(55.8, "mW", "native", icc, "B5m section, Native b5m line"),
            "native_max_tran_cap_viol": prose(
                [135, 169], "[tran, cap]", "native", icc, "b5m -> b6 table"
            ),
            "lec": prose(
                "SUCCEEDED 6,233 / 0 failing; 4/4 negative controls",
                "verdict",
                "signoff",
                icc,
                "B5m verification table, Formality rows",
            ),
        },
        "innovus_b5h": {
            "native_setup_wns": prose(0.215, "ns", "native", inn_h, "section 2 table, Setup WNS"),
            "native_hold_wns": prose(0.139, "ns", "native", inn_h, "section 2 table, Hold WNS"),
            "native_route_drc": prose(0, "count", "native", inn_h, "section 2 table, verify_drc"),
            "native_power_act01_mW": prose(
                70.62, "mW", "native", inn_h, "section 2 table, Power @ activity 0.1"
            ),
        },
        "innovus_b5j": {
            "native_setup_wns": prose(0.215, "ns", "native", inn_j, "section 3 table"),
            "native_hold_wns": prose(0.139, "ns", "native", inn_j, "section 3 table"),
            "native_route_drc": prose(0, "count", "native", inn_j, "section 3 table"),
            "lec": prose(
                "EQUIVALENT 4/4; 4/4 negative controls",
                "verdict",
                "signoff",
                inn_j,
                "section 3 table",
            ),
        },
        "innovus_b5k": {
            "native_setup_wns": prose(
                0.065, "ns", "native", inn_k, "section 2 table, Native setup WNS"
            ),
            "native_hold_wns": prose(
                0.011, "ns", "native", inn_k, "section 2 table, Native hold WNS"
            ),
            "native_route_drc": prose(0, "count", "native", inn_k, "section 2 table, verify_drc"),
            "native_power_act01_mW": prose(
                71.73, "mW", "native", inn_k, "section 2 table, Power @ activity 0.1"
            ),
            "native_max_cap_tran_viol": prose(
                [378, 122], "[cap, tran] nets", "native", inn_k, "section 2 table"
            ),
        },
    }
    k = lec_conformal("b4l")
    h["innovus_b5k"]["lec_runs"] = k
    h["innovus_b5k"]["lec"] = lec_summary(k, ["innovus_"], ["negctl"], "conformal")
    for arm, tag in (
        ("icc2_b5i", "icc2_b5i"),
        ("icc2_b5m", "icc2_b5m"),
        ("innovus_b5j", "innovus_b5j"),
        ("innovus_b5k", "innovus_b5k"),
        ("icc2_b5e", "icc2"),
    ):
        dl = drclvs(tag)
        if arm == "icc2_b5e":  # icc2_* files are the b5e GDS; its antenna file is not the b5e one
            dl = {k_: v for k_, v in dl.items() if not k_.startswith("antenna")}
        h[arm].update(dl)
    h["icc2_b5e"].update(magic(f"{COM}/signoff/drclvs/reports/icc2_magic_drc_real_by_rule.tsv"))
    return h


def synthesis():
    s1 = f"{COM}/syn/ss_probe/reports/step1_probe_metrics.tsv"
    s2 = f"{COM}/syn/ss_probe/reports/step2_dc_v2_probe_metrics.tsv"
    rows = {}
    for f in (s1, s2):
        lines = text(f).splitlines()
        hdr = lines[0].split("\t")
        for line in lines[1:]:
            r = dict(zip(hdr, line.split("\t")))
            rows[(r["arm"], r["lib"])] = (r, f)
    out = {}
    for arm, key in (
        ("openroad_b2", "yosys"),
        ("icc2_b6", "dc_v2"),
        ("innovus_b6", "genus_v1"),
        ("icc2_b7", "dc_v2"),
        ("innovus_b7", "genus_v1"),
        ("icc2_b8", "dc_v2"),
        ("icc2_b9", "dc_v2"),
        ("innovus_b8", "genus_v1"),
        ("innovus_b9", "genus_v1"),
        ("innovus_b10", "genus_v1"),
        ("innovus_b11", "genus_v1"),
        ("icc2_b5e", "dc_v1"),
    ):
        tt, f = rows[(key, "tt")]
        ss, _ = rows[(key, "ss")]
        out[arm] = {
            "netlist": key,
            "synth_leaf_cells": E(int(tt["leaf_cells"]), "count", "judge", f, note="incl. 10 SRAM"),
            "synth_zero_wire_setup_wns_tt": E(
                float(tt["setup_wns"]),
                "ns",
                "judge",
                f,
                note="PrimeTime, ideal clock, no parasitics, shared SDC",
            ),
            "synth_zero_wire_setup_wns_ss": E(float(ss["setup_wns"]), "ns", "judge", f),
            "synth_zero_wire_setup_viol_ss": E(int(ss["setup_viol"]), "count", "judge", f),
        }
    dcv2 = f"{COM}/reports/dc_synth_v2_summary.md"
    gen = f"{COM}/reports/genus_synth_summary.md"
    for b7, b6 in (("icc2_b7", "icc2_b6"), ("innovus_b7", "innovus_b6")):
        pass
    out["icc2_b6"]["synth_runtime"] = prose(
        333.6, "s", "native", dcv2, "Caveats: DC 'Overall Compile Wall Clock Time' (host contended)"
    )
    out["icc2_b6"]["synth_peak_rss"] = prose(1.55, "GB", "native", dcv2, "Caveats: Peak RSS")
    out["innovus_b6"]["synth_runtime"] = prose(
        704, "s", "native", gen, "QoR table: whole session wall 11:44 (/usr/bin/time)"
    )
    out["innovus_b6"]["synth_peak_rss"] = prose(2.03, "GB", "native", gen, "QoR table: peak RSS")
    fm = f"{COM}/signoff/lec/formality/reports/b4a2_dc_v2_vs_rtl/fm_log.txt"
    out["icc2_b6"]["synth_lec"] = lec_formality("b4a2")
    out["innovus_b6"]["synth_lec"] = lec_conformal("b4b_genus")
    for b7, b6 in (("icc2_b7", "icc2_b6"), ("innovus_b7", "innovus_b6"), ("icc2_b8", "icc2_b6"), ("icc2_b9", "icc2_b6"), ("innovus_b8", "innovus_b6"), ("innovus_b9", "innovus_b6"), ("innovus_b10", "innovus_b6"), ("innovus_b11", "innovus_b6")):  # b7/b8 share the b6 netlist synthesis (the ECO starts after synthesis)
        for k in ("synth_runtime", "synth_peak_rss", "synth_lec"):
            out[b7][k] = out[b6][k]
    _ = fm
    return out


def calibration():
    out = {}
    for c in ("nom", "min", "max"):
        f = f"{COM}/signoff/starrc/reports/correlation_{c}.md"
        t = text(f)
        m = re.search(
            r"^\| total C \| \d+ \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|.*?\| (\d+) \(([\d.]+) %\)",
            t,
            re.M,
        )
        r = re.search(r"^\| total R[^|]*\| \d+ \| ([\d.]+) \|", t, re.M)
        d = re.search(
            r"total design \(all nets\): C ref ([\d.]+) pF, test ([\d.]+) pF, ratio ([\d.]+)", t
        )
        out[c] = E(
            {
                "C_median_ratio": float(m.group(1)),
                "C_p5": float(m.group(2)),
                "C_p95": float(m.group(3)),
                "C_outside_10pct": float(m.group(5)) / 100,
                "R_median_ratio": float(r.group(1)),
                "design_C_openrcx_pF": float(d.group(1)),
                "design_C_starrc_pF": float(d.group(2)),
                "design_C_ratio": float(d.group(3)),
            },
            "ratio StarRC/OpenRCX",
            "signoff",
            f,
            note="tuned ITF vs OpenRCX on the OpenROAD DEF, nets C > 1 fF; calibrated to OpenRCX, not silicon",
        )
    return out


def quantus_crosscheck():
    """Cadence Quantus (Techgen cell-level qrcTechFile from the same authored ICT) vs StarRC, per net, on the three b6 DEFs.
    Every value comes from the committed reports written by signoff/quantus/scripts/{correlate_all,collect_runs}.py."""
    rep = f"{COM}/signoff/quantus/reports/quantus_vs_starrc.json"
    runs = f"{COM}/signoff/quantus/reports/quantus_runs.json"
    if not (tracked(rep) and tracked(runs)):
        warnings.append("quantus reports not committed; quantus_crosscheck omitted")
        return {}
    out = {"correlation": {}, "cost": {}, "pt_sensitivity_nom_tt": {}, "techgen": {}}
    rep_b9 = f"{COM}/signoff/quantus/reports/quantus_vs_starrc_icc2b9.json"  # ICC2 b9 (step 4 adopt-b9, 2026-11-13): same method, separate file written with CORR_TAG=_icc2b9
    corr_src = [(k, r, rep) for k, r in json.loads(text(rep))["results"].items()]
    if tracked(rep_b9):
        corr_src += [(k, r, rep_b9) for k, r in json.loads(text(rep_b9))["results"].items()]
    else:
        warnings.append("quantus ICC2 b9 correlation report not committed; omitted")
    rep_i11 = f"{COM}/signoff/quantus/reports/quantus_vs_starrc_innovusb11.json"  # Innovus b11 (2026-11-13): same method, written with CORR_TAG=_innovusb11
    if tracked(rep_i11):
        corr_src += [(k, r, rep_i11) for k, r in json.loads(text(rep_i11))["results"].items()]
    else:
        warnings.append("quantus Innovus b11 correlation report not committed; omitted")
    for k, r, rep in corr_src:
        out["correlation"][k] = E(
            {
                "total_C_median_err_pct": round(r["total_C"]["median_err_pct"], 2),
                "total_C_median_abs_err_pct": round(r["total_C"]["median_abs_err_pct"], 2),
                "total_C_p95_abs_err_pct": round(r["total_C"]["p95_abs_err_pct"], 2),
                "total_R_median_err_pct": round(r["total_R"]["median_err_pct"], 2),
                "total_R_p95_abs_err_pct": round(r["total_R"]["p95_abs_err_pct"], 2),
                "ground_C_median_err_pct": round(r["ground_C"]["median_err_pct"], 2),
                "design_C_ratio": round(r["design"]["C_ratio"], 4),
                "design_R_ratio": round(r["design"]["R_ratio"], 4),
                "gate_population_nets": r["gate_population_nets"],
                "label": r["label"],
                "tail_beyond_10pct": r["tail_flag"],
            },
            "percent error, Quantus vs StarRC",
            "signoff",
            rep,
            note="nets with StarRC total C > 1 fF; same authored ITF/ICT stack in both extractors, so agreement is not accuracy vs silicon",
        )
    q = json.loads(text(runs))
    for k, r in q["quantus_runs"].items():
        out["cost"][k] = E(
            {"wall_s": r["wall_s"], "session_peak_rss_kb": r["session_peak_rss_kb"], "nets": r["nets_extracted"], "errors": r["errors"]},
            "s / kB / nets",
            "signoff",
            runs,
            note="quantus -multi_cpu 2 under safe_run.sh; session RSS = sum over the process session sampled every 10 s",
        )
    for arm, r in q["pt_sensitivity_nom_tt"].items():
        out["pt_sensitivity_nom_tt"][arm] = E(
            r, "ns / mW", "signoff", runs,
            note="PrimeTime nom_tt, base SDC, same netlist; only the SPEF changes (StarRC vs Quantus); delta = Quantus - StarRC",
        )
    for c, r in q["techgen"].items():
        out["techgen"][c] = E(
            {"timing_lines": r["timing_lines"], "qrcTechFile_bytes": r["qrcTechFile_bytes"]}, "s / kB", "signoff", runs,
            note=(r.get("provenance") or "fresh cell-level Techgen run"),
        )
    return out


def clock_latency():
    """Measured clk_i insertion latency (PrimeTime, StarRC SPEF) per arm and corner, and the per-view clk_io tables built from it."""
    out = {"measured": {}, "tables": {}, "io_violators": {}}
    for arm, meta in ARMS.items():
        if meta["role"] not in ("final", "history") or not p(f"{SNAP}/clklat/{meta['pt']}_nom_tt/clk_latency.tsv").is_file():
            continue
        rows = {}
        for c in CORNERS:
            f = f"{SNAP}/clklat/{meta['pt']}_{c}/clk_latency.tsv"
            if not p(f).is_file():
                continue
            m = tsv(f)
            keep = {}
            for g in ("all", "flop", "sram", "in_capture", "out_launch"):
                for st in ("n", "min", "median", "mean", "max"):
                    k = f"{g}_rise_late_{st}"
                    if k in m:
                        v = num(m[k])
                        keep[f"{g}_{st}"] = v if st == "n" else round(v - 1.0, 4)
            rows[c] = {
                "label": "judge",
                "source": f,
                "unit": "ns (network latency = rising-edge arrival - 1.0 ns source latency; n = register clock pins)",
                "values": keep,
            }
        if rows:
            out["measured"][arm] = rows
    for v in ("arm", "shared"):
        f = f"{SNAP}/iolat_pv/iolat_pv_{v}.tsv"
        if not p(f).is_file():
            continue
        tab = {}
        for line in text(f).splitlines():
            if line.startswith("#") or not line.strip():
                continue
            a, rc, lib, e, l = line.split("\t")
            tab.setdefault(a, {})[f"{rc}_{lib}"] = {"early_ns": float(e), "late_ns": float(l)}
        out["tables"][v] = {
            "label": "derived",
            "source": [f],
            "unit": "ns (clk_io network latency; SDC adds 1.0 ns source latency)",
            "values": tab,
            "rule": "arm: each arm's own mean register-clock-pin latency; shared: mean of the three arms per corner",
        }
    for var in ("iolat_pv", "iolat_pvs"):
        for arm, meta in ARMS.items():
            for c in CORNERS:
                f = f"{SNAP}/pt/{var}/{meta['pt']}_{c}/io_viol_summary.tsv"
                if not p(f).is_file():
                    continue
                cnt = {}
                for line in text(f).splitlines()[1:]:
                    kind, tp, n, nm, wm = line.split("\t")
                    cnt[f"{kind}_{tp}"] = {"violators": int(n), "skew_limited": int(nm), "surviving": int(n) - int(nm), "worst_matched_slack": num(wm)}
                out["io_violators"].setdefault(var, {}).setdefault(arm, {})[c] = {
                    "label": "judge",
                    "source": f,
                    "unit": "count",
                    "values": cnt,
                    "note": "diag_io_viol.tcl: skew_limited = violators whose slack is >= 0 when clk_io is aligned to the macro register's own clock arrival",
                }
    return out


def sdc():
    out = {}
    for k, f in SDC_FILES.items():
        if p(f).is_file() and tracked(f):
            out[k] = E(
                hashlib.md5(p(f).read_bytes()).hexdigest(),
                "md5",
                "derived",
                f,
                rule="md5 of the file",
            )
    return out


def build():
    data = {
        "schema": 1,
        "design": "rv32i_cpu_top (Sky130 CPU macro, 10 x sky130_sram_1kbyte_1rw1r_32x256_8)",
        "pdk": "sky130A (open_pdks 0fe599b2), sky130_fd_sc_hd",
        "clock_period_ns": E(
            13.333, "ns", "derived", SDC_FILES["base"], rule="create_clock in the shared SDC"
        ),
        "labels": {
            "judge": "StarRC tuned ITF -> PrimeTime/PrimePower X-2025.06, identical for every arm",
            "native": "the implementation tool's own report (own RC/SDC/engine)",
            "signoff": "open deck / LEC / RedHawk run identically on every arm",
            "derived": "computed by compare.py by one stated rule",
        },
        "sdc": sdc(),
        "clock_latency": clock_latency(),
        "extraction_calibration": calibration(),
        "quantus_crosscheck": quantus_crosscheck(),
        "arms": {},
        "judge": {},
    }
    syn = synthesis()
    natives = {"openroad_b2": openroad(), "icc2_b6": icc2_b6(), "innovus_b6": innovus_b6()}
    if p(f"{SNAP}/icc2_b7").is_dir():
        natives["icc2_b7"] = icc2_b7()
    if p(f"{SNAP}/innovus_b7").is_dir():
        natives["innovus_b7"] = innovus_b7()
    if p(f"{SNAP}/icc2_b8").is_dir():
        natives["icc2_b8"] = icc2_b8()
    if p(f"{SNAP}/icc2_b9").is_dir():
        natives["icc2_b9"] = icc2_b9()
    if p(f"{SNAP}/innovus_b8").is_dir():
        natives["innovus_b8"] = innovus_b8()
    if p(f"{SNAP}/innovus_b9").is_dir():
        natives["innovus_b9"] = innovus_b9()
    if p(f"{SNAP}/innovus_b10").is_dir():
        natives["innovus_b10"] = innovus_b10()
    if p(f"{SNAP}/innovus_b11").is_dir():
        natives["innovus_b11"] = innovus_b11()
    natives.update(history())
    core = json.loads(text(f"{SNAP}/openroad/metrics.json"))
    core_src = f"{SNAP}/openroad/metrics.json"
    for arm, meta in ARMS.items():
        a = {k: v for k, v in meta.items()}
        a["metrics"] = natives.get(arm, {})
        if arm in syn:
            a["synthesis_metrics"] = syn[arm]
        cen = a["metrics"].get("census")
        if cen:  # one denominator for every arm (identical floorplan): core area minus macro area
            avail = core["design__core__area"] - core["design__instance__area__macros"]
            a["metrics"]["derived_util_stdcell"] = E(
                round(cen["values"]["logical_area_um2"] / avail, 4),
                "fraction",
                "derived",
                cen["source"] + [core_src],
                rule="census logical area / (OpenROAD core area - SRAM macro area); same denominator for all arms",
            )
        judge = {}
        for var in VARIANTS:
            recs = {c: judge_record(var, meta["pt"], c) for c in CORNERS}
            if not any(recs.values()):
                continue
            judge[var] = {
                "corners": recs,
                "summary": judge_summary(arm, recs, var),
                "power": power_b(var, meta["pt"]),
            }
            for c, r in recs.items():
                if not r:
                    continue
                want = data["sdc"].get(f"own:{arm}") if var == "own" else data["sdc"].get(var)
                if want and r["values"].get("sdc_md5") != want["value"]:
                    warnings.append(
                        f"{arm} {var} {c}: sdc_md5 {r['values'].get('sdc_md5')} != {want['value']}"
                    )
        judge["drv_nom_tt_base"] = judge_drv(meta["pt"])
        judge["drv_all_corners_base"] = judge_drv_all(meta["pt"])
        data["judge"][arm] = judge
        data["arms"][arm] = a
    data["warnings"] = warnings
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check", action="store_true", help="fail if comparison.json differs from a rebuild"
    )
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    js = json.dumps(build(), indent=1, sort_keys=False) + "\n"
    out = p(args.out) if not Path(args.out).is_absolute() else Path(args.out)
    if args.check:
        if not out.is_file() or out.read_text() != js:
            print(f"{args.out} is stale; re-run compare.py", file=sys.stderr)
            return 1
        return 0
    out.write_text(js)
    print(f"wrote {args.out}; warnings: {len(warnings)}")
    for w in warnings:
        print("  WARN", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
