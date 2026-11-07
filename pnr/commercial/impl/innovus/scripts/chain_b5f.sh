#!/bin/bash
# chain_b5f.sh -- B5f: rerun 01..06 with the narrowed D-cache-column strap keep-out (B5F=1) + the b5d placement screens; stops if the PDN self-check fails.  Then 07 (re-stream + PG connectivity).
cd "$(dirname "$0")/.."
export B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0
T=b5f_innovus; mkdir -p runs/$T; L=runs/$T/chain.log
: >> $L
run() { echo "$(date +%T) start $1" >> $L; scripts/run_stage.sh $1 $T > runs/$T/$1.out 2>&1; echo "$(date +%T) end $1 rc=$?" >> $L; }
for s in 01_floorplan 02_pdn; do
  run $s; grep -q STAGE_SAVED runs/$T/logs/$s.log || { echo "stage $s failed" >> $L; exit 1; }
done
grep -E 'PDN_SELFCHECK' runs/$T/logs/02_pdn.log >> $L
grep -q 'PDN_SELFCHECK: FAIL' runs/$T/logs/02_pdn.log && { echo "PDN self-check failed - stopped" >> $L; exit 1; }
for s in 03_place 04_cts 05a_route; do
  run $s; grep -q STAGE_SAVED runs/$T/logs/$s.log || { echo "stage $s failed" >> $L; exit 1; }
done
n=$(grep -E 'Total Violations' runs/$T/reports/drc_after_route.txt | grep -oE '[0-9]+' | head -1); echo "DRC after route: ${n:-0}" >> $L
FROMLBL=05a_routed
if [ -n "$n" ] && [ "$n" != "0" ]; then
  run 05b_repair; [ -d runs/$T/dbs/05b_repair.enc.dat ] && FROMLBL=05b_repair
fi
echo "$(date +%T) start 05_route from $FROMLBL" >> $L
FROM_LABEL=$FROMLBL scripts/run_stage.sh 05_route $T > runs/$T/05.out 2>&1
echo "$(date +%T) start 06_finish" >> $L
FROM_LABEL=05_route scripts/run_stage.sh 06_finish $T > runs/$T/06.out 2>&1
echo "$(date +%T) start 07_restream" >> $L
scripts/run_stage.sh 07_restream $T > runs/$T/07.out 2>&1
echo "$(date +%T) chain done" >> $L
