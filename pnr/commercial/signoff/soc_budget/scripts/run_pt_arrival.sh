#!/bin/bash
# run_pt_arrival.sh -- pt_arrival.tcl for tt, ss, ff, strictly serial (licensed_lock + safe_run each).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd)
RUN=$ROOT/pnr/commercial/signoff/soc_budget/runs/dc
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
export REPO=$ROOT RUN SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=1800
PD=$ROOT/pnr/commercial/pdk/sky130/scripts
mkdir -p $RUN/../pt; cd $RUN/../pt
for L in tt ss ff; do
  LIB=$L $PD/licensed_lock.sh $PD/safe_run.sh $RUN/pt_arrival_$L.log pt_shell -f $HERE/pt_arrival.tcl
  grep -q "^PT_ARRIVAL_DONE $L" $RUN/pt_arrival_$L.log || { echo "PT arrival $L FAILED"; exit 1; }
  sleep 30
done
echo "PT ARRIVAL OK"
