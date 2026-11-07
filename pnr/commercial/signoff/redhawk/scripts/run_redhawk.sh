#!/bin/bash
# run_redhawk.sh <arm> <static|dynamic>  -- ONE redhawk batch run in runs/<arm>/rh-<mode>/ under licensed_lock + safe_run (<=2 threads, 8G cap)
set -u
arm=$1; mode=$2   # mode: static | dynamic | dynamic-nodecap
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd)
base=${mode%%-*}; src=$ROOT/pnr/commercial/signoff/redhawk/runs/$arm/rh; [ "$mode" = dynamic-nodecap ] && src=$ROOT/pnr/commercial/signoff/redhawk/runs/$arm/rh_nodecap; w=$ROOT/pnr/commercial/signoff/redhawk/runs/$arm/rh-$mode
[ -s $src/rh.gsr ] || { echo "run gen_rh_inputs.py $arm first"; exit 2; }
rm -rf "$w"; mkdir -p "$w"; cd "$w"
for f in pg.ploc power.ipf custom_pgarc.lib; do ln -s ../rh/$f $f; done; cp -L $src/rh.gsr rh.gsr
cp -L $src/run_$base.tcl run.tcl
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
export SAFE_THREADS=2 SAFE_MEM_MAX=${SAFE_MEM_MAX:-9G} SAFE_MIN_AVAIL_GB=6 SAFE_TIMEOUT=${SAFE_TIMEOUT:-10800}
"$ROOT/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh" "$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$w/redhawk.log" \
  /usr/bin/time -v -o "$w/time.txt" redhawk -b run.tcl
echo "rc=$?" >> "$w/time.txt"
