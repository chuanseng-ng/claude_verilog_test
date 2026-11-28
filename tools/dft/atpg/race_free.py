#!/usr/bin/env python3
"""Race-free copy of the act-only flops for the zero-delay replay.

usage: race_free.py NETLIST.v --act-only act_only.json --out OUT.v [--top soc_top]    (act_only.json: act_only_flops.py --json)

Verilator evaluates a flop whose Q only feeds asynchronous resets or clocks in its Active region, with an immediate assignment.
Every ordinary flop and gate that reads that Q on the same clock edge sees the NEW value: a scan chain behind such a flop
loses one stage, and a capture edge reads the wrong state.  Silicon has clock-to-Q delay and hold timing, so it does not.

Fix in the replay copy only: for every act-only flop X
  * X stays as it is and keeps driving its trigger loads (asynchronous reset, set, clock and clock-gate pins);
  * a shadow flop X_s of the same cell and pins is added.  Its Q feeds only ordinary logic, so Verilator updates it in the NBA
    region like every other flop;
  * every data load of X.Q (D, SCD, SCE of a flop; latch D) is moved to the shadow copy of the net.  A gate between X.Q and
    the load is duplicated with its inputs on shadow nets, the original gate stays for the trigger loads;
  * X_s and the duplicated gates take their D, SCD and SCE from shadow nets too, so two act-only flops in a row do not race.
The shadow flop sees the same inputs on the same clock and reset as X, so it holds the same value as X in every cycle after
the first edge.  Gates and wires that are not in the forward cone of an act-only Q are untouched.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist_lib import CELL_RE, PIN_RE, norm  # noqa: E402

OUT_PINS = {"X", "Y", "Q", "Q_N", "GCLK", "HI", "LO", "COUT", "SUM"}
SEQ_RE = re.compile(r"sky130_fd_sc_hd__(sdf|df|edf|sedf|dlx|dlclk)")
TRIGGER_PINS = {"CLK", "RESET_B", "SET_B", "GATE", "GATE_N", "RESET", "SET"}
CONST_RE = re.compile(r"^\d+'[bBhHdD]")


def shadow(text: str, act_only: List[str], top: str = "soc_top") -> Tuple[str, dict]:
    cells: Dict[str, Tuple[str, List[Tuple[str, str]]]] = {}
    order: List[str] = []
    for m in CELL_RE.finditer(text):
        inst = norm(m.group(2))
        cells[inst] = (m.group(1), [(p, n.strip()) for p, n in PIN_RE.findall(m.group(3))])
        order.append(inst)
    missing = [x for x in act_only if x not in cells]
    if missing:
        raise SystemExit(f"act-only flops not in the netlist: {missing[:5]}")
    loads: Dict[str, List[Tuple[str, str]]] = {}
    for inst, (typ, pins) in cells.items():
        for p, n in pins:
            if p not in OUT_PINS and n and not CONST_RE.match(n):
                loads.setdefault(n, []).append((inst, p))
    seq = {i for i, (t, _) in cells.items() if SEQ_RE.match(t)}
    # S: nets of the combinational forward cone of every act-only Q (including the Q nets)
    cone: Set[str] = set()
    stack = []
    for x in act_only:
        q = dict(cells[x][1]).get("Q")
        if q:
            stack.append(q)
    gates: Set[str] = set()
    while stack:
        n = stack.pop()
        if n in cone:
            continue
        cone.add(n)
        for inst, p in loads.get(n, []):
            if inst in seq:
                continue
            gates.add(inst)
            stack += [nn for pp, nn in cells[inst][1] if pp in OUT_PINS and nn]
    # does the net reach a data pin of an ordinary flop/latch? (memoised, the cone is acyclic in combinational cells)
    memo: Dict[str, bool] = {}

    def reaches_data(n: str) -> bool:
        if n in memo:
            return memo[n]
        memo[n] = False
        r = False
        for inst, p in loads.get(n, []):
            if inst in seq:
                if p not in TRIGGER_PINS:
                    r = True
            elif any(reaches_data(nn) for pp, nn in cells[inst][1] if pp in OUT_PINS and nn):
                r = True
        memo[n] = r
        return r

    need = {n for n in cone if reaches_data(n)}
    sh = {n: f"rf_net{k}" for k, n in enumerate(sorted(need))}
    new_cells: List[str] = []

    def subst(pins: List[Tuple[str, str]], data_only: bool, outs: Dict[str, str]) -> str:
        parts = []
        for p, n in pins:
            if p in OUT_PINS and p in outs:
                parts.append(f".{p}({outs[p]})")
            elif n in sh and (p not in TRIGGER_PINS or not data_only):
                parts.append(f".{p}({sh[n]})")
            else:
                parts.append(f".{p}({n + ' ' if n.startswith(chr(92)) else n})")
        return ", ".join(parts)

    # shadow copies of the act-only flops, then of the gates that lead to a data pin
    for x in act_only:
        typ, pins = cells[x]
        q = dict(pins)["Q"]
        if q not in sh:
            continue  # Q feeds triggers only: nothing to shadow
        new_cells.append(f"  {typ} rf_{x} ({subst(pins, True, {'Q': sh[q]})});")
    for g in sorted(gates):
        typ, pins = cells[g]
        outs = {p: sh[n] for p, n in pins if p in OUT_PINS and n in sh}
        if not outs:
            continue
        new_cells.append(f"  {typ} rf_{g} ({subst(pins, False, outs)});")
    # move the data loads of cone nets to the shadow nets (text edit of the original cell bodies)
    edits: List[Tuple[int, int, str]] = []
    n_moved = 0
    for m in CELL_RE.finditer(text):
        inst = norm(m.group(2))
        if inst not in seq:
            continue
        pins = [(p, n.strip()) for p, n in PIN_RE.findall(m.group(3))]
        if not any(n in sh and p not in TRIGGER_PINS and p not in OUT_PINS for p, n in pins):
            continue
        body = m.group(3)
        for p, n in pins:
            if n in sh and p not in TRIGGER_PINS and p not in OUT_PINS:
                body = re.sub(rf"\.{p}\(\s*{re.escape(n)}\s*\)", f".{p}({sh[n]})", body, count=1)
                n_moved += 1
        edits.append((m.start(3), m.end(3), body))
    for a, b, body in sorted(edits, reverse=True):
        text = text[:a] + body + text[b:]
    info = {
        "act_only": len(act_only),
        "cone_nets": len(cone),
        "shadow_nets": len(sh),
        "shadow_cells": len(new_cells),
        "data_pins_moved": n_moved,
    }
    if not new_cells:
        return text, info
    mh = re.search(rf"^module {re.escape(top)}\s*\(", text, re.M)
    end = text.index("endmodule", mh.end())
    decl = "".join(f"  wire {w};\n" for w in sh.values())
    text = (
        text[:end]
        + "\n  // race-free shadow copies of the act-only flops (race_free.py)\n"
        + decl
        + "\n".join(new_cells)
        + "\n"
        + text[end:]
    )
    return text, info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("netlist")
    ap.add_argument("--act-only", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", default="soc_top")
    a = ap.parse_args(argv)
    names = json.loads(Path(a.act_only).read_text())["act_only"]
    new, info = shadow(Path(a.netlist).read_text(errors="replace"), names, a.top)
    Path(a.out).write_text(new)
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
