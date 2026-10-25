#!/bin/bash
# queue_extraction.sh -- run the load-gated, single-threaded vendor steps ONE AT A TIME, in priority order.
# nom first everywhere; min/max afterwards.  Progress log: build/logs/queue.log.
here=$(cd "$(dirname "$0")" && pwd)
source "$here/../../../../../tools/eda/pd_env.sh" >/dev/null 2>&1
log=$here/../build/logs/queue.log
step() { echo "$(date -Is) START $*" >> "$log"; "$@" >> "$log" 2>&1; echo "$(date -Is) END rc=$? $*" >> "$log"; }
step "$here/run_grdgenxo.sh" nom      # ~45 min single-thread
step "$here/run_techgen.sh" nom       # ~4 h single-thread (3% after 7 min measured); ICT parse verified
for c in min max; do step "$here/run_grdgenxo.sh" $c; done
for c in min max; do step "$here/run_techgen.sh" $c; done
echo "$(date -Is) QUEUE DONE" >> "$log"
