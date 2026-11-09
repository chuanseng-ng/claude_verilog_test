#!/bin/bash
# diag_one.sh <arm> <rc> <lib> <script.tcl> <outdir> [VAR=value ...] -- ONE DIAGNOSTIC pt_shell (safe_run.sh) on the SPEF snapshot of that arm/corner's base judge run,
# with the shared base SDC.  Writes <outdir>/<script>.log.  Used by the b7 ECO work (hold endpoint lists, dout0 net/path analysis).
set -eu
arm=$1; rc=$2; lib=$3; tcl=$4; out=$5; shift 5
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd); . "$HERE/arms.sh"
base=$ROOT/pnr/commercial/signoff/pt/runs/${arm}_${rc}_${lib}
mkdir -p "$out"; cd "$out"
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
export J_LIB=$lib J_RC=$rc J_ROOT=$ROOT J_NETLIST=${DIAG_NETLIST:-$ROOT/$(arm_netlist "$arm")} J_SPEF=$(ls $base/spef/*.spef) J_SDC=${DIAG_SDC:-$ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc} J_OUT=$out
for kv in "$@"; do export "$kv"; done
export SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=1800
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/$(basename "$tcl" .tcl)_${arm}_${rc}_${lib}.log" pt_shell -f "$HERE/$tcl"
