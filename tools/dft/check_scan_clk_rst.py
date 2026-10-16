#!/usr/bin/env python3
"""Gate: in scan mode every flop is clocked from a port and every async reset is tester-controlled.

Bead claude_verilog_test-j41m.2 (DFT Stage 1a), docs/design/DFT_ARCHITECTURE.md section 14.

usage: check_scan_clk_rst.py design.json [--top soc_top] [--scan-mode scan_mode_i] [--expect-gates N]
                             [--models cells.v ...]
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

TAP DOMAIN (bead claude_verilog_test-j41m.3, DFT Stage 1b). With --tap-prefix PFX (repeatable) every
sequential cell whose flattened name starts with "PFX." is a TAP-domain flop: by decision N4 it is on no scan
chain, so it is NOT held to the rules above. It is held to its own:

  * its CLK (latch EN) cone ends at the tck port and nowhere else (no mux, no flop-generated clock);
  * its async reset cone ends at the trst port, or at a TAP-domain "reset synchroniser" flop whose own
    async reset cone ends directly at the trst port (so nothing functional, no rst_n_i, no PLL/PMU reset,
    can reset or disturb the TAP, and a TAP flop cannot be reset by another TAP flop in a loop).
Everything outside the TAP is still held to the original rules, which also makes any path from a TAP flop
into a non-TAP clock or reset (other than through the scan-mode mux) a violation.

--scan-mode-net NAME names the flattened scan-mode NET (e.g. u_dft_ctrl.scan_mode_o) instead of the port,
for a design where scan mode is the OR of a pin and the TAP. The net's fan-in must contain BOTH the
--scan-mode port (the 1a pin leg) and at least one TAP-domain flop, so removing either leg fails.
--tap-allowed-nets NET (repeatable) lists the ONLY nets by which TAP-domain logic may drive non-TAP logic or an
output port; an undeclared TCK-domain crossing fails. It backs the `tck_i` entry in tools/cdc/cdc_config.yml.
--expect-tap-flops N fails if fewer than N TAP-domain flops are found (renamed/optimised-away guard).
--expect-reset-sync SYNC=CONSUMER (repeatable; bead claude_verilog_test-j41m.11) names one `cdc_reset_sync` chain on the
trst port and the logic it must reset, both as flattened instance-name prefixes, e.g.
`u_dft_ctrl.u_sw_rst=u_dft_ctrl.u_clk_sw`. Each chain is identified independently, by hierarchy, on this netlist (it has
had no opt_merge, so two structurally identical chains stay two; cdc_snitch's flow merges them and cannot tell them apart):

  * at least --reset-sync-min-flops (default 2) flops under SYNC, each with an async reset cone that is exactly the trst
    port and a clock cone that is exactly the tck port (a removed, bypassed, renamed or re-clocked chain fails and is named);
  * at least one sequential cell under CONSUMER (outside every declared SYNC) has an input cone ending at a flop of that
    SYNC, i.e. the consumer really is reset by this synchroniser and not by another chain;
  * the trst port reaches NO sequential cell outside the declared SYNC chains through combinational logic alone. This closes
    the TAP rule above, which accepts a TAP flop reset straight from the trst port, so a bypassed synchroniser passed.

BLOCK MODE (bead claude_verilog_test-j41m.4, the CPU hard macro). A hard macro has no test-clock mux of its own: the
parent (soc_top) muxes the test clock onto the macro's clock pin, so inside the macro "scan mode" is invisible on the clock
path and a flop clocked straight from the clock pin is correct. Three options express that:

  --clock-port PORT  (repeatable) a port that IS the block's clock root; a clock cone ending there needs no scan-mode mux
                     (every other port, and every flop-generated clock, is still a violation);
  --max-async-pins N fails if more than N async reset/set pins exist (0 for the macro: all its resets are the synchronous
                     rst_n_i that the parent already forces, so there is nothing for a reset mux to override);
  --expect-seq-min N fails if fewer than N sequential cells are found (a renamed/blackboxed block cannot pass vacuously);
  --all-latches-need-scan-mode  EVERY $dlatch must have scan_mode in its D cone, whether or not it clocks a traced flop.
                     Needed because the ASAP7 macro's clock gates clock only SRAM macros (models, not sequential cells),
                     so the clock-cone walk never reaches them and would pass vacuously;
  --expect-latches-min N  fails if fewer than N $dlatch cells exist (10 in the ASAP7 macro: 5 gates per cache).

CLOCK-GATE TE FORCE (bead claude_verilog_test-j41m.16). Every clock-gate latch the checker reaches (in a flop's clock cone, or
any latch with --all-latches-need-scan-mode) must be FORCED OPEN by scan mode, not merely mention it: with scan mode = 1 and
every other input unknown, the latch D input must evaluate to 1 (three-valued propagation through the enable cone, see
`tv`). That catches a test-enable pin that is tied 0, floating, driven by a functional register, inverted, ANDed with
a functional term, or missing from the cell altogether (plain dlclkp: a gate with no TE pin), and it works the same on the
Sky130 sdlclkp, the ASAP7 ICG and the behavioural rv32i_clock_gate, because all three flatten to the same $dlatch + AND.
A finding names the gate INSTANCE. --waive-clock-gate PREFIX (repeatable) accepts a documented exception by flattened
instance-name prefix; a waiver that matches no gate fails (stale).

Exit 0 only if there are no violations AND (with --expect-gates) the number of scan-mode muxes
found is at least N, so that a design in which the muxes were optimised away or renamed cannot
pass vacuously. A cell type with no definition (a library cell or hard macro the netlist instantiates
but does not define) also fails, because its outputs cannot be traced; give it a model with --models
(tools/dft/asap7_cell_models.v for the ASAP7 SoC netlist). Negative controls (run by
tb/tests/test_dft_scan_check.py): replacing the muxes with wires makes this fail.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SEQ_PREFIXES = (
    "$dff",
    "$adff",
    "$sdff",
    "$aldff",
    "$dffsr",
    "$dlatch",
    "$adlatch",
    "$sr",
    "$mem",
    "$dffe",
    "$sdffe",
    "$adffe",
)
ASYNC_PORTS = {"ARST": "arst", "ALOAD": "aload", "SET": "set", "CLR": "clr"}


def is_seq(t):
    return t.startswith(SEQ_PREFIXES)


def run_yosys(netlist, top, models=()):
    out = Path(tempfile.mkdtemp(prefix="scanchk_")) / "d.json"
    pre = "".join(f"read_verilog -sv {m}; " for m in models)
    script = (
        f"{pre}read_verilog -sv -defer {netlist}; hierarchy -top {top}; proc; flatten; opt_clean; "
        f"write_json {out}"
    )
    subprocess.run([os.environ.get("YOSYS", "yosys"), "-q", "-p", script], check=True)
    return str(out)


def load(path, top):
    d = json.load(open(path))
    mod = d["modules"][top]
    drivers = {}  # bit -> (cell name, port)
    cells = mod["cells"]
    for cname, c in cells.items():
        c.setdefault("port_directions", {})
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


def flat_name(cname):
    # yosys `flatten` names cells "$flatten<backslash>u_a.<backslash>u_b.$procdff$12": drop the marker and the escapes
    return cname.replace("$flatten", "").replace("\\", "")


def check_reset_syncs(a, cells, ports, drivers, cell_inputs, cone_leaves, violations):
    """--expect-reset-sync (see the module docstring). Appends to `violations`; returns the number of verified chains."""

    def fail(spec, msg):
        violations.append((spec, "reset_sync", "RESET_SYNC", msg))

    def under(cn, prefix):
        return flat_name(cn).startswith(prefix + ".")

    pairs = []
    for spec in a.expect_reset_sync:
        sync_p, _, cons_p = spec.partition("=")
        if not sync_p or not cons_p:
            fail(
                spec,
                "malformed --expect-reset-sync, expected SYNC=CONSUMER (instance-name prefixes)",
            )
            continue
        pairs.append((sync_p, cons_p))
    seq_cells = {cn: c for cn, c in cells.items() if is_seq(c["type"])}
    sync_cells = {sp: {cn for cn in seq_cells if under(cn, sp)} for sp, _ in pairs}
    all_sync = set().union(*sync_cells.values()) if sync_cells else set()

    ok = 0
    for sync_p, cons_p in pairs:
        good = set()
        for cn in sorted(sync_cells[sync_p]):
            c = seq_cells[cn]
            arst = [
                b for p in ASYNC_PORTS for b in c["connections"].get(p, []) if isinstance(b, int)
            ]
            clk = [
                b
                for b in (c["connections"].get("CLK") or c["connections"].get("EN") or [])
                if isinstance(b, int)
            ]
            if not arst or any(cone_leaves(b) != ({a.trst}, set()) for b in arst):
                fail(sync_p, f"flop {flat_name(cn)} async reset is not exactly port {a.trst}")
            elif not clk or any(cone_leaves(b) != ({a.tck}, set()) for b in clk):
                fail(sync_p, f"flop {flat_name(cn)} clock is not exactly port {a.tck}")
            else:
                good.add(cn)
        chain_ok = len(good) >= a.reset_sync_min_flops
        if not chain_ok:
            fail(
                sync_p,
                f"reset synchroniser chain {sync_p}: expected at least {a.reset_sync_min_flops} flops with "
                f"async reset = port {a.trst} and clock = port {a.tck}, found {len(good)} "
                f"(chain removed, bypassed, renamed or re-clocked?)",
            )
        consumers = [cn for cn in seq_cells if under(cn, cons_p) and cn not in all_sync]
        if not consumers:
            fail(
                sync_p,
                f"consumer {cons_p} has no sequential cells (prefix wrong or optimised away?)",
            )
            chain_ok = False
        elif not any(
            cone_leaves(b)[1] & good for cn in consumers for _, b in cell_inputs(seq_cells[cn])
        ):
            fail(
                sync_p,
                f"{cons_p} is not reset from {sync_p}: no cell under it has an input cone ending at a flop "
                f"of that synchroniser",
            )
            chain_ok = False
        ok += chain_ok

    # No sequential cell outside the declared chains may be reached from the trst port by combinational logic alone.
    fanout = {}
    for cn, c in cells.items():
        for _, b in cell_inputs(c):
            fanout.setdefault(b, []).append(cn)
    seen, stack, direct = set(), [b for b in ports[a.trst]["bits"] if isinstance(b, int)], set()
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        for cn in fanout.get(b, []):
            if is_seq(cells[cn]["type"]):
                direct.add(cn)
                continue
            for pn, bits in cells[cn]["connections"].items():
                if cells[cn]["port_directions"].get(pn) == "output":
                    stack.extend(x for x in bits if isinstance(x, int))
    # One finding per instance (not per flop), so a bypass cannot bury the named-chain findings under dozens of flop lines.
    by_inst = {}
    for cn in direct - all_sync:
        inst = flat_name(cn).rsplit(".", 1)[0]
        by_inst[inst] = by_inst.get(inst, 0) + 1
    for inst, n in sorted(by_inst.items()):
        fail(
            inst,
            f"port {a.trst} reaches {n} sequential cell(s) under {inst} without a cdc_reset_sync "
            f"(synchroniser bypassed?)",
        )
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs="?")
    ap.add_argument("--netlist")
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--scan-mode", default="scan_mode_i")
    ap.add_argument("--expect-gates", type=int, default=0)
    ap.add_argument("--max-print", type=int, default=12)
    ap.add_argument(
        "--clock-port",
        action="append",
        default=[],
        help="port that is the block's clock root (its test-clock mux is in the parent); see BLOCK MODE",
    )
    ap.add_argument(
        "--max-async-pins",
        type=int,
        default=None,
        help="fail if more async reset/set pins than this exist (BLOCK MODE: 0 for the CPU macro)",
    )
    ap.add_argument(
        "--all-latches-need-scan-mode",
        action="store_true",
        help="every $dlatch needs scan_mode in its D cone, even if it clocks no traced flop (BLOCK MODE)",
    )
    ap.add_argument(
        "--expect-latches-min",
        type=int,
        default=0,
        help="fail if fewer $dlatch cells than this exist (vacuity guard for --all-latches-need-scan-mode)",
    )
    ap.add_argument(
        "--expect-seq-min",
        type=int,
        default=0,
        help="fail if fewer sequential cells than this are found (vacuity guard)",
    )
    ap.add_argument(
        "--waive-clock-gate",
        action="append",
        default=[],
        metavar="PREFIX",
        help="flattened instance-name prefix of a clock gate exempt from the scan-mode force rule "
        "(repeatable; a prefix matching no gate is a violation)",
    )
    ap.add_argument(
        "--tap-prefix",
        action="append",
        default=[],
        help="flattened instance-name prefix of TAP-domain cells (repeatable); see the docstring",
    )
    ap.add_argument("--tck", default="tck_i", help="TAP clock port")
    ap.add_argument("--trst", default="trst_ni", help="TAP reset port")
    ap.add_argument(
        "--scan-mode-net",
        default=None,
        help="flattened net that IS scan mode (pin OR TAP); default: the --scan-mode port",
    )
    ap.add_argument("--expect-tap-flops", type=int, default=0)
    ap.add_argument(
        "--expect-reset-sync",
        action="append",
        default=[],
        metavar="SYNC=CONSUMER",
        help="a cdc_reset_sync chain on the trst port and the logic it resets, as flattened instance "
        "prefixes (repeatable); see the docstring",
    )
    ap.add_argument(
        "--reset-sync-min-flops",
        type=int,
        default=2,
        help="minimum flops each --expect-reset-sync chain must contain (STAGES of cdc_reset_sync)",
    )
    ap.add_argument(
        "--tap-alt-clock",
        action="append",
        default=[],
        help="additional port a TAP-domain cell may be clocked by exactly (repeatable), e.g. scan_clk_i "
        "for the pin-side half of the glitch-free test-clock switch",
    )
    ap.add_argument(
        "--tap-allowed-nets",
        action="append",
        default=[],
        help="flattened net the TAP domain may drive into non-TAP logic or an output port (repeatable); "
        "anything else crossing the TAP boundary is a violation",
    )
    ap.add_argument(
        "--models",
        action="append",
        default=[],
        help="Verilog behavioural/blackbox models of library cells and hard macros that the "
        "netlist instantiates but does not define (e.g. tools/dft/asap7_cell_models.v)",
    )
    a = ap.parse_args()
    path = a.json or run_yosys(a.netlist, a.top, a.models)
    cells, drivers, ports, in_bits = load(path, a.top)
    netnames = json.load(open(path))["modules"][a.top].get("netnames", {})
    # A cell whose module is undefined has no port directions, so its outputs would never be traced and every
    # cone ending in it would silently look controlled. Refuse to pass on such a netlist.
    undefined = sorted(
        {
            c["type"]
            for c in cells.values()
            if not c["type"].startswith("$") and not c["port_directions"]
        }
    )
    if undefined:
        print(
            f"FAIL: cell types with no definition (outputs untraceable, result would be vacuous): "
            f"{', '.join(undefined)}; pass --models FILE defining them"
        )
        return 1
    if a.scan_mode_net:
        if a.scan_mode_net not in netnames:
            print(
                f"FAIL: scan-mode net {a.scan_mode_net} not found in the flattened netlist (renamed?)"
            )
            return 1
        sm_bits = set(b for b in netnames[a.scan_mode_net]["bits"] if isinstance(b, int))
    else:
        sm_bits = set(b for b in ports[a.scan_mode]["bits"] if isinstance(b, int))

    def in_tap(cname):
        # yosys `flatten` names cells "$flatten\u_a.\u_b.$procdff$12": drop the marker and the escapes
        n = cname.replace("$flatten", "").replace("\\", "")
        return any(n.startswith(p + ".") for p in a.tap_prefix)

    def cone_leaves(bit):
        """Terminals of the combinational fan-in cone: (input-port names, sequential cell names)."""
        ports_hit, seqs_hit, seen, stack = set(), set(), set(), [bit]
        while stack:
            b = stack.pop()
            if b in seen:
                continue
            seen.add(b)
            if b in in_bits:
                ports_hit.add(in_bits[b])
                continue
            if b not in drivers:
                continue
            cn, _ = drivers[b]
            if is_seq(cells[cn]["type"]):
                seqs_hit.add(cn)
                continue
            stack.extend(x for _, x in cell_inputs(cells[cn]))
        return ports_hit, seqs_hit

    def cell_inputs(c):
        for port, bits in c["connections"].items():
            if c["port_directions"].get(port) == "input":
                for b in bits:
                    if isinstance(b, int):
                        yield port, b

    def mux_is_scan(c):
        return c["type"] in ("$mux", "$pmux") and any(
            isinstance(b, int) and b in sm_bits for b in c["connections"].get("S", [])
        )

    gates = sum(1 for c in cells.values() if mux_is_scan(c))

    def depends_on_scan_mode(bit, seen=None):
        seen = set() if seen is None else seen
        stack = [bit]
        while stack:
            b = stack.pop()
            if b in sm_bits or vnum(b) in sm_ids():
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

    # Structural hashing (value numbering) of the combinational cones. The scan-mode net is one cell
    # (e.g. dft_ctrl's `scan_mode_o = pin | tap_scan`) and the clock-gate test enable another cell with the same
    # inputs (`test_en_o = pin | tap_scan`): flatten keeps both. They are the same function of the same
    # nets, so the second IS scan mode. Two bits share a number only if they have the same cell type, the same
    # parameters and inputs with the same numbers (operands of bitwise AND/OR/XOR compared unordered), or are
    # the same bit; a leaf (port, sequential output, undriven bit) only equals itself.
    vid = {}
    vtab = {}
    _bitwise = ("$and", "$or", "$xor", "$xnor")

    def intern(key):
        return vtab.setdefault(key, len(vtab))

    def vin(c, port, i):
        bits = c["connections"].get(port, [])
        signed = str(c.get("parameters", {}).get(port + "_SIGNED", "0")).strip("0") != ""
        if i < len(bits):
            x = bits[i]
        elif signed and bits:
            x = bits[-1]
        else:
            x = "0"
        return ("c", x) if isinstance(x, str) else vid[x]

    def vnum(bit):
        stack = [bit]
        while stack:
            b = stack[-1]
            if b in vid:
                stack.pop()
                continue
            if b in in_bits or b not in drivers or is_seq(cells[drivers[b][0]]["type"]):
                vid[b] = intern(("leaf", b))
                stack.pop()
                continue
            c = cells[drivers[b][0]]
            pend = [x for _, x in cell_inputs(c) if x not in vid]
            if pend and b not in comb_seen:
                comb_seen.add(b)
                stack.extend(pend)
                continue
            for _, x in cell_inputs(c):
                vid.setdefault(x, intern(("leaf", x)))   # combinational loop: unevaluated input = leaf
            ybits = c["connections"].get("Y", [])
            i = ybits.index(b) if b in ybits else -1
            params = tuple(sorted((k, str(v)) for k, v in c.get("parameters", {}).items()))
            if c["type"] in _bitwise and i >= 0:
                ops = tuple(sorted((repr(vin(c, "A", i)), repr(vin(c, "B", i)))))
                key = (c["type"], params, ops)
            else:
                ports_ = tuple(
                    (pn, tuple(repr(vin(c, pn, j)) for j in range(len(c["connections"][pn]))))
                    for pn in sorted(c["connections"])
                    if c["port_directions"].get(pn) == "input"
                )
                key = (c["type"], params, ports_, b if i < 0 else i)
            vid[b] = intern(key)
            stack.pop()
        return vid[bit]

    comb_seen = set()
    sm_id_cache = []

    def sm_ids():
        if not sm_id_cache:
            sm_id_cache.append({vnum(b) for b in sm_bits})
        return sm_id_cache[0]

    fv_memo = {}

    def tv(bit):
        """Three-valued value (0, 1 or None = unknown) of `bit` when every scan-mode bit is 1.

        Ports, sequential outputs, undefined and unsupported cells are unknown, so the result is conservative:
        `tv(b) == 1` means b is 1 in scan mode whatever the functional inputs are."""
        if isinstance(bit, str):
            return {"0": 0, "1": 1}.get(bit)
        stack, visiting = [bit], set()
        while stack:
            b = stack[-1]
            if b in fv_memo:
                stack.pop()
            elif b in sm_bits or vnum(b) in sm_ids():
                fv_memo[b] = 1
            elif b in in_bits or b not in drivers or is_seq(cells[drivers[b][0]]["type"]):
                fv_memo[b] = None
            else:
                c = cells[drivers[b][0]]
                pend = [x for _, x in cell_inputs(c) if x not in fv_memo and x not in sm_bits]
                if pend and b not in visiting:
                    visiting.add(b)
                    stack.extend(pend)
                else:  # all inputs known, or a combinational loop (unevaluated inputs read as unknown)
                    fv_memo[b] = eval_cell(c, b)
        return fv_memo.get(bit)

    def in_val(c, port, i):
        bits = c["connections"].get(port, [])
        signed = str(c.get("parameters", {}).get(port + "_SIGNED", "0")).strip("0") != ""
        if i < len(bits):
            x = bits[i]
        elif signed and bits:
            x = bits[-1]
        else:
            return 0
        if isinstance(x, str):
            return {"0": 0, "1": 1}.get(x)
        return 1 if x in sm_bits else fv_memo.get(x)

    def red(c, port, op):
        vals = [in_val(c, port, i) for i in range(len(c["connections"].get(port, [])))]
        if op == "or":
            return 1 if 1 in vals else (0 if all(v == 0 for v in vals) else None)
        return 0 if 0 in vals else (1 if all(v == 1 for v in vals) else None)

    def t_not(v):
        return None if v is None else 1 - v

    def t_and(x, y):
        return 0 if (x == 0 or y == 0) else (1 if (x == 1 and y == 1) else None)

    def t_or(x, y):
        return 1 if (x == 1 or y == 1) else (0 if (x == 0 and y == 0) else None)

    def eval_cell(c, b):
        t = c["type"]
        ybits = c["connections"].get("Y", [])
        if b not in ybits:
            return None
        i = ybits.index(b)
        if t in ("$and", "$or", "$not", "$pos", "$buf"):
            av = in_val(c, "A", i)
            if t in ("$pos", "$buf"):
                return av
            if t == "$not":
                return t_not(av)
            bv = in_val(c, "B", i)
            return t_and(av, bv) if t == "$and" else t_or(av, bv)
        if t in ("$reduce_or", "$reduce_bool", "$logic_not", "$reduce_and"):
            if i > 0:
                return 0
            r = red(c, "A", "and" if t == "$reduce_and" else "or")
            return t_not(r) if t == "$logic_not" else r
        if t in ("$logic_and", "$logic_or"):
            if i > 0:
                return 0
            ra, rb = red(c, "A", "or"), red(c, "B", "or")
            return t_and(ra, rb) if t == "$logic_and" else t_or(ra, rb)
        if t == "$mux":
            sv = in_val(c, "S", 0)
            av, bv = in_val(c, "A", i), in_val(c, "B", i)
            if sv == 0:
                return av
            if sv == 1:
                return bv
            return av if (av is not None and av == bv) else None
        return None  # $xor, $eq, $pmux, arithmetic, ...: unknown (conservative)

    used_waivers = set()
    n_gates = [0]

    def gate_name(cn):
        n = flat_name(cn)
        return n.rsplit(".", 1)[0] if "." in n else n

    def waived(cn):
        n = gate_name(cn)
        hit = [w for w in a.waive_clock_gate if n == w or n.startswith(w + ".")]
        used_waivers.update(hit)
        return bool(hit)

    def gate_findings(cn):
        """Findings for one clock-gate latch: [] if scan mode forces it open (or it is waived)."""
        n_gates[0] += 1
        if waived(cn):
            return []
        d = list(cells[cn]["connections"].get("D", []))
        name = gate_name(cn)
        if not any(isinstance(x, int) and depends_on_scan_mode(x) for x in d):
            return [f"clock gate {name}: latch (clock gate) has no scan-mode term in its D input"]
        if not all(tv(x) == 1 for x in d):
            return [
                f"clock gate {name}: scan mode does not force the gate open (its enable is not 1 when scan "
                f"mode = 1 whatever the functional enable is: test-enable floating, tied, inverted, gated by "
                f"a functional term, or the cell has no TE pin)"
            ]
        return []

    def trace(bit, kind):
        """Return list of violation strings for the cone feeding `bit`."""
        viol, seen, stack = [], set(), [(bit, False)]  # (bit, passed_scan_mux)
        while stack:
            b, passed = stack.pop()
            if (b, passed) in seen:
                continue
            seen.add((b, passed))
            if b in in_bits:
                if (
                    kind == "clock"
                    and not passed
                    and in_bits[b] != a.scan_mode
                    and in_bits[b] not in a.clock_port
                ):
                    viol.append(f"clock reaches port {in_bits[b]} without a scan-mode mux")
                continue
            if b not in drivers:
                continue
            cn, port = drivers[b]
            c = cells[cn]
            t = c["type"]
            if is_seq(t):
                if kind == "clock" and t.startswith("$dlatch"):
                    viol.extend(
                        gate_findings(cn)
                    )  # clean only if scan mode FORCES the latch D to 1
                else:
                    viol.append(f"{kind} is generated by sequential cell {cn} ({t})")
                continue
            if mux_is_scan(c):
                continue  # controlled: the scan branch is a port, the other branch is bypassed
            for _, x in cell_inputs(c):
                stack.append((x, passed))
        return viol

    violations = []
    n_async = n_seq = n_tap = 0

    tap_cells = {cn for cn, c in cells.items() if is_seq(c["type"]) and in_tap(cn)}

    # TAP boundary: the TCK domain may drive the rest of the SoC through the DECLARED nets only. This is the
    # compensating check for tools/cdc/cdc_config.yml, where `tck_i` is listed in reset_domains (cdc_snitch can then
    # no longer see a TCK-launched signal reaching a functional register). Any TAP-prefixed cell (flop or gate)
    # whose output bit feeds a non-TAP cell or an output port must be in the allowed net list.
    if a.tap_allowed_nets:
        allowed = set()
        for nn in a.tap_allowed_nets:
            if nn not in netnames:
                violations.append(
                    (nn, "net", "TAP_BOUNDARY", "allowed TAP output net not found (renamed?)")
                )
                continue
            allowed |= {b for b in netnames[nn]["bits"] if isinstance(b, int)}
        tap_any = {cn for cn in cells if in_tap(cn)}
        crossing = {}
        for cn, c in cells.items():
            if cn in tap_any:
                continue
            for _, b in cell_inputs(c):
                if b in drivers and drivers[b][0] in tap_any and b not in allowed:
                    crossing[b] = (drivers[b][0], cn)
        for pn, p in ports.items():
            if p["direction"] == "output":
                for b in p["bits"]:
                    if (
                        isinstance(b, int)
                        and b in drivers
                        and drivers[b][0] in tap_any
                        and b not in allowed
                    ):
                        crossing[b] = (drivers[b][0], f"port {pn}")
        for b, (src, dst) in sorted(crossing.items()):
            violations.append((src, "tap", "TAP_BOUNDARY", f"undeclared TAP output reaches {dst}"))
    # TAP reset synchroniser flops: async reset cone ends directly (and only) at the trst port.
    tap_sync = set()
    for cn in tap_cells:
        rb = [b for b in cells[cn]["connections"].get("ARST", []) if isinstance(b, int)]
        if rb and all(cone_leaves(b) == ({a.trst}, set()) for b in rb):
            tap_sync.add(cn)

    if a.scan_mode_net:
        # both legs of scan mode must exist: the 1a pin and the TAP
        legs_ports, legs_seqs = set(), set()
        for b in sm_bits:
            p_, s_ = cone_leaves(b)
            legs_ports |= p_
            legs_seqs |= s_
        if a.scan_mode not in legs_ports:
            violations.append(
                (
                    a.scan_mode_net,
                    "net",
                    "SCAN_MODE",
                    f"pin leg {a.scan_mode} missing from scan mode",
                )
            )
        if a.tap_prefix and not (legs_seqs & tap_cells):
            violations.append(
                (a.scan_mode_net, "net", "SCAN_MODE", "TAP leg missing from scan mode")
            )

    for cname, c in cells.items():
        t = c["type"]
        if not is_seq(t):
            continue
        n_seq += 1
        if cname in tap_cells:
            n_tap += 1
            ck = c["connections"].get("CLK") or c["connections"].get("EN") or []
            for b in ck:
                if isinstance(b, int) and cone_leaves(b) not in [
                    ({p_}, set()) for p_ in [a.tck, *a.tap_alt_clock]
                ]:
                    ph, sh = cone_leaves(b)
                    violations.append(
                        (
                            cname,
                            t,
                            "CLK",
                            f"TAP clock cone is not exactly port {a.tck} (or an alt clock {a.tap_alt_clock}): "
                            f"ports {sorted(ph)} seq {sorted(sh)[:3]}",
                        )
                    )
            for p in ASYNC_PORTS:
                for b in c["connections"].get(p, []):
                    if isinstance(b, int):
                        n_async += 1
                        ports_hit, seqs_hit = cone_leaves(b)
                        if not (ports_hit <= {a.trst} and seqs_hit <= tap_sync):
                            violations.append(
                                (
                                    cname,
                                    t,
                                    p,
                                    f"TAP reset cone not trst-only: ports "
                                    f"{sorted(ports_hit)} seq {sorted(seqs_hit - tap_sync)[:3]}",
                                )
                            )
            continue
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

    n_latch = 0
    for cname, c in cells.items():
        if c["type"].startswith("$dlatch") and cname not in tap_cells:
            n_latch += 1
            if a.all_latches_need_scan_mode:
                for v in gate_findings(cname):
                    violations.append((cname, c["type"], "EN", v))

    for w in a.waive_clock_gate:
        if w not in used_waivers:
            violations.append(
                (w, "waiver", "CLOCK_GATE", f"waiver {w} matches no clock gate (stale or renamed?)")
            )

    n_rs_ok = 0
    if a.expect_reset_sync:
        n_rs_ok = check_reset_syncs(a, cells, ports, drivers, cell_inputs, cone_leaves, violations)

    print(
        f"sequential cells: {n_seq}; async reset/set pins checked: {n_async}; scan-mode muxes: {gates}; "
        f"TAP-domain flops: {n_tap} (reset synchronisers: {len(tap_sync)})"
    )
    if a.expect_reset_sync:
        print(f"reset synchronisers verified: {n_rs_ok} of {len(a.expect_reset_sync)}")
    uniq = sorted(set(violations))
    print(f"violations: {len(uniq)}")
    for v in uniq[: a.max_print]:
        print("FAIL:", *v)
    if len(uniq) > a.max_print:
        print(f"... {len(uniq) - a.max_print} more")
    if n_tap < a.expect_tap_flops:
        print(
            f"FAIL: expected at least {a.expect_tap_flops} TAP-domain flops, found {n_tap} "
            f"(prefix wrong or optimised away?)"
        )
        return 1
    if n_latch < a.expect_latches_min:
        print(
            f"FAIL: expected at least {a.expect_latches_min} latches, found {n_latch} (clock gates removed or renamed?)"
        )
        return 1
    if n_seq < a.expect_seq_min:
        print(
            f"FAIL: expected at least {a.expect_seq_min} sequential cells, found {n_seq} (blackboxed or renamed?)"
        )
        return 1
    if a.max_async_pins is not None and n_async > a.max_async_pins:
        print(
            f"FAIL: expected at most {a.max_async_pins} async reset/set pins, found {n_async} "
            f"(a derived or async reset appeared in the block: it needs a scan-mode override)"
        )
        return 1
    if gates < a.expect_gates:
        print(
            f"FAIL: expected at least {a.expect_gates} scan-mode muxes, found {gates} (optimised away?)"
        )
        return 1
    return 1 if uniq else 0


if __name__ == "__main__":
    sys.exit(main())
