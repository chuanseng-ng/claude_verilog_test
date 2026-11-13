#!/bin/bash
# b9_master.sh -- unattended, resumable driver for the step-4 adopt-b9 work (2026-11-09).  Markers: signoff/b9_master/<step>.done (rc); log signoff/b9_master.log.  Re-run the same command to resume.
#   1 wait for the Quantus icc2b9 chain (started separately: ARMS=icc2b9 quantus/scripts/chain_all.sh)      2 Quantus-vs-StarRC correlation + PrimeTime nom_tt sensitivity + quantus_runs.json
#   3 Innovus b9 probe (view-only)  4 Innovus b9 ECO + finish + restream (impl/innovus/scripts/chain_inn_b9.sh)  5 Innovus b9 verification chain (chain_b9_all.sh innovus, no Magic)
#   6 Magic std-cell GDS retry, ONE attempt per layout, alone, 1 h wall cap (coordinator decision 2026-11-09 21:26): Innovus b9 first, then ICC2 b9.  A stall => NOT RUN (marker *.observed records size/time).
# One licensed tool at a time; host stagger (load1 < 6, MemAvailable > 6 GB; Magic: > 12 GB); >= 60 s between job starts.  Nothing here edits docs or commits.
cd "$(dirname "$0")"; M=b9_master; mkdir -p $M; L=b9_master.log; LAST=0
LK=../pdk/sky130/scripts/licensed_lock.sh; REPO=$(cd ../../.. && pwd)
stagger() { local now l a need=${1:-6}; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a" -gt "$need" ] && break; sleep 20; done; LAST=$(date +%s); }
step() { local n=$1; shift; [ -f $M/$n.done ] && { echo "$(date +%T) skip $n (rc=$(cat $M/$n.done))" >> $L; return 0; }
  stagger; echo "$(date +%T) start $n" >> $L; "$@" > $M/$n.out 2>&1; local rc=$?; echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done; return $rc; }
# 1
step wait_quantus bash -c 'while pgrep -f "quantus/scripts/[c]hain_all.sh" >/dev/null || pgrep -x quantus >/dev/null; do sleep 30; done; for c in nom min max; do [ -f quantus/runs/icc2b9_$c/.done ] || { echo "icc2b9_$c quantus not done"; exit 1; }; done'
# 2
step q_pt $LK bash -c "cd pt && env PT_SET=quantus PT_STARRC_DIR=pnr/commercial/signoff/quantus/runs PT_NO_MARKER=1 GATE_LIGHT=1 scripts/run_one.sh icc2b9 nom tt 1"
step q_correlate bash -c "cd quantus/scripts && CORR_TAG=_icc2b9 python3 correlate_all.py --arms icc2b9"
step q_collect bash -c "cd quantus/scripts && python3 collect_runs.py"
# 3
step inn_probe $LK bash -c "cd ../impl/innovus && scripts/run_stage.sh b9m_probe b9_innovus"
# 4 (the chain has its own stagger / licensed locks / markers in impl/innovus/runs/b9_innovus/b6done)
step inn_eco_chain bash -c "cd ../impl/innovus && scripts/chain_inn_b9.sh"
# 5
step inn_verify bash -c "./chain_b9_all.sh innovus"
# 6 Magic retries, 1 h cap each, alone
magic_try() { # magic_try <icc2|innovus> <drclvs arm> 
  local arm=$1 A=$2 cn=${2}_mdrc_real_stdgds f=drclvs/runs/$2/mdrc_real_stdgds/reports/drc_violations.magic.rpt t0=$(date +%s)
  [ -f chain_b9_$arm/magic_drc.done ] && mv chain_b9_$arm/magic_drc.done chain_b9_$arm/magic_drc.attempt_prev.done
  rm -f drclvs/runs/$A/mdrc_real_stdgds/reports/drc_violations.magic.rpt
  ( sleep 3700; podman stop -t 5 $cn >/dev/null 2>&1; echo "$(date +%T) cap reached: podman stop $cn" >> $L ) & local w=$!
  B9_ONLY=magic_drc B9_MAGIC=1 MDRC_TIMEOUT=3600 ./chain_b9_all.sh $arm; local rc=$(cat chain_b9_$arm/magic_drc.done 2>/dev/null)
  kill $w 2>/dev/null; wait $w 2>/dev/null
  echo "arm=$arm rc=$rc wall_s=$(( $(date +%s)-t0 )) report_bytes=$(stat -c %s $f 2>/dev/null) report_lines=$(wc -l < $f 2>/dev/null) rss_now_kb=$(ps -o rss= -p $(pgrep -x magicdnull | head -1) 2>/dev/null)" > chain_b9_$arm/magic_retry.observed
  cat chain_b9_$arm/magic_retry.observed >> $L
}
step magic_innovus bash -c "$(declare -f stagger magic_try); LAST=0; L=$L; M=$M; stagger 12; magic_try innovus innovus_b9"
step magic_icc2 bash -c "$(declare -f stagger magic_try); LAST=0; L=$L; M=$M; stagger 12; magic_try icc2 icc2_b9"
echo "$(date +%T) b9_master done" >> $L
