#!/bin/bash
# b6_chain.sh [FIRST] [LAST] -- resumable ICC2 b6 stage chain.  One heavy tool at a time (host-wide licensed_lock.sh via launch_stage.sh), staggered:
#   before each stage wait for loadavg1 < 6 and MemAvailable > 6 GB, then >= 60 s since the previous job started.  Every step logs start/end to runs/b6_icc2/reports/chain.log
#   and writes runs/b6_icc2/markers/<stage>.done only when the stage log carries a STAGE_SAVED/WRITE_VERILOG marker; steps with a done marker are skipped on re-run.
#   The design library is copied to rv32i.dlib.bak after each stage so a host crash loses at most the stage being written.
set -u
TAG=b6_icc2
HERE=$(cd "$(dirname "$0")/.." && pwd); RUN=$HERE/runs/$TAG; M=$RUN/markers; CL=$RUN/reports/chain.log
mkdir -p $M $RUN/reports $RUN/logs
STAGES=${B6_STAGES:-"b6_01_floorplan b6_02_pdn b6_03_place b6_04_cts b6_05_route b6_06_eco b6_07_finish b6_08_write_verilog"}
FIRST=${1:-}; LAST=${2:-}; on=1; [ -n "$FIRST" ] && on=0
LAST_START=0
stagger() {
  local now l a; now=$(date +%s); [ $((now-LAST_START)) -lt 60 ] && sleep $((60-(now-LAST_START)))
  while :; do
    l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo)
    [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20
  done
  LAST_START=$(date +%s)
}
export SAFE_MEM_MAX=${SAFE_MEM_MAX:-8G} SAFE_MIN_AVAIL_GB=6 SAFE_TIMEOUT=${SAFE_TIMEOUT:-10800}
for s in $STAGES; do
  [ "$s" = "$FIRST" ] && on=1
  [ $on = 1 ] || continue
  if [ -f $M/$s.done ]; then echo "$(date +%T) skip $s (done marker)" >> $CL
  else
    stagger; echo "$(date +%T) start $s" >> $CL; t0=$(date +%s)
    $HERE/scripts/launch_stage.sh $s $TAG >> $CL 2>&1; rc=$?
    ok=$(grep -c "^STAGE_SAVED\|^WRITE_VERILOG" $RUN/logs/$s.log 2>/dev/null)
    echo "$(date +%T) end $s rc=$rc wall_s=$(( $(date +%s)-t0 )) saved_markers=$ok" >> $CL
    if [ $rc -ne 0 ] || [ "${ok:-0}" = 0 ]; then echo "$(date +%T) b6_chain: $s FAILED -- stopping" >> $CL; exit 1; fi
    touch $M/$s.done
    if [ "$s" != b6_07_finish ]; then rm -rf $RUN/rv32i.dlib.bak; cp -a $RUN/rv32i.dlib $RUN/rv32i.dlib.bak; fi
  fi
  [ "$s" = "$LAST" ] && break
done
echo "$(date +%T) b6_chain: done through ${s:-none}" >> $CL
