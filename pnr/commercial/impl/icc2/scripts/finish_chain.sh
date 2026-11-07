#!/bin/bash
# finish_chain.sh -- after 05z_fix: pick the better of 05z_fix / 05y_repair (fewer DRC+shorts; ties -> 05y), run 06_finish then 07_write_verilog.
HERE=$(cd "$(dirname "$0")/.." && pwd); RUN=$HERE/runs/b5e_icc2
while ! grep -q "icc2 05z_fix rc" $RUN/chain_05z.log 2>/dev/null; do sleep 15; done
fin=$(grep "^FIX_FINAL" $RUN/logs/05z_fix.log | tail -1)
d=$(echo "$fin" | sed -E 's/.*DRCs=([0-9]+).*/\1/'); s=$(echo "$fin" | sed -E 's/.*shorts=([0-9]+).*/\1/')
base=05y_repair
if [ -n "$d" ] && [ $((d+s)) -lt 2 ] && grep -q "^STAGE_SAVED: 05z_fix" $RUN/logs/05z_fix.log; then base=05z_fix; fi
echo "$(date +%FT%T) finish_chain: 05z result '$fin' -> 06_finish base $base" | tee -a $RUN/reports/stage_markers.txt
cp $RUN/rv32i.dlib $RUN/rv32i.dlib.bak2 -a 2>/dev/null
export B5E_FINISH_BASE=$base
for s in 06_finish 07_write_verilog; do
  t0=$(date +%s); $HERE/scripts/run_stage.sh $s b5e_icc2; rc=$?; t1=$(date +%s)
  rss=$(grep "Maximum resident set size" $RUN/logs/$s.time | awk '{printf "%d", $6/1024}')
  echo "$(date +%FT%T) $s rc=$rc wall_s=$((t1-t0)) peak_rss_mb=$rss" | tee -a $RUN/reports/stage_markers.txt
  [ $rc -eq 0 ] || exit 1
done
echo "$(date +%FT%T) finish_chain done" | tee -a $RUN/reports/stage_markers.txt
