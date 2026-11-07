#!/bin/bash
# run_stage.sh <NN_stage> [TAG] -- run one Innovus stage script under safe_run.sh (memory cap, load gate, process-group kill).
#   Log: runs/<TAG>/logs/<stage>.log ; wall + peak RSS: runs/<TAG>/logs/<stage>.time
set -u
S=$1; TAG=${2:-b5b_innovus}
IMPL=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$IMPL/../../../.." && pwd)
PDKDIR=$REPO/pnr/commercial/pdk/sky130
RUN=$IMPL/runs/$TAG
mkdir -p $RUN/logs
source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1
export REPO PDKDIR RUN TAG HERE=$PDKDIR
export SAFE_MEM_MAX=${SAFE_MEM_MAX:-7G} SAFE_THREADS=2 SAFE_TIMEOUT=${SAFE_TIMEOUT:-10800}
name=$(basename $S .tcl)
cd $RUN
/usr/bin/time -v -o $RUN/logs/$name.time $PDKDIR/scripts/safe_run.sh $RUN/logs/$name.log \
  innovus -nowin -files $IMPL/scripts/$name.tcl -log $RUN/logs/$name.innovus.log -overwrite
rc=$?
echo "innovus $name rc=$rc"
grep -E "Elapsed time|Maximum Resident|Elapsed \(wall" $RUN/logs/$name.time | tr '\n' ' '; echo
grep -cE '^\*\*ERROR' $RUN/logs/$name.log | sed 's/^/tool ERROR lines: /'
exit $rc
