#!/bin/bash
# finish_chain_b5m.sh -- after 05m_eco: 06_finish (fill, final reports, outputs) then 07_write_verilog on the 05i_eco block, both under ONE licensed-tool lock hold.
HERE=$(cd "$(dirname "$0")/.." && pwd); RUN=$HERE/runs/b5m_icc2
export B5E_FINISH_BASE=${B5M_BASE:-05m_exp}
for s in 06_finish 07_write_verilog_m; do
  t0=$(date +%s); $HERE/scripts/run_stage.sh $s b5m_icc2; rc=$?; t1=$(date +%s)
  rss=$(grep "Maximum resident set size" $RUN/logs/$s.time | awk '{printf "%d", $6/1024}')
  echo "$(date +%FT%T) $s rc=$rc wall_s=$((t1-t0)) peak_rss_mb=$rss" | tee -a $RUN/reports/stage_markers.txt
  [ $rc -eq 0 ] || exit 1
done
echo "$(date +%FT%T) finish_chain_b5m done" | tee -a $RUN/reports/stage_markers.txt
