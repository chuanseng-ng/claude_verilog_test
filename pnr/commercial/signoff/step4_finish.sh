#!/bin/bash
# step4_finish.sh -- after b8r2_flow.sh (b8 round 2 + verification chains): Magic DRC std-cell-GDS mode on the ROUND-2 layouts of icc2_b8 and innovus_b8 (one at a time, MemAvailable >= 12 GB),
# the dout0 / read-path diagnostics for the four final-candidate arms, and LAST, ALONE: the OpenROAD B2 std-cell-GDS Magic run (its first real attempt coincided with a host hang at ~07:36 on 2026-11-09,
# so it runs with a tighter watchdog: GUARD_RSS_GB=10, GUARD_MIN_GB=3).  Resumable (step4_finish/*.done).
cd "$(dirname "$0")"; M=step4_finish; mkdir -p $M; L=step4_finish.log
until grep -q "b8r2 verification chains done" b8r2.log 2>/dev/null; do sleep 60; done
LK=../pdk/sky130/scripts/licensed_lock.sh
gate() { while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); av=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$av" -ge 12 ] && break; sleep 30; done; }
mag() { local arm=$1 n=magic_$1; [ -f $M/$n.done ] && return; gate; sleep 60; echo "$(date +%T) start $n" >> $L
  $LK bash -c "cd drclvs && mkdir -p runs/$arm/logs && GUARD_RSS_GB=${GRSS:-11} GUARD_MIN_GB=${GMIN:-1.5} MDRC_TIMEOUT=43200 EXTRACT_TIMEOUT=18000 make ARM=$arm SRAM_MODE=real MDRC_STD=gds mdrc mdrc-class > runs/${arm}_mdrc_real_stdgds.make.log 2>&1"
  echo $? > $M/$n.done; echo "$(date +%T) end $n rc=$(cat $M/$n.done): $(tail -1 drclvs/runs/${arm}_mdrc_real_stdgds.make.log)" >> $L; }
mag icc2_b8; mag innovus_b8
for arm in icc2b6 icc2b8 innovusb6 innovusb8; do case $arm in icc2*) L2=icc2;; *) L2=innovus;; esac
  for c in "nom tt" "nom ss" "max ss" "nom ff"; do set -- $c; n=dout_${arm}_$1_$2; [ -f $M/$n.done ] && continue; gate
    $LK bash -c "cd pt && scripts/diag_one.sh $arm $1 $2 diag_dout_paths.tcl $PWD/pt/diag_dout2 DOUT_PINS=$PWD/../impl/$L2/eco_b7/dout0_violators_b6.txt" > $M/$n.out 2>&1; echo $? > $M/$n.done; done; done
GRSS=10 GMIN=3 mag openroad
echo "$(date +%T) step4_finish done" >> $L
