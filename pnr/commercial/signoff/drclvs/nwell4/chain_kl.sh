#!/bin/bash
# resumable: one KLayout nsc check per arm, done markers in nwell4/out
cd "$(dirname "$0")/.."; D=$PWD; O=$D/nwell4/out; R=$D/../../
run(){ n=$1; gds=$2; bx=$3; [ -f $O/$n.done ] && return 0
  while :; do l=$(cut -d' ' -f1 /proc/loadavg); m=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); [ ${l%.*} -lt 6 ] && [ $m -ge 6 ] && break; sleep 30; done
  SAFE_MIN_AVAIL_GB=5 SAFE_TIMEOUT=3000 $D/scripts/guard_run.sh $O/$n.log nw4_$n $D/scripts/ctr.sh nw4_$n klayout -b -r $D/nwell4/nwell_nsc_check.py -rd gds=$gds -rd boxes=$bx -rd top=rv32i_cpu_top -rd out=$O/$n.report.txt && touch $O/$n.done
  sleep 60; }
run icc2_b6 $D/runs/icc2_b6/gds/rv32i_cpu_top.fixed.gds $D/runs/icc2_b6/sram_boxes.txt
run innovus_b6 $D/runs/innovus_b6/gds/rv32i_cpu_top.fixed.gds $D/runs/innovus_b6/sram_boxes.txt
run openroad $R/runs/openroad/rv32i_cpu_top.gds $D/runs/openroad_ref/sram_boxes.txt
echo chain done > $O/chain.done
