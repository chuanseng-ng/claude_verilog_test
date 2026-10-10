#!/usr/bin/env bash
# Independent-simulator arm: the original ma7/u99 yosys `sim` harness (Liberty-derived cell
# models, cycle-based) on one ASAP7 netlist; then print the captured DBG_GPR[4] read and the
# first commits.
# usage: run_yosys_gate.sh <netlist.v (physical cells stripped)> <straight|branch> <out_dir> [mem_cap]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLS="$HERE/.."
NL="$1"; PROG="$2"; OUT="$3"; CAP="${4:-5G}"
if [ "$PROG" = straight ]; then S="$GLS/run_cpu_macro_check.sh"; V=cpu_gate_out.vcd; else S="$GLS/run_cpu_macro_check_branch.sh"; V=cpu_gate_out_branch.vcd; fi
bash "$S" "$NL" "$OUT" "$CAP" > "$OUT.log" 2>&1 || true
python3 "$HERE/../sky130/vcd_last.py" "$OUT/$V" apb_prdata_captured apb_prdata_captured_valid
python3 "$GLS/parse_cpu_commit_trace.py" "$OUT/$V" | sed -n '1,12p'
