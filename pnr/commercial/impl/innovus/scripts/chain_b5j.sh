#!/bin/bash
# chain_b5j.sh -- b5j: in-place n-well tie ECO on b5h's final pre-fill routed db, then the b5h finish (decap/fill, reports, outputs) and the GDS restream.
cd "$(dirname "$0")/.."
export B5H=1 B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0
T=b5j_innovus; mkdir -p runs/$T/dbs; L=runs/$T/chain.log
[ -d runs/$T/dbs/05_route.enc.dat ] || { cp -r runs/b5h_innovus/dbs/05_route.enc runs/b5h_innovus/dbs/05_route.enc.dat runs/$T/dbs/; echo "copied b5h 05_route db" >> $L; }
run() { scripts/gate_licensed.sh || exit 1; echo "$(date +%T) start $1" >> $L; scripts/run_stage.sh $1 $T > runs/$T/$1.out 2>&1; echo "$(date +%T) end $1 rc=$?" >> $L; }
if [ ! -d runs/$T/dbs/05j_taps.enc.dat ]; then
  run 05j_tapfix; grep -q STAGE_SAVED:\ 05j_taps runs/$T/logs/05j_tapfix.log || { echo "05j_tapfix failed" >> $L; exit 1; }
fi
grep -E "B5J|J_DRC" runs/$T/logs/05j_tapfix.log >> $L
FROM_LABEL=05j_taps run 06_finish; grep -q 'STAGE_SAVED: 06_finish' runs/$T/logs/06_finish.log || { echo "06_finish failed" >> $L; exit 1; }
run 07_restream
echo "$(date +%T) chain b5j done" >> $L
