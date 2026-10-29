#!/bin/bash
# run_chain.sh [TAG] [FIRST_STAGE] [LAST_STAGE] -- run the ICC2 stage chain one stage at a time under safe_run.sh (via run_stage.sh), stop on the first failure.
#   After every stage: stage marker line (wall s, peak RSS MB) in runs/<TAG>/reports/stage_markers.txt, and a backup copy of the design library
#   (runs/<TAG>/rv32i.dlib.bak) so that a host power-off loses at most the stage being written.  Resume: pass the stage to restart from.
set -u
TAG=${1:-b5e_icc2}; FIRST=${2:-01_floorplan}; LAST=${3:-07_write_verilog}
HERE=$(cd "$(dirname "$0")/.." && pwd)
RUN=$HERE/runs/$TAG
STAGES="01_floorplan 02_pdn 03_place 04_cts 05_route 05b_repair 05c_repair 06_finish 07_write_verilog"
mkdir -p $RUN/reports; on=0
for s in $STAGES; do
  [ "$s" = "$FIRST" ] && on=1
  [ $on = 1 ] || continue
  t0=$(date +%s)
  $HERE/scripts/run_stage.sh $s $TAG
  rc=$?
  t1=$(date +%s)
  rss=$(grep "Maximum resident set size" $RUN/logs/$s.time 2>/dev/null | awk '{printf "%d", $6/1024}')
  ok=$(grep -c "^STAGE_SAVED\|^WRITE_VERILOG" $RUN/logs/$s.log)
  echo "$(date +%FT%T) $s rc=$rc wall_s=$((t1-t0)) peak_rss_mb=${rss:-NA} saved_markers=$ok" | tee -a $RUN/reports/stage_markers.txt
  if [ $rc -ne 0 ] || [ "$ok" = 0 ]; then echo "run_chain: $s FAILED (rc=$rc, markers=$ok) -- stopping" | tee -a $RUN/reports/stage_markers.txt; exit 1; fi
  if [ "$s" != 07_write_verilog ]; then rm -rf $RUN/rv32i.dlib.bak; cp -a $RUN/rv32i.dlib $RUN/rv32i.dlib.bak; fi
  [ "$s" = "$LAST" ] && break
done
echo "run_chain: done through $s" | tee -a $RUN/reports/stage_markers.txt
