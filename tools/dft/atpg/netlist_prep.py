#!/usr/bin/env python3
"""Pre-pass on a Sky130 gate netlist before the ATPG cut (bead j41m.15): declare and apply the exclusions.

usage: netlist_prep.py NETLIST OUT.v --exclusions OUT.json [--key-qrx REGEX] [--clock-roots tck_i,scan_clk_i]
                       [--hold-mask] [--keep-unscanned]

What it does (each item is counted in the exclusions manifest, nothing is silent):
  1. deletes physical-only instances: fill, decap, tap, antenna diode (no logic);
  2. UNSCANNED flops = flop cells that are not sdf*/sedf* scan cells.  Each is classified:
       tck      clock root (through buffers/inverters) is tck_i      -> TAP and MBIST TDR flops, tested through JTAG
       scan_clk clock root is scan_clk_i                             -> clock switch
       key      Q net matches --key-qrx                              -> crypto key registers, masked in scan mode
       other    anything else (an error to be reported, never hidden)
     A reset-type flop (RESET_B / SET_B pin) is removed and its Q tied to the reset value: with trst_ni = 0 and
     tck_i = 0 the flop sits in reset.  A flop without a reset keeps an unknown power-up value: it becomes a FREE
     pseudo-input (every non-clock input tied constant, so its D cone is not observed) and is counted as `free_init_x`.
     Key flops are always removed with Q tied 0 (their cone is masked by scan_mode, so the value is irrelevant).
  3. --hold-mask: the 94 flops from derive_hold_mask.py keep their Q (still shift-controllable) but their D pin is
     tied 0, so the capture value is not observed.
With --keep-unscanned (A/B estimate only) steps 2 is skipped and the unscanned flops stay ordinary full-scan flops.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive_hold_mask  # noqa: E402
from netlist_lib import BUF_RE, CELL_RE, FILLER_RE, FLOP_TYPE_RE, INV_RE, SCAN_FLOP_RE, norm  # noqa: E402

RAW_PIN_RE = re.compile(r"\.(\w+)\(([^()]*)\)")
OUT_PINS = ("X", "Y", "Q", "Q_N", "HI", "LO")
SET_TYPE_RE = re.compile(r"sky130_fd_sc_hd__s?e?df(stp|sbp|bbp)")


def clock_root(net: str, driver: Dict[str, tuple]) -> str:
    for _ in range(64):
        d = driver.get(net)
        if d is None:
            return net
        net = d[1]
    return "loop"


def tie_pins(body: str) -> str:
    """Tie every input pin except CLK to a constant: D, DE, SCD, SCE -> 0; RESET_B, SET_B -> 1."""
    def sub(m):
        pin = m.group(1)
        if pin in OUT_PINS or pin == "CLK":
            return m.group(0)
        return f".{pin}(1'b{1 if pin in ('RESET_B', 'SET_B') else 0})"
    return RAW_PIN_RE.sub(sub, body)


def const_sub(body: str, pin: str, val: int) -> str:
    return re.sub(rf"\.{pin}\([^()]*\)", f".{pin}(1'b{val})", body)


def prep(netlist: Path, out: Path, key_qrx: Optional[str], clock_roots: List[str], hold_mask: bool,
         keep_unscanned: bool, full_scan: bool = False) -> dict:
    text = Path(netlist).read_text(encoding="utf-8", errors="replace")
    matches = list(CELL_RE.finditer(text))
    driver: Dict[str, tuple] = {}
    for m in matches:
        typ = m.group(1)
        if BUF_RE.match(typ) or INV_RE.match(typ):
            pins = {p: norm(n) for p, n in RAW_PIN_RE.findall(m.group(3))}
            o = pins.get("X") or pins.get("Y")
            if o:
                driver[o] = (m.group(2), pins.get("A", ""))
    qrx = re.compile(key_qrx) if key_qrx else None

    # flop census and classification
    classes: Dict[str, List[str]] = {"tck": [], "scan_clk": [], "key": [], "other": []}
    action: Dict[int, tuple] = {}
    n_scan = n_unscanned = 0
    free_init_x: List[str] = []
    types = Counter()
    mask_insts = set()
    if hold_mask:
        flops = {norm(m.group(2)): derive_hold_mask.Cell(m.group(1), norm(m.group(2)),
                                                         {p: norm(n) for p, n in RAW_PIN_RE.findall(m.group(3))})
                 for m in matches if FLOP_TYPE_RE.match(m.group(1))}
        mask = derive_hold_mask.derive(flops)
        mask_insts = {x["inst"] for x in mask}
        mask_rules = Counter(x["rule"] for x in mask)
    else:
        mask_rules = Counter()
    n_removed_phys = 0
    for idx, m in enumerate(matches):
        typ, inst, body = m.group(1), norm(m.group(2)), m.group(3)
        if FILLER_RE.match(typ):
            action[idx] = ("delete",)
            n_removed_phys += 1
            continue
        if not FLOP_TYPE_RE.match(typ):
            continue
        types[typ.replace("sky130_fd_sc_hd__", "")] += 1
        pins = {p: norm(n) for p, n in RAW_PIN_RE.findall(body)}
        if SCAN_FLOP_RE.match(typ):
            n_scan += 1
            if inst in mask_insts:
                action[idx] = ("tie_d",)
            continue
        if full_scan and not (qrx and qrx.search(pins.get("Q", ""))):
            n_scan += 1  # standalone module: every flop is a scan flop by assumption (the cut is full-scan)
            continue
        n_unscanned += 1
        root = clock_root(pins.get("CLK", ""), driver)
        q = pins.get("Q", "")
        if qrx and qrx.search(q):
            cls = "key"
        elif root == "tck_i" and "tck_i" in clock_roots:
            cls = "tck"
        elif root == "scan_clk_i" and "scan_clk_i" in clock_roots:
            cls = "scan_clk"
        else:
            cls = "other"
        classes[cls].append(inst)
        if keep_unscanned or cls == "other":
            continue
        has_reset = ("RESET_B" in pins) or ("SET_B" in pins)
        if cls == "key" or has_reset:
            val = 1 if SET_TYPE_RE.match(typ) and cls != "key" else 0
            raw_q = re.search(r"\.Q\(([^()]*)\)", body)
            action[idx] = ("remove", raw_q.group(1).strip() if raw_q else None, val, "Q_N" in pins)
        else:
            free_init_x.append(inst)
            action[idx] = ("free",)

    pieces = []
    last = 0
    assigns = []
    for idx, m in enumerate(matches):
        a = action.get(idx)
        if a is None:
            continue
        pieces.append(text[last:m.start()])
        last = m.end()
        if a[0] == "delete":
            continue
        typ, inst, body = m.group(1), m.group(2), m.group(3)
        if a[0] == "tie_d":
            pieces.append(f"\n {typ} {inst} ({const_sub(body, 'D', 0)});")
        elif a[0] == "free":
            pieces.append(f"\n {typ} {inst} ({tie_pins(body)});")
        elif a[0] == "remove":
            _, qraw, val, has_qn = a
            if qraw:
                assigns.append(f" assign {qraw} = 1'b{val};")
            if has_qn:
                qn = re.search(r"\.Q_N\(([^()]*)\)", body)
                if qn:
                    assigns.append(f" assign {qn.group(1).strip()} = 1'b{1 - val};")
    pieces.append(text[last:])
    new = "".join(pieces)
    if assigns:
        i = new.rindex("endmodule")
        new = new[:i] + "\n".join(a.replace(" = ", "  = ") for a in assigns) + "\n" + new[i:]
    Path(out).write_text(new)

    manifest = {
        "netlist": str(netlist),
        "flops_total": n_scan + n_unscanned,
        "flops_scan_cells": n_scan,
        "flops_unscanned": n_unscanned,
        "tck_flops": len(classes["tck"]),
        "scan_clk_flops": len(classes["scan_clk"]),
        "crypto_key_flops": len(classes["key"]),
        "other_unscanned_flops": len(classes["other"]),
        "other_unscanned_examples": classes["other"][:10],
        "free_init_x_flops": len(free_init_x),
        "hold_masked_flops": len(mask_insts),
        "hold_mask_rules": dict(mask_rules),
        "physical_cells_deleted": n_removed_phys,
        "flop_types": dict(types),
        "full_scan_assumed": full_scan,
        "keep_unscanned_mode": keep_unscanned,
        "unscanned_applied": not keep_unscanned,
    }
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("out")
    ap.add_argument("--exclusions", required=True)
    ap.add_argument("--key-qrx")
    ap.add_argument("--clock-roots", default="tck_i,scan_clk_i")
    ap.add_argument("--hold-mask", action="store_true")
    ap.add_argument("--keep-unscanned", action="store_true")
    ap.add_argument("--full-scan", action="store_true",
                    help="standalone module netlist: all flops are scanned by assumption; only --key-qrx flops are excluded")
    a = ap.parse_args(argv)
    man = prep(Path(a.netlist), Path(a.out), a.key_qrx, a.clock_roots.split(","), a.hold_mask, a.keep_unscanned,
               a.full_scan)
    Path(a.exclusions).write_text(json.dumps(man, indent=1))
    print(json.dumps({k: v for k, v in man.items() if k not in ("flop_types", "other_unscanned_examples")}))
    return 1 if man["other_unscanned_flops"] and not a.keep_unscanned else 0


if __name__ == "__main__":
    sys.exit(main())
