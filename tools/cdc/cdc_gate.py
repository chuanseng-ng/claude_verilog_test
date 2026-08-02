#!/usr/bin/env python3
"""Turn a raw cdc_snitch report into a meaningful pass/fail CDC gate.

cdc_snitch classifies a register BAD when its data combines more than one
clock domain.  On this SoC that raw verdict is unusable as a gate: the tool
models every top-level input port as its own clock domain, cannot tell a
clock-gate output from its source clock, and cannot express a qualified
crossing (an async FIFO, a 2-phase handshake).  The 2026-08-02 baseline was
BAD=16233, of which 15962 are pure modelling artifacts.

This script re-derives the verdict:

  1. canonicalize every source domain    (clock aliases, reset ports, buses)
  2. a register is still BAD only if >= 2 distinct canonical domains remain
  3. match the residue against explicit, justified waivers
  4. fail if anything is left unwaived -- or if a waiver matched nothing

Step 4's second half matters as much as the first: a waiver that stops
matching is either a fixed bug whose waiver should go, or a renamed signal
whose crossing is no longer being checked.  Both are failures.

Config format and the rationale for each rule: tools/cdc/cdc_config.yml
Usage:  cdc_gate.py <report> [-c config] [--json out] [-v]
Exit:   0 = clean, 1 = unwaived BAD or stale waiver, 2 = bad usage/parse
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# cdc_snitch writes:  "<stat> <magic?> <bit> <name> clk <clk> inputs ( <doms> )"
# `magic` is an empty field when absent, so the separator collapses to two
# spaces -- hence the optional group rather than a fixed column count.
_LINE_RE = re.compile(
    r"^(?P<stat>OK1|CDC|OKX|BAD)\s+(?P<magic>magic\s+)?"
    r"(?P<bit>\d+)\s+(?P<name>\S+)\s+clk\s+(?P<clk>\S+)\s+"
    r"inputs \((?P<inputs>.*)\)\s*$"
)
# Each input entry is summarize()d as "<count> x <domain>".
_DOM_RE = re.compile(r"^\s*\d+\s+x\s+")
# Bit-selects on a port name: apb_paddr_i[3] -> apb_paddr_i
_BITSEL_RE = re.compile(r"\[\d+\]$")

_VALID_KINDS = ("tool-limitation", "accepted-risk")


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict:
    try:
        import yaml
    except ImportError:  # pragma: no cover - environment problem, not logic
        raise ConfigError(
            "PyYAML is required to read the CDC gate config.\n"
            "  install with:  python3 -m pip install --user pyyaml"
        )
    with path.open() as fh:
        cfg = yaml.safe_load(fh) or {}

    if not cfg.get("clock_domains"):
        raise ConfigError("'clock_domains' must list the design's real clock domains")
    cfg.setdefault("domain_aliases", {})
    cfg.setdefault("reset_domains", [])
    cfg.setdefault("port_domains", {})
    cfg.setdefault("waivers", [])

    seen_ids = set()
    for i, w in enumerate(cfg["waivers"]):
        for field in ("id", "kind", "dest", "reason", "ref"):
            if not w.get(field):
                raise ConfigError(f"waiver #{i} is missing required field '{field}'")
        if w["id"] in seen_ids:
            raise ConfigError(f"duplicate waiver id '{w['id']}'")
        seen_ids.add(w["id"])
        if w["kind"] not in _VALID_KINDS:
            raise ConfigError(
                f"waiver '{w['id']}' has kind '{w['kind']}'; expected one of {_VALID_KINDS}"
            )
        # An accepted risk without a tracking issue is just an excuse.
        if w["kind"] == "accepted-risk" and not w.get("bead"):
            raise ConfigError(
                f"waiver '{w['id']}' is kind 'accepted-risk' and must name a tracking bead"
            )
        try:
            w["_dest_re"] = re.compile(w["dest"])
        except re.error as exc:
            raise ConfigError(f"waiver '{w['id']}' has an invalid 'dest' regex: {exc}")
    return cfg


def resolve_alias(dom: str, aliases: dict) -> str:
    """Follow the alias chain (cpu_gated_clk -> cpu_clk_i), guarding cycles."""
    seen = {dom}
    while dom in aliases:
        dom = aliases[dom]
        if dom in seen:
            raise ConfigError(f"domain_aliases contains a cycle at '{dom}'")
        seen.add(dom)
    return dom


def canonical_domains(raw_inputs: str, cfg: dict) -> set[str]:
    """Reduce cdc_snitch's raw input-domain list to real, distinct domains."""
    aliases = cfg["domain_aliases"]
    resets = set(cfg["reset_domains"])
    ports = cfg["port_domains"]

    clocks = set(cfg["clock_domains"])

    out: set[str] = set()
    for entry in raw_inputs.split(","):
        dom = _DOM_RE.sub("", entry).strip()
        if not dom:
            continue
        base = _BITSEL_RE.sub("", dom)  # collapse bus bits to the bus
        if base in resets:
            continue  # a reset is not a clock domain
        if base in ports:
            out.add(resolve_alias(ports[base], aliases))
            continue
        canon = resolve_alias(dom, aliases)
        if canon in clocks:
            out.add(canon)
            continue
        # Not a declared clock, not a reset, not mapped: a top-level port that
        # cdc_snitch is modelling as a clock domain. Collapse its bits to the
        # bus and tag it, so a port artifact can never be misread as a real
        # clock crossing in the gate output.
        out.add("PORT:" + base)
    return out


def parse_report(path: Path, cfg: dict):
    counts = Counter()
    residue = []
    unparsed = []
    for lineno, line in enumerate(path.open(), 1):
        if line.startswith(("  tree", "  ")) or not line.strip():
            continue  # verbose per-BAD trace lines
        m = _LINE_RE.match(line)
        if not m:
            if line.split(" ", 1)[0] in ("OK1", "CDC", "OKX", "BAD"):
                unparsed.append((lineno, line.rstrip()))
            continue
        counts[m.group("stat")] += 1
        if m.group("stat") != "BAD":
            continue
        doms = canonical_domains(m.group("inputs"), cfg)
        if len(doms) < 2:
            counts["RESOLVED"] += 1
            continue
        residue.append(
            {
                "name": m.group("name"),
                "clk": resolve_alias(m.group("clk"), cfg["domain_aliases"]),
                "domains": "+".join(sorted(doms)),
            }
        )
    return counts, residue, unparsed


def apply_waivers(residue, cfg):
    hits = defaultdict(list)
    unwaived = []
    for item in residue:
        for w in cfg["waivers"]:
            if not w["_dest_re"].search(item["name"]):
                continue
            # An optional exact domain-set match stops a broad `dest` regex
            # from silently absorbing a NEW crossing on the same instance.
            if w.get("domains") and w["domains"] != item["domains"]:
                continue
            hits[w["id"]].append(item)
            break
        else:
            unwaived.append(item)
    return hits, unwaived


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", type=Path, help="cdc_snitch report (soc_top_cdc.txt)")
    ap.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path(__file__).with_name("cdc_config.yml"),
        help="gate config (default: alongside this script)",
    )
    ap.add_argument("--json", type=Path, help="also write a machine-readable summary")
    ap.add_argument(
        "-v", "--verbose", action="store_true", help="list every waived register"
    )
    args = ap.parse_args(argv)

    if not args.report.is_file():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 2
    try:
        cfg = load_config(args.config)
        counts, residue, unparsed = parse_report(args.report, cfg)
    except ConfigError as exc:
        print(f"ERROR: {args.config}: {exc}", file=sys.stderr)
        return 2

    hits, unwaived = apply_waivers(residue, cfg)
    stale = [w["id"] for w in cfg["waivers"] if not hits.get(w["id"])]
    risks = [w for w in cfg["waivers"] if w["kind"] == "accepted-risk" and hits.get(w["id"])]

    raw_bad = counts["BAD"]
    print("=" * 72)
    print("CDC gate — cdc_snitch report, after domain canonicalization")
    print("=" * 72)
    print(f"  report        : {args.report}")
    print(f"  config        : {args.config}")
    print()
    print(f"  OK1 (same domain)          : {counts['OK1']:>6}")
    print(f"  CDC (marked magic_cdc)     : {counts['CDC']:>6}")
    print(f"  OKX (unmarked, 1 source)   : {counts['OKX']:>6}")
    print(f"  BAD (raw, from cdc_snitch) : {raw_bad:>6}")
    print(f"    - modelling artifacts    : {counts['RESOLVED']:>6}"
          "   (reset pins, clock-gate aliases, per-bit buses)")
    print(f"    - waived                 : {sum(len(v) for v in hits.values()):>6}")
    print(f"    - UNWAIVED               : {len(unwaived):>6}")
    print()

    if unparsed:
        print(f"  !! {len(unparsed)} classification line(s) did not parse — "
              "the report format may have changed:")
        for lineno, text in unparsed[:5]:
            print(f"       {args.report.name}:{lineno}: {text[:100]}")
        print()

    if hits:
        print("Waivers applied:")
        for w in cfg["waivers"]:
            got = hits.get(w["id"])
            if not got:
                continue
            tag = "RISK" if w["kind"] == "accepted-risk" else "tool"
            print(f"  [{tag}] {w['id']:<38} {len(got):>5} register(s)   {w['ref']}")
            if args.verbose:
                for item in got:
                    print(f"           {item['name']}  ({item['domains']})")
        print()

    if risks:
        print("!! Accepted-risk waivers are ACTIVE — these are real gaps, not "
              "tool artifacts:")
        for w in risks:
            print(f"     {w['id']}  (tracked: {w['bead']})")
            print(f"       {' '.join(w['reason'].split())[:150]}")
        print()

    failed = False
    if unwaived:
        failed = True
        by_class = defaultdict(list)
        for item in unwaived:
            by_class[item["domains"]].append(item)
        print(f"FAIL: {len(unwaived)} unwaived cross-domain register(s), "
              f"{len(by_class)} class(es):")
        for dom, items in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
            print(f"\n  {len(items):>5} register(s) combining: {dom}")
            for item in items[:6]:
                print(f"           {item['name']}   (clk {item['clk']})")
            if len(items) > 6:
                print(f"           ... and {len(items) - 6} more")
        print("\n  Each is either a real CDC defect, or a correct structure the "
              "tool\n  cannot express. Fix the former; add a justified waiver "
              "for the latter.")
        print()

    if stale:
        failed = True
        print("FAIL: stale waiver(s) — matched nothing in this report.")
        print("      A waiver that stops matching means the crossing it covered "
              "was\n      renamed, removed, or is no longer being checked. "
              "Re-confirm, don't\n      just delete:")
        for wid in stale:
            print(f"        {wid}")
        print()

    if not failed:
        print("PASS: no unwaived cross-domain registers; every waiver still matches.")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "counts": dict(counts),
                    "raw_bad": raw_bad,
                    "resolved": counts["RESOLVED"],
                    "waived": {k: len(v) for k, v in hits.items()},
                    "unwaived": unwaived,
                    "stale_waivers": stale,
                    "accepted_risks": [w["id"] for w in risks],
                    "pass": not failed,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"  wrote {args.json}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
