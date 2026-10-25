#!/usr/bin/env python3
"""Structural scan-chain connectivity check on a gate-level Verilog netlist (bead j41m.8, DFT Stage 2).

usage: check_scan_chains.py NETLIST [--in-fmt 'scan_in_i[%d]'] [--out-fmt 'scan_out_o[%d]'] [--chains N]
           [--en-net NET] [--expect-chains N] [--expect-unscanned N] [--expect-length L,L,...] [--json OUT]

Works on the netlist written by CVT.ScanInsert AND on later stages (placed, post-CTS, post-route, fill): hold buffers and
repair buffers that the flow puts between a flop Q and the next SCD pin are traced through (buf/dlygate/clkbuf, input A).

Checks (exit 1 on any failure, 0 only if all pass):
  1. every scan flop (sky130_fd_sc_hd__sdf*) has its SCD driven, through buffers only, by exactly one flop Q or one
     scan-in port, and every flop Q / scan-in port feeds at most one SCD (a chain, never a tree);
  2. walking from scan_in_i[k] reaches scan_out_o[k]'s driver for every chain that has an input load;
  3. every scan flop is on exactly one chain (no orphans, no loops);
  4. every SCE pin is on ONE net (the scan-enable net; --en-net names it) and that net is not a chain data net;
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
    ap.add_argument("--expect-chains", type=int)
    ap.add_argument("--expect-unscanned", type=int)
    ap.add_argument("--expect-length")
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

    sce_nets = {pins.get("SCE") for _, (_, pins) in scan.items()}
    if len(sce_nets) != 1:
        problems.append(f"SCE pins sit on {len(sce_nets)} nets, expected exactly 1: {sorted(map(str, sce_nets))[:4]}")
    elif a.en_net and next(iter(sce_nets)) != norm(a.en_net):
        problems.append(f"SCE net is {next(iter(sce_nets))}, expected {a.en_net}")

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
        "sce_nets": sorted(map(str, sce_nets)),
        "problems": problems,
    }
    print(f"scan flops {len(scan)}  unscanned flops {len(nonscan)}  chains {len(chains)}  lengths {lengths}")
    print(f"SCE nets: {result['sce_nets']}")
    for p in problems[:20]:
        print("FAIL:", p)
    if a.json:
        json.dump(result, open(a.json, "w"), indent=1)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
