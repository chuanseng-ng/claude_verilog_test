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

SEQ_PREFIXES = ("$dff", "$adff", "$sdff", "$aldff", "$dffsr", "$dlatch", "$adlatch", "$sr",
                "$mem", "$dffe", "$sdffe", "$adffe")
ASYNC_PORTS = {"ARST": "arst", "ALOAD": "aload", "SET": "set", "CLR": "clr"}


def is_seq(t):
    return t.startswith(SEQ_PREFIXES)


def run_yosys(netlist, top, models=()):
    out = Path(tempfile.mkdtemp(prefix="scanchk_")) / "d.json"
    pre = "".join(f"read_verilog -sv {m}; " for m in models)
    script = (f"{pre}read_verilog -sv -defer {netlist}; hierarchy -top {top}; proc; flatten; opt_clean; "
              f"write_json {out}")
    subprocess.run([os.environ.get("YOSYS", "yosys"), "-q", "-p", script], check=True)
    return str(out)


def load(path, top):
    d = json.load(open(path))
    mod = d["modules"][top]
    drivers = {}   # bit -> (cell name, port)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs="?")
    ap.add_argument("--netlist")
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--scan-mode", default="scan_mode_i")
    ap.add_argument("--expect-gates", type=int, default=0)
    ap.add_argument("--max-print", type=int, default=12)
    ap.add_argument("--tap-prefix", action="append", default=[],
                    help="flattened instance-name prefix of TAP-domain cells (repeatable); see the docstring")
    ap.add_argument("--tck", default="tck_i", help="TAP clock port")
    ap.add_argument("--trst", default="trst_ni", help="TAP reset port")
    ap.add_argument("--scan-mode-net", default=None,
                    help="flattened net that IS scan mode (pin OR TAP); default: the --scan-mode port")
    ap.add_argument("--expect-tap-flops", type=int, default=0)
    ap.add_argument("--tap-alt-clock", action="append", default=[],
                    help="additional port a TAP-domain cell may be clocked by exactly (repeatable), e.g. scan_clk_i "
                         "for the pin-side half of the glitch-free test-clock switch")
    ap.add_argument("--tap-allowed-nets", action="append", default=[],
                    help="flattened net the TAP domain may drive into non-TAP logic or an output port (repeatable); "
                         "anything else crossing the TAP boundary is a violation")
    ap.add_argument("--models", action="append", default=[],
                    help="Verilog behavioural/blackbox models of library cells and hard macros that the "
                         "netlist instantiates but does not define (e.g. tools/dft/asap7_cell_models.v)")
    a = ap.parse_args()
    path = a.json or run_yosys(a.netlist, a.top, a.models)
    cells, drivers, ports, in_bits = load(path, a.top)
    netnames = json.load(open(path))["modules"][a.top].get("netnames", {})
    # A cell whose module is undefined has no port directions, so its outputs would never be traced and every
    # cone ending in it would silently look controlled. Refuse to pass on such a netlist.
    undefined = sorted({c["type"] for c in cells.values()
                        if not c["type"].startswith("$") and not c["port_directions"]})
    if undefined:
        print(f"FAIL: cell types with no definition (outputs untraceable, result would be vacuous): "
              f"{', '.join(undefined)}; pass --models FILE defining them")
        return 1
    if a.scan_mode_net:
        if a.scan_mode_net not in netnames:
            print(f"FAIL: scan-mode net {a.scan_mode_net} not found in the flattened netlist (renamed?)")
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
                violations.append((nn, "net", "TAP_BOUNDARY", "allowed TAP output net not found (renamed?)"))
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
                    if isinstance(b, int) and b in drivers and drivers[b][0] in tap_any and b not in allowed:
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
            violations.append((a.scan_mode_net, "net", "SCAN_MODE", f"pin leg {a.scan_mode} missing from scan mode"))
        if a.tap_prefix and not (legs_seqs & tap_cells):
            violations.append((a.scan_mode_net, "net", "SCAN_MODE", "TAP leg missing from scan mode"))

    for cname, c in cells.items():
        t = c["type"]
        if not is_seq(t):
            continue
        n_seq += 1
        if cname in tap_cells:
            n_tap += 1
            ck = c["connections"].get("CLK") or c["connections"].get("EN") or []
            for b in ck:
                if isinstance(b, int) and cone_leaves(b) not in [({p_}, set()) for p_ in [a.tck, *a.tap_alt_clock]]:
                    ph, sh = cone_leaves(b)
                    violations.append((cname, t, "CLK", f"TAP clock cone is not exactly port {a.tck} (or an alt clock {a.tap_alt_clock}): "
                                       f"ports {sorted(ph)} seq {sorted(sh)[:3]}"))
            for p in ASYNC_PORTS:
                for b in c["connections"].get(p, []):
                    if isinstance(b, int):
                        n_async += 1
                        ports_hit, seqs_hit = cone_leaves(b)
                        if not (ports_hit <= {a.trst} and seqs_hit <= tap_sync):
                            violations.append((cname, t, p, f"TAP reset cone not trst-only: ports "
                                               f"{sorted(ports_hit)} seq {sorted(seqs_hit - tap_sync)[:3]}"))
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

    print(f"sequential cells: {n_seq}; async reset/set pins checked: {n_async}; scan-mode muxes: {gates}; "
          f"TAP-domain flops: {n_tap} (reset synchronisers: {len(tap_sync)})")
    uniq = sorted(set(violations))
    print(f"violations: {len(uniq)}")
    for v in uniq[: a.max_print]:
        print("FAIL:", *v)
    if len(uniq) > a.max_print:
        print(f"... {len(uniq) - a.max_print} more")
    if n_tap < a.expect_tap_flops:
        print(f"FAIL: expected at least {a.expect_tap_flops} TAP-domain flops, found {n_tap} "
              f"(prefix wrong or optimised away?)")
        return 1
    if gates < a.expect_gates:
        print(f"FAIL: expected at least {a.expect_gates} scan-mode muxes, found {gates} (optimised away?)")
        return 1
    return 1 if uniq else 0


if __name__ == "__main__":
    sys.exit(main())
