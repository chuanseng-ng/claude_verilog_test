#!/bin/bash
# run_diag.sh <script.tcl> <arm> <log-name> [VAR=value ...]  -- one DIAGNOSTIC pt_shell on the nom_tt SPEF snapshot of that arm's judge run.
set -eu
tcl=$1; arm=$2; logn=$3; shift 3
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd); . "$HERE/arms.sh"
out=$ROOT/pnr/commercial/signoff/pt/runs${PT_SET:+_$PT_SET}/${arm}_nom_${DIAG_LIB:-tt}
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
cd "$out"
export J_LIB=${DIAG_LIB:-tt} J_ROOT=$ROOT J_NETLIST=$ROOT/$(arm_netlist "$arm") J_SPEF=$(ls $out/spef/*.spef) J_SDC=$ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc
for kv in "$@"; do export "$kv"; done
export SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=1800
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/$logn" pt_shell -f "$HERE/$tcl"
