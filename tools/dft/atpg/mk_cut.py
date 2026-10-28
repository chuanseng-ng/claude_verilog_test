#!/usr/bin/env python3
"""Build the full-scan combinational ATPG cut of a (prepared) Sky130 gate netlist with Yosys (bead j41m.15).

usage: mk_cut.py NETLIST --top TOP --out DIR [--const port=0|1 ...] [--bbox-hdr FILE ...] [--yosys PATH] [--lib tt.lib]

Pipeline (the yosys script is written to DIR/mk_cut.ys so it can be re-run by hand):
  read_liberty (no -lib: every Sky130 cell becomes logic / $_DFF_ / $_DLATCH_)  -> read stubs for black boxes -> read netlist
  -> a wrapper `cut_top` ties the scan-mode capture constants (port=value) -> flatten -> opt (constants fold, the scan
  muxes and functional mux legs collapse) -> latches become flops (one structural approximation, counted) ->
  `expose -evert -evert-dff`: flop Q -> pseudo primary input, flop D -> pseudo primary output; black-box output pins ->
  inputs and input pins -> outputs -> abc -g (generic gates, the fault universe of Quaigh) -> write_blif.

Black boxes (CPU macro, SRAM) have no X state in Quaigh: coverage of the logic around them is an UPPER BOUND.
`opt -full` and `opt_dff` must NOT be used (they delete flops, see the comment in script()): on the timer probe `opt -full` removed every flop (2026-10-28).
"""

import argparse
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_YOSYS = "/nobackup/claude_sim_build/j41m15/bin/yosys"
DEFAULT_LIB = "/nobackup/claude_sim_build/j41m15/in/tt.lib"
GATES = "AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX"
DECL_RE = re.compile(r"^\s*(input|output|inout)\s*(\[[^\]]+\])?\s*([\w$\\.\[\]]+)\s*;", re.M)
PARAM_RE = re.compile(r"parameter\s+(\w+)\s*=\s*(\d+)\s*;")


def read_ports(text: str, top: str) -> List[Tuple[str, str, Optional[str]]]:
    """(direction, name, range) of every port of module `top` in Verilog-2001 non-ANSI or ANSI-ish text."""
    m = re.search(rf"\bmodule\s+{re.escape(top)}\s*\(", text)
    if not m:
        raise SystemExit(f"module {top} not found")
    end = text.index("endmodule", m.end())
    body = text[m.start():end]
    params = {k: int(v) for k, v in PARAM_RE.findall(body)}
    ports = []
    for d, rng, name in DECL_RE.findall(body):
        if d == "inout":
            continue  # power pins of the SRAM model; never connected in the gate netlist
        if rng:
            expr = rng[1:-1]
            for k, v in params.items():
                expr = re.sub(rf"\b{k}\b", str(v), expr)
            if not re.fullmatch(r"[\d\s+\-*:]+", expr):
                raise SystemExit(f"unsupported range expression {rng} on port {name}")
            hi, lo = (int(eval(x, {"__builtins__": {}}, {})) for x in expr.split(":"))  # noqa: S307  digits and + - * only
            rng = f"[{hi}:{lo}]"
        ports.append((d, name, rng))
    return ports


def bbox_stub(path: Path, top: str) -> str:
    raw = (gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)).read()
    ports = read_ports(raw, top)
    if not ports:
        raise SystemExit(f"no ports found for {top} in {path}")
    names = ", ".join(n for _, n, _ in ports)
    decl = "\n".join(f"  {d} {r or ''} {n};" for d, n, r in ports)
    return f"(* blackbox *)\nmodule {top}({names});\n{decl}\nendmodule\n"


def top_ports(netlist: Path, top: str) -> List[Tuple[str, str, Optional[str]]]:
    return read_ports(Path(netlist).read_text(errors="replace"), top)


def wrapper(top: str, ports, consts: Dict[str, int]) -> str:
    """cut_top: the original top with the constant ports tied; everything else is passed through as a port."""
    outer = [(d, n, r) for d, n, r in ports if n not in consts]
    for c in consts:
        if c not in [n for _, n, _ in ports]:
            raise SystemExit(f"--const {c}: not a port of {top}")
    lines = [f"module cut_top({', '.join(n for _, n, _ in outer)});"]
    for d, n, r in outer:
        lines.append(f"  {d} {r or ''} {n};")
    for d, n, r in ports:
        if n in consts:
            if r:
                raise SystemExit(f"--const {n}: bus ports are not supported")
            lines.append(f"  wire {n} = 1'b{consts[n]};")
    conn = ", ".join(f".{n}({n})" for _, n, _ in ports)
    lines.append(f"  {top} u_dut({conn});")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


LATCH_MAP = """\
(* techmap_celltype = "$_DLATCH_P_" *)
module _latch_p (input E, input D, output Q);
  \\$_DFF_P_ _TECHMAP_REPLACE_ (.C(E), .D(D), .Q(Q));
endmodule
(* techmap_celltype = "$_DLATCH_N_" *)
module _latch_n (input E, input D, output Q);
  \\$_DFF_N_ _TECHMAP_REPLACE_ (.C(E), .D(D), .Q(Q));
endmodule
"""


def script(netlist: Path, out: Path, lib: str, stubs: List[Path], consts: Dict[str, int], top: str,
           bbox_mods: List[str]) -> str:
    s = [
        f"read_liberty -ignore_miss_func -ignore_miss_dir -ignore_miss_data_latch {lib}",
    ]
    s += [f"read_verilog -sv -lib {p}" for p in stubs]
    s += [
        f"read_verilog -sv {netlist}",
        f"read_verilog -sv {out}/cut_top.v",
        "hierarchy -top cut_top",
        "flatten",
        "delete t:$scopeinfo",
        "opt_clean",
        # Async resets become sync logic on the reset net; the scan-mode constants fold it later.  Latches become
        # flops (counted).  Flops are NOT exposed here: write_blif emits them as `.latch` and Quaigh's own
        # `expose_dff` turns them into pseudo-input/output pairs (flop order = BLIF order, which the later
        # pattern-to-chain mapping needs).  opt_dff is never run (it replaces a flop whose D folds to a constant by that
        # constant, but a scan flop stays loadable), and `keep` stops opt_clean from deleting flops whose Q is unused
        # (their D stays observable through the chain).
        "async2sync",
        "dffunmap",  # async2sync leaves $_SDFF_* (sync reset); turn them into plain $_DFF_P_ + logic so every flop is a `.latch`
        f"techmap -map {out}/latch_map.v",
        "setattr -set keep 1 t:$_DFF_*",
        "opt_clean -purge",
        f"tee -o {out}/ff_census.rpt stat",
    ] + ([f"expose -evert {' '.join('t:' + m for m in bbox_mods)}"] if bbox_mods else []) + [
        "opt_expr", "opt_merge", "opt_muxtree", "opt_reduce", "opt_clean -purge",
        "opt_expr", "opt_merge", "opt_muxtree", "opt_reduce", "opt_clean -purge",
        "opt_expr", "opt_merge", "opt_muxtree", "opt_reduce", "opt_clean -purge",
        "opt_expr", "opt_merge", "opt_muxtree", "opt_reduce", "opt_clean -purge",
        f"tee -o {out}/pre_abc.rpt stat",
        f"abc -g {GATES}",
        "opt_clean -purge",
        f"tee -o {out}/cut_stat.rpt stat",
        f"write_blif -gates {out}/cut.blif",
    ]
    return "\n".join(s) + "\n"


def dce_blif(text: str) -> Tuple[str, int, int, List[str]]:
    """Drop `.names` blocks that reach no output and no flop D input (clock-network logic ends at `.latch` clocks, which
    Quaigh ignores: left in, its faults would be counted as 'proven untestable').  Returns (text, kept, dropped)."""
    text = text.replace("\\\n", " ")
    lines = text.split("\n")
    blocks, header, latches, outputs, unmodelled = {}, [], [], [], []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith(".names"):
            nets = ln.split()[1:]
            j = i + 1
            while j < len(lines) and lines[j] and not lines[j].startswith("."):
                j += 1
            blocks[nets[-1]] = (nets[:-1], lines[i:j])
            i = j
            continue
        if ln.startswith((".gate", ".subckt")):
            unmodelled.append(ln.split()[1])  # a cell with no logic function in the Liberty (clock gates): not data logic
        elif ln.startswith(".latch"):
            latches.append(ln)
        elif ln.startswith(".outputs"):
            outputs += ln.split()[1:]
            header.append(ln)
        elif ln.strip() and not ln.startswith("#"):
            header.append(ln)
        i += 1
    live, stack = set(), outputs + [ln.split()[1] for ln in latches]
    while stack:
        n = stack.pop()
        if n in live or n not in blocks:
            continue
        live.add(n)
        stack.extend(blocks[n][0])
    body = [ln for n, (_, b) in blocks.items() if n in live for ln in b]
    end = [h for h in header if h.startswith(".end")]
    head = [h for h in header if not h.startswith(".end")]
    return "\n".join(head + latches + body + end) + "\n", len(live), len(blocks) - len(live), unmodelled


def parse_consts(items: List[str]) -> Dict[str, int]:
    d = {}
    for it in items:
        k, v = it.split("=")
        if v not in ("0", "1"):
            raise SystemExit(f"bad constant {it}")
        d[k] = int(v)
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--top", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--const", action="append", default=[])
    ap.add_argument("--bbox", action="append", default=[], metavar="MODULE=HEADER_FILE",
                    help="black box: module name and a file (.v or .v.gz) whose header declares its ports")
    ap.add_argument("--yosys", default=DEFAULT_YOSYS)
    ap.add_argument("--lib", default=DEFAULT_LIB)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    consts = parse_consts(a.const)
    stubs = []
    for b in a.bbox:
        mod, hdr = b.split("=", 1)
        p = out / f"bbox_{mod}.v"
        p.write_text(bbox_stub(Path(hdr), mod))
        stubs.append(p)
    ports = top_ports(Path(a.netlist), a.top)
    (out / "cut_top.v").write_text(wrapper(a.top, ports, consts))
    (out / "latch_map.v").write_text(LATCH_MAP)
    ys = out / "mk_cut.ys"
    ys.write_text(script(Path(a.netlist), out, a.lib, stubs, consts, a.top, [b.split('=')[0] for b in a.bbox]))
    r = subprocess.run([a.yosys, "-q", "-l", str(out / "yosys.log"), str(ys)], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        return r.returncode
    stat = (out / "cut_stat.rpt").read_text()
    cells = int(re.search(r"Number of cells:\s+(\d+)", stat).group(1))
    raw = (out / "cut.blif").read_text()
    blif, kept, dropped, unmodelled = dce_blif(raw)
    bad = sorted({t for t in unmodelled if t.startswith("$")})
    if bad:  # a Yosys internal cell type in the BLIF is a flop or gate we failed to lower: never drop it silently
        print(f"ERROR: unlowered internal cells in the cut: {bad}")
        return 2
    (out / "cut_raw.blif").write_text(raw)
    (out / "cut.blif").write_text(blif)
    n_in = len(re.search(r"^\.inputs (.*?)(?<!\\)$", blif, re.M | re.S).group(1).replace("\\\n", " ").split())
    n_out = len(re.search(r"^\.outputs (.*?)(?<!\\)$", blif, re.M | re.S).group(1).replace("\\\n", " ").split())
    info = {"top": a.top, "constants": consts, "blackboxes": [b.split("=")[0] for b in a.bbox],
            "cut_cells_yosys": cells, "gates_kept": kept, "gates_dead_dropped": dropped,
            "unmodelled_cells_dropped": {t: unmodelled.count(t) for t in sorted(set(unmodelled))},
            "flops": len(re.findall(r"^\.latch", blif, re.M)), "cut_cells": cells, "cut_inputs": n_in, "cut_outputs": n_out}
    (out / "cut_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
