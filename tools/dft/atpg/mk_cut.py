#!/usr/bin/env python3
"""Build the full-scan combinational ATPG cut of a (prepared) Sky130 gate netlist with Yosys (bead j41m.15).

usage: mk_cut.py NETLIST --top TOP --out DIR [--const port=0|1 ...] [--bbox-hdr FILE ...] [--yosys PATH] [--lib tt.lib] [--cellpin]

Pipeline (the yosys script is written to DIR/mk_cut.ys so it can be re-run by hand):
  read_liberty (no -lib: every Sky130 cell becomes logic / $_DFF_ / $_DLATCH_)  -> read stubs for black boxes -> read netlist
  -> a wrapper `cut_top` ties the scan-mode capture constants (port=value) -> flatten -> opt (constants fold, the scan
  muxes and functional mux legs collapse) -> latches become flops (one structural approximation, counted) ->
  `expose -evert -evert-dff`: flop Q -> pseudo primary input, flop D -> pseudo primary output; black-box output pins ->
  inputs and input pins -> outputs -> abc -g (generic gates, the fault universe of Quaigh) -> write_blif.

Black boxes (CPU macro, SRAM) have no X state in Quaigh: coverage of the logic around them is an UPPER BOUND.
--cellpin (bead j41m.20): the fault universe becomes the Sky130 cell PINS instead of abc's generic gates.  Every Liberty cell model
(dumped once with `write_verilog`) is wrapped so each of its ports passes through a kept `$_BUF_`; abc is not run, the primitive
gates are lowered to `.names` here (lower_gates), and the output net of every surviving pin buffer is listed in DIR/cut_sites.txt.
A Quaigh output stuck-at fault on a pin buffer is the pin fault: on an output pin the stem, on an input pin the branch.
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


# Clock pins are not wrapped: a kept buffer would hide a constant clock (tck_i=0 makes the generic flow fold the 112 no-reset
# TAP flops; behind a buffer they survived, 114 extra flops on the fabric) and clock pins are outside the universe anyway.
CLOCK_PINS = ("CLK", "CLK_N", "GATE", "GATE_N")
PORTLIST_RE = re.compile(r"^module (\S+)\((.*?)\);\n(.*?)^endmodule\n?", re.M | re.S)


def wrap_cellpin(libv: str) -> Tuple[str, int]:
    """Wrap every port-bearing module of a `write_verilog` dump of the Liberty: module X becomes X__core, and a new X routes each
    port through a kept `$_BUF_` named cvtpinbuf_<port>.  Port-less cells (tap, fill) are copied.  Returns (text, wrapped modules)."""
    out, n = [], 0
    for m in PORTLIST_RE.finditer(libv):
        name, plist, body = m.group(1), m.group(2), m.group(3)
        ports = [p.strip() for p in plist.split(",") if p.strip()]
        if not ports:
            out.append(m.group(0))
            continue
        dirs = dict((pn, d) for d, pn in re.findall(r"^\s*(input|output)\s+(\w+);", body, re.M))
        missing = [p for p in ports if p not in dirs]
        if missing:
            raise SystemExit(f"{name}: no direction for ports {missing} (bus port in a Liberty cell?)")
        out.append(f"module {name}__core({plist});\n{body}endmodule\n")
        w = [f"module {name}({plist});"]
        for p in ports:
            if p in CLOCK_PINS:
                w += [f"  {dirs[p]} {p};", f"  wire cvtpin_{p} = {p};"]
                continue
            w += [f"  {dirs[p]} {p};", f"  wire cvtpin_{p};"]
            a, y = (p, f"cvtpin_{p}") if dirs[p] == "input" else (f"cvtpin_{p}", p)
            w.append(f"  (* keep *) \\$_BUF_ cvtpinbuf_{p} (.A({a}), .Y({y}));")
        w.append(f"  {name}__core u_core({', '.join(f'.{p}(cvtpin_{p})' for p in ports)});")
        out.append("\n".join(w) + "\nendmodule\n")
        n += 1
    return "\n".join(out), n


CTS_HEADER_RE = re.compile(r"^(\s+)(\w+)(\s+)(\\\S+ |\w+)(\s*\()(.*)$")


def unwrap_cts_cells(text: str) -> Tuple[str, int]:
    """Point every instance whose output pin (X/Y) drives a CTS clock net (`clknet_*`) at the unwrapped `<type>__core` model.
    The clock tree is clock-only logic (outside the universe), and a kept pin buffer on it would stop a constant clock from
    folding: with tck_i=0 the generic flow folds two transparent `dlxtn` latches of the DFT clock switch whose enable comes
    through the tck_i clock tree; behind buffered clkbuf cells they survived as free pseudo-inputs (fabric, j41m.20)."""
    lines = text.split("\n")
    out, n, i = [], 0, 0
    while i < len(lines):
        m = CTS_HEADER_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and ");" not in lines[j]:
            j += 1
        block = "\n".join(lines[i:j + 1])
        if re.search(r"\.(X|Y)\(\s*clknet_\S*\s*\)", block):
            lines[i] = m.group(1) + m.group(2) + "__core" + m.group(3) + m.group(4) + m.group(5) + m.group(6)
            n += 1
        out.extend(lines[i:j + 1])
        i = j + 1
    return "\n".join(out), n


# Yosys internal gate -> (input pins in order, single-output cover rows).  $_MUX_: Y = S ? B : A.
GATE_COVERS = {
    "$_BUF_": (["A"], ["1 1"]), "$_NOT_": (["A"], ["0 1"]),
    "$_AND_": (["A", "B"], ["11 1"]), "$_OR_": (["A", "B"], ["1- 1", "-1 1"]),
    "$_NAND_": (["A", "B"], ["0- 1", "-0 1"]), "$_NOR_": (["A", "B"], ["00 1"]),
    "$_XOR_": (["A", "B"], ["10 1", "01 1"]), "$_XNOR_": (["A", "B"], ["00 1", "11 1"]),
    "$_ANDNOT_": (["A", "B"], ["10 1"]), "$_ORNOT_": (["A", "B"], ["1- 1", "-0 1"]),
    "$_MUX_": (["A", "B", "S"], ["1-0 1", "-11 1"]),
}


def lower_gates(text: str) -> Tuple[str, List[str], Dict[str, int]]:
    """Replace every `.gate <yosys primitive> A=.. Y=..` line (and `$_DFF_P_`/`$_DFF_N_` by `.latch D Q re|fe C 2`, as write_blif does) of a `write_blif -gates` file by an equivalent `.names` block.
    Returns (text, output nets of the $_BUF_ pin buffers, census per gate type).  An unknown `$` gate is an error."""
    text = text.replace("\\\n", " ")
    lines, sites, census = [], [], {}
    for ln in text.split("\n"):
        if not ln.startswith(".gate "):
            lines.append(ln)
            continue
        f = ln.split()
        typ = f[1].lstrip("\\")
        if typ in ("$_DFF_P_", "$_DFF_N_"):
            conn = dict(x.split("=", 1) for x in f[2:])
            lines.append(f".latch {conn['D']} {conn['Q']} {'re' if typ == '$_DFF_P_' else 'fe'} {conn['C']} 2")
            census[typ] = census.get(typ, 0) + 1
            continue
        if typ == "$_FF_":  # global-clock flop (async2sync); write_blif writes it as a clockless `.latch D Q 2`
            conn = dict(x.split("=", 1) for x in f[2:])
            lines.append(f".latch {conn['D']} {conn['Q']} 2")
            census[typ] = census.get(typ, 0) + 1
            continue
        if typ not in GATE_COVERS:
            if typ.startswith("$"):
                raise SystemExit(f"lower_gates: no cover for {typ}: {ln[:120]}")
            lines.append(ln)  # a Liberty cell without a function (clock gate): dce_blif counts it as unmodelled
            continue
        conn = dict(x.split("=", 1) for x in f[2:])
        ins, rows = GATE_COVERS[typ]
        lines.append(".names " + " ".join(conn[i] for i in ins) + " " + conn["Y"])
        lines += rows
        census[typ] = census.get(typ, 0) + 1
        if typ == "$_BUF_":
            sites.append(conn["Y"])
    return "\n".join(lines), sites, census


def script(netlist: Path, out: Path, lib: str, stubs: List[Path], consts: Dict[str, int], top: str,
           bbox_mods: List[str], cellpin: bool = False) -> str:
    s = [
        f"read_verilog -sv -icells {out}/libcells_pin.v" if cellpin else
        f"read_liberty -ignore_miss_func -ignore_miss_dir -ignore_miss_data_latch {lib}",
    ]
    s += [f"read_verilog -sv -lib {p}" for p in stubs]
    s += [
        f"read_verilog -sv {netlist}",
        f"read_verilog -sv {out}/cut_top.v",
        "hierarchy -top cut_top",
    ] + ([
        # memory (fabric, j41m.20): the pin wrappers double the hierarchy, and flatten's per-instance $scopeinfo cells and the
        # src attributes on ~2.5 M objects pushed Yosys to the 12 GiB cap (OOM in flatten); neither is used by the cut
        "setattr -unset src",
        "flatten -noscopeinfo",
    ] if cellpin else ["flatten"]) + [
        # lowers word-level cells (none in a Liberty-only netlist, where this is a no-op; pin_inject.py adds `assign` muxes)
        "simplemap",
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
    ] + ([] if cellpin else [f"abc -g {GATES}"]) + [
        "opt_clean -purge",
        f"tee -o {out}/cut_stat.rpt stat",
        f"write_blif -icells -gates {out}/cut.blif" if cellpin else f"write_blif -gates {out}/cut.blif",
    ]
    return "\n".join(s) + "\n"


def dce_blif(text: str) -> Tuple[str, int, int, List[str], List[str]]:
    """Drop `.names` blocks that reach no output and no flop D input (clock-network logic ends at `.latch` clocks, which
    Quaigh ignores: left in, its faults would be counted as 'proven untestable').  Outputs with no driver (a black-box CLOCK pin whose net
    is a clock tree) are removed from .outputs and reported.  Returns (text, kept, dropped, unmodelled cells, undriven outputs)."""
    text = text.replace("\\\n", " ")
    lines = text.split("\n")
    blocks, header, latches, outputs, unmodelled, inputs = {}, [], [], [], [], set()
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
        elif ln.startswith(".inputs"):
            inputs.update(ln.split()[1:])
            header.append(ln)
        elif ln.strip() and not ln.startswith("#"):
            header.append(ln)
        i += 1
    driven = inputs | set(blocks) | {ln.split()[2] for ln in latches}
    undriven = [o for o in outputs if o not in driven]
    if undriven:
        gone = set(undriven)
        header = [(".outputs " + " ".join(o for o in h.split()[1:] if o not in gone)) if h.startswith(".outputs") else h
                  for h in header]
        outputs = [o for o in outputs if o not in gone]
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
    return "\n".join(head + latches + body + end) + "\n", len(live), len(blocks) - len(live), unmodelled, undriven


def undefined_cone_outputs(text: str) -> List[str]:
    """Outputs whose fan-in cone reads a net nothing defines (a clock tree rooted at a function-less clock gate: in the
    cell-pin cut its clock buffers keep a black-box clock pin alive that abc folds away in the generic cut)."""
    t = text.replace("\\\n", " ")
    blocks = {}
    for m in re.finditer(r"^\.names (.*)$", t, re.M):
        nets = m.group(1).split()
        blocks[nets[-1]] = nets[:-1]
    ins = set(re.search(r"^\.inputs(.*)$", t, re.M).group(1).split())
    latq = {ln.split()[2] for ln in re.findall(r"^\.latch .*$", t, re.M)}
    outs = re.search(r"^\.outputs(.*)$", t, re.M).group(1).split()
    fanout: Dict[str, List[str]] = {}
    for y, deps in blocks.items():
        for d in deps:
            fanout.setdefault(d, []).append(y)
    defined = ins | latq | set(blocks)
    tainted = set()
    stack = [y for y, deps in blocks.items() if any(d not in defined for d in deps)]
    while stack:
        y = stack.pop()
        if y in tainted:
            continue
        tainted.add(y)
        stack.extend(fanout.get(y, []))
    return [o for o in outs if o in tainted or o not in defined]


def drop_unobservable_latches(text: str) -> Tuple[str, int]:
    """Remove latches whose Q never reaches an output, following latch D -> Q edges backwards (sequential liveness, as the
    generic flow's first `opt_clean` does before `keep` is set).  In the cell-pin cut the kept pin buffers otherwise anchor them:
    the 112 no-reset TAP flops whose D is their own Q and two `$_FF_` survived there (fabric, j41m.20).  Returns (text, removed)."""
    t = text.replace("\\\n", " ")
    blocks = {}
    for m in re.finditer(r"^\.names (.*)$", t, re.M):
        nets = m.group(1).split()
        blocks[nets[-1]] = nets[:-1]
    lat = {}
    for ln in re.findall(r"^\.latch .*$", t, re.M):
        f = ln.split()
        lat[f[2]] = f[1]  # Q -> D
    outs = re.search(r"^\.outputs(.*)$", t, re.M).group(1).split()
    live, stack = set(), list(outs)
    while stack:
        n = stack.pop()
        if n in live:
            continue
        live.add(n)
        if n in blocks:
            stack.extend(blocks[n])
        elif n in lat:
            stack.append(lat[n])
    dead = {q for q in lat if q not in live}
    if not dead:
        return t, 0
    keep = [ln for ln in t.split("\n") if not (ln.startswith(".latch") and ln.split()[2] in dead)]
    return "\n".join(keep), len(dead)


def match_port_order(text: str, ref: str) -> str:
    """Rewrite `.inputs` / `.outputs` of `text` in the order of the reference cut `ref` (same name sets required).  Yosys'
    `expose -evert` orders the black-box pins differently in the cell-pin cut, and Quaigh patterns are positional (inputs,
    then flops in .latch order); the .latch order is checked by simulating the same patterns on both cuts."""
    t = text.replace("\\\n", " ")
    r = ref.replace("\\\n", " ")
    for kw in (".inputs", ".outputs"):
        m = re.search(rf"^\{kw}(.*)$", t, re.M)
        want = re.search(rf"^\{kw}(.*)$", r, re.M).group(1).split()
        have = m.group(1).split()
        if sorted(have) != sorted(want):
            raise SystemExit(f"--ref-cut: {kw} differ: {len(set(have) ^ set(want))} names, e.g. {sorted(set(have) ^ set(want))[:4]}")
        t = t[:m.start()] + kw + " " + " ".join(want) + t[m.end():]
    return t


def drop_outputs(text: str, gone: List[str]) -> str:
    g = set(gone)
    t = text.replace("\\\n", " ")
    return re.sub(r"^(\.outputs)(.*)$", lambda m: m.group(1) + "".join(" " + o for o in m.group(2).split() if o not in g),
                  t, count=1, flags=re.M)


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
    ap.add_argument("--cellpin", action="store_true", help="fault universe = Sky130 cell pins (bead j41m.20)")
    ap.add_argument("--ref-cut", help="reorder .inputs/.outputs to this generic cut DIR's cut.blif (positional patterns)")
    ap.add_argument("--skip-yosys", action="store_true",
                    help="reuse DIR/cut.blif and DIR/cut_stat.rpt of a previous run whose post-processing failed (the fabric Yosys step peaks at ~12 GB)")
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
    if a.cellpin:
        dump = out / "libcells.v"
        r = subprocess.run([a.yosys, "-q", "-p", f"read_liberty -ignore_miss_func -ignore_miss_dir -ignore_miss_data_latch {a.lib}; "
                            f"write_verilog -noattr -noexpr {dump}"], capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-2000:])
            return r.returncode
        wrapped, n_wrapped = wrap_cellpin(dump.read_text())
        (out / "libcells_pin.v").write_text(wrapped)
        nl_text, n_cts = unwrap_cts_cells(Path(a.netlist).read_text(errors="replace"))
        a.netlist = str(out / "netlist_cellpin.v")
        Path(a.netlist).write_text(nl_text)
    ys.write_text(script(Path(a.netlist), out, a.lib, stubs, consts, a.top, [b.split('=')[0] for b in a.bbox], a.cellpin))
    if a.skip_yosys:
        if not (out / "cut_raw.blif").exists():
            raise SystemExit("--skip-yosys: no DIR/cut_raw.blif from a previous run")
        (out / "cut.blif").write_text((out / "cut_raw.blif").read_text())
        r = subprocess.CompletedProcess([], 0, "", "")
    else:
        r = subprocess.run([a.yosys, "-q", "-l", str(out / "yosys.log"), str(ys)], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        return r.returncode
    stat = (out / "cut_stat.rpt").read_text()
    cells = int(re.search(r"Number of cells:\s+(\d+)", stat).group(1))
    raw = (out / "cut.blif").read_text()
    (out / "cut_raw.blif").write_text(raw)  # Yosys' own output, before any post-processing (--skip-yosys restarts from it)
    sites, census = [], {}
    if a.cellpin:
        raw, sites, census = lower_gates(raw)
    blif, kept, dropped, unmodelled, undriven = dce_blif(raw)
    dead_latches = 0
    if a.cellpin:
        blif, dead_latches = drop_unobservable_latches(blif)
        if dead_latches:  # a dead latch's Q is now undefined: its private D cone and Q-pin buffers go with dce
            blif, kept, dropped2, _, _ = dce_blif(blif)
            dropped += dropped2
        undef = undefined_cone_outputs(blif)
        if undef:
            blif, kept, dropped2, _, _ = dce_blif(drop_outputs(blif, undef))
            dropped += dropped2
            undriven = undriven + undef
    if a.ref_cut:
        blif = match_port_order(blif, (Path(a.ref_cut) / "cut.blif").read_text())
    odd = [o for o in undriven if not re.search(r"\.(clk_i|clk0|clk1|clk)$", o)]
    if odd:
        print(f"ERROR: undriven outputs that are not clock pins: {odd[:5]}")
        return 2
    bad = sorted({t for t in unmodelled if t.startswith("$")})
    if bad:  # a Yosys internal cell type in the BLIF is a flop or gate we failed to lower: never drop it silently
        print(f"ERROR: unlowered internal cells in the cut: {bad}")
        return 2
    (out / "cut.blif").write_text(blif)
    n_in = len(re.search(r"^\.inputs (.*?)(?<!\\)$", blif, re.M | re.S).group(1).replace("\\\n", " ").split())
    n_out = len(re.search(r"^\.outputs (.*?)(?<!\\)$", blif, re.M | re.S).group(1).replace("\\\n", " ").split())
    info = {"top": a.top, "constants": consts, "blackboxes": [b.split("=")[0] for b in a.bbox],
            "cut_cells_yosys": cells, "gates_kept": kept, "gates_dead_dropped": dropped,
            "undriven_clock_outputs_dropped": undriven,
            "unmodelled_cells_dropped": {t: unmodelled.count(t) for t in sorted(set(unmodelled))},
            "flops": len(re.findall(r"^\.latch", blif, re.M)), "cut_cells": cells, "cut_inputs": n_in, "cut_outputs": n_out}
    if a.cellpin:
        driven = set(re.findall(r"^\.names .* (\S+)$", blif, re.M))
        live = [x for x in sites if x in driven]
        n_buf = int(re.search(r"\\?\$_BUF_\s+(\d+)", stat).group(1))
        if n_buf != len(sites) or len(set(live)) != len(live):
            print(f"ERROR: pin-buffer census mismatch: yosys {n_buf}, lowered {len(sites)}, unique live {len(set(live))}/{len(live)}")
            return 2
        (out / "cut_sites.txt").write_text("\n".join(live) + "\n")
        info.update({"cellpin": True, "cts_cells_unwrapped": n_cts, "unobservable_latches_dropped": dead_latches, "lib_modules_wrapped": n_wrapped, "gate_census": census, "pin_buffers": len(sites),
                     "pin_buffers_dead_dropped": len(sites) - len(live), "fault_sites": len(live), "pin_faults": 2 * len(live)})
    (out / "cut_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
