#!/bin/bash
# lrun.sh <stage> <tag> -- one Innovus stage under the host-wide licensed-tool flock (env passes through); appends start/end to runs/<tag>/chain.log
cd "$(dirname "$0")/.."
export B5H=1 B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0
S=$1; T=$2; L=runs/$T/chain.log; LOCK=/tmp/claude-1001/licensed_tool.lock
echo "$(date +%T) wait lock $S" >> $L
flock $LOCK bash -c "scripts/gate_host.sh || exit 1; echo \"\$(date +%T) start $S\" >> $L; scripts/run_stage.sh $S $T > runs/$T/$S.out 2>&1; echo \"\$(date +%T) end $S rc=\$?\" >> $L"
