#!/bin/bash
# b7_master.sh -- after both b7 verification chains: Magic DRC in the sign-off mode (std cells from the GDS) ONE AT A TIME (each needs MemAvailable >= 11 GB, ~25 min): b7 ICC2, b7 Innovus,
# OpenROAD B2, then the b6 arms (so the sign-off Magic figure exists for every arm, whichever generation ends up final); then the b6-vs-b7 dout0 path diagnostics.
# Resumable: signoff/b7_master/<step>.done.
cd "$(dirname "$0")"; M=b7_master; mkdir -p $M; L=b7_master.log
until grep -q "chain_b7_icc2_all done" chain_b7_icc2_all.log 2>/dev/null && grep -q "chain_b7_innovus_all done" chain_b7_innovus_all.log 2>/dev/null; do sleep 60; done
LK=../pdk/sky130/scripts/licensed_lock.sh
gate() { while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a" -ge 12 ] && break; sleep 30; done; }
mag() { # mag <ARM>
  local n=magic_$1; [ -f $M/$n.done ] && return; gate; echo "$(date +%T) start $n" >> $L; sleep 60
  $LK bash -c "cd drclvs && mkdir -p runs/$1/logs && GUARD_RSS_GB=11 MDRC_TIMEOUT=43200 EXTRACT_TIMEOUT=18000 make ARM=$1 SRAM_MODE=real MDRC_STD=gds mdrc mdrc-class > runs/$1_mdrc_real_stdgds.make.log 2>&1"; echo $? > $M/$n.done; echo "$(date +%T) end $n rc=$(cat $M/$n.done)" >> $L
}
for a in icc2_b7 innovus_b7 openroad icc2_b6 innovus_b6; do mag $a; done
# dout0 path diagnostics (b6 vs b7), base SDC, PT on the judge SPEF snapshots
D=../signoff/pt; PT=pt
for arm in icc2b6 icc2b7; do for c in "nom tt" "nom ss" "max ss" "nom ff"; do set -- $c
  n=dout_${arm}_$1_$2; [ -f $M/$n.done ] && continue; gate
  $LK bash -c "cd pt && scripts/diag_one.sh $arm $1 $2 diag_dout_paths.tcl $PWD/pt/diag_dout DOUT_PINS=$PWD/../impl/icc2/eco_b7/dout_pins_dcache.txt" > $M/$n.out 2>&1; echo $? > $M/$n.done
done; done
for arm in innovusb6 innovusb7; do for c in "nom tt" "nom ss" "max ss" "nom ff"; do set -- $c
  n=dout_${arm}_$1_$2; [ -f $M/$n.done ] && continue; gate
  $LK bash -c "cd pt && scripts/diag_one.sh $arm $1 $2 diag_dout_paths.tcl $PWD/pt/diag_dout DOUT_PINS=$PWD/../impl/innovus/eco_b7/dout_pins_dcache.txt" > $M/$n.out 2>&1; echo $? > $M/$n.done
done; done
echo "$(date +%T) b7_master done" >> $L
