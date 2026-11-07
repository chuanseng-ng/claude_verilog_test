#!/bin/bash
# StarRC nom/min/max for ICC2 b5i (arm icc2b5i), strictly one at a time; skips corners already complete.
# Every StarXtract launch holds the host-wide licensed-tool lock for the whole tool lifetime (flock; pgrep checks alone are racy), then applies the memory gate.
cd "$(dirname "$0")/.."
LOCK=/tmp/claude-1001/licensed_tool.lock
for c in ${CORNERS:-nom min max}; do
  [ -f runs/icc2b5i_$c/star/.starrc_complete ] && continue
  echo "$(date +%T) wait lock starrc $c"
  flock $LOCK bash -c "GATE_LIGHT=1 ../../impl/innovus/scripts/gate_host.sh || exit 1; echo \"\$(date +%T) start starrc $c\"; scripts/run_starrc.sh icc2b5i $c > runs/icc2b5i_$c.out 2>&1; echo \"\$(date +%T) end starrc $c rc=\$?\""
done
