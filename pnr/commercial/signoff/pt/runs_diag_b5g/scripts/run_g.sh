#!/bin/bash
# run_g.sh <tag> <sdc> <spef> [VAR=val ...]   -- ONE diagnostic pt_shell under safe_run.sh (<=2 threads).  Output: runs_diag_b5g/<tag>/
set -eu
tag=$1; sdc=$2; spef=$3; shift 3
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../../.." && pwd)
out=$ROOT/pnr/commercial/signoff/pt/runs_diag_b5g/$tag; mkdir -p "$out"; cd "$out"
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
export G_ROOT=$ROOT G_NETLIST=$ROOT/pnr/commercial/impl/innovus/runs/b5g_innovus/out/rv32i_cpu_top.nl.v G_SPEF=$spef G_SDC=$sdc G_OUT=$out
for kv in "$@"; do export "$kv"; done
export SAFE_THREADS=2 SAFE_MEM_MAX=${SAFE_MEM_MAX:-7G} SAFE_TIMEOUT=${SAFE_TIMEOUT:-2400}
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/pt.log" pt_shell -f "$HERE/diag_gap.tcl"
[ -s "$out/metrics.tsv" ] && grep -q '^hold_all_wns' "$out/metrics.tsv" && echo "DONE $tag" || { echo "FAILED $tag"; exit 1; }
