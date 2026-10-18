#!/usr/bin/env python3
"""Prove that named output ports of one module are driven DIRECTLY by flip-flops.

Bead claude_verilog_test-ktwt. ``pmu.sv`` used to drive ``*_clk_en_o`` / ``*_iso_en_o`` /
``*_rst_n_o`` from a combinational decode of a 4-bit binary state register. Those nets feed
``cdc_sync`` D pins and the ASYNC clear of ``u_cpu_pmu_rst_sync`` in ``soc_top.sv``, where a
decode glitch is a real event. A functional simulation can never show a glitch (zero-delay
simulators settle each delta cycle), so the property is checked structurally: after ``proc``,
every bit of each named output port must be the Q pin of a ``$dff``-family cell, with nothing
(no LUT, no gate, no mux) in between.

Flow: sv2v (the project's SystemVerilog front-end for yosys, same as the CDC and DFT gates) ->
yosys ``read_verilog; hierarchy -top; proc; opt_clean; write_json`` -> walk the JSON.

Exit status: 0 every bit flop-driven; 1 at least one bit is not (each is printed); 2 tool or
input error. A tool that produced no usable result is never reported as a pass.

Usage:
    check_registered_outputs.py --top pmu --ports cpu_clk_en_o,cpu_iso_en_o,... \
        rtl/soc/apb4_register_bank.sv rtl/soc/pmu.sv
Tools are taken from ``$YOSYS`` / ``$SV2V`` or PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Cell types whose output is a registered value. $dlatch/$adlatch are deliberately absent: a
# latch is transparent, so its output can still follow a glitching D input.
FLOP_TYPES = frozenset(
    {
        "$dff",
        "$dffe",
        "$sdff",
        "$sdffe",
        "$sdffce",
        "$adff",
        "$adffe",
        "$aldff",
        "$aldffe",
        "$dffsr",
        "$dffsre",
    }
)


def _tool(env_name: str, exe: str) -> str:
    path = os.environ.get(env_name) or shutil.which(exe)
    if not path:
        print(f"error: {exe} not found (set ${env_name} or put it on PATH)", file=sys.stderr)
        sys.exit(2)
    return path


def netlist_json(files: list[str], top: str, workdir: Path) -> dict:
    """Return yosys' JSON netlist of ``top`` after ``proc`` (hierarchy kept)."""
    sv2v, yosys = _tool("SV2V", "sv2v"), _tool("YOSYS", "yosys")
    flat = workdir / "flat.v"
    out = workdir / "nl.json"
    res = subprocess.run(
        [sv2v, *files, f"--write={flat}"], capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        print(f"error: sv2v failed:\n{res.stderr}", file=sys.stderr)
        sys.exit(2)
    script = (
        f"read_verilog -sv {flat}; hierarchy -top {top}; proc; opt_clean; write_json {out}"
    )
    res = subprocess.run([yosys, "-q", "-p", script], capture_output=True, text=True, check=False)
    if res.returncode != 0 or not out.exists():
        print(f"error: yosys failed:\n{res.stdout}\n{res.stderr}", file=sys.stderr)
        sys.exit(2)
    return json.loads(out.read_text())


def check(nl: dict, top: str, ports: list[str]) -> list[str]:
    """Return one message per output-port bit that is not driven straight by a flop."""
    mod = nl["modules"].get(top)
    if mod is None:
        return [f"module {top} not in netlist"]
    # bit id -> list of (cell name, cell type) that drive it
    drivers: dict[int, list[tuple[str, str]]] = {}
    for cname, cell in mod["cells"].items():
        dirs = cell.get("port_directions", {})
        for pin, bits in cell["connections"].items():
            if dirs.get(pin) != "output":
                continue
            for b in bits:
                if isinstance(b, int):
                    drivers.setdefault(b, []).append((cname, cell["type"]))
    bad: list[str] = []
    for port in ports:
        p = mod["ports"].get(port)
        if p is None:
            bad.append(f"{port}: no such port on {top}")
            continue
        if p["direction"] != "output":
            bad.append(f"{port}: not an output port")
            continue
        for i, b in enumerate(p["bits"]):
            drv = drivers.get(b) if isinstance(b, int) else None
            if not drv:
                bad.append(f"{port}[{i}]: not driven by any cell (constant or alias to an input)")
            elif len(drv) != 1 or drv[0][1] not in FLOP_TYPES:
                bad.append(f"{port}[{i}]: driven by {', '.join(t for _, t in drv)}, not a flop")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--top", required=True)
    ap.add_argument("--ports", required=True, help="comma-separated output port names")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    ports = [p for p in args.ports.split(",") if p]
    if not ports:
        print("error: --ports is empty", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="chkregout_") as td:
        nl = netlist_json(args.files, args.top, Path(td))
    bad = check(nl, args.top, ports)
    for msg in bad:
        print(f"FAIL {msg}")
    n_bits = len(ports)
    if bad:
        print(f"registered-output check: {len(bad)} violation(s) over {n_bits} port(s)")
        return 1
    print(f"registered-output check: PASS, {n_bits} port(s) all flop-driven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
