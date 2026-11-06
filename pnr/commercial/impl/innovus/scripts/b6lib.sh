#!/bin/bash
# b6lib.sh -- shared helpers for the Innovus b6 chains.  source it from impl/innovus (cwd).  One licensed tool at a time (licensed_lock.sh = host-wide flock + pgrep wait),
#   host stagger: loadavg1 < 6, MemAvailable > 6 GB, >= 60 s between job starts.  Stage = one run_stage.sh (safe_run.sh: memory cap SAFE_MEM_MAX, process-group kill).  Resumable: <run>/b6done/<name>.done holds the rc.
export B6=1 B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0 SAFE_MEM_MAX=${SAFE_MEM_MAX:-11G} SAFE_TIMEOUT=${SAFE_TIMEOUT:-28800}
T=${T:-b6_innovus}; mkdir -p runs/$T/b6done; L=runs/$T/chain.log; LK=../../pdk/sky130/scripts/licensed_lock.sh; LAST=0
stagger() {
  local now l a; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do
    l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo)
    [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20
  done
  LAST=$(date +%s)
}
# stage <donename> <script> <saved-label-that-proves-success> [VAR=val ...]
stage() {
  local n=$1 s=$2 lab=$3; shift 3
  if [ -f runs/$T/b6done/$n.done ]; then echo "$(date +%T) skip $n (done)" >> $L; return 0; fi
  stagger; echo "$(date +%T) start $n" >> $L
  env "$@" $LK scripts/run_stage.sh $s $T > runs/$T/$n.out 2>&1; local rc=$?
  local ok=1; [ -n "$lab" ] && ! grep -q "STAGE_SAVED: $lab" runs/$T/logs/$s.log && ok=0
  echo "$(date +%T) end $n rc=$rc saved_ok=$ok" >> $L
  if [ $ok = 1 ]; then echo $rc > runs/$T/b6done/$n.done; return 0; fi
  echo "$(date +%T) STOP: $n did not save $lab" >> $L; return 1
}
# job <donename> <cmd...> : any non-Innovus job (open tools, python), same staggering / markers, run from impl/innovus; rc recorded, never stops the chain
job() {
  local n=$1; shift
  if [ -f runs/$T/b6done/$n.done ]; then echo "$(date +%T) skip $n (done)" >> $L; return 0; fi
  stagger; echo "$(date +%T) start $n" >> $L
  "$@" > runs/$T/$n.out 2>&1; local rc=$?
  echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > runs/$T/b6done/$n.done; return $rc
}
