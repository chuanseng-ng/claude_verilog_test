#!/usr/bin/env python3
import sys

vcd_path = sys.argv[1]
want = {"commit_valid_o", "commit_insn_o", "commit_pc_o", "debug_rs1_data_o", "debug_rs2_data_o", "trap_taken_o"}
name_to_id, ids = {}, {}
cur, cur_time = {}, 0
commits = []
in_defs = True
# bead ma7 step 1: value changes inside one "#<time>" block are all
# SIMULTANEOUS per the VCD spec -- their textual order within the block is
# implementation-defined, not causal. The original per-line snapshot (check
# commit_valid_o's transition immediately when its own line is seen, using
# whatever partial `cur` state existed so far) happened to work for arm 1's
# yosys-emitted VCD only because that tool's dump order put
# commit_valid_o's line after commit_insn_o/commit_pc_o's within each block.
# Verilator's dump order puts commit_valid_o first, which made the same
# per-line logic capture a stale (pre-update) insn/pc snapshot -- not a
# functional bug in the DUT, a bug in this parser's tool-order assumption.
# Fix: buffer each block's changes and apply them atomically before testing
# for the commit_valid_o 0->1 edge, so the result no longer depends on a
# specific tool's internal dump ordering.
pending = {}


def _flush(commits, cur, pending, cur_time):
    if not pending:
        return
    was_valid = cur.get("commit_valid_o")
    cur.update(pending)
    pending.clear()
    if cur.get("commit_valid_o") == "1" and was_valid != "1":
        commits.append((cur_time, dict(cur)))


with open(vcd_path) as f:
    for line in f:
        line = line.rstrip("\n")
        if in_defs:
            # bead ma7 step 1: Verilator's VCD indents $var/$scope lines to
            # show hierarchy (e.g. "   $var wire 1 . commit_valid_o $end"),
            # unlike yosys's flattened-netlist VCD which emits them at column
            # 0. .strip() makes this parser work for both arms' VCDs.
            stripped = line.strip()
            if stripped.startswith("$var"):
                parts = stripped.split()
                vid, name = parts[3], parts[4]
                # prefer the TOP-level (non "dut."-prefixed) copy
                if name in want and (name not in name_to_id):
                    name_to_id[name] = vid
                    ids[vid] = name
            elif stripped.startswith("$enddefinitions"):
                in_defs = False
            continue
        if not line:
            continue
        if line[0] == "#":
            _flush(commits, cur, pending, cur_time)
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
        pending[name] = val
    _flush(commits, cur, pending, cur_time)

print(f"total commit_valid_o rising edges: {len(commits)}")
for t, snap in commits:
    insn = int(snap.get("commit_insn_o", "0") or "0", 2)
    pc = int(snap.get("commit_pc_o", "0") or "0", 2)
    rs1 = int(snap.get("debug_rs1_data_o", "0") or "0", 2)
    rs2 = int(snap.get("debug_rs2_data_o", "0") or "0", 2)
    trap = snap.get("trap_taken_o", "?")
    print(f"t={t:>6} pc={pc:#06x} insn={insn:#010x} rs1={rs1:#010x} rs2={rs2:#010x} trap={trap}")
