#!/bin/bash
IMPL=$(cd "$(dirname "$0")/.." && pwd); REPO=$(cd "$IMPL/../../../.." && pwd); PDKDIR=$REPO/pnr/commercial/pdk/sky130
export RUN=$IMPL/runs/b5c_innovus RUN_B5B=$IMPL/runs/b5b_innovus REPO PDKDIR HERE=$PDKDIR
source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1
export SAFE_MEM_MAX=7G SAFE_THREADS=2 SAFE_TIMEOUT=3600
cd $RUN; $PDKDIR/scripts/safe_run.sh $RUN/logs/diag.log innovus -nowin -files $IMPL/scripts/diag_congestion.tcl -log $RUN/logs/diag.innovus.log -overwrite
