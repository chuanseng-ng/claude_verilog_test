#!/usr/bin/env python3
"""Derive the scan-view hold mask from STABLE synchroniser Q-net names (bead j41m.15, carried over from j41m.8).

usage: derive_hold_mask.py NETLIST [--out mask.json] [--validate exempt_pins.txt] [--drop-rule RULE]

The mask is the set of 94 scanned capture flops whose D pin fails hold in the scan view (DFT_ARCHITECTURE 14.13):
34 gray-pointer stage-0 D pins of the 10 async_axi_fifo synchronisers plus 60 MBIST tck->destination rows.  In the
ATPG cut each masked flop keeps its Q as a shift-controllable pseudo-input but its D is NOT observed (capture masking).

Instance ids (`_155181_`) change on every synthesis; the Q-net names below come from the RTL hierarchy and do not.
Validation compares the derived instances with a pin list written by the STA (`exempt_pins.txt`, `<inst>/D` per line)
for the SAME netlist.  --drop-rule exists for the negative control.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist_lib import FLOP_TYPE_RE, Cell, read_cells  # noqa: E402

# (rule name, Q-net regex).  Stage 0 of the 2-FF synchronisers only (`sync_q[0][i]`); stage 1 has no hold exposure.
RULES = (
    ("cdc_gray_axi",
     r"^u_cpu_axi_cdc\.u_(?:aw|w|ar|b|r)_fifo\.u_(?:wr_ptr_to_rd|rd_ptr_to_wr)\.sync_q\[0\]\[\d+\]$"),
    ("mbist_ptr_sync",
     r"^u_mbist\.(?:g_cpu\.u_xing_cpu|u_xing_core)\.u_fifo\.u_wr_ptr_to_rd\.sync_q\[0\]\[\d+\]$"),
    ("mbist_ctl_hold", r"^u_mbist\.(?:g_cpu\.u_xing_cpu|u_xing_core)\.ctl_w\[\d+\]$"),
    ("mbist_core_cfg", r"^u_mbist\.core_cfg_w\[\d+\]$"),
    ("mbist_cpu_cfg", r"^mb_cpu_cfg\[\d+\]$"),
)
_COMPILED = tuple((n, re.compile(p)) for n, p in RULES)


def rule_for(qnet: str, drop_rules: Iterable[str] = ()) -> Optional[str]:
    drop = set(drop_rules)
    for name, rx in _COMPILED:
        if name not in drop and rx.match(qnet):
            return name
    return None


def read_flops(path) -> Dict[str, Cell]:
    return {i: c for i, c in read_cells(path).items() if FLOP_TYPE_RE.match(c.typ)}


def derive(flops: Dict[str, Cell], drop_rules: Iterable[str] = ()) -> List[dict]:
    drop = set(drop_rules)
    out = []
    for inst, c in flops.items():
        q = c.pins.get("Q", "")
        r = rule_for(q, drop)
        if r:
            out.append({"inst": inst, "qnet": q, "dnet": c.pins.get("D", ""), "rule": r, "type": c.typ})
    return sorted(out, key=lambda m: m["inst"])


def validate(mask: List[dict], exempt_file) -> dict:
    expected = {ln.split("/")[0] for ln in Path(exempt_file).read_text().split() if ln.strip()}
    got = {m["inst"] for m in mask}
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    return {
        "ok": not missing and not extra,
        "expected": len(expected),
        "derived": len(got),
        "matched": len(expected & got),
        "missing": missing,
        "extra": extra,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--out")
    ap.add_argument("--validate")
    ap.add_argument("--drop-rule", action="append", default=[])
    a = ap.parse_args(argv)
    mask = derive(read_flops(a.netlist), a.drop_rule)
    by_rule: Dict[str, int] = {}
    for m in mask:
        by_rule[m["rule"]] = by_rule.get(m["rule"], 0) + 1
    print(f"hold-mask flops derived: {len(mask)}  by rule: {by_rule}")
    rc = 0
    result = {"count": len(mask), "by_rule": by_rule, "flops": mask}
    if a.validate:
        rep = validate(mask, a.validate)
        result["validation"] = rep
        print(f"validate vs {a.validate}: matched {rep['matched']}/{rep['expected']}  derived {rep['derived']}  "
              f"missing {len(rep['missing'])}  extra {len(rep['extra'])}")
        if not rep["ok"]:
            print("MISMATCH missing:", rep["missing"][:10], "extra:", rep["extra"][:10])
            rc = 1
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
