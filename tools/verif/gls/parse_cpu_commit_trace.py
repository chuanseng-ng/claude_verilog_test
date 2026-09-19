#!/usr/bin/env python3
import sys

vcd_path = sys.argv[1]
want = {"commit_valid_o", "commit_insn_o", "commit_pc_o", "debug_rs1_data_o", "debug_rs2_data_o", "trap_taken_o"}
name_to_id, ids = {}, {}
cur, cur_time = {}, 0
commits = []
in_defs = True
with open(vcd_path) as f:
    for line in f:
        line = line.rstrip("\n")
        if in_defs:
            if line.startswith("$var"):
                parts = line.split()
                vid, name = parts[3], parts[4]
                # prefer the TOP-level (non "dut."-prefixed) copy
                if name in want and (name not in name_to_id):
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
        if name == "commit_valid_o":
            if val == "1" and prev != "1":
                commits.append((cur_time, dict(cur)))

print(f"total commit_valid_o rising edges: {len(commits)}")
for t, snap in commits:
    insn = int(snap.get("commit_insn_o", "0") or "0", 2)
    pc = int(snap.get("commit_pc_o", "0") or "0", 2)
    rs1 = int(snap.get("debug_rs1_data_o", "0") or "0", 2)
    rs2 = int(snap.get("debug_rs2_data_o", "0") or "0", 2)
    trap = snap.get("trap_taken_o", "?")
    print(f"t={t:>6} pc={pc:#06x} insn={insn:#010x} rs1={rs1:#010x} rs2={rs2:#010x} trap={trap}")
