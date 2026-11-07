#!/bin/bash
# chain_b5c.sh -- B5c: rerun 01..06 with the left-edge placement screen (B5C_SCREEN=1 in 03_place.tcl); everything else identical to b5b.
cd "$(dirname "$0")/.."
export B5C_SCREEN=1 B5C_STRAP=${B5C_STRAP:-0} B5D=${B5D:-0}
T=${TAG:-b5c_innovus}; L=runs/$T/chain.log; : > $L
for s in 01_floorplan 02_pdn 03_place 04_cts 05a_route; do
  echo "$(date +%T) start $s" >> $L; scripts/run_stage.sh $s $T > runs/$T/$s.out 2>&1; echo "$(date +%T) end $s rc=$?" >> $L
  grep -q "STAGE_SAVED" runs/$T/logs/$s.log || { [ $s = 05a_route ] || { echo "stage $s failed" >> $L; exit 1; }; }
done
n=$(grep -E 'Total Violations' runs/$T/reports/drc_after_route.txt | grep -oE '[0-9]+' | head -1); echo "DRC after route: $n" >> $L
FROMLBL=05a_routed
if [ "${n:-1}" != "0" ]; then
  echo "$(date +%T) start 05b_repair" >> $L; scripts/run_stage.sh 05b_repair $T > runs/$T/05b.out 2>&1
  [ -d runs/$T/dbs/05b_repair.enc.dat ] && FROMLBL=05b_repair
fi
echo "$(date +%T) start 05_route from $FROMLBL" >> $L
FROM_LABEL=$FROMLBL scripts/run_stage.sh 05_route $T > runs/$T/05.out 2>&1
echo "$(date +%T) start 06_finish" >> $L
FROM_LABEL=05_route scripts/run_stage.sh 06_finish $T > runs/$T/06.out 2>&1
echo "$(date +%T) chain done" >> $L
