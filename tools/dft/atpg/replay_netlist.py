#!/usr/bin/env python3
"""Build the simulation netlist for the scan replay (bead j41m.19): black boxes become tb-driven vectors, faults get runtime selects.

usage: replay_netlist.py SIM.v --map map.json --bbox-dir CUT_DIR --out-dir DIR [--top soc_top] [--faults faults.json --cellpin-cut CUT5]

The ATPG cut (mk_cut.py) exposes the three black boxes of the fabric (CPU macro, two SRAM macros) as free pseudo-inputs (their
outputs) and observed outputs (their inputs), and ties the exclusions.  The replay has to give the real gate netlist exactly those
degrees of freedom, so this script rewrites the post-fill netlist:

  * every black-box instance is deleted; the net on each of its output bits is driven from `rp_fv[i]`, and each input bit is
    copied to `rp_ov[j]`.  The bit order is the order of the cut's `.inputs` (outputs) list, so the tb applies a pattern's
    black-box PI bits with no further table;
  * every unscanned latch/flop that the cut treats as a free pseudo-input (map.json kind `free`: no scan load can set it) is
    deleted and its Q net is driven from `rp_fv` as well (counted: these bits are NOT reachable by scan on silicon);
  * `--faults`: single stuck-at faults are injected at instance pins (pin_inject.inject: select input `fsel_k` per fault), so
    one Verilator build serves every fault;
  * a wrapper `replay_top` flattens the pins to `pi_vec` (cut `.inputs` order, then the free-latch bits) and `po_vec` (cut
    `.outputs` order) and exposes the control pins (scan_clk_i, scan_en_i, scan_mode_i, scan_rst_ni, trst_ni, tck_i, clk_i,
    cpu_clk_i, tms_i, tdi_i, scan_in_i, scan_out_o) directly.

Nothing of the tool's own is a model of the design: the logic under test is the unmodified netlist text.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist_lib import CELL_RE, PIN_RE, norm  # noqa: E402

DECL_RE = re.compile(r"^\s*(input|output)\s+(?:\[(\d+):(\d+)\]\s*)?([^;]+);", re.M)
DIRECT = ("scan_clk_i", "scan_en_i", "scan_mode_i", "scan_rst_ni", "trst_ni", "tck_i", "clk_i", "cpu_clk_i", "tms_i", "tdi_i")


def read_bbox_ports(path: Path) -> Dict[str, Tuple[str, int]]:
    """port -> (direction, width) from a bbox_*.v header (mk_cut.py writes them)."""
    ports: Dict[str, Tuple[str, int]] = {}
    for m in DECL_RE.finditer(path.read_text()):
        w = int(m.group(2)) - int(m.group(3)) + 1 if m.group(2) else 1
        for n in m.group(4).split(","):
            ports[n.strip()] = (m.group(1), w)
    return ports


def conn_bits(expr: str, width: int) -> List[Optional[str]]:
    """Net of each bit of a port connection, LSB first.  None = unconnected.  Accepts `net`, `net[3]`, `{a, b}`, `1'b0`."""
    e = expr.strip()
    if not e:
        return [None] * width
    if e.startswith("{"):
        parts = [p.strip() for p in e.strip("{}").split(",")]
        if len(parts) != width:
            raise SystemExit(f"concatenation of {len(parts)} nets on a {width}-bit port: {e[:80]}")
        return [raw(p) if p else None for p in reversed(parts)]
    if width == 1:
        return [raw(e)]
    return [f"{raw(e)}[{b}]" for b in range(width)]


def raw(tok: str) -> str:
    """A net token as the netlist wrote it: an escaped identifier keeps its backslash and gets the terminating space."""
    t = tok.strip()
    return t + " " if t.startswith("\\") else t


def esc(net: str) -> str:
    return net


def top_decls(text: str, top: str) -> Dict[str, Tuple[str, int]]:
    m = re.search(rf"^module {re.escape(top)}\s*\(", text, re.M)
    end = text.index("endmodule", m.end())
    out: Dict[str, Tuple[str, int]] = {}
    for d in DECL_RE.finditer(text[m.end():end]):
        w = int(d.group(2)) - int(d.group(3)) + 1 if d.group(2) else 1
        for n in d.group(4).split(","):
            out[n.strip().replace("\\", "").strip()] = (d.group(1), w)
    return out


def inject_pins(text: str, top: str, faults: List[Tuple[str, str, str, int]]) -> str:
    """Single stuck-at fault per entry (instance, pin, 'in'|'out', value), runtime-selected by top input fsel_k.

    input pin  .A(net) -> .A(cvtf_k)  with  assign cvtf_k = fsel_k ? V : net   (branch fault: only this instance sees it)
    output pin .Y(net) -> .Y(cvtf_k)  with  assign net = fsel_k ? V : cvtf_k   (stem fault: every load sees it)
    Same semantics as pin_inject.inject, but it finds instances with the CELL_RE of the OpenROAD netlists (pins on the instance line).
    """
    spans = {norm(m.group(2)): m for m in CELL_RE.finditer(text)}
    edits: Dict[str, List[Tuple[int, str, str, str, int]]] = {}
    seen = set()
    for k, (inst, pin, d, v) in enumerate(faults):
        if (inst, pin) in seen:
            raise SystemExit(f"pin {inst}.{pin} sampled twice")
        seen.add((inst, pin))
        if inst not in spans:
            raise SystemExit(f"instance {inst} not found in the netlist")
        edits.setdefault(inst, []).append((k, pin, d, v, 0))
    decls, assigns = [], []
    repl: List[Tuple[int, int, str]] = []
    for inst, lst in edits.items():
        m = spans[inst]
        body = m.group(3)
        for k, pin, d, v, _ in lst:
            pm = re.search(rf"\.{re.escape(pin)}\(([^()]*)\)", body)
            if not pm or not pm.group(1).strip():
                raise SystemExit(f"pin {inst}.{pin}: no connection in the netlist")
            net = raw(pm.group(1))
            body = body[:pm.start()] + f".{pin}(cvtf_{k})" + body[pm.end():]
            decls += [f"  wire cvtf_{k};"]
            assigns.append(f" assign cvtf_{k} = fsel_{k} ? 1'b{v} : {net};" if d == "in" else f" assign {net} = fsel_{k} ? 1'b{v} : cvtf_{k};")
        repl.append((m.start(3), m.end(3), body))
    for a, b, new in sorted(repl, reverse=True):
        text = text[:a] + new + text[b:]
    mh = re.search(rf"^module {re.escape(top)}\s*\(", text, re.M)
    head_end = text.index(");", mh.end())
    header = "".join(f", fsel_{k}" for k in range(len(faults)))
    ins = "".join(f"\n  input fsel_{k};" for k in range(len(faults)))
    end = text.rindex("endmodule")
    return text[:head_end] + header + text[head_end:head_end + 2] + ins + "\n" + "\n".join(decls) + text[head_end + 2:end] + "\n".join(assigns) + "\n" + text[end:]


def rewrite(text: str, plan: dict, bbox_ports: Dict[str, Dict[str, Tuple[str, int]]], top: str) -> Tuple[str, dict]:
    """Delete black boxes and free cells; return the new text and the vector sizes."""
    # vector indices: PI order of the cut for black-box outputs, then the free latch bits
    fv_idx: Dict[Tuple[str, str, Optional[int]], int] = {}
    n_in = len(plan["inputs"])
    for i, x in enumerate(plan["inputs"]):
        if x["kind"] == "bb":
            fv_idx[(x["inst"], x["port"], x["bit"])] = i
    free = [x for x in plan["latches"] if x["kind"] == "free"]
    free_idx = {x["inst"]: n_in + k for k, x in enumerate(free)}
    ov_idx: Dict[Tuple[str, str, Optional[int]], int] = {}
    for j, x in enumerate(plan["outputs"]):
        if x["kind"] == "bb":
            ov_idx[(x["inst"], x["port"], x["bit"])] = j
    assigns: List[str] = []
    pieces, last, deleted = [], 0, []
    used_fv, used_ov = set(), set()
    for m in CELL_RE.finditer(text):
        typ, inst, body = m.group(1), norm(m.group(2)), m.group(3)
        if typ in plan["blackboxes"].values() and inst in plan["blackboxes"]:
            ports = bbox_ports[typ]
            pins = {p: n for p, n in PIN_RE.findall(body)}
            for p, (d, w) in ports.items():
                bits = conn_bits(pins.get(p, ""), w)
                for b, net in enumerate(bits):
                    key = (inst, p, b if w > 1 else None)
                    if net is None:
                        continue
                    if d == "output":
                        if key in fv_idx:
                            assigns.append(f" assign {esc(net)} = rp_fv[{fv_idx[key]}];")
                            used_fv.add(fv_idx[key])
                        else:
                            assigns.append(f" assign {esc(net)} = 1'b0;  // output bit not in the cut")
                    elif key in ov_idx:
                        assigns.append(f" assign rp_ov[{ov_idx[key]}] = {net};")
                        used_ov.add(ov_idx[key])
            pieces.append(text[last:m.start()])
            last = m.end()
            deleted.append(inst)
        elif inst in free_idx:
            q = {p: n for p, n in PIN_RE.findall(body)}["Q"]
            assigns.append(f" assign {raw(q)} = rp_fv[{free_idx[inst]}];")
            used_fv.add(free_idx[inst])
            pieces.append(text[last:m.start()])
            last = m.end()
            deleted.append(inst)
    pieces.append(text[last:])
    new = "".join(pieces)
    miss_fv = [i for i, x in enumerate(plan["inputs"]) if x["kind"] == "bb" and i not in used_fv]
    miss_ov = [j for j, x in enumerate(plan["outputs"]) if x["kind"] == "bb" and j not in used_ov]
    n_fv = n_in + len(free)
    n_ov = len(plan["outputs"])
    m = re.search(rf"^module {re.escape(top)}\s*\(", new, re.M)
    head_end = new.index(");", m.end())
    new = (new[:m.end()] + "rp_fv, rp_ov, " + new[m.end():head_end + 2]
           + f"\n  input [{n_fv - 1}:0] rp_fv;\n  output [{n_ov - 1}:0] rp_ov;\n" + new[head_end + 2:])
    i = new.rindex("endmodule")
    new = new[:i] + "\n".join(assigns) + "\n" + new[i:]
    return new, {"n_fv": n_fv, "n_ov": n_ov, "deleted": deleted, "free_bits": len(free),
                 "fv_unused_bb_bits": miss_fv, "ov_unused_bb_bits": miss_ov}


def wrapper(text: str, plan: dict, top: str, n_fault: int, n_fv: int, n_ov: int) -> str:
    decls = top_decls(text, top)
    n_pi = n_fv - 0  # pi_vec carries the cut inputs and then the free-latch bits: same layout as rp_fv
    pi_bits: Dict[str, Dict[int, int]] = {}
    for i, x in enumerate(plan["inputs"]):
        if x["kind"] == "pin" and x["port"] not in DIRECT:
            pi_bits.setdefault(x["port"], {})[x["bit"] or 0] = i
    po_bits: Dict[str, Dict[int, int]] = {}
    for j, x in enumerate(plan["outputs"]):
        if x["kind"] == "pin":
            po_bits.setdefault(x["port"], {})[x["bit"] or 0] = j
    lines = ["`timescale 1ns/1ps", "module replay_top(",
             f"  input [{n_pi - 1}:0] pi_vec, output [{n_ov - 1}:0] po_vec,",
             "  input scan_clk_i, scan_en_i, scan_mode_i, scan_rst_ni, trst_ni, tck_i, clk_i, cpu_clk_i, tms_i, tdi_i,",
             "  input [255:0] fsel, input [7:0] scan_in_i, output [7:0] scan_out_o, output tdo_o, output [7:0] dbg_o, output [23:0] dbg2_o);"]
    if n_fault > 256:
        raise SystemExit("at most 256 faults per build (fsel is 256 bits wide)")
    conns = []
    for name, (d, w) in decls.items():
        if name in ("rp_fv", "rp_ov") or name.startswith("fsel_"):
            continue
        rng = f"[{w - 1}:0] " if w > 1 else ""
        if name in ("scan_in_i", "scan_out_o", "tdo_o") or name in DIRECT:
            conns.append(f".{name}({name})")
            continue
        lines.append(f"  wire {rng}w_{name};")
        conns.append(f".{name}(w_{name})")
        if d == "input":
            for b in range(w):
                src = pi_bits.get(name, {}).get(b)
                lines.append(f"  assign w_{name}{f'[{b}]' if w > 1 else ''} = {f'pi_vec[{src}]' if src is not None else chr(49) + chr(39) + 'b0'};")
        else:
            for b in range(w):
                dst = po_bits.get(name, {}).get(b)
                if dst is not None:
                    lines.append(f"  assign po_vec[{dst}] = w_{name}{f'[{b}]' if w > 1 else ''};")
    for k in range(n_fault):
        conns.append(f".fsel_{k}(fsel[{k}])")
    conns.append(".rp_fv(pi_vec)")
    conns.append(".rp_ov(rp_ov_w)")
    lines.append(f"  wire [{n_ov - 1}:0] rp_ov_w;")
    for j, x in enumerate(plan["outputs"]):
        if x["kind"] == "bb":
            lines.append(f"  assign po_vec[{j}] = rp_ov_w[{j}];")
    # scan_out_o pins are cut outputs too
    for j, x in enumerate(plan["outputs"]):
        if x["kind"] == "pin" and x["port"] == "scan_out_o":
            lines.append(f"  assign po_vec[{j}] = scan_out_o[{x['bit']}];")
    lines.append(f"  {top} u_dut({', '.join(conns)});")
    lines.append("  // debug taps (not part of the netlist): scan_mode, scan_en, wipe_done, test_clk, core_clk, cpu_core_clk")
    lines.append("  assign dbg_o = {2'b0, u_dut.cpu_core_clk, u_dut.core_clk, u_dut.dft_test_clk, u_dut.crypto_wipe_done, u_dut.dft_scan_en, u_dut.dft_scan_mode};")
    taps = []
    cellmap = {norm(m.group(2)): {p_: raw(n_) for p_, n_ in PIN_RE.findall(m.group(3))} for m in CELL_RE.finditer(text)}
    for k, pos in ((0, 0), (0, 1), (5, 0), (5, 1)):
        inst = plan["chains"][k][pos]
        pins = cellmap[inst]
        taps += [f"u_dut.{pins[x]}" for x in ("CLK", "SCE", "Q")]
    lines.append("  // debug taps of the first two flops of chains 0 and 5: CLK, SCE, Q each")
    lines.append("  assign dbg2_o = {" + ", ".join(taps) + "};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--map", required=True)
    ap.add_argument("--bbox-dir", required=True, help="directory with the bbox_<module>.v files of mk_cut.py")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--faults", help="JSON list of {net, value}: sites of the cell-pin cut to inject (select fsel_k each)")
    ap.add_argument("--cellpin-cut", help="cut5 directory (cut.blif) that names the fault sites")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(a.map).read_text())
    text = Path(a.netlist).read_text(errors="replace")
    n_fault = 0
    if a.faults:
        import pin_inject
        faults = json.loads(Path(a.faults).read_text())
        need = [f["net"] for f in faults if "inst" not in f]
        pins = pin_inject.site_pins((Path(a.cellpin_cut) / "cut.blif").read_text(), need) if need else {}
        # an entry with explicit inst/pin/dir is injected as given (shift-phase conditioning, below); the others are cell-pin sites
        fl = [((f["inst"], f["pin"], f["dir"]) if "inst" in f else pins[f["net"]]) + (int(f["value"]),) for f in faults]
        text = inject_pins(text, a.top, fl)
        n_fault = len(fl)
        (out / "fault_pins.json").write_text(json.dumps([{"k": k, "site": f.get("net", ""), "inst": i, "pin": p, "dir": d, "value": v}
                                                         for k, (f, (i, p, d, v)) in enumerate(zip(faults, fl))], indent=1))
    bbox_ports = {}
    for typ in set(plan["blackboxes"].values()):
        bbox_ports[typ] = read_bbox_ports(Path(a.bbox_dir) / f"bbox_{typ}.v")
    new, info = rewrite(text, plan, bbox_ports, a.top)
    (out / "soc_replay.v").write_text(new)
    (out / "replay_top.v").write_text(wrapper(new, plan, a.top, n_fault, info["n_fv"], info["n_ov"]))
    info["n_fault"] = n_fault
    info["n_pi"] = len(plan["inputs"])
    (out / "replay_info.json").write_text(json.dumps(info))
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in info.items()}))
    return 1 if info["fv_unused_bb_bits"] or info["ov_unused_bb_bits"] else 0


if __name__ == "__main__":
    sys.exit(main())
