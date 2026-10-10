#!/usr/bin/env bash
# Main-RTL pair: run the given gate arms and compare to rtl_main on the observations that do
# NOT depend on the APB debug handshake (commit stream, AXI writes, per-cycle trace). The
# registered APB outputs of main (999e44a) make tb_sky130_cpu_check.sv's APB sequencer
# time out on the RTL arm itself, so debug-GPR reads are unavailable for main.
# usage: main_pair_compare.sh <work_dir> <gate_arm_dir>...
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W="$1"; shift
for g in "$@"; do
  bash "$HERE/run_arm.sh" "$W/$g" "$W/progs" > /dev/null 2>&1
  echo "#### $g vs rtl_main"
  python3 "$HERE/compare_arms.py" diff "$W/rtl_main/run" "$W/$g/run" | grep -E "^[a-z_0-9]+:|FAIL commit\(pc|FAIL axi-write\(addr|first (commit|AXI)" | sed 's/  (.*//'
done
