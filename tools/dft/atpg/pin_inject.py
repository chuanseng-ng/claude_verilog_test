#!/usr/bin/env python3
"""Cell-pin fault injection in the gate-level Verilog netlist (bead j41m.20): the re-grade that does NOT go through the cell-pin cut.

usage: pin_inject.py PREP.v --top TOP --cellpin-cut DIR --faults faults.json --patterns P.test --out DIR [--const ...] [--bbox ...]

`mk_cut.py --cellpin` builds the fault universe out of pin buffers it inserts in the Liberty cell models; Quaigh then grades the
buffers.  This script checks that construction from the other side.  Each sampled pin fault (a site net of DIR/cut_sites.txt, as
regrade.py --sites dumps them) is mapped back to (instance, pin) through the pin-buffer cut, then injected into the ORIGINAL netlist
text at that instance pin:
  input pin  `.A(net)`  ->  `.A(cvtf_k)`  with  `assign cvtf_k = fsel_k ? 1'bV : net;`   (the branch: only this instance sees it)
  output pin `.Y(net)`  ->  `.Y(cvtf_k)`  with  `assign net = fsel_k ? 1'bV : cvtf_k;`   (the stem: every load sees it)
with `fsel_k` a new top input.  The faulted netlist goes through the UNCHANGED generic flow (`mk_cut.py` without --cellpin:
read_liberty + abc), and regrade_vl.py's preselected mode simulates the Quaigh patterns in Verilator with each select raised in turn
and proves the undetected faults with Yosys' SAT.  Nothing here uses the pin wrapper, lower_gates or Quaigh's fault engine.
"""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mk_cut  # noqa: E402
import regrade_vl  # noqa: E402

DUT = "u_dut."
INST_RE = re.compile(r"^(\s+)(\S+)\s+(\\\S+ |\S+)\s*\($", re.M)


def site_pins(cut_blif: str, sites: List[str]) -> Dict[str, Tuple[str, str, str]]:
    """site net -> (instance as Yosys names it, pin, 'in'|'out').  An input-pin buffer keeps the internal name
    `u_dut.<inst>.cvtpin_<PIN>` as its output; an output-pin buffer drives the outer net and READS that name."""
    drv = {}
    for m in re.finditer(r"^\.names (\S+) (\S+)\n1 1$", cut_blif.replace("\\\n", " "), re.M):
        drv[m.group(2)] = m.group(1)
    ret = {}
    for s in sites:
        name, d = (s, "in") if ".cvtpin_" in s else (drv.get(s, ""), "out")
        if not name.startswith(DUT) or ".cvtpin_" not in name:
            raise SystemExit(f"site {s}: cannot map to an instance pin (driver {name!r})")
        inst, pin = name[len(DUT):].rsplit(".cvtpin_", 1)
        ret[s] = (inst, pin, d)
    return ret


def inject(text: str, top: str, faults: List[Tuple[str, str, str, int]]) -> str:
    """faults: (instance, pin, 'in'|'out', value) in select order.  Returns the faulted netlist text."""
    m = re.search(rf"^module {re.escape(top)}\s*\(", text, re.M)
    if not m:
        raise SystemExit(f"module {top} not found")
    end = text.index("endmodule", m.end())
    head_end = text.index(");", m.end())
    body = text[head_end:end]
    insts = {}
    for im in INST_RE.finditer(body):
        insts.setdefault(im.group(3).strip().lstrip("\\"), im.start())
    decls, assigns, seen = [], [], set()
    for k, (inst, pin, d, v) in enumerate(faults):
        if (inst, pin) in seen:
            raise SystemExit(f"pin {inst}.{pin} sampled twice")
        seen.add((inst, pin))
        if inst not in insts:
            raise SystemExit(f"instance {inst} not found in {top}")
        start = insts[inst]
        stop = body.index(");", start)
        blk = body[start:stop]
        pm = re.search(rf"\.{re.escape(pin)}\((.*?)\)(,?)\s*$", blk, re.M)
        if not pm or not pm.group(1).strip():
            raise SystemExit(f"pin {inst}.{pin}: no connection in the netlist")
        net = pm.group(1).strip()
        blk2 = blk[:pm.start()] + f".{pin}(cvtf_{k}){pm.group(2)}" + blk[pm.end():]
        body = body[:start] + blk2 + body[stop:]
        delta = len(blk2) - len(blk)
        insts = {i: (p + delta if p > start else p) for i, p in insts.items()}
        decls += [f"  input fsel_{k};", f"  wire cvtf_{k};"]
        assigns.append(f"  assign cvtf_{k} = fsel_{k} ? 1'b{v} : {net};" if d == "in"
                       else f"  assign {net} = fsel_{k} ? 1'b{v} : cvtf_{k};")
    header = text[m.start():head_end] + "".join(f", fsel_{k}" for k in range(len(faults)))
    return (text[:m.start()] + header + body[:2] + "\n" + "\n".join(decls) + body[2:] + "\n".join(assigns) + "\n"
            + text[end:])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--top", required=True)
    ap.add_argument("--cellpin-cut", required=True, help="output DIR of mk_cut.py --cellpin (cut.blif, cut_sites.txt)")
    ap.add_argument("--faults", required=True, help="regrade.py --sites --dump-faults output")
    ap.add_argument("--patterns", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--const", action="append", default=[])
    ap.add_argument("--bbox", action="append", default=[])
    ap.add_argument("--yosys", default=mk_cut.DEFAULT_YOSYS)
    ap.add_argument("--vl-shell", default=regrade_vl.DEFAULT_VL_SHELL)
    ap.add_argument("--sat-undetected", type=int, default=60)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cut = Path(a.cellpin_cut)
    faults = json.loads(Path(a.faults).read_text())
    pins = site_pins((cut / "cut.blif").read_text(), [f["net"] for f in faults])
    fl = [(*pins[f["net"]], int(f["value"])) for f in faults]
    (out / "pins.json").write_text(json.dumps([{"site": f["net"], "inst": i, "pin": p, "dir": d, "value": v,
                                                 "own_sim_detects": f.get("own_sim_detects")}
                                                for f, (i, p, d, v) in zip(faults, fl)], indent=1))
    faulted = out / "faulted.v"
    faulted.write_text(inject(Path(a.netlist).read_text(errors="replace"), a.top, fl))
    margs = [str(faulted), "--top", a.top, "--out", str(out / "cut"), "--yosys", a.yosys]
    margs += [x for c in a.const for x in ("--const", c)] + [x for b in a.bbox for x in ("--bbox", b)]
    rc = mk_cut.main(margs)
    if rc != 0:
        return rc
    with tempfile.TemporaryDirectory(dir=out) as td:
        rep = regrade_vl.run(out / "cut" / "cut.blif", Path(a.patterns), faults, a.yosys, a.vl_shell, Path(td),
                             a.sat_undetected, preselected=True)
    rep["method"] = "pin_inject: faults injected at instance pins of the Verilog netlist, generic flow, Verilator + Yosys SAT"
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in rep if k not in ("disagreements", "holes")}), "disagreements:", len(rep["disagreements"]))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
