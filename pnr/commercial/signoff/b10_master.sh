#!/bin/bash
# b10_master.sh -- unattended, resumable driver for the Innovus b10 max-transition round (2026-11-13).  Markers: signoff/b10_master/<step>.done (rc); log signoff/b10_master.log.  Re-run the same command to resume:
#   cd pnr/commercial/signoff && setsid nohup ./b10_master.sh > b10_master.stdout 2>&1 &
#   1 inn_chain  : Innovus b10 finish + restream (impl/innovus/scripts/chain_inn_b10.sh; the ECO stage 10_eco is skipped when its marker exists)
#   2 inn_verify : chain_b10_all.sh innovus (LVS, KLayout, deck antenna, LEC + negative controls, StarRC x3, PT judge base/own/iolat x 9, clk latency, iolat tables, iolat_pv) -- no Magic
#   3 lef_obs    : lef_vs_gds_obs.py evidence on the b10 layout
#   4 magic      : Magic std-cell GDS, ALONE, ONE attempt, 1 h wall cap (a stall = NOT RUN; marker *.observed records size / time)
# One licensed tool at a time; stagger: load1 < 6, MemAvailable > 6 GB (Magic > 12 GB), >= 60 s between job starts.  Nothing here edits docs or commits.  No pgrep -f self-match: only pgrep -x / pid files.
cd "$(dirname "$0")"; M=b10_master; mkdir -p $M; L=b10_master.log; LAST=0
LK=../pdk/sky130/scripts/licensed_lock.sh; REPO=$(cd ../../.. && pwd)
stagger() { local now l a need=${1:-6}; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a" -gt "$need" ] && break; sleep 20; done; LAST=$(date +%s); }
step() { local n=$1; shift; [ -f $M/$n.done ] && { echo "$(date +%T) skip $n (rc=$(cat $M/$n.done))" >> $L; return 0; }
  stagger; echo "$(date +%T) start $n" >> $L; "$@" > $M/$n.out 2>&1; local rc=$?; echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done; return $rc; }
step inn_chain bash -c "cd ../impl/innovus && scripts/chain_inn_b10.sh"
step inn_verify bash -c "./chain_b10_all.sh innovus"
step lef_obs bash -c "source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1; S=\$PDK_ROOT/sky130A/libs.ref/sky130_sram_macros; drclvs/scripts/ctr.sh b10_lef_obs klayout -b -r drclvs/scripts/lef_vs_gds_obs.py -rd gds=\$S/gds/sky130_sram_1kbyte_1rw1r_32x256_8.gds -rd lef=\$S/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef -rd viol=$REPO/pnr/commercial/impl/innovus/runs/b10_innovus/reports/final_drc.txt -rd deffile=$REPO/pnr/commercial/impl/innovus/runs/b10_innovus/out/rv32i_cpu_top.def > drclvs/reports/lef_vs_gds_obs_innovus_b10.txt 2>&1"
magic_try() { # magic_try <drclvs arm>
  local A=$1 cn=${1}_mdrc_real_stdgds f=drclvs/runs/$1/mdrc_real_stdgds/reports/drc_violations.magic.rpt t0=$(date +%s)
  [ -f chain_b10_innovus/magic_drc.done ] && mv chain_b10_innovus/magic_drc.done chain_b10_innovus/magic_drc.attempt_prev.done
  rm -f $f
  ( sleep 3700; podman stop -t 5 $cn >/dev/null 2>&1; echo "$(date +%T) cap reached: podman stop $cn" >> $L ) & local w=$!
  B10_ONLY=magic_drc B10_MAGIC=1 MDRC_TIMEOUT=3600 ./chain_b10_all.sh innovus; local rc=$(cat chain_b10_innovus/magic_drc.done 2>/dev/null)
  kill $w 2>/dev/null; wait $w 2>/dev/null
  echo "arm=innovus rc=$rc wall_s=$(( $(date +%s)-t0 )) report_bytes=$(stat -c %s $f 2>/dev/null) report_lines=$(wc -l < $f 2>/dev/null)" > chain_b10_innovus/magic_retry.observed
  cat chain_b10_innovus/magic_retry.observed >> $L
}
step magic bash -c "$(declare -f stagger magic_try); LAST=0; L=$L; M=$M; stagger 12; magic_try innovus_b10"
echo "$(date +%T) b10_master done" >> $L
