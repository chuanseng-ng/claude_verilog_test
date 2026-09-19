#!/usr/bin/env python3
"""diff_asap7_sram_boundary.py -- SRAM macro-boundary structural + placement diff.

Built for bead `claude_verilog_test-lxv` (2026-09-19): diagnosing why switching
pnr/asap7/cpu/config.json from USE_SYNLIG:true to USE_SYNLIG:false+sv2v caused
detailed routing to regress from a 2045-violation baseline to 108716 violations,
concentrated as DRT-0255 "Maze Route cannot find path" failures on SRAM macro
pins (clk0/csb0/addr0/din0/dout0).

Two independent, run-free checks (no PD invocation needed -- operates on
already-completed run artifacts):

1. `netlist` mode: compares the immediate gate-level fanin structure driving a
   given macro instance's pin between two post-synthesis netlists (e.g. a
   Synlig-frontend build vs an sv2v-frontend build of the same RTL). Reports
   the driving cell type and its own fanin arity so a structural regression
   (an inserted buffer layer, a widened mux, a different gate family) is
   visible even though auto-generated net numbers differ between independent
   synthesis runs.

2. `placement` mode: compares (a) standard-cell count inside a bounding box
   (e.g. the PL_MACRO_HALO keepout zone around a macro row) and (b) the
   Manhattan distance from a stably-named driver instance (e.g. a per-macro
   ICG clock-gate cell) to that macro's known pin location, between two DEF
   files at the same pipeline stage.

Usage:
    diff_asap7_sram_boundary.py netlist <good.v> <bad.v> \\
        --net u_core.u_dcache.data_csb0[0]

    diff_asap7_sram_boundary.py placement <good.def> <bad.def> \\
        --box 0 47 60 99 --exclude-substr sram

Neither mode requires an OpenROAD/LibreLane invocation; both are pure text
parsers over existing run artifacts. See bd show claude_verilog_test-lxv for
the full diagnostic trail this script was written to reproduce.
"""
import argparse
import re
import sys


def find_driver_context(path, net, context=6):
    """Return the instance block whose output pin drives `net`, plus a few
    lines of leading context (the driving cell's own module/type + input
    pins), from a flattened post-synthesis Verilog netlist.

    `net` is given without the leading backslash/trailing space Yosys uses
    for escaped hierarchical identifiers; both are added when searching.
    """
    escaped = re.escape(net)
    pat = re.compile(r'\.\s*[A-Za-z_][\w]*\s*\(\s*\\' + escaped + r'\s*\)')
    lines = open(path).readlines()
    hits = []
    for i, line in enumerate(lines):
        if pat.search(line):
            start = max(0, i - context)
            hits.append((i, ''.join(lines[start:i + 1])))
    return hits


def cmd_netlist(args):
    good_hits = find_driver_context(args.good, args.net)
    bad_hits = find_driver_context(args.bad, args.net)
    print(f"=== driver(s) of {args.net!r} ===")
    print(f"-- {args.good} ({len(good_hits)} match(es)) --")
    for lineno, ctx in good_hits:
        print(f"  [line {lineno + 1}]\n{ctx}")
    print(f"-- {args.bad} ({len(bad_hits)} match(es)) --")
    for lineno, ctx in bad_hits:
        print(f"  [line {lineno + 1}]\n{ctx}")
    if not good_hits or not bad_hits:
        print("WARNING: net not found in one or both files -- check escaping/name.")
        return 1
    return 0


def parse_def_components(path):
    units = 1000
    comps = []
    in_comp = False
    with open(path) as f:
        for line in f:
            m = re.match(r'UNITS DISTANCE MICRONS (\d+)', line)
            if m:
                units = int(m.group(1))
            s = line.strip()
            if s.startswith('COMPONENTS'):
                in_comp = True
                continue
            if in_comp and s.startswith('END COMPONENTS'):
                break
            if in_comp and s.startswith('-'):
                head = re.match(r'-\s+(\S+)\s+(\S+)', s)
                loc = re.search(
                    r'(PLACED|FIXED)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)', s)
                if head and loc:
                    inst, cell = head.groups()
                    _status, x, y, _orient = loc.groups()
                    comps.append((inst, cell, int(x) / units, int(y) / units))
    return comps


def cmd_placement(args):
    x0, y0, x1, y1 = args.box
    for label, path in [('good', args.good), ('bad', args.bad)]:
        comps = parse_def_components(path)
        total = len(comps)
        n = sum(1 for _inst, cell, x, y in comps
                if x0 <= x <= x1 and y0 <= y <= y1
                and (not args.exclude_substr
                     or args.exclude_substr.lower() not in cell.lower()))
        macros = sum(1 for _inst, cell, _x, _y in comps
                     if args.exclude_substr
                     and args.exclude_substr.lower() in cell.lower())
        print(f"{label}: {path}")
        print(f"  total_components={total} macros_matched={macros} "
              f"stdcells_in_box={n} box=({x0},{y0})-({x1},{y1})")

    if args.driver_inst and args.pin_xy:
        px, py = args.pin_xy
        for label, path in [('good', args.good), ('bad', args.bad)]:
            comps = parse_def_components(path)
            by_inst = {inst: (x, y) for inst, _c, x, y in comps}
            if args.driver_inst not in by_inst:
                print(f"{label}: driver instance {args.driver_inst!r} not found")
                continue
            dx, dy = by_inst[args.driver_inst]
            dist = abs(dx - px) + abs(dy - py)
            print(f"{label}: driver={args.driver_inst} at ({dx:.3f},{dy:.3f}) "
                  f"pin=({px:.3f},{py:.3f}) manhattan_dist={dist:.3f}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='mode', required=True)

    p_net = sub.add_parser('netlist', help='compare gate-level driver of a net')
    p_net.add_argument('good')
    p_net.add_argument('bad')
    p_net.add_argument('--net', required=True,
                        help='hierarchical net name, e.g. '
                             'u_core.u_dcache.data_csb0[0]')
    p_net.set_defaults(func=cmd_netlist)

    p_pl = sub.add_parser('placement', help='compare DEF placement density/distance')
    p_pl.add_argument('good')
    p_pl.add_argument('bad')
    p_pl.add_argument('--box', nargs=4, type=float, metavar=('X0', 'Y0', 'X1', 'Y1'),
                       required=True, help='bounding box in microns')
    p_pl.add_argument('--exclude-substr', default=None,
                       help='cell-name substring to treat as a macro '
                            '(excluded from stdcell count, counted separately)')
    p_pl.add_argument('--driver-inst', default=None,
                       help='optional: a stable hierarchical instance name '
                            '(e.g. an ICG cell) whose distance to a known pin '
                            'location should be compared')
    p_pl.add_argument('--pin-xy', nargs=2, type=float, metavar=('X', 'Y'),
                       default=None, help='absolute (x,y) in microns of the '
                       'target pin, required with --driver-inst')
    p_pl.set_defaults(func=cmd_placement)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
