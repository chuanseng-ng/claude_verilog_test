#!/bin/bash
# run_stage.sh <script.tcl> [TAG] -- run one ICC2 stage script under safe_run.sh (memory cap, load gate, process-group kill).
#   Log: runs/<TAG>/logs/<script>.log ; peak RSS/wall: runs/<TAG>/logs/<script>.time
set -u
S=$1; TAG=${2:-b5a_icc2}
HERE=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
PDKDIR=$REPO/pnr/commercial/pdk/sky130
RUN=$HERE/runs/$TAG
mkdir -p $RUN/logs
source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1
export REPO PDKDIR RUN TAG
export SAFE_MEM_MAX=${SAFE_MEM_MAX:-6G} SAFE_THREADS=2 SAFE_TIMEOUT=${SAFE_TIMEOUT:-7200}
name=$(basename $S .tcl)
cd $RUN
/usr/bin/time -v -o $RUN/logs/$name.time $PDKDIR/scripts/safe_run.sh $RUN/logs/$name.log icc2_shell -f $HERE/scripts/$name.tcl
rc=$?
echo "icc2 $name rc=$rc"
grep -E "Maximum memory usage for this session:|Elapsed time" $RUN/logs/$name.log | tail -2
exit $rc
