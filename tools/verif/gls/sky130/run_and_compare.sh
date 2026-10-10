#!/usr/bin/env bash
# Run a built gate arm on all programs and diff against the RTL arm's run + sweep expectations.
# usage: run_and_compare.sh <work_dir> <gate_arm_dir_name> [rtl_arm_dir_name=rtl_arm]
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
W="$1"; G="$2"; R="${3:-rtl_arm}"
bash "$HERE/run_arm.sh" "$W/$G" "$W/progs" > /dev/null 2>&1
echo "######## $G vs $R"
python3 "$HERE/compare_arms.py" diff "$W/$R/run" "$W/$G/run" | grep -E "IDENTICAL|DIVERGES|first (commit|AXI)|GPR x"
echo "-- port matrix ($G)"
python3 "$HERE/port_matrix.py" "$W/$G/run" "$W/progs" | tail -34
