#!/bin/bash
# run_dc.sh -- ONE dc_shell run under licensed_lock + safe_run (serial host rule).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd)
RUN=$ROOT/pnr/commercial/signoff/soc_budget/runs/dc; mkdir -p $RUN; cd $RUN
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
export REPO=$ROOT RUN SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=3600
PD=$ROOT/pnr/commercial/pdk/sky130/scripts
$PD/licensed_lock.sh $PD/safe_run.sh $RUN/dc.log dc_shell -f $HERE/dc_drivers.tcl
grep -q '^DC_DONE' $RUN/dc.log && echo "DC OK" || { echo "DC FAILED"; exit 1; }
