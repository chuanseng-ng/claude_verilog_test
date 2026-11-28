#!/usr/bin/env python3
"""List the flops that Verilator evaluates only in its Active region.

usage: act_only_flops.py OBJ_DIR [--map map.json] [--json]

Verilator treats a flop whose Q only feeds an asynchronous reset or a clock as clock-generating logic and assigns its Q
immediately, in `*_act_sequent_*`, not in the NBA region.  A scan flop behind such a flop samples the NEW Q on the same clock
edge, so the zero-delay replay shifts the chain by one stage per such flop (the chain looks one flop shorter).  Silicon does not
do this: hold timing is checked by STA.  A flop is "act-only" when its `buf_Q` is assigned in an act/ico function and in no NBA
function.  With --map the flops are reported as chain/position of the scan chains in map.json (replay_netlist.py / mk_cut.py).

Doc: tm:ch:dft-architecture:1814-chain2-cause
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path

ASSIGN_RE = re.compile(r"u_dut__DOT___(\d+)___DOT__buf_Q = ")
FUNC_RE = re.compile(r"^(?:VL_ATTR_COLD )?void\s+\S*?___(\w+)\(")


def classify(obj_dir: Path):
    """Return (act_names, nba_names) of the cell instances whose buf_Q is assigned in an act/ico or an nba function."""
    act, nba = set(), set()
    for f in glob.glob(str(obj_dir / "Vreplay_top___024root__*.cpp")):
        cur = ""
        for line in open(f, errors="replace"):
            if line.startswith("void ") or line.startswith("VL_ATTR_COLD void"):
                cur = line.split("(")[0].split()[-1]
            m = ASSIGN_RE.search(line)
            if not m:
                continue
            name = "_%s_" % m.group(1)
            if "_act_" in cur or "_ico_" in cur or "ico" in cur.split("___")[-1]:
                act.add(name)
            elif "nba" in cur:
                nba.add(name)
    return act, nba


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("obj_dir")
    ap.add_argument("--map")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    act, nba = classify(Path(a.obj_dir))
    only = sorted(act - nba)
    if not act:
        print(
            "no act-region flop assignment found: wrong OBJ_DIR or a different Verilator naming",
            file=sys.stderr,
        )
        return 2
    out = {"act_only": only, "n_act": len(act), "n_nba": len(nba), "chains": {}}
    if a.map:
        m = json.load(open(a.map))
        for k, ch in enumerate(m["chains"]):
            pos = [i for i, n in enumerate(ch) if n in set(only)]
            if pos:
                out["chains"][str(k)] = {
                    "len": len(ch),
                    "positions": pos,
                    "latency_if_shift_race": len(ch) - len(pos),
                }
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"act-only flops: {len(only)} (act {len(act)}, nba {len(nba)})")
        for k, v in out["chains"].items():
            print(
                f"  chain {k}: len {v['len']} act-only positions {v['positions']} -> expected zero-delay latency {v['latency_if_shift_race']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
