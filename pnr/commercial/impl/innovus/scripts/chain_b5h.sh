#!/bin/bash
# chain_b5h.sh -- B5h: rerun 01..05 from the start of P&R with the b5f/b5g physical setup (B5C_SCREEN B5D B5F, no extra strap keep-out) PLUS B5H=1:
#   capTable rc_nom (captbl6) in every stage, symmetric SDC-visible I/O latency (clk_io), ccopt update_io_latency false.
#   Stops after the post-route optimisation (05_route); 05g/05h repair and 06_finish/07 are run by hand once the result is read.
cd "$(dirname "$0")/.."
export B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0 B5H=1
T=b5h_innovus; mkdir -p runs/$T; L=runs/$T/chain.log
: >> $L
run() { scripts/gate_host.sh || exit 1; echo "$(date +%T) start $1" >> $L; scripts/run_stage.sh $1 $T > runs/$T/$1.out 2>&1; echo "$(date +%T) end $1 rc=$?" >> $L; }
[ -s captbl6/sky130A_nom_li1m1.captbl ] || { echo "no captbl" >> $L; exit 1; }
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
scripts/gate_host.sh || exit 1
echo "$(date +%T) start 05_route from $FROMLBL" >> $L
FROM_LABEL=$FROMLBL scripts/run_stage.sh 05_route $T > runs/$T/05.out 2>&1
echo "$(date +%T) end 05_route rc=$?  chain (to 05_route) done" >> $L
