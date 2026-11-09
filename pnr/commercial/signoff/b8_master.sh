#!/bin/bash
# b8_master.sh -- after both b8 verification chains: Magic DRC (std cells from the GDS) for icc2_b8 and innovus_b8 one at a time, then the dout0 / read-path diagnostics b6 vs b8 (the 163 / 161 b6 violator pins).
cd "$(dirname "$0")"; M=b8_master; mkdir -p $M; L=b8_master.log
until grep -q "chain_b8_icc2_all done" chain_b8_icc2_all.log 2>/dev/null && grep -q "chain_b8_innovus_all done" chain_b8_innovus_all.log 2>/dev/null; do sleep 60; done
LK=../pdk/sky130/scripts/licensed_lock.sh
gate() { while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a" -ge 12 ] && break; sleep 30; done; }
for a in icc2_b8 innovus_b8; do n=magic_$a; [ -f $M/$n.done ] && continue; gate; echo "$(date +%T) start $n" >> $L; sleep 60
  $LK bash -c "cd drclvs && mkdir -p runs/$a/logs && GUARD_RSS_GB=11 MDRC_TIMEOUT=43200 EXTRACT_TIMEOUT=18000 make ARM=$a SRAM_MODE=real MDRC_STD=gds mdrc mdrc-class > runs/${a}_mdrc_real_stdgds.make.log 2>&1"; echo $? > $M/$n.done; echo "$(date +%T) end $n rc=$(cat $M/$n.done)" >> $L; done
for arm in icc2b8 innovusb8; do case $arm in icc2b8) L2=icc2;; *) L2=innovus;; esac
  for c in "nom tt" "nom ss" "max ss" "nom ff"; do set -- $c; n=dout_${arm}_$1_$2; [ -f $M/$n.done ] && continue; gate
    $LK bash -c "cd pt && scripts/diag_one.sh $arm $1 $2 diag_dout_paths.tcl $PWD/pt/diag_dout DOUT_PINS=$PWD/../impl/$L2/eco_b7/dout0_violators_b6.txt" > $M/$n.out 2>&1; echo $? > $M/$n.done; done; done
echo "$(date +%T) b8_master done" >> $L
