#!/bin/bash
# queue_extraction2.sh -- successor to queue_extraction.sh after Techgen nom hit the old 4 h timeout (47 %, 2026-10-26).
# Waits for the in-flight grdgenxo min (pid given as $1), then grdgenxo max and Techgen nom/min/max (12 h cap each).
here=$(cd "$(dirname "$0")" && pwd)
source "$here/../../../../../tools/eda/pd_env.sh" >/dev/null 2>&1
log=$here/../build/logs/queue.log
step() { echo "$(date -Is) START $*" >> "$log"; "$@" >> "$log" 2>&1; echo "$(date -Is) END rc=$? $*" >> "$log"; }
[ -n "${1:-}" ] && [ "$1" != - ] && while kill -0 "$1" 2>/dev/null; do sleep 60; done
[ -z "${SKIP_GRDGENXO:-}" ] && step "$here/run_grdgenxo.sh" max
export TECHGEN_CPUS=${TECHGEN_CPUS:-2}
TECHGEN_RESTART=${TECHGEN_RESTART_NOM:-} step "$here/run_techgen.sh" nom
for c in min max; do step "$here/run_techgen.sh" $c; done
echo "$(date -Is) QUEUE2 DONE" >> "$log"
