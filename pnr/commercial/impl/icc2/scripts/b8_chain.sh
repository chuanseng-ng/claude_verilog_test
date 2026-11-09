#!/bin/bash
# b8_chain.sh [FIRST] [LAST] -- resumable ICC2 b8 stage chain (b8 = b6 flow on the FLIPPED I-cache floorplan pnr/sky130/cpu/macro_placement_flipic.cfg + the b7 ECO set).  Same rules as b6_chain.sh
#   (one licensed tool at a time via launch_stage.sh, load1<6, MemAvailable>6 GB, >=60 s between starts, done markers in runs/b8_icc2/markers).  Stages: B8_STAGES.
set -u
TAG=b8_icc2
HERE=$(cd "$(dirname "$0")/.." && pwd); RUN=$HERE/runs/$TAG; M=$RUN/markers; CL=$RUN/reports/chain.log
mkdir -p $M $RUN/reports $RUN/logs $RUN/eco_in
export MACRO_CFG=macro_placement_flipic.cfg
STAGES=${B8_STAGES:-"b8_01_floorplan b8_02_pdn b8_03_place b8_04_cts b8_05_route b8_05b_write"}
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
    ok=$(grep -c "^STAGE_SAVED\|^WRITE_VERILOG\|^WRITE_PRE_DONE" $RUN/logs/$s.log 2>/dev/null)
    echo "$(date +%T) end $s rc=$rc wall_s=$(( $(date +%s)-t0 )) saved_markers=$ok" >> $CL
    if [ $rc -ne 0 ] || [ "${ok:-0}" = 0 ]; then echo "$(date +%T) b8_chain: $s FAILED -- stopping" >> $CL; exit 1; fi
    touch $M/$s.done
    case $s in b8_05b_write|b8_07_finish|b8_08_write_verilog) ;; *) rm -rf $RUN/rv32i.dlib.bak; cp -a $RUN/rv32i.dlib $RUN/rv32i.dlib.bak ;; esac
  fi
  [ "$s" = "$LAST" ] && break
done
echo "$(date +%T) b8_chain: done through ${s:-none}" >> $CL
