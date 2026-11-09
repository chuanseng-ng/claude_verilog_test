#!/bin/bash
# step4_fixups.sh -- repairs after the b7/b8 chains (2026-11-09): (1) iolat tables + the per-view runs redone for the four b7/b8 arms (mk_iolat_tables.py failed when run while the other arm was half measured),
# (2) OpenROAD B2: GDS inspect + fixed copy (the earlier std-cell Magic run read a nonexistent GDS and reported 0 items), (3) Magic DRC std-cell-GDS mode for openroad, icc2_b8, innovus_b8
# (b8_master.sh clobbered its loop variable: it ran make ARM=13).  Resumable (step4_fixups/*.done).
cd "$(dirname "$0")"; M=step4_fixups; mkdir -p $M; L=step4_fixups.log
LK=../pdk/sky130/scripts/licensed_lock.sh
gate() { while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); av=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$av" -ge 12 ] && break; sleep 30; done; }
if [ ! -f $M/pv.done ]; then
  for d in chain_b7_icc2 chain_b7_innovus chain_b8_icc2 chain_b8_innovus; do rm -f $d/pv_*.done $d/iolat_tables.done; done
  for x in "b7 icc2" "b7 innovus" "b8 icc2" "b8 innovus"; do set -- $x; echo "$(date +%T) chain_$1_all.sh $2 (pv redo)" >> $L; ./chain_$1_all.sh $2; done; echo 0 > $M/pv.done
fi
if [ ! -f $M/openroad_gds.done ]; then
  gate; $LK bash -c "make -C drclvs ARM=openroad PIN_MODE=none inspect fixgds > drclvs/runs/openroad/logs/make_inspect_fixgds.log 2>&1"; echo $? > $M/openroad_gds.done
  echo "$(date +%T) openroad inspect/fixgds rc=$(cat $M/openroad_gds.done); fixed gds: $(ls -la drclvs/runs/openroad/gds/*.fixed.gds 2>&1 | tail -1)" >> $L
fi
for arm in openroad icc2_b8 innovus_b8; do
  n=magic_$arm; [ -f $M/$n.done ] && continue; gate; sleep 60; echo "$(date +%T) start $n" >> $L
  $LK bash -c "cd drclvs && mkdir -p runs/$arm/logs && GUARD_RSS_GB=11 MDRC_TIMEOUT=43200 EXTRACT_TIMEOUT=18000 make ARM=$arm SRAM_MODE=real MDRC_STD=gds mdrc mdrc-class > runs/${arm}_mdrc_real_stdgds.make.log 2>&1"
  echo $? > $M/$n.done; echo "$(date +%T) end $n rc=$(cat $M/$n.done): $(tail -1 drclvs/runs/${arm}_mdrc_real_stdgds.make.log)" >> $L
done
echo "$(date +%T) step4_fixups done" >> $L
