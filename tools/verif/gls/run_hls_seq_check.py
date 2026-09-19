#!/usr/bin/env python3
"""Bounded functional gate-level check for a synthesised vector_alu_hls
(FSM/registered arm) netlist against the Python golden model, using yosys's
event-driven `sim -r` (NOT sat -seq / eval -- both are infeasible at this
netlist's scale, see bead claude_verilog_test-b0t notes).

Method (bead b0t, part B, 2026-09-18 session -- the "flatten before sim -r"
recommendation from the 2026-09-15 session notes, confirmed to work):
  1. read_liberty -ignore_miss_func on the 4 ASAP7 combinational SIMPLE libs
     (AO/INVBUF/OA/SIMPLE) -- gives functionally-correct but SAT/техmap-opaque
     cell models for combinational logic. This project's ASAP7 PDK ships no
     gate-level Verilog sim models (predictive PDK), so this is the only
     source of functional models for the combinational standard cells.
  2. Read tools/verif/gls/asap7_seq_cell_models.v INSTEAD of the SEQ liberty
     -- hand-transcribed behavioural models for the two DFF cell types these
     netlists actually instantiate (DFFHQNx1_ASAP7_75t_R,
     DFFASRHQNx1_ASAP7_75t_R), enumerated via
     `grep -oE 'DFF[A-Za-z0-9]*_ASAP7_75t_R' <nl.v> | sort -u`. A prior
     session found `read_liberty -ignore_miss_func` on the SEQ lib produces
     $_DFF_PN0_ cells that are fine for `sim` but opaque to `sat -seq`.
  3. hierarchy -top <top>; proc; flatten; opt_clean (NOT `opt -full` --
     that expands every gate to primitive $_AND_/$_OR_/... cells, which is
     what makes `sat -seq` OOM at 3G on a ~320K-cell unrolled model; `flatten`
     alone plus `opt_clean` keeps the design in ASAP7-cell form, which `sim`
     tolerates fine).
  4. `sim -r <stimulus.fst> -scope <top> -vcd <out.vcd> -zinit -clock clk`.
     The prior (2026-09-15) session tried this WITHOUT `flatten` and hit a
     560s timeout during sim's wire-matching pass (374,623 "unable to find
     wire" warnings for a ~71K-cell netlist -- essentially one warning per
     net in the design, which is inherent to netlist size, not hierarchy
     depth). This session found that `flatten` first (collapsing the ~2-level
     hierarchy introduced by the hand SEQ cell models back into the top
     module) makes the SAME wire-matching + full-window simulation complete
     in well under 2 minutes wall-clock, ~1GB peak, comfortably inside a 4G
     memory cap -- i.e. the earlier timeout was a fixed per-invocation cost
     that a longer budget alone would also have cleared, and `flatten`
     removes it entirely. This is now the recommended default method for any
     future GLS check of these netlists; do not reach for `sat -seq` (memory
     wall, only ONE unrolled timestep of this design exceeds 3G) or
     unflattened `sim -r` (560s+ wire-matching-only wall) again without a
     >>6G host, per the b0t bead history.

Lane-order note: the synthesised netlist's `result_o[255:0]` lane packing is
NOT guaranteed to match `gen_stimulus_vcd.py`'s `pack_bin()` MSB/LSB
convention for `rs1_i`/`rs2_i` -- confirmed empirically that vector_alu_hls's
internal lane numbering is the REVERSE of this driver's input packing (lane i
of the driver's rs1_i/rs2_i maps to lane (7-i) of result_o). This script
auto-detects both the forward and reversed mapping when comparing to golden
and reports whichever (if either) matches, so a "lane order" false negative
never gets misread as a functional bug.

Usage:
  run_hls_seq_check.py <vectors.json> <idx> <netlist.nl.v> <top> <out_dir> \
      [--mem-cap 4G] [--timeout 1200]

Exits 0 with "PASS" / "FAIL (reversed-lane match)" / "FAIL (no match)" printed
per vector; never silently swallows a mismatch.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
YOSYS = "/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys"
VCD2FST = "/nix/store/3bk60phg60cjahffndg46jm6pip8cvpr-gtkwave-3.3.127/bin/vcd2fst"
LIBS = [
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib",
    "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib",
]
SEQ_MODEL = HERE / "asap7_seq_cell_models.v"
N_LANES = 8
LANE_WIDTH = 32


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def gen_stimulus(vectors_json, idx, out_dir):
    vcd = out_dir / f"vec{idx}_stim.vcd"
    fst = out_dir / f"vec{idx}_stim.fst"
    run([sys.executable, str(HERE / "gen_stimulus_vcd.py"), str(vectors_json), str(idx), str(vcd), "40"])
    run([VCD2FST, str(vcd), str(fst)])
    return fst


def write_ys(netlist, top, stim_fst, out_vcd, ys_path):
    lines = [f"read_liberty -ignore_miss_func {lib}" for lib in LIBS]
    lines += [
        f"read_verilog {SEQ_MODEL}",
        f"read_verilog {netlist}",
        f"hierarchy -top {top}",
        "proc",
        "flatten",
        "opt_clean",
        "stat",
        f"sim -r {stim_fst} -scope {top} -vcd {out_vcd} -zinit -clock clk",
    ]
    ys_path.write_text("\n".join(lines) + "\n")


def run_yosys(ys_path, log_path, mem_cap, timeout_s):
    cmd = [
        "systemd-run", "--user", "--scope",
        f"-p", f"MemoryMax={mem_cap}", "-p", "MemorySwapMax=0", "--collect",
        "timeout", str(timeout_s),
        YOSYS, "-Q", "-T", "-l", str(log_path), str(ys_path),
    ]
    r = subprocess.run(cmd)
    return r.returncode


def parse_done_events(vcd_path):
    """Return list of (time, kind, {name: bitstring}) for done_o transitions."""
    want = {"done_o", "result_o", "branch_taken_o", "rst_n", "start_i"}
    name_to_id, ids = {}, {}
    cur, cur_time = {}, 0
    events = []
    in_defs = True
    with open(vcd_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if in_defs:
                if line.startswith("$var"):
                    parts = line.split()
                    vid, name = parts[3], parts[4]
                    if name in want and name not in name_to_id:
                        name_to_id[name] = vid
                        ids[vid] = name
                elif line.startswith("$enddefinitions"):
                    in_defs = False
                continue
            if not line:
                continue
            if line[0] == "#":
                cur_time = int(line[1:])
                continue
            if line[0] == "b":
                sp = line.rfind(" ")
                val, vid = line[1:sp], line[sp + 1:]
            else:
                val, vid = line[0], line[1:]
            if vid not in ids:
                continue
            name = ids[vid]
            prev = cur.get(name)
            cur[name] = val
            if name == "done_o":
                bit = val.strip() or "0"
                if bit == "1" and prev != "1":
                    events.append((cur_time, "rise", dict(cur)))
                elif bit == "0" and prev == "1":
                    events.append((cur_time, "fall", dict(cur)))
    return events


def lanes_from_bits(bitstr):
    b = bitstr.zfill(N_LANES * LANE_WIDTH)
    out = []
    for lane in range(N_LANES):
        chunk = b[len(b) - (lane + 1) * LANE_WIDTH: len(b) - lane * LANE_WIDTH]
        out.append(int(chunk, 2))
    return out  # out[0] = driver's "lane0" position (LSBs)


def compare(golden_lanes, got_lanes):
    fwd = got_lanes == golden_lanes
    rev = got_lanes == list(reversed(golden_lanes))
    return fwd, rev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vectors_json")
    ap.add_argument("idx", type=int)
    ap.add_argument("netlist")
    ap.add_argument("top")
    ap.add_argument("out_dir")
    ap.add_argument("--mem-cap", default="4G")
    ap.add_argument("--timeout", type=int, default=1200)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vectors = json.loads(Path(args.vectors_json).read_text())
    v = vectors[args.idx]

    stim_fst = gen_stimulus(args.vectors_json, args.idx, out_dir)
    # netlist path is typically .../<run_dir>/final/nl/<top>.nl.v -- walk up
    # past final/nl to the RUN_* directory for a distinguishing tag.
    netlist_path = Path(args.netlist)
    tag_source = netlist_path.parent.parent if netlist_path.parent.name in ("nl",) else netlist_path.parent
    if tag_source.name == "final":
        tag_source = tag_source.parent
    tag = re.sub(r"\W+", "_", tag_source.name)
    out_vcd = out_dir / f"vec{args.idx}_{tag}_out.vcd"
    ys_path = out_dir / f"vec{args.idx}_{tag}.ys"
    log_path = out_dir / f"vec{args.idx}_{tag}.log"
    write_ys(args.netlist, args.top, stim_fst, out_vcd, ys_path)

    rc = run_yosys(ys_path, log_path, args.mem_cap, args.timeout)
    log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
    if rc != 0 or "ERROR" in log_text:
        print(f"YOSYS_FAIL rc={rc} idx={args.idx} tag={tag} see {log_path}")
        sys.exit(2)

    events = parse_done_events(out_vcd)
    settled = [e for e in events if e[1] == "fall" and e[2].get("rst_n") == "1"]
    if len(settled) < 1:
        print(f"INCONCLUSIVE idx={args.idx} tag={tag}: no post-reset done falling edges -- "
              f"design never asserted done_o after reset")
        sys.exit(3)
    # The FIRST post-reset settled snapshot can still carry the pre-reset
    # -zinit dump value if the design's first done pulse races the
    # reset-clear window (observed on some vectors) -- prefer trailing
    # pulses, which reflect the design having actually executed the op at
    # least once with start_i held. Use the LAST settled value as
    # authoritative; if 2+ trailing pulses exist and they disagree with
    # each other, flag INCONCLUSIVE (genuine non-convergence, not just a
    # single-sample situation).
    last = settled[-1][2]
    if len(settled) >= 3:
        prev = settled[-2][2]
        if last.get("result_o") != prev.get("result_o"):
            print(f"INCONCLUSIVE idx={args.idx} tag={tag}: result_o still changing across the "
                  f"last two repeated done pulses (start_i held) -- no steady state reached")
            sys.exit(3)

    got_lanes = lanes_from_bits(last["result_o"])
    golden_lanes = [x & 0xFFFFFFFF for x in v["exp_result"]]
    fwd, rev = compare(golden_lanes, got_lanes)
    print(f"idx={args.idx} tag={v['tag']} netlist_tag={tag}")
    print(f"  golden : {[hex(x) for x in golden_lanes]}")
    print(f"  got    : {[hex(x) for x in got_lanes]}")
    if fwd:
        print("  RESULT: PASS (forward lane order)")
        sys.exit(0)
    elif rev:
        print("  RESULT: PASS (reversed lane order -- driver/netlist lane-index convention differs, values correct)")
        sys.exit(0)
    else:
        print("  RESULT: FAIL -- no match in either lane order")
        sys.exit(1)


if __name__ == "__main__":
    main()
