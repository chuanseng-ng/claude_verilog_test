#!/usr/bin/env python3
"""Gate: in scan mode every flop is clocked from a port and every async reset is tester-controlled.

Bead claude_verilog_test-j41m.2 (DFT Stage 1a), docs/design/DFT_ARCHITECTURE.md section 14.

usage: check_scan_clk_rst.py design.json [--top soc_top] [--scan-mode scan_mode_i] [--expect-gates N]
       check_scan_clk_rst.py --netlist soc_top_sv2v.v [...]   # runs yosys itself (needs yosys on PATH)

Input is a Yosys JSON of the FLATTENED, `proc`-ed design (no techmap, so $adff/$dff/$dlatch/$mux
survive). For every sequential cell it traces the fan-in cone of

  * ARST (async reset/set) of every $adff/$dffsr/$adlatch-class cell, and
  * CLK (or EN for a latch) of every sequential cell,

backwards through combinational cells and applies the scan-mode rules:

  RESET  a path is CONTROLLED if it ends at a primary input (a pin: the tester drives it), a
         constant, or a $mux whose select is the scan-mode port (the override: in scan mode that
         mux delivers the scan reset). It is a VIOLATION if it ends at the output of ANY
         sequential cell (a flop, latch or memory): that reset toggles while the chains shift.
  CLOCK  a path is CONTROLLED if it passes a $mux whose select is the scan-mode port (the
         test-clock bypass), or ends at a $dlatch whose D input depends on the scan-mode port (the
         clock-gate latch, whose enable is forced by test_en = scan_mode). It is a VIOLATION if it
         ends at a sequential cell output (a flop-generated clock), or at a primary input without
         having passed a scan-mode mux (a flop on a functional clock root in scan mode).

Exit 0 only if there are no violations AND (with --expect-gates) the number of scan-mode muxes
found is at least N, so that a design in which the muxes were optimised away or renamed cannot
pass vacuously. Negative controls (run by tests/test_dft_scan_check.py): replacing the muxes with
wires makes this fail.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SEQ_PREFIXES = ("$dff", "$adff", "$sdff", "$aldff", "$dffsr", "$dlatch", "$adlatch", "$sr",
                "$mem", "$dffe", "$sdffe", "$adffe")
ASYNC_PORTS = {"ARST": "arst", "ALOAD": "aload", "SET": "set", "CLR": "clr"}


def is_seq(t):
    return t.startswith(SEQ_PREFIXES)


def run_yosys(netlist, top):
    out = Path(tempfile.mkdtemp(prefix="scanchk_")) / "d.json"
    script = f"read_verilog -sv -defer {netlist}; hierarchy -top {top}; proc; flatten; opt_clean; write_json {out}"
    subprocess.run([os.environ.get("YOSYS", "yosys"), "-q", "-p", script], check=True)
    return str(out)


def load(path, top):
    d = json.load(open(path))
    mod = d["modules"][top]
    drivers = {}   # bit -> (cell name, port)
    cells = mod["cells"]
    for cname, c in cells.items():
        for port, bits in c["connections"].items():
            if c["port_directions"].get(port) == "output":
                for b in bits:
                    if isinstance(b, int):
                        drivers[b] = (cname, port)
    ports = {n: p for n, p in mod["ports"].items()}
    in_bits = {}
    for n, p in ports.items():
        if p["direction"] == "input":
            for b in p["bits"]:
                if isinstance(b, int):
                    in_bits[b] = n
    return cells, drivers, ports, in_bits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs="?")
    ap.add_argument("--netlist")
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--scan-mode", default="scan_mode_i")
    ap.add_argument("--expect-gates", type=int, default=0)
    ap.add_argument("--max-print", type=int, default=12)
    a = ap.parse_args()
    path = a.json or run_yosys(a.netlist, a.top)
    cells, drivers, ports, in_bits = load(path, a.top)
    sm_bits = set(b for b in ports[a.scan_mode]["bits"] if isinstance(b, int))

    def cell_inputs(c):
        for port, bits in c["connections"].items():
            if c["port_directions"].get(port) == "input":
                for b in bits:
                    if isinstance(b, int):
                        yield port, b

    def mux_is_scan(c):
        return c["type"] in ("$mux", "$pmux") and any(
            isinstance(b, int) and b in sm_bits for b in c["connections"].get("S", []))

    gates = sum(1 for c in cells.values() if mux_is_scan(c))

    def depends_on_scan_mode(bit, seen=None):
        seen = set() if seen is None else seen
        stack = [bit]
        while stack:
            b = stack.pop()
            if b in sm_bits:
                return True
            if b in seen or b not in drivers:
                continue
            seen.add(b)
            cn, _ = drivers[b]
            c = cells[cn]
            if is_seq(c["type"]):
                continue
            stack.extend(x for _, x in cell_inputs(c))
        return False

    def trace(bit, kind):
        """Return list of violation strings for the cone feeding `bit`."""
        viol, seen, stack = [], set(), [(bit, False)]   # (bit, passed_scan_mux)
        while stack:
            b, passed = stack.pop()
            if (b, passed) in seen:
                continue
            seen.add((b, passed))
            if b in in_bits:
                if kind == "clock" and not passed and in_bits[b] != a.scan_mode:
                    viol.append(f"clock reaches port {in_bits[b]} without a scan-mode mux")
                continue
            if b not in drivers:
                continue
            cn, port = drivers[b]
            c = cells[cn]
            t = c["type"]
            if is_seq(t):
                if kind == "clock" and t.startswith("$dlatch"):
                    d = c["connections"].get("D", [])
                    if any(isinstance(x, int) and depends_on_scan_mode(x) for x in d):
                        continue   # clock-gate latch with the scan-mode force in its D cone
                    viol.append(f"clock-gate latch {cn} has no scan-mode term in its enable")
                else:
                    viol.append(f"{kind} is generated by sequential cell {cn} ({t})")
                continue
            if mux_is_scan(c):
                continue   # controlled: the scan branch is a port, the other branch is bypassed
            for _, x in cell_inputs(c):
                stack.append((x, passed))
        return viol

    violations = []
    n_async = n_seq = 0
    for cname, c in cells.items():
        t = c["type"]
        if not is_seq(t):
            continue
        n_seq += 1
        # clock / latch enable
        ck = c["connections"].get("CLK") or c["connections"].get("EN") or []
        for b in ck:
            if isinstance(b, int):
                # a mux-selected clock counts as `passed`: handled by trace() stopping at the mux
                for v in trace(b, "clock"):
                    violations.append((cname, t, "CLK", v))
        for p in ASYNC_PORTS:
            for b in c["connections"].get(p, []):
                if isinstance(b, int):
                    n_async += 1
                    for v in trace(b, "reset"):
                        violations.append((cname, t, p, v))

    print(f"sequential cells: {n_seq}; async reset/set pins checked: {n_async}; scan-mode muxes: {gates}")
    uniq = sorted(set(violations))
    print(f"violations: {len(uniq)}")
    for v in uniq[: a.max_print]:
        print("FAIL:", *v)
    if len(uniq) > a.max_print:
        print(f"... {len(uniq) - a.max_print} more")
    if gates < a.expect_gates:
        print(f"FAIL: expected at least {a.expect_gates} scan-mode muxes, found {gates} (optimised away?)")
        return 1
    return 1 if uniq else 0


if __name__ == "__main__":
    sys.exit(main())
