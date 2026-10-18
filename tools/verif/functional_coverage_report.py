#!/usr/bin/env python3
"""Merge and gate FUNCTIONAL (covergroup) coverage written by the cocotb suites (bead h367).

Why this exists
---------------
``tools/verif/coverage_report.py`` measures Verilator *code* coverage.  The cocotb flow had no
covergroup mechanism at all, so the verification sign-off criterion ``functional_coverage_pct: 100``
could not be met for any peripheral.  The suites now sample ``cocotb-coverage`` (PyPI) coverpoints
through ``tb/cocotb/soc/func_cov.py`` and write one YAML file per simulator process
(``$FUNC_COV_DIR/<module>__<pid>.yml``, the library's own ``export_to_yaml`` format).  This script
merges every such file of a run (all CI shards) and gates the result.  Method, evaluation and how a
peripheral adds a model: ``docs/verification/FUNCTIONAL_COVERAGE.md``.

Merge
-----
The input format is ``{item name: {type, size, coverage, cover_percentage, weight, at_least,
bins:_hits}}``; only items with ``bins:_hits`` (coverpoints and crosses) carry data.  The same
coverpoint in two files is ONE coverpoint: its per-bin hit counts are added.  Totals are RECOMPUTED
from the merged hit counts (a bin is covered at ``hits >= at_least``, a coverpoint is worth
``weight`` per bin), never taken from the inputs' ``coverage`` counters.  Two files that declare
the same coverpoint with different bin sets (or weight / at_least) are a model mismatch -- the
union would silently change the denominator -- and are an ERROR (exit 2).

Waivers (``--waivers``)
-----------------------
One per line, ``item | bin | category | justification``.  ``item`` is the full coverage name
(``i2c.bus.addr_result``); ``bin`` is the bin label, or for a cross the labels joined by commas
(``read,nack``).  ``category`` is ``b`` -- unreachable by design -- the only waivable class: a bin
that is merely not hit yet is a test gap and is fixed by a test, never by a waiver.  A justification
is mandatory.  A waiver removes an UNCOVERED bin from the denominator; the raw percentage is
reported beside the adjusted one.  A waiver is STALE -- and fails ``--gate`` -- when its item or
bin is not in the merged model OR when its bin was in fact hit (an unneeded waiver rots).

Gates (``--gates``)
-------------------
``group | floor_pct | min_bins | justification``, one line per top-level group (the first dotted
component, ``i2c``).  Every group listed here is REQUIRED: its absence from the data is an ERROR,
never a pass (cf. bead dwp: exit 0 over no data).  ``floor_pct`` is checked against the ADJUSTED
percentage; ``min_bins`` against the model size (waived bins included) so deleting coverpoints to
reach the floor fails the gate.  Lowering either is an explicit, reviewable edit of that file.

Exit status
-----------
0 report written / gate passed.  1 ``--gate`` and a group is under its floor, under its
``min_bins``, or a waiver is stale.  2 could not evaluate: no input, an unparsable file, a model
mismatch, a bad waiver / gates file, or a required group with no data.  Exit 2 never means
"evaluated and failed".

Usage::

    functional_coverage_report.py --in <dir-or-file> [--in ...] [--waivers FILE] [--gates FILE]
                                  [--out-md F] [--out-json F] [--out-yaml F] [--gate]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

EXIT_OK, EXIT_GATE_FAIL, EXIT_ERROR = 0, 1, 2
HITS_KEY = "bins:_hits"


class ReportError(Exception):
    """The input cannot be evaluated (maps to exit status 2)."""


@dataclass
class Leaf:
    """A coverpoint or cross after merging."""

    name: str
    kind: str  # "point" | "cross"
    weight: int
    at_least: int
    hits: OrderedDict = field(default_factory=OrderedDict)  # bin key -> merged hit count

    def covered(self, key: str) -> bool:
        return self.hits[key] >= self.at_least


@dataclass(frozen=True)
class Waiver:
    item: str
    bin: str  # normalised bin key, as it appears in the YAML
    category: str
    reason: str
    line: int


@dataclass(frozen=True)
class Gate:
    group: str
    floor_pct: float
    min_bins: int
    reason: str


def _norm_key(key) -> str:
    """The YAML bin key as a string; a cross key is the str() of a label tuple."""
    return str(key)


def _kind(type_str: str) -> str:
    return "cross" if "CoverCross" in type_str else "point"


def load_yaml(path: Path) -> dict:
    """Parse one cocotb-coverage YAML export into ``{name: Leaf}`` (data items only)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReportError(f"{path}: cannot read as YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ReportError(f"{path}: not a coverage export (top level is not a mapping)")
    leaves = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict) or HITS_KEY not in entry:
            continue  # a CoverItem group node: recomputed from its leaves
        try:
            hits = OrderedDict((_norm_key(k), int(v)) for k, v in entry[HITS_KEY].items())
            leaves[str(name)] = Leaf(
                str(name),
                _kind(str(entry.get("type", ""))),
                int(entry["weight"]),
                int(entry["at_least"]),
                hits,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ReportError(f"{path}: malformed entry {name!r}: {exc}") from exc
    if not leaves:
        raise ReportError(f"{path}: contains no coverpoint (an empty database is not a pass)")
    return leaves


def merge(dbs: list) -> dict:
    """Merge per-process databases: hit counts add, the model must agree."""
    merged: dict = {}
    for source, db in dbs:
        for name, leaf in db.items():
            cur = merged.get(name)
            if cur is None:
                merged[name] = Leaf(
                    name, leaf.kind, leaf.weight, leaf.at_least, OrderedDict(leaf.hits)
                )
                continue
            if (
                set(cur.hits) != set(leaf.hits)
                or cur.weight != leaf.weight
                or cur.at_least != leaf.at_least
                or cur.kind != leaf.kind
            ):
                raise ReportError(
                    f"model mismatch for {name!r} in {source}: bins/weight/at_least differ from "
                    f"another input (a different revision of the model?)"
                )
            for key, count in leaf.hits.items():
                cur.hits[key] += count
    return merged


def collect_inputs(specs: list) -> list:
    """Expand --in arguments (files or directories) to a sorted list of YAML paths."""
    paths = []
    for spec in specs:
        p = Path(spec)
        if p.is_dir():
            paths += sorted(list(p.rglob("*.yml")) + list(p.rglob("*.yaml")))
        elif p.is_file():
            paths.append(p)
        else:
            raise ReportError(f"--in {spec}: no such file or directory")
    if not paths:
        raise ReportError("no coverage YAML found: nothing was measured (this is not a pass)")
    return paths


def _cross_key(parts: list) -> str:
    return str(tuple(parts))


def parse_waivers(path: Path) -> list:
    """``item | bin | category | justification`` lines; ``#`` comments and blanks ignored."""
    out = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("|")]
        if len(fields) != 4 or not all(fields):
            raise ReportError(f"{path}:{no}: want 'item | bin | category | justification'")
        item, binspec, category, reason = fields
        if category != "b":
            raise ReportError(
                f"{path}:{no}: category must be 'b' (unreachable by design); "
                f"a test gap is fixed by a test, not waived"
            )
        parts = [p.strip() for p in binspec.split(",")]
        out.append(
            Waiver(item, binspec if len(parts) == 1 else _cross_key(parts), category, reason, no)
        )
    return out


def parse_gates(path: Path) -> list:
    """``group | floor_pct | min_bins | justification`` lines."""
    out = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [f.strip() for f in line.split("|")]
        if len(fields) != 4 or not all(fields):
            raise ReportError(f"{path}:{no}: want 'group | floor_pct | min_bins | justification'")
        try:
            out.append(Gate(fields[0], float(fields[1]), int(fields[2]), fields[3]))
        except ValueError as exc:
            raise ReportError(f"{path}:{no}: {exc}") from exc
    return out


@dataclass
class GroupResult:
    name: str
    size: int = 0
    covered: int = 0
    waived: int = 0
    bins: int = 0
    uncovered: list = field(default_factory=list)  # (item, bin) not covered and not waived
    waived_list: list = field(default_factory=list)  # (item, bin, reason)

    @property
    def raw_pct(self) -> float:
        return 100.0 * self.covered / self.size if self.size else 0.0

    @property
    def adjusted_pct(self) -> float:
        denom = self.size - self.waived
        return 100.0 * self.covered / denom if denom > 0 else 0.0


def evaluate(model: dict, waivers: list) -> tuple:
    """Return ``(groups, subgroups, stale)``: per top-level group and per two-level group results
    plus the stale-waiver messages."""
    by_key = {(w.item, w.bin): w for w in waivers}
    used = set()
    groups: dict = {}
    subgroups: dict = {}
    for name in sorted(model):
        leaf = model[name]
        top = name.split(".")[0]
        sub = ".".join(name.split(".")[:2])
        for key in leaf.hits:
            targets = (
                groups.setdefault(top, GroupResult(top)),
                subgroups.setdefault(sub, GroupResult(sub)),
            )
            covered = leaf.covered(key)
            wv = by_key.get((name, key))
            if wv is not None:
                used.add((name, key))
            for res in targets:
                res.size += leaf.weight
                res.bins += 1
                if covered:
                    res.covered += leaf.weight
                elif wv is not None:
                    res.waived += leaf.weight
                    res.waived_list.append((name, key, wv.reason))
                else:
                    res.uncovered.append((name, key))
    stale = []
    for w in waivers:
        leaf = model.get(w.item)
        if leaf is None or w.bin not in leaf.hits:
            stale.append(f"waiver line {w.line}: {w.item} / {w.bin} is not in the merged model")
        elif leaf.covered(w.bin):
            stale.append(
                f"waiver line {w.line}: {w.item} / {w.bin} was HIT ({leaf.hits[w.bin]}), "
                f"the waiver is unneeded -- remove it"
            )
    return groups, subgroups, stale


def gate_failures(groups: dict, gates: list, stale: list) -> list:
    """Every reason the gate is red.  A required group with no data raises ReportError."""
    fails = list(stale)
    for gate in gates:
        res = groups.get(gate.group)
        if res is None:
            raise ReportError(
                f"required group {gate.group!r} has no data: its tests did not "
                f"sample (or did not export) -- not a pass"
            )
        if res.bins < gate.min_bins:
            fails.append(
                f"{gate.group}: model has {res.bins} bins, below min_bins "
                f"{gate.min_bins} (was the model shrunk?)"
            )
        if res.adjusted_pct + 1e-9 < gate.floor_pct:
            fails.append(
                f"{gate.group}: adjusted {res.adjusted_pct:.2f}% < floor "
                f"{gate.floor_pct:g}% ({len(res.uncovered)} bin(s) uncovered)"
            )
    return fails


def merged_yaml(model: dict) -> dict:
    """The merged model in cocotb-coverage's export schema (readable by its merge/report tools)."""
    out: dict = {}
    for name in sorted(model, key=str.lower):
        leaf = model[name]
        size = leaf.weight * len(leaf.hits)
        cov = leaf.weight * sum(1 for k in leaf.hits if leaf.covered(k))
        out[name] = {
            "type": f"<class 'cocotb_coverage.coverage.Cover{leaf.kind.capitalize()}'>",
            "size": size,
            "coverage": cov,
            "cover_percentage": round(100.0 * cov / size, 2) if size else 0.0,
            "weight": leaf.weight,
            "at_least": leaf.at_least,
            HITS_KEY: dict(leaf.hits),
        }
    return out


def render_md(
    groups: dict, subgroups: dict, model: dict, stale: list, fails: list, inputs: list
) -> str:
    lines = [
        "# Functional coverage",
        "",
        f"Merged {len(inputs)} coverage file(s); {sum(len(v.hits) for v in model.values())} "
        f"bins in {len(model)} coverpoints/crosses.",
        "",
        "| group | bins | covered | waived | raw % | adjusted % |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for res in list(groups.values()) + list(subgroups.values()):
        lines.append(
            f"| {res.name} | {res.bins} | {res.covered}/{res.size} | {res.waived} | "
            f"{res.raw_pct:.2f} | {res.adjusted_pct:.2f} |"
        )
    for res in groups.values():
        if res.uncovered:
            lines += ["", f"## Uncovered bins in `{res.name}`", ""]
            lines += [f"- `{item}` / `{key}`" for item, key in res.uncovered]
        if res.waived_list:
            lines += ["", f"## Waived bins in `{res.name}` (category b, unreachable by design)", ""]
            lines += [f"- `{item}` / `{key}`: {why}" for item, key, why in res.waived_list]
    lines += ["", "## Gate", ""]
    lines += [f"- FAIL: {f}" for f in stale + [f for f in fails if f not in stale]] or ["- PASS"]
    return "\n".join(lines) + "\n"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument(
        "--in",
        dest="inputs",
        action="append",
        default=[],
        metavar="PATH",
        help="coverage YAML file or directory (repeatable)",
    )
    ap.add_argument("--waivers", type=Path)
    ap.add_argument("--gates", type=Path)
    ap.add_argument("--out-md", type=Path)
    ap.add_argument("--out-json", type=Path)
    ap.add_argument("--out-yaml", type=Path, help="merged database, cocotb-coverage schema")
    ap.add_argument("--gate", action="store_true", help="exit 1 when a gate is red")
    args = ap.parse_args(argv)
    try:
        paths = collect_inputs(args.inputs)
        model = merge([(str(p), load_yaml(p)) for p in paths])
        waivers = parse_waivers(args.waivers) if args.waivers else []
        gates = parse_gates(args.gates) if args.gates else []
        groups, subgroups, stale = evaluate(model, waivers)
        fails = gate_failures(groups, gates, stale) if args.gate else []
    except ReportError as exc:
        print(f"functional_coverage_report: ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR
    md = render_md(groups, subgroups, model, stale, fails, paths)
    print(md)
    if args.out_md:
        args.out_md.write_text(md, encoding="utf-8")
    if args.out_json:
        args.out_json.write_text(
            json.dumps(
                {
                    "inputs": [str(p) for p in paths],
                    "groups": {
                        g.name: {
                            "bins": g.bins,
                            "size": g.size,
                            "covered": g.covered,
                            "waived": g.waived,
                            "raw_pct": round(g.raw_pct, 2),
                            "adjusted_pct": round(g.adjusted_pct, 2),
                            "uncovered": [list(u) for u in g.uncovered],
                        }
                        for g in groups.values()
                    },
                    "stale_waivers": stale,
                    "gate_failures": fails,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.out_yaml:
        args.out_yaml.write_text(
            yaml.safe_dump(merged_yaml(model), default_flow_style=False), encoding="utf-8"
        )
    if args.gate and fails:
        print(f"functional_coverage_report: GATE FAILED ({len(fails)})", file=sys.stderr)
        return EXIT_GATE_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
