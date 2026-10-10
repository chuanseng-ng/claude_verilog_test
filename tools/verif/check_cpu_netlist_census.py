#!/usr/bin/env python3
"""Tripwire: the forwarding-select flops survived synthesis (bead gc0y deliverable 4).

This is NOT a general correctness proof.  It guards the ONE known casualty of the dud4 defect:
with the hazard-unit port connections elaborated as ``5'x`` the Synlig netlist had no ``fwd_b_*``
nets/flops and 5 fewer flops (4863 vs 4868 on main RTL, 4829 vs 4834 on the pinned RTL).

Checks on a flat Yosys gate netlist (Verilog):
  * every ``--require-net`` regex (default: the three fwd_b_* registers) matches a declared net;
  * the number of flop instances (cells matching ``--flop-regex``) is inside [min, max].
Defaults are the Sky130 ``rv32i_cpu_top`` numbers (4868 dfxtp on current main, band +-60 for RTL
growth).  The ASAP7 netlists do not keep these net names, so use ``--require-net`` overrides or
only the flop band there.  Exit 0 pass, 1 tripwire fired, 2 unreadable/empty input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_NETS = [r"fwd_b_sel_r\[", r"fwd_b_ex1c_r", r"fwd_b_ex1b2_r"]
DEFAULT_FLOP = r"^\s*sky130_fd_sc_hd__(?:dfxtp|dfrtp|dfstp|dfbbp|dfxbp|dfrbp|dfsbp)\w*\s"


def census(text: str, nets: list[str], flop_regex: str) -> dict:
    """Count matching nets (declared) and flop instances."""
    net_hits = {
        n: len(re.findall(r"^\s*(?:wire|input|output)\b[^;\n]*" + n, text, re.M)) for n in nets
    }
    flops = len(re.findall(flop_regex, text, re.M))
    return {"nets": net_hits, "flops": flops}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    ap.add_argument("netlist", type=Path)
    ap.add_argument("--require-net", action="append", default=None, help="regex; repeatable")
    ap.add_argument("--flop-regex", default=DEFAULT_FLOP)
    ap.add_argument("--min-flops", type=int, default=4800)
    ap.add_argument("--max-flops", type=int, default=4950)
    args = ap.parse_args(argv)
    try:
        text = args.netlist.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"check_cpu_netlist_census: cannot read {args.netlist}: {exc}", file=sys.stderr)
        return 2
    if "module " not in text:
        print(
            "check_cpu_netlist_census: no Verilog module in input (never a pass)", file=sys.stderr
        )
        return 2
    nets = DEFAULT_NETS if args.require_net is None else args.require_net
    res = census(text, nets, args.flop_regex)
    bad = [f"required net /{n}/ not declared" for n, c in res["nets"].items() if c == 0]
    if not args.min_flops <= res["flops"] <= args.max_flops:
        bad.append(f"flop count {res['flops']} outside [{args.min_flops}, {args.max_flops}]")
    print(f"census: flops={res['flops']} nets={res['nets']}")
    for b in bad:
        print(f"TRIPWIRE: {b}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
