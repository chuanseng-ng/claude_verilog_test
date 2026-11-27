#!/usr/bin/env python3
"""Map the bits of a Quaigh pattern onto the scan chains and pins of the gate-level scan netlist (bead j41m.19).

usage: pattern_map.py CUT.blif NETLIST.v --out map.json [--cut-info cut_info.json] [--hold-mask] [--clock-pis a,b,c]
                      [--const name=V ...] [--in-fmt 'scan_in_i[%d]'] [--out-fmt 'scan_out_o[%d]'] [--chains 8]

A Quaigh pattern line is `N: <bits>`; the bit order is the BLIF `.inputs` order, then the `.latch` Q order (the pseudo-primary
inputs).  The expected response (`quaigh simulate --expose-ff`) is the `.outputs` order, then the `.latch` D order.  This tool
turns the two lists into a plan that a tester can apply:

  pseudo-PI (latch)   -> (scan chain, position from scan-in) by walking the chains of NETLIST (SCD traced back through the
                         hold/repair buffers, as tools/dft/check_scan_chains.py does);
  PI                  -> a primary pin (scan_in_i[k] is the chain data, ignored in capture), a black-box output (CPU macro,
                         SRAM macros: free pseudo-inputs of the cut), a clock (value ignored, only if no gate reads it), or a
                         fixed value (the cut's constants: scan_mode, test-mode ties);
  latch D             -> the same chain position, unless the flop is hold-masked (its D is not observed: not compared);
  PO                  -> a primary pin or a black-box input (observed outputs of the cut).

Nothing is guessed.  A bit that cannot be mapped is listed in `unmapped` and the tool exits 1 (`--allow-free` accepts only the
documented class of unscanned flops with free power-up state, which no scan load can set).  The cell-pin cut (mk_cut.py --cellpin)
names a flop Q `u_dut.<inst>.cvtpin_Q`; an async-reset flop shows as `$auto$async2sync...` and is recovered from the gate
`.names $false <raw> <inst>.cvtpin_RESET_B <inst>.cvtpin_Q` that restores the reset.  A generic cut does not carry instance names
(abc renames the nets) and is refused.

Shift convention (positive-edge scan flops, SCD of position p driven by Q of p-1, position 0 fed by scan_in): after L shift edges
the bit sent first sits at position L-1.  `chain_load_stream` / `chain_unload_stream` below give the per-edge values.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist_lib import BUF_RE, FLOP_TYPE_RE, SCAN_FLOP_RE, Cell, iter_cells  # noqa: E402

DUT = "u_dut."
OUT_PINS = ("X", "Y", "Q", "Q_N", "HI", "LO")
CLOCK_SINK_RE = re.compile(r"\.(clk\d?|clk_i)$")
LATCH_TYPE_RE = re.compile(r"sky130_fd_sc_hd__dlx\w*")
Q_RE = re.compile(r"^u_dut\.(?P<inst>.+)\.cvtpin_Q$")
BIT_RE = re.compile(r"^(?P<base>.+)\[(?P<bit>\d+)\]$")
DEFAULT_CLOCKS = ("clk_i", "cpu_clk_i", "scan_clk_i")
DEFAULT_CONSTS = {"scan_mode_i": 1, "scan_en_i": 0, "trst_ni": 0, "tck_i": 0, "scan_rst_ni": 1}


class Blif:
    """Only what the mapper needs from a BLIF: the port lists, the latches, the signals a gate reads, the reset-restore gates."""

    def __init__(self):
        self.inputs: List[str] = []
        self.outputs: List[str] = []
        self.latches: List[Tuple[str, str]] = []  # (D, Q)
        self.qgates: Dict[str, str] = {}  # raw Q net -> flop instance (async-reset flops)
        self.read: set = set()  # every signal that is an input of some .names gate
        self.fanout: Dict[str, List[str]] = {}  # signal -> outputs of the gates that read it (only when track_edges)


def parse_blif(lines: Iterable[str], track_edges: bool = False) -> Blif:
    b = Blif()
    cont = ""
    for raw in lines:
        raw = raw.rstrip("\n")
        if raw.endswith("\\"):
            cont += raw[:-1] + " "
            continue
        ln = (cont + raw).strip()
        cont = ""
        if not ln or ln[0] != ".":
            continue
        tok = ln.split()
        if tok[0] == ".inputs":
            b.inputs += tok[1:]
        elif tok[0] == ".outputs":
            b.outputs += tok[1:]
        elif tok[0] == ".latch":
            b.latches.append((tok[1], tok[2]))
        elif tok[0] == ".names":
            ins, out = tok[1:-1], tok[-1]
            b.read.update(ins)
            if track_edges:
                for i in ins:
                    b.fanout.setdefault(i, []).append(out)
            m = Q_RE.match(out)
            if m:
                # async-reset flop (RESET_B/SET_B restore) or transparent latch: the raw Q of the cut is an `$auto$async2sync` net
                for i in ins:
                    if i.startswith("$auto$async2sync"):
                        b.qgates[i] = m.group("inst")
    return b


def latch_instance(q: str, qgates: Dict[str, str]) -> Optional[str]:
    """Flop instance behind a latch Q name of the cell-pin cut, or None when the name does not identify one."""
    m = Q_RE.match(q)
    if m:
        return m.group("inst")
    return qgates.get(q)


def trace_back(net: str, driver: Dict[str, Tuple[str, str]], cells: Dict[str, Cell]) -> Tuple[str, str]:
    """Follow `net` back through buffers.  ('flop', inst) | ('port', net) | ('other', inst)."""
    for _ in range(64):
        d = driver.get(net)
        if d is None:
            return ("port", net)
        inst, pin = d
        c = cells[inst]
        if FLOP_TYPE_RE.match(c.typ) and pin == "Q":
            return ("flop", inst)
        if BUF_RE.match(c.typ):
            net = c.pins.get("A", "")
            continue
        return ("other", inst)
    return ("other", "loop")


def build_driver(cells: Dict[str, Cell]) -> Dict[str, Tuple[str, str]]:
    drv: Dict[str, Tuple[str, str]] = {}
    for inst, c in cells.items():
        for pin, net in c.pins.items():
            if pin in OUT_PINS:
                drv[net] = (inst, pin)
    return drv


def walk_chains(cells: Dict[str, Cell], n_ports: int, in_fmt: str = "scan_in_i[%d]") -> Tuple[List[List[str]], List[str]]:
    """Chains as instance lists, position 0 first.  Returns (chains, problems); chain k has an empty list when scan_in k has no load."""
    drv = build_driver(cells)
    nxt: Dict[str, List[str]] = {}
    heads: Dict[str, List[str]] = {}
    problems: List[str] = []
    for inst, c in cells.items():
        if not SCAN_FLOP_RE.match(c.typ):
            continue
        kind, who = trace_back(c.pins.get("SCD", ""), drv, cells)
        if kind == "flop":
            nxt.setdefault(who, []).append(inst)
        elif kind == "port":
            heads.setdefault(who, []).append(inst)
        else:
            problems.append(f"{inst}: SCD driven by non-buffer cell {who}")
    chains: List[List[str]] = []
    seen: set = set()
    for k in range(n_ports):
        hs = heads.get(in_fmt % k, [])
        if len(hs) > 1:
            problems.append(f"scan_in {k}: {len(hs)} flops on one scan-in port")
        chain: List[str] = []
        cur = hs[0] if hs else None
        while cur is not None:
            if cur in seen:
                problems.append(f"loop at {cur}")
                break
            seen.add(cur)
            chain.append(cur)
            succ = nxt.get(cur, [])
            if len(succ) > 1:
                problems.append(f"{cur}: Q feeds {len(succ)} SCD pins")
            cur = succ[0] if succ else None
        chains.append(chain)
    orphans = [i for i, c in cells.items() if SCAN_FLOP_RE.match(c.typ) and i not in seen]
    if orphans:
        problems.append(f"{len(orphans)} scan flops are on no chain (first: {orphans[:3]})")
    return chains, problems


def split_bit(name: str) -> Tuple[str, Optional[int]]:
    m = BIT_RE.match(name)
    return (m.group("base"), int(m.group("bit"))) if m else (name, None)


def cone_endpoints(blif: Blif, start: str, ignore: Iterable[str] = ()) -> List[str]:
    """Observable endpoints (a primary output or a latch D) in the combinational fan-out cone of `start`."""
    targets = set(blif.outputs) | {d for d, _ in blif.latches}
    targets = {t for t in targets if not CLOCK_SINK_RE.search(t)} - set(ignore)  # a clock reaching a black-box clock pin is clock distribution
    seen, stack, hit = {start}, [start], []
    while stack:
        n = stack.pop()
        if n in targets:
            hit.append(n)
        for o in blif.fanout.get(n, ()):
            if o not in seen:
                seen.add(o)
                stack.append(o)
    return hit


def classify_pi(name: str, *, clocks: Iterable[str], consts: Dict[str, int], blackboxes: Dict[str, str],
                top_inputs: set, scan_in_re: "re.Pattern[str]", clock_hits: Dict[str, List[str]]) -> dict:
    """One BLIF input -> {kind, ...}; kind 'unmapped' carries the reason."""
    base, bit = split_bit(name)
    if base in consts:
        return {"kind": "fixed", "name": name, "value": consts[base]}
    m = scan_in_re.match(name)
    if m:
        return {"kind": "scan_in", "name": name, "chain": int(m.group(1))}
    if name in set(clocks):
        if clock_hits.get(name):
            return {"kind": "unmapped", "name": name,
                    "why": f"clock input reaches {len(clock_hits[name])} observable endpoints (e.g. {clock_hits[name][0]}): its value would matter"}
        return {"kind": "clock", "name": name}
    if name.startswith(DUT):
        rest = name[len(DUT):]
        rbase, rbit = split_bit(rest)
        inst, _, port = rbase.rpartition(".")
        if inst in blackboxes:
            return {"kind": "bb", "name": name, "inst": inst, "port": port, "bit": rbit}
        return {"kind": "unmapped", "name": name, "why": "hierarchical name that is not a known black-box port"}
    if base in top_inputs:
        return {"kind": "pin", "name": name, "port": base, "bit": bit}
    return {"kind": "unmapped", "name": name, "why": "not a top-level input of the netlist"}


def classify_po(name: str, *, blackboxes: Dict[str, str], top_outputs: set) -> dict:
    base, bit = split_bit(name)
    if name.startswith(DUT):
        rbase, rbit = split_bit(name[len(DUT):])
        inst, _, port = rbase.rpartition(".")
        if inst in blackboxes:
            return {"kind": "bb", "name": name, "inst": inst, "port": port, "bit": rbit}
        return {"kind": "unmapped", "name": name, "why": "hierarchical name that is not a known black-box port"}
    if base in top_outputs:
        return {"kind": "pin", "name": name, "port": base, "bit": bit}
    return {"kind": "unmapped", "name": name, "why": "not a top-level output of the netlist"}


def top_ports(text: str, top: str) -> Tuple[set, set]:
    """Input and output port base names of module `top` (structural netlist, one declaration per line)."""
    m = re.search(rf"^module {re.escape(top)}\s*\(", text, re.M)
    if not m:
        raise SystemExit(f"module {top} not found")
    end = text.index("endmodule", m.end())
    body = text[m.end():end]
    ins, outs = set(), set()
    for d in re.finditer(r"^\s*(input|output)\s+(?:\[[^\]]*\]\s*)?([^;]+);", body, re.M):
        names = [n.strip().replace("\\", "").strip() for n in d.group(2).split(",")]
        (ins if d.group(1) == "input" else outs).update(n for n in names if n)
    return ins, outs


def latch_class(inst: Optional[str], cells: Dict[str, Cell], pos: Dict[str, Tuple[int, int]],
                masked: set) -> dict:
    if inst is None:
        return {"kind": "unmapped", "why": "latch Q name does not identify a flop instance"}
    c = cells.get(inst)
    if c is None:
        return {"kind": "unmapped", "inst": inst, "why": "flop instance not in the netlist"}
    if not FLOP_TYPE_RE.match(c.typ) and not LATCH_TYPE_RE.match(c.typ):
        return {"kind": "unmapped", "inst": inst, "why": f"{c.typ} is neither a flop nor a latch"}
    if inst in pos:
        k, p = pos[inst]
        return {"kind": "scan", "inst": inst, "chain": k, "pos": p, "masked": inst in masked}
    return {"kind": "free", "inst": inst, "type": c.typ, "why": "unscanned flop or latch: no scan load can set it"}


def chain_load_stream(values: List[int], max_len: int) -> List[int]:
    """Bits to present at scan-in on each of `max_len` shift edges so that position p ends up holding values[p].

    The bit sent first lands in the LAST position; a chain shorter than the longest is padded in front (those bits fall off the end).
    """
    n = len(values)
    return [0] * (max_len - n) + list(reversed(values))


def chain_unload_stream(values: List[int], max_len: int) -> List[int]:
    """Bits seen at scan-out BEFORE each of `max_len` shift edges when the chain holds values (position n-1 first); 0 beyond the end."""
    return list(reversed(values)) + [0] * (max_len - len(values))


def build_map(blif: Blif, cells: Dict[str, Cell], netlist_text: str, *, top: str, consts: Dict[str, int],
              clocks: Iterable[str], n_ports: int, in_fmt: str, out_fmt: str, masked: set) -> dict:
    chains, problems = walk_chains(cells, n_ports, in_fmt)
    pos = {inst: (k, p) for k, ch in enumerate(chains) for p, inst in enumerate(ch)}
    ins, outs = top_ports(netlist_text, top)
    blackboxes = {i: c.typ for i, c in cells.items() if not c.typ.startswith(("sky130_fd_sc_", "sky130_ef_sc_"))}
    scan_in_re = re.compile(re.escape(in_fmt).replace(r"%d", r"(\d+)").replace(r"\[", r"\[").replace(r"\]", r"\]"))
    latches = []
    for d, q in blif.latches:
        lc = latch_class(latch_instance(q, blif.qgates), cells, pos, masked)
        lc["q"] = q
        lc["d"] = d
        latches.append(lc)
    free_d = {x["d"] for x in latches if x["kind"] == "free"}  # an unscanned latch is never compared, so a clock that only reaches its D is harmless
    clock_hits = {c: cone_endpoints(blif, c, free_d) for c in clocks if c in blif.fanout}
    pis = [classify_pi(n, clocks=clocks, consts=consts, blackboxes=blackboxes, top_inputs=ins, scan_in_re=scan_in_re,
                       clock_hits=clock_hits) for n in blif.inputs]
    pos_ = [classify_po(n, blackboxes=blackboxes, top_outputs=outs) for n in blif.outputs]
    unmapped = ([{"list": "inputs", "idx": i, **x} for i, x in enumerate(pis) if x["kind"] == "unmapped"]
                + [{"list": "outputs", "idx": i, **x} for i, x in enumerate(pos_) if x["kind"] == "unmapped"]
                + [{"list": "latches", "idx": i, **x} for i, x in enumerate(latches) if x["kind"] == "unmapped"])
    seen_pos = {(x["chain"], x["pos"]) for x in latches if x["kind"] == "scan"}
    in_cut = len(seen_pos)
    on_chain = sum(len(c) for c in chains)
    count = lambda lst: {k: sum(1 for x in lst if x["kind"] == k) for k in sorted({x["kind"] for x in lst})}  # noqa: E731
    return {
        "top": top,
        "chain_len": [len(c) for c in chains],
        "chains": chains,
        "chain_problems": problems,
        "blackboxes": blackboxes,
        "inputs": pis,
        "outputs": pos_,
        "latches": latches,
        "unmapped": unmapped,
        "summary": {
            "inputs": count(pis), "outputs": count(pos_), "latches": count(latches),
            "scan_flops_on_chains": on_chain, "scan_flops_in_cut": in_cut,
            "scan_flops_on_chains_not_in_cut": on_chain - in_cut,
            "masked_latches": sum(1 for x in latches if x.get("masked")),
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("blif")
    ap.add_argument("netlist")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--cut-info", help="cut_info.json of mk_cut.py: its `constants` are the fixed pins")
    ap.add_argument("--const", action="append", default=[], help="name=V, fixed pin (default: the cut_info constants)")
    ap.add_argument("--clock-pis", default=",".join(DEFAULT_CLOCKS))
    ap.add_argument("--hold-mask", action="store_true", help="do not compare the D of the hold-masked flops (derive_hold_mask.py)")
    ap.add_argument("--in-fmt", default="scan_in_i[%d]")
    ap.add_argument("--out-fmt", default="scan_out_o[%d]")
    ap.add_argument("--chains", type=int, default=8)
    ap.add_argument("--allow-free", action="store_true",
                    help="accept latches of unscanned flops (free power-up state); they are listed, never applied by scan")
    a = ap.parse_args(argv)

    consts = dict(DEFAULT_CONSTS)
    if a.cut_info:
        consts = {k: int(v) for k, v in json.loads(Path(a.cut_info).read_text())["constants"].items()}
    for c in a.const:
        k, v = c.split("=")
        consts[k] = int(v)
    text = Path(a.netlist).read_text(encoding="utf-8", errors="replace")
    cells = {c.inst: c for c in iter_cells(text)}
    # the black-box instances are not sky130 cells: iter_cells already matches rv32i_cpu_top and sky130_sram_*
    masked: set = set()
    if a.hold_mask:
        import derive_hold_mask
        flops = {i: c for i, c in cells.items() if FLOP_TYPE_RE.match(c.typ)}
        masked = {m["inst"] for m in derive_hold_mask.derive(flops)}
    with open(a.blif, encoding="utf-8", errors="replace") as fh:
        blif = parse_blif(fh, track_edges=True)
    plan = build_map(blif, cells, text, top=a.top, consts=consts, clocks=a.clock_pis.split(","), n_ports=a.chains,
                     in_fmt=a.in_fmt, out_fmt=a.out_fmt, masked=masked)
    plan["constants"] = consts
    plan["hold_mask"] = sorted(masked)
    Path(a.out).write_text(json.dumps(plan))
    s = plan["summary"]
    print(json.dumps({"chain_len": plan["chain_len"], **s, "chain_problems": plan["chain_problems"][:5],
                      "unmapped": len(plan["unmapped"])}))
    bad = list(plan["unmapped"])
    if not a.allow_free:
        bad += [x for x in plan["latches"] if x["kind"] == "free"]
    for x in bad[:20]:
        print("UNMAPPED", json.dumps(x), file=sys.stderr)
    if plan["chain_problems"]:
        print("CHAIN PROBLEMS", plan["chain_problems"][:10], file=sys.stderr)
    return 1 if (bad or plan["chain_problems"]) else 0


if __name__ == "__main__":
    sys.exit(main())
