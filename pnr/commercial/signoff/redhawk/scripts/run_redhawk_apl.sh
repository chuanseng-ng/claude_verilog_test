#!/bin/bash
# run_redhawk_apl.sh <arm> <static|dynamic|dynamic-nodecap>  -- STEP 8 variant of run_redhawk.sh: inputs from runs/<arm>/rh_apl (or rh_apl_nodecap), work dir runs/<arm>/rh-apl-<mode>.
#   ONE redhawk batch under licensed_lock + safe_run (<=2 threads, 9G cap).  APL data + ASSUMED package model are in the generated gsr/tcl (gen_rh_inputs_apl.py).
set -u
arm=$1; mode=$2
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd)
base=${mode%%-*}; R=$ROOT/pnr/commercial/signoff/redhawk/runs/$arm
src=$R/rh_apl; [ "$mode" = dynamic-nodecap ] && src=$R/rh_apl_nodecap; [ "$mode" = dynamic-estdecap ] && src=$R/rh_apl_estdecap
w=$R/rh-apl-$mode
[ -s $src/rh.gsr ] || { echo "run gen_rh_inputs_apl.py $arm first"; exit 2; }
rm -rf "$w"; mkdir -p "$w"; cd "$w"
for f in pg.ploc power.ipf custom_pgarc.lib; do ln -s ../rh/$f $f; done; cp -L $src/rh.gsr rh.gsr
cp -L $R/rh_apl/run_$base.tcl run.tcl
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
export BROWSER=/bin/true
export SAFE_THREADS=2 SAFE_MEM_MAX=${SAFE_MEM_MAX:-9G} SAFE_MIN_AVAIL_GB=6 SAFE_TIMEOUT=${SAFE_TIMEOUT:-10800}
"$ROOT/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh" "$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$w/redhawk.log" \
  /usr/bin/time -v -o "$w/time.txt" redhawk -b run.tcl
echo "rc=$?" >> "$w/time.txt"
