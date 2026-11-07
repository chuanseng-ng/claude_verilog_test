#!/usr/bin/env python3
"""Structural scan-chain connectivity check on a gate-level Verilog netlist (bead j41m.8, DFT Stage 2).

usage: check_scan_chains.py NETLIST [--in-fmt 'scan_in_i[%d]'] [--out-fmt 'scan_out_o[%d]'] [--chains N]
           [--en-net NET] [--out-gate-net NET] [--expect-chains N] [--expect-unscanned N] [--expect-length L,L,...] [--json OUT]

Works on the netlist written by CVT.ScanInsert AND on later stages (placed, post-CTS, post-route, fill): hold buffers and
repair buffers that the flow puts between a flop Q and the next SCD pin are traced through (buf/dlygate/clkbuf, input A).

Checks (exit 1 on any failure, 0 only if all pass):
  1. every scan flop (sky130_fd_sc_hd__sdf*) has its SCD driven, through buffers only, by exactly one flop Q or one
     scan-in port, and every flop Q / scan-in port feeds at most one SCD (a chain, never a tree);
  2. walking from scan_in_i[k] reaches scan_out_o[k]'s driver for every chain that has an input load;
  3. every scan flop is on exactly one chain (no orphans, no loops);
  4. every SCE pin traces back (through buffers) to ONE root net (--en-net names it);
  4b. with --out-gate-net NET (SoC, bead j41m.17): every scan_out_o[n] is driven by an AND2 (sky130 and2_*) whose one input
      traces, through buffers only, to the chain's last flop Q and whose other input traces, through buffers only, to the net
      NET (the crypto wipe-done net).  A buffer, or any other driver, in place of the AND is an error.
  5. optional: chain count, per-chain lengths, number of flops that are NOT scan cells (--expect-unscanned).
Prints chain lengths and the unscanned-flop count so a run record can quote them.
"""
import argparse
import json
import re
import sys
from collections import defaultdict

CELL_RE = re.compile(r"\n\s*(sky130_fd_sc_hd__\w+)\s+(\\?\S+)\s*\((.*?)\);", re.S)
PIN_RE = re.compile(r"\.(\w+)\(([^()]*)\)")
BUF_RE = re.compile(r"sky130_fd_sc_hd__(buf|clkbuf|dlygate\w*|dlymetal\w*|clkdlybuf\w*)_")
FLOP_RE = re.compile(r"sky130_fd_sc_hd__(sdf|df|edf|sedf)\w*")


def norm(n: str) -> str:
    return n.strip().replace("\\", "").replace(" ", "")


def parse(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    cells = {}
    for typ, name, body in CELL_RE.findall(text):
        cells[name.strip()] = (typ, {p: norm(n) for p, n in PIN_RE.findall(body)})
    return cells


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--in-fmt", default="scan_in_i[%d]")
    ap.add_argument("--out-fmt", default="scan_out_o[%d]")
    ap.add_argument("--chains", type=int, default=8, help="number of scan port pairs to look for")
    ap.add_argument("--en-net")
    ap.add_argument("--out-gate-net", help="net every scan_out_o[n] must be ANDed with (crypto wipe-done); omit for the CPU macro")
    ap.add_argument("--expect-chains", type=int)
    ap.add_argument("--expect-unscanned", type=int)
    ap.add_argument("--expect-length")
    ap.add_argument("--explain-qrx", help="regex: unscanned flops whose Q net matches are accounted for (crypto keys)")
    ap.add_argument("--explain-clk", help="comma list of clock roots (through buffers/inverters) whose flops are intentionally unscanned")
    ap.add_argument("--json")
    a = ap.parse_args()

    cells = parse(a.netlist)
    problems = []
    raw = open(a.netlist, encoding="utf-8", errors="replace").read()
    if re.search(r"\bscan_(?:enable|in|out)_\d+\b", raw):
        problems.append("insert_dft's own ports (scan_enable_N / scan_in_N / scan_out_N) are still in the netlist")
    driver = {}  # net -> (cell, pin) for output pins
    for cname, (typ, pins) in cells.items():
        for pin, net in pins.items():
            if pin in ("Q", "X", "Y", "HI", "LO", "Q_N"):
                driver[net] = (cname, pin)

    def trace_back(net):
        """Follow `net` back through buffers; return ('flop', cell) | ('port', net) | ('other', cell)."""
        for _ in range(64):
            d = driver.get(net)
            if d is None:
                return ("port", net)
            cell, pin = d
            typ, pins = cells[cell]
            if FLOP_RE.match(typ) and pin == "Q":
                return ("flop", cell)
            if BUF_RE.match(typ):
                net = pins.get("A", "")
                continue
            return ("other", cell)
        return ("other", "loop")

    def root_net(net, stop=None):
        """Follow `net` back through buffers only, stopping at `stop`; return the net where the walk ends."""
        for _ in range(64):
            if net == stop:
                return net
            d = driver.get(net)
            if d is None:
                return net
            typ_, pins_ = cells[d[0]]
            if BUF_RE.match(typ_):
                net = pins_.get("A", "")
                continue
            return net
        return net

    def check_out_gate(k, out_net, last):
        """scan_out_o[k] must be and2(Q of the chain's last flop, wipe-done net); returns a list of problems."""
        want = norm(a.out_gate_net)
        out_net = root_net(out_net)  # later stages may add port/repair buffers after the gate
        d = driver.get(out_net)
        if d is None:
            return [f"chain {k}: {out_net} has no driver"]
        cell, _pin = d
        typ, pins_ = cells[cell]
        if not re.match(r"sky130_fd_sc_hd__and2_\d+$", typ):
            return [f"chain {k}: the scan-out port is driven (behind buffers only) by {typ} {cell}, expected an AND2 gated by {want} (no wipe-done gate)"]
        ins = [pins_.get("A", ""), pins_.get("B", "")]
        for flop_in, gate_in in (ins, ins[::-1]):
            if trace_back(flop_in) == ("flop", last) and root_net(gate_in, want) == want:
                return []
        return [
            f"chain {k}: AND {cell} on {out_net} has inputs {ins}: one must trace to the last flop {last} and the other to {want} "
            f"(found {[trace_back(i) for i in ins]}, roots {[root_net(i, want) for i in ins]})"
        ]

    scan = {c: v for c, v in cells.items() if re.match(r"sky130_fd_sc_hd__sdf", v[0])}
    nonscan = {c: v for c, v in cells.items() if FLOP_RE.match(v[0]) and c not in scan}

    pred = {}
    heads = defaultdict(list)
    succ_count = defaultdict(int)
    for c, (typ, pins) in scan.items():
        kind, who = trace_back(pins.get("SCD", ""))
        if kind == "other":
            problems.append(f"SCD of {c} is driven by {who}, not a flop Q or a scan-in port")
            continue
        pred[c] = (kind, who)
        succ_count[(kind, who)] += 1
    for key, n in succ_count.items():
        if n > 1:
            problems.append(f"{key[0]} {key[1]} feeds {n} SCD pins (a tree, not a chain)")

    nxt = {}
    for c, (kind, who) in pred.items():
        if kind == "flop":
            nxt[who] = c
    port_head = {}
    for c, (kind, who) in pred.items():
        if kind == "port":
            port_head[who] = c

    chains = []
    seen = set()
    for k in range(a.chains):
        pin_net = norm(a.in_fmt % k)
        out_net = norm(a.out_fmt % k)
        head = port_head.get(pin_net)
        if head is None:
            continue
        cur, length = head, 0
        while cur is not None and cur not in seen:
            seen.add(cur)
            length += 1
            last = cur
            cur = nxt.get(cur)
        if cur is not None:
            problems.append(f"chain {k} loops at {cur}")
        if a.out_gate_net:
            problems.extend(check_out_gate(k, out_net, last))
        else:
            end = trace_back(out_net)
            if end != ("flop", last):
                problems.append(f"chain {k}: {out_net} is driven by {end}, expected the last flop {last}")
        chains.append({"index": k, "length": length, "first": head, "last": last})
    orphans = [c for c in scan if c not in seen]
    if orphans:
        problems.append(f"{len(orphans)} scan flops are on no chain (first: {orphans[:3]})")
    stray = [p for p in port_head if p not in {norm(a.in_fmt % k) for k in range(a.chains)}]
    if stray:
        problems.append(f"scan flops fed from unexpected port(s) {stray}")

    # SCE: after repair_design / CTS the enable net is a buffer tree; trace each pin back to its root.
    roots = defaultdict(int)
    stop = norm(a.en_net) if a.en_net else None

    def gate_sig(cell):
        """(function, input roots) of a cell, inputs followed back through buffers: two cells with the same signature are the same gate."""
        typ, pins_ = cells[cell]
        fn = re.sub(r"_\d+$", "", typ.replace("sky130_fd_sc_hd__", ""))
        ins = sorted((pn, root_net(n)) for pn, n in pins_.items() if pn not in ("X", "Y", "Q", "Q_N", "HI", "LO"))
        return fn, tuple(ins)

    ref_sig = None
    if stop and driver.get(stop):
        ref_sig = gate_sig(driver[stop][0])

    def sce_root(net):
        for _ in range(64):
            if net == stop:
                return stop
            d = driver.get(net)
            if d is None:
                return net
            cell, _pin = d
            typ, pins_ = cells[cell]
            if BUF_RE.match(typ):
                net = pins_.get("A", "")
                continue
            # the resizer clones the enable gate to split fanout (cloneN): same function, same input nets = same root
            if ref_sig is not None and gate_sig(cell) == ref_sig:
                return stop
            return f"{typ.replace('sky130_fd_sc_hd__', '')}:{cell}"
        return "loop"

    for _, (_, pins) in scan.items():
        roots[sce_root(pins.get("SCE", ""))] += 1
    sce_nets = set(roots)
    if len(roots) != 1:
        problems.append(f"SCE pins trace to {len(roots)} different roots, expected exactly 1: {sorted(roots.items(), key=lambda kv: -kv[1])[:4]}")
    elif a.en_net and next(iter(roots)) != norm(a.en_net):
        problems.append(f"SCE root is {next(iter(roots))}, expected {a.en_net}")

    if a.explain_qrx or a.explain_clk:
        qrx = re.compile(a.explain_qrx) if a.explain_qrx else None
        clk_roots = set(norm(x) for x in (a.explain_clk or "").split(",") if x)

        def clk_root(net):
            for _ in range(64):
                d = driver.get(net)
                if d is None:
                    return net
                cell, _pin = d
                typ, pins_ = cells[cell]
                if BUF_RE.match(typ) or re.match(r"sky130_fd_sc_hd__(inv|clkinv)_", typ):
                    net = pins_.get("A", "")
                    continue
                return f"{typ}:{cell}"
            return "loop"

        unexplained = []
        by_reason = defaultdict(int)
        for c, (typ, pins) in nonscan.items():
            if qrx and qrx.search(pins.get("Q", "")):
                by_reason["qnet-regex"] += 1
            elif clk_root(pins.get("CLK", "")) in clk_roots:
                by_reason["clock:" + clk_root(pins.get("CLK", ""))] += 1
            else:
                unexplained.append(c)
        print("unscanned flops explained by:", dict(by_reason))
        if unexplained:
            problems.append(f"{len(unexplained)} unscanned flops are not explained by the exclusion rules (first: {unexplained[:3]})")
    lengths = [c["length"] for c in chains]
    if a.expect_chains is not None and len(chains) != a.expect_chains:
        problems.append(f"{len(chains)} chains, expected {a.expect_chains}")
    if a.expect_unscanned is not None and len(nonscan) != a.expect_unscanned:
        problems.append(f"{len(nonscan)} non-scan flops, expected {a.expect_unscanned}")
    if a.expect_length and [int(x) for x in a.expect_length.split(",")] != lengths:
        problems.append(f"chain lengths {lengths}, expected {a.expect_length}")

    result = {
        "scan_flops": len(scan),
        "unscanned_flops": len(nonscan),
        "chains": chains,
        "chain_lengths": lengths,
        "sce_roots": dict(roots),
        "problems": problems,
    }
    print(f"scan flops {len(scan)}  unscanned flops {len(nonscan)}  chains {len(chains)}  lengths {lengths}")
    print(f"SCE roots: {result['sce_roots']}")
    for p in problems[:20]:
        print("FAIL:", p)
    if a.json:
        json.dump(result, open(a.json, "w"), indent=1)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
