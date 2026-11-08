#!/bin/bash
# resumable: clip windows from each arm's GDS, then Magic DRC with std cells = LEF abstracts (production) vs GDS cells (A/B).
cd "$(dirname "$0")/.."; D=$PWD; O=$D/nwell4/out; R=$D/../../
while [ ! -f $O/chain.done ]; do sleep 20; done
gate(){ while :; do l=$(cut -d' ' -f1 /proc/loadavg); m=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); [ ${l%.*} -lt 6 ] && [ $m -ge 6 ] && break; sleep 30; done; }
job(){ n=$1; shift; [ -f $O/$n.done ] && return 0; gate
  SAFE_MIN_AVAIL_GB=5 SAFE_TIMEOUT=2400 $D/scripts/guard_run.sh $O/$n.log nw4_$n $D/scripts/ctr.sh nw4_$n "$@" && touch $O/$n.done; sleep 60; }
declare -A GDS=( [icc2_b6]=$D/runs/icc2_b6/gds/rv32i_cpu_top.fixed.gds [innovus_b6]=$D/runs/innovus_b6/gds/rv32i_cpu_top.fixed.gds [openroad]=$R/runs/openroad/rv32i_cpu_top.gds )
declare -A WIN=( [P]=0,0,101,930 [C]=0,419,700,519 [F]=1250,925,1580,1265 )
for arm in icc2_b6 innovus_b6 openroad; do for w in P C F; do
  clip=$O/clip_${arm}_$w.gds
  job clip_${arm}_$w klayout -b -r $D/nwell4/clip_gds.py -rd gds=${GDS[$arm]} -rd top=rv32i_cpu_top -rd box=${WIN[$w]} -rd name=clip_top -rd out=$clip
  for std in lef gds; do
    n=m_${arm}_${w}_$std; e=$O/$n.env.tcl
    { cat $D/runs/icc2_b6/mdrc_real/env.tcl; echo "set ::env(DESIGN_NAME) clip_top"; echo "set ::env(CURRENT_GDS) $clip"; echo "set ::env(STD) $std"; echo "set ::env(STEP_ID) Magic.DRC"; } > $e
    job $n bash $D/scripts/in_container/magic_step.sh $e $O/$n $D/nwell4/magic_drc_variant.tcl
  done
done; done
echo done > $O/chain_ab.done
