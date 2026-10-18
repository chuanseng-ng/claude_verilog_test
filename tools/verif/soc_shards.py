#!/usr/bin/env python3
"""Shard planning and the suite-union check for the soc_all_ci suite list (bead 9ayu.1).

The ordered list of `soc_all_ci` sub-make invocations lives in ONE place,
`SOC_CI_SUITES` in tb/cocotb/soc/Makefile.  An entry is the sub-make's arguments joined with
':' (`sram_controller:SRAM_TARGET=sky130` is `make sram_controller SRAM_TARGET=sky130`).  This
script reads that variable straight from the Makefile (no make, no Verilator needed) and

  list      prints the entries, one per line (--units: the sharding units, see below);
  select    prints the entries of ONE shard (space separated, in list order) -- what
            `make soc_ci_shard SHARD=k NSHARDS=n` and the CI matrix jobs run;
  plan      prints the whole assignment with the estimated load of every shard;
  union     the CI gate: given the `suites_ran.txt` every shard wrote, fails unless the union is
            EXACTLY the list -- no suite lost, none run twice, none unknown.

A suite listed in `SOC_CI_SPLITS` is too heavy for one shard: it is sharded as several UNITS,
`suite:TESTCASE=a,b` (cocotb runs only those tests of the module), whose slices together cover
every test of the module exactly once (tb/tests/test_soc_shards.py checks that against the test
file).  `soc_all_ci` is unaffected: it runs the whole module.  All shard-side logic (select,
plan, union) works on units.

Assignment is deterministic (same inputs, same output, on any host), so every matrix job and the
merge job compute the same plan independently.  It is greedy longest-processing-time on the cost
model in tools/verif/soc_shard_weights.json: a suite costs `run_s`, plus `build_s` of its build
group (suites sharing one content-keyed Verilator build dir) the first time that group lands in a
shard.  A suite absent from the weights file costs `default_run_s`, so a newly added suite shards
without any edit here.  The weights only steer the balance; correctness (the union check) does
not depend on them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MAKEFILE = REPO / "tb" / "cocotb" / "soc" / "Makefile"
DEFAULT_WEIGHTS = Path(__file__).resolve().with_name("soc_shard_weights.json")

_VAR_RE = re.compile(r"^SOC_CI_SUITES\s*:?=((?:[^\n]*\\\n)*[^\n]*)$", re.M)


def parse_suites(makefile_text: str) -> list[str]:
    """Return the ordered SOC_CI_SUITES entries of a Makefile's text."""
    m = _VAR_RE.search(makefile_text)
    if not m:
        raise ValueError("SOC_CI_SUITES is not defined in the Makefile")
    body = m.group(1).replace("\\\n", " ")
    entries = body.split()
    if not entries:
        raise ValueError("SOC_CI_SUITES is empty")
    dup = sorted({e for e in entries if entries.count(e) > 1})
    if dup:
        raise ValueError(f"SOC_CI_SUITES has duplicate entries: {dup}")
    return entries


_SPLIT_RE = re.compile(r"^SOC_CI_SPLITS\s*:?=((?:[^\n]*\\\n)*[^\n]*)$", re.M)


def parse_splits(makefile_text: str) -> dict[str, list[list[str]]]:
    """Return {suite: [[test, ...], ...]} from SOC_CI_SPLITS (empty if the variable is absent)."""
    m = _SPLIT_RE.search(makefile_text)
    return parse_splits_value(m.group(1).replace("\\\n", " ")) if m else {}


def parse_splits_value(value: str) -> dict[str, list[list[str]]]:
    """Parse the VALUE of SOC_CI_SPLITS: `suite=a,b|c ...` -> {suite: [[a, b], [c]]}."""
    out: dict[str, list[list[str]]] = {}
    for entry in value.split():
        suite, sep, rest = entry.partition("=")
        if not sep or not rest:
            raise ValueError(f"bad SOC_CI_SPLITS entry {entry!r} (want suite=a,b|c)")
        slices = [[t for t in sl.split(",") if t] for sl in rest.split("|")]
        if any(not sl for sl in slices):
            raise ValueError(f"empty slice in SOC_CI_SPLITS entry {entry!r}")
        if suite in out:
            raise ValueError(f"duplicate SOC_CI_SPLITS suite {suite!r}")
        out[suite] = slices
    return out


def expand_units(suites: list[str], splits: dict[str, list[list[str]]]) -> list[str]:
    """Replace each split suite by its `suite:TESTCASE=a,b` units, keeping list order."""
    unknown = sorted(set(splits) - set(suites))
    if unknown:
        raise ValueError(f"SOC_CI_SPLITS names suites not in SOC_CI_SUITES: {unknown}")
    units: list[str] = []
    for suite in suites:
        if suite in splits:
            units.extend(f"{suite}:TESTCASE={','.join(sl)}" for sl in splits[suite])
        else:
            units.append(suite)
    return units


def load_units(makefile: Path = DEFAULT_MAKEFILE) -> list[str]:
    text = Path(makefile).read_text()
    return expand_units(parse_suites(text), parse_splits(text))


def load_suites(makefile: Path = DEFAULT_MAKEFILE) -> list[str]:
    return parse_suites(Path(makefile).read_text())


def load_weights(path: Path | None = DEFAULT_WEIGHTS) -> dict:
    if path is None or not Path(path).exists():
        return {"default_run_s": 40.0, "groups": {}, "suites": {}}
    w = json.loads(Path(path).read_text())
    w.setdefault("default_run_s", 40.0)
    w.setdefault("groups", {})
    w.setdefault("suites", {})
    return w


def assign(suites: list[str], nshards: int, weights: dict) -> list[list[str]]:
    """Greedy LPT assignment; every shard keeps the list order.  Deterministic."""
    if nshards < 1:
        raise ValueError("nshards must be >= 1")
    dflt = float(weights.get("default_run_s", 40.0))

    def run_s(s: str) -> float:
        return float(weights["suites"].get(s, {}).get("run_s", dflt))

    def group(s: str) -> str | None:
        return weights["suites"].get(s, {}).get("group")

    def build_s(g: str) -> float:
        return float(weights["groups"].get(g, {}).get("build_s", 0.0))

    index = {s: i for i, s in enumerate(suites)}
    order = sorted(suites, key=lambda s: (-run_s(s), index[s]))
    load = [0.0] * nshards
    groups_in: list[set[str]] = [set() for _ in range(nshards)]
    members: list[list[str]] = [[] for _ in range(nshards)]
    for s in order:
        g = group(s)

        def cost_in(k: int, s=s, g=g) -> float:
            extra = build_s(g) if g and g not in groups_in[k] else 0.0
            return load[k] + run_s(s) + extra

        best = min(range(nshards), key=lambda k: (cost_in(k), k))
        load[best] = cost_in(best)
        if g:
            groups_in[best].add(g)
        members[best].append(s)
    return [sorted(m, key=index.__getitem__) for m in members]


def shard_loads(shards: list[list[str]], weights: dict) -> list[float]:
    dflt = float(weights.get("default_run_s", 40.0))
    out = []
    for m in shards:
        seen: set[str] = set()
        t = 0.0
        for s in m:
            info = weights["suites"].get(s, {})
            t += float(info.get("run_s", dflt))
            g = info.get("group")
            if g and g not in seen:
                seen.add(g)
                t += float(weights["groups"].get(g, {}).get("build_s", 0.0))
        out.append(t)
    return out


def check_union(expected: list[str], ran_by_shard: dict[str, list[str]]) -> list[str]:
    """Return a list of problems (empty = the shards ran exactly `expected`, each once)."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    exp = set(expected)
    for shard, ran in ran_by_shard.items():
        if not ran:
            problems.append(f"{shard}: ran no suites (empty or missing manifest)")
        for s in ran:
            if s in seen:
                problems.append(f"{s}: run twice ({seen[s]} and {shard})")
            else:
                seen[s] = shard
            if s not in exp:
                problems.append(f"{s}: run by {shard} but not in SOC_CI_SUITES")
    for s in expected:
        if s not in seen:
            problems.append(f"{s}: in SOC_CI_SUITES but run by no shard (silently lost)")
    return problems


def _read_manifest(p: Path) -> list[str]:
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text().splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--makefile", type=Path, default=DEFAULT_MAKEFILE)
    ap.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--units", action="store_true", help="print the sharding units")
    p_sel = sub.add_parser("select")
    p_sel.add_argument("--shard", type=int, required=True)
    p_sel.add_argument("--nshards", type=int, required=True)
    p_sel.add_argument("--suites", help="space separated list to shard instead of the Makefile's")
    p_sel.add_argument("--splits", default="", help="value of SOC_CI_SPLITS (with --suites)")
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--nshards", type=int, required=True)
    p_un = sub.add_parser("union")
    p_un.add_argument("manifests", nargs="+", type=Path, help="one suites_ran.txt per shard")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "select" and a.suites:
            suites = expand_units(a.suites.split(), parse_splits_value(a.splits))
        elif a.cmd == "list" and not a.units:
            suites = load_suites(a.makefile)
        else:
            suites = load_units(a.makefile)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if a.cmd == "list":
        print("\n".join(suites))
        return 0
    if a.cmd == "select":
        if not 0 <= a.shard < a.nshards:
            print(f"ERROR: --shard must be in 0..{a.nshards - 1}", file=sys.stderr)
            return 2
        print(" ".join(assign(suites, a.nshards, load_weights(a.weights))[a.shard]))
        return 0
    if a.cmd == "plan":
        w = load_weights(a.weights)
        shards = assign(suites, a.nshards, w)
        for k, (m, t) in enumerate(zip(shards, shard_loads(shards, w))):
            print(f"shard {k}: est {t:7.1f} s  {len(m):2d} suites  {' '.join(m)}")
        return 0
    if a.cmd == "union":
        ran = {str(p): _read_manifest(p) for p in a.manifests}
        problems = check_union(suites, ran)
        total = sum(len(v) for v in ran.values())
        if problems:
            print(f"FAIL: suite union check: {len(problems)} problem(s)")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(
            f"OK: {total} suites run by {len(ran)} shards == the {len(suites)} sharding units of "
            "SOC_CI_SUITES (none lost, none twice)"
        )
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
