#!/usr/bin/env python3
"""Digest a merged urg text report into per-module scores and a machine-readable hole list.

    vcs_cov_holes.py <urgReport dir> [--json out.json] [--tables]

Reads `modlist.txt` (per-module scores) and `modinfo.txt` (per-module detail: uncovered lines, branch
arms, condition rows, FSM states/transitions, never-toggled ports/signals) of a report written by
`tools/eda/vcs_coverage.py merge` (urg -flex_merge modules, -format text|both).  Nothing here changes a
score: it only re-slices what urg printed so a human can rank the holes.

A point is reported as a hole only if it is uncovered in EVERY version (parameter shape) of the module
that carries it -- a point hit in one configuration is not listed (the same "hit if any instance hit it"
rule as tools/verif/coverage_report.py).  `shapes` says how many versions the module has.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"^\s*(-?\d+(?:\.\d+)?|--)\s*")


def parse_modlist(path: Path) -> dict[str, dict]:
    """Module rows of `Design Module List`: the rows under every column-0 `SCORE ... NAME` header (up to the
    next blank line).  Parameter-shape sub-rows sit under an indented header and are skipped."""
    out = {}
    keys = ("score", "line", "cond", "toggle", "fsm", "branch", "assert")
    collecting = False
    for ln in path.read_text(errors="replace").splitlines():
        if ln.startswith("SCORE") and "NAME" in ln:
            collecting = True
            continue
        if collecting:
            if not ln.strip():
                collecting = False
                continue
            f = ln.split()
            if len(f) >= 8 and re.fullmatch(r"-?\d+(\.\d+)?|--", f[0]):
                out[f[7]] = {k: (None if v == "--" else float(v)) for k, v in zip(keys, f[:7])}
    return out


# Header forms: `... Module : pmu`, `... Module : pmu (version = 1)`, `... Module : aes128_core ( parameter A=1,B=2 ) `
SEC = re.compile(r"^(Line|Cond|Toggle|FSM|Branch) Coverage for Module : (\S+)(?:\s+\((?:version = )?(.*?)\))?\s*$")
MODHDR = re.compile(r"^Module : (\S+)\s*$")
SRC = re.compile(r"^\s*(\d+)\s{2,}(?:(\d+)/(\d+)\s+(==>)?\s*)?(.*)$")


def sections(text: str):
    """Yield (kind, module, version, [lines]) for every per-module coverage section of modinfo.txt."""
    lines = text.splitlines()
    cur = None
    buf: list[str] = []
    for ln in lines:
        m = SEC.match(ln)
        if m or ln.startswith("Module : ") or ln.startswith("Coverage for Instance") \
                or re.match(r"^(Line|Cond|Toggle|FSM|Branch) Coverage for Instance", ln):
            if cur:
                yield (*cur, buf)
            cur = (m.group(1), m.group(2), (m.group(3) or "0").strip()) if m else None
            buf = []
            continue
        if cur:
            buf.append(ln)
    if cur:
        yield (*cur, buf)


def line_status(buf: list[str]) -> dict[int, tuple[bool, str]]:
    """source line -> (covered?, text) for every listed line carrying a hit/total counter."""
    out: dict[int, tuple[bool, str]] = {}
    for ln in buf:
        m = re.match(r"^(\d+)\s+(\d+)/(\d+)(\s+==>)?\s*(.*)$", ln)
        if m:
            ok = m.group(4) is None
            ln_no = int(m.group(1))
            # a generate loop lists the same line once per iteration (`***repeat n`): uncovered if ANY iteration missed it
            prev = out.get(ln_no)
            out[ln_no] = (ok and (prev[0] if prev else True), m.group(5).strip())
    return out


def branch_status(buf: list[str]) -> dict[tuple[int, str], tuple[bool, str]]:
    """(statement line, arm row) -> (covered?, statement text) for every row of the `Branches:` tables."""
    out: dict[tuple[int, str], tuple[bool, str]] = {}
    stmt_line = None
    stmt_txt = ""
    i = 0
    n = len(buf)
    while i < n:
        ln = buf[i]
        m = re.match(r"^(\d+)\s{2,}(\S.*)$", ln)
        if m and stmt_line is None:
            stmt_line, stmt_txt = int(m.group(1)), m.group(2).strip()
        if ln.strip() == "Branches:":
            i += 1
            while i < n and not buf[i].strip():
                i += 1
            i += 1  # column header
            while i < n and buf[i].strip():
                row = buf[i].rstrip()
                if row.endswith("Covered") and "Status" not in row:
                    ok = not row.endswith("Not Covered")
                    arm = re.sub(r"\s+", " ", re.sub(r"(Not )?Covered$", "", row)).strip()
                    key = (stmt_line or 0, arm)
                    prev = out.get(key)
                    out[key] = (ok and (prev[0] if prev else True), stmt_txt)
                i += 1
            stmt_line = None
            continue
        i += 1
    return out


def cond_status(buf: list[str]) -> dict[tuple[int, str, str], bool]:
    out: dict[tuple[int, str, str], bool] = {}
    line = 0
    expr = ""
    for ln in buf:
        m = re.match(r"^\s*LINE\s+(\d+)", ln)
        if m:
            line = int(m.group(1))
            continue
        m = re.match(r"^\s*EXPRESSION\s+(.*)$", ln)
        if m:
            expr = m.group(1).strip()
            continue
        r = ln.rstrip()
        if r.endswith("Covered") and "Status" not in r and line:
            ok = not r.endswith("Not Covered")
            key = (line, expr, re.sub(r"\s+", " ", re.sub(r"(Not )?Covered$", "", r)).strip())
            out[key] = ok and out.get(key, True)
    return out


def fsm_status(buf: list[str]) -> dict[tuple[str, str, str, int], bool]:
    out: dict[tuple[str, str, str, int], bool] = {}
    fsm = ""
    kind = ""
    for ln in buf:
        m = re.match(r"^Summary for FSM :: (\S+)", ln)
        if m:
            fsm = m.group(1)
            continue
        if re.match(r"^states\s+Line No", ln):
            kind = "state"
            continue
        if re.match(r"^transitions\s+Line No", ln):
            kind = "transition"
            continue
        m = re.match(r"^(\S+)\s+(\d+)\s+(Not Covered|Covered)\s*$", ln)
        if m and kind:
            out[(fsm, kind, m.group(1), int(m.group(2)))] = m.group(3) == "Covered"
    return out


def toggle_status(buf: list[str]) -> dict[tuple[str, int, str], str]:
    """(name, width, port|signal) -> 'never' | 'partial' | 'full'."""
    out = {}
    kind = "port"
    for ln in buf:
        if ln.startswith("Port Details"):
            kind = "port"
        elif ln.startswith("Signal Details"):
            kind = "signal"
        m = re.match(r"^(\S+?)(?:\[(\d+):(\d+)\])?\s+(Yes|No)\s+(Yes|No)\s+(Yes|No)(?:\s+(\w+))?\s*$", ln)
        if not m:
            continue
        hi, lo = m.group(2), m.group(3)
        width = abs(int(hi) - int(lo)) + 1 if hi is not None else 1
        t, f10, f01 = m.group(4), m.group(5), m.group(6)
        st = "never" if (t, f10, f01) == ("No", "No", "No") else ("full" if (f10, f01) == ("Yes", "Yes") and t == "Yes" else "partial")
        rng = f"[{hi}:{lo}]" if hi is not None else ""
        out[(m.group(1) + rng, width, kind)] = st
    return out


def combine(per_shape: list[dict]) -> tuple[list, list]:
    """-> (never_hit, shape_only): keys uncovered in every shape that lists them / uncovered in some but hit in another."""
    keys = set()
    for d in per_shape:
        keys |= set(d)
    never, some = [], []
    for k in keys:
        st = [d[k] for d in per_shape if k in d]
        bad = [x for x in st if not (x[0] if isinstance(x, tuple) else x)]
        if not bad:
            continue
        (never if len(bad) == len(st) else some).append(k)
    return sorted(never, key=str), sorted(some, key=str)


def digest(report: Path) -> dict:
    scores = parse_modlist(report / "modlist.txt")
    text = (report / "modinfo.txt").read_text(errors="replace")
    files: dict[str, str] = {}
    cur = None
    for ln in text.splitlines():
        m = MODHDR.match(ln)
        if m:
            cur = m.group(1)
        elif cur and ln.startswith("/") and ln.endswith((".sv", ".v")) and cur not in files:
            files[cur] = ln.strip()
    per = collections.defaultdict(lambda: collections.defaultdict(list))  # mod -> kind -> [per-shape dict]
    shapes = collections.defaultdict(set)
    texts: dict[tuple[str, int], str] = {}
    for kind, mod, ver, buf in sections(text):
        shapes[mod].add(ver)
        if kind == "Line":
            st = line_status(buf)
            per[mod]["line"].append({k: v[0] for k, v in st.items()})
            for k, v in st.items():
                texts[(mod, k)] = v[1]
        elif kind == "Branch":
            st = branch_status(buf)
            per[mod]["branch"].append({k: v[0] for k, v in st.items()})
            for k, v in st.items():
                texts[(mod, k[0])] = v[1]
        elif kind == "Cond":
            per[mod]["cond"].append(cond_status(buf))
        elif kind == "FSM":
            per[mod]["fsm"].append(fsm_status(buf))
        elif kind == "Toggle":
            per[mod]["toggle_raw"].append(toggle_status(buf))
    res = {}
    for mod, sc in scores.items():
        d = per.get(mod, {})
        r = {"scores": sc, "file": files.get(mod), "shapes": max(1, len(shapes.get(mod, ()))),
             "shape_labels": sorted(shapes.get(mod, ()))}
        for kind in ("line", "branch", "cond", "fsm"):
            if d.get(kind):
                nv, sm = combine(d[kind])
                if kind == "line":
                    nv = [(k, texts.get((mod, k), "")) for k in nv]
                    sm = [(k, texts.get((mod, k), "")) for k in sm]
                elif kind == "branch":
                    nv = [(k[0], k[1], texts.get((mod, k[0]), "")) for k in nv]
                    sm = [(k[0], k[1], texts.get((mod, k[0]), "")) for k in sm]
                r[kind] = nv
                r[kind + "_shape_only"] = sm
        raw = d.get("toggle_raw", [])
        if raw:
            names = set()
            for x in raw:
                names |= set(x)
            nev, par = [], []
            for k in sorted(names):
                sts = [x[k] for x in raw if k in x]
                if all(s == "never" for s in sts):
                    nev.append(k)
                elif not any(s == "full" for s in sts):
                    par.append(k)
            r["toggle_never"] = nev
            r["toggle_partial"] = par
        res[mod] = r
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    data = digest(a.report)
    if a.json:
        a.json.write_text(json.dumps(data, indent=1))
    print(f"{len(data)} modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
