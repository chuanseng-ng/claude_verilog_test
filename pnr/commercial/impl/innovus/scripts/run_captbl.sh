#!/bin/bash
IMPL=$(cd "$(dirname "$0")/.." && pwd); REPO=$(cd "$IMPL/../../../.." && pwd); PDKDIR=$REPO/pnr/commercial/pdk/sky130
RUN=$IMPL/runs/captbl; mkdir -p $RUN; source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1
export REPO PDKDIR RUN HERE=$PDKDIR SAFE_MEM_MAX=4G SAFE_THREADS=1 SAFE_TIMEOUT=7200
cd $RUN
/usr/bin/time -v -o $RUN/captbl.time $PDKDIR/scripts/safe_run.sh $RUN/captbl.log innovus -nowin -files $IMPL/scripts/gen_captbl.tcl -log $RUN/captbl.innovus.log -overwrite
echo "captbl rc=$?"
